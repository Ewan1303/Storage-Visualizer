"""The file type viewer's results: one model, shown as a thumbnail grid or as a list."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from ..core.categories import KIND_NOUNS, Kind, kind_of_extension
from ..core.formatting import format_size
from ..core.model import DirNode, FileNode
from .painting import glyph, glyph_font, qcolor
from .state import ViewState
from .tables import RowIcons
from .theme import ThemeManager
from .thumbnails import ThumbnailProvider, size_step

NAME, SIZE, TYPE, MODIFIED, FOLDER = range(5)
HEADERS = ("Name", "Size", "Type", "Modified", "Folder")
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def type_text(node: FileNode) -> str:
    """'JPG photo', 'MP4 video', 'XYZ file'."""
    kind = kind_of_extension(node.ext)
    ext = node.ext.upper()
    if kind == Kind.OTHER:
        return f"{ext} file" if ext else "File"
    return f"{ext} {KIND_NOUNS[kind][0]}" if ext else KIND_NOUNS[kind][0].capitalize()


def date_text(mtime: float) -> str:
    if mtime <= 0:
        return ""
    try:
        return datetime.fromtimestamp(mtime).strftime("%d %b %Y")
    except (OverflowError, OSError, ValueError):
        return ""


class FileResultsModel(QAbstractTableModel):
    """The files found, in the chosen order."""

    sortChanged = Signal(int, object)  # column, Qt.SortOrder

    def __init__(self, state: ViewState, themes: ThemeManager, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.icons = RowIcons(themes)
        self._files: list[FileNode] = []
        self._column = SIZE
        self._order = Qt.SortOrder.DescendingOrder
        self._folders: dict[DirNode, str] = {}  # folder -> its path text, for one scan
        self._folders_tree = None

    # -------------------------------------------------------------- content

    def set_files(self, files: list[FileNode], sorted_by: tuple | None = None) -> None:
        """Show ``files``; ``sorted_by`` (column, order) says they are already in that order."""
        self.beginResetModel()
        self._files = list(files)
        if not self._files:
            self._folders = {}  # let go of folder names from an old scan
        if sorted_by != (self._column, self._order):
            self._sort_files()
        self.endResetModel()

    def sort_files(self, files: list[FileNode], column: int, order: Qt.SortOrder) -> None:
        """Sort a list the way the model would, in place. Safe on a worker thread."""
        files.sort(key=self._key(column), reverse=order == Qt.SortOrder.DescendingOrder)

    def files(self) -> list[FileNode]:
        return self._files

    def file_at(self, row: int) -> FileNode | None:
        return self._files[row] if 0 <= row < len(self._files) else None

    def folder_text(self, node: FileNode) -> str:
        """Where a file is, relative to the scanned folder."""
        tree = self.state.tree
        if tree is not self._folders_tree:
            self._folders, self._folders_tree = {}, tree
        folder = node.parent
        text = self._folders.get(folder)
        if text is None:
            if tree is None:
                return ""
            parts = tree.parts_of(folder)
            text = "\\".join(parts) if parts else tree.display_name(tree.root)
            self._folders[folder] = text
        return text

    # -------------------------------------------------------------- sorting

    @property
    def sort_column(self) -> int:
        return self._column

    @property
    def sort_order(self) -> Qt.SortOrder:
        return self._order

    def _key(self, column: int) -> Callable:
        if column == NAME:
            return lambda f: f.name.casefold()
        if column == TYPE:
            return lambda f: (kind_of_extension(f.ext), f.ext)
        if column == MODIFIED:
            return lambda f: f.mtime
        if column == FOLDER:
            return lambda f: (self.folder_text(f).casefold(), f.name.casefold())
        return lambda f: f.size + f.cloud

    def _sort_files(self) -> None:
        if self._files:
            self.sort_files(self._files, self._column, self._order)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        self._column, self._order = column, order
        self.layoutAboutToBeChanged.emit()
        kept = self.persistentIndexList()
        nodes = [self._files[i.row()] for i in kept]
        self._sort_files()
        rows = {node: row for row, node in enumerate(self._files)} if kept else {}
        self.changePersistentIndexList(kept, [self.index(rows[n], i.column()) for n, i in zip(nodes, kept)])
        self.layoutChanged.emit()
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(HEADERS) - 1)
        self.sortChanged.emit(column, order)

    # ------------------------------------------------------------- Qt model

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._files)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            if section == self._column:
                arrow = "↓" if self._order == Qt.SortOrder.DescendingOrder else "↑"
                return f"{HEADERS[section]} {arrow}"
            return HEADERS[section]
        if role == Qt.ItemDataRole.TextAlignmentRole and section == SIZE:
            return _RIGHT
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = self._files[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == NAME:
                return node.name
            if column == SIZE:
                return format_size(node.size + node.cloud)
            if column == TYPE:
                return type_text(node)
            if column == MODIFIED:
                return date_text(node.mtime)
            if column == FOLDER:
                return self.folder_text(node)
            return None
        if role == Qt.ItemDataRole.DecorationRole and column == NAME:
            return self.icons.category(node.category)
        if role == Qt.ItemDataRole.DecorationRole and column == TYPE and node.cloud:
            return self.icons.cloud()
        if role == Qt.ItemDataRole.TextAlignmentRole and column == SIZE:
            return _RIGHT
        if role == Qt.ItemDataRole.ToolTipRole:
            tree = self.state.tree
            path = tree.path_of(node) if tree is not None else node.name
            return f"{path}\nOnline-only: not stored on this PC" if node.cloud else path
        return None


def fit(image: QImage, box: QRectF, ratio: float) -> QRectF:
    """Where to draw ``image`` inside ``box``: whole, centred, never blown up past its own pixels."""
    width, height = image.width() / ratio, image.height() / ratio
    scale = min(box.width() / width, box.height() / height, 1.0)
    w, h = width * scale, height * scale
    return QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)


def paint_placeholder(p: QPainter, box: QRectF, node: FileNode, theme, font: QFont) -> None:
    """A tile with the file's extension, while (or instead of) a thumbnail."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(qcolor(theme.raised))
    p.drawRoundedRect(box, 6, 6)
    label = QFont(font)
    label.setWeight(QFont.Weight.DemiBold)
    label.setPointSizeF(max(8.0, min(16.0, box.width() / 9)))
    p.setFont(label)
    p.setPen(qcolor(theme.muted))
    p.drawText(box, Qt.AlignmentFlag.AlignCenter, node.ext.upper() or "FILE")


