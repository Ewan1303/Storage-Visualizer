"""What kind of file something is, judged by its extension.

Two levels:

* **Kinds** (photos, videos, music, documents, archives, programs, other) are
  what the file type viewer lets you pick from.
* **Categories** group kinds into the four colours used by the charts, plus
  "Other". In a treemap any two file types can end up side by side, and four
  hues is the most that stay easy to tell apart from one another for
  colour-blind viewers too (the colours themselves, and how they were checked,
  live in ``storagevis.ui.theme``).
"""

from __future__ import annotations

from enum import IntEnum
from typing import NamedTuple


class Category(NamedTuple):
    index: int
    key: str
    label: str


MEDIA, IMAGES, PROGRAMS, DOCUMENTS, OTHER = range(5)

CATEGORIES: tuple[Category, ...] = (
    Category(MEDIA, "media", "Video & audio"),
    Category(IMAGES, "images", "Images"),
    Category(PROGRAMS, "programs", "Programs & system"),
    Category(DOCUMENTS, "documents", "Documents & archives"),
    Category(OTHER, "other", "Other"),
)
COUNT = len(CATEGORIES)


class Kind(IntEnum):
    PHOTOS = 0
    VIDEOS = 1
    MUSIC = 2
    DOCUMENTS = 3
    ARCHIVES = 4
    PROGRAMS = 5
    OTHER = 6


KIND_LABELS = {
    Kind.PHOTOS: "Photos & images",
    Kind.VIDEOS: "Videos",
    Kind.MUSIC: "Music & audio",
    Kind.DOCUMENTS: "Documents",
    Kind.ARCHIVES: "Archives & disk images",
    Kind.PROGRAMS: "Programs & system",
    Kind.OTHER: "Other files",
}

# One word per kind, for counts such as "1,204 photos".
KIND_NOUNS = {
    Kind.PHOTOS: ("photo", "photos"),
    Kind.VIDEOS: ("video", "videos"),
    Kind.MUSIC: ("audio file", "audio files"),
    Kind.DOCUMENTS: ("document", "documents"),
    Kind.ARCHIVES: ("archive", "archives"),
    Kind.PROGRAMS: ("program file", "program files"),
    Kind.OTHER: ("other file", "other files"),
}

KIND_CATEGORY = {
    Kind.PHOTOS: IMAGES,
    Kind.VIDEOS: MEDIA,
    Kind.MUSIC: MEDIA,
    Kind.DOCUMENTS: DOCUMENTS,
    Kind.ARCHIVES: DOCUMENTS,
    Kind.PROGRAMS: PROGRAMS,
    Kind.OTHER: OTHER,
}

# Longest text after the last dot that still counts as an extension, so that
# "notes.final version" is not reported as a ".final version" file.
MAX_EXTENSION_LENGTH = 10

_KIND_EXTENSIONS = {
    Kind.VIDEOS: """
        mp4 m4v mkv mov avi wmv webm flv f4v mpg mpeg mpe m2v m2ts mts vob 3gp 3g2
        ogv rm rmvb asf divx mxf braw r3d insv lrv
    """,
    Kind.MUSIC: """
        mp3 wav flac aac ogg oga opus m4a m4b m4p wma aiff aif aifc ape alac mid
        midi amr dsf dff mka wv caf ac3 dts
    """,
    Kind.PHOTOS: """
        jpg jpeg jpe jfif png apng gif bmp dib tif tiff webp heic heif avif jxl jp2
        j2k raw cr2 cr3 crw nef nrw arw srf sr2 dng orf rw2 raf srw pef x3f 3fr erf
        kdc mrw psd psb xcf kra ai eps svg svgz ico icns cur tga dds exr hdr
        afphoto afdesign clip cdr emf wmf pcx ppm pgm pbm
    """,
    Kind.PROGRAMS: """
        exe dll sys msi msp msu msix msixbundle appx appxbundle cab mui cat drv ocx
        cpl scr efi com so dylib pyd lib a node jar pdb
        pak vpk bsa ba2 bundle assets ress resource uasset umap upk rpf wad cpk pck
        obb apk xapk aab forge big dat bin vdf acf
    """,
    Kind.DOCUMENTS: """
        pdf doc docx docm dot dotx dotm xls xlsx xlsm xlsb xlt xltx ppt pptx pptm pps
        ppsx pot potx odt ods odp odg odf rtf txt md markdown rst csv tsv epub mobi
        azw azw3 djvu xps oxps pages numbers key one onepkg msg eml pst ost vsd vsdx
        pub tex bib
    """,
    Kind.ARCHIVES: """
        zip rar 7z tar gz tgz bz2 tbz2 xz txz zst lz lzma lz4 z cpio arj iso img dmg
        vhd vhdx vmdk vdi qcow2 wim esd swm
    """,
}

EXTENSION_KIND: dict[str, Kind] = {
    ext: kind for kind, words in _KIND_EXTENSIONS.items() for ext in words.split()
}
EXTENSION_CATEGORY: dict[str, int] = {ext: KIND_CATEGORY[kind] for ext, kind in EXTENSION_KIND.items()}


def extension_of(name: str) -> str:
    """Lower-case extension without the dot, or '' when the name has none."""
    dot = name.rfind(".")
    if dot <= 0 or len(name) - dot - 1 > MAX_EXTENSION_LENGTH:
        return ""
    ext = name[dot + 1:]
    if " " in ext:
        return ""
    return ext.lower()


def category_of_extension(ext: str) -> int:
    return EXTENSION_CATEGORY.get(ext, OTHER)


def category_of(name: str) -> int:
    return EXTENSION_CATEGORY.get(extension_of(name), OTHER)


def kind_of_extension(ext: str) -> Kind:
    return EXTENSION_KIND.get(ext, Kind.OTHER)


def kinds_in_category(category: int) -> frozenset[Kind]:
    """The kinds a chart colour stands for, e.g. video & audio -> videos and music."""
    return frozenset(kind for kind, cat in KIND_CATEGORY.items() if cat == category)
