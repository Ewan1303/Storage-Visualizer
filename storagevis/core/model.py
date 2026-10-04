"""The in-memory tree of a scanned folder, and the size queries the views need.

Nodes are kept tiny (``__slots__``) because scanning a whole drive can create
millions of them. Every node carries two sizes:

* ``size``  - bytes actually stored on this PC
* ``cloud`` - bytes of OneDrive-style "online-only" files, which appear in the
  folder but take no local space until they are opened
"""

from __future__ import annotations

import heapq
import itertools
import os
import sys
from array import array
from collections.abc import Iterator
from operator import attrgetter, itemgetter
from typing import NamedTuple

from .categories import COUNT as N_CATEGORIES
from .categories import EXTENSION_CATEGORY, OTHER, category_of_extension, extension_of
from .system import to_fs_path

# Per-folder bytes by category: N_CATEGORIES local slots, then N_CATEGORIES online-only slots.
_ZERO_CATEGORIES = array("q", bytes(8 * 2 * N_CATEGORIES))


class Node:
    __slots__ = ("name", "parent", "size", "cloud")
    is_dir = False

    def __init__(self, name: str, parent: DirNode | None) -> None:
        self.name = name
        self.parent = parent
        self.size = 0
        self.cloud = 0

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name!r} size={self.size} cloud={self.cloud}>"


class FileNode(Node):
    # ``ext`` is shared between files (interned), so storing it costs one pointer.
    __slots__ = ("ext", "mtime")

    def __init__(self, name: str, parent: DirNode | None, size: int, cloud: int, ext: str,
                 mtime: float = 0.0) -> None:
        self.name = name
        self.parent = parent
        self.size = size
        self.cloud = cloud
        self.ext = ext
        self.mtime = mtime  # last modified, seconds since 1970 (0 when unknown)

    @property
    def total(self) -> int:
        """Bytes counting online-only content too: the file's size as Explorer shows it."""
        return self.size + self.cloud

    @property
    def category(self) -> int:
        return EXTENSION_CATEGORY.get(self.ext, OTHER)

    @property
    def extension(self) -> str:
        return self.ext

    @property
    def online_only(self) -> bool:
        return self.cloud > 0


class DirNode(Node):
    __slots__ = ("children", "files", "dirs", "by_category", "biggest", "biggest_total", "error")
    is_dir = True

    def __init__(self, name: str, parent: DirNode | None = None) -> None:
        self.name = name
        self.parent = parent
        self.size = 0
        self.cloud = 0
        self.children: list[Node] = []
        self.files = 0          # files in this folder; everything below it once aggregate() has run
        self.dirs = 0           # sub-folders below this one, filled in by aggregate()
        self.by_category = _ZERO_CATEGORIES[:]
        self.biggest = 0        # largest local file at or below this folder (after aggregate())
        self.biggest_total = 0  # the same, counting online-only files
        self.error: str | None = None

    def add_dir(self, name: str) -> DirNode:
        child = DirNode(name, self)
        self.children.append(child)
        return child

    def add_file(self, name: str, nbytes: int, *, online_only: bool = False, mtime: float = 0.0) -> FileNode:
        """Add a file and count it in this folder's own totals."""
        ext = sys.intern(extension_of(name))
        category = EXTENSION_CATEGORY.get(ext, OTHER)
        if online_only:
            node = FileNode(name, self, 0, nbytes, ext, mtime)
            self.cloud += nbytes
            self.by_category[N_CATEGORIES + category] += nbytes
        else:
            node = FileNode(name, self, nbytes, 0, ext, mtime)
            self.size += nbytes
            self.by_category[category] += nbytes
            self.biggest = max(self.biggest, nbytes)
        self.biggest_total = max(self.biggest_total, nbytes)
        self.children.append(node)
        self.files += 1
        return node


