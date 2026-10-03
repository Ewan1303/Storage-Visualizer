"""What the treemap and the sunburst have in common: caching, hovering and clicking."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ..core.layout import FILE, REST
from .describe import tooltip_lines
from .painting import paint_tooltip, qcolor
from .state import ViewState
from .theme import ThemeManager


class ChartView(QWidget):
    """Base class for the two charts.

    A subclass builds a layout for the current size (``build_layout``), paints it
    into a cached pixmap (``paint_chart``), finds the item under a point
    (``item_at``) and outlines items (``paint_outline``). Items are the layout's
    tiles or segments: anything with ``kind``, ``node``, ``value`` and ``count``.

    Mouse: hover shows a card, click selects, double-click zooms in, right-click
    asks for a context menu, and the mouse's back button goes up a level.
    """

    contextMenuRequested = Signal(object, QPoint)  # node, global position

    def __init__(self, state: ViewState, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.themes = themes
        self.setMouseTracking(True)
        self.setMinimumSize(240, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._pixmap: QPixmap | None = None
        self._layout_dirty = True
        self._pixels_dirty = True
        self._resizing = False
        self._hover = None       # item under the mouse
        self._external = None    # node hovered in another widget, e.g. a table row
        self._mouse: QPoint | None = None
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(120)
        self._settle.timeout.connect(self._resize_settled)
        state.treeChanged.connect(self.invalidate_layout)
        state.rootChanged.connect(self.invalidate_layout)
        state.sizesChanged.connect(self.invalidate_layout)
        state.emphasisChanged.connect(self.invalidate_pixels)
        state.selectionChanged.connect(self.update)
        state.hoverChanged.connect(self._on_hover_changed)
        themes.changed.connect(self.invalidate_pixels)

    # ------------------------------------------------------- subclass hooks

    def build_layout(self) -> None:
        raise NotImplementedError

    def clear_layout(self) -> None:
        raise NotImplementedError

    def paint_chart(self, painter: QPainter) -> None:
        raise NotImplementedError

    def item_at(self, pos: QPoint):
        raise NotImplementedError

    def item_for(self, node):
        """The item drawn for ``node``, or None if it is too small to be drawn."""
        raise NotImplementedError

    def paint_outline(self, painter: QPainter, item, *, selected: bool) -> None:
        raise NotImplementedError

    def is_empty(self) -> bool:
        """True when the current folder has nothing to draw."""
        raise NotImplementedError

    def describe(self, item):
        return tooltip_lines(self.state, item.kind, item.node, item.value, item.count)

    def lift_colour(self) -> QColor:
        """Wash laid over a hovered tile so it visibly responds."""
        return QColor(255, 255, 255, 38) if self.themes.theme.is_dark else QColor(0, 0, 0, 24)

    # --------------------------------------------------------- invalidation

    def invalidate_layout(self) -> None:
        """The content changed (another folder, other sizes): rebuild at the next paint."""
        self.clear_layout()
        self._pixmap = None  # never stretch a picture of something else while resizing
        self._resizing = False
        self._settle.stop()
        self._layout_dirty = True
        self._hover = None
        self._external = None
        self.update()

    def invalidate_pixels(self) -> None:
        self._pixels_dirty = True
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._pixmap is None:
            self._layout_dirty = True
            return
        # Redrawing a big tree on every pixel of a drag is wasteful: stretch the
        # old picture until the size settles.
        self._resizing = True
        self._settle.start()

    def _resize_settled(self) -> None:
        self._resizing = False
        self.clear_layout()
        self._layout_dirty = True
        self._hover = None
        self.update()

    # ------------------------------------------------------------- painting

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        theme = self.themes.theme
        if self.state.tree is None or self.state.root is None or self.width() < 2 or self.height() < 2:
            p.fillRect(self.rect(), qcolor(theme.surface))
            return
        if self._resizing and self._pixmap is not None:
            p.fillRect(self.rect(), qcolor(theme.surface))
            p.drawPixmap(self.rect(), self._pixmap)
            return
        if self._layout_dirty:
            self.build_layout()
            self._layout_dirty = False
            self._pixels_dirty = True
        if self._pixels_dirty or self._pixmap is None:
            self._pixmap = self._render()
            self._pixels_dirty = False
        p.drawPixmap(0, 0, self._pixmap)
        if self.is_empty():
            self._paint_empty_message(p)
            return
        self._paint_overlay(p)

    def _paint_empty_message(self, p: QPainter) -> None:
        state, root = self.state, self.state.root
        if root.error and not root.children:
            text = f"This folder couldn't be read ({root.error})."
        elif root.cloud and not state.include_cloud:
            text = ("Everything here is stored online only, so it takes no space on this PC.\n"
                    "Turn on View → Count online-only files to see it.")
        else:
            text = "Nothing to show: this folder is empty."
        p.setPen(qcolor(self.themes.theme.muted))
        p.drawText(self.rect().adjusted(24, 24, -24, -24),
                   int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), text)

    def _render(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(qcolor(self.themes.theme.surface))
        painter = QPainter(pixmap)
        try:
            self.paint_chart(painter)
        finally:
            painter.end()
        return pixmap

    def _paint_overlay(self, p: QPainter) -> None:
        selected = self.state.selected
        if selected is not None:
            item = self.item_for(selected)
            if item is not None:
                self.paint_outline(p, item, selected=True)
        if self._hover is not None:
            self.paint_outline(p, self._hover, selected=False)
            if self._mouse is not None:
                paint_tooltip(p, self.themes.theme, self._mouse, self.rect(), self.describe(self._hover),
                              self.font())
        elif self._external is not None:
            item = self.item_for(self._external)
            if item is not None:
                self.paint_outline(p, item, selected=False)

    # ---------------------------------------------------------------- mouse

    def _item_under(self, pos: QPoint):
        return None if self._layout_dirty else self.item_at(pos)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        self._mouse = pos
        item = self._item_under(pos)
        if item is not self._hover:
            self._hover = item
            node = item.node if item is not None and item.kind != REST else None
            self.state.hover(node, source=self)
        self.update()

    def leaveEvent(self, event) -> None:
        self._mouse = None
        if self._hover is not None:
            self._hover = None
            self.state.hover(None, source=self)
        self.update()

    def mousePressEvent(self, event) -> None:
        item = self._item_under(event.position().toPoint())
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            self.click(item)
        elif button == Qt.MouseButton.RightButton:
            if item is not None:
                self.contextMenuRequested.emit(item.node, event.globalPosition().toPoint())
        elif button == Qt.MouseButton.BackButton:
            self.state.go_up()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activate(self._item_under(event.position().toPoint()))

    def click(self, item) -> None:
        self.state.select(item.node if item is not None and item.kind != REST else None)

    def activate(self, item) -> None:
        """Double-click: zoom into a folder, or into the folder holding a file."""
        if item is None:
            return
        if item.kind == FILE:
            self.state.set_root(item.node.parent)
        else:
            self.state.set_root(item.node)

    def _on_hover_changed(self, source: object) -> None:
        if source is not self:
            self._external = self.state.hovered
            self.update()
