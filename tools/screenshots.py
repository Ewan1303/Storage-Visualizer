"""Render screenshots of the app from the made-up demo data, without showing a window.

    python tools/screenshots.py                      writes docs/*.png (used by the README)
    python tools/screenshots.py some_folder          writes there instead
    python tools/screenshots.py some_folder --pages  also the start and scanning pages

The demo data keeps real file and folder names out of the pictures. The start
page lists this PC's real drives, so it is only drawn when asked for.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from storagevis.core.categories import Kind  # noqa: E402
from storagevis.core.demo import build_demo_tree  # noqa: E402
from storagevis.core.scanner import ScanProgress  # noqa: E402
from storagevis.ui.file_viewer import FileViewer  # noqa: E402
from storagevis.ui.main_window import MainWindow  # noqa: E402
from storagevis.ui.painting import app_icon  # noqa: E402
from storagevis.ui.settings import Settings  # noqa: E402
from storagevis.ui.theme import ThemeManager  # noqa: E402


def settle(app: QApplication, rounds: int = 6) -> None:
    for _ in range(rounds):
        app.processEvents()


def settle_viewer(app: QApplication, viewer, window) -> None:
    """Wait for the viewer's search, then for every thumbnail in view."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        settle(app)
        viewer.grab()  # paints the cells in view, which asks for their thumbnails
        if viewer.model.rowCount() and window.thumbnails.pending() == 0:
            settle(app)
            return
        time.sleep(0.05)


def hover(widget: QWidget, x: float, y: float) -> None:
    """Send a synthetic mouse move, so the real mouse pointer is never touched."""
    local = QPointF(x, y)
    event = QMouseEvent(QEvent.Type.MouseMove, local, QPointF(widget.mapToGlobal(local.toPoint())),
                        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0]) if args else ROOT / "docs"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    themes = ThemeManager(app, "dark")
    window = MainWindow(themes, Settings(None))
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.resize(1400, 860)
    window.show()
    window.load_tree(build_demo_tree(), demo=True)
    settle(app)

    page = window.results_page
    for mode in ("dark", "light"):
        themes.set_mode(mode)
        for view in ("treemap", "sunburst"):
            window.set_view(view)
            settle(app)
            chart = page.treemap if view == "treemap" else page.sunburst
            if view == "treemap":
                hover(chart, chart.width() * 0.30, chart.height() * 0.55)
            else:
                hover(chart, chart.width() * 0.62, chart.height() * 0.38)
            settle(app)
            window.grab().save(str(out / f"{view}-{mode}.png"))
            print("wrote", out / f"{view}-{mode}.png")

    # The file type viewer, made by hand so it never appears on screen either.
    viewer = FileViewer(window.state, themes, Settings(None), window.thumbnails)
    viewer.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    viewer.resize(1400, 860)
    window._viewer = viewer
    themes.set_mode("dark")
    window.state.go_top()
    window.open_viewer({Kind.PHOTOS, Kind.VIDEOS}, set(), in_folder=False)
    settle_viewer(app, viewer, window)
    viewer.grid.setCurrentIndex(viewer.model.index(1, 0))
    settle_viewer(app, viewer, window)
    viewer.grab().save(str(out / "viewer-dark.png"))
    print("wrote", out / "viewer-dark.png")
    themes.set_mode("light")
    viewer.list_button.setChecked(True)
    viewer.sort_box.setCurrentIndex(2)  # newest first
    viewer.list.setCurrentIndex(viewer.model.index(0, 0))
    settle_viewer(app, viewer, window)
    viewer.grab().save(str(out / "viewer-list-light.png"))
    print("wrote", out / "viewer-list-light.png")
    viewer.close()

    if "--pages" in sys.argv:
        themes.set_mode("dark")
        window.start_page.refresh(has_results=True)
        window.pages.setCurrentWidget(window.start_page)
        settle(app)
        window.grab().save(str(out / "start.png"))
        window.scan_page.begin("C:\\", 814 * 1024 ** 3)
        window.scan_page.show_progress(ScanProgress(
            files=1_234_567, folders=210_345, bytes=512 * 1024 ** 3, cloud_bytes=0, errors=12,
            current="C:\\Windows\\WinSxS\\amd64_microsoft-windows-shell32_31bf3856ad364e35", elapsed=61.5,
            done=False))
        window.pages.setCurrentWidget(window.scan_page)
        settle(app)
        window.grab().save(str(out / "scanning.png"))
        print("wrote", out / "start.png", "and", out / "scanning.png")
    window.close()


if __name__ == "__main__":
    main()