def aggregate(root: DirNode) -> None:
    """Turn every folder's own totals into totals for everything below it.

    Run once, after the tree is built.
    """
    order = [root]
    for folder in order:  # breadth-first: the list grows while it is walked
        for child in folder.children:
            if child.is_dir:
                order.append(child)
    slots = range(2 * N_CATEGORIES)
    for folder in reversed(order):  # children are always finished before their parent
        parent = folder.parent
        if folder is root or parent is None:
            continue
        parent.size += folder.size
        parent.cloud += folder.cloud
        parent.files += folder.files
        parent.dirs += folder.dirs + 1
        if folder.biggest > parent.biggest:
            parent.biggest = folder.biggest
        if folder.biggest_total > parent.biggest_total:
            parent.biggest_total = folder.biggest_total
        into, add = parent.by_category, folder.by_category
        for i in slots:
            into[i] += add[i]


def iter_files(root: DirNode) -> Iterator[FileNode]:
    stack = [root]
    while stack:
        folder = stack.pop()
        for child in folder.children:
            if child.is_dir:
                stack.append(child)
            else:
                yield child


def is_within(node: Node | None, ancestor: Node) -> bool:
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent
    return False


def count_extensions(root: DirNode) -> dict[str, list[int]]:
    """{extension: [local bytes, online-only bytes, file count]} below ``root``."""
    totals: dict[str, list[int]] = {}
    get = totals.get
    for f in iter_files(root):
        record = get(f.ext)
        if record is None:
            record = totals[f.ext] = [0, 0, 0]
        record[0] += f.size
        record[1] += f.cloud
        record[2] += 1
    return totals


def dominant(values: list[int]) -> int:
    """The category holding the most bytes (Other when there are none)."""
    best = max(range(N_CATEGORIES), key=values.__getitem__)
    return best if values[best] > 0 else OTHER


class ScanTree:
    """A finished scan: the tree plus the totals gathered while walking it."""

    def __init__(self, root: DirNode, root_path: str, *, elapsed: float = 0.0, complete: bool = True,
                 errors: list[tuple[str, str]] | None = None, error_count: int | None = None,
                 skipped_links: int = 0, extensions: dict[str, list[int]] | None = None,
                 disk: tuple[int, int, int] | None = None) -> None:
        self.root = root
        self.root_path = root_path
        self.elapsed = elapsed
        self.complete = complete
        self.errors = errors or []
        self.error_count = len(self.errors) if error_count is None else error_count
        self.skipped_links = skipped_links
        self.disk = disk  # (total, used, free) of the drive, when known
        self.extensions = count_extensions(root) if extensions is None else extensions

    def path_of(self, node: Node) -> str:
        names = []
        while node is not None and node is not self.root:
            names.append(node.name)
            node = node.parent
        if not names:
            return self.root_path
        return os.path.join(self.root_path, *reversed(names))

    def fs_path_of(self, node: Node) -> str:
        return to_fs_path(self.path_of(node))

    def display_name(self, node: Node) -> str:
        if node is self.root:
            path = self.root_path.rstrip("\\/")
            return os.path.basename(path) or path or self.root_path
        return node.name

    def parts_of(self, node: Node) -> list[str]:
        """Names from the scan root down to ``node`` (empty for the root)."""
        names = []
        while node is not None and node is not self.root:
            names.append(node.name)
            node = node.parent
        return names[::-1]

    def find(self, parts: list[str]) -> Node | None:
        """The node at ``parts`` below the root (see :meth:`parts_of`), if it still exists."""
        node: Node = self.root
        for name in parts:
            if not node.is_dir:
                return None
            wanted = os.path.normcase(name)
            for child in node.children:
                if os.path.normcase(child.name) == wanted:
                    node = child
                    break
            else:
                return None
        return node

    def dispose(self) -> None:
        """Break every parent/child link so the whole tree is freed at once.

        Without this, the links form reference cycles that only a full garbage
        collection can clear, which takes seconds for a whole drive. The tree
        is unusable afterwards.
        """
        stack = [self.root]
        while stack:
            folder = stack.pop()
            children, folder.children = folder.children, []
            stack.extend(child for child in children if child.is_dir)


class ExtensionStat(NamedTuple):
    extension: str
    category: int
    bytes: int
    files: int


