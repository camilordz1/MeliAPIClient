import io
import os

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MIN_SIDE = 500
QUALITIES = (92, 85, 78, 70)

PILLOW_HINT = 'pip install "meli-python-sdk[images]"'


def read_picture_source(source) -> tuple[bytes, str | None]:
    """Read a picture source, returning its bytes and a filename hint."""
    if isinstance(source, (str, os.PathLike)):
        path = os.fspath(source)
        with open(path, "rb") as fileobj:
            data = fileobj.read()
        hint = os.path.basename(path)
    elif isinstance(source, (bytes, bytearray)):
        data = bytes(source)
        hint = None
    elif hasattr(source, "read"):
        data = source.read()
        if isinstance(data, str):
            raise TypeError("picture file object must be opened in binary mode")
        name = getattr(source, "name", "")
        hint = os.path.basename(name) if isinstance(name, str) and name else None
    else:
        raise TypeError("picture source must be a path, bytes or a binary file object")

    if not data:
        raise ValueError("picture source is empty")
    return bytes(data), hint


def _flatten_on_white(image) -> "object":
    """Flatten a transparent image onto a white background."""
    from PIL import Image

    background = Image.new("RGB", image.size, (255, 255, 255))
    rgba = image.convert("RGBA")
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def to_jpeg_bytes(
    data: bytes,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
    min_side: int = MIN_SIDE,
) -> bytes:
    """Convert image bytes to JPEG, flattening transparency and upscaling tiny images."""
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ImportError(
            f"Pillow is required for image conversion; run {PILLOW_HINT}"
        ) from exc

    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            has_alpha = opened.mode in ("RGBA", "LA") or (
                opened.mode == "P" and "transparency" in opened.info
            )
            image = _flatten_on_white(opened) if has_alpha else opened.convert("RGB")

            width, height = image.size
            short_side = min(width, height)
            if short_side < min_side:
                scale = min_side / short_side
                image = image.resize(
                    (
                        max(1, round(width * scale)),
                        max(1, round(height * scale)),
                    ),
                    Image.Resampling.LANCZOS,
                )

            for quality in QUALITIES:
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=quality, optimize=True)
                if buffer.tell() <= max_bytes:
                    return buffer.getvalue()

        raise ValueError(
            f"picture cannot be converted to JPEG under {max_bytes} bytes"
        )
    except UnidentifiedImageError as exc:
        raise ValueError("unsupported or corrupt image") from exc
