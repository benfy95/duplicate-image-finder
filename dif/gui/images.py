"""Background thumbnail / preview loading (via Pillow, so every format works)."""

from collections import OrderedDict

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap

from ..loader import open_image


def pil_to_qimage(im):
    im = im.convert("RGB")
    w, h = im.size
    data = im.tobytes("raw", "RGB")
    return QImage(data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class _Signals(QObject):
    done = Signal(str, int, QImage)


class _Task(QRunnable):
    def __init__(self, path, size, signals):
        super().__init__()
        self.path, self.size, self.signals = path, size, signals

    def run(self):
        try:
            im, _, _ = open_image(self.path, max_side=self.size)
            q = pil_to_qimage(im)
        except Exception:
            q = QImage()
        try:
            self.signals.done.emit(self.path, self.size, q)
        except RuntimeError:  # receiver deleted while loading
            pass


class ImageLoader(QObject):
    """Loads images off the GUI thread; keeps an LRU cache of pixmaps."""
    loaded = Signal(str, int)  # path, size

    def __init__(self, parent=None, cache_items=400):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.cache = OrderedDict()
        self.cache_items = cache_items
        self.inflight = set()
        self.sig = _Signals()
        self.sig.done.connect(self._done)

    def get(self, path, size):
        key = (path, size)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if key not in self.inflight:
            self.inflight.add(key)
            self.pool.start(_Task(path, size, self.sig))
        return None

    def _done(self, path, size, qimg):
        key = (path, size)
        self.inflight.discard(key)
        self.cache[key] = QPixmap.fromImage(qimg) if not qimg.isNull() else QPixmap()
        while len(self.cache) > self.cache_items:
            self.cache.popitem(last=False)
        self.loaded.emit(path, size)

    def clear_queue(self):
        self.pool.clear()
        self.inflight.clear()