class SizeView:
    """Sizes as currently shown: local bytes only, or including online-only files.

    Also caches the sorted child lists and per-folder statistics, which are
    worked out lazily for the folders someone actually looks at. The tree never
    changes after a scan, so these lookups are safe to run on a worker thread.
    """

    def __init__(self, tree: ScanTree, include_cloud: bool = False) -> None:
        self.tree = tree
        self.include_cloud = include_cloud
        self._sorted: dict[Node, list[Node]] = {}
        self._extensions: dict[Node, list[ExtensionStat]] = {}
        self._largest: dict[tuple[Node, int], list[FileNode]] = {}
        self._folded: dict[tuple[Node, int], list[int]] = {}

    def value(self, node: Node) -> int:
        return node.size + node.cloud if self.include_cloud else node.size

    def children(self, node: Node) -> list[Node]:
        """Children of a folder, largest first."""
        kids = self._sorted.get(node)
        if kids is None:
            if not node.is_dir:
                return []
            key = (lambda n: n.size + n.cloud) if self.include_cloud else attrgetter("size")
            kids = sorted(node.children, key=key, reverse=True)
            self._sorted[node] = kids
        return kids

    def category_values(self, node: Node) -> list[int]:
        """Bytes per file-type category, in category order."""
        if node.is_dir:
            c = node.by_category
            if self.include_cloud:
                return [c[i] + c[i + N_CATEGORIES] for i in range(N_CATEGORIES)]
            return list(c[:N_CATEGORIES])
        values = [0] * N_CATEGORIES
        values[node.category] = self.value(node)
        return values

    def dominant_category(self, node: Node) -> int:
        if not node.is_dir:
            return node.category
        return dominant(self.category_values(node))

    def folded_category_values(self, node: DirNode, count: int) -> list[int]:
        """Bytes per category of the ``count`` smallest non-empty children of ``node``.

        These are the items a view folds into one "small items" area because
        they are too small to draw one by one.
        """
        key = (node, count)
        cached = self._folded.get(key)
        if cached is not None:
            return cached
        kids = self.children(node)
        value = self.value
        end = len(kids)
        while end > 0 and value(kids[end - 1]) <= 0:
            end -= 1
        totals = [0] * N_CATEGORIES
        for child in kids[max(0, end - count):end]:
            if child.is_dir:
                for i, v in enumerate(self.category_values(child)):
                    totals[i] += v
            else:
                totals[child.category] += value(child)
        self._folded[key] = totals
        return totals

    def largest_files(self, under: DirNode, limit: int = 200) -> list[FileNode]:
        """The ``limit`` biggest files at or below ``under``, biggest first.

        Folders are opened best-first by the biggest file they hold, so the
        search stops as soon as no unopened folder could beat the list so far.
        """
        key = (under, limit)
        cached = self._largest.get(key)
        if cached is not None:
            return cached
        value = self.value
        biggest = attrgetter("biggest_total" if self.include_cloud else "biggest")
        order = itertools.count()
        best: list[tuple[int, int, FileNode]] = []  # min-heap of the files kept so far
        folders = [(-biggest(under), next(order), under)]  # max-heap by biggest file inside
        while folders:
            negative, _, folder = heapq.heappop(folders)
            if len(best) >= limit and -negative <= best[0][0]:
                break
            for child in folder.children:
                if child.is_dir:
                    b = biggest(child)
                    if b > 0 and (len(best) < limit or b > best[0][0]):
                        heapq.heappush(folders, (-b, next(order), child))
                    continue
                v = value(child)
                if v <= 0:
                    continue
                if len(best) < limit:
                    heapq.heappush(best, (v, next(order), child))
                elif v > best[0][0]:
                    heapq.heapreplace(best, (v, next(order), child))
        result = [f for _, _, f in sorted(best, key=itemgetter(0, 1), reverse=True)]
        self._largest[key] = result
        return result

    def extension_stats(self, under: DirNode) -> list[ExtensionStat]:
        """Bytes and file counts per extension below ``under``, largest first."""
        cached = self._extensions.get(under)
        if cached is not None:
            return cached
        totals = self.tree.extensions if under is self.tree.root else count_extensions(under)
        rows = []
        for ext, (local, cloud, files) in totals.items():
            value = local + cloud if self.include_cloud else local
            rows.append(ExtensionStat(ext, category_of_extension(ext), value, files))
        rows.sort(key=lambda r: (r.bytes, r.files), reverse=True)
        self._extensions[under] = rows
        return rows

    def has_extension_stats(self, under: DirNode) -> bool:
        return under is self.tree.root or under in self._extensions
