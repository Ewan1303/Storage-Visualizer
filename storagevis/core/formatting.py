"""Human-friendly numbers: sizes, counts, shares and durations."""

from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB", "EB")


def format_size(n: int) -> str:
    """Bytes the way Windows Explorer counts them (1 KB = 1024 bytes), to 3 significant figures."""
    if n < 1000:
        return f"{n} B"
    value = float(n)
    unit = 0
    # 999.5 rather than 1024 so that rounding never shows "1000 KB" or "1024 KB".
    while value >= 999.5 and unit < len(_UNITS) - 1:
        value /= 1024.0
        unit += 1
    if value >= 99.95:
        text = f"{value:.0f}"
    elif value >= 9.995:
        text = f"{value:.1f}"
    else:
        text = f"{value:.2f}"
    return f"{text} {_UNITS[unit]}"


def format_count(n: int, singular: str | None = None, plural: str | None = None) -> str:
    """12345 -> '12,345'; with a noun: '1 file', '12,345 files'."""
    text = f"{n:,}"
    if singular is None:
        return text
    word = singular if n == 1 else (plural or singular + "s")
    return f"{text} {word}"


def format_share(fraction: float) -> str:
    """0.4567 -> '45.7%'. Tiny non-zero shares read '<0.1%' rather than '0%'."""
    if fraction <= 0:
        return "0%"
    percent = fraction * 100.0
    if percent < 0.1:
        return "<0.1%"
    text = f"{percent:.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return text + "%"


def format_duration(seconds: float) -> str:
    if seconds < 10:
        return f"{seconds:.1f} s"
    if seconds < 59.5:
        return f"{seconds:.0f} s"
    minutes, secs = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes} min {secs:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"
