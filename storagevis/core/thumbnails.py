"""File thumbnails from the Windows shell: the same pictures Explorer shows.

That covers photos (including HEIC or RAW when Windows has the codec), frames
from videos, album art and document previews. The result is plain pixels, so
the core stays free of Qt.

Each thread that asks needs COM, which is switched on the first time that
thread calls :func:`shell_thumbnail`. Run this off the UI thread: video
thumbnails can take a moment.
"""

from __future__ import annotations

import ctypes
import os
import threading
import uuid
from typing import NamedTuple

IS_WINDOWS = os.name == "nt"


class Thumbnail(NamedTuple):
    width: int
    height: int
    pixels: bytes      # 32-bit BGRA, rows top to bottom
    has_alpha: bool    # False when every alpha byte is 0 (plain photos come back like that)


# IShellItemImageFactory::GetImage flags (SIIGBF_*)
RESIZE_TO_FIT = 0x00
ICON_ONLY = 0x04
IN_CACHE_ONLY = 0x10

_COINIT_APARTMENTTHREADED = 0x2
_COINIT_DISABLE_OLE1DDE = 0x4
_DIB_RGB_COLORS = 0


def shell_thumbnail(path: str, size: int, *, cached_only: bool = False) -> Thumbnail | None:
    """A thumbnail no bigger than ``size`` pixels a side, or None.

    With ``cached_only`` (used for online-only OneDrive files) nothing is
    downloaded: Windows' thumbnail cache is used if it has the picture,
    otherwise the file type's icon.
    """
    if not IS_WINDOWS or _api is None:
        return None
    _api.ensure_com()
    bitmap = _api.get_image(path, size, IN_CACHE_ONLY if cached_only else RESIZE_TO_FIT)
    if bitmap is None and cached_only:
        bitmap = _api.get_image(path, size, ICON_ONLY)
    if bitmap is None:
        return None
    try:
        return _api.read_bitmap(bitmap)
    finally:
        _api.gdi32.DeleteObject(bitmap)


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> _GUID:
        guid = cls()
        ctypes.memmove(ctypes.byref(guid), uuid.UUID(text).bytes_le, ctypes.sizeof(guid))
        return guid


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long), ("bmPlanes", ctypes.c_ushort),
                ("bmBitsPixel", ctypes.c_ushort), ("bmBits", ctypes.c_void_p)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", ctypes.c_ushort), ("biBitCount", ctypes.c_ushort),
                ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_long), ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


# IShellItemImageFactory: IUnknown's three methods, then GetImage.
_GET_IMAGE = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, _SIZE, ctypes.c_int,
                                ctypes.POINTER(ctypes.c_void_p))
_RELEASE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)


class _ShellApi:
    """The handful of Windows calls needed, with their argument types declared once."""

    def __init__(self) -> None:
        self.shell32 = ctypes.WinDLL("shell32")
        self.ole32 = ctypes.WinDLL("ole32")
        self.gdi32 = ctypes.WinDLL("gdi32")
        self.user32 = ctypes.WinDLL("user32")
        self.iid_image_factory = _GUID.parse("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")
        self._local = threading.local()

        self.shell32.SHCreateItemFromParsingName.argtypes = [
            ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        self.shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
        self.ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.ole32.CoInitializeEx.restype = ctypes.c_long
        self.gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self.gdi32.GetObjectW.restype = ctypes.c_int
        self.gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
        self.gdi32.GetDIBits.restype = ctypes.c_int
        self.gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        self.gdi32.DeleteObject.restype = ctypes.c_int
        self.user32.GetDC.argtypes = [ctypes.c_void_p]
        self.user32.GetDC.restype = ctypes.c_void_p
        self.user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.user32.ReleaseDC.restype = ctypes.c_int

    def ensure_com(self) -> None:
        if not getattr(self._local, "com", False):
            # S_OK, or S_FALSE when this thread already had COM (Qt's UI thread does).
            self.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED | _COINIT_DISABLE_OLE1DDE)
            self._local.com = True

    def get_image(self, path: str, size: int, flags: int) -> int | None:
        factory = ctypes.c_void_p()
        result = self.shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(self.iid_image_factory),
                                                          ctypes.byref(factory))
        if result != 0 or not factory.value:
            return None
        vtable = ctypes.cast(factory, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        try:
            bitmap = ctypes.c_void_p()
            result = _GET_IMAGE(vtable[3])(factory, _SIZE(size, size), flags, ctypes.byref(bitmap))
            return bitmap.value if result == 0 and bitmap.value else None
        finally:
            _RELEASE(vtable[2])(factory)

    def read_bitmap(self, bitmap: int) -> Thumbnail | None:
        info = _BITMAP()
        if not self.gdi32.GetObjectW(bitmap, ctypes.sizeof(info), ctypes.byref(info)):
            return None
        width, height = info.bmWidth, abs(info.bmHeight)
        if width <= 0 or height <= 0:
            return None
        # A negative height asks for rows top to bottom, the order Qt expects.
        header = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        pixels = ctypes.create_string_buffer(width * height * 4)
        screen = self.user32.GetDC(None)
        try:
            rows = self.gdi32.GetDIBits(screen, bitmap, 0, height, pixels, ctypes.byref(header), _DIB_RGB_COLORS)
        finally:
            self.user32.ReleaseDC(None, screen)
        if rows != height:
            return None
        data = pixels.raw
        return Thumbnail(width, height, data, max(data[3::4]) > 0)


_api: _ShellApi | None = None
if IS_WINDOWS:
    try:
        _api = _ShellApi()
    except (OSError, AttributeError):  # a stripped-down Windows without the shell
        _api = None
