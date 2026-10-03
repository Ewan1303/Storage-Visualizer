"""Drives the real window off-screen with the demo data and a small scan."""

import time

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from storagevis.core.demo import build_demo_tree
from storagevis.core.layout import FOLDER
from storagevis.ui.main_window import MainWindow
from storagevis.ui.settings import Settings
from storagevis.ui.theme import ThemeManager

pytestmark = pytest.mark.usefixtures("release_trees")


@pytest.fixture
def window(qapp):
    themes = ThemeManager(qapp, "dark")
    win = MainWindow(themes, Settings(None))
    win.resize(1300, 820)
    win.show()
    win.load_tree(build_demo_tree())
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()
    qapp.processEvents()


def mouse(widget, kind, x, y, button=Qt.MouseButton.NoButton):
    point = QPointF(x, y)
    held = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else button
    event = QMouseEvent(kind, point, QPointF(widget.mapToGlobal(point.toPoint())), button, held,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def wait_for(qapp, condition, seconds=30):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    return condition()


def test_both_views_render(window, qapp):
    for view in ("treemap", "sunburst"):
        window.set_view(view)
        qapp.processEvents()
        assert not window.grab().isNull()
    assert window.results_page.view == "sunburst"


def test_click_selects_double_click_zooms_and_up_returns(window, qapp):
    state = window.state
    treemap = window.results_page.treemap
    window.set_view("treemap")
    treemap.grab()  # lays the treemap out
    tile = next(t for t in treemap._map if t.kind == FOLDER and t.header)
    x, y = tile.x + 12, tile.y + 9  # inside its title strip
    mouse(treemap, QEvent.Type.MouseMove, x, y)
    assert state.hovered is tile.node
    treemap.grab()  # paints the hover card
    mouse(treemap, QEvent.Type.MouseButtonPress, x, y, Qt.MouseButton.LeftButton)
    assert state.selected is tile.node
    mouse(treemap, QEvent.Type.MouseButtonDblClick, x, y, Qt.MouseButton.LeftButton)
    assert state.root is tile.node
    window.actions["up"].trigger()
    assert state.root is state.tree.root
    assert state.selected is tile.node


def test_sunburst_centre_goes_up(window, qapp):
    state = window.state
    users = next(n for n in state.tree.root.children if n.name == "Users")
    state.set_root(users)
    window.set_view("sunburst")
    sunburst = window.results_page.sunburst
    sunburst.grab()
    centre_x, centre_y = sunburst.width() / 2, sunburst.height() / 2
    mouse(sunburst, QEvent.Type.MouseButtonPress, centre_x, centre_y, Qt.MouseButton.LeftButton)
    assert state.root is state.tree.root


def test_tables_follow_the_view(window, qapp):
    state = window.state
    side = window.results_page.side
    contents = side.contents.model()
    assert contents.rowCount() == len(state.tree.root.children)
    users = next(n for n in state.tree.root.children if n.name == "Users")
    state.set_root(users)
    assert contents.rowCount() == 1
    state.go_top()
    side.tabs.setCurrentWidget(side.largest)
    qapp.processEvents()
    assert side.largest.model().node_at(0).name == "TestMachine.vhdx"
    side.tabs.setCurrentWidget(side.types)
    qapp.processEvents()
    types = side.types.model()
    assert types.rowCount() > 10
    assert types.stat_at(0).extension == "pak"


def test_big_folders_count_file_types_in_the_background(window, qapp, monkeypatch):
    from storagevis.ui.tables import TypesModel
    monkeypatch.setattr(TypesModel, "BACKGROUND_FROM", 0)
    state = window.state
    side = window.results_page.side
    side.tabs.setCurrentWidget(side.types)
    users = next(n for n in state.tree.root.children if n.name == "Users")
    state.set_root(users)
    types = side.types.model()
    assert types.loading and types.rowCount() == 1
    assert wait_for(qapp, lambda: not types.loading, seconds=10)
    assert types.rowCount() > 5
    assert sum(r.files for r in types._rows) == users.files


def test_highlights(window, qapp):
    state = window.state
    state.toggle_emphasis(("category", 0))
    assert state.emphasis == ("category", 0)
    window.results_page.treemap.grab()
    state.toggle_emphasis(("category", 0))
    assert state.emphasis is None
    state.set_emphasis(("extension", "mp4"))
    window.set_view("sunburst")
    window.results_page.sunburst.grab()
    window.actions["clear"].trigger()
    assert state.emphasis is None


def test_online_only_files_can_be_counted(window, qapp):
    state = window.state
    before = state.sizes.value(state.root)
    window.actions["online"].trigger()
    assert state.include_cloud
    assert state.sizes.value(state.root) > before
    window.grab()
    window.actions["online"].trigger()
    assert not state.include_cloud


def test_a_folder_of_online_only_files_explains_itself(window, qapp):
    state = window.state
    shared = state.tree.find(["Users", "Alex", "OneDrive", "Shared photos"])
    state.set_root(shared)
    for view, chart in (("treemap", window.results_page.treemap), ("sunburst", window.results_page.sunburst)):
        window.set_view(view)
        chart.grab()
        assert chart.is_empty()
    window.actions["online"].trigger()
    for chart in (window.results_page.treemap, window.results_page.sunburst):
        chart.grab()
        # The key under the chart may reflow and resize it; the chart redraws once that settles.
        assert wait_for(qapp, lambda: not chart._resizing, seconds=2)
        chart.grab()
        assert not chart.is_empty()


def test_theme_switching(window, qapp):
    for mode in ("light", "dark", "system"):
        window.actions[f"theme_{mode}"].trigger()
        assert window.themes.mode == mode
        assert not window.grab().isNull()


def test_scan_and_rescan_from_the_window(qapp, workdir, make_file):
    make_file(workdir / "a" / "one.bin", 1234)
    make_file(workdir / "b.jpg", 10)
    win = MainWindow(ThemeManager(qapp, "dark"), Settings(None))
    win.show()
    win.start_scan(str(workdir))
    assert wait_for(qapp, lambda: win.state.tree is not None)
    assert win.state.tree.root.size == 1244
    assert win.pages.currentWidget() is win.results_page
    win.state.set_root(win.state.tree.find(["a"]))
    win.rescan()
    assert wait_for(qapp, lambda: win.state.tree is not None and win._scanner is None)
    assert win.state.root.name == "a"  # the view comes back to the same folder
    win.close()
