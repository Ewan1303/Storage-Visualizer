"""The file type viewer: every photo, video or other kind of file in a scan, in one window.

Pick the kinds of file at the top, narrow them down by name, extension, size
or folder, and browse the results as thumbnails or as a list.
"""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListView, QMainWindow, QMenu, QMessageBox, QSlider, QSplitter,
                               QStackedWidget, QTableView, QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME
from ..core.categories import KIND_CATEGORY, KIND_LABELS, KIND_NOUNS, Kind
from ..core.finder import SYSTEM_FOLDERS, FileMatches, FileQuery, find_files
from ..core.formatting import format_count, format_size
from ..core.model import FileNode
from ..core.system import open_path, reveal_in_file_manager
from .background import Background
from .painting import glyph_icon, swatch_icon
from .settings import Settings
from .state import ViewState
from .theme import ThemeManager
from .thumbnails import ThumbnailProvider
from .viewer_preview import PreviewPanel
from .viewer_results import FOLDER, MODIFIED, NAME, SIZE, TYPE, FileResultsModel, GridDelegate
from .widgets import FlowLayout, labelled, menu_text

KB, MB, GB = 1024, 1024 ** 2, 1024 ** 3

SIZE_CHOICES = (
    ("Any size", 1),
    ("At least 100 KB", 100 * KB),
    ("At least 1 MB", MB),
    ("At least 10 MB", 10 * MB),
    ("At least 100 MB", 100 * MB),
    ("At least 1 GB", GB),
)
SORT_CHOICES = (
    ("Largest first", SIZE, Qt.SortOrder.DescendingOrder),
    ("Smallest first", SIZE, Qt.SortOrder.AscendingOrder),
    ("Newest first", MODIFIED, Qt.SortOrder.DescendingOrder),
    ("Oldest first", MODIFIED, Qt.SortOrder.AscendingOrder),
    ("Name", NAME, Qt.SortOrder.AscendingOrder),
    ("Folder", FOLDER, Qt.SortOrder.AscendingOrder),
)
DEFAULT_KINDS = frozenset({Kind.PHOTOS, Kind.VIDEOS})
EVERYWHERE, THIS_FOLDER = 0, 1


