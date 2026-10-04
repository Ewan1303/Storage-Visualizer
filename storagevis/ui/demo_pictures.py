"""Pictures for the made-up demo drive, drawn on the fly (its files do not exist).

Landscapes stand in for photos and videos, simple covers for music, so the
file type viewer looks as it does with real files in --demo mode and in the
README screenshots, without showing anybody's real pictures.
"""

from __future__ import annotations

import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient

from ..core.categories import Kind, extension_of, kind_of_extension

_SKIES = (  # (top of the sky, horizon)
    ("#ffb38a", "#7b6fd0"),
    ("#4f9be8", "#dff0ff"),
    ("#2b2d6e", "#ff8a65"),
    ("#0b1033", "#3a4c86"),
    ("#ffd59a", "#ff8c5a"),
    ("#8fcfe0", "#f6e7c8"),
)
_LANDS = ("#2f5d50", "#4b6b3a", "#5a4a6e", "#3d4f7a", "#6b5040", "#2e4a5c")
_COVERS = ("#e85d75", "#3f88c5", "#f2a541", "#2fbf71", "#8e6bd8", "#e4572e", "#1b998b")


def demo_picture(path: str, size: int) -> QImage | None:
    name = path.replace("/", "\\").rsplit("\\", 1)[-1]
    kind = kind_of_extension(extension_of(name))
    rng = random.Random(name)
    if kind == Kind.PHOTOS:
        across, down = rng.choice(((4, 3), (4, 3), (3, 2), (3, 4)))
        return _landscape(rng, size, across, down)
    if kind == Kind.VIDEOS:
        return _landscape(rng, size, 16, 9)
    if kind == Kind.MUSIC:
        return _cover(rng, size)
    return None


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def _landscape(rng: random.Random, size: int, across: int, down: int) -> QImage:
    if across >= down:
        width, height = size, round(size * down / across)
    else:
        width, height = round(size * across / down), size
    image = QImage(width, height, QImage.Format.Format_RGB32)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    top, horizon = (QColor(c) for c in rng.choice(_SKIES))
    sky = QLinearGradient(0, 0, 0, height)
    sky.setColorAt(0, top)
    sky.setColorAt(0.7, horizon)
    p.fillRect(image.rect(), sky)

    sun = QPointF(rng.uniform(0.2, 0.8) * width, rng.uniform(0.15, 0.45) * height)
    radius = rng.uniform(0.06, 0.12) * min(width, height)
    glow = QRadialGradient(sun, radius * 3.2)
    glow.setColorAt(0, QColor(255, 244, 214, 150))
    glow.setColorAt(1, QColor(255, 244, 214, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(sun, radius * 3.2, radius * 3.2)
    p.setBrush(QColor("#fff4d6"))
    p.drawEllipse(sun, radius, radius)

    land = QColor(rng.choice(_LANDS))
    water = rng.random() < 0.35
    for layer in range(3):  # far hills are paler, like haze
        base = height * (0.52 + 0.12 * layer)
        p.setBrush(_mix(land, horizon, 0.55 - 0.27 * layer))
        path = QPainterPath(QPointF(0, height))
        path.lineTo(0, base)
        steps = rng.randint(3, 6)
        for step in range(1, steps + 1):
            x = width * step / steps
            peak = QPointF(x - width / steps / 2, base - rng.uniform(0.05, 0.25) * height * (1 - 0.3 * layer))
            point = QPointF(x, base - rng.uniform(0.0, 0.06) * height)
            if layer == 0:
                path.lineTo(peak)  # sharp mountains far away
                path.lineTo(point)
            else:
                path.quadTo(peak, point)  # rounded hills closer in
        path.lineTo(width, height)
        path.closeSubpath()
        p.drawPath(path)
        if water and layer == 1:
            break
    if water:
        lake = QLinearGradient(0, height * 0.72, 0, height)
        lake.setColorAt(0, _mix(horizon, top, 0.3))
        lake.setColorAt(1, top.darker(140))
        p.fillRect(0, round(height * 0.72), width, height, lake)
        p.setBrush(QColor(255, 244, 214, 90))
        p.drawRect(round(sun.x() - radius * 0.6), round(height * 0.74), round(radius * 1.2), round(height * 0.2))
    p.end()
    return image


def _cover(rng: random.Random, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_RGB32)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    main = QColor(rng.choice(_COVERS))
    accent = QColor(rng.choice(_COVERS))
    p.fillRect(image.rect(), main.darker(170))
    p.setPen(Qt.PenStyle.NoPen)
    centre = QPointF(size * rng.uniform(0.35, 0.65), size * rng.uniform(0.35, 0.65))
    style = rng.randrange(3)
    if style == 0:
        for ring in range(6, 0, -1):
            p.setBrush(main if ring % 2 else accent)
            p.drawEllipse(centre, size * 0.08 * ring, size * 0.08 * ring)
    elif style == 1:
        p.setBrush(accent)
        for stripe in range(-size, size * 2, max(8, size // 8)):
            path = QPainterPath(QPointF(stripe, 0))
            path.lineTo(stripe + size * 0.06, 0)
            path.lineTo(stripe + size * 0.06 - size, size)
            path.lineTo(stripe - size, size)
            path.closeSubpath()
            p.drawPath(path)
        p.setBrush(main)
        p.drawEllipse(centre, size * 0.22, size * 0.22)
    else:
        p.setBrush(main)
        p.drawEllipse(centre, size * 0.38, size * 0.38)
        p.setBrush(accent)
        p.drawEllipse(QPointF(centre.x() + size * 0.18, centre.y() - size * 0.14), size * 0.12, size * 0.12)
    p.end()
    return image
