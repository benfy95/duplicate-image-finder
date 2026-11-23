"""Full-size image viewer: arrow keys to flip, wheel / Ctrl +/- to zoom, drag to pan."""

import os

from PySide6.QtCore import QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout)

from ..i18n import human_size, tr
from .images import ImageLoader
from .model import KEEP_COLOR, REMOVE_COLOR, kind_text

PREVIEW = 2048      # shown first (fast); full resolution loads when zoomed in
FULL = 0            # ImageLoader size 0 = original resolution
ZOOM_MIN, ZOOM_MAX, STEP = 0.05, 16.0, 1.25


NAV_SIZE = 48      # round previous / next buttons over the image


def _chevron_icon(direction):
    """White chevron (< or >) for the round navigation buttons."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    if direction < 0:
        p.drawPolyline([QPointF(38, 16), QPointF(22, 32), QPointF(38, 48)])
    else:
        p.drawPolyline([QPointF(26, 16), QPointF(42, 32), QPointF(26, 48)])
    p.end()
    return QIcon(pm)


def _nav_button(parent, direction, tip, slot):
    b = QToolButton(parent)
    b.setIcon(_chevron_icon(direction))
    b.setIconSize(QSize(26, 26))
    b.setFixedSize(NAV_SIZE, NAV_SIZE)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)        # never steal the arrow keys
    b.setStyleSheet(f"QToolButton {{ background: rgba(0,0,0,110); border: 1px solid rgba(255,255,255,40); "
                    f"border-radius: {NAV_SIZE // 2}px; }}"
                    f"QToolButton:hover {{ background: rgba(0,0,0,185); }}"
                    f"QToolButton:pressed {{ background: rgba(60,60,60,200); }}")
    b.clicked.connect(slot)
    return b


class ZoomView(QScrollArea):
    """Scrollable image with fit-to-window or free zoom (relative to original pixels)."""

    def __init__(self, on_zoom):
        super().__init__()
        self.on_zoom = on_zoom
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidgetResizable(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)      # arrow keys go to the dialog
        self.setStyleSheet("QScrollArea { background:#202020; border:none; }")
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background:#202020; color:#bbb;")
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setWidget(self.label)
        self.pix = None
        self.orig = (1, 1)
        self.zoom = None              # None = fit to window
        self._drag = None

    def set_image(self, pix, orig_size, keep_zoom=False):
        self.pix = pix
        self.orig = (max(1, orig_size[0]), max(1, orig_size[1]))
        if not keep_zoom:
            self.zoom = None
        self.render()

    def set_text(self, text):
        self.pix = None
        self.label.setPixmap(QPixmap())
        self.label.setText(text)
        self.label.resize(self.viewport().size())

    def effective_zoom(self):
        if self.zoom is not None:
            return self.zoom
        vw, vh = self.viewport().width(), self.viewport().height()
        return min(vw / self.orig[0], vh / self.orig[1], 1.0 if max(self.orig) < 64 else 99)

    def render(self):
        if self.pix is None or self.pix.isNull():
            return
        z = self.effective_zoom()
        w, h = max(1, round(self.orig[0] * z)), max(1, round(self.orig[1] * z))
        mode = Qt.TransformationMode.SmoothTransformation if z < 2 else Qt.TransformationMode.FastTransformation
        self.label.setPixmap(self.pix.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, mode))
        self.label.resize(w, h)
        self.on_zoom(z)

    def set_zoom(self, z, anchor=None):
        """Zoom to z, keeping the image point under `anchor` (viewport coords) still."""
        old = self.effective_zoom()
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        if anchor is None:
            anchor = QPoint(self.viewport().width() // 2, self.viewport().height() // 2)
        hs, vs = self.horizontalScrollBar(), self.verticalScrollBar()
        # image coordinates (original pixels) under the anchor
        lx = anchor.x() + hs.value() - self.label.x() if self.label.width() >= self.viewport().width() else \
            anchor.x() - self.label.x()
        ly = anchor.y() + vs.value() - self.label.y() if self.label.height() >= self.viewport().height() else \
            anchor.y() - self.label.y()
        ix, iy = lx / old, ly / old
        self.zoom = z
        self.render()
        hs.setValue(round(ix * z - anchor.x()))
        vs.setValue(round(iy * z - anchor.y()))

    def fit(self):
        self.zoom = None
        self.render()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d:
            self.set_zoom(self.effective_zoom() * (STEP ** (d / 120)), e.position().toPoint())
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = (e.position().toPoint(), self.horizontalScrollBar().value(),
                          self.verticalScrollBar().value())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag:
            p0, h0, v0 = self._drag
            d = e.position().toPoint() - p0
            self.horizontalScrollBar().setValue(h0 - d.x())
            self.verticalScrollBar().setValue(v0 - d.y())

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.viewport().unsetCursor()

    def mouseDoubleClickEvent(self, e):
        # toggle 100% <-> fit
        if self.zoom is None or abs(self.effective_zoom() - 1.0) > 1e-3:
            self.set_zoom(1.0, e.position().toPoint())
        else:
            self.fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.zoom is None:
            self.render()
        self.place_nav()

    def place_nav(self):
        """Previous / next buttons centered on the left and right edges of the image area."""
        nav = getattr(self, "nav", ())
        if len(nav) == 2:
            y = (self.height() - NAV_SIZE) // 2
            nav[0].move(16, y)
            nav[1].move(self.width() - NAV_SIZE - 16, y)
            for b in nav:
                b.raise_()


class ViewerDialog(QDialog):
    def __init__(self, parent, loader, ft, members, start):
        super().__init__(parent)
        self.loader, self.ft, self.members, self.pos = loader, ft, members, start
        self.full_loader = ImageLoader(self, cache_items=3)   # few full-size images in memory
        self.resize(1250, 860)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        lay = QVBoxLayout(self)
        self.view = ZoomView(self._zoom_changed)
        lay.addWidget(self.view, 1)
        self.info = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.info)
        row = QHBoxLayout()
        # previous / next: round icon buttons over the left and right edges of the image
        self.btn_prev = _nav_button(self.view, -1, tr("prev_tip"), lambda: self.step(-1))
        self.btn_next = _nav_button(self.view, 1, tr("next_tip"), lambda: self.step(1))
        self.view.nav = (self.btn_prev, self.btn_next)
        for b in self.view.nav:
            b.setVisible(len(members) > 1)
        self.btn_fit = QPushButton(tr("zoom_fit"))
        self.btn_100 = QPushButton("100%")
        close = QPushButton(tr("close"))
        for b in (self.btn_fit, self.btn_100, close):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)        # never steal the arrow keys
        self.btn_fit.clicked.connect(self.view.fit)
        self.btn_100.clicked.connect(lambda: self.view.set_zoom(1.0))
        close.clicked.connect(self.accept)
        self.zoom_label = QLabel()
        self.hint = QLabel(tr("viewer_hint"))
        self.hint.setStyleSheet("color:gray;")
        row.addWidget(self.btn_fit)
        row.addWidget(self.btn_100)
        row.addWidget(self.zoom_label)
        row.addStretch()
        row.addWidget(self.hint)
        row.addStretch()
        row.addWidget(close)
        lay.addLayout(row)

        seen = set()

        def sc(keys, fn):
            # Each key sequence may be registered only once: Qt treats duplicates
            # as ambiguous and then fires neither.
            for k in keys:
                seq = QKeySequence(k)
                if seq.isEmpty() or seq.toString() in seen:
                    continue
                seen.add(seq.toString())
                s = QShortcut(seq, self)
                s.setContext(Qt.ShortcutContext.WindowShortcut)
                s.activated.connect(fn)
        sc(["Left", "Up", "PgUp", "Backspace"], lambda: self.step(-1))
        sc(["Right", "Down", "PgDown", "Space"], lambda: self.step(1))
        sc(["Ctrl++", "Ctrl+=", "+", "="], lambda: self.view.set_zoom(self.view.effective_zoom() * STEP))
        sc(["Ctrl+-", "-"], lambda: self.view.set_zoom(self.view.effective_zoom() / STEP))
        sc(["Ctrl+0", "0"], self.view.fit)
        sc(["Ctrl+1", "1"], lambda: self.view.set_zoom(1.0))
        sc(["Home"], lambda: self.goto(0))
        sc(["End"], lambda: self.goto(len(self.members) - 1))

        loader.loaded.connect(self._loaded)
        self.full_loader.loaded.connect(self._loaded_full)
        self._have_full = False
        self.show_current()

    # ----- navigation -----
    def step(self, d):
        self.goto((self.pos + d) % len(self.members))

    def goto(self, pos):
        self.pos = pos
        self.show_current()

    def current_path(self):
        return self.ft.paths[self.members[self.pos].idx]

    def show_current(self):
        m = self.members[self.pos]
        i = m.idx
        tag = tr("tag_remove") if m.remove else tr("tag_keep")
        color = REMOVE_COLOR.name() if m.remove else KEEP_COLOR.name()
        self.setWindowTitle(f"{os.path.basename(self.ft.paths[i])}  ({self.pos + 1}/{len(self.members)})")
        self.info.setText(
            f"<b style='color:{color}'>{tag}</b> · {kind_text(m)} · {self.ft.w[i]} × {self.ft.h[i]} · "
            f"{human_size(self.ft.size[i])} · {self.ft.fmt[i]} · ({self.pos + 1}/{len(self.members)})"
            f"<br>{self.ft.paths[i]}")
        full = self.full_loader.cache.get((self.current_path(), FULL))
        self._have_full = full is not None and not full.isNull()
        pix = full if self._have_full else self.loader.get(self.current_path(), PREVIEW)
        if pix is None:
            self.view.set_text("…")
        elif pix.isNull():
            self.view.set_text("✕")
        else:
            self.view.set_image(pix, self._orig())
        # preload neighbours so flipping is instant
        for d in (1, -1):
            j = self.members[(self.pos + d) % len(self.members)].idx
            self.loader.get(self.ft.paths[j], PREVIEW)

    def _orig(self):
        i = self.members[self.pos].idx
        return int(self.ft.w[i]), int(self.ft.h[i])

    def _loaded(self, path, size):
        if size == PREVIEW and path == self.current_path() and not self._have_full:
            pix = self.loader.get(path, PREVIEW)
            if pix is not None and not pix.isNull():
                self.view.set_image(pix, self._orig(), keep_zoom=True)
            elif pix is not None:
                self.view.set_text("✕")

    def _loaded_full(self, path, size):
        if path == self.current_path():
            pix = self.full_loader.get(path, FULL)
            if pix is not None and not pix.isNull():
                self._have_full = True
                hs, vs = self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()
                self.view.set_image(pix, self._orig(), keep_zoom=True)
                self.view.horizontalScrollBar().setValue(hs)
                self.view.verticalScrollBar().setValue(vs)

    def _zoom_changed(self, z):
        self.zoom_label.setText(f"{z * 100:.0f}%")
        # the 2048px preview is no longer sharp enough: fetch the original
        if not self._have_full and self.view.pix is not None:
            shown = max(self.view.pix.width(), self.view.pix.height())
            needed = max(self._orig()) * z
            if needed > shown * 1.05 and max(self._orig()) > shown:
                self.full_loader.get(self.current_path(), FULL)

    def done(self, r):
        for sig, slot in ((self.loader.loaded, self._loaded), (self.full_loader.loaded, self._loaded_full)):
            try:
                sig.disconnect(slot)
            except Exception:
                pass
        self.full_loader.clear_queue()
        super().done(r)
