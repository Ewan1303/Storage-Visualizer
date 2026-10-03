"""Geometry for the two views: a squarified treemap and a sunburst.

Nothing here knows about Qt or the disk. The builders take a *size source*, any
object with ``value(node)`` and ``children(node)`` (children largest first, as
``model.SizeView`` provides), and return plain tiles and segments that the views
turn into pixels. Nodes only need an ``is_dir`` attribute.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from operator import attrgetter, itemgetter
from typing import Any, Protocol

FILE, FOLDER, REST = 0, 1, 2
"""Item kinds. REST stands for a folder's many items that are too small to draw one by one."""


class SizeSource(Protocol):
    def value(self, node: Any) -> int: ...
    def children(self, node: Any) -> Sequence[Any]: ...


Rect = tuple[float, float, float, float]


def squarify(values: Sequence[float], x: float, y: float, w: float, h: float) -> list[Rect]:
    """Split a rectangle into one rectangle per value, with areas proportional to the values.

    This is the squarified layout of Bruls, Huizing and van Wijk: the values
    (positive, largest first) are laid out in rows along the shorter side, and
    a row stops growing as soon as one more value would make its worst aspect
    ratio worse.
    """
    n = len(values)
    if n == 0 or w <= 0 or h <= 0:
        return []
    total = float(sum(values))
    if total <= 0:
        return []
    scale = w * h / total
    rects: list[Rect] = []
    i = 0
    while i < n:
        if w <= 1e-9 or h <= 1e-9:  # rounding left nothing over
            rects.extend((x, y, 0.0, 0.0) for _ in range(n - i))
            break
        side2 = min(w, h) ** 2
        first = values[i] * scale
        row_sum = row_min = row_max = first
        worst = max(side2 * row_max / (row_sum * row_sum), (row_sum * row_sum) / (side2 * row_min))
        j = i + 1
        while j < n:
            area = values[j] * scale
            grown = row_sum + area
            grown_min = min(row_min, area)
            grown_max = max(row_max, area)
            ratio = max(side2 * grown_max / (grown * grown), (grown * grown) / (side2 * grown_min))
            if ratio > worst:
                break
            row_sum, row_min, row_max, worst = grown, grown_min, grown_max, ratio
            j += 1
        last_row = j >= n
        if w >= h:
            # The row becomes a column down the left side.
            col_w = w if last_row else row_sum / h
            yy = y
            for k in range(i, j):
                hh = (y + h - yy) if k == j - 1 else values[k] * scale / col_w
                rects.append((x, yy, col_w, hh))
                yy += hh
            x += col_w
            w -= col_w
        else:
            # The row runs along the top.
            row_h = h if last_row else row_sum / w
            xx = x
            for k in range(i, j):
                ww = (x + w - xx) if k == j - 1 else values[k] * scale / row_h
                rects.append((xx, y, ww, row_h))
                xx += ww
            y += row_h
            h -= row_h
        i = j
    return rects


# ---------------------------------------------------------------------- treemap

@dataclass(eq=False, slots=True)
class Tile:
    kind: int
    node: Any          # the file or folder; for REST, the folder the small items are in
    x: int             # the tile's cell; it is drawn ``gap`` pixels inside this
    y: int
    w: int
    h: int
    depth: int         # 1 for children of the view's root
    value: int
    count: int = 0     # REST only: how many items were folded together
    header: bool = False
    children: list[Tile] = field(default_factory=list)

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


@dataclass(frozen=True)
class TreemapStyle:
    gap: int = 1                # each tile is drawn this far inside its cell: 2 px between neighbours
    padding: int = 3            # space between a folder's edge and its contents
    header: int = 18            # height of a folder's title strip
    min_header_width: int = 56  # narrower folders get no title strip
    min_area: float = 40.0      # items smaller than this (square pixels) are folded into one REST tile
    max_tiles: int = 60_000


class Treemap:
    def __init__(self, root: Tile, index: dict[Any, Tile]) -> None:
        self.root = root
        self._index = index

    def tile_for(self, node: Any) -> Tile | None:
        return self._index.get(node)

    def hit(self, px: float, py: float) -> Tile | None:
        """The deepest tile under a point (None for the view's own background)."""
        tile = self.root
        if not tile.contains(px, py):
            return None
        while True:
            for child in tile.children:
                if child.contains(px, py):
                    tile = child
                    break
            else:
                return None if tile is self.root else tile

    def __iter__(self) -> Iterator[Tile]:
        stack = list(reversed(self.root.children))
        while stack:
            tile = stack.pop()
            yield tile
            stack.extend(reversed(tile.children))


def build_treemap(root: Any, source: SizeSource, width: int, height: int,
                  style: TreemapStyle | None = None) -> Treemap:
    style = style or TreemapStyle()
    top = Tile(FOLDER, root, 0, 0, int(width), int(height), 0, source.value(root))
    index = {root: top}
    builder = _TreemapBuilder(source, style, index)
    p = style.padding
    builder.fill(top, root, p, p, width - 2 * p, height - 2 * p)
    return Treemap(top, index)


