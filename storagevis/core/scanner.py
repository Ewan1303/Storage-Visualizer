"""Walks a folder tree in background threads and builds a :class:`ScanTree`.

Opening folders is the slow part of a scan, and CPython lets go of the GIL
while Windows reads a folder, so several worker threads keep the disk busy.

What gets counted:

* each file's size as Windows reports it (like Explorer's "Size" column);
* OneDrive "online-only" files separately, because they take no local space;
* never the same data twice through junctions, mount points or symlinks, which
  are skipped. (Hard links, such as Windows' own component store, are still
  counted once per name, as most tools do.)
"""

from __future__ import annotations

import gc
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass

from .categories import COUNT as N_CATEGORIES
from .categories import EXTENSION_CATEGORY, OTHER, extension_of
from .model import DirNode, FileNode, ScanTree, aggregate
from .system import disk_usage, to_display_path, to_fs_path

# FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_OFFLINE: the file is listed
# but its contents live in the cloud (OneDrive "online-only" files).
ONLINE_ONLY_ATTRIBUTES = 0x0040_0000 | 0x0000_1000

# Waiting on the disk, not the CPU, is what limits a scan, so this is more
# threads than most PCs have cores: measured on Windows, 8 beat 4 by ~30%
# and 16 added nothing.
DEFAULT_WORKERS = 8

MAX_RECORDED_ERRORS = 1000

_HAS_ATTRIBUTES = hasattr(os.stat_result, "st_file_attributes")


@dataclass(frozen=True)
class ScanProgress:
    files: int
    folders: int
    bytes: int
    cloud_bytes: int
    errors: int
    current: str
    elapsed: float
    done: bool


class _WorkerTotals:
    """What one worker thread has found; summed when progress is asked for."""

    __slots__ = ("files", "folders", "bytes", "cloud", "errors", "links", "extensions")

    def __init__(self) -> None:
        self.files = self.folders = self.bytes = self.cloud = self.errors = self.links = 0
        self.extensions: dict[str, list[int]] = {}


