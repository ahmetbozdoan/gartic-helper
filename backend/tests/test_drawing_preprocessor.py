import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from gartic_helper.services.drawing_preprocessor import EmptyDrawingError, preprocess_drawing


def encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_small_offcenter_drawing_is_centered_and_scaled() -> None:
    image = Image.new("RGB", (384, 224), "white")
    ImageDraw.Draw(image).rectangle((10, 10, 60, 60), outline="black", width=2)

    model_input = preprocess_drawing(encode_png(image))

    assert model_input.shape == (1, 1, 28, 28)
    assert model_input.dtype == np.float32
    ink_rows = np.flatnonzero(model_input[0, 0].max(axis=1) > 0.3)
    # Kare 28x28 alanın büyük kısmını kaplamalı ve kenarlara yapışık olmamalı.
    assert ink_rows[0] >= 1 and ink_rows[-1] <= 26
    assert ink_rows[-1] - ink_rows[0] >= 20


def test_light_colored_lines_count_as_ink() -> None:
    image = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(image).line((20, 100, 180, 100), fill=(255, 220, 0), width=3)

    assert preprocess_drawing(encode_png(image)).max() > 0.5


def test_bucket_filled_area_becomes_outline() -> None:
    image = Image.new("RGB", (384, 224), "white")
    ImageDraw.Draw(image).rectangle((100, 20, 280, 200), fill=(90, 200, 70), outline="black")

    bitmap = preprocess_drawing(encode_png(image))[0, 0]

    # Quick Draw'daki gibi içi boş kare: merkez boş, kenarlar dolu.
    assert bitmap[10:18, 10:18].max() < 0.1
    assert bitmap[:, 3:6].max() > 0.5


def test_thick_and_thin_strokes_have_same_width() -> None:
    thin_image = Image.new("RGB", (384, 224), "white")
    ImageDraw.Draw(thin_image).line((50, 112, 330, 112), fill="black", width=2)
    thick_image = Image.new("RGB", (384, 224), "white")
    ImageDraw.Draw(thick_image).line((50, 112, 330, 112), fill="blue", width=12)

    thin_rows = (preprocess_drawing(encode_png(thin_image))[0, 0] > 0.3).any(axis=1).sum()
    thick_rows = (preprocess_drawing(encode_png(thick_image))[0, 0] > 0.3).any(axis=1).sum()

    assert abs(int(thin_rows) - int(thick_rows)) <= 1


def test_blank_canvas_raises() -> None:
    with pytest.raises(EmptyDrawingError):
        preprocess_drawing(encode_png(Image.new("RGB", (100, 100), "white")))
