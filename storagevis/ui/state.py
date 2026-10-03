"""What the user is looking at, shared by every widget.

Widgets never talk to each other directly: they change this state and react
to its signals, so the treemap, sunburst, tables and details panel stay in
step (hovering a table row outlines the same item in the chart, and so on).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..core.model import DirNode, Node, ScanTree, SizeView, dominant, is_within

Emphasis = tuple[str, object]  # ("category", index) or ("extension", "mp4")


class ViewState(QObject):
    treeChanged = Signal()
    rootChanged = Signal()
    sizesChanged = Signal()           # online-only files switched in or out
    selectionChanged = Signal()
    hoverChanged = Signal(object)     # carries the widget that set it
    emphasisChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.tree: ScanTree | None = None
        self.sizes: SizeView | None = None
        self.root: DirNode | None = None
        self.selected: Node | None = None
        self.hovered: Node | None = None
        self.emphasis: Emphasis | None = None
        self.include_cloud = False

    # ------------------------------------------------------------------ tree

    def set_tree(self, tree: ScanTree | None, root: DirNode | None = None) -> None:
        self.tree = tree
        self.sizes = SizeView(tree, self.include_cloud) if tree is not None else None
        self.root = root if root is not None else (tree.root if tree is not None else None)
        self.selected = None
        self.hovered = None
        self.emphasis = None
        self.treeChanged.emit()
        self.rootChanged.emit()
        self.selectionChanged.emit()
        self.emphasisChanged.emit()

    def set_include_cloud(self, include: bool) -> None:
        if include == self.include_cloud:
            return
        self.include_cloud = include
        if self.tree is not None:
            self.sizes = SizeView(self.tree, include)
        self.sizesChanged.emit()

    # ------------------------------------------------------------ navigation

    def set_root(self, node: Node | None) -> None:
        if node is None or not node.is_dir or node is self.root or self.tree is None:
            return
        self.root = node
        self.hovered = None
        if self.selected is not None and not is_within(self.selected, node):
            self.selected = None
            self.selectionChanged.emit()
        self.rootChanged.emit()

    @property
    def can_go_up(self) -> bool:
        return self.root is not None and self.tree is not None and self.root is not self.tree.root

    def go_up(self) -> None:
        if self.can_go_up:
            previous = self.root
            self.set_root(previous.parent)
            self.select(previous)  # so it is easy to see where you came from

    def go_top(self) -> None:
        if self.tree is not None:
            self.set_root(self.tree.root)

    # ---------------------------------------------------- selection & hover

    def select(self, node: Node | None) -> None:
        if node is not self.selected:
            self.selected = node
            self.selectionChanged.emit()

    def hover(self, node: Node | None, source: object = None) -> None:
        if node is not self.hovered:
            self.hovered = node
            self.hoverChanged.emit(source)

    # -------------------------------------------------------------- emphasis

    def set_emphasis(self, emphasis: Emphasis | None) -> None:
        if emphasis != self.emphasis:
            self.emphasis = emphasis
            self.emphasisChanged.emit()

    def toggle_emphasis(self, emphasis: Emphasis) -> None:
        self.set_emphasis(None if emphasis == self.emphasis else emphasis)

    def emphasised(self, node: Node) -> bool:
        """Whether an item matches the current highlight (always true with no highlight).

        Folders count as their largest file type, the way they are coloured.
        """
        if self.emphasis is None:
            return True
        kind, value = self.emphasis
        if kind == "category":
            category = node.category if not node.is_dir else self.sizes.dominant_category(node)
            return category == value
        if node.is_dir:
            return False
        return node.ext == value

    def folded_category(self, folder: DirNode, count: int) -> int:
        """The file type filling most of a folder's ``count`` smallest items."""
        return dominant(self.sizes.folded_category_values(folder, count))

    def folded_emphasised(self, folder: DirNode, count: int) -> bool:
        if self.emphasis is None:
            return True
        kind, value = self.emphasis
        return kind == "category" and self.folded_category(folder, count) == value
