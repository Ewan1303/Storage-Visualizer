"""File-type categories used to colour the visualisations.

There are four named categories plus "Other". In a treemap any two file types
can end up side by side, and four hues is the most that stay easy to tell apart
from one another for colour-blind viewers too (the colours themselves, and how
they were checked, live in ``storagevis.ui.theme``).
"""

from __future__ import annotations

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

# Longest text after the last dot that still counts as an extension, so that
# "notes.final version" is not reported as a ".final version" file.
MAX_EXTENSION_LENGTH = 10

_EXTENSIONS = {
    MEDIA: """
        mp4 m4v mkv mov avi wmv webm flv f4v mpg mpeg mpe m2v m2ts mts vob 3gp 3g2
        ogv rm rmvb asf divx mxf braw r3d insv lrv
        mp3 wav flac aac ogg oga opus m4a m4b m4p wma aiff aif aifc ape alac mid
        midi amr dsf dff mka wv caf ac3 dts
    """,
    IMAGES: """
        jpg jpeg jpe jfif png apng gif bmp dib tif tiff webp heic heif avif jxl jp2
        j2k raw cr2 cr3 crw nef nrw arw srf sr2 dng orf rw2 raf srw pef x3f 3fr erf
        kdc mrw psd psb xcf kra ai eps svg svgz ico icns cur tga dds exr hdr
        afphoto afdesign clip cdr emf wmf pcx ppm pgm pbm
    """,
    PROGRAMS: """
        exe dll sys msi msp msu msix msixbundle appx appxbundle cab mui cat drv ocx
        cpl scr efi com so dylib pyd lib a node jar pdb
        pak vpk bsa ba2 bundle assets ress resource uasset umap upk rpf wad cpk pck
        obb apk xapk aab forge big dat bin vdf acf
    """,
    DOCUMENTS: """
        pdf doc docx docm dot dotx dotm xls xlsx xlsm xlsb xlt xltx ppt pptx pptm pps
        ppsx pot potx odt ods odp odg odf rtf txt md markdown rst csv tsv epub mobi
        azw azw3 djvu xps oxps pages numbers key one onepkg msg eml pst ost vsd vsdx
        pub tex bib
        zip rar 7z tar gz tgz bz2 tbz2 xz txz zst lz lzma lz4 z cpio arj iso img dmg
        vhd vhdx vmdk vdi qcow2 wim esd swm
    """,
}

EXTENSION_CATEGORY: dict[str, int] = {
    ext: category for category, words in _EXTENSIONS.items() for ext in words.split()
}


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
