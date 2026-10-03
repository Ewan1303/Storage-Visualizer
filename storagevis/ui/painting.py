"""Painting helpers shared by the custom widgets: colours, icons and the hover card."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap)

from .theme import Theme

INK_DARK = "#0b0b0b"
INK_LIGHT = "#ffffff"


# ------------------------------------------------------------------- colours

@lru_cache(maxsize=1024)
def qcolor(value: str) -> QColor:
    """A cached QColor for a hex string. Treat it as read-only; copy before changing it."""
    return QColor(value)


def with_alpha(value: str, alpha: float) -> QColor:
    colour = QColor(value)
    colour.setAlphaF(alpha)
    return colour


def blend(a: QColor, b: QColor, t: float) -> QColor:
    """``a`` moved ``t`` of the way towards ``b``."""
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(colour: QColor) -> float:
    return (0.2126 * _linear(colour.redF()) + 0.7152 * _linear(colour.greenF())
            + 0.0722 * _linear(colour.blueF()))


def contrast(a: QColor, b: QColor) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@lru_cache(maxsize=128)
def ink_for(fill: str) -> QColor:
    """Black or white, whichever reads better on ``fill``."""
    dark, light = qcolor(INK_DARK), qcolor(INK_LIGHT)
    background = qcolor(fill)
    return dark if contrast(background, dark) >= contrast(background, light) else light


# --------------------------------------------------------------------- icons

ICON_FONT = "Segoe MDL2 Assets"

# name: (Segoe MDL2 Assets glyph, fallback character)
GLYPHS = {
    "up": ("", "↑"),
    "refresh": ("", "↻"),
    "add": ("", "+"),
    "warning": ("", "⚠"),
}


def glyph_font(pixel_size: int) -> tuple[QFont, bool]:
    """The icon font at a size, and whether it is really available (else use the fallbacks)."""
    if _icon_font_available():
        font = QFont(ICON_FONT)
    else:
        font = QFont()
    font.setPixelSize(pixel_size)
    return font, _icon_font_available()


def glyph(name: str, available: bool) -> str:
    icon, fallback = GLYPHS[name]
    return icon if available else fallback


@lru_cache(maxsize=1)
def _icon_font_available() -> bool:
    return ICON_FONT in QFontDatabase.families()


def glyph_icon(name: str, colour: str, size: int = 16) -> QIcon:
    font, available = glyph_font(max(8, round(size * 0.8)))
    text = glyph(name, available)
    icon = QIcon()
    for scale in (1.0, 1.25, 1.5, 2.0):
        side = round(size * scale)
        pixmap = QPixmap(side, side)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(font)
        painter.setPen(qcolor(colour))
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def _scaled_icon(paint, size: int) -> QIcon:
    icon = QIcon()
    for scale in (1.0, 1.25, 1.5, 2.0):
        side = round(size * scale)
        pixmap = QPixmap(side, side)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint(painter, size)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def swatch_icon(colour: str, size: int = 14) -> QIcon:
    """A small rounded square: the identity key beside a file or type name."""
    def paint(p: QPainter, s: int) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(colour))
        inset = s * 0.15
        p.drawRoundedRect(QRectF(inset, inset, s - 2 * inset, s - 2 * inset), 2, 2)
    return _scaled_icon(paint, size)


def folder_icon(colour: str, size: int = 14) -> QIcon:
    def paint(p: QPainter, s: int) -> None:
        path = QPainterPath()
        u = s / 14.0
        path.moveTo(1.5 * u, 3 * u)
        path.lineTo(5.5 * u, 3 * u)
        path.lineTo(7 * u, 4.5 * u)
        path.lineTo(12.5 * u, 4.5 * u)
        path.lineTo(12.5 * u, 11.5 * u)
        path.lineTo(1.5 * u, 11.5 * u)
        path.closeSubpath()
        p.setPen(QPen(qcolor(colour), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
    return _scaled_icon(paint, size)


def _app_icon_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = size / 32.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(qcolor("#1a1a19"))
    p.drawRoundedRect(QRectF(0, 0, size, size), 7 * u, 7 * u)
    tiles = (
        ((3, 3, 15, 26), "#3987e5"),
        ((19, 3, 10, 14), "#c98500"),
        ((19, 18, 10, 6), "#d55181"),
        ((19, 25, 10, 4), "#008300"),
    )
    for (x, y, w, h), colour in tiles:
        p.setBrush(qcolor(colour))
        p.drawRoundedRect(QRectF(x * u, y * u, w * u, h * u), 1.5 * u, 1.5 * u)
    p.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(_app_icon_pixmap(size))
    return icon


# ---------------------------------------------------------------- hover card

@dataclass
class TipLine:
    """One line of the hover card.

    Roles: "value" (the size, strongest), "title", "detail", "path" (quietest),
    "key" (a short colour stroke and text) and "bar" (a stacked bar of ``parts``).
    """
    text: str
    role: str = "detail"
    extra: str = ""                 # quieter text after a "value"
    category: int | None = None     # "key": which category colour to show
    parts: Sequence[int] = field(default_factory=tuple)  # "bar": bytes per category


def paint_tooltip(p: QPainter, theme: Theme, anchor: QPoint, bounds: QRect,
                  lines: Sequence[TipLine], base: QFont) -> None:
    pad, spacing, max_width, min_width = 10, 4, 380, 170
    value_font = QFont(base)
    value_font.setPointSizeF(base.pointSizeF() + 2)
    value_font.setWeight(QFont.Weight.DemiBold)
    title_font = QFont(base)
    title_font.setWeight(QFont.Weight.DemiBold)
    fonts = {"value": value_font, "title": title_font}
    metrics = {role: QFontMetrics(fonts.get(role, base)) for role in ("value", "title", "detail")}
    base_metrics = metrics["detail"]

    rows: list[tuple[TipLine, int]] = []
    content = min_width
    for line in lines:
        if line.role == "bar":
            rows.append((line, 6))
            continue
        fm = metrics.get(line.role, base_metrics)
        width = fm.horizontalAdvance(line.text)
        if line.extra:
            width += 10 + base_metrics.horizontalAdvance(line.extra)
        if line.role == "key":
            width += 18
        content = max(content, min(width, max_width))
        rows.append((line, fm.height()))
    width = content + 2 * pad
    height = sum(h for _, h in rows) + spacing * (len(rows) - 1) + 2 * pad

    x, y = anchor.x() + 16, anchor.y() + 18
    if x + width > bounds.right() - 4:
        x = anchor.x() - width - 12
    if y + height > bounds.bottom() - 4:
        y = anchor.y() - height - 12
    x = max(bounds.left() + 4, x)
    y = max(bounds.top() + 4, y)

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(qcolor(theme.border), 1))
    p.setBrush(qcolor(theme.raised))
    p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, width, height), 6, 6)

    cy = y + pad
    left = x + pad
    for line, h in rows:
        if line.role == "bar":
            _paint_parts(p, theme, QRectF(left, cy, content, 6), line.parts)
            cy += h + spacing
            continue
        font = fonts.get(line.role, base)
        fm = metrics.get(line.role, base_metrics)
        p.setFont(font)
        text_left = left
        available = content
        if line.role == "key" and line.category is not None:
            p.setPen(QPen(qcolor(theme.categories[line.category]), 3, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            mid = cy + h / 2
            p.drawLine(QPointF(left + 1.5, mid), QPointF(left + 11.5, mid))
            text_left += 18
            available -= 18
        colour = {"value": theme.text, "title": theme.text, "path": theme.muted}.get(line.role, theme.text2)
        p.setPen(qcolor(colour))
        extra_width = base_metrics.horizontalAdvance(line.extra) + 10 if line.extra else 0
        text = fm.elidedText(line.text, Qt.TextElideMode.ElideMiddle if line.role == "path"
                             else Qt.TextElideMode.ElideRight, max(20, available - extra_width))
        baseline = cy + fm.ascent()
        p.drawText(QPointF(text_left, baseline), text)
        if line.extra:
            p.setFont(base)
            p.setPen(qcolor(theme.text2))
            extra_x = text_left + fm.horizontalAdvance(text) + 10
            p.drawText(QPointF(extra_x, baseline), base_metrics.elidedText(
                line.extra, Qt.TextElideMode.ElideRight, int(left + content - extra_x)))
        cy += h + spacing
    p.restore()


def _paint_parts(p: QPainter, theme: Theme, rect: QRectF, parts: Sequence[int]) -> None:
    """A thin stacked bar, one segment per category in fixed order, 2 px apart."""
    total = sum(parts)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(qcolor(theme.track))
    p.drawRoundedRect(rect, 2, 2)
    if total <= 0:
        return
    shown = [(i, v) for i, v in enumerate(parts) if v > 0 and v / total * rect.width() >= 1]
    gaps = 2 * (len(shown) - 1)
    usable = rect.width() - gaps
    x = rect.left()
    for n, (i, v) in enumerate(shown):
        w = usable * v / sum(val for _, val in shown)
        if n == len(shown) - 1:
            w = rect.right() - x
        p.setBrush(qcolor(theme.categories[i]))
        p.drawRoundedRect(QRectF(x, rect.top(), max(w, 1.0), rect.height()), 2, 2)
        x += w + 2
