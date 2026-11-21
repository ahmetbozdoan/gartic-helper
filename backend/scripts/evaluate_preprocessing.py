"""
Ön işleme + modelin Gartic tarzı çizimlerdeki başarısını ölçer.

Eğitimde kullanılmayan Quick Draw çizimleri (dosyanın ortasından) Gartic canvas'ına benzer biçimde
üç farklı şekilde render edilir: ince siyah çizgi, kalın renkli çizgi, boya kovasıyla doldurulmuş.
Kullanım: python scripts/evaluate_preprocessing.py
"""

import io
import json
import random
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from gartic_helper.dependencies import get_quickdraw_classifier  # noqa: E402
from gartic_helper.services.drawing_preprocessor import (  # noqa: E402
    EmptyDrawingError,
    preprocess_drawing,
)

CATEGORY_TRANSLATIONS_PATH = BACKEND_ROOT / "data" / "quickdraw_categories_tr.json"
EVALUATION_DRAWINGS_PATH = BACKEND_ROOT / "data" / "quickdraw" / "evaluation_drawings.json"
SIMPLIFIED_URL_TEMPLATE = (
    "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{category}.ndjson"
)
DRAWINGS_PER_CATEGORY = 3
FETCH_BYTES = 200_000
CANVAS_SIZE = (384, 224)
RENDER_STYLES = ("thin_black", "thick_colored", "bucket_filled")
FILL_COLORS = ((90, 200, 70), (240, 200, 0), (220, 40, 40), (60, 120, 230))


def fetch_evaluation_drawings(category: str) -> list:
    url = SIMPLIFIED_URL_TEMPLATE.format(category=urllib.parse.quote(category))
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as response:
        file_size = int(response.headers["Content-Length"])
    # Eğitim verisi dosya başından alındığı için ortadan okunur; ilk satır yarım olabilir, atlanır.
    start = file_size // 2
    request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{start + FETCH_BYTES}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        lines = response.read().split(b"\n")[1:-1]
    drawings = []
    for line in lines:
        record = json.loads(line)
        if record.get("recognized"):
            drawings.append(record["drawing"])
        if len(drawings) >= DRAWINGS_PER_CATEGORY:
            break
    return drawings


def load_evaluation_drawings(categories: list[str]) -> dict[str, list]:
    if EVALUATION_DRAWINGS_PATH.exists():
        return json.loads(EVALUATION_DRAWINGS_PATH.read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=16) as executor:
        drawings_by_category = dict(
            zip(categories, executor.map(fetch_evaluation_drawings, categories), strict=True)
        )
    EVALUATION_DRAWINGS_PATH.write_text(json.dumps(drawings_by_category), encoding="utf-8")
    return drawings_by_category


def render_gartic_style(drawing: list, style: str, rng: random.Random) -> bytes:
    image = Image.new("RGB", CANVAS_SIZE, "white")
    draw = ImageDraw.Draw(image)
    scale = rng.uniform(0.45, 0.8)
    offset_x = rng.uniform(10, CANVAS_SIZE[0] - 256 * scale - 10)
    offset_y = rng.uniform(5, max(6, CANVAS_SIZE[1] - 256 * scale - 5))
    line_color = (0, 0, 0) if style != "thick_colored" else rng.choice(FILL_COLORS)
    line_width = 2 if style == "thin_black" else (6 if style == "thick_colored" else 3)

    def to_canvas(x: float, y: float) -> tuple[float, float]:
        return offset_x + x * scale, offset_y + y * scale

    for xs, ys, *_ in drawing:
        points = [to_canvas(x, y) for x, y in zip(xs, ys, strict=True)]
        if len(points) > 1:
            draw.line(points, fill=line_color, width=line_width, joint="curve")

    if style == "bucket_filled":
        # Çizimin ortasına boya kovası; arka planı doldurursa (kapalı alan yoksa) geri alınır.
        before_fill = image.copy()
        ImageDraw.floodfill(image, to_canvas(128, 128), rng.choice(FILL_COLORS), thresh=40)
        white_ratio = (np.asarray(image) == 255).all(axis=2).mean()
        if white_ratio < 0.4:
            image = before_fill

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> None:
    categories = list(json.loads(CATEGORY_TRANSLATIONS_PATH.read_text(encoding="utf-8")))
    drawings_by_category = load_evaluation_drawings(categories)
    classifier = get_quickdraw_classifier()
    rng = random.Random(7)

    for style in RENDER_STYLES:
        top1_hits = top3_hits = total = 0
        for category in categories:
            for drawing in drawings_by_category.get(category, []):
                try:
                    model_input = preprocess_drawing(render_gartic_style(drawing, style, rng))
                except EmptyDrawingError:
                    continue
                predicted = [p.category for p in classifier.predict(model_input, top_k=3)]
                total += 1
                top1_hits += predicted[0] == category
                top3_hits += category in predicted
        print(f"{style:14s} n={total:4d} top1={top1_hits / total:.3f} top3={top3_hits / total:.3f}")


if __name__ == "__main__":
    main()
