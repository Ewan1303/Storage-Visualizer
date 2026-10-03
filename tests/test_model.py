import gc
import os
import random

from storagevis.core.categories import COUNT, DOCUMENTS, IMAGES, MEDIA, OTHER, PROGRAMS
from storagevis.core.demo import build_demo_tree
from storagevis.core.model import DirNode, ScanTree, SizeView, aggregate, is_within, iter_files


def make_tree():
    root = DirNode("C:\\Data")
    photos = root.add_dir("Photos")
    photos.add_file("a.jpg", 300)
    photos.add_file("b.png", 200)
    cloud = photos.add_dir("Cloud")
    cloud.add_file("c.jpg", 1000, online_only=True)
    videos = root.add_dir("Videos")
    videos.add_file("film.mkv", 5000)
    root.add_file("notes.txt", 50)
    root.add_file("setup.exe", 700)
    empty = root.add_dir("Empty")
    aggregate(root)
    return ScanTree(root, "C:\\Data"), {"photos": photos, "cloud": cloud, "videos": videos, "empty": empty}


def test_aggregate_adds_everything_below_each_folder():
    tree, d = make_tree()
    root = tree.root
    assert root.size == 300 + 200 + 5000 + 50 + 700
    assert root.cloud == 1000
    assert (root.files, root.dirs) == (6, 4)
    assert (d["photos"].files, d["photos"].dirs) == (3, 1)
    assert (d["photos"].size, d["photos"].cloud) == (500, 1000)
    expected = [0] * COUNT
    expected[MEDIA], expected[IMAGES], expected[PROGRAMS], expected[DOCUMENTS] = 5000, 500, 700, 50
    assert list(root.by_category[:COUNT]) == expected
    assert root.by_category[COUNT + IMAGES] == 1000


def test_size_view_with_and_without_online_only_files():
    tree, d = make_tree()
    local, both = SizeView(tree), SizeView(tree, include_cloud=True)
    assert local.value(tree.root) == 6250
    assert both.value(tree.root) == 7250
    assert [n.name for n in local.children(tree.root)] == ["Videos", "setup.exe", "Photos", "notes.txt", "Empty"]
    assert both.children(tree.root)[1].name == "Photos"
    assert local.category_values(d["photos"])[IMAGES] == 500
    assert both.category_values(d["photos"])[IMAGES] == 1500
    assert local.dominant_category(tree.root) == MEDIA
    assert local.dominant_category(d["empty"]) == OTHER


def test_largest_files_anywhere_and_below_a_folder():
    tree, d = make_tree()
    local = SizeView(tree)
    assert [f.name for f in local.largest_files(tree.root, 3)] == ["film.mkv", "setup.exe", "a.jpg"]
    assert [f.name for f in local.largest_files(d["photos"], 5)] == ["a.jpg", "b.png"]
    both = SizeView(tree, include_cloud=True)
    assert [f.name for f in both.largest_files(d["photos"], 5)] == ["c.jpg", "a.jpg", "b.png"]


def test_largest_files_match_a_brute_force_search():
    rng = random.Random(3)
    root = DirNode("R")
    folders = [root]
    for i in range(300):
        parent = rng.choice(folders)
        if rng.random() < 0.25:
            folders.append(parent.add_dir(f"d{i}"))
        else:
            parent.add_file(f"f{i}.bin", rng.randint(0, 10_000), online_only=rng.random() < 0.2)
    aggregate(root)
    tree = ScanTree(root, "R")
    for include_cloud in (False, True):
        view = SizeView(tree, include_cloud)
        for folder in folders[:20]:
            files = [f for f in iter_files(folder) if view.value(f) > 0]
            expected = sorted((view.value(f) for f in files), reverse=True)[:15]
            assert [view.value(f) for f in view.largest_files(folder, 15)] == expected


def test_dispose_frees_the_tree_without_the_garbage_collector():
    gc.collect()
    tree = build_demo_tree()
    tree.dispose()
    del tree
    assert gc.collect() < 50  # thousands of nodes would show up here if cycles were left


def test_extension_stats():
    tree, d = make_tree()
    stats = SizeView(tree).extension_stats(tree.root)
    by_ext = {s.extension: s for s in stats}
    assert stats[0].extension == "mkv"
    assert (by_ext["jpg"].bytes, by_ext["jpg"].files) == (300, 2)
    assert {s.extension: s.bytes for s in SizeView(tree, True).extension_stats(tree.root)}["jpg"] == 1300
    assert {s.extension for s in SizeView(tree).extension_stats(d["photos"])} == {"jpg", "png"}


def test_paths_and_lookup():
    tree, d = make_tree()
    assert tree.path_of(tree.root) == "C:\\Data"
    assert tree.path_of(d["cloud"]) == os.path.join("C:\\Data", "Photos", "Cloud")
    assert tree.parts_of(d["cloud"]) == ["Photos", "Cloud"]
    assert tree.find(["Photos", "Cloud"]) is d["cloud"]
    assert tree.find(["Nope"]) is None
    assert tree.find([]) is tree.root
    assert tree.display_name(tree.root) == "Data"
    drive = ScanTree(DirNode("C:\\"), "C:\\")
    assert drive.display_name(drive.root) == "C:"
    assert is_within(d["cloud"], tree.root)
    assert not is_within(tree.root, d["cloud"])


def test_folded_category_values_cover_the_smallest_items():
    root = DirNode("R")
    for i in range(5):
        root.add_file(f"big{i}.mp4", 1000)
    for i in range(10):
        root.add_file(f"small{i}.jpg", 3)
    root.add_file("zero.txt", 0)
    aggregate(root)
    values = SizeView(ScanTree(root, "R")).folded_category_values(root, 10)
    assert values[IMAGES] == 30
    assert values[MEDIA] == 0


def test_demo_tree_is_consistent():
    tree = build_demo_tree()
    files = list(iter_files(tree.root))
    assert len(files) == tree.root.files
    assert sum(f.size for f in files) == tree.root.size
    assert sum(f.cloud for f in files) == tree.root.cloud > 0
    assert sum(tree.root.by_category) == tree.root.size + tree.root.cloud