class Scanner:
    """Scans one folder (or drive) in the background.

    ``start()`` returns at once; poll ``progress()`` and read ``result`` once
    ``done`` is true. ``cancel()`` stops early and still produces a (partial) tree.
    """

    def __init__(self, path: str, *, workers: int = DEFAULT_WORKERS) -> None:
        display = os.path.abspath(to_display_path(path))
        if not os.path.isdir(display):
            raise NotADirectoryError(f"Not a folder: {display}")
        self.path = display
        self._fs_root = to_fs_path(display)
        self._workers = [_WorkerTotals() for _ in range(max(1, workers))]
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._errors: list[tuple[str, str]] = []
        self._errors_lock = threading.Lock()
        self._current = self._fs_root
        self._started: float | None = None
        self._finished: float | None = None
        self._thread: threading.Thread | None = None
        self._result: ScanTree | None = None
        self._failure: BaseException | None = None
        self.disk = disk_usage(display)

    # -------------------------------------------------------------- public API

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("This scanner has already been started")
        self._started = time.perf_counter()
        self._thread = threading.Thread(target=self._run, name="scan", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def result(self) -> ScanTree | None:
        return self._result

    @property
    def failure(self) -> BaseException | None:
        """Set if the scan broke down completely (not for unreadable folders)."""
        return self._failure

    def progress(self) -> ScanProgress:
        w = self._workers
        if self._started is None:
            elapsed = 0.0
        else:
            elapsed = (self._finished or time.perf_counter()) - self._started
        return ScanProgress(
            files=sum(t.files for t in w),
            folders=sum(t.folders for t in w),
            bytes=sum(t.bytes for t in w),
            cloud_bytes=sum(t.cloud for t in w),
            errors=sum(t.errors for t in w),
            current=to_display_path(self._current),
            elapsed=elapsed,
            done=self._done.is_set(),
        )

    # ---------------------------------------------------------------- internals

    def _run(self) -> None:
        root = DirNode(self.path)
        jobs: queue.Queue = queue.Queue()
        jobs.put((root, self._fs_root))
        # Millions of new objects would otherwise set off constant full garbage
        # collections, which can double the scan time.
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            threads = [
                threading.Thread(target=self._work, args=(totals, jobs), name=f"scan-{i}", daemon=True)
                for i, totals in enumerate(self._workers)
            ]
            for t in threads:
                t.start()
            jobs.join()
            for _ in threads:
                jobs.put(None)
            for t in threads:
                t.join()
            aggregate(root)
            self._result = self._build_tree(root)
            # The tree lives until the next scan, so keep the collector from
            # walking it again and again; release_tree() undoes this.
            gc.freeze()
        except BaseException as exc:  # reported to the UI through .failure
            self._failure = exc
        finally:
            if gc_was_enabled:
                gc.enable()
            self._finished = time.perf_counter()
            self._done.set()

    def _work(self, totals: _WorkerTotals, jobs: queue.Queue) -> None:
        while True:
            job = jobs.get()
            try:
                if job is None:
                    return
                if self._cancel.is_set():
                    continue  # drain the queue so join() returns quickly
                node, fs_path = job
                self._current = fs_path
                try:
                    self._list(node, fs_path, totals, jobs)
                except Exception as exc:  # a bug, not a disk problem: keep the other workers going
                    node.error = f"Unexpected error: {exc!r}"
                    totals.errors += 1
                    self._record_error(fs_path, node.error)
            finally:
                jobs.task_done()

    def _list(self, node: DirNode, fs_path: str, totals: _WorkerTotals, jobs: queue.Queue) -> None:
        try:
            entries = os.scandir(fs_path)
        except OSError as exc:
            node.error = _describe(exc)
            totals.errors += 1
            self._record_error(fs_path, node.error)
            return

        children = node.children
        by_category = node.by_category
        extensions = totals.extensions
        categories = EXTENSION_CATEGORY
        intern = sys.intern
        subfolders: list[tuple[DirNode, str]] = []
        size = cloud = files = biggest = biggest_total = 0
        try:
            with entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.is_junction():
                                totals.links += 1  # junction or mount point: its data is counted elsewhere
                                continue
                            child = DirNode(entry.name, node)
                            children.append(child)
                            subfolders.append((child, entry.path))
                            continue
                        if entry.is_symlink():
                            totals.links += 1
                            continue
                        st = entry.stat(follow_symlinks=False)  # free on Windows: comes with the listing
                    except OSError:
                        totals.errors += 1
                        continue
                    name = entry.name
                    ext = intern(extension_of(name))  # one shared string per extension
                    category = categories.get(ext, OTHER)
                    nbytes = st.st_size
                    record = extensions.get(ext)
                    if record is None:
                        record = extensions[ext] = [0, 0, 0]
                    record[2] += 1
                    if _HAS_ATTRIBUTES and st.st_file_attributes & ONLINE_ONLY_ATTRIBUTES:
                        children.append(FileNode(name, node, 0, nbytes, ext))
                        cloud += nbytes
                        by_category[N_CATEGORIES + category] += nbytes
                        record[1] += nbytes
                    else:
                        children.append(FileNode(name, node, nbytes, 0, ext))
                        size += nbytes
                        by_category[category] += nbytes
                        record[0] += nbytes
                        if nbytes > biggest:
                            biggest = nbytes
                    if nbytes > biggest_total:
                        biggest_total = nbytes
                    files += 1
        except OSError as exc:  # the listing broke off part way through
            node.error = _describe(exc)
            totals.errors += 1
            self._record_error(fs_path, node.error)

        node.size = size
        node.cloud = cloud
        node.files = files
        node.biggest = biggest
        node.biggest_total = biggest_total
        totals.files += files
        totals.folders += 1
        totals.bytes += size
        totals.cloud += cloud
        for child, path in subfolders:
            jobs.put((child, path))

    def _record_error(self, fs_path: str, message: str) -> None:
        with self._errors_lock:
            if len(self._errors) < MAX_RECORDED_ERRORS:
                self._errors.append((to_display_path(fs_path), message))

    def _build_tree(self, root: DirNode) -> ScanTree:
        extensions: dict[str, list[int]] = {}
        for totals in self._workers:
            for ext, (local, cloud, files) in totals.extensions.items():
                record = extensions.get(ext)
                if record is None:
                    extensions[ext] = [local, cloud, files]
                else:
                    record[0] += local
                    record[1] += cloud
                    record[2] += files
        return ScanTree(
            root,
            self.path,
            elapsed=time.perf_counter() - (self._started or time.perf_counter()),
            complete=not self._cancel.is_set(),
            errors=list(self._errors),
            error_count=sum(t.errors for t in self._workers),
            skipped_links=sum(t.links for t in self._workers),
            extensions=extensions,
            disk=self.disk,
        )


def release_tree(tree: ScanTree | None = None) -> None:
    """Free a tree from an earlier scan, once nothing else refers to it.

    Breaking its links (``ScanTree.dispose``) lets reference counting free it
    at once; unfreezing undoes the ``gc.freeze()`` at the end of ``Scanner._run``.
    """
    if tree is not None:
        tree.dispose()
    gc.unfreeze()


def _describe(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "Access denied"
    if isinstance(exc, FileNotFoundError):
        return "No longer exists"
    return exc.strerror or str(exc)
