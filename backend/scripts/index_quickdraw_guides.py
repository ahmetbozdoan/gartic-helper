"""
Quick Draw simplified çizimlerini indirip yerel bir kılavuza dönüştürür.

Tam veri kümesi (345 kategori, onlarca GB ndjson) eklenti paketine koyulmaz.
Her kategorinin dosya boyutu kaydedilir; tanınmış çizimlerden sınırlı bir örnek
backend/data/quickdraw/guides altına yazılır. Kullanım:

    python scripts/index_quickdraw_guides.py
"""

import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS_PATH = BACKEND_ROOT / "data" / "quickdraw_categories_tr.json"
GUIDES_DIR = BACKEND_ROOT / "data" / "quickdraw" / "guides"
INDEX_PATH = BACKEND_ROOT / "data" / "quickdraw" / "guide_index.json"
OFFICIAL_CATEGORIES_URL = (
    "https://raw.githubusercontent.com/googlecreativelab/quickdraw-dataset/master/categories.txt"
)
SIMPLIFIED_URL = (
    "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{category}.ndjson"
)
DRAWINGS_PER_CATEGORY = 24
CHUNK_BYTES = 256 * 1024
MAX_BYTES_PER_CATEGORY = 2 * 1024 * 1024
MAX_WORKERS = 8
REQUEST_TIMEOUT_SECONDS = 90


def fetch_bytes(url: str, start: int | None = None, end: int | None = None) -> tuple[bytes, dict]:
    headers = {}
    if start is not None and end is not None:
        headers["Range"] = f"bytes={start}-{end}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read(), dict(response.headers)


def official_categories() -> list[str]:
    payload, _ = fetch_bytes(OFFICIAL_CATEGORIES_URL)
    return [line.strip() for line in payload.decode("utf-8").splitlines() if line.strip()]


def category_url(category: str) -> str:
    return SIMPLIFIED_URL.format(category=urllib.parse.quote(category))


def parse_recognized_drawings(payload: bytes, limit: int) -> tuple[list, bytes]:
    """Tam satırları ayrıştırır; sonda kesilen satırı bir sonraki parçaya bırakır."""
    if b"\n" not in payload:
        return [], payload
    complete, _, remainder = payload.rpartition(b"\n")
    drawings: list[list[list[list[int]]]] = []
    for line in complete.split(b"\n"):
        if not line:
            continue
        record = json.loads(line)
        if not record.get("recognized"):
            continue
        strokes = []
        for stroke in record["drawing"]:
            if len(stroke) < 2 or len(stroke[0]) != len(stroke[1]):
                raise ValueError(f"Beklenmeyen çizgi biçimi: word={record.get('word')!r}")
            strokes.append([stroke[0], stroke[1]])
        if strokes:
            drawings.append(strokes)
        if len(drawings) >= limit:
            break
    return drawings, remainder


def sample_category(category: str) -> dict:
    url = category_url(category)
    _, head = fetch_bytes(url, 0, 0)
    content_range = head.get("Content-Range", "")
    file_bytes = int(content_range.split("/")[-1]) if "/" in content_range else None
    if not file_bytes:
        raise RuntimeError(f"Dosya boyutu okunamadı: category={category!r}")

    drawings: list = []
    pending = b""
    downloaded = 0
    while len(drawings) < DRAWINGS_PER_CATEGORY and downloaded < min(
        file_bytes, MAX_BYTES_PER_CATEGORY
    ):
        end = min(downloaded + CHUNK_BYTES, file_bytes) - 1
        chunk, _ = fetch_bytes(url, downloaded, end)
        downloaded += len(chunk)
        found, pending = parse_recognized_drawings(
            pending + chunk, DRAWINGS_PER_CATEGORY - len(drawings)
        )
        drawings.extend(found)
    if not drawings:
        raise RuntimeError(f"Tanınmış çizim bulunamadı: category={category!r}")

    output_path = GUIDES_DIR / f"{category.replace(' ', '_')}.json"
    output_path.write_text(json.dumps(drawings, separators=(",", ":")), encoding="utf-8")
    return {
        "file_bytes": file_bytes,
        "downloaded_bytes": downloaded,
        "sampled_drawings": len(drawings),
        "strokes": len(drawings[0]),
    }


def main() -> None:
    categories = official_categories()
    mapping = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    missing = sorted(set(categories) - set(mapping))
    extra = sorted(set(mapping) - set(categories))
    if missing or extra or len(categories) != 345:
        raise SystemExit(
            f"Kategori eşleştirmesi resmi listeyle uyuşmuyor: missing={missing} extra={extra}"
        )

    GUIDES_DIR.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    index: dict[str, dict] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(sample_category, category): category for category in categories}
        for completed, future in enumerate(as_completed(futures), start=1):
            category = futures[future]
            try:
                index[category] = future.result()
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
                failures.append(category)
                print(f"[HATA] {category}: {error}", flush=True)
                continue
            print(
                f"[{completed}/{len(categories)}] {category}: "
                f"{index[category]['sampled_drawings']} çizim, "
                f"dosya {index[category]['file_bytes'] / 1_000_000:.1f} MB "
                f"({time.time() - started_at:.0f} sn)",
                flush=True,
            )

    ordered = {category: index[category] for category in categories if category in index}
    total_file_bytes = sum(item["file_bytes"] for item in ordered.values())
    total_downloaded = sum(item["downloaded_bytes"] for item in ordered.values())
    summary = {
        "source": "https://storage.googleapis.com/quickdraw_dataset/full/simplified/",
        "license": "CC BY 4.0",
        "attribution": "Quick, Draw! dataset, Google",
        "category_count": len(ordered),
        "drawings_per_category": DRAWINGS_PER_CATEGORY,
        "total_file_bytes": total_file_bytes,
        "total_downloaded_bytes": total_downloaded,
        "categories": ordered,
    }
    INDEX_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"İndeks yazıldı: {len(ordered)} kategori, "
        f"tam veri {total_file_bytes / 1_000_000_000:.1f} GB, "
        f"indirilen {total_downloaded / 1_000_000:.1f} MB"
    )
    if failures:
        raise SystemExit(f"Başarısız kategoriler: {failures}")


if __name__ == "__main__":
    main()