class _TreemapBuilder:
    def __init__(self, source: SizeSource, style: TreemapStyle, index: dict[Any, Tile]) -> None:
        self.source = source
        self.style = style
        self.index = index
        self.budget = style.max_tiles

    def fill(self, tile: Tile, node: Any, x: float, y: float, w: float, h: float) -> None:
        """Lay out ``node``'s children inside the given rectangle."""
        if w < 1 or h < 1:
            return
        value = self.source.value
        total = value(node)
        if total <= 0:
            return
        threshold = self.style.min_area * total / (w * h)  # smallest value worth its own tile
        items: list[tuple[int, Any]] = []
        shown = folded = 0
        for child in self.source.children(node):
            v = value(child)
            if v <= 0:
                break
            if v < threshold:
                folded += 1
                continue
            items.append((v, child))
            shown += v
        if folded:
            items.append((total - shown, None))
            items.sort(key=itemgetter(0), reverse=True)

        rects = squarify([v for v, _ in items], x, y, w, h)
        depth = tile.depth + 1
        for (v, child), (rx, ry, rw, rh) in zip(items, rects):
            if self.budget <= 0:
                break
            # Snap edges to whole pixels so every gap comes out the same width.
            x0, y0 = round(rx), round(ry)
            cw, ch = round(rx + rw) - x0, round(ry + rh) - y0
            if cw <= 0 or ch <= 0:
                continue
            self.budget -= 1
            if child is None:
                t = Tile(REST, node, x0, y0, cw, ch, depth, v, count=folded)
            elif child.is_dir:
                t = Tile(FOLDER, child, x0, y0, cw, ch, depth, v)
                self.index[child] = t
                self.open(t, child)
            else:
                t = Tile(FILE, child, x0, y0, cw, ch, depth, v)
                self.index[child] = t
            tile.children.append(t)

    def open(self, tile: Tile, node: Any) -> None:
        """Give a folder tile a title strip if it fits, then lay out what is inside it."""
        s = self.style
        g, p = s.gap, s.padding
        x, y, w, h = tile.x + g, tile.y + g, tile.w - 2 * g, tile.h - 2 * g
        if w >= s.min_header_width and h >= s.header + p + 8:
            tile.header = True
            self.fill(tile, node, x + p, y + s.header, w - 2 * p, h - s.header - p)
        elif w >= 2 * p + 6 and h >= 2 * p + 6:
            self.fill(tile, node, x + p, y + p, w - 2 * p, h - 2 * p)


# --------------------------------------------------------------------- sunburst

@dataclass(eq=False, slots=True)
class Segment:
    kind: int
    node: Any          # for REST, the folder the small items are in
    ring: int          # 1 is the ring around the centre circle
    start: float       # fractions of a full turn, clockwise from 12 o'clock
    end: float
    value: int
    count: int = 0


class Sunburst:
    def __init__(self, root: Any, rings: list[list[Segment]], index: dict[Any, Segment]) -> None:
        self.root = root
        self.rings = rings  # rings[0] touches the centre
        self._index = index
        self._starts = [[s.start for s in ring] for ring in rings]

    @property
    def depth(self) -> int:
        return len(self.rings)

    def segment_for(self, node: Any) -> Segment | None:
        return self._index.get(node)

    def segment_at(self, ring: int, fraction: float) -> Segment | None:
        if ring < 1 or ring > len(self.rings):
            return None
        i = bisect_right(self._starts[ring - 1], fraction) - 1
        if i < 0:
            return None
        segment = self.rings[ring - 1][i]
        return segment if fraction < segment.end else None

    def __iter__(self) -> Iterator[Segment]:
        for ring in self.rings:
            yield from ring


def build_sunburst(root: Any, source: SizeSource, max_rings: int = 6,
                   min_fraction: float = 0.002) -> Sunburst:
    """Rings of segments, each child taking its share of its parent's angle.

    Items narrower than ``min_fraction`` of a full turn are folded into one
    REST segment at the end of their parent's span.
    """
    value = source.value
    rings: list[list[Segment]] = [[] for _ in range(max_rings)]
    index: dict[Any, Segment] = {}
    if value(root) > 0:
        stack = [(root, 0.0, 1.0, 1)]
        while stack:
            node, start, end, ring = stack.pop()
            total = value(node)
            span = end - start
            position = start
            folded = folded_value = 0
            for child in source.children(node):
                v = value(child)
                if v <= 0:
                    break
                share = span * v / total
                if share < min_fraction:
                    folded += 1
                    folded_value += v
                    continue
                kind = FOLDER if child.is_dir else FILE
                segment = Segment(kind, child, ring, position, position + share, v)
                rings[ring - 1].append(segment)
                index[child] = segment
                if kind == FOLDER and ring < max_rings:
                    stack.append((child, position, position + share, ring + 1))
                position += share
            if folded and end > position:
                rings[ring - 1].append(Segment(REST, node, ring, position, end, folded_value, folded))
    for ring in rings:
        ring.sort(key=attrgetter("start"))
    while rings and not rings[-1]:
        rings.pop()
    return Sunburst(root, rings, index)
