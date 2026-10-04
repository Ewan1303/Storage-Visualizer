"""The page shown after a scan: navigation bar, side panel, chart and legend."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from .breadcrumb import Breadcrumb
from .legend import Legend
from .side_panel import SidePanel
from .state import ViewState
from .summary import SummaryBar
from .sunburst_view import SunburstView
from .theme import ThemeManager
from .treemap_view import TreemapView

VIEWS = ("treemap", "sunburst")
SUNBURST_NOTE = "Folders take the colour of the file type that fills most of them."


def _tool_button(action: QAction, style: Qt.ToolButtonStyle) -> QToolButton:
    button = QToolButton()
    button.setDefaultAction(action)
    button.setToolButtonStyle(style)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class ResultsPage(QWidget):
    def __init__(self, state: ViewState, themes: ThemeManager, actions: dict[str, QAction],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        top = QWidget()
        top.setObjectName("TopBar")
        top.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        bar = QHBoxLayout(top)
        bar.setContentsMargins(8, 6, 10, 6)
        bar.setSpacing(6)
        bar.addWidget(_tool_button(actions["up"], Qt.ToolButtonStyle.ToolButtonIconOnly))
        self.breadcrumb = Breadcrumb(state)
        bar.addWidget(self.breadcrumb, 1)
        segmented = QWidget()
        segmented.setObjectName("Segmented")
        segmented.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        seg = QHBoxLayout(segmented)
        seg.setContentsMargins(2, 2, 2, 2)
        seg.setSpacing(2)
        for key in VIEWS:
            seg.addWidget(_tool_button(actions[key], Qt.ToolButtonStyle.ToolButtonTextOnly))
        bar.addWidget(segmented)
        bar.addSpacing(10)
        bar.addWidget(_tool_button(actions["viewer"], Qt.ToolButtonStyle.ToolButtonTextBesideIcon))
        bar.addWidget(_tool_button(actions["rescan"], Qt.ToolButtonStyle.ToolButtonTextBesideIcon))
        bar.addWidget(_tool_button(actions["new_scan"], Qt.ToolButtonStyle.ToolButtonTextBesideIcon))

        self.side = SidePanel(state, themes)
        self.side.setMinimumWidth(300)

        chart_area = QWidget()
        chart_area.setObjectName("ChartArea")
        chart_area.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        area = QVBoxLayout(chart_area)
        area.setContentsMargins(0, 0, 0, 10)
        area.setSpacing(6)
        self.summary = SummaryBar(state, themes)
        self.treemap = TreemapView(state, themes)
        self.sunburst = SunburstView(state, themes)
        self.charts = QStackedWidget()
        self.charts.addWidget(self.treemap)
        self.charts.addWidget(self.sunburst)
        self.legend = Legend(state, themes)
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(14, 0, 14, 0)
        legend_row.addWidget(self.legend)
        charts_row = QHBoxLayout()
        charts_row.setContentsMargins(10, 0, 10, 0)
        charts_row.addWidget(self.charts)
        area.addWidget(self.summary)
        area.addLayout(charts_row, 1)
        area.addLayout(legend_row)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.side)
        self.splitter.addWidget(chart_area)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([400, 1000])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(top)
        layout.addWidget(self.splitter, 1)

    @property
    def view(self) -> str:
        return "sunburst" if self.charts.currentWidget() is self.sunburst else "treemap"

    def set_view(self, name: str) -> None:
        sunburst = name == "sunburst"
        self.charts.setCurrentWidget(self.sunburst if sunburst else self.treemap)
        self.legend.set_note(SUNBURST_NOTE if sunburst else "")
