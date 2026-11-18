import io
import sys

import pytest
import responses
from PIL import Image

from meli_sdk.exceptions import MeliAPIError
from meli_sdk.models import UploadedPicture
from meli_sdk.pictures import JPEG_MAGIC, to_jpeg_bytes

API_URL = "https://api.mercadolibre.com"
UPLOAD_URL = f"{API_URL}/pictures/items/upload"
UPLOAD_RESPONSE = {
    "id": "959699-MLM43299127002_092020",
    "max_size": "994x1020",
    "dominant_color": None,
    "crop": {"top_left_x": 0, "top_left_y": 0, "width": 994, "height": 1020},
    "variations": [
        {
            "size": "M",
            "url": "http://http2.mlstatic.com/picture.jpg",
            "secure_url": "https://http2.mlstatic.com/picture.jpg",
        }
    ],
}


def image_bytes(fmt="PNG", mode="RGB", size=(600, 600), color=(255, 0, 0, 255)) -> bytes:
    """Build an in-memory image and return its encoded bytes."""
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def test_upload_jpeg_passthrough_without_conversion(client, mocked, monkeypatch):
    """A valid JPEG is uploaded as-is, without Pillow."""
    data = image_bytes("JPEG")
    mocked.add(responses.POST, UPLOAD_URL, json=UPLOAD_RESPONSE)

    def fail(*args, **kwargs):
        raise AssertionError("to_jpeg_bytes must not be called")

    monkeypatch.setattr("meli_sdk.items.to_jpeg_bytes", fail)

    client.items.upload_picture(data, filename="photo.png")

    body = mocked.calls[0].request.body
    assert data in body
    assert b"Content-Type: image/jpeg" in body
    assert b'filename="photo.jpg"' in body


def test_upload_png_passthrough_keeps_png(client, mocked):
    """A valid PNG keeps its format and MIME type."""
    data = image_bytes("PNG")
    mocked.add(responses.POST, UPLOAD_URL, json=UPLOAD_RESPONSE)

    client.items.upload_picture(data, filename="photo.jpg")

    body = mocked.calls[0].request.body
    assert data in body
    assert b"Content-Type: image/png" in body
    assert b'filename="photo.png"' in body


def test_upload_webp_auto_converts_to_jpeg(client, mocked):
    """WebP is converted to JPEG under auto mode."""
    data = image_bytes("WEBP")
    mocked.add(responses.POST, UPLOAD_URL, json=UPLOAD_RESPONSE)

    client.items.upload_picture(data, filename="photo.webp")

    body = mocked.calls[0].request.body
    assert JPEG_MAGIC in body
    assert b"Content-Type: image/jpeg" in body
    assert b'filename="photo.jpg"' in body


def test_upload_convert_true_upscales_small_jpeg(client, mocked):
    """convert=True always re-encodes, upscaling small pictures."""
    data = image_bytes("JPEG", size=(100, 200))
    expected = to_jpeg_bytes(data)
    mocked.add(responses.POST, UPLOAD_URL, json=UPLOAD_RESPONSE)

    client.items.upload_picture(data, filename="small.jpg", convert=True)

    body = mocked.calls[0].request.body
    assert expected in body
    with Image.open(io.BytesIO(expected)) as image:
        assert image.size == (500, 1000)


def test_upload_convert_false_rejects_webp(client, mocked):
    """convert=False rejects anything that is not a small JPEG or PNG."""
    with pytest.raises(ValueError):
        client.items.upload_picture(image_bytes("WEBP"), convert=False)

    assert len(mocked.calls) == 0


@pytest.mark.parametrize("convert", [1, "true", None])
def test_upload_invalid_convert_value(client, mocked, convert):
    """Only auto, True and False are accepted."""
    with pytest.raises(ValueError):
        client.items.upload_picture(image_bytes("JPEG"), convert=convert)


def test_upload_returns_uploaded_picture(client, mocked):
    """The response is parsed into an UploadedPicture."""
    mocked.add(responses.POST, UPLOAD_URL, json=UPLOAD_RESPONSE)

    picture = client.items.upload_picture(image_bytes("JPEG"))

    assert isinstance(picture, UploadedPicture)
    assert picture.id == "959699-MLM43299127002_092020"
    assert picture.max_size == "994x1020"
    assert picture.secure_url == "https://http2.mlstatic.com/picture.jpg"


def test_upload_missing_id_raises(client, mocked):
    """A response without an id raises MeliAPIError."""
    mocked.add(responses.POST, UPLOAD_URL, json={"max_size": "994x1020"})

    with pytest.raises(MeliAPIError) as exc_info:
        client.items.upload_picture(image_bytes("JPEG"))

    assert exc_info.value.status_code == 200


def test_upload_without_pillow_still_passes_jpeg_through(client, mocked, monkeypatch):
    """A JPEG passthrough does not need Pillow."""
    data = image_bytes("JPEG")
    mocked.add(responses.POST, UPLOAD_URL, json=UPLOAD_RESPONSE)
    monkeypatch.setitem(sys.modules, "PIL", None)

    picture = client.items.upload_picture(data)

    assert picture.id == UPLOAD_RESPONSE["id"]


def test_add_picture_posts_id(client, mocked):
    """Linking a picture posts its id to the item."""
    mocked.add(
        responses.POST,
        f"{API_URL}/items/MCO1/pictures",
        json={"id": "MCO1"},
        match=[responses.matchers.json_params_matcher({"id": "PIC1"})],
    )

    assert client.items.add_picture("MCO1", "PIC1") == {"id": "MCO1"}


@pytest.mark.parametrize("picture_id", ["", "  ", None, 123])
def test_add_picture_rejects_empty_id(client, mocked, picture_id):
    """The picture id must be a non-empty string."""
    with pytest.raises(ValueError):
        client.items.add_picture("MCO1", picture_id)
