import pytest

from storagevis.core.categories import Kind, kind_of_extension
from storagevis.core.demo import build_demo_tree
from storagevis.core.finder import FileQuery, find_files
from storagevis.core.model import DirNode, ScanTree, aggregate, iter_files

PHOTOS_AND_VIDEOS = frozenset({Kind.PHOTOS, Kind.VIDEOS})


@pytest.fixture
def tree():
    root = DirNode("C:\\")
    me = root.add_dir("Users").add_dir("me")
    pictures = me.add_dir("Pictures")
    pictures.add_file("beach.jpg", 3_000_000, mtime=100.0)
    pictures.add_file("Party.PNG", 500_000)
    pictures.add_file("empty.jpg", 0)
    videos = me.add_dir("Videos")
    videos.add_file("holiday.mp4", 900_000_000)
    videos.add_file("cloud.mov", 400_000_000, online_only=True)
    me.add_dir("Music").add_file("song.mp3", 5_000_000)
    appdata = me.add_dir("AppData")
    appdata.add_file("icon.png", 2_000)
    appdata.add_file("cache.mp4", 10_000)
    root.add_dir("Windows").add_file("wallpaper.jpg", 1_000_000)
    me.add_dir("Documents").add_file("notes.txt", 100)
    aggregate(root)
    return ScanTree(root, "C:\\")


def names(matches):
    return sorted(f.name for f in matches.files)


def test_photos_and_videos_without_system_folders_or_empty_files(tree):
    matches = find_files(tree.root, FileQuery(kinds=PHOTOS_AND_VIDEOS))
    assert names(matches) == ["Party.PNG", "beach.jpg", "cloud.mov", "holiday.mp4"]
    assert matches.by_kind == {Kind.PHOTOS: 2, Kind.VIDEOS: 2}
    assert matches.bytes == 3_000_000 + 500_000 + 900_000_000 + 400_000_000
    assert matches.cloud_bytes == 400_000_000  # online-only files are still listed


def test_system_folders_can_be_included(tree):
    matches = find_files(tree.root, FileQuery(kinds=frozenset({Kind.PHOTOS}), skip_system=False))
    assert names(matches) == ["Party.PNG", "beach.jpg", "icon.png", "wallpaper.jpg"]


def test_the_folder_searched_is_never_skipped_itself(tree):
    appdata = tree.find(["Users", "me", "AppData"])
    assert names(find_files(appdata, FileQuery(kinds=frozenset({Kind.PHOTOS})))) == ["icon.png"]


def test_name_extension_and_size_filters(tree):
    assert names(find_files(tree.root, FileQuery(kinds=PHOTOS_AND_VIDEOS, text="pAR"))) == ["Party.PNG"]
    only_mp4 = find_files(tree.root, FileQuery(kinds=PHOTOS_AND_VIDEOS, extensions=frozenset({"mp4"})))
    assert names(only_mp4) == ["holiday.mp4"]
    # The extension picker still offers every extension of the chosen kinds.
    assert {ext for ext, _files, _bytes in only_mp4.extensions} == {"jpg", "png", "mp4", "mov"}
    big = find_files(tree.root, FileQuery(kinds=PHOTOS_AND_VIDEOS, min_size=10_000_000))
    assert names(big) == ["cloud.mov", "holiday.mp4"]


def test_no_kinds_means_no_files(tree):
    assert find_files(tree.root, FileQuery(kinds=frozenset())).files == []


def test_skipping_folders_by_their_totals_misses_nothing():
    tree = build_demo_tree()
    for kind in Kind:
        matches = find_files(tree.root, FileQuery(kinds=frozenset({kind}), skip_system=False))
        expected = {f for f in iter_files(tree.root) if f.size + f.cloud > 0 and kind_of_extension(f.ext) == kind}
        assert set(matches.files) == expected, kind
    everything = find_files(tree.root, FileQuery(skip_system=False))
    assert len(everything.files) == sum(1 for f in iter_files(tree.root) if f.size + f.cloud > 0)


def test_a_search_can_be_abandoned():
    assert find_files(build_demo_tree().root, FileQuery(), stop=lambda: True) is None
