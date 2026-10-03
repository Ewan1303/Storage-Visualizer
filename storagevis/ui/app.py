"""Starts the app: command line, Qt application, theme and main window."""

from __future__ import annotations

import argparse
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_NAME, __version__
from ..core.demo import build_demo_tree
from ..core.system import IS_WINDOWS
from .main_window import MainWindow
from .painting import app_icon
from .settings import Settings, default_settings_path
from .theme import THEME_MODES, ThemeManager


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="storage_visualizer",
        description="See what is taking up space on your drives, as a treemap or a sunburst.")
    parser.add_argument("path", nargs="?", help='a drive or folder to scan straight away, e.g. C:\\ or "D:\\Games"')
    parser.add_argument("--theme", choices=THEME_MODES, help="colour theme (default: match Windows)")
    parser.add_argument("--demo", action="store_true", help="show made-up example data instead of scanning")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def _install_excepthook() -> None:
    """Show unexpected errors in a dialog instead of losing them (there is no console under pythonw)."""
    showing = False

    def hook(kind, value, tb) -> None:
        nonlocal showing
        text = "".join(traceback.format_exception(kind, value, tb))
        if sys.stderr is not None:
            try:
                sys.stderr.write(text)
            except Exception:
                pass
        if QApplication.instance() is None or showing:
            return
        showing = True
        try:
            box = QMessageBox(QMessageBox.Icon.Critical, APP_NAME,
                              "Something went wrong. The app is still running, but this view may be out of date.")
            box.setDetailedText(text)
            box.exec()
        finally:
            showing = False

    sys.excepthook = hook


def _set_windows_app_id() -> None:
    """Group the window under its own taskbar icon rather than Python's."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StorageVisualizer.App")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if IS_WINDOWS:
        _set_windows_app_id()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())

    settings = Settings(default_settings_path())
    themes = ThemeManager(app, args.theme or str(settings.get("theme", "system")))
    _install_excepthook()

    window = MainWindow(themes, settings)
    window.show()
    if args.demo:
        window.load_tree(build_demo_tree())
    elif args.path:
        window.start_scan(args.path)
    return app.exec()
