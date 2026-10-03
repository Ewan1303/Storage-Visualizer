"""Runs slow lookups off the UI thread and hands the answers back on it."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal


class Background(QObject):
    """One worker thread; ``finished(job, result)`` arrives on the UI thread.

    Qt queues a signal emitted from another thread, so receivers run safely
    on the thread that owns them. ``result`` is None if the lookup failed.
    """

    finished = Signal(object, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lookup")

    def run(self, job: object, work: Callable[[], object]) -> None:
        # Emit from the worker itself: a done-callback can run straight away on
        # the calling thread, which would deliver the answer before run() returns.
        def task() -> None:
            try:
                result = work()
            except Exception:
                result = None
            try:
                self.finished.emit(job, result)
            except RuntimeError:  # the window was closed while this was running
                pass
        self._pool.submit(task)
