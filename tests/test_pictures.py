import io
import random
import sys

import pytest
from PIL import Image

from meli_sdk.pictures import (
    JPEG_MAGIC,
    read_picture_source,
    to_jpeg_bytes,
)


def image_bytes(fmt="PNG", mode="RGB", size=(100, 100), color=(255, 0, 0, 255)) -> bytes:
    """Build an in-memory image and return its encoded bytes."""
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def decoded_size(data: bytes) -> tuple:
    """Return the size of an encoded image."""
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def test_read_picture_source_path_bytes_and_fileobj(tmp_path):
    """A path, bytes and a file object are read with the right filename hint."""
    data = image_bytes()
    path = tmp_path / "foto.png"
    path.write_bytes(data)

    from_path, path_hint = read_picture_source(path)
    assert from_path == data
    assert path_hint == "foto.png"

    from_str, str_hint = read_picture_source(str(path))
    assert from_str == data
    assert str_hint == "foto.png"

    from_bytes, bytes_hint = read_picture_source(data)
    assert from_bytes == data
    assert bytes_hint is None

    with open(path, "rb") as fileobj:
        from_file, file_hint = read_picture_source(fileobj)
    assert from_file == data
    assert file_hint == "foto.png"


def test_read_picture_source_rejects(tmp_path):
    """Empty, missing and unsupported sources are rejected."""

    class TextFile:
        def read(self) -> str:
            return "text"

    with pytest.raises(ValueError):
        read_picture_source(b"")

    with pytest.raises(FileNotFoundError):
        read_picture_source(tmp_path / "missing.png")

    with pytest.raises(TypeError):
        read_picture_source(123)

    with pytest.raises(TypeError):
        read_picture_source(TextFile())


def test_to_jpeg_flattens_rgba_on_white():
    """Transparent pixels become white instead of black."""
    data = image_bytes("PNG", "RGBA", (10, 10), (255, 0, 0, 0))

    jpeg = to_jpeg_bytes(data)

    assert jpeg.startswith(JPEG_MAGIC)
    with Image.open(io.BytesIO(jpeg)) as image:
        red, green, blue = image.convert("RGB").getpixel((5, 5))
    assert min(red, green, blue) >= 250


def test_to_jpeg_upscales_small_images():
    """The short side is raised to 500 px, keeping the aspect ratio."""
    data = image_bytes("PNG", "RGB", (100, 200))

    jpeg = to_jpeg_bytes(data)

    assert decoded_size(jpeg) == (500, 1000)


def test_to_jpeg_keeps_large_images_size():
    """A large image keeps its size."""
    data = image_bytes("PNG", "RGB", (800, 600))

    assert decoded_size(to_jpeg_bytes(data)) == (800, 600)


def test_to_jpeg_converts_webp():
    """WebP input is converted to JPEG."""
    data = image_bytes("WEBP", "RGB", (600, 600))

    assert to_jpeg_bytes(data).startswith(JPEG_MAGIC)


def test_to_jpeg_raises_when_it_cannot_fit():
    """Oversized results raise instead of returning too many bytes."""
    raw = random.Random(0).randbytes(800 * 800 * 3)
    buffer = io.BytesIO()
    Image.frombytes("RGB", (800, 800), raw).save(buffer, format="PNG")

    with pytest.raises(ValueError):
        to_jpeg_bytes(buffer.getvalue(), max_bytes=1000)


def test_to_jpeg_rejects_corrupt_data():
    """Corrupt data raises a ValueError with a clear message."""
    with pytest.raises(ValueError, match="unsupported or corrupt image"):
        to_jpeg_bytes(b"not an image")


def test_to_jpeg_without_pillow_raises_import_error_with_hint(monkeypatch):
    """A missing Pillow raises ImportError with the install hint."""
    data = image_bytes()

    monkeypatch.setitem(sys.modules, "PIL", None)
    with pytest.raises(ImportError, match=r"meli-python-sdk\[images\]"):
        to_jpeg_bytes(data)
