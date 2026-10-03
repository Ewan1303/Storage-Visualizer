import os
import subprocess

import pytest

import storagevis.core.scanner as scanner_module
from storagevis.core.categories import IMAGES, MEDIA
from storagevis.core.model import SizeView
from storagevis.core.scanner import Scanner

pytestmark = pytest.mark.usefixtures("release_trees")


def scan(path, **options):
    scanner = Scanner(str(path), **options)
    scanner.start()
    assert scanner.wait(60)
    assert scanner.failure is None
    return scanner.result


def test_scan_counts_sizes_files_and_folders(workdir, make_file):
    make_file(workdir / "a.jpg", 1000)
    make_file(workdir / "sub" / "b.mp4", 5000)
    make_file(workdir / "sub" / "deeper" / "c.txt", 10)
    (workdir / "empty").mkdir()
    tree = scan(workdir)
    root = tree.root
    assert (root.size, root.cloud) == (6010, 0)
    assert (root.files, root.dirs) == (3, 3)
    assert root.by_category[MEDIA] == 5000
    assert root.by_category[IMAGES] == 1000
    assert tree.extensions["mp4"] == [5000, 0, 1]
    assert [f.name for f in SizeView(tree).largest_files(root, 5)] == ["b.mp4", "a.jpg", "c.txt"]
    assert (root.biggest, tree.find(["sub"]).biggest) == (5000, 5000)
    assert tree.complete and tree.error_count == 0
    assert tree.root_path == str(workdir)
    assert tree.find(["sub"]).size == 5010


def test_one_worker_and_many_agree(workdir, make_file):
    for i in range(30):
        make_file(workdir / f"d{i % 5}" / f"e{i % 3}" / f"f{i}.bin", 100 + i)
    one, many = scan(workdir, workers=1), scan(workdir, workers=8)
    assert (one.root.size, one.root.files, one.root.dirs) == (many.root.size, many.root.files, many.root.dirs)
    assert one.root.size == sum(100 + i for i in range(30))


@pytest.mark.skipif(os.name != "nt", reason="junctions are a Windows feature")
def test_junctions_are_not_followed(workdir, make_file):
    target = workdir / "real"
    make_file(target / "data.bin", 4096)
    link = workdir / "link"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    assert os.path.isjunction(link)
    tree = scan(workdir)
    assert tree.root.size == 4096  # once, not twice
    assert tree.skipped_links == 1


def test_folders_nested_past_260_characters(workdir, make_file):
    deep = workdir
    while len(str(deep)) < 300:
        deep = deep / ("x" * 40)
    make_file(deep / "deep.bin", 777)
    tree = scan(workdir)
    assert (tree.root.size, tree.root.files) == (777, 1)
    assert tree.error_count == 0


def test_cancelling_gives_an_incomplete_tree(workdir, make_file):
    make_file(workdir / "a.bin", 10)
    scanner = Scanner(str(workdir))
    scanner.cancel()
    scanner.start()
    assert scanner.wait(10)
    assert scanner.result is not None
    assert not scanner.result.complete
    assert scanner.result.root.files == 0


def test_progress_matches_the_result(workdir, make_file):
    for i in range(10):
        make_file(workdir / f"f{i}.bin", 100)
    scanner = Scanner(str(workdir))
    scanner.start()
    scanner.wait(30)
    progress = scanner.progress()
    assert progress.done
    assert (progress.files, progress.bytes, progress.folders) == (10, 1000, 1)


def test_a_file_is_not_a_scan_target(workdir, make_file):
    path = make_file(workdir / "a.bin", 1)
    with pytest.raises(NotADirectoryError):
        Scanner(str(path))


def test_unreadable_folders_are_reported_and_skipped(workdir, make_file, monkeypatch):
    make_file(workdir / "ok" / "a.bin", 5)
    make_file(workdir / "locked" / "b.bin", 7)
    real_scandir = os.scandir

    def scandir(path):
        if str(path).endswith("locked"):
            raise PermissionError(13, "Access is denied")
        return real_scandir(path)

    monkeypatch.setattr(scanner_module.os, "scandir", scandir)
    tree = scan(workdir)
    assert tree.root.size == 5
    assert tree.error_count == 1
    assert tree.errors[0][0].endswith("locked")
    assert tree.errors[0][1] == "Access denied"
    assert tree.find(["locked"]).error == "Access denied"
