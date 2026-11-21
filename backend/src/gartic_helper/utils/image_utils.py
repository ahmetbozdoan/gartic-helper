"""Data URL <-> bytes dönüşümleri."""

import base64
import binascii
import re

DATA_URL_REGEX = re.compile(
    r"^data:(?P<mime_type>image/[\w.+-]+);base64,(?P<payload>.+)$", re.DOTALL
)


def decode_image_data_url(data_url: str) -> tuple[bytes, str]:
    """'data:image/png;base64,...' biçimindeki metni (bytes, mime_type) olarak çözer."""
    match = DATA_URL_REGEX.match(data_url.strip())
    if match is None:
        raise ValueError(f"Geçersiz görsel data URL'si (ilk 40 karakter: {data_url[:40]!r})")
    try:
        image_bytes = base64.b64decode(match.group("payload"), validate=True)
    except binascii.Error as error:
        raise ValueError(f"Görsel base64 çözülemedi: {error}") from error
    return image_bytes, match.group("mime_type")


def encode_image_data_url(image_bytes: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
