"""The treemap: every file a rectangle sized by its bytes, nested inside its folders."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from ..core.formatting import format_count, format_size
from ..core.layout import FILE, FOLDER, REST, Tile, Treemap, TreemapStyle, build_treemap
from .chart_view import ChartView
from .painting import blend, ink_for, qcolor


class TreemapView(ChartView):
    STYLE = TreemapStyle()

    def __init__(self, state, themes, parent=None) -> None:
        super().__init__(state, themes, parent)
        self._map: Treemap | None = None
        self._make_fonts()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.FontChange:
            self._make_fonts()
            self.invalidate_pixels()

    def _make_fonts(self) -> None:
        base = self.font()
        size = base.pointSizeF() if base.pointSizeF() > 0 else 9.0
        self._name_font = QFont(base)
        self._name_font.setPointSizeF(max(7.5, size - 0.5))
        self._name_font.setWeight(QFont.Weight.DemiBold)
        self._size_font = QFont(base)
        self._size_font.setPointSizeF(max(7.5, size - 0.5))
        self._label_font = QFont(base)
        self._label_font.setPointSizeF(max(7.0, size - 1.0))

    # -------------------------------------------------------------- layout

    def clear_layout(self) -> None:
        self._map = None

    def build_layout(self) -> None:
        self._map = build_treemap(self.state.root, self.state.sizes, self.width(), self.height(), self.STYLE)

    def item_at(self, pos: QPoint) -> Tile | None:
        return self._map.hit(pos.x(), pos.y()) if self._map is not None else None

    def item_for(self, node) -> Tile | None:
        if self._map is None or node is self.state.root:
            return None
        return self._map.tile_for(node)

    def is_empty(self) -> bool:
        return self._map is None or not self._map.root.children

    # ------------------------------------------------------------ painting

    def paint_chart(self, p: QPainter) -> None:
        if self._map is None:
            return
        theme = self.themes.theme
        state = self.state
        sizes = state.sizes
        frames = [qcolor(c) for c in theme.frames]
        fills = [qcolor(c) for c in theme.categories]
        dimmed = [blend(c, frames[0], 0.78) for c in fills]
        surface, text, text2 = qcolor(theme.surface), qcolor(theme.text), qcolor(theme.text2)
        emphasis = state.emphasis is not None
        gap = self.STYLE.gap
        name_fm = QFontMetrics(self._name_font)
        size_fm = QFontMetrics(self._size_font)
        label_fm = QFontMetrics(self._label_font)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        stack = list(reversed(self._map.root.children))
        while stack:
            t = stack.pop()
            x, y, w, h = t.x + gap, t.y + gap, t.w - 2 * gap, t.h - 2 * gap
            if w < 1 or h < 1:
                continue
            frame_index = min(t.depth, len(frames)) - 1
            if t.kind == FOLDER and (t.children or t.header):
                p.fillRect(x, y, w, h, frames[frame_index])
                if t.header:
                    self._paint_header(p, t, x, y, w, name_fm, size_fm, text, text2)
                stack.extend(reversed(t.children))
            elif t.kind == REST:
                # Many items too small to draw: the colour of what fills most of them,
                # with a mesh so it reads as lots of small files rather than one big one.
                background = frames[min(t.depth - 1, len(frames)) - 1] if t.depth > 1 else surface
                category = state.folded_category(t.node, t.count)
                matches = state.folded_emphasised(t.node, t.count)
                self._paint_mesh(p, x, y, w, h, fills[category] if matches else dimmed[category], background)
                label = format_count(t.count, "small item")
                width = label_fm.horizontalAdvance(label) + 8
                if matches and width <= w - 4 and h >= label_fm.height() + 8:
                    p.fillRect(x + 2, y + 2, width, label_fm.height() + 2, background)
                    p.setFont(self._label_font)
                    p.setPen(text2)
                    p.drawText(x + 6, y + 3 + label_fm.ascent(), label)
            else:
                # A file, or a folder too small to open up: show what it is mostly made of.
                category = t.node.category if t.kind == FILE else sizes.dominant_category(t.node)
                matches = not emphasis or state.emphasised(t.node)
                p.fillRect(x, y, w, h, fills[category] if matches else dimmed[category])
                if t.kind == FILE and matches and w >= 46 and h >= 16:
                    self._paint_label(p, t, x, y, w, h, label_fm, ink_for(theme.categories[category]))

    MESH = 8  # 6 px cells with 2 px gaps, like the smallest real tiles

    def _paint_mesh(self, p: QPainter, x: int, y: int, w: int, h: int, fill: QColor, gap: QColor) -> None:
        p.fillRect(x, y, w, h, fill)
        step = self.MESH
        for gx in range(x + step - 2, x + w - 2, step):
            p.fillRect(gx, y, 2, h, gap)
        for gy in range(y + step - 2, y + h - 2, step):
            p.fillRect(x, gy, w, 2, gap)

    def _paint_header(self, p: QPainter, t: Tile, x: int, y: int, w: int,
                      name_fm: QFontMetrics, size_fm: QFontMetrics, text: QColor, text2: QColor) -> None:
        header = self.STYLE.header
        available = w - 10
        size_text = format_size(t.value)
        size_width = size_fm.horizontalAdvance(size_text)
        baseline = y + (header - name_fm.height()) // 2 + name_fm.ascent()
        p.setFont(self._name_font)
        p.setPen(text)
        if available >= size_width + 44:
            name = name_fm.elidedText(t.node.name, Qt.TextElideMode.ElideRight, available - size_width - 10)
            p.drawText(x + 5, baseline, name)
            p.setFont(self._size_font)
            p.setPen(text2)
            p.drawText(x + w - 5 - size_width, baseline, size_text)
        else:
            name = name_fm.elidedText(t.node.name, Qt.TextElideMode.ElideRight, available)
            if len(name) > 1:
                p.drawText(x + 5, baseline, name)

    def _paint_label(self, p: QPainter, t: Tile, x: int, y: int, w: int, h: int,
                     fm: QFontMetrics, ink: QColor) -> None:
        name = fm.elidedText(t.node.name, Qt.TextElideMode.ElideRight, w - 8)
        if len(name) <= 1:
            return
        p.setFont(self._label_font)
        p.setPen(ink)
        top = y + 3
        p.drawText(x + 4, top + fm.ascent(), name)
        if h >= 2 * fm.height() + 6:
            quieter = QColor(ink)
            quieter.setAlphaF(0.8)
            p.setPen(quieter)
            p.drawText(x + 4, top + fm.height() + fm.ascent(), format_size(t.value))

    def paint_outline(self, p: QPainter, t: Tile, *, selected: bool) -> None:
        gap = self.STYLE.gap
        rect = QRect(t.x + gap, t.y + gap, t.w - 2 * gap, t.h - 2 * gap)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        ink = qcolor(self.themes.theme.text)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if selected:
            p.setPen(QPen(ink, 2))
            p.drawRect(QRectF(rect).adjusted(1, 1, -1, -1))
        else:
            if t.kind != FOLDER or not t.children:
                p.fillRect(rect, self.lift_colour())
            p.setPen(QPen(ink, 1))
            p.drawRect(rect.adjusted(0, 0, -1, -1))
        p.restore()
