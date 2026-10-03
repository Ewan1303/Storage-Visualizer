"""The sunburst: rings of folders around the current one, each slice sized by its bytes.

Folders take the colour of the file type that fills most of them; files keep
their own type colour. The centre is the folder being looked at; click it to go up.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPainterPath, QPen

from ..core.formatting import format_size
from ..core.layout import FILE, FOLDER, REST, Segment, Sunburst, build_sunburst
from .chart_view import ChartView
from .describe import tooltip_lines
from .painting import TipLine, blend, ink_for, qcolor


def _sector(cx: float, cy: float, inner: float, outer: float, start: float, end: float) -> QPainterPath:
    """Ring slice from ``start`` to ``end`` (fractions of a turn, clockwise from 12 o'clock)."""
    a0 = 90.0 - start * 360.0           # Qt measures degrees anticlockwise from 3 o'clock
    sweep = -(end - start) * 360.0
    outer_rect = QRectF(cx - outer, cy - outer, 2 * outer, 2 * outer)
    inner_rect = QRectF(cx - inner, cy - inner, 2 * inner, 2 * inner)
    path = QPainterPath()
    path.arcMoveTo(outer_rect, a0)
    path.arcTo(outer_rect, a0, sweep)
    path.arcTo(inner_rect, a0 + sweep, -sweep)
    path.closeSubpath()
    return path


class SunburstView(ChartView):
    MAX_RINGS = 6

    def __init__(self, state, themes, parent=None) -> None:
        super().__init__(state, themes, parent)
        self._burst: Sunburst | None = None
        self._centre: Segment | None = None
        self._paths: dict[Segment, QPainterPath] = {}
        self._cx = self._cy = 0.0
        self._r0 = self._ring = 1.0

    # -------------------------------------------------------------- layout

    def clear_layout(self) -> None:
        self._burst = None
        self._centre = None
        self._paths = {}

    def build_layout(self) -> None:
        w, h = self.width(), self.height()
        radius = max(24.0, min(w, h) / 2 - 18)
        min_fraction = max(0.0008, 2.5 / (2 * math.pi * radius))  # about 2.5 px at the outer edge
        root = self.state.root
        self._burst = build_sunburst(root, self.state.sizes, self.MAX_RINGS, min_fraction)
        self._centre = Segment(FOLDER, root, 0, 0.0, 1.0, self.state.sizes.value(root))
        self._cx, self._cy = w / 2, h / 2
        self._r0 = radius * 0.28
        self._ring = (radius - self._r0) / max(1, self._burst.depth)
        self._paths = {}

    def _radii(self, ring: int) -> tuple[float, float]:
        inner = self._r0 + (ring - 1) * self._ring
        return inner, inner + self._ring

    def _path(self, segment: Segment) -> QPainterPath:
        path = self._paths.get(segment)
        if path is None:
            if segment is self._centre:
                path = QPainterPath()
                path.addEllipse(QPointF(self._cx, self._cy), self._r0 - 2, self._r0 - 2)
            else:
                inner, outer = self._radii(segment.ring)
                path = _sector(self._cx, self._cy, inner, outer, segment.start, segment.end)
            self._paths[segment] = path
        return path

    def item_at(self, pos: QPoint) -> Segment | None:
        if self._burst is None:
            return None
        dx, dy = pos.x() - self._cx, pos.y() - self._cy
        r = math.hypot(dx, dy)
        if r <= self._r0:
            return self._centre
        ring = int((r - self._r0) // self._ring) + 1
        fraction = (math.atan2(dx, -dy) / (2 * math.pi)) % 1.0
        return self._burst.segment_at(ring, fraction)

    def item_for(self, node) -> Segment | None:
        if self._burst is None or node is self.state.root:
            return None
        return self._burst.segment_for(node)

    def is_empty(self) -> bool:
        return self._burst is None or self._burst.depth == 0

    def describe(self, item: Segment) -> list[TipLine]:
        lines = tooltip_lines(self.state, item.kind, item.node, item.value, item.count)
        if item is self._centre and self.state.can_go_up:
            lines.append(TipLine("Click the centre to go up a level", "detail"))
        return lines

    def click(self, item) -> None:
        if item is not None and item is self._centre:
            self.state.go_up()
        else:
            super().click(item)

    def activate(self, item) -> None:
        if item is not self._centre:
            super().activate(item)

    # ------------------------------------------------------------ painting

    def paint_chart(self, p: QPainter) -> None:
        if self.is_empty():
            return
        theme = self.themes.theme
        state = self.state
        sizes = state.sizes
        fills = [qcolor(c) for c in theme.categories]
        frames = [qcolor(c) for c in theme.frames]
        dimmed = [blend(c, frames[0], 0.78) for c in fills]
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        gap = QPen(qcolor(theme.surface), 1.6)  # the surface showing between slices, not a border
        gap.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(gap)
        labels = []
        for segment in self._burst:
            if segment.kind == REST:
                # Items too thin to draw, in the colour of what fills most of them.
                category = state.folded_category(segment.node, segment.count)
                matches = state.folded_emphasised(segment.node, segment.count)
                p.setBrush(fills[category] if matches else dimmed[category])
            else:
                category = segment.node.category if segment.kind == FILE else sizes.dominant_category(segment.node)
                matches = state.emphasised(segment.node)
                p.setBrush(fills[category] if matches else dimmed[category])
                if matches and segment.ring <= 2:
                    labels.append((segment, theme.categories[category]))
            p.drawPath(self._path(segment))

        self._paint_labels(p, labels)
        self._paint_centre(p)

    def _paint_labels(self, p: QPainter, labels: list[tuple[Segment, str]]) -> None:
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        fm = QFontMetrics(font)
        p.setFont(font)
        if fm.height() > self._ring - 6:
            return
        for segment, fill in labels:
            inner, outer = self._radii(segment.ring)
            mid_r = (inner + outer) / 2
            span = segment.end - segment.start
            room = 2 * mid_r * math.sin(min(span, 0.5) * math.pi) - 10  # chord across the slice
            if room < 30:
                continue
            name = fm.elidedText(segment.node.name, Qt.TextElideMode.ElideRight, int(room))
            if len(name) <= 1:
                continue
            # Text runs along the ring, turned so it is never upside down.
            degrees = (segment.start + segment.end) / 2 * 360.0
            radians = math.radians(degrees)
            rotation = degrees - 180 if 90 < degrees < 270 else degrees
            p.save()
            p.translate(self._cx + mid_r * math.sin(radians), self._cy - mid_r * math.cos(radians))
            p.rotate(rotation)
            p.setPen(ink_for(fill))
            p.drawText(QPointF(-fm.horizontalAdvance(name) / 2, fm.ascent() - fm.height() / 2), name)
            p.restore()

    def _paint_centre(self, p: QPainter) -> None:
        theme = self.themes.theme
        root = self.state.root
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(theme.frames[0]))
        p.drawEllipse(QPointF(self._cx, self._cy), self._r0 - 2, self._r0 - 2)

        name_font = QFont(self.font())
        name_font.setWeight(QFont.Weight.DemiBold)
        size_font = QFont(self.font())
        size_font.setPointSizeF(size_font.pointSizeF() + 4)
        size_font.setWeight(QFont.Weight.DemiBold)
        name_fm, size_fm, small_fm = QFontMetrics(name_font), QFontMetrics(size_font), QFontMetrics(self.font())
        width = int(self._r0 * 1.6)
        lines = [
            (size_font, size_fm, theme.text, format_size(self.state.sizes.value(root))),
            (name_font, name_fm, theme.text2, self.state.tree.display_name(root)),
        ]
        if self.state.can_go_up:
            lines.append((self.font(), small_fm, theme.muted, "↑ Up a level"))
        total = sum(fm.height() for _, fm, _, _ in lines)
        y = self._cy - total / 2
        for font, fm, colour, value in lines:
            text = fm.elidedText(value, Qt.TextElideMode.ElideRight, width)
            p.setFont(font)
            p.setPen(qcolor(colour))
            p.drawText(QPointF(self._cx - fm.horizontalAdvance(text) / 2, y + fm.ascent()), text)
            y += fm.height()

    def paint_outline(self, p: QPainter, segment: Segment, *, selected: bool) -> None:
        path = self._path(segment)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not selected:
            p.fillPath(path, self.lift_colour())
        p.setPen(QPen(qcolor(self.themes.theme.text), 2.5 if selected else 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.restore()