class KindChips(QWidget):
    """One toggle per kind of file, each with the colour its files have in the charts."""

    changed = Signal()

    def __init__(self, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.themes = themes
        self._quiet = False
        self.buttons: dict[Kind, QToolButton] = {}
        flow = FlowLayout(self, spacing=6)
        for kind in Kind:
            button = QToolButton()
            button.setText(menu_text(KIND_LABELS[kind]))
            button.setCheckable(True)
            button.setProperty("chip", True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.toggled.connect(self._toggled)
            self.buttons[kind] = button
            flow.addWidget(button)
        themes.changed.connect(self._restyle)
        self._restyle()

    def _restyle(self, _theme=None) -> None:
        for kind, button in self.buttons.items():
            button.setIcon(swatch_icon(self.themes.theme.categories[KIND_CATEGORY[kind]], 14))

    def kinds(self) -> frozenset[Kind]:
        return frozenset(kind for kind, button in self.buttons.items() if button.isChecked())

    def set_kinds(self, kinds) -> None:
        self._quiet = True
        try:
            for kind, button in self.buttons.items():
                button.setChecked(kind in kinds)
        finally:
            self._quiet = False
        self.changed.emit()

    def _toggled(self, _checked: bool) -> None:
        if not self._quiet:
            self.changed.emit()


class GridView(QListView):
    """The thumbnail grid; says when its width changes so the cells can be refitted."""

    resized = Signal()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class StayOpenMenu(QMenu):
    """A menu whose tick boxes can be toggled several at a time without it closing."""

    def mouseReleaseEvent(self, event) -> None:
        action = self.actionAt(event.position().toPoint())
        if action is not None and action.isCheckable() and action.isEnabled():
            action.trigger()
            return
        super().mouseReleaseEvent(event)


class FileViewer(QMainWindow):
    showInChart = Signal()  # the main window should come to the front

    def __init__(self, state: ViewState, themes: ThemeManager, settings: Settings,
                 thumbnails: ThumbnailProvider) -> None:
        super().__init__()
        self.state = state
        self.themes = themes
        self.settings = settings
        self.thumbnails = thumbnails
        self._extensions: frozenset[str] | None = None
        self._matches: FileMatches | None = None
        self._folder = None   # the folder searched when the scope is "Only in ..."
        self._job = 0
        self._dirty = True
        self.setWindowTitle(f"File type viewer — {APP_NAME}")
        self.setMinimumSize(780, 520)

        self._build_filters()
        self._build_results()
        self._build_status()
        self._wire()
        self._restore_settings()
        self._root_changed()

    # ---------------------------------------------------------------- layout

    def _build_filters(self) -> None:
        self.chips = KindChips(self.themes)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search file names")
        self.search.setClearButtonEnabled(True)
        self._search_icon = self.search.addAction(glyph_icon("search", self.themes.theme.muted),
                                                  QLineEdit.ActionPosition.LeadingPosition)
        self.extension_button = QToolButton()
        self.extension_button.setProperty("chip", True)
        self.extension_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.extension_menu = StayOpenMenu(self.extension_button)
        self.extension_button.setMenu(self.extension_menu)
        self.size_box = QComboBox()
        for label, minimum in SIZE_CHOICES:
            self.size_box.addItem(label, minimum)
        self.scope_box = QComboBox()
        self.scope_box.addItem("Everything scanned")
        self.scope_box.addItem("This folder")
        self.include_system = QCheckBox("Include app and system folders")
        names = ", ".join(sorted(SYSTEM_FOLDERS, key=str.casefold))
        self.include_system.setToolTip(
            "Folders full of program and system files, skipped unless this is ticked, so your own photos "
            f"and videos are not buried under app icons and game files:\n{names}")

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.search, 1)
        row.addWidget(self.extension_button)
        row.addWidget(self.size_box)
        row.addWidget(self.scope_box)
        row.addSpacing(4)
        row.addWidget(self.include_system)

        self.filter_bar = QWidget()
        self.filter_bar.setObjectName("FilterBar")
        self.filter_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        bar = QVBoxLayout(self.filter_bar)
        bar.setContentsMargins(14, 12, 14, 12)
        bar.setSpacing(10)
        bar.addWidget(self.chips)
        bar.addLayout(row)

    def _build_results(self) -> None:
        self.summary = labelled("", "secondary", elide=Qt.TextElideMode.ElideRight)
        self.sort_box = QComboBox()
        for label, _column, _order in SORT_CHOICES:
            self.sort_box.addItem(label)
        self.grid_button = QToolButton()
        self.list_button = QToolButton()
        for button, tip in ((self.grid_button, "Thumbnails"), (self.list_button, "List")):
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.grid_button.setChecked(True)
        segmented = QWidget()
        segmented.setObjectName("Segmented")
        segmented.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        seg = QHBoxLayout(segmented)
        seg.setContentsMargins(2, 2, 2, 2)
        seg.setSpacing(2)
        seg.addWidget(self.grid_button)
        seg.addWidget(self.list_button)
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(96, 256)
        self.zoom.setSingleStep(16)
        self.zoom.setPageStep(32)
        self.zoom.setValue(160)
        self.zoom.setFixedWidth(110)
        self.zoom.setToolTip("Thumbnail size")

        header = QHBoxLayout()
        header.setContentsMargins(14, 8, 14, 8)
        header.setSpacing(8)
        header.addWidget(self.summary, 1)
        header.addWidget(labelled("Sort", "muted"))
        header.addWidget(self.sort_box)
        header.addSpacing(6)
        header.addWidget(segmented)
        header.addWidget(self.zoom)

        self.model = FileResultsModel(self.state, self.themes, self)
        self.delegate = GridDelegate(self.state, self.themes, self.thumbnails, self)
        self.grid = GridView()
        # Always showing the scroll bar keeps the width steady while cells are refitted.
        self.grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setUniformItemSizes(True)
        self.grid.setLayoutMode(QListView.LayoutMode.Batched)
        self.grid.setBatchSize(400)
        self.grid.setSpacing(0)
        self.grid.setMouseTracking(True)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.grid.verticalScrollBar().setSingleStep(30)
        self.grid.setItemDelegate(self.delegate)
        self.grid.setModel(self.model)
        self.grid.setModelColumn(NAME)
        self.grid.setContentsMargins(8, 8, 8, 8)

        self.list = QTableView()
        self.list.setModel(self.model)
        self.list.setSelectionModel(self.grid.selectionModel())  # one selection, two views
        self.list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list.setShowGrid(False)
        self.list.setWordWrap(False)
        self.list.setIconSize(QSize(14, 14))
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.verticalHeader().hide()
        self.list.verticalHeader().setDefaultSectionSize(26)
        columns = self.list.horizontalHeader()
        columns.setHighlightSections(False)
        columns.setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        for column, width in ((SIZE, 80), (TYPE, 130), (MODIFIED, 110), (FOLDER, 280)):
            columns.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            columns.resizeSection(column, width)
        columns.setSortIndicator(SIZE, Qt.SortOrder.DescendingOrder)
        self.list.setSortingEnabled(True)

        for view in (self.grid, self.list):
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(lambda pos, v=view: self._context_menu(v, pos))
            view.activated.connect(self._activated)  # double-click or Enter

        self.message = QLabel()
        self.message.setProperty("role", "muted")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setContentsMargins(40, 40, 40, 40)
        self.stack = QStackedWidget()
        for page in (self.grid, self.list, self.message):
            self.stack.addWidget(page)

        self.preview = PreviewPanel(self.state, self.themes, self.thumbnails)
        self.preview.setMinimumWidth(260)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setCollapsible(0, False)
        self.splitter.setSizes([900, 320])

        results = QWidget()
        results.setObjectName("Panel")
        results.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        column = QVBoxLayout(results)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addLayout(header)
        column.addWidget(self.splitter, 1)

        central = QWidget()
        page = QVBoxLayout(central)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addWidget(self.filter_bar)
        page.addWidget(results, 1)
        self.setCentralWidget(central)

    def _build_status(self) -> None:
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        self.selection_label = QLabel("")
        status.addWidget(self.selection_label, 1)

    def _wire(self) -> None:
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self.search_now)
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(60)
        self._repaint_timer.timeout.connect(self._repaint_thumbnails)
        self._background = Background(self)
        self._background.finished.connect(self._found)

        self.chips.changed.connect(self._kinds_changed)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        self.size_box.currentIndexChanged.connect(lambda _i: self.search_now())
        self.scope_box.currentIndexChanged.connect(self._scope_chosen)
        self.include_system.toggled.connect(lambda _on: self.search_now())
        self.sort_box.currentIndexChanged.connect(self._sort_chosen)
        self.model.sortChanged.connect(self._sort_shown)
        self.grid_button.toggled.connect(lambda _on: self._show_results_page())
        self.zoom.valueChanged.connect(self._zoom_changed)
        self.grid.resized.connect(self._fit_grid)
        self.grid.selectionModel().selectionChanged.connect(lambda *_: self._selection_changed())
        self.preview.actionRequested.connect(self._act)
        self.thumbnails.ready.connect(self._thumbnail_ready)
        self.state.treeChanged.connect(self._tree_changed)
        self.state.rootChanged.connect(self._root_changed)
        self.themes.changed.connect(self._restyle)

        QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self, self.search.setFocus)
        copy = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), self.stack, lambda: self._act("copy", self._selected()))
        copy.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._restyle()
        self._zoom_changed(self.zoom.value())

    def _restyle(self, _theme=None) -> None:
        colour = self.themes.theme.text
        self.grid_button.setIcon(glyph_icon("grid", colour))
        self.list_button.setIcon(glyph_icon("list", colour))
        self._search_icon.setIcon(glyph_icon("search", self.themes.theme.muted))
        self.grid.viewport().update()

    # ---------------------------------------------------------------- public

    def show_types(self, kinds=None, extensions=None, in_folder: bool | None = None) -> None:
        """Bring the window up showing ``kinds`` (optionally only ``extensions``).

        ``in_folder`` limits the search to the folder the main window is showing
        (False searches everything scanned; None keeps the current choice).
        """
        if kinds is not None:
            self.chips.set_kinds(frozenset(kinds))
        if extensions is not None:
            self._extensions = frozenset(extensions) or None
            self._update_extension_button()
        if in_folder is not None:
            self._set_scope(in_folder)
        self._dirty = True
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_now()

    def search_now(self) -> None:
        """Start looking for files that match the filters (on a worker thread)."""
        self._search_timer.stop()
        self._job += 1
        if not self.isVisible():
            self._dirty = True  # look once the window is shown
            return
        self._dirty = False
        tree = self.state.tree
        if tree is None:
            self._set_results(None, "Scan a drive or folder first: the files it finds will show up here.")
            return
        kinds = self.chips.kinds()
        if not kinds:
            self._set_results(None, "Choose one or more kinds of file above.")
            return
        query = FileQuery(
            kinds=kinds,
            extensions=self._extensions,
            text=self.search.text(),
            min_size=self.size_box.currentData() or 1,
            skip_system=not self.include_system.isChecked(),
        )
        under = self._scope_root()
        job = self._job
        order = (self.model.sort_column, self.model.sort_order)
        self.summary.setFullText("Looking…")

        def work():
            matches = find_files(under, query, stop=lambda: job != self._job)
            if matches is not None and job == self._job:
                self.model.sort_files(matches.files, *order)  # millions of files take a while to sort
            return matches, order
        self._background.run((job, tree, query), work)

    # ------------------------------------------------------------- searching

    def _scope_root(self):
        if self.scope_box.currentIndex() == THIS_FOLDER and self._folder is not None:
            return self._folder
        return self.state.tree.root

    def _set_scope(self, in_folder: bool) -> None:
        """Search everything, or only the folder the main window shows right now.

        The folder is pinned when chosen, so moving around in the main window
        (or "Show in chart" from here) does not quietly change these results.
        """
        state = self.state
        inside = state.tree is not None and state.root is not None and state.root is not state.tree.root
        self._folder = state.root if in_folder and inside else None
        self.scope_box.blockSignals(True)
        if self._folder is not None:
            self.scope_box.setItemText(THIS_FOLDER, f"Only in {state.tree.display_name(self._folder)}")
            self.scope_box.model().item(THIS_FOLDER).setEnabled(True)
            self.scope_box.setCurrentIndex(THIS_FOLDER)
        else:
            self.scope_box.setCurrentIndex(EVERYWHERE)
            self._offer_current_folder()
        self.scope_box.blockSignals(False)

    def _scope_chosen(self, index: int) -> None:
        self._set_scope(index == THIS_FOLDER)
        self.search_now()

    def _offer_current_folder(self) -> None:
        """Name the main window's folder in the scope list, ready to be picked."""
        state = self.state
        inside = state.tree is not None and state.root is not None and state.root is not state.tree.root
        self.scope_box.setItemText(THIS_FOLDER, f"Only in {state.tree.display_name(state.root)}" if inside
                                   else "Only in the current folder")
        self.scope_box.model().item(THIS_FOLDER).setEnabled(inside)

    def _kinds_changed(self) -> None:
        self._extensions = None  # an extension picked for one kind would hide all the others
        self._update_extension_button()
        self.search_now()

    def _found(self, job: tuple, result: tuple | None) -> None:
        number, tree, query = job
        if number != self._job or tree is not self.state.tree or result is None or result[0] is None:
            return  # the filters or the scan changed while this was running
        matches, order = result
        self._set_results(matches, None if matches.files else self._nothing_found(query), order)

    def _set_results(self, matches: FileMatches | None, message: str | None, order: tuple | None = None) -> None:
        self._matches = matches
        self.model.set_files(matches.files if matches is not None else [], sorted_by=order)
        self._fill_extension_menu()
        if message:
            self.message.setText(message)
        self._show_results_page(message is not None)
        self.summary.setFullText(self._summary(matches))
        self._selection_changed()

    def _nothing_found(self, query: FileQuery) -> str:
        names = [KIND_NOUNS[k][1] for k in sorted(query.kinds)]
        what = ", ".join(names[:-1]) + f" or {names[-1]}" if len(names) > 1 else names[0]
        hints = []
        if query.text:
            hints.append("a shorter search")
        if query.extensions:
            hints.append("all extensions")
        if query.min_size > 1:
            hints.append("a smaller minimum size")
        if query.skip_system:
            hints.append("including app and system folders")
        text = f"No {what} found here."
        if hints:
            text += " Try " + ", ".join(hints[:-1]) + (" or " if len(hints) > 1 else "") + hints[-1] + "."
        return text

    def _summary(self, matches: FileMatches | None) -> str:
        if matches is None or not matches.files:
            return ""
        text = f"{format_count(len(matches.files), 'file')}  ·  {format_size(matches.bytes)}"
        if len(matches.by_kind) > 1:
            parts = [format_count(n, *KIND_NOUNS[k]) for k, n in sorted(matches.by_kind.items())]
            text += "  ·  " + ", ".join(parts)
        if matches.cloud_bytes:
            text += f"  ·  {format_size(matches.cloud_bytes)} of it online-only"
        return text

    def _show_results_page(self, message: bool | None = None) -> None:
        if message is None:
            message = self.stack.currentWidget() is self.message
        grid = self.grid_button.isChecked()
        self.zoom.setVisible(grid)
        self.stack.setCurrentWidget(self.message if message else (self.grid if grid else self.list))

    # -------------------------------------------------------- extension menu

    def _fill_extension_menu(self) -> None:
        menu = self.extension_menu
        menu.clear()
        everything = menu.addAction("All extensions")
        everything.setCheckable(True)
        everything.setChecked(self._extensions is None)
        everything.triggered.connect(self._all_extensions)
        rows = self._matches.extensions if self._matches is not None else []
        if rows:
            menu.addSeparator()
        for ext, files, nbytes in rows[:40]:
            label = f".{ext}" if ext else "(no extension)"
            action = menu.addAction(f"{label}    {format_count(files, 'file')}  ·  {format_size(nbytes)}")
            action.setCheckable(True)
            action.setChecked(self._extensions is not None and ext in self._extensions)
            action.toggled.connect(lambda on, e=ext: self._toggle_extension(e, on))
        self._update_extension_button()

    def _all_extensions(self) -> None:
        self._extensions = None
        self._fill_extension_menu()
        self.search_now()

    def _toggle_extension(self, ext: str, on: bool) -> None:
        chosen = set(self._extensions or ())
        if on:
            chosen.add(ext)
        else:
            chosen.discard(ext)
        self._extensions = frozenset(chosen) or None
        for action in self.extension_menu.actions():
            if action.text() == "All extensions":
                action.setChecked(self._extensions is None)
        self._update_extension_button()
        self._search_timer.start()

    def _update_extension_button(self) -> None:
        chosen = sorted(self._extensions or ())
        if not chosen:
            text = "All extensions"
        elif len(chosen) <= 3:
            text = ", ".join(f".{e}" if e else "(none)" for e in chosen)
        else:
            text = f"{len(chosen)} extensions"
        self.extension_button.setText(text + "  ▾")

    # -------------------------------------------------------------- sorting

    def _sort_chosen(self, index: int) -> None:
        if 0 <= index < len(SORT_CHOICES):
            _label, column, order = SORT_CHOICES[index]
            self.list.horizontalHeader().setSortIndicator(column, order)  # sorts the model too

    def _sort_shown(self, column: int, order) -> None:
        for i, (_label, c, o) in enumerate(SORT_CHOICES):
            if c == column and o == order:
                break
        else:
            i = -1
        self.sort_box.blockSignals(True)
        self.sort_box.setCurrentIndex(i)
        self.sort_box.blockSignals(False)

    # ----------------------------------------------------------- selection

    def _selected(self) -> list[FileNode]:
        rows = sorted({index.row() for index in self.grid.selectionModel().selectedIndexes()})
        return [f for f in (self.model.file_at(r) for r in rows) if f is not None]

    def _selection_changed(self) -> None:
        files = self._selected()
        self.preview.show_files(files)
        if files:
            total = sum(f.size + f.cloud for f in files)
            self.selection_label.setText(f"{format_count(len(files))} selected  ·  {format_size(total)}")
        else:
            self.selection_label.setText("Double-click a file to open it. Right-click for more.")

    def _activated(self, index: QModelIndex) -> None:
        node = self.model.file_at(index.row())
        if node is not None:
            self._act("open", [node])

    def _context_menu(self, view: QAbstractItemView, pos: QPoint) -> None:
        index = view.indexAt(pos)
        if index.isValid() and not view.selectionModel().isSelected(index):
            flags = QItemSelectionModel.SelectionFlag
            view.selectionModel().select(index, flags.ClearAndSelect | flags.Rows)
        files = self._selected()
        if not files:
            return
        menu = QMenu(self)
        if len(files) == 1:
            menu.addAction("Open", lambda: self._act("open", files))
        menu.addAction(self.preview.buttons["reveal"].text(), lambda: self._act("reveal", files))
        menu.addAction("Show in chart", lambda: self._act("chart", files))
        menu.addAction("Copy path" if len(files) == 1 else f"Copy {len(files)} paths",
                       lambda: self._act("copy", files))
        menu.exec(view.viewport().mapToGlobal(pos))

    def _act(self, action: str, files: list[FileNode]) -> None:
        tree = self.state.tree
        if tree is None or not files:
            return
        first = files[0]
        try:
            if action == "open":
                open_path(tree.path_of(first))
            elif action == "reveal":
                reveal_in_file_manager(tree.path_of(first))
            elif action == "copy":
                QGuiApplication.clipboard().setText("\n".join(tree.path_of(f) for f in files))
                self.statusBar().showMessage(
                    "Copied the path" if len(files) == 1 else f"Copied {len(files)} paths", 2500)
            elif action == "chart":
                self.state.set_root(first.parent)
                self.state.select(first)
                self.showInChart.emit()
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Couldn't open {tree.path_of(first)}:\n{exc}")

    # ------------------------------------------------------------- reacting

    def _tree_changed(self) -> None:
        # Let go of the old scan's files at once: the main window frees them next.
        self._job += 1
        self._matches = None
        self.model.set_files([])
        self.preview.clear()
        self._extensions = None
        self._update_extension_button()
        self._set_scope(False)
        self.search_now()

    def _root_changed(self) -> None:
        if self.scope_box.currentIndex() != THIS_FOLDER:
            self._offer_current_folder()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            QTimer.singleShot(0, self._search_if_needed)

    def _search_if_needed(self) -> None:
        if self._dirty:  # nothing has searched since the window was hidden
            self.search_now()

    def _zoom_changed(self, value: int) -> None:
        self.delegate.thumb = value
        self._fit_grid()

    def _fit_grid(self) -> None:
        """As many columns as fit at the chosen size, stretched to use the whole row."""
        width = self.grid.viewport().width()
        smallest = self.delegate.smallest_cell()
        columns = max(1, width // smallest)
        self.delegate.cell_width = max(smallest, width // columns)
        self.grid.setGridSize(self.delegate.cell_size(self.grid.fontMetrics()))
        self.grid.viewport().update()

    def _thumbnail_ready(self) -> None:
        if not self._repaint_timer.isActive():
            self._repaint_timer.start()

    def _repaint_thumbnails(self) -> None:
        if self.isVisible():
            self.grid.viewport().update()
            self.preview.refresh_picture()

    # -------------------------------------------------------------- settings

    def _restore_settings(self) -> None:
        geometry = self.settings.get_bytes("viewer/geometry")
        if geometry is None or not self.restoreGeometry(geometry):
            self.resize(1280, 820)
        kinds = str(self.settings.get("viewer/kinds", ""))
        try:
            chosen = frozenset(Kind(int(k)) for k in kinds.split(",") if k.strip())
        except ValueError:
            chosen = frozenset()
        self.chips.set_kinds(chosen or DEFAULT_KINDS)
        self.include_system.setChecked(bool(self.settings.get("viewer/include_system", False)))
        self.size_box.setCurrentIndex(max(0, min(len(SIZE_CHOICES) - 1, int(self.settings.get("viewer/size", 0)))))
        sort = int(self.settings.get("viewer/sort", 0))
        self.sort_box.setCurrentIndex(sort if 0 <= sort < len(SORT_CHOICES) else 0)
        self._sort_chosen(self.sort_box.currentIndex())
        self.zoom.setValue(int(self.settings.get("viewer/thumbnail", 160)))
        self.list_button.setChecked(str(self.settings.get("viewer/view", "grid")) == "list")
        self.grid_button.setChecked(not self.list_button.isChecked())
        sizes = str(self.settings.get("viewer/splitter", ""))
        if sizes:
            try:
                self.splitter.setSizes([int(s) for s in sizes.split(",")])
            except ValueError:
                pass

    def save_settings(self) -> None:
        self.settings.set("viewer/geometry", self.saveGeometry())
        self.settings.set("viewer/kinds", ",".join(str(int(k)) for k in sorted(self.chips.kinds())))
        self.settings.set("viewer/include_system", self.include_system.isChecked())
        self.settings.set("viewer/size", self.size_box.currentIndex())
        self.settings.set("viewer/sort", max(0, self.sort_box.currentIndex()))
        self.settings.set("viewer/thumbnail", self.zoom.value())
        self.settings.set("viewer/view", "grid" if self.grid_button.isChecked() else "list")
        self.settings.set("viewer/splitter", ",".join(str(s) for s in self.splitter.sizes()))

    def closeEvent(self, event) -> None:
        self.save_settings()
        super().closeEvent(event)
