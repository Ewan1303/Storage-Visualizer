"""The left-hand panel: three tables over the details of the selected item."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QTabWidget, QVBoxLayout, QWidget

from ..core.model import Node
from .details import DetailsPanel
from .state import ViewState
from .tables import ContentsModel, LargestModel, NodeTable, TypesModel, TypesTable
from .theme import ThemeManager


class SidePanel(QWidget):
    contextMenuRequested = Signal(object, QPoint)
    actionRequested = Signal(str, object)

    def __init__(self, state: ViewState, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.state = state

        self.contents = NodeTable(state, ContentsModel(state, themes), themes)
        self.types = TypesTable(state, TypesModel(state, themes), themes)
        self.largest = NodeTable(state, LargestModel(state, themes), themes, last_column_width=130)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.contents, "Contents")
        self.tabs.addTab(self.types, "File types")
        self.tabs.addTab(self.largest, "Largest files")

        line = QFrame()
        line.setFixedHeight(1)
        line.setObjectName("Rule")
        line.setStyleSheet("background: palette(mid);")
        self.details = DetailsPanel(state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(line)
        layout.addWidget(self.details)

        self.contents.nodeActivated.connect(self._open_from_contents)
        self.largest.nodeActivated.connect(self._open_from_largest)
        self.contents.contextMenuForNode.connect(self.contextMenuRequested)
        self.largest.contextMenuForNode.connect(self.contextMenuRequested)
        self.details.actionRequested.connect(self.actionRequested)

    def _open_from_contents(self, node: Node) -> None:
        if node.is_dir:
            self.state.set_root(node)

    def _open_from_largest(self, node: Node) -> None:
        self.state.set_root(node.parent)
        self.state.select(node)
