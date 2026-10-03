"""Facts about the selected item (or the current folder), with buttons to act on it."""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from ..core.categories import CATEGORIES
from ..core.formatting import format_size
from ..core.model import Node
from ..core.system import IS_WINDOWS
from .describe import file_type, folder_contents, mostly, share_of_view
from .state import ViewState
from .widgets import ElidedLabel, FlowLayout, labelled

REVEAL_LABEL = "Show in Explorer" if IS_WINDOWS else "Show in folder"


class DetailsPanel(QWidget):
    actionRequested = Signal(str, object)  # "open" | "reveal" | "copy" | "zoom", node

    def __init__(self, state: ViewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._node: Node | None = None

        self.heading = labelled("", "section")
        self.name = ElidedLabel("", Qt.TextElideMode.ElideMiddle)
        bold = QFont(self.name.font())
        bold.setPointSizeF(bold.pointSizeF() + 1.5)
        bold.setWeight(QFont.Weight.DemiBold)
        self.name.setFont(bold)
        self.size = labelled("", "secondary", elide=Qt.TextElideMode.ElideRight)
        self.kind = labelled("", "secondary", elide=Qt.TextElideMode.ElideRight)
        self.modified = labelled("", "muted", elide=Qt.TextElideMode.ElideRight)
        self.path = labelled("", "muted", elide=Qt.TextElideMode.ElideMiddle)
        self.path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.buttons: dict[str, QPushButton] = {}
        actions = QWidget()
        row = FlowLayout(actions, spacing=6)
        row.setContentsMargins(0, 6, 0, 0)
        for key, label in (("open", "Open"), ("reveal", REVEAL_LABEL), ("copy", "Copy path"), ("zoom", "Zoom in")):
            button = QPushButton(label)
            button.setProperty("compact", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self._act(k))
            self.buttons[key] = button
            row.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(3)
        layout.addWidget(self.heading)
        layout.addSpacing(2)
        layout.addWidget(self.name)
        layout.addWidget(self.size)
        layout.addWidget(self.kind)
        layout.addWidget(self.modified)
        layout.addWidget(self.path)
        layout.addWidget(actions)

        for signal in (state.treeChanged, state.rootChanged, state.sizesChanged, state.selectionChanged):
            signal.connect(self.refresh)
        self.refresh()

    def _act(self, key: str) -> None:
        if self._node is not None:
            self.actionRequested.emit(key, self._node)

    def refresh(self) -> None:
        state = self.state
        tree = state.tree
        if tree is None or state.root is None:
            self._node = None
            for label in (self.name, self.size, self.kind, self.modified, self.path):
                label.setFullText("")
            self.heading.setText("")
            for button in self.buttons.values():
                button.setEnabled(False)
            return
        node = state.selected if state.selected is not None else state.root
        self._node = node
        self.heading.setText("SELECTED" if state.selected is not None else "THIS FOLDER")
        self.name.setFullText(tree.display_name(node))
        value = state.sizes.value(node)
        size = format_size(value)
        if node is not state.root:
            size += f"  ·  {share_of_view(state, value)}"
        self.size.setFullText(size)
        if node.is_dir:
            kind = folder_contents(node)
            dominant = mostly(state, node)
            if dominant:
                kind += f"  ·  {dominant}"
        else:
            kind = f"{CATEGORIES[node.category].label}  ·  {file_type(node)}"
            if node.online_only:
                kind += "  ·  online-only"
        self.kind.setFullText(kind)
        modified = self._modified(tree.fs_path_of(node))
        self.modified.setFullText(modified)
        self.modified.setVisible(bool(modified))
        self.path.setFullText(tree.path_of(node))
        for key in ("open", "reveal", "copy"):
            self.buttons[key].setEnabled(True)
        self.buttons["zoom"].setEnabled(node.is_dir and node is not state.root)
        self.buttons["zoom"].setVisible(node.is_dir)

    @staticmethod
    def _modified(fs_path: str) -> str:
        try:
            stamp = os.stat(fs_path, follow_symlinks=False).st_mtime
        except OSError:
            return ""
        return "Modified " + datetime.fromtimestamp(stamp).strftime("%d %b %Y, %H:%M")
