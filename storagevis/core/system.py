"""Operating-system helpers: drives, special folders, long paths and the shell.

Everything Windows-specific lives here so the rest of the core stays portable.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

IS_WINDOWS = os.name == "nt"

_LONG_PREFIX = "\\\\?\\"
_UNC_PREFIX = "\\\\?\\UNC\\"


def to_fs_path(path: str) -> str:
    """Absolute path in the form used for filesystem calls.

    On Windows this adds the ``\\\\?\\`` prefix, so folders nested deeper than the
    old 260-character limit (common inside node_modules) can still be read.
    """
    if not IS_WINDOWS:
        return os.path.abspath(path)
    if path.startswith(_LONG_PREFIX):
        return path
    path = os.path.abspath(path)
    if path.startswith("\\\\"):
        return _UNC_PREFIX + path[2:]
    return _LONG_PREFIX + path


def to_display_path(path: str) -> str:
    """Undo :func:`to_fs_path` for showing a path to people."""
    if path.startswith(_UNC_PREFIX):
        return "\\\\" + path[len(_UNC_PREFIX):]
    if path.startswith(_LONG_PREFIX):
        return path[len(_LONG_PREFIX):]
    return path


def drive_of(path: str) -> str:
    """'C:\\Users\\me' -> 'C:\\'; UNC paths give their share root."""
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    return drive + os.sep if drive else os.sep


def is_drive_root(path: str) -> bool:
    return os.path.abspath(path) == drive_of(path)


def disk_usage(path: str) -> tuple[int, int, int] | None:
    """(total, used, free) bytes of the volume holding ``path``, or None."""
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return usage.total, usage.used, usage.free


# --------------------------------------------------------------------------- drives

_DRIVE_KINDS = {2: "removable", 3: "fixed", 4: "network", 5: "cdrom", 6: "ram"}
_DEFAULT_LABELS = {
    "fixed": "Local Disk",
    "removable": "USB Drive",
    "network": "Network Drive",
    "cdrom": "CD Drive",
    "ram": "RAM Disk",
}
_SEM_FAILCRITICALERRORS = 0x0001


@dataclass(frozen=True)
class DriveInfo:
    root: str
    label: str
    kind: str
    total: int | None = None
    free: int | None = None

    @property
    def used(self) -> int | None:
        if self.total is None or self.free is None:
            return None
        return self.total - self.free

    @property
    def title(self) -> str:
        """'Local Disk (C:)', like Explorer shows it."""
        letter = self.root.rstrip("\\/") or self.root
        name = self.label or _DEFAULT_LABELS.get(self.kind, "Drive")
        return f"{name} ({letter})" if IS_WINDOWS else name


def list_drives() -> list[DriveInfo]:
    if not IS_WINDOWS:
        usage = disk_usage("/")
        if usage:
            return [DriveInfo("/", "File system", "fixed", usage[0], usage[2])]
        return [DriveInfo("/", "File system", "fixed")]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetDriveTypeW.restype = ctypes.c_uint
    kernel32.SetThreadErrorMode.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
    kernel32.SetThreadErrorMode.restype = ctypes.c_int

    # Without this an empty card reader can pop up "There is no disk in the drive".
    old_mode = ctypes.c_uint()
    kernel32.SetThreadErrorMode(_SEM_FAILCRITICALERRORS, ctypes.byref(old_mode))
    try:
        drives = []
        for root in os.listdrives():
            kind = _DRIVE_KINDS.get(kernel32.GetDriveTypeW(root), "unknown")
            if kind in ("removable", "cdrom") and not os.path.isdir(root):
                continue  # an empty card reader or disc drive: nothing to scan
            local = kind in ("fixed", "removable", "ram", "cdrom")
            label = _volume_label(kernel32, root) if local else ""
            usage = disk_usage(root) if local else None
            if usage:
                drives.append(DriveInfo(root, label, kind, usage[0], usage[2]))
            else:
                drives.append(DriveInfo(root, label, kind))
        return drives
    finally:
        kernel32.SetThreadErrorMode(old_mode.value, None)


def _volume_label(kernel32, root: str) -> str:
    fn = kernel32.GetVolumeInformationW
    fn.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    buffer = ctypes.create_unicode_buffer(261)
    if fn(root, buffer, len(buffer), None, None, None, None, 0):
        return buffer.value
    return ""


# ------------------------------------------------------------------ special folders

_KNOWN_FOLDERS = (
    ("Desktop", "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"),
    ("Documents", "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"),
    ("Downloads", "{374DE290-123F-4565-9164-39C4925E467B}"),
    ("Pictures", "{33E28130-4E1E-4676-835A-98395C3BC3BB}"),
    ("Videos", "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}"),
    ("Music", "{4BD8D571-6D19-48D3-BE97-422220080E43}"),
)


def special_folders() -> list[tuple[str, str]]:
    """[(label, path)] for Home, Desktop, Documents, ... that exist on this PC.

    Windows is asked where each one really is, because OneDrive often moves
    Documents and Desktop out of the home folder.
    """
    folders = [("Home", str(Path.home()))]
    for label, guid in _KNOWN_FOLDERS:
        path = _known_folder(guid) if IS_WINDOWS else None
        if not path:
            path = str(Path.home() / label)
        if os.path.isdir(path) and all(os.path.normcase(path) != os.path.normcase(p) for _, p in folders):
            folders.append((label, path))
    return folders


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _known_folder(guid_text: str) -> str | None:
    try:
        shell32 = ctypes.WinDLL("shell32")
        ole32 = ctypes.WinDLL("ole32")
    except OSError:
        return None
    get_path = shell32.SHGetKnownFolderPath
    get_path.argtypes = [ctypes.POINTER(_GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    get_path.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

    guid = _GUID()
    ctypes.memmove(ctypes.byref(guid), uuid.UUID(guid_text).bytes_le, ctypes.sizeof(guid))
    buffer = ctypes.c_void_p()
    result = get_path(ctypes.byref(guid), 0, None, ctypes.byref(buffer))
    try:
        if result != 0 or not buffer.value:
            return None
        return ctypes.wstring_at(buffer.value)
    finally:
        ole32.CoTaskMemFree(buffer)  # required whether or not the call succeeded


# ---------------------------------------------------------------------------- shell

def open_path(path: str) -> None:
    """Open a file with its default app, or a folder in the file manager."""
    if IS_WINDOWS:
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_in_file_manager(path: str) -> None:
    """Open the containing folder with ``path`` selected."""
    if IS_WINDOWS:
        if is_drive_root(path):
            os.startfile(path)
        else:
            subprocess.Popen(f'explorer /select,"{path}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) or path])