def paint_badge(p: QPainter, centre_x: float, centre_y: float, name: str, radius: float = 11) -> None:
    """A small dark disc with a white glyph: a video's play sign, the online-only cloud."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 150))
    p.drawEllipse(QRectF(centre_x - radius, centre_y - radius, 2 * radius, 2 * radius))
    font, available = glyph_font(round(radius * 1.05))
    p.setFont(font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(centre_x - radius, centre_y - radius, 2 * radius, 2 * radius),
               Qt.AlignmentFlag.AlignCenter, glyph(name, available))


class GridDelegate(QStyledItemDelegate):
    """Draws one grid cell: the thumbnail, then the name and the size and date."""

    PAD = 6
    SHAPE = 0.75  # picture area height / width: most photos and videos are landscape

    def __init__(self, state: ViewState, themes: ThemeManager, thumbnails: ThumbnailProvider,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.themes = themes
        self.thumbnails = thumbnails
        self.thumb = 160                          # smallest picture width, set by the size slider
        self.cell_width = self.smallest_cell()    # stretched so the cells fill each row

    def smallest_cell(self) -> int:
        return self.thumb + 2 * self.PAD + 8

    def cell_size(self, fm: QFontMetrics) -> QSize:
        picture = (self.cell_width - 8 - 2 * self.PAD) * self.SHAPE
        return QSize(self.cell_width, round(picture + 2 * fm.height() + 2 * self.PAD + 14))

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return self.cell_size(option.fontMetrics)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        node = index.model().file_at(index.row())
        tree = self.state.tree
        if node is None or tree is None:
            return
        theme = self.themes.theme
        pad = self.PAD
        cell = QRectF(option.rect).adjusted(4, 4, -4, -4)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        widget = option.widget
        ratio = widget.devicePixelRatioF() if widget is not None else 1.0

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if selected or hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor(theme.selected if selected else theme.hover))
            p.drawRoundedRect(cell, 8, 8)

        box = QRectF(cell.left() + pad, cell.top() + pad, cell.width() - 2 * pad,
                     (cell.width() - 2 * pad) * self.SHAPE)
        image = self.thumbnails.image(tree.path_of(node), size_step(box.width() * ratio), node.cloud > 0)
        if image is not None and not image.isNull():
            target = fit(image, box, ratio)
            clip = QPainterPath()
            clip.addRoundedRect(target, 4, 4)
            p.setClipPath(clip)
            p.drawImage(target, image)
            p.setClipping(False)
        else:
            target = box
            paint_placeholder(p, box, node, theme, option.font)
        if kind_of_extension(node.ext) == Kind.VIDEOS:
            paint_badge(p, target.left() + 16, target.bottom() - 16, "play")
        if node.cloud:
            paint_badge(p, target.right() - 16, target.top() + 16, "cloud")

        fm = option.fontMetrics
        width = cell.width() - 2 * pad
        top = box.bottom() + 6
        p.setFont(option.font)
        p.setPen(qcolor(theme.text))
        p.drawText(QRectF(cell.left() + pad, top, width, fm.height()), Qt.AlignmentFlag.AlignCenter,
                   fm.elidedText(node.name, Qt.TextElideMode.ElideMiddle, int(width)))
        details = format_size(node.size + node.cloud)
        if node.mtime > 0:
            details += f"  ·  {date_text(node.mtime)}"
        p.setPen(qcolor(theme.text2))
        p.drawText(QRectF(cell.left() + pad, top + fm.height(), width, fm.height()), Qt.AlignmentFlag.AlignCenter,
                   fm.elidedText(details, Qt.TextElideMode.ElideRight, int(width)))
        p.restore()
