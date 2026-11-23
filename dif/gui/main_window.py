"""Main application window."""

import csv
import json
import os
import subprocess
import sys
import time

from PySide6.QtCore import QByteArray, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QRadioButton, QSpinBox, QSplitter, QStatusBar, QStyle, QStyledItemDelegate,
    QStyleOptionButton,
    QTreeView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import CACHE_PATH, CONTACT_EMAIL, DATA_DIR, LOG_DIR, PROJECT_URL, SETTINGS_PATH, __version__
from .. import actions, i18n
from ..session_log import SessionLog
from ..engine import Cancelled, ScanEngine, ScanOptions
from ..formats import describe_supported
from ..variants import DEFAULT_PATTERNS
from ..i18n import human_size, tr
from .images import ImageLoader
from .variant_dialog import VariantDialog
from .viewer import ViewerDialog
from .model import C_DATE, C_FMT, C_FOLDER, C_MATCH, C_NAME, C_REMOVE, C_RES, C_SIZE, KEEP_COLOR, REMOVE_COLOR, \
    COLS, GroupModel, date_text, kind_text

THUMB_SIZES = {"thumb_s": 160, "thumb_m": 240, "thumb_l": 360}
THEMES = ("system", "light", "dark")
HIDEABLE_COLS = (C_MATCH, C_RES, C_SIZE, C_DATE, C_FMT, C_FOLDER)   # Select and Name always stay
COL_WIDTHS = ((C_REMOVE, 150), (C_NAME, 270), (C_MATCH, 120), (C_RES, 105), (C_SIZE, 110), (C_DATE, 130), (C_FMT, 55))
VIEW = 2048


def open_in_explorer(path, select=False):
    """Open a file / folder with its default app, or show it in the file manager."""
    try:
        if sys.platform == "win32":
            if select:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if select else ["open", path])
        else:   # Linux: most file managers cannot select a file, so open its folder
            target = os.path.dirname(path) if select and not os.path.isdir(path) else path
            subprocess.Popen(["xdg-open", target])
    except OSError:
        pass


