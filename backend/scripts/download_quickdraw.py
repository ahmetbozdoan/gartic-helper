"""
Quick Draw veri setinden eğitim bitmaplerini ve kılavuz çizimlerini kısmi olarak indirir.

Dosyaların tamamı ~40 GB olduğu için HTTP Range ile her kategoriden sadece ilk N örnek alınır.
Kullanım: python scripts/download_quickdraw.py --samples-per-category 4000
"""

import argparse
import ast
import json
import struct
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CATEGORY_TRANSLATIONS_PATH = BACKEND_ROOT / "data" / "quickdraw_categories_tr.json"
QUICKDRAW_DATA_DIR = BACKEND_ROOT / "data" / "quickdraw"
BITMAPS_DIR = QUICKDRAW_DATA_DIR / "bitmaps"
GUIDE_DRAWINGS_PATH = QUICKDRAW_DATA_DIR / "guide_drawings.json"

BITMAP_URL_TEMPLATE = (
    "https://storage.googleapis.com/quickdraw_dataset/full/numpy_bitmap/{category}.npy"
)
SIMPLIFIED_URL_TEMPLATE = (
    "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{category}.ndjson"
)
BITMAP_PIXEL_COUNT = 28 * 28
NPY_HEADER_FETCH_BYTES = 1024
SIMPLIFIED_FETCH_BYTES = 400_000
MAX_RETRIES = 4


def fetch_byte_range(url: str, start: int, end: int) -> bytes:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except OSError as error:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"İndirme başarısız: url={url} range={start}-{end} error={error}"
                ) from error
            time.sleep(2 * attempt)
    raise AssertionError("unreachable")


def build_category_url(url_template: str, category: str) -> str:
    return url_template.format(category=urllib.parse.quote(category))


def category_file_stem(category: str) -> str:
    return category.replace(" ", "_")


def download_bitmaps(category: str, sample_count: int) -> int:
    output_path = BITMAPS_DIR / f"{category_file_stem(category)}.npy"
    if output_path.exists():
        existing_count = np.load(output_path, mmap_mode="r").shape[0]
        if existing_count >= sample_count:
            return existing_count

    url = build_category_url(BITMAP_URL_TEMPLATE, category)
    header_bytes = fetch_byte_range(url, 0, NPY_HEADER_FETCH_BYTES - 1)
    if header_bytes[:6] != b"\x93NUMPY":
        raise RuntimeError(f"Beklenmeyen npy başlığı: category={category!r}")

    # npy v1 başlık uzunluğu 2 bayt, v2+ 4 bayttır.
    if header_bytes[6] == 1:
        header_length = struct.unpack("<H", header_bytes[8:10])[0]
        data_offset = 10 + header_length
    else:
        header_length = struct.unpack("<I", header_bytes[8:12])[0]
        data_offset = 12 + header_length
    header = ast.literal_eval(header_bytes[data_offset - header_length : data_offset].decode())

    available_count = header["shape"][0]
    download_count = min(sample_count, available_count)
    payload = fetch_byte_range(
        url, data_offset, data_offset + download_count * BITMAP_PIXEL_COUNT - 1
    )
    bitmaps = np.frombuffer(payload, dtype=np.uint8).reshape(download_count, BITMAP_PIXEL_COUNT)
    np.save(output_path, bitmaps)
    return download_count


def download_guide_drawings(category: str, drawing_count: int) -> list[list[list[list[int]]]]:
    """Oyunun tanıdığı (recognized) çizimlerden ilk N tanesini [[xs, ys], ...] olarak döndürür."""
    url = build_category_url(SIMPLIFIED_URL_TEMPLATE, category)
    payload = fetch_byte_range(url, 0, SIMPLIFIED_FETCH_BYTES - 1)

    drawings: list[list[list[list[int]]]] = []
    # Son satır Range sınırında kesilmiş olabilir, atlanır.
    for line in payload.split(b"\n")[:-1]:
        record = json.loads(line)
        if record.get("recognized"):
            drawings.append([[stroke[0], stroke[1]] for stroke in record["drawing"]])
        if len(drawings) >= drawing_count:
            break
    return drawings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-per-category", type=int, default=4000)
    parser.add_argument("--guide-drawings-per-category", type=int, default=10)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--skip-bitmaps", action="store_true")
    args = parser.parse_args()

    categories = list(json.loads(CATEGORY_TRANSLATIONS_PATH.read_text(encoding="utf-8")))
    BITMAPS_DIR.mkdir(parents=True, exist_ok=True)

    def process_category(category: str) -> tuple[str, int, list]:
        bitmap_count = (
            0 if args.skip_bitmaps else download_bitmaps(category, args.samples_per_category)
        )
        guide_drawings = download_guide_drawings(category, args.guide_drawings_per_category)
        return category, bitmap_count, guide_drawings

    guide_drawings_by_category: dict[str, list] = {}
    failed_categories: list[str] = []
    started_at = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_category, category): category for category in categories}
        for completed_index, future in enumerate(as_completed(futures), start=1):
            category = futures[future]
            try:
                _, bitmap_count, guide_drawings = future.result()
            except RuntimeError as error:
                failed_categories.append(category)
                print(f"[HATA] {category}: {error}", flush=True)
                continue
            guide_drawings_by_category[category] = guide_drawings
            print(
                f"[{completed_index}/{len(categories)}] {category}: "
                f"{bitmap_count} bitmap, {len(guide_drawings)} kılavuz "
                f"({time.time() - started_at:.0f} sn)",
                flush=True,
            )

    ordered_guides = {
        category: guide_drawings_by_category[category]
        for category in categories
        if category in guide_drawings_by_category
    }
    GUIDE_DRAWINGS_PATH.write_text(json.dumps(ordered_guides, separators=(",", ":")), "utf-8")
    print(f"Kılavuz çizimleri yazıldı: {GUIDE_DRAWINGS_PATH}")
    if failed_categories:
        print(f"Başarısız kategoriler (tekrar çalıştırın): {failed_categories}")


if __name__ == "__main__":
    main()
