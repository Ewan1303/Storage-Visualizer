"""Clickable path from the scanned folder down to the one being viewed."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QToolButton, QWidget

from .state import ViewState
from .widgets import menu_text


class Breadcrumb(QWidget):
    MAX_VISIBLE = 5
    MAX_NAME_WIDTH = 220

    def __init__(self, state: ViewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        state.treeChanged.connect(self._rebuild)
        state.rootChanged.connect(self._rebuild)

    def _clear(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._clear()
        state = self.state
        if state.tree is None or state.root is None:
            return
        chain = []
        node = state.root
        while node is not None:
            chain.append(node)
            node = node.parent
        chain.reverse()
        hidden = []
        if len(chain) > self.MAX_VISIBLE:
            keep = self.MAX_VISIBLE - 1
            hidden = chain[1:-keep]
            chain = [chain[0], None, *chain[-keep:]]
        for i, node in enumerate(chain):
            if i:
                separator = QLabel("›")
                separator.setProperty("role", "muted")
                separator.setContentsMargins(2, 0, 2, 0)
                self._row.addWidget(separator)
            button = QToolButton()
            button.setProperty("crumb", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if node is None:
                button.setText("…")
                button.setToolTip("More folders")
                menu = QMenu(button)
                for folder in hidden:
                    action = menu.addAction(menu_text(state.tree.display_name(folder)))
                    action.triggered.connect(lambda _checked=False, n=folder: self.state.set_root(n))
                button.setMenu(menu)
                button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            else:
                name = state.tree.display_name(node)
                shown = button.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, self.MAX_NAME_WIDTH)
                button.setText(menu_text(shown))
                button.setToolTip(state.tree.path_of(node))
                if node is state.root:
                    button.setProperty("current", True)
                else:
                    button.clicked.connect(lambda _checked=False, n=node: self.state.set_root(n))
            self._row.addWidget(button)
        self._row.addStretch(1)
