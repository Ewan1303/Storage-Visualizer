"""The start page (pick a drive or folder) and the page shown while a scan runs."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QGridLayout, QHBoxLayout, QProgressBar, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from .. import APP_NAME
from ..core.formatting import format_count, format_duration, format_size
from ..core.scanner import ScanProgress
from ..core.system import DriveInfo, list_drives, special_folders
from .painting import folder_icon, glyph, glyph_font, qcolor
from .theme import STATUS_CRITICAL, STATUS_WARNING, ThemeManager
from .widgets import labelled


class DriveCard(QAbstractButton):
    """A drive with a fill bar. Clicking it scans the whole drive."""

    def __init__(self, drive: DriveInfo, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.drive = drive
        self.themes = themes
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedSize(QSize(256, 92))
        self.setToolTip(f"Scan everything on {drive.root}")
        self.setAccessibleName(f"Scan {drive.title}")
        themes.changed.connect(self.update)

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        theme = self.themes.theme
        drive = self.drive
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hovered = self.underMouse() or self.isDown()
        outline = theme.text2 if self.hasFocus() else theme.border
        p.setPen(QPen(qcolor(outline), 1))
        p.setBrush(qcolor(theme.hover if hovered else theme.surface))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        fm = self.fontMetrics()
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        p.setFont(bold)
        p.setPen(qcolor(theme.text))
        title = fm.elidedText(drive.title, Qt.TextElideMode.ElideRight, self.width() - 32)
        p.drawText(16, 14 + fm.ascent(), title)

        bar = QRectF(16, 44, self.width() - 32, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(theme.track))
        p.drawRoundedRect(bar, 3, 3)
        status = self.status()
        x = 16
        if drive.total:
            used = (drive.used or 0) / drive.total
            p.setBrush(qcolor(status[1] if status else theme.text2))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(3.0, bar.width() * used), bar.height()), 3, 3)
            caption = f"{format_size(drive.free)} free of {format_size(drive.total)}"
            if status:
                font, available = glyph_font(fm.height() - 2)
                p.setFont(font)
                p.setPen(qcolor(status[1]))
                p.drawText(QRectF(x, 60, fm.height(), fm.height()), Qt.AlignmentFlag.AlignCenter,
                           glyph("warning", available))
                x += fm.height() + 4
                caption = f"{status[0]}  ·  {caption}"
        else:
            caption = "Network drive" if drive.kind == "network" else "Size unknown"
        p.setFont(self.font())
        p.setPen(qcolor(theme.text2))
        p.drawText(x, 60 + fm.ascent(), fm.elidedText(caption, Qt.TextElideMode.ElideRight, self.width() - x - 12))

    def status(self) -> tuple[str, str] | None:
        """('Almost full', colour) when the drive is short of space, else None."""
        drive = self.drive
        if not drive.total or drive.free is None:
            return None
        free = drive.free / drive.total
        if free < 0.05:
            return "Almost full", STATUS_CRITICAL
        if free < 0.10:
            return "Getting full", STATUS_WARNING
        return None


class StartPage(QWidget):
    scanRequested = Signal(str)
    browseRequested = Signal()
    resumeRequested = Signal()

    DRIVES_PER_ROW = 3
    FOLDERS_PER_ROW = 4

    def __init__(self, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.themes = themes
        column = QWidget()
        column.setMaximumWidth(4 + self.DRIVES_PER_ROW * 268)
        column.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(labelled(APP_NAME, "hero"))
        col.addSpacing(4)
        col.addWidget(labelled("See what is taking up space. Pick a drive or a folder to scan.", "secondary"))
        col.addSpacing(28)
        col.addWidget(labelled("DRIVES", "section"))
        col.addSpacing(8)
        self._drives = QGridLayout()
        self._drives.setSpacing(12)
        self._drives.setContentsMargins(0, 0, 0, 0)
        self._drives.setColumnStretch(self.DRIVES_PER_ROW, 1)  # pack cards to the left
        col.addLayout(self._drives)
        col.addSpacing(28)
        col.addWidget(labelled("FOLDERS", "section"))
        col.addSpacing(8)
        self._folders = QGridLayout()
        self._folders.setHorizontalSpacing(8)
        self._folders.setVerticalSpacing(8)
        self._folders.setContentsMargins(0, 0, 0, 0)
        for index in range(self.FOLDERS_PER_ROW):
            self._folders.setColumnMinimumWidth(index, 150)
        self._folders.setColumnStretch(self.FOLDERS_PER_ROW, 1)
        col.addLayout(self._folders)
        col.addSpacing(24)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.browse_button = QPushButton("Choose a folder…")
        self.browse_button.setProperty("primary", True)
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.clicked.connect(self.browseRequested)
        self.resume_button = QPushButton("Back to results")
        self.resume_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume_button.clicked.connect(self.resumeRequested)
        buttons.addWidget(self.browse_button)
        buttons.addWidget(self.resume_button)
        buttons.addStretch(1)
        col.addLayout(buttons)
        col.addSpacing(14)
        col.addWidget(labelled("You can also drop a folder onto this window, or press Ctrl+O.", "muted"))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 32, 32, 32)
        outer.addStretch(1)
        outer.addWidget(column, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(2)
        themes.changed.connect(self._restyle)

    def _restyle(self, _theme=None) -> None:
        icon = folder_icon(self.themes.theme.text2)
        for i in range(self._folders.count()):
            widget = self._folders.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setIcon(icon)

    @staticmethod
    def _clear(grid: QGridLayout) -> None:
        while grid.count():
            widget = grid.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def refresh(self, has_results: bool) -> None:
        self._clear(self._drives)
        for i, drive in enumerate(list_drives()):
            card = DriveCard(drive, self.themes)
            card.clicked.connect(lambda _checked=False, root=drive.root: self.scanRequested.emit(root))
            self._drives.addWidget(card, i // self.DRIVES_PER_ROW, i % self.DRIVES_PER_ROW)
        self._clear(self._folders)
        for i, (label, path) in enumerate(special_folders()):
            button = QPushButton(label)
            button.setToolTip(path)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, p=path: self.scanRequested.emit(p))
            self._folders.addWidget(button, i // self.FOLDERS_PER_ROW, i % self.FOLDERS_PER_ROW)
        self._restyle()
        self.resume_button.setVisible(has_results)


class ScanPage(QWidget):
    stopRequested = Signal()    # stop and show what was found so far
    cancelRequested = Signal()  # stop and throw the results away

    def __init__(self, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expected: int | None = None

        card = QWidget()
        card.setObjectName("ScanCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        card.setFixedWidth(640)
        v = QVBoxLayout(card)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(6)
        self.caption = labelled("SCANNING", "section")
        self.path = labelled("", "title", elide=Qt.TextElideMode.ElideMiddle)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        v.addWidget(self.caption)
        v.addWidget(self.path)
        v.addSpacing(10)
        v.addWidget(self.bar)
        v.addSpacing(16)

        stats = QGridLayout()
        stats.setHorizontalSpacing(28)
        stats.setVerticalSpacing(0)
        self.values: dict[str, object] = {}
        for column, key in enumerate(("Files", "Folders", "Found", "Time")):
            value = labelled("0", "stat")
            stats.addWidget(value, 0, column)
            stats.addWidget(labelled(key, "muted"), 1, column)
            self.values[key] = value
        stats.setColumnStretch(4, 1)
        v.addLayout(stats)
        v.addSpacing(14)
        self.current = labelled("", "muted", elide=Qt.TextElideMode.ElideMiddle)
        v.addWidget(self.current)
        v.addSpacing(14)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.stop_button = QPushButton("Stop and show results")
        self.stop_button.clicked.connect(self.stopRequested)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancelRequested)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        v.addLayout(buttons)

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(2)

    def begin(self, path: str, expected_bytes: int | None) -> None:
        """``expected_bytes`` (used space, when a whole drive is scanned) makes the bar measurable."""
        self._expected = expected_bytes if expected_bytes else None
        self.caption.setText("SCANNING")
        self.path.setFullText(path)
        if self._expected:
            self.bar.setRange(0, 1000)
            self.bar.setValue(0)
        else:
            self.bar.setRange(0, 0)  # busy: no way to know how much is left in a folder
        for value in self.values.values():
            value.setText("0")
        self.current.setFullText("")
        self.stop_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

    def show_progress(self, progress: ScanProgress) -> None:
        self.values["Files"].setText(format_count(progress.files))
        self.values["Folders"].setText(format_count(progress.folders))
        self.values["Found"].setText(format_size(progress.bytes))
        self.values["Time"].setText(format_duration(progress.elapsed))
        self.current.setFullText(progress.current)
        if self._expected:
            self.bar.setValue(min(990, int(progress.bytes * 1000 / self._expected)))

    def set_stopping(self) -> None:
        self.caption.setText("STOPPING…")
        self.stop_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
