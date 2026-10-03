"""The file-type key under the chart. Clicking a type highlights just those files."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..core.categories import CATEGORIES
from ..core.formatting import format_share, format_size
from .painting import blend, qcolor
from .state import ViewState
from .theme import ThemeManager

_CLEAR = -1  # chip index that clears an extension highlight


class Legend(QWidget):
    ROW_GAP = 4
    CHIP_GAP = 6

    def __init__(self, state: ViewState, themes: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.themes = themes
        self._note = ""
        self._hover: int | None = None
        self.setMouseTracking(True)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        for signal in (state.treeChanged, state.rootChanged, state.sizesChanged, state.emphasisChanged):
            signal.connect(self._changed)
        themes.changed.connect(self._changed)

    def set_note(self, text: str) -> None:
        self._note = text
        self._changed()

    def _changed(self, *_args) -> None:
        self.updateGeometry()
        self.update()

    # --------------------------------------------------------------- layout

    def _bold(self) -> QFont:
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def _chips(self, width: int) -> tuple[list[tuple[QRect, int, str, str]], QRect | None, int]:
        fm = self.fontMetrics()
        bold = QFontMetrics(self._bold())
        height = fm.height() + 10
        state = self.state
        values = [0] * len(CATEGORIES)
        if state.sizes is not None and state.root is not None:
            values = state.sizes.category_values(state.root)
        total = sum(values)

        chips: list[tuple[QRect, int, str, str]] = []
        x = y = 0
        emphasis = state.emphasis
        if emphasis is not None and emphasis[0] == "extension":
            label = f"Highlighting .{emphasis[1]} files" if emphasis[1] else "Highlighting files with no extension"
            w = bold.horizontalAdvance(label) + fm.horizontalAdvance("  ✕") + 20
            chips.append((QRect(0, 0, w, height), _CLEAR, label, "✕"))
            x = w + self.CHIP_GAP
        for category in CATEGORIES:
            v = values[category.index]
            value_text = f"{format_size(v)}  {format_share(v / total)}" if total else ""
            w = 10 + 8 + bold.horizontalAdvance(category.label) + 8 + fm.horizontalAdvance(value_text) + 16
            if x > 0 and x + w > width:
                x = 0
                y += height + self.ROW_GAP
            chips.append((QRect(x, y, w, height), category.index, category.label, value_text))
            x += w + self.CHIP_GAP
        note_rect = None
        if self._note:
            w = fm.horizontalAdvance(self._note) + 12
            if x > 0 and x + w > width:
                x = 0
                y += height + self.ROW_GAP
            note_rect = QRect(x, y, w, height)
        return chips, note_rect, y + height

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._chips(max(width, 200))[2]

    def sizeHint(self) -> QSize:
        width = self.width() if self.width() > 0 else 800
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        return QSize(200, self.fontMetrics().height() + 10)

    # ------------------------------------------------------------- painting

    def paintEvent(self, event) -> None:
        theme = self.themes.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = self.fontMetrics()
        bold_font = self._bold()
        chips, note_rect, _ = self._chips(self.width())
        emphasis = self.state.emphasis
        for rect, index, label, value_text in chips:
            active = emphasis == ("category", index)
            faded = emphasis is not None and not active and index != _CLEAR
            if active or index == _CLEAR:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qcolor(theme.selected))
                p.drawRoundedRect(QRectF(rect), 6, 6)
            elif self._hover == index:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qcolor(theme.hover))
                p.drawRoundedRect(QRectF(rect), 6, 6)
            baseline = rect.top() + (rect.height() - fm.height()) // 2 + fm.ascent()
            x = rect.left() + 8
            if index != _CLEAR:
                colour = qcolor(theme.categories[index])
                if faded:
                    colour = blend(colour, qcolor(theme.surface), 0.7)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(colour)
                p.drawRoundedRect(QRectF(x, rect.center().y() - 5 + 0.5, 10, 10), 2, 2)
                x += 18
            p.setFont(bold_font)
            p.setPen(qcolor(theme.muted if faded else theme.text))
            p.drawText(x, baseline, label)
            x += QFontMetrics(bold_font).horizontalAdvance(label) + 8
            p.setFont(self.font())
            p.setPen(qcolor(theme.muted if faded else theme.text2))
            p.drawText(x, baseline, value_text)
        if note_rect is not None:
            p.setFont(self.font())
            p.setPen(qcolor(theme.muted))
            p.drawText(note_rect.adjusted(4, 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), self._note)

    # ---------------------------------------------------------------- mouse

    def _index_at(self, pos: QPoint) -> int | None:
        for rect, index, _, _ in self._chips(self.width())[0]:
            if rect.contains(pos):
                return index
        return None

    def mouseMoveEvent(self, event) -> None:
        index = self._index_at(event.position().toPoint())
        if index != self._hover:
            self._hover = index
            self.setCursor(Qt.CursorShape.PointingHandCursor if index is not None else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.unsetCursor()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._index_at(event.position().toPoint())
        if index == _CLEAR:
            self.state.set_emphasis(None)
        elif index is not None:
            self.state.toggle_emphasis(("category", index))
