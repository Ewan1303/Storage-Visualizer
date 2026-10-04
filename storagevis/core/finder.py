"""Finding every file of the chosen kinds below a folder: the file type viewer's search.

Folders whose byte totals show none of the wanted kinds are skipped without
opening them, so asking for "all photos" on a whole drive stays quick.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .categories import COUNT as N_CATEGORIES
from .categories import EXTENSION_KIND, KIND_CATEGORY, Kind
from .model import DirNode, FileNode

# Folders that hold programs, caches and system files rather than things people
# made or saved. Skipped by default so "all my photos" is not buried under
# thousands of app icons and game textures.
SYSTEM_FOLDERS = frozenset({
    "windows", "windows.old", "program files", "program files (x86)", "programdata",
    "appdata", "$recycle.bin", "system volume information", "$windows.~bt", "$windows.~ws",
    "recovery", "msocache", "steamapps", "node_modules", ".git", ".svn", ".hg", "__pycache__",
    "site-packages", ".venv", "venv", ".cache", ".gradle", ".nuget", ".npm",
})


@dataclass(frozen=True)
class FileQuery:
    kinds: frozenset[Kind] = frozenset(Kind)
    extensions: frozenset[str] | None = None  # None: every extension of those kinds
    text: str = ""                            # part of the name, any case
    min_size: int = 1                         # bytes; empty files are never listed
    skip_system: bool = True                  # leave out SYSTEM_FOLDERS below the start


@dataclass
class FileMatches:
    files: list[FileNode]                     # everything that passed every filter
    # (extension, files, bytes) for the chosen kinds before the extension filter,
    # most files first: what the extension picker offers.
    extensions: list[tuple[str, int, int]] = field(default_factory=list)
    bytes: int = 0                            # of ``files``, counting online-only content
    cloud_bytes: int = 0                      # the online-only part of ``bytes``
    by_kind: dict[Kind, int] = field(default_factory=dict)  # file counts


def find_files(under: DirNode, query: FileQuery,
               stop: Callable[[], bool] | None = None) -> FileMatches | None:
    """Every file below ``under`` that matches ``query``, or None if ``stop()`` said so.

    Sizes here always include online-only content: an online-only photo is
    still one of your photos, even though it takes no space on this PC.
    """
    kinds = query.kinds
    if not kinds:
        return FileMatches([])
    categories = sorted({KIND_CATEGORY[k] for k in kinds})
    every_kind = len(kinds) == len(Kind)
    extensions = query.extensions
    text = query.text.casefold().strip()
    min_size = max(1, query.min_size)
    skip = SYSTEM_FOLDERS if query.skip_system else frozenset()
    kind_of = EXTENSION_KIND.get
    other = Kind.OTHER

    files: list[FileNode] = []
    per_extension: dict[str, list[int]] = {}
    stack = [under]
    visited = 0
    while stack:
        folder = stack.pop()
        visited += 1
        if stop is not None and visited & 255 == 1 and stop():  # the 1st folder, then every 256th
            return None
        for child in folder.children:
            if child.is_dir:
                if skip and child.name.casefold() in skip:
                    continue
                if not every_kind and not _holds(child, categories):
                    continue
                stack.append(child)
                continue
            nbytes = child.size + child.cloud
            if nbytes < min_size:
                continue
            if not every_kind and kind_of(child.ext, other) not in kinds:
                continue
            if text and text not in child.name.casefold():
                continue
            record = per_extension.get(child.ext)
            if record is None:
                record = per_extension[child.ext] = [0, 0]
            record[0] += 1
            record[1] += nbytes
            if extensions is None or child.ext in extensions:
                files.append(child)

    matches = FileMatches(files)
    matches.extensions = sorted(((ext, n, b) for ext, (n, b) in per_extension.items()),
                                key=lambda row: (row[1], row[2]), reverse=True)
    by_kind: dict[Kind, int] = {}
    for f in files:
        matches.bytes += f.size + f.cloud
        matches.cloud_bytes += f.cloud
        kind = kind_of(f.ext, other)
        by_kind[kind] = by_kind.get(kind, 0) + 1
    matches.by_kind = by_kind
    return matches


def _holds(folder: DirNode, categories: list[int]) -> bool:
    """Whether anything below ``folder`` belongs to one of the chart categories."""
    totals = folder.by_category
    return any(totals[c] or totals[N_CATEGORIES + c] for c in categories)
