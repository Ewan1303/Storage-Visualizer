"""Colours and widget styling for the light and dark themes.

File-type colours come from a colour-blind-checked categorical palette. In a
treemap any two types can touch, so every pair has to stay distinguishable,
not just neighbours in a fixed order. Of the palette's eight hues, four
(blue, yellow, magenta, green) were the largest set that passed every pairwise
check (protanopia, deuteranopia and normal vision) in both themes. "Other" is a
neutral grey that differs from all four by lightness, checked the same way.
Text never wears these colours; labels inside a coloured tile use black or
white, whichever contrasts more.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Theme:
    name: str
    is_dark: bool
    window: str      # app background
    surface: str     # panels and chart background
    raised: str      # buttons, cards, tooltips
    hover: str       # hover wash on controls
    selected: str    # selected rows, checked buttons
    border: str      # hairlines
    text: str
    text2: str       # secondary text
    muted: str       # least important text
    track: str       # the empty part of bars
    frames: tuple[str, ...]      # treemap folder fills, by depth
    categories: tuple[str, ...]  # file-type fills, in storagevis.core.categories order
    primary: str     # high-contrast button fill
    primary_text: str


DARK = Theme(
    name="dark",
    is_dark=True,
    window="#131312",
    surface="#1a1a19",
    raised="#242422",
    hover="#2c2c2a",
    selected="#383835",
    border="#313130",
    text="#ffffff",
    text2="#c3c2b7",
    muted="#898781",
    track="#2c2c2a",
    frames=("#232322", "#292927", "#2f2f2c", "#353532"),
    categories=("#3987e5", "#c98500", "#d55181", "#008300", "#52514e"),
    primary="#ffffff",
    primary_text="#0b0b0b",
)

LIGHT = Theme(
    name="light",
    is_dark=False,
    window="#f1f0ec",
    surface="#fcfcfb",
    raised="#ffffff",
    hover="#ebeae6",
    selected="#e1e0d9",
    border="#dfdfdc",
    text="#0b0b0b",
    text2="#52514e",
    muted="#6f6e69",  # darker than the dark theme's grey so small text keeps ~5:1 contrast
    track="#ebeae6",
    frames=("#f3f2ef", "#ebeae6", "#e3e2dd", "#dbdad4"),
    categories=("#2a78d6", "#eda100", "#e87ba4", "#008300", "#c3c2b7"),
    primary="#0b0b0b",
    primary_text="#ffffff",
)

THEME_MODES = ("system", "light", "dark")

# Status colours mean "something needs attention". They are the same in both
# themes, are never used for file types, and always come with an icon and words.
STATUS_WARNING = "#fab219"
STATUS_CRITICAL = "#d03b3b"


class ThemeManager(QObject):
    """Applies the chosen theme to the whole app and tells custom widgets when it changes."""

    changed = Signal(object)

    def __init__(self, app: QApplication, mode: str = "system") -> None:
        super().__init__(app)
        self._app = app
        self._mode = mode if mode in THEME_MODES else "system"
        self._theme: Theme = DARK
        self._applying = False
        app.styleHints().colorSchemeChanged.connect(self._on_system_scheme)
        self._apply()

    @property
    def theme(self) -> Theme:
        return self._theme

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode in THEME_MODES and mode != self._mode:
            self._mode = mode
            self._apply()

    def _resolve(self) -> Theme:
        if self._mode == "light":
            return LIGHT
        if self._mode == "dark":
            return DARK
        return DARK if self._app.styleHints().colorScheme() == Qt.ColorScheme.Dark else LIGHT

    def _on_system_scheme(self, _scheme) -> None:
        if self._mode == "system" and not self._applying and self._resolve() is not self._theme:
            self._apply()

    def _apply(self) -> None:
        self._applying = True
        try:
            hints = self._app.styleHints()
            if hasattr(hints, "setColorScheme"):  # Qt 6.8+: also themes the title bar
                scheme = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(
                    self._mode, Qt.ColorScheme.Unknown)
                hints.setColorScheme(scheme)
            self._theme = self._resolve()
            self._app.setPalette(build_palette(self._theme))
            self._app.setStyleSheet(build_stylesheet(self._theme))
        finally:
            self._applying = False
        self.changed.emit(self._theme)


def build_palette(t: Theme) -> QPalette:
    pal = QPalette()
    role = QPalette.ColorRole
    colours = {
        role.Window: t.window,
        role.WindowText: t.text,
        role.Base: t.surface,
        role.AlternateBase: t.raised,
        role.Text: t.text,
        role.Button: t.raised,
        role.ButtonText: t.text,
        role.BrightText: t.text,
        role.Highlight: t.selected,
        role.HighlightedText: t.text,
        role.ToolTipBase: t.raised,
        role.ToolTipText: t.text,
        role.PlaceholderText: t.muted,
        role.Link: t.text,
        role.Light: t.hover,
        role.Midlight: t.raised,
        role.Mid: t.border,
        role.Dark: t.border,
        role.Shadow: t.window,
    }
    for r, value in colours.items():
        pal.setColor(r, QColor(value))
    disabled = QPalette.ColorGroup.Disabled
    for r in (role.WindowText, role.Text, role.ButtonText):
        pal.setColor(disabled, r, QColor(t.muted))
    return pal


_ASSETS = Path(__file__).resolve().parent / "assets"


def _tick(theme: Theme, on: str) -> str:
    """Path to the tick drawn in check boxes ("box": on a filled box, "text": on a menu row)."""
    return (_ASSETS / f"tick-{theme.name}-{on}.svg").as_posix()


def build_stylesheet(t: Theme) -> str:
    return f"""
    QMainWindow, QStackedWidget#Pages {{ background: {t.window}; }}
    QWidget#Panel, QWidget#TopBar, QWidget#SidePanel, QWidget#ChartArea {{ background: {t.surface}; }}
    QWidget#TopBar {{ border-bottom: 1px solid {t.border}; }}
    QWidget#ScanCard {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px; }}

    QLabel {{ background: transparent; }}
    QLabel[role="hero"] {{ font-size: 22pt; font-weight: 600; }}
    QLabel[role="title"] {{ font-size: 14pt; font-weight: 600; }}
    QLabel[role="section"] {{ color: {t.muted}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
    QLabel[role="secondary"] {{ color: {t.text2}; }}
    QLabel[role="muted"] {{ color: {t.muted}; }}
    QLabel[role="stat"] {{ font-size: 16pt; font-weight: 600; }}

    QToolButton {{
        background: transparent; border: none; border-radius: 6px; padding: 4px 8px; color: {t.text};
    }}
    QToolButton:hover {{ background: {t.hover}; }}
    QToolButton:pressed, QToolButton:checked {{ background: {t.selected}; }}
    QToolButton:disabled {{ color: {t.muted}; }}
    QToolButton[crumb="true"] {{ padding: 4px 6px; color: {t.text2}; }}
    QToolButton[crumb="true"]:hover {{ color: {t.text}; }}
    QToolButton[current="true"] {{ color: {t.text}; font-weight: 600; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}

    QWidget#Segmented {{ background: {t.window}; border: 1px solid {t.border}; border-radius: 7px; }}
    QWidget#Segmented QToolButton {{ border-radius: 5px; padding: 3px 12px; color: {t.text2}; }}
    QWidget#Segmented QToolButton:checked {{ background: {t.raised}; color: {t.text}; }}

    QPushButton {{
        background: {t.raised}; color: {t.text}; border: 1px solid {t.border};
        border-radius: 6px; padding: 6px 14px;
    }}
    QPushButton:hover {{ background: {t.hover}; }}
    QPushButton:pressed {{ background: {t.selected}; }}
    QPushButton:disabled {{ color: {t.muted}; }}
    QPushButton[primary="true"] {{ background: {t.primary}; color: {t.primary_text}; border: 1px solid {t.primary}; }}
    QPushButton[primary="true"]:hover {{ background: {t.text2}; border-color: {t.text2}; }}
    QPushButton[compact="true"] {{ padding: 4px 10px; }}
    QPushButton[flat="true"] {{ background: transparent; border: none; padding: 4px 8px; color: {t.text2}; }}
    QPushButton[flat="true"]:hover {{ background: {t.hover}; color: {t.text}; }}

    QTabWidget::pane {{ border: none; }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        background: transparent; color: {t.text2}; padding: 8px 12px; margin-right: 2px;
        border: none; border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:hover {{ color: {t.text}; }}
    QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.text}; }}

    QTableView {{
        background: {t.surface}; alternate-background-color: {t.surface}; border: none;
        gridline-color: transparent; selection-background-color: {t.selected};
        selection-color: {t.text}; outline: 0;
    }}
    QTableView::item {{ border: none; padding: 0 4px; }}
    QTableView::item:hover {{ background: {t.hover}; }}
    QTableView::item:selected {{ background: {t.selected}; color: {t.text}; }}
    QHeaderView {{ background: {t.surface}; border: none; }}
    QHeaderView::section {{
        background: {t.surface}; color: {t.muted}; border: none; border-bottom: 1px solid {t.border};
        padding: 5px 6px; font-weight: 600;
    }}
    QHeaderView::section:hover {{ color: {t.text}; }}
    QHeaderView::up-arrow, QHeaderView::down-arrow {{ image: none; width: 0; height: 0; }}
    QTableCornerButton::section {{ background: {t.surface}; border: none; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle {{ background: {t.selected}; border-radius: 3px; margin: 2px; }}
    QScrollBar::handle:hover {{ background: {t.muted}; }}
    QScrollBar::handle:vertical {{ min-height: 28px; }}
    QScrollBar::handle:horizontal {{ min-width: 28px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    QMenuBar {{ background: {t.window}; color: {t.text}; padding: 2px 4px; }}
    QMenuBar::item {{ background: transparent; padding: 4px 10px; border-radius: 4px; }}
    QMenuBar::item:selected {{ background: {t.hover}; }}
    QMenu {{ background: {t.raised}; color: {t.text}; border: 1px solid {t.border}; padding: 4px; }}
    QMenu::item {{ padding: 6px 28px 6px 28px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {t.selected}; }}
    QMenu::item:disabled {{ color: {t.muted}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 8px; }}
    QMenu::indicator {{ width: 14px; height: 14px; left: 8px; }}
    QMenu::indicator:checked {{ image: url("{_tick(t, 'text')}"); }}

    QSplitter::handle {{ background: {t.border}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}

    QStatusBar {{ background: {t.window}; color: {t.text2}; border-top: 1px solid {t.border}; }}
    QStatusBar::item {{ border: none; }}
    QStatusBar QLabel {{ color: {t.text2}; padding: 0 6px; }}

    QProgressBar {{ background: {t.track}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
    QProgressBar::chunk {{ background: {t.text2}; border-radius: 3px; }}

    QToolTip {{ background: {t.raised}; color: {t.text}; border: 1px solid {t.border}; padding: 4px 6px; }}

    QPlainTextEdit {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; border-radius: 6px; }}
    QDialog, QMessageBox {{ background: {t.window}; }}

    QLineEdit {{
        background: {t.raised}; color: {t.text}; border: 1px solid {t.border}; border-radius: 6px;
        padding: 5px 8px; selection-background-color: {t.selected}; selection-color: {t.text};
    }}
    QLineEdit:focus {{ border-color: {t.text2}; }}
    QComboBox {{
        background: {t.raised}; color: {t.text}; border: 1px solid {t.border}; border-radius: 6px;
        padding: 4px 10px; min-height: 20px;
    }}
    QComboBox:hover {{ background: {t.hover}; }}
    QComboBox:disabled {{ color: {t.muted}; }}
    QComboBox QAbstractItemView {{
        background: {t.raised}; color: {t.text}; border: 1px solid {t.border}; outline: 0;
        selection-background-color: {t.selected}; selection-color: {t.text};
    }}
    QCheckBox {{ spacing: 7px; color: {t.text2}; }}
    QCheckBox:hover {{ color: {t.text}; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px; border: 1px solid {t.text2}; border-radius: 3px; background: {t.raised};
    }}
    QCheckBox::indicator:hover {{ border-color: {t.text}; }}
    QCheckBox::indicator:checked {{ background: {t.text}; border-color: {t.text}; image: url("{_tick(t, 'box')}"); }}
    QSlider::groove:horizontal {{ height: 4px; background: {t.track}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t.text2}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: {t.text}; }}
    QListView {{ background: {t.surface}; border: none; outline: 0; }}
    QToolButton[chip="true"] {{
        border: 1px solid {t.border}; border-radius: 14px; padding: 4px 12px 4px 9px; color: {t.text2};
    }}
    QToolButton[chip="true"]:hover {{ background: {t.hover}; color: {t.text}; }}
    QToolButton[chip="true"]:checked {{ background: {t.selected}; border-color: {t.text2}; color: {t.text}; }}
    QWidget#FilterBar {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}
    """