# ---------------------------------------------------------------- threads
class ScanThread(QThread):
    progress = Signal(str, int, int)
    log = Signal(str)
    finished_ok = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, opts):
        super().__init__()
        self.opts = opts
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            eng = ScanEngine(self.opts, CACHE_PATH, progress=self.progress.emit,
                             log=self.log.emit, is_cancelled=lambda: self._cancel)
            self.finished_ok.emit(eng.run())
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:
            import traceback
            self.failed.emit(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")


class ActionThread(QThread):
    progress = Signal(int, int)
    done = Signal(object, int, str, object)  # done_idx set, failed count, csv path, [(path, ok, info)]

    def __init__(self, items, mode, roots, dest):
        super().__init__()
        self.items, self.mode, self.roots, self.dest = items, mode, roots, dest

    def run(self):
        done, fail, results = set(), 0, []
        for n, (idx, path, kept) in enumerate(self.items, 1):
            ok, info = actions.apply_one(path, self.mode, self.roots, self.dest)
            results.append((path, ok, info))
            if ok:
                done.add(idx)
            else:
                fail += 1
            self.progress.emit(n, len(self.items))
        self.done.emit(done, fail, "", results)


# ---------------------------------------------------------------- widgets
def _fmt_duration(sec):
    """1:05 / 1:02:03"""
    sec = int(round(sec))
    h, m, s = sec // 3600, sec // 60 % 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class FolderList(QTreeWidget):
    """Folders to scan: [Subfolders checkbox | path]. Accepts drag & drop of folders."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.default_recursive = True
        self.setColumnCount(2)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.header().setStretchLastSection(True)
        self.header().resizeSection(0, 110)
        self.itemChanged.connect(lambda *_: self.changed.emit())
        # Ctrl / Shift + click selects several rows; Delete or right-click > Remove
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selectedItems():
            self.remove_selected()
            return
        super().keyPressEvent(e)

    def _context_menu(self, pos):
        if not self.selectedItems():
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        n = len(self.selectedItems())
        menu.addAction(tr("remove_folders", n=n) if n > 1 else tr("remove_folder"), self.remove_selected)
        menu.exec(self.viewport().mapToGlobal(pos))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isdir(p):
                self.add_folder(p)
        e.acceptProposedAction()

    def add_folder(self, p, recursive=None):
        p = os.path.normpath(p)
        if p in self.folders():
            return
        it = QTreeWidgetItem(["", p])
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        rec = self.default_recursive if recursive is None else recursive
        it.setCheckState(0, Qt.CheckState.Checked if rec else Qt.CheckState.Unchecked)
        it.setToolTip(1, p)
        self.addTopLevelItem(it)
        self.changed.emit()

    def remove_selected(self):
        for it in self.selectedItems():
            self.takeTopLevelItem(self.indexOfTopLevelItem(it))
        self.changed.emit()

    def count(self):
        return self.topLevelItemCount()

    def clear_all(self):
        self.clear()
        self.changed.emit()

    def folders(self):
        return [self.topLevelItem(i).text(1) for i in range(self.count())]

    def entries(self):
        """[(path, include_subfolders)]"""
        return [(it.text(1), it.checkState(0) == Qt.CheckState.Checked)
                for it in (self.topLevelItem(i) for i in range(self.count()))]

    def set_all_recursive(self, on):
        for i in range(self.count()):
            self.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def retranslate(self):
        self.setHeaderLabels([tr("col_subfolders"), tr("col_folder")])
        for i in range(self.count()):
            self.topLevelItem(i).setToolTip(0, tr("subfolders_tip"))


class CheckHeader(QHeaderView):
    """Header with an ALL checkbox in the Remove column.

    Ticked = every duplicate in every group is marked (one copy per group is
    always kept); partial = some are marked; unticked = nothing marked."""
    toggled = Signal()

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.state = Qt.CheckState.Unchecked
        self.setSectionsClickable(True)

    def set_state(self, state):
        if state != self.state:
            self.state = state
            self.viewport().update()

    def _box_rect(self, section_rect):
        opt = QStyleOptionButton()
        r = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, self)
        y = section_rect.top() + (section_rect.height() - r.height()) // 2
        return QRect(section_rect.left() + 6, y, r.width(), r.height())

    def paintSection(self, painter, rect, logical):
        painter.save()
        super().paintSection(painter, rect, logical)
        painter.restore()
        if logical == C_REMOVE:
            opt = QStyleOptionButton()
            opt.rect = self._box_rect(rect)
            opt.state = QStyle.StateFlag.State_Enabled | {
                Qt.CheckState.Checked: QStyle.StateFlag.State_On,
                Qt.CheckState.PartiallyChecked: QStyle.StateFlag.State_NoChange,
            }.get(self.state, QStyle.StateFlag.State_Off)
            self.style().drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox, opt, painter, self)

    def mousePressEvent(self, e):
        logical = self.logicalIndexAt(e.position().toPoint())
        if logical == C_REMOVE:
            x0 = self.sectionViewportPosition(C_REMOVE)
            rect = QRect(x0, 0, self.sectionSize(C_REMOVE), self.height())
            # click on the box or the label toggles; leave the resize edge alone
            if e.position().x() < rect.right() - 6:
                self.toggled.emit()
                return
        super().mousePressEvent(e)


class PreviewDelegate(QStyledItemDelegate):
    """Preview cards: the selected image gets a thick frame on top of its normal
    look, so its green (KEEP) / red (REMOVE) background and text stay visible.
    White on a dark theme, Windows blue on a light one."""

    FRAME = 5               # px, drawn outside the card
    MARGIN = FRAME + 2      # each item reserves this much around its card for the frame

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width() + 2 * self.MARGIN, s.height() + 2 * self.MARGIN)

    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        full = QRect(option.rect)
        option.rect = full.adjusted(self.MARGIN, self.MARGIN, -self.MARGIN, -self.MARGIN)   # the card itself
        if selected:
            # draw the card as if unselected: the system selection fill would hide the KEEP/REMOVE color
            option.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus)
        super().paint(painter, option, index)
        if selected:
            dark = option.palette.window().color().lightness() < 128
            painter.save()
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            pen = QPen(QColor(255, 255, 255) if dark else QColor(0, 99, 177), self.FRAME)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # drawn just outside the card (in the spacing around it), so it covers nothing
            o = self.FRAME // 2 + 1
            painter.drawRoundedRect(option.rect.adjusted(-o, -o, o, o), 8, 8)
            painter.restore()


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = self._load_settings()
        i18n.set_lang(self.settings.get("lang", "en"))
        self.thumb = self.settings.get("thumb", 240)
        self.variant_patterns = self.settings.get("variant_patterns", list(DEFAULT_PATTERNS))
        self.exc_patterns_on = self.settings.get("exc_patterns_on", True)
        self.exc_prefix_on = self.settings.get("exc_prefix_on", False)
        self.exc_prefix_len = self.settings.get("exc_prefix_len", 8)
        self.result = None
        self.scan_thread = None
        self.action_thread = None
        self.preview_group = None
        self._loading = True
        self.slog = SessionLog(LOG_DIR)       # off until File > Enable logging
        self._hidden = []                     # [(group, cache ids)] kept as "not duplicates", not listed
        self.loader = ImageLoader(self)
        self.loader.loaded.connect(self._thumb_loaded)
        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self._save_settings)
        self._build()
        self._build_menus()
        self._apply_settings()
        self._connect_autosave()
        self._loading = False
        self.retranslate()
        QTimer.singleShot(50, self._detect_device)

    # ================================================================ settings
    def _load_settings(self):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _schedule_save(self, *_):
        if not self._loading:
            self._save_timer.start()

    def _save_settings(self):
        s = {
            "lang": i18n.get_lang(),
            "folders": [[p, rec] for p, rec in self.folder_list.entries()],
            "recursive": self.cb_sub.isChecked(),
            "crops": self.cb_crop.isChecked(),
            "sniff": self.cb_sniff.isChecked(),
            "similarity": self.sp_sim.value(),
            "crop_sim": self.sp_crop.value(),
            "device": self.device_pref,
            "mode": self._mode(),
            "dest": self.ed_dest.text(),
            "thumb": self.thumb,
            "theme": self.theme,
            "variant_patterns": self.variant_patterns,
            "exc_patterns_on": self.exc_patterns_on,
            "exc_prefix_on": self.exc_prefix_on,
            "exc_prefix_len": self.exc_prefix_len,
            "preview": self.act_preview.isChecked(),
            "geometry": bytes(self.saveGeometry().toBase64()).decode(),
            "window_state": bytes(self.saveState().toBase64()).decode(),
            "splitter": bytes(self.split.saveState().toBase64()).decode(),
            "header_v2": bytes(self.tree.header().saveState().toBase64()).decode(),   # v2: Date column
        }
        self.settings = s
        try:
            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            tmp = SETTINGS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SETTINGS_PATH)  # atomic: never leaves a half-written file
        except OSError:
            pass

    @staticmethod
    def _b64(s):
        return QByteArray.fromBase64(s.encode()) if s else None

    def _apply_settings(self):
        s = self.settings
        self.cb_sub.setChecked(s.get("recursive", True))
        self.folder_list.default_recursive = self.cb_sub.isChecked()
        self.folder_list.clear_all()
        for f in s.get("folders", []):
            path, rec = (f, None) if isinstance(f, str) else (f[0], bool(f[1]))  # old format: plain paths
            if os.path.isdir(path):
                self.folder_list.add_folder(path, rec)
        if not self.folder_list.count() and "folders" not in s:
            test = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "images")
            if os.path.isdir(test):
                self.folder_list.add_folder(test)
        self.cb_crop.setChecked(s.get("crops", True))
        self.cb_sniff.setChecked(s.get("sniff", False))
        self.sp_sim.setValue(s.get("similarity", 89))
        self.sp_crop.setValue(s.get("crop_sim", 80))
        self.device_pref = s.get("device", "auto") if s.get("device") in ("auto", "cpu") else "auto"
        {"move": self.rb_move, "recycle": self.rb_recycle, "delete": self.rb_delete}.get(
            s.get("mode", "move"), self.rb_move).setChecked(True)
        self.ed_dest.setText(s.get("dest", ""))
        self._set_thumb(s.get("thumb", 240), save=False)
        self._set_theme(s.get("theme", "system") if s.get("theme") in THEMES else "system", save=False)
        self.variant_patterns = s.get("variant_patterns", list(DEFAULT_PATTERNS))
        self.exc_patterns_on = s.get("exc_patterns_on", True)
        self.exc_prefix_on = s.get("exc_prefix_on", False)
        self.exc_prefix_len = s.get("exc_prefix_len", 8)
        self.act_preview.setChecked(s.get("preview", True))
        self.preview_panel.setVisible(s.get("preview", True))
        self.resize(1400, 900)
        for key, fn in (("geometry", self.restoreGeometry), ("window_state", self.restoreState),
                        ("splitter", self.split.restoreState), ("header_v2", self.tree.header().restoreState)):
            b = self._b64(s.get(key))
            if b is not None:
                fn(b)
        hdr = self.tree.header()
        hdr.setSectionsClickable(True)   # click a column title to sort
        hdr.setSectionsMovable(True)
        hdr.setFirstSectionMovable(False)
        for c in (C_REMOVE, C_NAME):       # essential columns are always shown
            hdr.setSectionHidden(c, False)
        if hdr.visualIndex(C_REMOVE) != 0:
            hdr.moveSection(hdr.visualIndex(C_REMOVE), 0)
        self._sync_column_menu()
        self._sync_menu_from_widgets()

    def _connect_autosave(self):
        for sig in (self.cb_sub.toggled, self.cb_crop.toggled, self.cb_sniff.toggled,
                    self.sp_sim.valueChanged, self.sp_crop.valueChanged,
                    self.ed_dest.textChanged,
                    self.rb_move.toggled, self.rb_recycle.toggled, self.rb_delete.toggled,
                    self.folder_list.changed, self.split.splitterMoved,
                    self.tree.header().sectionResized, self.tree.header().sectionMoved):
            sig.connect(self._schedule_save)

    def _reset_settings(self):
        if QMessageBox.question(self, tr("confirm_title"), tr("reset_q")) != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(SETTINGS_PATH)
        except OSError:
            pass
        self._loading = True
        self.settings = {}
        i18n.set_lang("en")
        self._apply_settings()
        self._loading = False
        self.retranslate()
        self._save_settings()

    # ================================================================ UI
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- top: folders + options + scan button
        top = QHBoxLayout()
        self.box_folders = QGroupBox()
        fl = QHBoxLayout(self.box_folders)
        self.folder_list = FolderList()
        self.folder_list.setMaximumHeight(110)
        fl.addWidget(self.folder_list, 1)
        fb = QVBoxLayout()
        self.btn_add = QPushButton()
        self.btn_add.clicked.connect(self._add_folder)
        self.btn_rm = QPushButton()
        self.btn_rm.clicked.connect(self.folder_list.remove_selected)
        fb.addWidget(self.btn_add)
        fb.addWidget(self.btn_rm)
        fb.addStretch()
        fl.addLayout(fb)
        self.box_folders.setMinimumWidth(460)
        top.addWidget(self.box_folders, 5)

        self.box_opts = QGroupBox()
        g = QGridLayout(self.box_opts)
        # Subfolders are chosen per folder in the folder table; this hidden box is
        # the default for newly added folders (Settings menu).
        self.cb_sub = QCheckBox(self)
        self.cb_sub.hide()
        self.cb_sub.toggled.connect(lambda on: setattr(self.folder_list, "default_recursive", on))
        self.cb_crop = QCheckBox()
        self.cb_sniff = QCheckBox()
        g.addWidget(self.cb_crop, 0, 0)
        g.addWidget(self.cb_sniff, 1, 0)
        self.lb_sim = QLabel()
        self.sp_sim = QSpinBox()
        self.sp_sim.setRange(70, 100)
        self.sp_sim.setSuffix(" %")
        self.lb_crop = QLabel()
        self.sp_crop = QSpinBox()
        self.sp_crop.setRange(50, 99)
        self.sp_crop.setSuffix(" %")
        self.cb_crop.toggled.connect(self.sp_crop.setEnabled)
        g.addWidget(self.lb_sim, 0, 2)
        g.addWidget(self.sp_sim, 0, 3)
        g.addWidget(self.lb_crop, 1, 2)
        g.addWidget(self.sp_crop, 1, 3)
        # Device and Language live in the Settings menu.
        self.device_pref = "auto"
        g.setColumnStretch(1, 1)
        top.addWidget(self.box_opts, 4)

        self.btn_scan = QPushButton()
        self.btn_scan.setMinimumSize(130, 70)
        f = self.btn_scan.font()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        self.btn_scan.setFont(f)
        self.btn_scan.clicked.connect(self._scan_clicked)
        scan_col = QVBoxLayout()
        scan_col.addWidget(self.btn_scan, 1)
        self.btn_variants = QPushButton()
        self.btn_variants.clicked.connect(self._edit_variants)
        scan_col.addWidget(self.btn_variants)
        self.btn_clear = QPushButton()
        self.btn_clear.clicked.connect(self._clear_workspace)
        scan_col.addWidget(self.btn_clear)
        top.addLayout(scan_col)
        root.addLayout(top)

        # --- middle: results tree | preview
        self.split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.lb_legend = QLabel()
        self.lb_legend.setWordWrap(True)
        self.lb_legend.setStyleSheet("padding:3px 2px;")
        legend_row = QHBoxLayout()
        self.lb_files_title = QLabel()
        self.lb_files_title.setStyleSheet("font-weight:bold; font-size:11pt; padding-right:10px;")
        legend_row.addWidget(self.lb_files_title)
        legend_row.addWidget(self.lb_legend, 1)
        ll.addLayout(legend_row)
        self.model = GroupModel(self)
        self.model.marksChanged.connect(self._update_summary)
        self.tree = QTreeView()
        self.check_header = CheckHeader(self.tree)
        self.tree.setHeader(self.check_header)
        self.tree.setModel(self.model)
        self.check_header.toggled.connect(self._toggle_all)
        self.model.marksChanged.connect(self._update_all_box)
        self.model.modelReset.connect(self._update_all_box)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.selectionModel().currentChanged.connect(self._current_changed)
        self.tree.doubleClicked.connect(self._tree_double)
        hdr = self.tree.header()
        hdr.setStretchLastSection(True)
        # click a column title to sort (again to reverse); the Select column has its checkbox
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        hdr.sectionClicked.connect(self._sort_by)
        self.model.layoutChanged.connect(self._after_sort)
        for col, w in COL_WIDTHS:
            hdr.resizeSection(col, w)
        hdr.setSectionsClickable(True)     # QTreeView turns this off when it takes the header
        hdr.setSectionsMovable(True)       # drag a column title to reorder; Select stays first
        hdr.setFirstSectionMovable(False)
        ll.addWidget(self.tree, 1)
        stats_row = QHBoxLayout()
        self.lb_stats = QLabel()
        self.lb_stats.setStyleSheet("padding:3px 2px; font-weight:bold;")
        stats_row.addWidget(self.lb_stats, 1)
        self.btn_unhide = QPushButton()
        self.btn_unhide.hide()
        self.btn_unhide.clicked.connect(self._unhide)
        stats_row.addWidget(self.btn_unhide)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setMinimumWidth(320)
        self.progress.hide()
        stats_row.addWidget(self.progress, 1)
        ll.addLayout(stats_row)
        self.model.modelReset.connect(self._update_stats)
        self.split.addWidget(left)

        self.preview_panel = QWidget()
        pl = QVBoxLayout(self.preview_panel)
        pl.setContentsMargins(0, 0, 0, 0)
        self.lb_preview = QLabel()
        self.lb_preview.setWordWrap(True)
        prev_row = QHBoxLayout()
        self.lb_preview_title = QLabel()
        self.lb_preview_title.setStyleSheet("font-weight:bold; font-size:11pt; padding-right:10px;")
        prev_row.addWidget(self.lb_preview_title)
        prev_row.addWidget(self.lb_preview, 1)
        pl.addLayout(prev_row)
        self.lb_preview_group = QLabel()       # which group the preview shows
        self.lb_preview_group.setStyleSheet("font-weight:bold; font-size:10.5pt; padding:4px 2px 2px 2px;")
        pl.addWidget(self.lb_preview_group)
        self.preview = QListWidget()
        self.preview.setViewMode(QListWidget.ViewMode.IconMode)
        self.preview.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.preview.setMovement(QListWidget.Movement.Static)
        self.preview.setSpacing(4)             # cards also keep a margin for the selection frame
        self.preview.setWordWrap(True)
        self.preview.setItemDelegate(PreviewDelegate(self.preview))
        self.preview.itemDoubleClicked.connect(self._preview_double)
        self.preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.preview.customContextMenuRequested.connect(self._preview_menu)
        pl.addWidget(self.preview, 1)
        pb = QGridLayout()
        self.btn_keep_this = QPushButton()
        self.btn_toggle = QPushButton()
        self.btn_open = QPushButton()
        self.btn_show = QPushButton()
        self.btn_keep_this.clicked.connect(self._keep_this)
        self.btn_toggle.clicked.connect(self._toggle_selected)
        self.btn_open.clicked.connect(lambda: self._open_selected(False))
        self.btn_show.clicked.connect(lambda: self._open_selected(True))
        for k, b in enumerate((self.btn_keep_this, self.btn_toggle, self.btn_open, self.btn_show)):
            pb.addWidget(b, k // 2, k % 2)
        pl.addLayout(pb)
        self.preview_panel.setMinimumWidth(300)
        self.split.addWidget(self.preview_panel)
        self.split.setSizes([800, 600])
        root.addWidget(self.split, 1)

        # --- bottom: actions
        self.box_act = QGroupBox()
        al = QGridLayout(self.box_act)
        self.rb_move = QRadioButton()
        self.rb_recycle = QRadioButton()
        self.rb_delete = QRadioButton()
        self.mode_group = QButtonGroup(self)
        for b in (self.rb_move, self.rb_recycle, self.rb_delete):
            self.mode_group.addButton(b)
            b.toggled.connect(lambda on: self._sync_menu_from_widgets() if on else None)
        self.ed_dest = QLineEdit()
        self.btn_dest = QPushButton()
        self.btn_dest.clicked.connect(self._choose_dest)
        al.addWidget(self.rb_move, 0, 0)
        al.addWidget(self.ed_dest, 0, 1)
        al.addWidget(self.btn_dest, 0, 2)
        al.addWidget(self.rb_recycle, 1, 0)
        al.addWidget(self.rb_delete, 1, 1)
        self.lb_summary = QLabel()
        self.lb_summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lb_summary.setContentsMargins(0, 0, 10, 0)     # sits just left of Apply
        al.addWidget(self.lb_summary, 0, 4, 2, 1)
        self.btn_apply = QPushButton()
        self.btn_apply.setMinimumSize(130, 50)
        fa = self.btn_apply.font()
        fa.setBold(True)
        self.btn_apply.setFont(fa)
        self.btn_apply.clicked.connect(self._apply)
        al.addWidget(self.btn_apply, 0, 5, 2, 1)
        al.setColumnStretch(1, 1)
        al.setColumnStretch(4, 1)
        root.addWidget(self.box_act)

        # --- status bar
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lb_status = QLabel()
        sb.addWidget(self.lb_status, 1)
        self.btn_errors = QPushButton()
        self.btn_errors.setFlat(True)
        self.btn_errors.hide()
        self.btn_errors.clicked.connect(self._show_errors)
        sb.addPermanentWidget(self.btn_errors)
        self.lb_dev = QLabel()
        sb.addPermanentWidget(self.lb_dev)
        self._status_key = ("ready", {})
        self._scan_stages = None
        self._result_folders = []          # folders of the scan shown (for Save progress)

    # ================================================================ menus
    def _act(self, key, slot=None, shortcut=None, checkable=False, menu=None):
        a = QAction(self)
        a.setCheckable(checkable)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if slot:
            (a.toggled if checkable else a.triggered).connect(slot)
        self._acts.append((a, key))
        if menu is not None:
            menu.addAction(a)
        return a

    def _menu(self, parent, key):
        m = parent.addMenu("")
        self._menus.append((m, key))
        return m

    def _build_menus(self):
        self._acts, self._menus = [], []
        mb = self.menuBar()

        # File
        m = self._menu(mb, "m_file")
        self._act("a_save_progress", self._save_progress, "Ctrl+S", menu=m)
        self._act("a_load_progress", self._load_progress, "Ctrl+O", menu=m)
        m.addSeparator()
        self._act("a_export_scan", self._export_scan, menu=m)
        self._act("a_import_scan", self._import_scan, menu=m)
        self._act("a_export", self._export_csv, "Ctrl+E", menu=m)
        m.addSeparator()
        self.act_log = self._act("a_logging", self._toggle_logging, checkable=True, menu=m)
        self._act("a_open_logs", lambda: (os.makedirs(LOG_DIR, exist_ok=True), open_in_explorer(LOG_DIR)), menu=m)
        m.addSeparator()
        self._act("a_exit", self.close, "Ctrl+Q", menu=m)

        # Select
        m = self._menu(mb, "m_edit")
        self._act("a_sel_all", self.model.auto_select, "Ctrl+A", menu=m)
        self._act("a_sel_exact", lambda: self.model.select_kinds({"exact"}), menu=m)
        self._act("a_sel_similar", lambda: self.model.select_kinds({"similar"}), menu=m)
        self._act("a_sel_cropped", lambda: self.model.select_kinds({"cropped"}), menu=m)
        self._act("a_sel_variants", lambda: self.model.select_kinds({"exact", "similar", "cropped", "variant"}), menu=m)
        m.addSeparator()
        self._act("a_group_mark", lambda: self._current_group_mark(True), "Ctrl+G", menu=m)
        self._act("a_group_unmark", lambda: self._current_group_mark(False), "Ctrl+Shift+G", menu=m)
        m.addSeparator()
        self._act("a_invert", self.model.invert, "Ctrl+I", menu=m)

        # View
        m = self._menu(mb, "m_view")
        self._act("a_expand", self.tree.expandAll, "Ctrl+Down", menu=m)
        self._act("a_collapse", self.tree.collapseAll, "Ctrl+Up", menu=m)
        m.addSeparator()
        self.act_preview = self._act("a_preview", self._toggle_preview, "F3", checkable=True, menu=m)
        sub = self._menu(m, "a_columns")
        self.col_acts = {}
        for col in HIDEABLE_COLS:
            a = QAction("", self, checkable=True)
            a.toggled.connect(lambda on, c=col: self._show_column(c, on))
            sub.addAction(a)
            self.col_acts[col] = a
        sub.addSeparator()
        self._act("a_reset_columns", self._reset_columns, menu=sub)
        sub = self._menu(m, "a_thumbs")
        self.thumb_group = QActionGroup(self)
        self.thumb_acts = {}
        for key, size in THUMB_SIZES.items():
            a = self._act(key, lambda on, s=size: self._set_thumb(s) if on else None, checkable=True, menu=sub)
            self.thumb_group.addAction(a)
            self.thumb_acts[size] = a

        # Settings: Device and Language, then maintenance items. The scan options
        # live in the window (Options panel, bottom bar, Variants button).
        m = self._menu(mb, "m_settings")
        self.dev_acts, self.lang_acts, self.mode_acts = {}, {}, {}
        self.menu_device = sub = self._menu(m, "device")
        grp = QActionGroup(self)
        for code in ("auto", "cpu"):
            a = QAction("", self, checkable=True)
            a.toggled.connect(lambda on, c=code: self._change_device(c) if on else None)
            grp.addAction(a)
            sub.addAction(a)
            self.dev_acts[code] = a
        sub = self._menu(m, "theme")
        grp = QActionGroup(self)
        self.theme_acts = {}
        for code in THEMES:
            a = QAction("", self, checkable=True)
            a.toggled.connect(lambda on, c=code: self._set_theme(c) if on else None)
            grp.addAction(a)
            sub.addAction(a)
            self.theme_acts[code] = a
        sub = self._menu(m, "language")
        grp = QActionGroup(self)
        for code, name in i18n.LANGS:             # names stay in their own language
            a = QAction(name, self, checkable=True)
            a.toggled.connect(lambda on, c=code: self._change_lang(c) if on else None)
            grp.addAction(a)
            sub.addAction(a)
            self.lang_acts[code] = a
        m.addSeparator()
        self._act("clear_cache", self._clear_cache, menu=m)
        self._act("a_open_data", lambda: (os.makedirs(DATA_DIR, exist_ok=True), open_in_explorer(DATA_DIR)), menu=m)
        self._act("a_reset", self._reset_settings, menu=m)

        # About
        m = self._menu(mb, "m_about")
        self._act("formats", self._formats, menu=m)
        self._act("a_about", self._about, "F1", menu=m)

    def _set_theme(self, code, save=True):
        """Light / dark / follow Windows. Qt redraws every window in the new colors."""
        self.theme = code
        scheme = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(code, Qt.ColorScheme.Unknown)
        QApplication.styleHints().setColorScheme(scheme)
        # widgets with a style sheet keep their old text color until re-polished
        for wdg in self.findChildren(QWidget):
            if wdg.styleSheet():
                wdg.setStyleSheet(wdg.styleSheet())
        self._sync_menu_from_widgets()
        if hasattr(self, "preview"):
            self.preview.viewport().update()
        if save:
            self._schedule_save()

    def _sync_menu_from_widgets(self, *_):
        for acts, key in ((getattr(self, "thumb_acts", {}), self.thumb),
                          (getattr(self, "dev_acts", {}), self.device_pref),
                          (getattr(self, "theme_acts", {}), getattr(self, "theme", "system")),
                          (getattr(self, "lang_acts", {}), i18n.get_lang())):
            a = acts.get(key)
            if a and not a.isChecked():
                a.setChecked(True)

    # ================================================================ translation
    def _change_lang(self, code):
        if code == i18n.get_lang() and not self._loading:
            return
        i18n.set_lang(code)
        if not self._loading:
            self.retranslate()
            self._schedule_save()

    def retranslate(self):
        self.setWindowTitle(f"{tr('app_title')} {__version__}")
        for m, key in self._menus:
            m.setTitle(tr(key))
        for a, key in self._acts:
            a.setText(tr(key))
        self.box_folders.setTitle(tr("folders"))
        self.folder_list.setToolTip(tr("drop_hint"))
        self.folder_list.retranslate()
        self.btn_add.setText(tr("add_folder"))
        self.btn_rm.setText(tr("remove_folder"))
        self.btn_add.setToolTip(tr("add_folder_tip"))
        self.btn_rm.setToolTip(tr("remove_folder_tip"))
        self.box_opts.setTitle(tr("options"))
        self.cb_sub.setText(tr("subfolders"))
        self.cb_crop.setText(tr("detect_crops"))
        self.cb_sniff.setText(tr("sniff"))
        self.cb_sniff.setToolTip(tr("sniff_tip"))
        self.lb_sim.setText(tr("similarity"))
        self.lb_sim.setToolTip(tr("similarity_tip"))
        self.sp_sim.setToolTip(tr("similarity_tip"))
        self.lb_crop.setText(tr("crop_sim"))
        self.lb_crop.setToolTip(tr("crop_sim_tip"))
        self.sp_crop.setToolTip(tr("crop_sim_tip"))
        self.dev_acts["auto"].setText(tr("device_auto"))
        self.dev_acts["cpu"].setText(tr("device_cpu"))
        self.btn_scan.setText(tr("cancel") if self.scan_thread else tr("scan"))
        self.btn_variants.setText(tr("btn_variants"))
        self.btn_variants.setToolTip(tr("btn_variants_tip"))
        self.btn_clear.setText(tr("btn_clear"))
        self.btn_clear.setToolTip(tr("btn_clear_tip"))
        self.lb_legend.setText(tr("legend"))
        self.lb_files_title.setText(tr("title_files"))
        self.lb_preview_title.setText(tr("title_preview"))
        self._update_stats()
        self.lb_preview.setText(tr("preview_hint"))
        self.btn_keep_this.setText(tr("keep_this"))
        self.btn_toggle.setText(tr("toggle"))
        self.btn_open.setText(tr("open_default"))
        self.btn_open.setToolTip(tr("open_default_tip"))
        self.btn_show.setText(tr("show_folder"))
        self.box_act.setTitle(tr("action_box"))
        self.rb_move.setText(tr("act_move"))
        self.rb_recycle.setText(tr("act_recycle"))
        self.rb_delete.setText(tr("act_delete"))
        for code, a in self.theme_acts.items():
            a.setText(tr("theme_" + code))
        for col, a in self.col_acts.items():
            a.setText(tr(COLS[col]))
        self.btn_dest.setText(tr("browse"))
        self.btn_apply.setText(tr("apply"))
        self.model.retranslate()
        self._update_summary()
        self._set_status(*self._status_key)
        self._update_errors_btn()
        self._sync_menu_from_widgets()
        self._fill_preview()

    def _set_status(self, key, kw):
        """Bottom status bar: short, overall status (details go to the row under Files)."""
        self._status_key = (key, kw)
        if key == "busy" and "n" in kw:   # scan: stage n of total + time left
            text = tr("scan_busy", n=kw["n"], total=kw["total"], what=tr(kw["what"]))
            if kw.get("eta"):
                text += " · " + tr("eta", t=kw["eta"])
            self.lb_status.setText(text)
        elif key == "busy":        # kw: {"what": short-status key}
            self.lb_status.setText(tr(kw["what"]))
        else:
            self.lb_status.setText(tr(key, **kw))

    # ================================================================ misc actions
    def _change_device(self, code):
        if code == self.device_pref:
            return
        self.device_pref = code
        if not self._loading:
            self._detect_device()
            self._schedule_save()

    def _detect_device(self):
        self.lb_dev.setText(tr("detecting_device"))
        from ..features import pick_device
        _, label = pick_device(self.device_pref)
        self.lb_dev.setText(label)
        self.lb_dev.setToolTip("" if label.startswith("GPU") else tr("cpu_warn"))

    def _add_folder(self):
        """Pick one or more folders (Ctrl / Shift in the dialog)."""
        from .folder_dialog import pick_folders
        last = self.folder_list.folders()[-1] if self.folder_list.count() else ""
        for d in pick_folders(self, tr("add_folders_title"), os.path.dirname(last) if last else ""):
            self.folder_list.add_folder(d)

    def _choose_dest(self):
        d = QFileDialog.getExistingDirectory(self, tr("act_move"), self.ed_dest.text())
        if d:
            self.ed_dest.setText(os.path.normpath(d))
            self.rb_move.setChecked(True)

    def _mode(self):
        if self.rb_recycle.isChecked():
            return actions.RECYCLE
        if self.rb_delete.isChecked():
            return actions.DELETE
        return actions.MOVE

    def _clear_cache(self):
        if QMessageBox.question(self, tr("confirm_title"), tr("clear_cache_q")) != QMessageBox.StandardButton.Yes:
            return
        from ..cache import Cache
        c = Cache(CACHE_PATH)
        c.clear()
        c.close()

    def _formats(self):
        QMessageBox.information(self, tr("formats"), "  ".join(describe_supported()))

    def _about(self):
        box = QMessageBox(self)
        box.setWindowTitle(tr("a_about"))
        box.setIconPixmap(self.windowIcon().pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)   # clickable GitHub link
        box.setText(tr("about_text", ver=__version__, dev=self.lb_dev.text(), n=len(describe_supported()),
                       data=DATA_DIR, logs=LOG_DIR, url=PROJECT_URL, mail=CONTACT_EMAIL))
        box.exec()

    def _toggle_preview(self, on):
        self.preview_panel.setVisible(on)
        self._schedule_save()

    def _set_thumb(self, size, save=True):
        self.thumb = size
        self.preview.setIconSize(QSize(size, size))
        self.preview.setGridSize(QSize(size + 30, size + 90))
        if hasattr(self, "thumb_acts") and size in self.thumb_acts:
            self.thumb_acts[size].setChecked(True)
        self._fill_preview(keep_selection=True)
        if save:
            self._schedule_save()

    def _export_csv(self):
        if not self.result or not self.model.groups:
            QMessageBox.information(self, tr("app_title"), tr("no_results"))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("a_export"), "duplicates.csv", "CSV (*.csv)")
        if not path:
            return
        ft = self.result.files
        n = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["group", "action", "match", "score", "width", "height", "bytes", "modified", "format", "path"])
            for gi, g in enumerate(self.model.groups, 1):
                for m in g.members:
                    i = m.idx
                    w.writerow([gi, "remove" if m.remove else "keep", m.kind, round(m.score, 3),
                                ft.w[i], ft.h[i], ft.size[i], date_text(ft.mtime[i]), ft.fmt[i], ft.paths[i]])
                    n += 1
        QMessageBox.information(self, tr("app_title"), tr("export_done", n=n, path=path))

    def _update_all_box(self):
        total = self.model.total_files()
        n = self.model.n_marked
        if n == 0 or total == 0:
            st = Qt.CheckState.Unchecked
        elif n >= total:
            st = Qt.CheckState.Checked
        else:
            st = Qt.CheckState.PartiallyChecked
        self.check_header.set_state(st)

    def _toggle_all(self):
        """Select box: ticked -> clear everything; otherwise tick EVERY file (keepers too)."""
        if not self.model.groups:
            return
        if self.check_header.state == Qt.CheckState.Checked:
            self.model.unmark_all()
        else:
            self.model.mark_all()

    def _eff_patterns(self):
        return list(self.variant_patterns) if self.exc_patterns_on else []

    def _eff_prefix(self):
        return int(self.exc_prefix_len) if self.exc_prefix_on else 0

    def _update_stats(self):
        """Totals under the Files list: groups, duplicate files, exceptions."""
        if not hasattr(self, "lb_stats"):
            return
        if not self.result:
            self.lb_stats.setText(tr("stats_none"))
            return
        groups = self.model.groups
        dups = sum(1 for g in groups for m in g.members[1:] if m.kind != "variant")
        exc = sum(1 for g in groups for m in g.members if m.kind == "variant")
        text = tr("stats_row", groups=len(groups), dups=dups)
        if exc:
            text += tr("stats_exc", n=exc)
        if self._hidden:
            text += tr("stats_hidden", n=len(self._hidden))
        self.lb_stats.setText(text)
        self.btn_unhide.setText(tr("btn_unhide", n=len(self._hidden)))
        self.btn_unhide.setVisible(bool(self._hidden) and not self.progress.isVisible())

    def _toggle_logging(self, on):
        if on:
            from ..features import HAS_ORT, pick_device
            from ..loader import HAS_HEIF, HAS_JXL, HAS_RAW
            dev = pick_device(self.device_pref)[1]
            ort_ver = __import__("onnxruntime").__version__ if HAS_ORT else "missing"
            path = self.slog.start([
                f"Duplicate Image Finder {__version__}",
                f"Device: {dev} (setting: {self.device_pref}) · ONNX Runtime {ort_ver}",
                f"Formats: HEIF={HAS_HEIF} JXL={HAS_JXL} RAW={HAS_RAW} · Language: {i18n.get_lang()}"])
            self.statusBar().showMessage(tr("log_on", path=path), 8000)
        else:
            self.slog.stop()
            self.statusBar().showMessage(tr("log_off"), 5000)

    def _log_results(self, res):
        if not self.slog.enabled:
            return
        log, ft = self.slog.write, res.files
        log(f"scan finished: device={res.device_label}")
        log("  stats: " + ", ".join(f"{k}={v}" for k, v in res.stats.items()))
        for wmsg in res.warnings:
            log(f"  WARNING: {wmsg}")
        for gi, g in enumerate(res.groups, 1):
            log(f"  group {gi} ({len(g.members)} files)")
            for m in g.members:
                i = m.idx
                act = "REMOVE" if m.remove else "KEEP  "
                why = f" [{m.reason}]" if getattr(m, "reason", "") else ""
                log(f"    {act} {m.kind:8s} {m.score:5.3f}{why}  {ft.w[i]}x{ft.h[i]}  {human_size(ft.size[i]):>9s}  "
                    f"{ft.fmt[i]:5s}  {ft.paths[i]}")
        errs = [(p, e) for p, e in zip(ft.paths, ft.error) if e]
        if errs:
            log(f"  unreadable files: {len(errs)}")
            for p, e in errs:
                log(f"    {p}  ->  {e}")

    def _hide_groups(self, groups):
        """Remember fully-kept groups in the cache so later scans skip them.
        They show again if a file changes, a new copy appears, or the cache is cleared."""
        ft = self.result.files
        from ..cache import Cache
        c = Cache(CACHE_PATH)
        try:
            gids = c.add_ignored([[(ft.paths[m.idx], int(ft.size[m.idx]), int(ft.mtime[m.idx])) for m in g.members]
                                  for g in groups])
        finally:
            c.close()
        for g in groups:
            self.slog.write("hidden (kept, not duplicates): " + " | ".join(ft.paths[m.idx] for m in g.members))
        self._hidden += [(g, [gid]) for g, gid in zip(groups, gids)]
        self.preview_group = None
        self.model.remove_groups(groups)
        self.preview.clear()
        self.statusBar().showMessage(tr("hidden_done", n=len(groups)), 8000)

    # ================================================================ saved scans
    def _busy(self):
        return bool(self.scan_thread or self.action_thread)

    def _scan_options(self):
        return {"crops": self.cb_crop.isChecked(), "misnamed": self.cb_sniff.isChecked(),
                "similarity": self.sp_sim.value(), "crop_match": self.sp_crop.value(),
                "patterns": self._eff_patterns(), "prefix": self._eff_prefix()}

    def _can_save(self):
        if self._busy():
            return False
        if not self.result:
            QMessageBox.information(self, tr("app_title"), tr("nothing_to_save"))
            return False
        return True

    def _write_scan(self, path):
        from .. import session_file
        try:
            session_file.save(path, self.result, self.model.groups, self._result_folders, self._scan_options())
        except OSError as e:
            QMessageBox.critical(self, tr("app_title"), tr("save_failed", err=str(e)))
            return False
        self.slog.write(f"scan saved: {path} ({len(self.model.groups)} groups)")
        return True

    def _save_progress(self):
        """Save groups and ticks for the scanned folders (File > Load progress restores them)."""
        from .. import session_file
        if self._can_save() and self._write_scan(session_file.progress_path(DATA_DIR, self._result_folders)):
            self.statusBar().showMessage(tr("progress_saved", n=len(self.model.groups)), 8000)

    def _load_progress(self):
        from .. import session_file
        if self._busy():
            return
        folders = self.folder_list.entries()
        if not folders:
            QMessageBox.warning(self, tr("app_title"), tr("no_folders"))
            return
        path = session_file.progress_path(DATA_DIR, folders)
        if not os.path.exists(path):
            QMessageBox.information(self, tr("app_title"), tr("no_progress"))
            return
        self._open_scan(path)

    def _export_scan(self):
        from .. import session_file
        if not self._can_save():
            return
        start = os.path.join(self.settings.get("scan_dir", os.path.expanduser("~")),
                             time.strftime("duplicates_%Y%m%d_%H%M") + session_file.XML_EXT)
        path, _ = QFileDialog.getSaveFileName(self, tr("a_export_scan"), start, tr("scan_filter_xml"))
        if path and not path.lower().endswith(session_file.XML_EXT):
            path += session_file.XML_EXT
        if path and self._write_scan(path):
            self.settings["scan_dir"] = os.path.dirname(path)
            self._schedule_save()
            self.statusBar().showMessage(tr("scan_exported", path=path), 8000)

    def _import_scan(self):
        if self._busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("a_import_scan"),
                                              self.settings.get("scan_dir", os.path.expanduser("~")), tr("scan_filter"))
        if path:
            self.settings["scan_dir"] = os.path.dirname(path)
            self._schedule_save()
            self._open_scan(path)

    def _open_scan(self, path):
        """Load a saved scan, after checking it against the disk and warning about changes."""
        from .. import session_file
        try:
            data = session_file.read(path)
            result, rep = session_file.build(data)
        except session_file.ScanFileError as e:
            QMessageBox.critical(self, tr("app_title"), tr("scan_file_bad", err=str(e)))
            return
        if self.result and QMessageBox.question(self, tr("app_title"), tr("replace_results_q")) \
                != QMessageBox.StandardButton.Yes:
            return
        saved_folders = [(p, bool(r)) for p, r in data["folders"]]
        nl = chr(10)
        issues = []
        if rep["missing_folders"]:
            issues.append(tr("ld_missing_folders", list=nl.join("   " + p for p in rep["missing_folders"])))
        if rep["missing_files"]:
            issues.append(tr("ld_missing_files", n=rep["missing_files"]))
        if rep["changed_files"]:
            issues.append(tr("ld_changed_files", n=rep["changed_files"]))
        if rep["dropped_groups"]:
            issues.append(tr("ld_dropped_groups", n=rep["dropped_groups"]))
        if session_file.folders_key(saved_folders) != session_file.folders_key(self.folder_list.entries()):
            issues.append(tr("ld_folders_replaced", list=nl.join("   " + p for p, _ in saved_folders)))
        if not result.groups:
            QMessageBox.warning(self, tr("app_title"), nl.join([tr("ld_empty"), ""] + issues))
            return
        if issues:
            box = QMessageBox(QMessageBox.Icon.Warning, tr("app_title"),
                              nl.join([tr("ld_intro", saved=rep["saved"]), ""] + issues + ["", tr("ld_continue")]),
                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
        # show it like a finished scan
        self.folder_list.clear_all()
        for p, rec in saved_folders:
            if os.path.isdir(p):
                self.folder_list.add_folder(p, rec)
        self._result_folders = saved_folders
        self.loader.clear_queue()
        self.preview_group = None
        self.preview.clear()
        self._hidden = []
        self.result = result
        self.model.set_result(result)
        if len(result.groups) <= 300:
            self.tree.expandAll()
        self._set_status("loaded_status", {"groups": len(result.groups), "saved": rep["saved"]})
        self._update_errors_btn()
        self._update_stats()
        self.tree.setCurrentIndex(self.model.index(0, C_NAME))
        self.slog.write(f"scan loaded: {path} ({len(result.groups)} groups; missing {rep['missing_files']}, "
                        f"changed {rep['changed_files']})")

    def _unhide(self):
        """Show groups the user kept earlier again, and stop hiding them in later scans."""
        if not self._hidden or not self.result or self.scan_thread or self.action_thread:
            return
        n = len(self._hidden)
        if QMessageBox.question(self, tr("app_title"), tr("unhide_q", n=n)) != QMessageBox.StandardButton.Yes:
            return
        from ..cache import Cache
        c = Cache(CACHE_PATH)
        try:
            c.remove_ignored([gid for _, gids in self._hidden for gid in gids])
        finally:
            c.close()
        groups = [g for g, _ in self._hidden]
        self._hidden = []
        ft = self.result.files
        for g in groups:
            self.slog.write("unhidden: " + " | ".join(ft.paths[m.idx] for m in g.members))
        self.model.add_groups(groups)
        if self.model.rowCount() <= 300:
            self.tree.expandAll()
        self.statusBar().showMessage(tr("unhide_done", n=n), 8000)

    def _clear_workspace(self):
        """Clear results, marks and preview. Folders, settings and cache are kept."""
        if self.scan_thread or self.action_thread:
            return
        self.loader.clear_queue()
        self.result = None
        self._hidden = []
        self.preview_group = None
        self.model.set_result(None)
        self.preview.clear()
        self.btn_errors.hide()
        self.progress.hide()
        self._set_status("ready", {})
        self._update_summary()

    def _edit_variants(self):
        dlg = VariantDialog(self, self.variant_patterns, self.exc_patterns_on,
                            self.exc_prefix_on, self.exc_prefix_len)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.variant_patterns = dlg.patterns()
        self.exc_patterns_on = dlg.cb_pat.isChecked()
        self.exc_prefix_on = dlg.cb_pre.isChecked()
        self.exc_prefix_len = dlg.sp_pre.value()
        self._schedule_save()
        if self.result:                      # apply to the current results right away
            self.preview_group = None
            self.model.reapply_variants(self._eff_patterns(), self._eff_prefix())
            if len(self.model.groups) <= 300:
                self.tree.expandAll()
            self._fill_preview()

    def _current_group_mark(self, mark):
        gi, _ = self.model.member_at(self.tree.currentIndex())
        if gi is not None:
            self.model.set_group(gi, mark)

    # ================================================================ scanning
    def _scan_clicked(self):
        if self.scan_thread:
            self.scan_thread.cancel()
            self.btn_scan.setEnabled(False)
            return
        if self.action_thread:
            return
        folders = self.folder_list.entries()   # [(path, include_subfolders)]
        if not folders:
            QMessageBox.warning(self, tr("app_title"), tr("no_folders"))
            return
        sim = self.sp_sim.value()
        opts = ScanOptions(
            folders=folders,
            recursive=self.cb_sub.isChecked(),
            detect_crops=self.cb_crop.isChecked(),
            sniff=self.cb_sniff.isChecked(),
            phash_dist=int(64 * (100 - sim) / 100),
            crop_sim=self.sp_crop.value() / 100.0,
            device=self.device_pref,
            exclude=[self.ed_dest.text()] if self.ed_dest.text().strip() else [],
            variant_patterns=self._eff_patterns(),
            prefix_len=self._eff_prefix(),
        )
        self._save_settings()
        self._result_folders = folders
        self.model.set_result(None)
        self.result = None
        self.preview_group = None
        self.preview.clear()
        self.loader.clear_queue()
        self.btn_errors.hide()
        if self.slog.enabled:
            self.slog.write("-" * 70)
            self.slog.write("scan started")
            for p, rec in opts.folders:
                self.slog.write(f"  folder: {p}  (subfolders: {'yes' if rec else 'no'})")
            self.slog.write(f"  crops={opts.detect_crops} misnamed={opts.sniff} phash_dist={opts.phash_dist} "
                            f"crop_sim={opts.crop_sim:.2f} device={opts.device}")
            self.slog.write(f"  exceptions: patterns={opts.variant_patterns} prefix_len={opts.prefix_len}")
        self._scan_stages = self.SCAN_STAGES if opts.detect_crops else self.SCAN_STAGES_NO_CROPS
        self._last_stage = None
        self.scan_thread = ScanThread(opts)
        self.scan_thread.progress.connect(self._on_progress)
        self.scan_thread.log.connect(self._on_log)
        self.scan_thread.finished_ok.connect(self._on_scan_done)
        self.scan_thread.cancelled.connect(self._on_scan_cancelled)
        self.scan_thread.failed.connect(self._on_scan_failed)
        self.scan_thread.finished.connect(self._on_thread_finished)
        self._set_scanning(True)
        self.scan_thread.start()

    def _set_scanning(self, on):
        self.btn_scan.setText(tr("cancel") if on else tr("scan"))
        self.btn_scan.setEnabled(True)
        for w in (self.box_folders, self.box_opts, self.box_act):
            w.setEnabled(not on)
        self.btn_clear.setEnabled(not on)
        self.menu_device.setEnabled(not on)
        self.progress.setVisible(on)
        self.progress.setRange(0, 0)
        self.lb_stats.setVisible(not on or not self.result)
        if on:
            self.btn_unhide.hide()
        else:
            self._update_stats()      # e.g. show "Show hidden (N)" now that the progress bar is gone
    SCAN_STAGES = ("enumerate", "cache", "model", "analyze", "exact", "visual", "features", "verify", "group")
    SCAN_STAGES_NO_CROPS = ("enumerate", "cache", "analyze", "exact", "visual", "group")

    def _on_progress(self, stage, done, total):
        now = time.monotonic()
        if stage != getattr(self, "_last_stage", None):
            self._last_stage = stage
            self._stage_t0 = now
            self._eta_text, self._eta_t = "", 0.0
            self.slog.write(f"stage: {stage}")
        # remaining time of the current stage, from its average speed so far;
        # shown after 2 s and refreshed once per second so it doesn't flicker
        if total > 0 and 0 < done < total:
            elapsed = now - self._stage_t0
            if elapsed >= 2 and now - self._eta_t >= 1:
                self._eta_t = now
                self._eta_text = _fmt_duration(elapsed * (total - done) / done)
        elif done >= total:
            self._eta_text = ""
        stages = self._scan_stages or self.SCAN_STAGES
        n = stages.index(stage) + 1 if stage in stages else 0
        self._set_status("busy", {"what": "sname_" + stage, "n": n, "total": len(stages),
                                  "eta": self._eta_text})                       # bottom: overall
        self.lb_stats.setText(tr("stage_" + stage, done=done, total=total))      # top: detailed
        self.lb_stats.setVisible(True)
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        else:
            self.progress.setRange(0, 0)

    def _on_log(self, msg):
        self.slog.write(msg)
        if msg.startswith("Device:"):
            self.lb_dev.setText(msg.split(":", 1)[1].strip())

    def _on_scan_done(self, res):
        self.result = res
        self.model.set_result(res)
        if len(res.groups) <= 300:
            self.tree.expandAll()
        st = res.stats
        self._set_status("done_status", {"groups": st["groups"], "dups": st["duplicates"],
                                         "files": st["files"], "sec": st["seconds"]})
        self._hidden = list(getattr(res, "hidden", []))
        self._update_errors_btn()
        self._update_stats()
        self._log_results(res)
        if res.groups:
            self.tree.setCurrentIndex(self.model.index(0, C_NAME))
        if res.warnings:
            QMessageBox.warning(self, tr("warnings"), "\n".join(res.warnings[:20]))

    def _on_scan_cancelled(self):
        self._set_status("cancelled", {})
        self.slog.write("scan canceled by user")
        self._update_stats()

    def _on_scan_failed(self, err):
        self._set_status("ready", {})
        self.slog.write("SCAN FAILED: " + err)
        self._update_stats()
        QMessageBox.critical(self, tr("app_title"), tr("scan_failed", err=err[:3000]))

    def _on_thread_finished(self):
        self.scan_thread = None
        self._set_scanning(False)

    def _update_errors_btn(self):
        if not self.result:
            return
        n = self.result.stats.get("errors", 0)
        self.btn_errors.setText(tr("errors_btn", n=n))
        self.btn_errors.setVisible(n > 0)

    def _show_errors(self):
        ft = self.result.files
        lines = [f"{p}\n    {e}" for p, e in zip(ft.paths, ft.error) if e]
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("errors_title"))
        dlg.resize(900, 500)
        lay = QVBoxLayout(dlg)
        t = QPlainTextEdit("\n".join(lines))
        t.setReadOnly(True)
        lay.addWidget(t)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()

    # ================================================================ summary / preview
    def _update_summary(self):
        self.lb_summary.setText(tr("summary", n=self.model.n_marked, size=human_size(self.model.bytes_marked)))
        self._fill_preview(keep_selection=True)

    def _current_changed(self, cur, prev):
        gi, mi = self.model.member_at(cur)
        if gi is None:
            return
        if gi != self.preview_group:
            self.preview_group = gi
            self._fill_preview()
        if mi is not None and mi < self.preview.count():
            self.preview.setCurrentRow(mi)

    # ---- columns: View > Columns
    def _show_column(self, col, on):
        hdr = self.tree.header()
        if hdr.isSectionHidden(col) == (not on):
            return
        hdr.setSectionHidden(col, not on)
        if on and hdr.sectionSize(col) < 30:
            hdr.resizeSection(col, dict(COL_WIDTHS).get(col, 120))
        self._schedule_save()

    def _sync_column_menu(self):
        hdr = self.tree.header()
        for col, a in getattr(self, "col_acts", {}).items():
            a.blockSignals(True)
            a.setChecked(not hdr.isSectionHidden(col))
            a.blockSignals(False)

    def _reset_columns(self):
        """All columns shown, in the original order and widths."""
        hdr = self.tree.header()
        for col in range(self.model.columnCount()):
            hdr.setSectionHidden(col, False)
            if hdr.visualIndex(col) != col:
                hdr.moveSection(hdr.visualIndex(col), col)
        for col, w in COL_WIDTHS:
            hdr.resizeSection(col, w)
        self._sync_column_menu()
        self._schedule_save()

    def _sort_by(self, col):
        if col == C_REMOVE:
            return
        hdr = self.tree.header()
        cur = self.model.sort_key
        order = (Qt.SortOrder.DescendingOrder if cur and cur[0] == col and cur[1] == Qt.SortOrder.AscendingOrder
                 else Qt.SortOrder.AscendingOrder)
        hdr.setSortIndicator(col, order)
        self.model.sort(col, order)

    def _after_sort(self):
        """Groups moved: the preview follows the selected group to its new row."""
        gi, _ = self.model.member_at(self.tree.currentIndex())
        if gi is not None and gi != self.preview_group:
            self.preview_group = gi
        self._fill_preview(keep_selection=True)

    def _fill_preview(self, keep_selection=False):
        if not hasattr(self, "preview"):
            return
        sel = self.preview.currentRow() if keep_selection else -1
        self.preview.clear()
        self.lb_preview_group.clear()
        gi = self.preview_group
        if self.result is None or gi is None or gi >= len(self.model.groups):
            return
        ft = self.result.files
        g = self.model.groups[gi]
        self.lb_preview_group.setText(tr("preview_group", name=tr("group_n", n=gi + 1, count=len(g.members)),
                                         size=human_size(sum(int(ft.size[m.idx]) for m in g.members if m.remove))))
        for m in g.members:
            i = m.idx
            item = QListWidgetItem()
            tag = ("☑ " + tr("tag_remove")) if m.remove else ("☐ " + tr("tag_keep"))
            item.setText(f"{tag} · {kind_text(m)}\n{os.path.basename(ft.paths[i])}\n"
                         f"{ft.w[i]}×{ft.h[i]} · {human_size(ft.size[i])} · {ft.fmt[i]}\n{date_text(ft.mtime[i])}")
            item.setToolTip(ft.paths[i])
            item.setForeground(REMOVE_COLOR if m.remove else KEEP_COLOR)
            bg = QColor(REMOVE_COLOR if m.remove else KEEP_COLOR)
            bg.setAlpha(28)
            item.setBackground(bg)
            pix = self.loader.get(ft.paths[i], self.thumb)
            if pix is not None and not pix.isNull():
                item.setIcon(QIcon(pix))
            item.setData(Qt.ItemDataRole.UserRole, ft.paths[i])
            self.preview.addItem(item)
        if 0 <= sel < self.preview.count():
            self.preview.setCurrentRow(sel)

    def _thumb_loaded(self, path, size):
        if size != self.thumb:
            return
        for r in range(self.preview.count()):
            it = self.preview.item(r)
            if it.data(Qt.ItemDataRole.UserRole) == path:
                pix = self.loader.get(path, self.thumb)
                if pix is not None and not pix.isNull():
                    it.setIcon(QIcon(pix))

    def _selected_member(self):
        gi = self.preview_group
        r = self.preview.currentRow()
        if gi is None or r < 0 or gi >= len(self.model.groups):
            return None, None
        return gi, r

    def _keep_this(self):
        gi, r = self._selected_member()
        if gi is not None:
            self.model.keep_only(gi, r)

    def _toggle_selected(self):
        gi, r = self._selected_member()
        if gi is not None:
            m = self.model.groups[gi].members[r]
            self.model.set_remove(gi, r, not m.remove)

    def _open_selected(self, folder):
        gi, r = self._selected_member()
        if gi is not None:
            open_in_explorer(self.result.files.paths[self.model.groups[gi].members[r].idx], folder)

    def _preview_double(self, item):
        gi = self.preview_group
        if gi is not None:
            ViewerDialog(self, self.loader, self.result.files, self.model.groups[gi].members,
                         self.preview.row(item)).exec()

    def _tree_double(self, index):
        gi, mi = self.model.member_at(index)
        if mi is not None and index.column() != C_REMOVE:
            ViewerDialog(self, self.loader, self.result.files, self.model.groups[gi].members, mi).exec()

    def _member_menu(self, gi, mi, global_pos):
        path = self.result.files.paths[self.model.groups[gi].members[mi].idx]
        menu = QMenu(self)
        menu.addAction(tr("keep_this"), lambda: self.model.keep_only(gi, mi))
        menu.addAction(tr("toggle"), lambda: self.model.set_remove(
            gi, mi, not self.model.groups[gi].members[mi].remove))
        menu.addSeparator()
        menu.addAction(tr("a_group_mark"), lambda: self.model.set_group(gi, True))
        menu.addAction(tr("a_group_unmark"), lambda: self.model.set_group(gi, False))
        menu.addSeparator()
        menu.addAction(tr("open_default"), lambda: open_in_explorer(path))
        menu.addAction(tr("show_folder"), lambda: open_in_explorer(path, True))
        menu.exec(global_pos)

    def _group_menu(self, gi, global_pos):
        menu = QMenu(self)
        menu.addAction(tr("a_group_mark"), lambda: self.model.set_group(gi, True))
        menu.addAction(tr("a_group_unmark"), lambda: self.model.set_group(gi, False))
        menu.exec(global_pos)

    def _tree_menu(self, pos):
        gi, mi = self.model.member_at(self.tree.indexAt(pos))
        gp = self.tree.viewport().mapToGlobal(pos)
        if mi is not None:
            self._member_menu(gi, mi, gp)
        elif gi is not None:
            self._group_menu(gi, gp)

    def _preview_menu(self, pos):
        item = self.preview.itemAt(pos)
        if item is not None and self.preview_group is not None:
            self._member_menu(self.preview_group, self.preview.row(item),
                              self.preview.viewport().mapToGlobal(pos))

    # ================================================================ apply
    def _apply(self):
        if not self.result or self.scan_thread or self.action_thread:
            return
        mode = self._mode()
        # groups where every file is KEEP = "not duplicates": remembered in the cache
        keep_groups = [g for g in self.model.groups if not any(m.remove for m in g.members)]
        # Moving whole groups is safe (nothing is lost); recycling/deleting them is not.
        marked, skipped = self.model.marked(allow_full=(mode == actions.MOVE))
        if skipped:
            QMessageBox.warning(self, tr("app_title"), tr("skipped_groups", n=skipped))
        if not marked:
            if keep_groups:
                answer = QMessageBox.question(self, tr("confirm_title"), tr("confirm_hide_only", n=len(keep_groups)))
                if answer == QMessageBox.StandardButton.Yes:
                    self._hide_groups(keep_groups)
            elif not skipped:
                QMessageBox.information(self, tr("app_title"), tr("nothing_marked"))
            return
        ft = self.result.files
        size = human_size(sum(int(ft.size[m.idx]) for _, m in marked))
        dest = self.ed_dest.text().strip()
        if mode == actions.MOVE:
            if not dest:
                QMessageBox.warning(self, tr("app_title"), tr("no_dest"))
                return
            dest = os.path.abspath(dest)
            msg = tr("confirm_move", n=len(marked), size=size, dest=dest)
        elif mode == actions.RECYCLE:
            msg = tr("confirm_recycle", n=len(marked), size=size)
        else:
            msg = tr("confirm_delete", n=len(marked), size=size)
        if keep_groups:
            msg += "\n\n" + tr("hide_note", n=len(keep_groups))
        icon = QMessageBox.Icon.Warning if mode == actions.DELETE else QMessageBox.Icon.Question
        box = QMessageBox(icon, tr("confirm_title"), msg,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self._save_settings()
        if keep_groups:
            self._hide_groups(keep_groups)
        items = []
        for g, m in marked:
            kept = next((ft.paths[x.idx] for x in g.members if not x.remove), "")
            items.append((m.idx, ft.paths[m.idx], kept))
        self.slog.write(f"apply: {mode} {len(items)} files" + (f" to {dest}" if mode == actions.MOVE else ""))
        self.action_thread = ActionThread(items, mode, self.result.roots, dest)
        self._set_status("busy", {"what": "short_" + mode})
        self.lb_stats.setVisible(True)
        self.action_thread.progress.connect(
            lambda d, t: (self.lb_stats.setText(tr("applying", done=d, total=t)),
                          self.progress.setRange(0, t), self.progress.setValue(d)))
        self.action_thread.done.connect(self._apply_done)
        self.progress.show()
        for w in (self.box_folders, self.box_opts, self.box_act, self.btn_scan, self.btn_clear):
            w.setEnabled(False)
        self.action_thread.start()

    def _apply_done(self, done_idx, fail, log_path, results=()):
        if self.slog.enabled:
            self.slog.write(f"apply finished: {len(done_idx)} ok, {fail} failed (csv: {log_path})")
            for path, ok, info in results:
                self.slog.write(f"  {'ok    ' if ok else 'FAILED'}  {path}  ->  {info}")
        self.progress.hide()
        for w in (self.box_folders, self.box_opts, self.box_act, self.btn_scan, self.btn_clear):
            w.setEnabled(True)
        self.action_thread = None
        self.preview_group = None
        self.model.remove_done(done_idx)
        self.preview.clear()
        self._set_status("apply_done_short", {"ok": len(done_idx), "fail": fail})
        msg = tr("apply_done_nolog", ok=len(done_idx), fail=fail)
        QMessageBox.information(self, tr("app_title"), msg)

    def closeEvent(self, e):
        if self.scan_thread:
            self.scan_thread.cancel()
            self.scan_thread.wait(10000)
        if self.action_thread:
            self.action_thread.wait()
        self._save_timer.stop()
        self._save_settings()
        self.slog.stop()
        super().closeEvent(e)
