"""Render screenshots of the app from the made-up demo data, without showing a window.

    python tools/screenshots.py                      writes docs/*.png (used by the README)
    python tools/screenshots.py some_folder          writes there instead
    python tools/screenshots.py some_folder --pages  also the start and scanning pages

The demo data keeps real file and folder names out of the pictures. The start
page lists this PC's real drives, so it is only drawn when asked for.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from storagevis.core.demo import build_demo_tree  # noqa: E402
from storagevis.core.scanner import ScanProgress  # noqa: E402
from storagevis.ui.main_window import MainWindow  # noqa: E402
from storagevis.ui.painting import app_icon  # noqa: E402
from storagevis.ui.settings import Settings  # noqa: E402
from storagevis.ui.theme import ThemeManager  # noqa: E402


def settle(app: QApplication, rounds: int = 6) -> None:
    for _ in range(rounds):
        app.processEvents()


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
    window.load_tree(build_demo_tree())
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
