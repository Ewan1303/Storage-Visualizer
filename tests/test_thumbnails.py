import os
import threading

import pytest

from storagevis.core.thumbnails import shell_thumbnail

pytestmark = pytest.mark.skipif(os.name != "nt", reason="uses the Windows shell")


@pytest.fixture
def picture(qapp, workdir):
    """A 600 x 300 picture: red on the left, blue on the right."""
    from PySide6.QtGui import QColor, QImage, QPainter

    image = QImage(600, 300, QImage.Format.Format_RGB32)
    image.fill(QColor("#2060ff"))
    painter = QPainter(image)
    painter.fillRect(0, 0, 300, 300, QColor("#ff2020"))
    painter.end()
    path = workdir / "split.png"
    assert image.save(str(path))
    return str(path)


def test_a_thumbnail_keeps_the_shape_and_fits_the_size(picture):
    thumb = shell_thumbnail(picture, 64)
    assert thumb is not None
    assert (thumb.width, thumb.height) == (64, 32)
    assert len(thumb.pixels) == thumb.width * thumb.height * 4
    # Rows come top to bottom and pixels as BGRA: red on the left, blue on the right.
    left = thumb.pixels[(16 * thumb.width + 4) * 4:(16 * thumb.width + 4) * 4 + 3]
    right = thumb.pixels[(16 * thumb.width + 60) * 4:(16 * thumb.width + 60) * 4 + 3]
    assert left[2] > 200 and left[0] < 80
    assert right[0] > 200 and right[2] < 80


def test_thumbnails_work_on_other_threads(picture):
    found = {}
    worker = threading.Thread(target=lambda: found.setdefault("thumb", shell_thumbnail(picture, 48)))
    worker.start()
    worker.join()
    assert found["thumb"] is not None and found["thumb"].width == 48


def test_a_missing_file_has_no_thumbnail(workdir):
    assert shell_thumbnail(str(workdir / "not-there.jpg"), 64) is None


def test_cached_only_never_fails_loudly(picture):
    thumb = shell_thumbnail(picture, 64, cached_only=True)  # cached picture, or else the type's icon
    assert thumb is None or (thumb.width <= 64 and thumb.height <= 64)
