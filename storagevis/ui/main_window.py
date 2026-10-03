"""The main window: runs scans and wires the pages, menus and shell actions together."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QLabel, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout)

from .. import APP_NAME, __version__
from ..core.categories import CATEGORIES
from ..core.formatting import format_count, format_duration
from ..core.model import Node, ScanTree
from ..core.scanner import Scanner, release_tree
from ..core.system import is_drive_root, open_path, reveal_in_file_manager
from .details import REVEAL_LABEL
from .pages import ScanPage, StartPage
from .painting import folder_icon, glyph_icon
from .results_page import VIEWS, ResultsPage
from .settings import Settings
from .state import ViewState
from .theme import ThemeManager


class MainWindow(QMainWindow):
    def __init__(self, themes: ThemeManager, settings: Settings) -> None:
        super().__init__()
        self.themes = themes
        self.settings = settings
        self.state = ViewState()
        self.state.include_cloud = bool(settings.get("include_online_only", False))
        self._scanner: Scanner | None = None
        self._restore_parts: list[str] | None = None
        self._discard_scan = False

        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.setMinimumSize(960, 620)

        self.actions = self._make_actions()
        self.start_page = StartPage(themes)
        self.scan_page = ScanPage(themes)
        self.results_page = ResultsPage(self.state, themes, self.actions)
        self.pages = QStackedWidget()
        self.pages.setObjectName("Pages")
        for page in (self.start_page, self.scan_page, self.results_page):
            self.pages.addWidget(page)
        self.setCentralWidget(self.pages)
        self._make_menus()
        self._make_status_bar()

        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._poll_scan)

        self.start_page.scanRequested.connect(lambda path: self.start_scan(path))
        self.start_page.browseRequested.connect(self.browse)
        self.start_page.resumeRequested.connect(self.show_results)
        self.scan_page.stopRequested.connect(lambda: self.stop_scan(keep_results=True))
        self.scan_page.cancelRequested.connect(lambda: self.stop_scan(keep_results=False))
        for chart in (self.results_page.treemap, self.results_page.sunburst):
            chart.contextMenuRequested.connect(self.show_node_menu)
        self.results_page.side.contextMenuRequested.connect(self.show_node_menu)
        self.results_page.side.actionRequested.connect(self.node_action)
        for signal in (self.state.treeChanged, self.state.rootChanged):
            signal.connect(self._update_actions)
        self.pages.currentChanged.connect(lambda _index: self._update_actions())
        themes.changed.connect(self._refresh_icons)

        self._refresh_icons()
        self._restore_settings()
        self.show_start()

    # --------------------------------------------------------------- actions

    def _make_actions(self) -> dict[str, QAction]:
        actions: dict[str, QAction] = {}

        def add(key: str, text: str, slot: Callable, shortcut: str | list[str] | None = None,
                checkable: bool = False, tip: str | None = None) -> QAction:
            action = QAction(text, self)
            if isinstance(shortcut, list):
                action.setShortcuts([QKeySequence(s) for s in shortcut])
            elif shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.setCheckable(checkable)
            if tip:
                action.setToolTip(tip)
            action.triggered.connect(slot)
            self.addAction(action)  # shortcuts work even while the menus are closed
            actions[key] = action
            return action

        add("new_scan", "New scan", self.show_start, "Ctrl+N", tip="Pick another drive or folder (Ctrl+N)")
        add("open_folder", "Scan a folder…", self.browse, "Ctrl+O")
        add("rescan", "Rescan", self.rescan, "F5", tip="Scan the same folder again (F5)")
        add("exit", "Exit", self.close, "Ctrl+Q")
        add("treemap", "Treemap", lambda: self.set_view("treemap"), "Ctrl+1", checkable=True,
            tip="Rectangles sized by bytes (Ctrl+1)")
        add("sunburst", "Sunburst", lambda: self.set_view("sunburst"), "Ctrl+2", checkable=True,
            tip="Rings of folders around the current one (Ctrl+2)")
        views = QActionGroup(self)
        views.setExclusive(True)
        views.addAction(actions["treemap"])
        views.addAction(actions["sunburst"])
        add("up", "Up one level", self.state.go_up, ["Backspace", "Alt+Up"], tip="Up one level (Backspace)")
        add("top", "Back to the scanned folder", self.state.go_top, "Alt+Home")
        add("clear", "Clear highlight and selection", self._clear_highlight, "Esc")
        add("online", "Count online-only files", self._set_include_cloud, checkable=True,
            tip="Include OneDrive files that are stored only in the cloud")
        themes = QActionGroup(self)
        themes.setExclusive(True)
        for mode, text in (("system", "Match Windows"), ("light", "Light"), ("dark", "Dark")):
            action = add(f"theme_{mode}", text, lambda _checked=False, m=mode: self._set_theme(m), checkable=True)
            themes.addAction(action)
        add("issues", "Items that couldn't be read…", self.show_issues)
        add("shortcuts", "Keyboard and mouse", self.show_shortcuts, "F1")
        add("about", f"About {APP_NAME}", self.show_about)
        return actions

    def _make_menus(self) -> None:
        a = self.actions
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        for key in ("new_scan", "open_folder", "rescan"):
            file_menu.addAction(a[key])
        file_menu.addSeparator()
        file_menu.addAction(a["exit"])
        view = bar.addMenu("&View")
        view.addAction(a["treemap"])
        view.addAction(a["sunburst"])
        view.addSeparator()
        view.addAction(a["up"])
        view.addAction(a["top"])
        view.addAction(a["clear"])
        view.addSeparator()
        view.addAction(a["online"])
        view.addSeparator()
        theme_menu = view.addMenu("Theme")
        for mode in ("system", "light", "dark"):
            theme_menu.addAction(a[f"theme_{mode}"])
        help_menu = bar.addMenu("&Help")
        help_menu.addAction(a["shortcuts"])
        help_menu.addAction(a["issues"])
        help_menu.addSeparator()
        help_menu.addAction(a["about"])

    def _make_status_bar(self) -> None:
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        self.status_label = QLabel("")
        status.addWidget(self.status_label, 1)
        self.issues_button = QPushButton("")
        self.issues_button.setProperty("flat", True)
        self.issues_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.issues_button.clicked.connect(self.show_issues)
        self.issues_button.hide()
        status.addPermanentWidget(self.issues_button)

    def _refresh_icons(self, _theme=None) -> None:
        colour = self.themes.theme.text
        for key, glyph in (("up", "up"), ("rescan", "refresh"), ("new_scan", "add")):
            self.actions[key].setIcon(glyph_icon(glyph, colour))
        self.actions["open_folder"].setIcon(folder_icon(colour))

    def _update_actions(self) -> None:
        a = self.actions
        scanning = self._scanner is not None
        tree = self.state.tree
        on_results = self.pages.currentWidget() is self.results_page
        a["new_scan"].setEnabled(not scanning)
        a["open_folder"].setEnabled(not scanning)
        a["rescan"].setEnabled(tree is not None and not scanning)
        a["up"].setEnabled(on_results and self.state.can_go_up)
        a["top"].setEnabled(on_results and self.state.can_go_up)
        a["issues"].setEnabled(tree is not None and tree.error_count > 0)

    # ----------------------------------------------------------------- pages

    def show_start(self) -> None:
        if self._scanner is not None:
            return
        self.start_page.refresh(has_results=self.state.tree is not None)
        self.pages.setCurrentWidget(self.start_page)
        self.setWindowTitle(APP_NAME)
        self.status_label.setText("")
        self.issues_button.hide()

    def show_results(self) -> None:
        tree = self.state.tree
        if tree is None:
            return
        self.pages.setCurrentWidget(self.results_page)
        self.setWindowTitle(f"{tree.root_path} — {APP_NAME}")
        self._show_scan_summary(tree)

    def set_view(self, name: str) -> None:
        name = name if name in VIEWS else "treemap"
        self.results_page.set_view(name)
        self.actions[name].setChecked(True)

    def load_tree(self, tree: ScanTree, root: Node | None = None) -> None:
        """Show a finished scan (or the demo data)."""
        self.state.set_tree(tree, root)
        self.show_results()

    def _show_scan_summary(self, tree: ScanTree) -> None:
        parts = [f"Scanned {format_count(tree.root.files, 'file')} and "
                 f"{format_count(tree.root.dirs, 'folder')} in {format_duration(tree.elapsed)}"]
        if not tree.complete:
            parts.append("stopped early, so sizes are incomplete")
        if tree.skipped_links:
            parts.append(f"{format_count(tree.skipped_links, 'link')} skipped so nothing is counted twice")
        self.status_label.setText("  ·  ".join(parts))
        if tree.error_count:
            self.issues_button.setText(f"⚠  {format_count(tree.error_count, 'item')} couldn't be read")
            self.issues_button.show()
        else:
            self.issues_button.hide()

    # ----------------------------------------------------------------- scans

    def start_scan(self, path: str, restore_parts: list[str] | None = None) -> None:
        if self._scanner is not None:
            return
        path = os.path.abspath(os.path.expanduser(path.strip().strip('"')))
        if not os.path.isdir(path):
            QMessageBox.warning(self, APP_NAME, f"Can't find this folder:\n{path}")
            return
        try:
            scanner = Scanner(path)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Can't scan {path}:\n{exc}")
            return
        self._drop_tree()
        self._scanner = scanner
        self._restore_parts = restore_parts
        self._discard_scan = False
        expected = scanner.disk[1] if scanner.disk and is_drive_root(scanner.path) else None
        self.scan_page.begin(scanner.path, expected)
        self.pages.setCurrentWidget(self.scan_page)
        self.setWindowTitle(f"Scanning {scanner.path} — {APP_NAME}")
        self.status_label.setText("")
        self.issues_button.hide()
        self._update_actions()
        scanner.start()
        self._poll.start()

    def _poll_scan(self) -> None:
        scanner = self._scanner
        if scanner is None:
            self._poll.stop()
            return
        self.scan_page.show_progress(scanner.progress())
        if scanner.done:
            self._poll.stop()
            self._finish_scan()

    def _finish_scan(self) -> None:
        scanner, self._scanner = self._scanner, None
        failure, tree = scanner.failure, scanner.result
        del scanner
        parts, self._restore_parts = self._restore_parts, None
        if failure is not None or tree is None or self._discard_scan:
            self._release_memory(tree)
            tree = None
            if failure is not None:
                QMessageBox.critical(self, APP_NAME, f"The scan stopped with an error:\n\n{failure!r}")
            self._update_actions()
            self.show_start()
            return
        root = None
        if parts:
            found = tree.find(parts)
            if found is not None and found.is_dir:
                root = found
        self.load_tree(tree, root)
        self._update_actions()

    def stop_scan(self, keep_results: bool) -> None:
        if self._scanner is None:
            return
        self._discard_scan = not keep_results
        self._scanner.cancel()
        self.scan_page.set_stopping()

    def rescan(self) -> None:
        tree = self.state.tree
        if tree is None or self._scanner is not None:
            return
        self.start_scan(tree.root_path, restore_parts=tree.parts_of(self.state.root))

    def browse(self) -> None:
        if self._scanner is not None:
            return
        start = str(self.settings.get("last_folder", str(Path.home())))
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to scan", start)
        if path:
            self.settings.set("last_folder", path)
            self.start_scan(path)

    def _drop_tree(self) -> None:
        tree = self.state.tree
        if tree is not None:
            self.state.set_tree(None)  # every widget lets go of the old nodes first
        self._release_memory(tree)

    @staticmethod
    def _release_memory(tree: ScanTree | None) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            release_tree(tree)
        finally:
            QApplication.restoreOverrideCursor()

    # ------------------------------------------------------- items and shell

    def show_node_menu(self, node: Node, pos: QPoint) -> None:
        state = self.state
        if state.tree is None or node is None:
            return
        menu = QMenu(self)
        if node.is_dir:
            if node is not state.root:
                menu.addAction("Zoom in", lambda: state.set_root(node))
            menu.addAction("Open folder", lambda: self.node_action("open", node))
        else:
            menu.addAction("Open", lambda: self.node_action("open", node))
            if node.parent is not state.root:
                menu.addAction("Zoom to its folder", lambda: self.node_action("zoom", node))
        menu.addAction(REVEAL_LABEL, lambda: self.node_action("reveal", node))
        menu.addAction("Copy path", lambda: self.node_action("copy", node))
        if not node.is_dir:
            menu.addSeparator()
            ext = node.extension
            label = f"Highlight .{ext} files" if ext else "Highlight files with no extension"
            menu.addAction(label, lambda: state.set_emphasis(("extension", ext)))
            category = CATEGORIES[node.category]
            menu.addAction(f"Highlight {category.label.lower()}",
                           lambda: state.set_emphasis(("category", category.index)))
        menu.exec(pos)

    def node_action(self, action: str, node: Node) -> None:
        tree = self.state.tree
        if tree is None:
            return
        path = tree.path_of(node)
        try:
            if action == "open":
                open_path(path)
            elif action == "reveal":
                reveal_in_file_manager(path)
            elif action == "copy":
                QGuiApplication.clipboard().setText(path)
                self.statusBar().showMessage(f"Copied {path}", 3000)
            elif action == "zoom":
                if node.is_dir:
                    self.state.set_root(node)
                else:
                    self.state.set_root(node.parent)
                    self.state.select(node)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Couldn't open {path}:\n{exc}")

    def _clear_highlight(self) -> None:
        if self.state.emphasis is not None:
            self.state.set_emphasis(None)
        else:
            self.state.select(None)

    def _set_include_cloud(self, checked: bool) -> None:
        self.state.set_include_cloud(checked)
        self.settings.set("include_online_only", checked)

    def _set_theme(self, mode: str) -> None:
        self.themes.set_mode(mode)
        self.settings.set("theme", mode)

    # --------------------------------------------------------------- dialogs

    def show_issues(self) -> None:
        tree = self.state.tree
        if tree is None or not tree.error_count:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Items that couldn't be read")
        dialog.resize(760, 440)
        layout = QVBoxLayout(dialog)
        intro = QLabel(
            f"{format_count(tree.error_count, 'item')} couldn't be read, so their sizes are missing from "
            "the totals. Windows protects some system folders; running the app as administrator reads more "
            "of them.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(f"{path}    ({reason})" for path, reason in tree.errors))
        layout.addWidget(text, 1)
        if tree.error_count > len(tree.errors):
            layout.addWidget(QLabel(f"Showing the first {format_count(len(tree.errors))} folders."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy = buttons.addButton("Copy list", QDialogButtonBox.ButtonRole.ActionRole)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(text.toPlainText()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def show_shortcuts(self) -> None:
        rows = (
            ("Click", "Select a file or folder"),
            ("Double-click", "Zoom into a folder (or a file's folder)"),
            ("Right-click", "Open, show in Explorer, copy the path, highlight a type"),
            ("Backspace or mouse Back", "Up one level"),
            ("Alt+Home", "Back to the scanned folder"),
            ("Click a type in the key", "Highlight just that type; click again to clear"),
            ("Esc", "Clear the highlight, then the selection"),
            ("Ctrl+1 / Ctrl+2", "Treemap / sunburst"),
            ("F5", "Rescan"),
            ("Ctrl+O", "Scan a folder"),
            ("Ctrl+N", "New scan"),
        )
        html = "<table cellspacing='6'>" + "".join(
            f"<tr><td><b>{key}</b></td><td>&nbsp;&nbsp;{what}</td></tr>" for key, what in rows) + "</table>"
        QMessageBox.information(self, "Keyboard and mouse", html)

    def show_about(self) -> None:
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br><br>"
            "Shows what is using the space on a drive or in a folder, as a treemap or a sunburst.<br><br>"
            "Sizes are what Windows reports for each file. OneDrive files that are only stored online "
            "are counted separately, and links are skipped so nothing is counted twice.")

    # ---------------------------------------------------------- drag & drop

    @staticmethod
    def _dropped_folder(event) -> str | None:
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            return None
        for url in mime.urls():
            if url.isLocalFile() and os.path.isdir(url.toLocalFile()):
                return url.toLocalFile()
        return None

    def dragEnterEvent(self, event) -> None:
        if self._scanner is None and self._dropped_folder(event):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        path = self._dropped_folder(event)
        if path:
            event.acceptProposedAction()
            self.start_scan(path)

    # -------------------------------------------------------------- settings

    def _restore_settings(self) -> None:
        geometry = self.settings.get_bytes("window/geometry")
        if geometry is None or not self.restoreGeometry(geometry):
            self.resize(1400, 880)
        self.set_view(str(self.settings.get("view", "treemap")))
        sizes = str(self.settings.get("window/splitter", ""))
        if sizes:
            try:
                self.results_page.splitter.setSizes([int(s) for s in sizes.split(",")])
            except ValueError:
                pass
        self.actions["online"].setChecked(self.state.include_cloud)
        self.actions[f"theme_{self.themes.mode}"].setChecked(True)

    def _save_settings(self) -> None:
        self.settings.set("window/geometry", self.saveGeometry())
        self.settings.set("window/splitter", ",".join(str(s) for s in self.results_page.splitter.sizes()))
        self.settings.set("view", self.results_page.view)
        self.settings.sync()

    def closeEvent(self, event) -> None:
        if self._scanner is not None:
            self._scanner.cancel()
        self._save_settings()
        super().closeEvent(event)
