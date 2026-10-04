"""The tables beside the chart: what is in this folder, file types, and the largest files.

They are the chart's readable twin: every size the chart shows can also be
read here without hovering.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QTableView, QWidget)

from ..core.categories import CATEGORIES
from ..core.formatting import format_count, format_share, format_size
from ..core.model import ExtensionStat, Node
from .background import Background
from .painting import folder_icon, glyph_icon, qcolor, swatch_icon
from .state import ViewState
from .theme import ThemeManager

SHARE_ROLE = Qt.ItemDataRole.UserRole + 1
NAME, SIZE, SHARE, LAST = range(4)
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class RowIcons:
    """Theme-coloured row icons, rebuilt when the theme changes."""

    def __init__(self, themes: ThemeManager) -> None:
        self.themes = themes
        self._cache: dict[tuple, QIcon] = {}
        themes.changed.connect(lambda _theme: self._cache.clear())

    def folder(self) -> QIcon:
        key = ("folder", self.themes.theme.name)
        if key not in self._cache:
            self._cache[key] = folder_icon(self.themes.theme.text2)
        return self._cache[key]

    def category(self, index: int) -> QIcon:
        key = ("category", index, self.themes.theme.name)
        if key not in self._cache:
            self._cache[key] = swatch_icon(self.themes.theme.categories[index])
        return self._cache[key]

    def cloud(self) -> QIcon:
        """Marks online-only files."""
        key = ("cloud", self.themes.theme.name)
        if key not in self._cache:
            self._cache[key] = glyph_icon("cloud", self.themes.theme.text2, 14)
        return self._cache[key]


class BaseTableModel(QAbstractTableModel):
    """Rows recomputed from the view state. Hidden tables wait until they are shown."""

    headers: tuple[str, ...] = ("Name", "Size", "Share", "")
    right_aligned: tuple[int, ...] = (SIZE, LAST)

    def __init__(self, state: ViewState, themes: ThemeManager, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.themes = themes
        self.icons = RowIcons(themes)
        self._rows: list = []
        self._total = 0
        self._sort_column = SIZE
        self._sort_order = Qt.SortOrder.DescendingOrder
        self._dirty = True
        self._active = False
        for signal in (state.treeChanged, state.rootChanged, state.sizesChanged):
            signal.connect(self.invalidate)
        themes.changed.connect(self._restyle)

    # ------------------------------------------------------------- loading

    def load(self) -> list:
        raise NotImplementedError

    def sort_key(self, column: int) -> Callable:
        raise NotImplementedError

    def set_active(self, active: bool) -> None:
        self._active = active
        if active and self._dirty:
            self.refresh()

    def invalidate(self) -> None:
        self._dirty = True
        if self._active or self.state.tree is None:
            self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        state = self.state
        if state.tree is not None and state.root is not None:
            self._total = state.sizes.value(state.root)
            self._rows = self.load()
            self._sort_rows()
        else:
            self.unload()
            self._rows = []
            self._total = 0
        self._dirty = False
        self.endResetModel()

    def unload(self) -> None:
        """Forget anything still pending for a tree that has gone."""

    def _restyle(self, _theme) -> None:
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, self.columnCount() - 1))

    def _sort_rows(self) -> None:
        if not self._rows:
            return
        self._rows.sort(key=self.sort_key(self._sort_column),
                        reverse=self._sort_order == Qt.SortOrder.DescendingOrder)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        self._sort_column, self._sort_order = column, order
        self.layoutAboutToBeChanged.emit()
        self._sort_rows()
        self.layoutChanged.emit()
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)

    # ------------------------------------------------------------ Qt model

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                # The sort direction is shown in the text: Fusion would draw its arrow over it.
                if section == self._sort_column:
                    arrow = "↓" if self._sort_order == Qt.SortOrder.DescendingOrder else "↑"
                    return f"{self.headers[section]} {arrow}"
                return self.headers[section]
            if role == Qt.ItemDataRole.TextAlignmentRole and section in self.right_aligned:
                return _RIGHT
        return None

    def row(self, index: int):
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def node_at(self, index: int) -> Node | None:
        return None

    def row_of(self, node: Node | None) -> int | None:
        return None


class NodeTableModel(BaseTableModel):
    """Rows that are files or folders."""

    def node_at(self, index: int) -> Node | None:
        return self.row(index)

    def row_of(self, node: Node | None) -> int | None:
        if node is None:
            return None
        for i, row in enumerate(self._rows):
            if row is node:
                return i
        return None

    def name_tooltip(self, node: Node) -> str:
        return self.state.tree.path_of(node)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = self._rows[index.row()]
        column = index.column()
        value = self.state.sizes.value(node)
        if role == Qt.ItemDataRole.DisplayRole:
            if column == NAME:
                return node.name
            if column == SIZE:
                return format_size(value)
            if column == LAST:
                return self.last_column(node)
            return None
        if role == SHARE_ROLE:
            return value / self._total if self._total else 0.0
        if role == Qt.ItemDataRole.DecorationRole and column == NAME:
            return self.icons.folder() if node.is_dir else self.icons.category(node.category)
        if role == Qt.ItemDataRole.TextAlignmentRole and column in self.right_aligned:
            return _RIGHT
        if role == Qt.ItemDataRole.ToolTipRole:
            if node.is_dir and node.error:
                return f"{self.name_tooltip(node)}\nCouldn't be read: {node.error}"
            return self.name_tooltip(node)
        if role == Qt.ItemDataRole.ForegroundRole and node.is_dir and node.error and not node.children:
            return qcolor(self.themes.theme.muted)
        return None

    def last_column(self, node: Node) -> str:
        raise NotImplementedError


class ContentsModel(NodeTableModel):
    """Everything directly inside the folder being viewed."""

    headers = ("Name", "Size", "Share", "Files")

    def load(self) -> list:
        return list(self.state.sizes.children(self.state.root))

    def sort_key(self, column: int) -> Callable:
        value = self.state.sizes.value
        if column == NAME:
            return lambda n: n.name.casefold()
        if column == LAST:
            return lambda n: n.files if n.is_dir else -1
        return value

    def last_column(self, node: Node) -> str:
        return format_count(node.files) if node.is_dir else ""


class LargestModel(NodeTableModel):
    """The biggest files anywhere below the folder being viewed."""

    headers = ("Name", "Size", "Share", "Folder")
    right_aligned = (SIZE,)
    LIMIT = 200

    def load(self) -> list:
        return list(self.state.sizes.largest_files(self.state.root, self.LIMIT))

    def sort_key(self, column: int) -> Callable:
        if column == NAME:
            return lambda n: n.name.casefold()
        if column == LAST:
            return lambda n: self.last_column(n).casefold()
        return self.state.sizes.value

    def last_column(self, node: Node) -> str:
        parts = []
        folder = node.parent
        while folder is not None and folder is not self.state.root:
            parts.append(folder.name)
            folder = folder.parent
        return "\\".join(reversed(parts)) if parts else "(this folder)"


class TypesModel(BaseTableModel):
    """Bytes per file extension below the folder being viewed.

    Counting means visiting every file below the folder, so for big folders it
    happens in the background while the table says so.
    """

    headers = ("Type", "Size", "Share", "Files")
    LIMIT = 300
    BACKGROUND_FROM = 40_000  # files below the folder

    def __init__(self, state: ViewState, themes: ThemeManager, parent=None) -> None:
        super().__init__(state, themes, parent)
        self._background = Background(self)
        self._background.finished.connect(self._counted)
        self._job = 0
        self.loading = False

    def load(self) -> list:
        sizes, root = self.state.sizes, self.state.root
        self._job += 1
        if sizes.has_extension_stats(root) or root.files < self.BACKGROUND_FROM:
            self.loading = False
            return self._top(sizes.extension_stats(root))
        self.loading = True
        self._background.run((self._job, sizes, root), lambda: sizes.extension_stats(root))
        return []

    def unload(self) -> None:
        self._job += 1
        self.loading = False

    def _top(self, stats: list[ExtensionStat]) -> list[ExtensionStat]:
        return [r for r in stats[:self.LIMIT] if r.files]

    def _counted(self, job: tuple, stats) -> None:
        number, sizes, root = job
        if number != self._job or sizes is not self.state.sizes or root is not self.state.root:
            return  # the view moved on while this was counting
        self.beginResetModel()
        self.loading = False
        self._rows = self._top(stats or [])
        self._sort_rows()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if self.loading and not parent.isValid():
            return 1
        return super().rowCount(parent)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if self.loading:
            return Qt.ItemFlag.ItemIsEnabled
        return super().flags(index)

    def sort_key(self, column: int) -> Callable:
        if column == NAME:
            return lambda r: r.extension
        if column == LAST:
            return lambda r: r.files
        return lambda r: r.bytes

    def stat_at(self, index: int) -> ExtensionStat | None:
        return self.row(index)

    def row_of_extension(self, ext: str) -> int | None:
        for i, row in enumerate(self._rows):
            if row.extension == ext:
                return i
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if self.loading:
            if role == Qt.ItemDataRole.DisplayRole and index.column() == NAME:
                return "Counting file types…"
            if role == Qt.ItemDataRole.ForegroundRole:
                return qcolor(self.themes.theme.muted)
            return None
        stat: ExtensionStat = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == NAME:
                return f".{stat.extension}" if stat.extension else "(no extension)"
            if column == SIZE:
                return format_size(stat.bytes)
            if column == LAST:
                return format_count(stat.files)
            return None
        if role == SHARE_ROLE:
            return stat.bytes / self._total if self._total else 0.0
        if role == Qt.ItemDataRole.DecorationRole and column == NAME:
            return self.icons.category(stat.category)
        if role == Qt.ItemDataRole.TextAlignmentRole and column in self.right_aligned:
            return _RIGHT
        if role == Qt.ItemDataRole.ToolTipRole:
            return (f"{CATEGORIES[stat.category].label}. Click to highlight these files in the chart; "
                    "double-click to list them all in the file type viewer.")
        return None


class ShareDelegate(QStyledItemDelegate):
    """A share column drawn as a quiet bar with the percentage beside it."""

    def __init__(self, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.themes = themes

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        fraction = index.data(SHARE_ROLE) or 0.0
        theme = self.themes.theme
        rect = option.rect.adjusted(6, 0, -6, 0)
        fm = option.fontMetrics
        text_width = fm.horizontalAdvance("100.0%") + 4
        bar = QRectF(rect.left(), rect.center().y() - 2.5, max(0, rect.width() - text_width - 6), 5)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(theme.track))
        painter.drawRoundedRect(bar, 2.5, 2.5)
        if fraction > 0 and bar.width() > 0:
            painter.setBrush(qcolor(theme.text2))
            painter.drawRoundedRect(QRectF(bar.left(), bar.top(), max(2.0, bar.width() * min(fraction, 1.0)),
                                           bar.height()), 2.5, 2.5)
        painter.setPen(qcolor(theme.text2))
        painter.drawText(QRectF(bar.right() + 6, rect.top(), text_width, rect.height()), _RIGHT,
                         format_share(fraction))
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(120, option.fontMetrics.height() + 8)


class _Table(QTableView):
    """Shared look and behaviour of the three tables."""

    def __init__(self, state: ViewState, model: BaseTableModel, themes: ThemeManager,
                 last_column_width: int = 70) -> None:
        super().__init__()
        self.state = state
        self.setModel(model)
        self.setItemDelegateForColumn(SHARE, ShareDelegate(themes, self))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setIconSize(QSize(14, 14))
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(26)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(SIZE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(SHARE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(LAST, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(SIZE, 76)
        header.resizeSection(SHARE, 112)
        header.resizeSection(LAST, last_column_width)
        header.setSortIndicator(SIZE, Qt.SortOrder.DescendingOrder)
        header.setSortIndicatorShown(True)
        self.setSortingEnabled(True)

    def table_model(self) -> BaseTableModel:
        return self.model()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if isinstance(self.model(), BaseTableModel):
            self.model().set_active(True)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if isinstance(self.model(), BaseTableModel):  # the model may be gone while the app shuts down
            self.model().set_active(False)


class NodeTable(_Table):
    """A table of files and folders, kept in step with the chart's selection and hover."""

    nodeActivated = Signal(object)
    contextMenuForNode = Signal(object, QPoint)

    def __init__(self, state: ViewState, model: NodeTableModel, themes: ThemeManager,
                 last_column_width: int = 70) -> None:
        super().__init__(state, model, themes, last_column_width)
        self._syncing = False
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.entered.connect(self._entered)
        self.doubleClicked.connect(self._double_clicked)
        self.selectionModel().currentRowChanged.connect(self._current_changed)
        state.selectionChanged.connect(self._sync_selection)
        model.modelReset.connect(self._sync_selection)
        model.layoutChanged.connect(self._sync_selection)

    def _entered(self, index: QModelIndex) -> None:
        self.state.hover(self.table_model().node_at(index.row()), source=self)

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Leave:
            self.state.hover(None, source=self)
        return super().viewportEvent(event)

    def _current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if self._syncing or not current.isValid():
            return
        node = self.table_model().node_at(current.row())
        if node is not None:
            self.state.select(node)

    def _sync_selection(self) -> None:
        row = self.table_model().row_of(self.state.selected)
        self._syncing = True
        try:
            if row is None:
                self.clearSelection()
                self.setCurrentIndex(QModelIndex())
            else:
                index = self.model().index(row, NAME)
                self.setCurrentIndex(index)
                self.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)
        finally:
            self._syncing = False

    def _double_clicked(self, index: QModelIndex) -> None:
        node = self.table_model().node_at(index.row())
        if node is not None:
            self.nodeActivated.emit(node)

    def _context_menu(self, pos: QPoint) -> None:
        index = self.indexAt(pos)
        node = self.table_model().node_at(index.row()) if index.isValid() else None
        if node is not None:
            self.contextMenuForNode.emit(node, self.viewport().mapToGlobal(pos))


