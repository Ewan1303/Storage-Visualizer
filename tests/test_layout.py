import itertools
import random

import pytest

from storagevis.core.layout import FILE, FOLDER, REST, TreemapStyle, build_sunburst, build_treemap, squarify


class FakeNode:
    """Just enough of a file or folder for the layouts."""

    def __init__(self, name, size=0, children=None):
        self.name = name
        self.is_dir = children is not None
        self.children = children or []
        self.parent = None
        self._size = size
        for child in self.children:
            child.parent = self

    @property
    def size(self):
        return sum(c.size for c in self.children) if self.is_dir else self._size


class FakeSource:
    def value(self, node):
        return node.size

    def children(self, node):
        return sorted(node.children, key=lambda n: n.size, reverse=True)


def folder(name, *children):
    return FakeNode(name, children=list(children))


def file(name, size):
    return FakeNode(name, size)


def sample_tree():
    rng = random.Random(7)
    tiny = folder("tiny", *[file(f"t{i}.txt", rng.randint(1, 5)) for i in range(400)])
    clips = folder("clips", file("c.mp4", 9000), file("d.mp4", 6000))
    media = folder("media", file("a.mp4", 40000), file("b.mp4", 25000), clips)
    return folder("root", media, tiny, file("big.iso", 50000), file("one.txt", 1))


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) - max(ax, bx) > 1e-6 and min(ay + ah, by + bh) - max(ay, by) > 1e-6


# ------------------------------------------------------------------- squarify

def test_squarify_areas_are_proportional_and_inside():
    values = [50, 25, 12, 8, 3, 2]
    rects = squarify(values, 0, 0, 300, 200)
    total = sum(values)
    for v, (x, y, w, h) in zip(values, rects):
        assert w * h == pytest.approx(300 * 200 * v / total, rel=1e-6)
        assert x >= -1e-9 and y >= -1e-9 and x + w <= 300 + 1e-9 and y + h <= 200 + 1e-9


def test_squarify_fills_without_overlap():
    rng = random.Random(1)
    values = sorted((rng.uniform(1, 100) for _ in range(40)), reverse=True)
    rects = squarify(values, 10, 20, 640, 480)
    assert sum(w * h for _, _, w, h in rects) == pytest.approx(640 * 480)
    for a, b in itertools.combinations(rects, 2):
        assert not overlaps(a, b)


def test_squarify_keeps_tiles_close_to_square():
    for _, _, w, h in squarify([1] * 16, 0, 0, 400, 400):
        assert max(w / h, h / w) < 2.5


def test_squarify_edge_cases():
    assert squarify([], 0, 0, 100, 100) == []
    assert squarify([5], 0, 0, 0, 100) == []
    assert squarify([5], 3, 4, 100, 50) == [(3, 4, 100, 50)]


# -------------------------------------------------------------------- treemap

def test_treemap_children_stay_inside_their_parent():
    tm = build_treemap(sample_tree(), FakeSource(), 800, 600)

    def check(tile):
        for child in tile.children:
            assert tile.x <= child.x and child.x + child.w <= tile.x + tile.w
            assert tile.y <= child.y and child.y + child.h <= tile.y + tile.h
            check(child)
    check(tm.root)


def test_treemap_siblings_do_not_overlap():
    tm = build_treemap(sample_tree(), FakeSource(), 800, 600)
    for tile in [tm.root, *tm]:
        cells = [(c.x, c.y, c.w, c.h) for c in tile.children]
        for a, b in itertools.combinations(cells, 2):
            assert not overlaps(a, b)


def test_treemap_areas_follow_sizes():
    root = folder("root", file("a", 300), file("b", 100))
    tm = build_treemap(root, FakeSource(), 400, 400, TreemapStyle(padding=0, gap=0))
    a, b = tm.root.children
    assert a.node.name == "a"
    assert a.w * a.h == pytest.approx(3 * b.w * b.h, rel=0.02)


def test_treemap_folds_items_too_small_to_draw():
    root = sample_tree()
    tm = build_treemap(root, FakeSource(), 800, 600)
    rests = [t for t in tm if t.kind == REST]
    tiny = next(c for c in root.children if c.name == "tiny")
    assert any(t.node is tiny and t.count == 400 for t in rests)
    assert tm.tile_for(tiny).kind == FOLDER


def test_treemap_hit_finds_the_deepest_tile():
    tm = build_treemap(sample_tree(), FakeSource(), 800, 600)
    checked = 0
    for tile in tm:
        if tile.kind == FILE and tile.w > 4 and tile.h > 4:
            assert tm.hit(tile.x + tile.w // 2, tile.y + tile.h // 2) is tile
            checked += 1
    assert checked >= 4
    assert tm.hit(-5, -5) is None


def test_treemap_headers_only_where_they_fit():
    style = TreemapStyle()
    tm = build_treemap(sample_tree(), FakeSource(), 800, 600, style)
    headers = [t for t in tm if t.header]
    assert headers
    for tile in headers:
        assert tile.w - 2 * style.gap >= style.min_header_width
        assert tile.h - 2 * style.gap >= style.header


def test_treemap_of_an_empty_folder():
    tm = build_treemap(folder("root"), FakeSource(), 300, 200)
    assert tm.root.children == []
    assert tm.hit(10, 10) is None


# ------------------------------------------------------------------- sunburst

def test_sunburst_children_share_their_parents_angle():
    root = sample_tree()
    sb = build_sunburst(root, FakeSource(), max_rings=4, min_fraction=0.001)
    for segment in sb:
        assert 0 <= segment.start < segment.end <= 1 + 1e-9
        if segment.kind != REST and segment.ring > 1:
            parent = sb.segment_for(segment.node.parent)
            assert parent.start - 1e-9 <= segment.start and segment.end <= parent.end + 1e-9
            assert parent.ring == segment.ring - 1
    assert sum(s.end - s.start for s in sb.rings[0]) == pytest.approx(1.0)


def test_sunburst_segment_at():
    sb = build_sunburst(folder("root", file("a", 3), file("b", 1)), FakeSource())
    assert sb.segment_at(1, 0.1).node.name == "a"
    assert sb.segment_at(1, 0.8).node.name == "b"
    assert sb.segment_at(2, 0.1) is None
    assert sb.depth == 1


def test_sunburst_folds_thin_slices():
    sb = build_sunburst(sample_tree(), FakeSource(), min_fraction=0.01)
    assert any(s.kind == REST for s in sb)


def test_sunburst_stops_at_max_rings():
    deep = file("leaf", 10)
    for i in range(10):
        deep = folder(f"d{i}", deep)
    sb = build_sunburst(folder("root", deep), FakeSource(), max_rings=4)
    assert sb.depth == 4
