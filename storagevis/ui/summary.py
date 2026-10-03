"""The line above the chart: what is being viewed, how big it is, and how full the drive is."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..core.formatting import format_count, format_share, format_size
from ..core.system import drive_of
from .painting import qcolor
from .state import ViewState
from .theme import ThemeManager
from .widgets import labelled


class DriveMeter(QWidget):
    """How full the scanned drive is: this scan, everything else, and free space."""

    def __init__(self, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.themes = themes
        self._drive = ""
        self._disk: tuple[int, int, int] | None = None
        self._scanned = 0
        self.setFixedWidth(330)
        themes.changed.connect(self.update)

    def set_disk(self, drive: str, disk: tuple[int, int, int] | None, scanned: int) -> None:
        self._drive, self._disk, self._scanned = drive, disk, scanned
        self.setVisible(disk is not None and disk[0] > 0)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(330, self.fontMetrics().height() * 2 + 20)

    def paintEvent(self, event) -> None:
        if self._disk is None:
            return
        theme = self.themes.theme
        total, used, free = self._disk
        scanned = min(self._scanned, used)
        other = max(used - scanned, 0)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = self.fontMetrics()
        width = self.width()

        heading = f"{self._drive}  {format_size(free)} free of {format_size(total)}"
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        p.setFont(bold)
        p.setPen(qcolor(theme.text))
        p.drawText(0, fm.ascent(), heading)

        bar = QRectF(0, fm.height() + 5, width, 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(theme.track))
        p.drawRoundedRect(bar, 3, 3)
        x = bar.left()
        for part, colour in ((scanned, theme.text2), (other, theme.muted)):
            w = bar.width() * part / total if total else 0
            if w >= 1:
                p.setBrush(qcolor(colour))
                p.drawRoundedRect(QRectF(x, bar.top(), w, bar.height()), 3, 3)
                x += w + 2  # 2 px of surface between parts

        p.setFont(self.font())
        top = bar.bottom() + 6
        x = 0.0
        for label, colour in ((f"This scan {format_size(scanned)}", theme.text2),
                              (f"Other {format_size(other)}", theme.muted),
                              (f"Free {format_share(free / total) if total else ''}", theme.track)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qcolor(colour))
            p.drawRoundedRect(QRectF(x, top + (fm.height() - 8) / 2, 8, 8), 2, 2)
            p.setPen(qcolor(theme.text2))
            p.drawText(int(x + 12), int(top + fm.ascent()), label)
            x += 12 + fm.horizontalAdvance(label) + 14

    def minimumSizeHint(self) -> QSize:
        return QSize(330, self.fontMetrics().height() * 2 + 20)


class SummaryBar(QWidget):
    def __init__(self, state: ViewState, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.title = labelled("", "title", elide=Qt.TextElideMode.ElideMiddle)
        self.stats = labelled("", "secondary", elide=Qt.TextElideMode.ElideRight)
        self.meter = DriveMeter(themes)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        text.addWidget(self.title)
        text.addWidget(self.stats)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 10)
        row.setSpacing(24)
        row.addLayout(text, 1)
        row.addWidget(self.meter, 0, Qt.AlignmentFlag.AlignVCenter)

        for signal in (state.treeChanged, state.rootChanged, state.sizesChanged):
            signal.connect(self.refresh)

    def refresh(self) -> None:
        state = self.state
        tree, root, sizes = state.tree, state.root, state.sizes
        if tree is None or root is None:
            self.title.setFullText("")
            self.stats.setFullText("")
            self.meter.set_disk("", None, 0)
            return
        self.title.setFullText(tree.display_name(root))
        value = sizes.value(root)
        parts = [format_size(value), format_count(root.files, "file"), format_count(root.dirs, "folder")]
        if root.cloud and not state.include_cloud:
            parts.append(f"plus {format_size(root.cloud)} online-only")
        if root is not tree.root and sizes.value(tree.root):
            parts.append(f"{format_share(value / sizes.value(tree.root))} of the scan")
        if root.error and not root.children:
            parts = [f"This folder couldn't be read: {root.error}"]
        self.stats.setFullText("  ·  ".join(parts))
        drive = drive_of(tree.root_path).rstrip("\\/") or tree.root_path
        self.meter.set_disk(drive, tree.disk, tree.root.size)
