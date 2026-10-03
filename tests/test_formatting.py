import pytest

from storagevis.core.formatting import format_count, format_duration, format_share, format_size

KB, MB, GB = 1024, 1024 ** 2, 1024 ** 3


@pytest.mark.parametrize("value, text", [
    (0, "0 B"),
    (999, "999 B"),
    (1000, "0.98 KB"),
    (1024, "1.00 KB"),
    (10 * KB, "10.0 KB"),
    (int(99.96 * KB), "100 KB"),
    (1023 * KB, "1.00 MB"),
    (int(5.7 * GB), "5.70 GB"),
    (931 * GB, "931 GB"),
    (2 * 1024 * GB, "2.00 TB"),
])
def test_format_size(value, text):
    assert format_size(value) == text


def test_format_size_never_shows_four_digit_values():
    for n in range(1000, 5 * MB, 997):
        number = format_size(n).split()[0]
        assert float(number) < 1000, n


def test_format_count():
    assert format_count(1234567) == "1,234,567"
    assert format_count(1, "file") == "1 file"
    assert format_count(2, "file") == "2 files"
    assert format_count(0, "folder") == "0 folders"
    assert format_count(3, "small item") == "3 small items"


@pytest.mark.parametrize("fraction, text", [
    (0, "0%"), (0.0004, "<0.1%"), (0.5, "50%"), (0.4567, "45.7%"), (1, "100%"),
])
def test_format_share(fraction, text):
    assert format_share(fraction) == text


@pytest.mark.parametrize("seconds, text", [
    (4.7, "4.7 s"), (42.2, "42 s"), (65, "1 min 05 s"), (3720, "1 h 02 min"),
])
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text
