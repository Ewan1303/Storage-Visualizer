import pytest

from storagevis.core import categories as c


def test_no_extension_is_listed_twice():
    words = [w for text in c._KIND_EXTENSIONS.values() for w in text.split()]
    duplicates = {w for w in words if words.count(w) > 1}
    assert not duplicates


def test_every_extension_gets_the_colour_of_its_kind():
    for ext, kind in c.EXTENSION_KIND.items():
        assert c.EXTENSION_CATEGORY[ext] == c.KIND_CATEGORY[kind]
    assert set(c.KIND_LABELS) == set(c.Kind) == set(c.KIND_NOUNS) == set(c.KIND_CATEGORY)


@pytest.mark.parametrize("ext, kind", [
    ("mp4", c.Kind.VIDEOS), ("flac", c.Kind.MUSIC), ("heic", c.Kind.PHOTOS), ("pdf", c.Kind.DOCUMENTS),
    ("zip", c.Kind.ARCHIVES), ("dll", c.Kind.PROGRAMS), ("py", c.Kind.OTHER), ("", c.Kind.OTHER),
])
def test_kind_of_extension(ext, kind):
    assert c.kind_of_extension(ext) == kind


def test_kinds_in_category():
    assert c.kinds_in_category(c.MEDIA) == {c.Kind.VIDEOS, c.Kind.MUSIC}
    assert c.kinds_in_category(c.DOCUMENTS) == {c.Kind.DOCUMENTS, c.Kind.ARCHIVES}
    assert c.kinds_in_category(c.IMAGES) == {c.Kind.PHOTOS}


def test_extensions_are_lower_case():
    assert all(ext == ext.lower() for ext in c.EXTENSION_CATEGORY)


@pytest.mark.parametrize("name, ext", [
    ("Movie.MP4", "mp4"),
    ("archive.tar.gz", "gz"),
    (".bashrc", ""),
    ("README", ""),
    ("trailing.", ""),
    ("notes.final version", ""),
    ("weird.abcdefghijklmnop", ""),
])
def test_extension_of(name, ext):
    assert c.extension_of(name) == ext


@pytest.mark.parametrize("name, category", [
    ("holiday.mkv", c.MEDIA),
    ("song.FLAC", c.MEDIA),
    ("IMG_0001.JPG", c.IMAGES),
    ("setup.exe", c.PROGRAMS),
    ("pagefile.sys", c.PROGRAMS),
    ("report.pdf", c.DOCUMENTS),
    ("backup.7z", c.DOCUMENTS),
    ("script.py", c.OTHER),
    ("no_extension", c.OTHER),
])
def test_category_of(name, category):
    assert c.category_of(name) == category


def test_categories_are_in_index_order():
    assert [cat.index for cat in c.CATEGORIES] == list(range(c.COUNT))
