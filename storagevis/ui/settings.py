"""Remembers the window, the chosen view and the theme between runs.

Settings go in ``settings.ini`` next to the app (not the registry), so the app
keeps everything in its own folder. Set STORAGE_VISUALIZER_SETTINGS to use
another file.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings


def default_settings_path() -> Path:
    override = os.environ.get("STORAGE_VISUALIZER_SETTINGS")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "settings.ini"


class Settings:
    """A thin wrapper over an INI file. With no path, values only live in memory (tests)."""

    def __init__(self, path: str | os.PathLike | None) -> None:
        self._store = QSettings(str(path), QSettings.Format.IniFormat) if path is not None else None
        self._memory: dict[str, object] = {}

    def get(self, key: str, default):
        if self._store is None:
            return self._memory.get(key, default)
        if isinstance(default, bool):
            return self._store.value(key, default, type=bool)
        if isinstance(default, int):
            return self._store.value(key, default, type=int)
        value = self._store.value(key, default)
        return default if value is None else value

    def get_bytes(self, key: str) -> QByteArray | None:
        value = self._memory.get(key) if self._store is None else self._store.value(key)
        return value if isinstance(value, QByteArray) and not value.isEmpty() else None

    def set(self, key: str, value) -> None:
        if self._store is None:
            self._memory[key] = value
        else:
            self._store.setValue(key, value)

    def sync(self) -> None:
        if self._store is not None:
            self._store.sync()