class TypesTable(_Table):
    """File types; clicking one highlights its files in the chart, double-clicking lists them."""

    extensionActivated = Signal(str)

    def __init__(self, state: ViewState, model: TypesModel, themes: ThemeManager) -> None:
        super().__init__(state, model, themes, last_column_width=64)
        self.clicked.connect(self._clicked)
        self.doubleClicked.connect(self._double_clicked)
        state.emphasisChanged.connect(self._sync_selection)
        model.modelReset.connect(self._sync_selection)
        model.layoutChanged.connect(self._sync_selection)

    def _clicked(self, index: QModelIndex) -> None:
        stat = self.table_model().stat_at(index.row())
        if stat is not None:
            self.state.toggle_emphasis(("extension", stat.extension))

    def _double_clicked(self, index: QModelIndex) -> None:
        stat = self.table_model().stat_at(index.row())
        if stat is not None:
            self.state.set_emphasis(("extension", stat.extension))
            self.extensionActivated.emit(stat.extension)

    def _sync_selection(self) -> None:
        emphasis = self.state.emphasis
        row = None
        if emphasis is not None and emphasis[0] == "extension":
            row = self.table_model().row_of_extension(emphasis[1])
        blocker = self.selectionModel().blockSignals(True)
        try:
            if row is None:
                self.clearSelection()
            else:
                self.selectRow(row)
        finally:
            self.selectionModel().blockSignals(blocker)
        self.viewport().update()
