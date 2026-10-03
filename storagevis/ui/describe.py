"""Words for files and folders, shared by the hover cards and the details panel."""

from __future__ import annotations

from ..core.categories import CATEGORIES, OTHER
from ..core.formatting import format_count, format_share, format_size
from ..core.layout import FILE, REST
from ..core.model import DirNode, FileNode, Node
from .painting import TipLine
from .state import ViewState


def share_of_view(state: ViewState, value: int) -> str:
    total = state.sizes.value(state.root) if state.root is not None else 0
    return f"{format_share(value / total)} of this view" if total > 0 else ""


def file_type(node: FileNode) -> str:
    ext = node.extension
    return f"{ext.upper()} file" if ext else "File"


def folder_contents(node: DirNode) -> str:
    if node.error and not node.children:
        return f"Couldn't be read: {node.error}"
    return f"{format_count(node.files, 'file')} · {format_count(node.dirs, 'folder')}"


def mostly_of(parts: list[int]) -> str:
    """'Mostly images (62%)' for bytes per category."""
    total = sum(parts)
    if total <= 0:
        return ""
    best = max(range(len(parts)), key=parts.__getitem__)
    label = "other file types" if best == OTHER else CATEGORIES[best].label.lower()
    return f"Mostly {label} ({format_share(parts[best] / total)})"


def mostly(state: ViewState, node: Node) -> str:
    return mostly_of(state.sizes.category_values(node))


def tooltip_lines(state: ViewState, kind: int, node: Node, value: int, count: int = 0) -> list[TipLine]:
    tree = state.tree
    lines = [TipLine(format_size(value), "value", extra=share_of_view(state, value))]
    if kind == REST:
        lines.append(TipLine(format_count(count, "small item"), "title"))
        parts = state.sizes.folded_category_values(node, count)
        if sum(parts) > 0:
            lines.append(TipLine("", "bar", parts=parts))
            lines.append(TipLine(mostly_of(parts), "detail"))
        lines.append(TipLine("Too small to draw one by one. Double-click to zoom in.", "detail"))
        lines.append(TipLine(tree.path_of(node), "path"))
        return lines
    lines.append(TipLine(tree.display_name(node), "title"))
    if kind == FILE:
        lines.append(TipLine(f"{CATEGORIES[node.category].label} · {file_type(node)}", "key",
                             category=node.category))
        if node.online_only:
            lines.append(TipLine("Online-only: not stored on this PC", "detail"))
        lines.append(TipLine(tree.path_of(node.parent), "path"))
        return lines
    lines.append(TipLine(folder_contents(node), "detail"))
    parts = state.sizes.category_values(node)
    if sum(parts) > 0:
        lines.append(TipLine("", "bar", parts=parts))
        lines.append(TipLine(mostly(state, node), "detail"))
    if node.error and node.children:
        lines.append(TipLine(f"Partly unreadable: {node.error}", "detail"))
    lines.append(TipLine(tree.path_of(node), "path"))
    return lines
