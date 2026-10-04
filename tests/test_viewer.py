"""Drives the file type viewer off-screen, on the demo drive."""

import time

import pytest

from storagevis.core.categories import Kind, kind_of_extension
from storagevis.core.demo import build_demo_tree
from storagevis.core.finder import FileQuery, find_files
from storagevis.core.model import is_within
from storagevis.ui.main_window import MainWindow
from storagevis.ui.settings import Settings
from storagevis.ui.theme import ThemeManager
from storagevis.ui.viewer_results import NAME

pytestmark = pytest.mark.usefixtures("release_trees")

PHOTOS_AND_VIDEOS = {Kind.PHOTOS, Kind.VIDEOS}


def wait_for(qapp, condition, seconds=15):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    return condition()


@pytest.fixture
def window(qapp):
    win = MainWindow(ThemeManager(qapp, "dark"), Settings(None))
    win.resize(1300, 820)
    win.show()
    win.load_tree(build_demo_tree(), demo=True)
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()
    qapp.processEvents()


@pytest.fixture
def viewer(window, qapp):
    window.open_viewer(PHOTOS_AND_VIDEOS, set(), in_folder=False)
    view = window._viewer
    assert wait_for(qapp, lambda: view.model.rowCount() > 0)
    return view


def shown_names(viewer):
    return [viewer.model.file_at(row).name for row in range(viewer.model.rowCount())]


def test_lists_every_photo_and_video_outside_system_folders(window, viewer):
    expected = find_files(window.state.tree.root, FileQuery(kinds=frozenset(PHOTOS_AND_VIDEOS)))
    assert viewer.model.rowCount() == len(expected.files) > 1000
    assert {kind_of_extension(f.ext) for f in viewer.model.files()} == PHOTOS_AND_VIDEOS
    assert "photos" in viewer.summary.fullText() and "videos" in viewer.summary.fullText()
    sizes = [f.size + f.cloud for f in viewer.model.files()]
    assert sizes == sorted(sizes, reverse=True)  # largest first by default


def test_thumbnails_are_drawn(window, viewer, qapp):
    viewer.grid.grab()  # paints the visible cells, which asks for their pictures
    assert wait_for(qapp, lambda: window.thumbnails.pending() == 0)
    first = viewer.model.file_at(0)
    path = window.state.tree.path_of(first)
    images = [window.thumbnails.image(path, size) for size in (128, 160, 192, 256)]
    assert any(image is not None and not image.isNull() for image in images)
    assert not viewer.grab().isNull()


def test_search_list_view_and_sorting(viewer, qapp):
    viewer.search.setText("VID_2025")
    assert wait_for(qapp, lambda: viewer.model.rowCount() == 14)
    assert all("VID_2025" in name for name in shown_names(viewer))
    viewer.list_button.setChecked(True)
    assert viewer.stack.currentWidget() is viewer.list
    viewer.sort_box.setCurrentIndex(2)  # newest first
    dates = [f.mtime for f in viewer.model.files()]
    assert dates == sorted(dates, reverse=True)
    viewer.list.horizontalHeader().setSortIndicator(NAME, viewer.model.sort_order.AscendingOrder)
    assert viewer.sort_box.currentText() == "Name"
    assert shown_names(viewer) == sorted(shown_names(viewer), key=str.casefold)


def test_extension_filter(viewer, qapp):
    menu_items = {a.text().split()[0]: a for a in viewer.extension_menu.actions() if a.isCheckable()}
    assert ".mp4" in menu_items and ".jpg" in menu_items
    menu_items[".mp4"].setChecked(True)
    assert wait_for(qapp, lambda: viewer.model.rowCount() and all(n.endswith(".mp4") for n in shown_names(viewer)))
    assert ".mp4" in viewer.extension_button.text()


def test_ctrl_c_copies_the_selected_paths(window, viewer, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    viewer.grid.setCurrentIndex(viewer.model.index(0, NAME))
    viewer.grid.setFocus()
    QTest.keyClick(viewer.grid, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == window.state.tree.path_of(viewer.model.file_at(0))


def test_select_preview_and_show_in_chart(window, viewer, qapp):
    viewer.grid.setCurrentIndex(viewer.model.index(0, NAME))
    first = viewer.model.file_at(0)
    assert viewer.preview.name.fullText() == first.name
    viewer.preview.buttons["chart"].click()
    assert window.state.root is first.parent
    assert window.state.selected is first


def test_this_folder_stays_put_when_the_main_window_moves(window, viewer, qapp):
    state = window.state
    pictures = state.tree.find(["Users", "Alex", "Pictures"])
    state.set_root(pictures)
    viewer.show_types(in_folder=True)
    assert wait_for(qapp, lambda: all(is_within(f, pictures) for f in viewer.model.files()))
    count = viewer.model.rowCount()
    assert viewer.scope_box.currentText() == "Only in Pictures"
    state.set_root(state.tree.find(["Users", "Alex", "Pictures", "RAW"]))  # e.g. "Show in chart"
    qapp.processEvents()
    assert viewer.model.rowCount() == count
    assert viewer.scope_box.currentText() == "Only in Pictures"


def test_nothing_chosen_and_nothing_found(viewer, qapp):
    viewer.chips.set_kinds(set())
    assert viewer.stack.currentWidget() is viewer.message
    assert "Choose" in viewer.message.text()
    viewer.chips.set_kinds({Kind.PHOTOS})
    viewer.search.setText("no file is called this")
    assert wait_for(qapp, lambda: "No photos found" in viewer.message.text())
    assert viewer.stack.currentWidget() is viewer.message
    assert "a shorter search" in viewer.message.text()


def test_a_new_scan_empties_the_viewer(window, viewer, qapp):
    window.state.set_tree(None)
    assert viewer.model.rowCount() == 0
    assert "Scan a drive" in viewer.message.text()


def test_ways_in_from_the_main_window(window, qapp):
    window.results_page.side.typeActivated.emit("mp4")
    view = window._viewer
    assert wait_for(qapp, lambda: view.model.rowCount() > 0)
    assert all(f.ext == "mp4" for f in view.model.files())
    window.results_page.legend.browseRequested.emit(0)  # video & audio
    assert view.chips.kinds() == {Kind.VIDEOS, Kind.MUSIC}
    assert wait_for(qapp, lambda: any(f.ext == "mp3" for f in view.model.files()))
