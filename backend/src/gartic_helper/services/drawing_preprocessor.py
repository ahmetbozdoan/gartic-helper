"""Gartic canvas görüntüsünü Quick Draw 28x28 bitmap biçimine dönüştürür."""

import io

import numpy as np
from PIL import Image, ImageFilter
from skimage.morphology import skeletonize

QUICKDRAW_IMAGE_SIZE = 28
# Quick Draw bitmapleri 256 birimlik çizim alanı + 2x16 kenar boşluğu + 16 birim çizgi kalınlığıyla
# (toplam 304 birim) render edilmiştir; Gartic çizimi de aynı oranlara getirilir.
QUICKDRAW_DRAWING_SPAN = 256
QUICKDRAW_TOTAL_PADDING = 2 * 16 + 16
QUICKDRAW_LINE_WIDTH = 16
INTERMEDIATE_SIZE = QUICKDRAW_IMAGE_SIZE * 4
INK_THRESHOLD = 40
INTERMEDIATE_INK_THRESHOLD = 20
# Komşu pikseller arasında bu kadar renk farkı (herhangi bir kanalda) varsa kenar sayılır.
COLOR_EDGE_THRESHOLD = 40
# Görüntünün uzun kenarının bu oranından kalın bölgeler (boya kovası) dolgu sayılır.
FILL_EROSION_RATIO = 0.02


class EmptyDrawingError(ValueError):
    """Görüntüde çizim (mürekkep) yoksa fırlatılır."""


def detect_color_edges(rgb_pixels: np.ndarray) -> np.ndarray:
    """
    Quick Draw çizimleri sadece çizgiden oluşur; Gartic'te ise boya kovasıyla doldurulmuş alanlar
    olur. Renk değişen yerler kenar sayılır: ince çizgiler korunur, dolguların sadece dış hatları
    ve farklı renkler arasındaki sınırlar kalır, tek renkli iç kısımlar boşalır.
    """
    signed_pixels = rgb_pixels.astype(np.int16)
    horizontal_difference = np.abs(np.diff(signed_pixels, axis=1)).max(axis=2)
    vertical_difference = np.abs(np.diff(signed_pixels, axis=0)).max(axis=2)

    edge_mask = np.zeros(rgb_pixels.shape[:2], dtype=bool)
    horizontal_edges = horizontal_difference > COLOR_EDGE_THRESHOLD
    vertical_edges = vertical_difference > COLOR_EDGE_THRESHOLD
    # Fark iki komşu piksel arasında olduğu için kenar ikisine de işaretlenir.
    edge_mask[:, :-1] |= horizontal_edges
    edge_mask[:, 1:] |= horizontal_edges
    edge_mask[:-1, :] |= vertical_edges
    edge_mask[1:, :] |= vertical_edges
    return edge_mask


def extract_stroke_centerlines(rgb_pixels: np.ndarray, ink_mask: np.ndarray) -> np.ndarray:
    """
    Fırça kalınlığından ve dolgulardan bağımsız, 1 piksellik çizgi orta hatlarını çıkarır.
    Dolguların içi silinir (aşındırma), renkler arası sınırlar eklenir (renk kenarları), sonra
    hepsi iskeletleştirilir; Quick Draw kalınlığı sonradan tek tip olarak uygulanır.
    """
    erosion_size = max(3, int(max(ink_mask.shape) * FILL_EROSION_RATIO) | 1)
    mask_image = Image.fromarray(ink_mask.astype(np.uint8) * 255)
    fill_interior = np.asarray(mask_image.filter(ImageFilter.MinFilter(erosion_size))) > 0
    stroke_mask = (ink_mask & ~fill_interior) | detect_color_edges(rgb_pixels)
    return skeletonize(stroke_mask)


def preprocess_drawing(image_bytes: bytes) -> np.ndarray:
    """PNG baytlarını modele uygun (1, 1, 28, 28) float32 dizisine çevirir (0=boş, 1=mürekkep)."""
    with Image.open(io.BytesIO(image_bytes)) as source_image:
        rgb_pixels = np.asarray(source_image.convert("RGB"), dtype=np.uint8)

    # En koyu kanal kullanılır; böylece sarı gibi açık renkli çizgiler de mürekkep sayılır.
    ink_mask = (255 - rgb_pixels.min(axis=2)) > INK_THRESHOLD
    if not ink_mask.any():
        raise EmptyDrawingError("Canvas'ta çizim yok")
    ink_mask = extract_stroke_centerlines(rgb_pixels, ink_mask)

    ink_rows = np.flatnonzero(ink_mask.any(axis=1))
    ink_columns = np.flatnonzero(ink_mask.any(axis=0))
    cropped_mask = ink_mask[ink_rows[0] : ink_rows[-1] + 1, ink_columns[0] : ink_columns[-1] + 1]

    cropped_height, cropped_width = cropped_mask.shape
    drawing_span = max(cropped_height, cropped_width)
    padding_pixels = round(drawing_span * QUICKDRAW_TOTAL_PADDING / QUICKDRAW_DRAWING_SPAN / 2)
    square_size = drawing_span + 2 * padding_pixels
    square_pixels = np.zeros((square_size, square_size), dtype=np.uint8)
    offset_y = (square_size - cropped_height) // 2
    offset_x = (square_size - cropped_width) // 2
    square_pixels[offset_y : offset_y + cropped_height, offset_x : offset_x + cropped_width] = (
        cropped_mask * 255
    )

    # Önce ara boyuta küçültülür, ince çizgiler kaybolmasın diye ikilenir, sonra Quick Draw
    # kalınlığına genişletilir ve son boyuta alan ortalamasıyla (antialias) indirilir.
    intermediate_image = Image.fromarray(square_pixels).resize(
        (INTERMEDIATE_SIZE, INTERMEDIATE_SIZE), Image.Resampling.BOX
    )
    intermediate_image = intermediate_image.point(
        lambda value: 255 if value > INTERMEDIATE_INK_THRESHOLD else 0
    )
    line_width_pixels = (
        INTERMEDIATE_SIZE
        * QUICKDRAW_LINE_WIDTH
        / (QUICKDRAW_DRAWING_SPAN + QUICKDRAW_TOTAL_PADDING)
    )
    dilation_size = int(line_width_pixels) | 1
    if dilation_size >= 3:
        intermediate_image = intermediate_image.filter(ImageFilter.MaxFilter(dilation_size))
    final_image = intermediate_image.resize(
        (QUICKDRAW_IMAGE_SIZE, QUICKDRAW_IMAGE_SIZE), Image.Resampling.BOX
    )

    model_input = np.asarray(final_image, dtype=np.float32) / 255.0
    return model_input.reshape(1, 1, QUICKDRAW_IMAGE_SIZE, QUICKDRAW_IMAGE_SIZE)
