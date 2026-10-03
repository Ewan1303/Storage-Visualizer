"""Shared fixtures. Tests only ever write inside tests/.tmp in this project."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from storagevis.core.system import to_fs_path

SCRATCH = Path(__file__).resolve().parent / ".tmp"


@pytest.fixture
def workdir():
    """A fresh, empty folder inside the project, removed afterwards."""
    SCRATCH.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=SCRATCH))
    yield path
    _remove_links(path)
    shutil.rmtree(to_fs_path(str(path)), ignore_errors=True)


def _remove_links(root: Path) -> None:
    """Remove junctions first, so cleaning up can never reach outside the test folder."""
    for current, dirs, _files in os.walk(root):
        for name in list(dirs):
            full = os.path.join(current, name)
            if os.path.isjunction(full) or os.path.islink(full):
                os.rmdir(full)
                dirs.remove(name)


@pytest.fixture
def make_file():
    """Write a file of ``size`` bytes, creating folders as needed (long paths allowed)."""
    def write(path: Path, size: int) -> Path:
        os.makedirs(to_fs_path(str(path.parent)), exist_ok=True)
        with open(to_fs_path(str(path)), "wb") as f:
            f.write(b"\0" * size)
        return path
    return write


@pytest.fixture
def release_trees():
    """Undo the scanner's gc.freeze() once a test is done with its trees."""
    yield
    from storagevis.core.scanner import release_tree
    release_tree()


@pytest.fixture(scope="session")
def qapp():
    """A Qt application that draws off-screen (no windows appear)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    yield app
