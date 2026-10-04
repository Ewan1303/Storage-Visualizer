"""Thumbnails for the file type viewer, made on worker threads and kept in a small cache."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QImageReader

from ..core.thumbnails import shell_thumbnail

MAX_WAITING = 160  # requests beyond this are dropped, oldest first: they have scrolled out of view
CACHE_SIZE = 900   # thumbnails kept in memory (about 100 MB at the largest size)

# Thumbnails are made at a few fixed sizes so a picture is reused when the
# grid is resized a little, instead of being made again for every pixel.
SIZE_STEPS = (64, 96, 128, 160, 192, 256, 320, 384, 512)


def size_step(pixels: float) -> int:
    """The smallest thumbnail size at least ``pixels`` wide."""
    for step in SIZE_STEPS:
        if step >= pixels:
            return step
    return SIZE_STEPS[-1]


class ThumbnailProvider(QObject):
    """Answers ``image(path, size)`` at once from the cache, or returns None and
    starts making the picture; ``ready`` fires when new pictures are done.

    The newest requests are served first, so scrolling quickly through
    thousands of photos only spends time on the ones still in view.
    """

    ready = Signal()

    def __init__(self, workers: int = 3, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache: OrderedDict[tuple[str, int], QImage | None] = OrderedDict()
        self._waiting: OrderedDict[tuple[str, int], bool] = OrderedDict()
        self._busy = 0
        self._lock = threading.Condition()
        self._closed = False
        # Made-up data has no files on disk; it draws its own pictures instead.
        self.picture_maker: Callable[[str, int], QImage | None] | None = None
        for i in range(workers):
            threading.Thread(target=self._work, name=f"thumbnails-{i}", daemon=True).start()

    def image(self, path: str, size: int, online_only: bool = False) -> QImage | None:
        key = (path, size)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            if key in self._waiting:
                self._waiting.move_to_end(key)  # wanted again: serve it sooner
            else:
                self._waiting[key] = online_only
                while len(self._waiting) > MAX_WAITING:
                    self._waiting.popitem(last=False)
                self._lock.notify()
        return None

    def pending(self) -> int:
        """Pictures asked for and not finished yet."""
        with self._lock:
            return len(self._waiting) + self._busy

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._waiting.clear()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._waiting.clear()
            self._lock.notify_all()

    def _work(self) -> None:
        while True:
            with self._lock:
                while not self._waiting and not self._closed:
                    self._lock.wait()
                if self._closed:
                    return
                (path, size), online_only = self._waiting.popitem(last=True)
                self._busy += 1
            try:
                image = self._make(path, size, online_only)
            except Exception:  # an odd file must not stop the other thumbnails
                image = None
            with self._lock:
                self._busy -= 1
                if self._closed:
                    return
                self._cache[(path, size)] = image
                while len(self._cache) > CACHE_SIZE:
                    self._cache.popitem(last=False)
            try:
                self.ready.emit()
            except RuntimeError:  # the app is closing
                return

    def _make(self, path: str, size: int, online_only: bool) -> QImage | None:
        maker = self.picture_maker
        if maker is not None:
            return maker(path, size)
        thumb = shell_thumbnail(path, size, cached_only=online_only)
        if thumb is not None:
            fmt = QImage.Format.Format_ARGB32_Premultiplied if thumb.has_alpha else QImage.Format.Format_RGB32
            return QImage(thumb.pixels, thumb.width, thumb.height, thumb.width * 4, fmt).copy()
        if online_only:
            return None  # reading it would download it
        # Where the Windows shell cannot help, Qt can still read common image files.
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        if not reader.canRead():
            return None
        source = reader.size()
        if source.isValid() and max(source.width(), source.height()) > size:
            reader.setScaledSize(source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        return None if image.isNull() else image
