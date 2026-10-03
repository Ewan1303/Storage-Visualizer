import pytest

from storagevis.core import categories as c


def test_no_extension_is_listed_twice():
    words = [w for text in c._EXTENSIONS.values() for w in text.split()]
    duplicates = {w for w in words if words.count(w) > 1}
    assert not duplicates


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
