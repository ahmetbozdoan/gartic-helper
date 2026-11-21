"""
Sketchy SVG arşivini çıkartır, bütünlüğünü sayar ve kategori indeksini yazar.

Tam arşiv (yaklaşık 1 GB sıkıştırılmış, on binlerce SVG) eklenti paketine koyulmaz.
Kullanım:

    python scripts/index_sketchy.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import py7zr

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SKETCHY_ROOT = BACKEND_ROOT / "data" / "sketchy"
ARCHIVE_PATH = SKETCHY_ROOT / "sketches-06-04.7z"
EXTRACT_ROOT = SKETCHY_ROOT / "extracted"
EXPECTED_ARCHIVE_BYTES = 1_054_609_993
EXPECTED_ARCHIVE_SHA256 = "a79a6a62aa81c4f057f2e9ec9f39a57df9addf35416ec9a2fe100fc3e90aed25"
# SketchKit, çıkartılmış klasörün içerik MD5'ini bu değerle karşılaştırır.
SKETCHKIT_DIR_MD5 = "73bb8cb745dd7945ee8c998a58bf9f0a"
TRANSLATIONS_PATH = BACKEND_ROOT / "data" / "quickdraw_categories_tr.json"
INDEX_PATH = SKETCHY_ROOT / "category_index.json"
EXTENSION_DIR = BACKEND_ROOT.parent / "extension" / "assets" / "sketchy"
DRAWINGS_PER_CATEGORY = 8
# Klasör adı Quick Draw anahtarıyla birebir örtüşmeyen kategoriler.
QUICKDRAW_ALIASES = {
    "ape": "monkey",
    "car_(sedan)": "car",
    "crocodilian": "crocodile",
    "hermit_crab": "crab",
    "hotdog": "hot dog",
    "motorcycle": "motorbike",
    "racket": "tennis racquet",
    "songbird": "bird",
    "teddy_bear": "teddy-bear",
    "turtle": "sea turtle",
    "wading_bird": "bird",
}
# Quick Draw'da karşılığı olmayan, Gartic kelime listesine göre Türkçe adlar.
EXTRA_TURKISH = {
    "armor": ["zırh"],
    "beetle": ["böcek"],
    "bell": ["zil", "çan"],
    "blimp": ["zeplin"],
    "cabin": ["külübe", "kulübe"],
    "chicken": ["tavuk"],
    "deer": ["geyik"],
    "geyser": ["gayzer"],
    "jack-o-lantern": ["balkabağı"],
    "jellyfish": ["deniz anası", "denizanası"],
    "lizard": ["kertenkele"],
    "pistol": ["tabanca", "silah"],
    "pretzel": ["pretzel"],
    "ray": ["vatoz"],
    "rocket": ["roket"],
    "seagull": ["martı"],
    "seal": ["fok"],
    "starfish": ["denizyıldızı", "deniz yıldızı"],
    "tank": ["tank"],
    "volcano": ["volkan", "yanardağ"],
    "wheelchair": ["tekerlekli sandalye"],
    "window": ["pencere"],
    "turtle": ["kaplumbağa"],
}
INVALID_HEADINGS = {
    "invalid/error",
    "unidentifiable/ambiguous",
    "context",
    "perspective",
}
SVG_SAMPLE_COUNT = 3


def normalize_turkish(text: str) -> str:
    lowered = text.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
    return re.sub(r"\s+", " ", lowered).strip()


def verify_archive_hash() -> None:
    digest = hashlib.sha256()
    size = 0
    with ARCHIVE_PATH.open("rb") as archive_file:
        while True:
            block = archive_file.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            digest.update(block)
    checksum = digest.hexdigest()
    if size != EXPECTED_ARCHIVE_BYTES or checksum != EXPECTED_ARCHIVE_SHA256:
        raise RuntimeError(f"Arşiv bütünlüğü bozuk: {size} bayt, SHA-256 {checksum}")


def extract_archive() -> None:
    sketches_dir = EXTRACT_ROOT / "sketches"
    if sketches_dir.exists():
        extracted_files = sum(1 for path in sketches_dir.rglob("*") if path.is_file())
        if extracted_files > 0:
            print(f"Çıkartılmış klasör var: {extracted_files} dosya")
            return
    print("Arşiv çıkartılıyor...")
    EXTRACT_ROOT.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(ARCHIVE_PATH, mode="r") as archive:
        archive.extractall(path=EXTRACT_ROOT)
    print("Çıkartma bitti")


def directory_md5(root: Path) -> str:
    """SketchKit dir_md5 ile aynı: gizli dosyalar hariç, POSIX yol sırasıyla içerik."""
    relative_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )
    digest = hashlib.md5()
    for relative_path in relative_paths:
        with (root / relative_path).open("rb") as file_handle:
            while True:
                block = file_handle.read(8192)
                if not block:
                    break
                digest.update(block)
    return digest.hexdigest()


def read_invalid_names(category_dir: Path) -> set[str]:
    invalid_path = category_dir / "invalid.txt"
    if not invalid_path.exists():
        return set()
    invalid_names: set[str] = set()
    for line in invalid_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        name = line.strip()
        if not name or name.lower() in INVALID_HEADINGS:
            continue
        invalid_names.add(name if name.endswith(".svg") else f"{name}.svg")
    return invalid_names


def inspect_svg(svg_path: Path) -> dict[str, object]:
    text = svg_path.read_text(encoding="utf-8", errors="ignore")
    view_box = re.search(r'viewBox="([^"]+)"', text)
    width = re.search(r'\bwidth="([^"]+)"', text)
    height = re.search(r'\bheight="([^"]+)"', text)
    return {
        "bytes": svg_path.stat().st_size,
        "view_box": view_box.group(1) if view_box else None,
        "width": width.group(1) if width else None,
        "height": height.group(1) if height else None,
        "path_count": len(re.findall(r"<path\b", text)),
        "has_transform": "transform=" in text,
    }


def turkish_words_for_category(
    category: str, turkish_by_quickdraw: dict[str, list[str]]
) -> list[str]:
    spaced = re.sub(r"\s+", " ", category.replace("_", " ").replace("-", " ")).strip()
    lookup_names = [category, category.replace("_", " "), spaced]
    alias = QUICKDRAW_ALIASES.get(category)
    if alias:
        lookup_names.append(alias)
    words: list[str] = []
    for name in lookup_names:
        for word in turkish_by_quickdraw.get(name, []):
            normalized = normalize_turkish(word)
            if normalized not in words:
                words.append(normalized)
    for word in EXTRA_TURKISH.get(category, []):
        normalized = normalize_turkish(word)
        if normalized not in words:
            words.append(normalized)
    return words


COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
HIDDEN_GROUP_PATTERN = re.compile(r'<g display="none">.*?</g>', re.DOTALL)
TIMING_ATTRIBUTE_PATTERN = re.compile(r'\s+t="[^"]*"')


def sanitize_svg(svg_text: str) -> str:
    """Yorum, Flickr bağlantısı ve çizim zamanı özniteliklerini çıkarır."""
    without_notes = HIDDEN_GROUP_PATTERN.sub("", COMMENT_PATTERN.sub("", svg_text))
    return TIMING_ATTRIBUTE_PATTERN.sub("", without_notes)


def export_extension_subset(turkish_by_quickdraw: dict[str, list[str]]) -> None:
    """Her kategorinin en küçük geçerli çizimlerinden sınırlı bir kopya yazar."""
    sketches_dir = EXTRACT_ROOT / "sketches"
    if EXTENSION_DIR.exists():
        for old_path in EXTENSION_DIR.rglob("*"):
            if old_path.is_file():
                old_path.unlink()
    translations: dict[str, list[str]] = {}
    drawing_counts: dict[str, int] = {}
    exported_bytes = 0
    for category_dir in sorted(path for path in sketches_dir.iterdir() if path.is_dir()):
        turkish_words = turkish_words_for_category(category_dir.name, turkish_by_quickdraw)
        if not turkish_words:
            continue
        invalid_names = read_invalid_names(category_dir)
        svg_paths = [path for path in category_dir.glob("*.svg") if path.name not in invalid_names]
        svg_paths.sort(key=lambda path: (path.stat().st_size, path.name))
        chosen = svg_paths[:DRAWINGS_PER_CATEGORY]
        if not chosen:
            continue
        target_dir = EXTENSION_DIR / category_dir.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for index, svg_path in enumerate(chosen, start=1):
            cleaned = sanitize_svg(svg_path.read_text(encoding="utf-8", errors="ignore"))
            if "<path" not in cleaned:
                raise RuntimeError(f"SVG çizim içermiyor: {svg_path}")
            payload = cleaned.encode("utf-8")
            (target_dir / f"{index}.svg").write_bytes(payload)
            exported_bytes += len(payload)
        translations[category_dir.name] = turkish_words
        drawing_counts[category_dir.name] = len(chosen)
    extension_index = {
        "attribution": "Sketchy Database (Sangkloy et al., Georgia Tech)",
        "drawings_per_category": DRAWINGS_PER_CATEGORY,
        "translations": translations,
        "drawing_counts": drawing_counts,
    }
    (EXTENSION_DIR / "index.json").write_text(
        json.dumps(extension_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Eklenti alt kümesi: {len(translations)} kategori, "
        f"{sum(drawing_counts.values())} SVG, {exported_bytes / 1024**2:.1f} MB"
    )


def load_quickdraw_translations() -> dict[str, list[str]]:
    raw_translations: dict[str, list[str]] = json.loads(
        TRANSLATIONS_PATH.read_text(encoding="utf-8")
    )
    return {
        category: [normalize_turkish(word) for word in words]
        for category, words in raw_translations.items()
    }


def build_index() -> None:
    sketches_dir = EXTRACT_ROOT / "sketches"
    if not sketches_dir.is_dir():
        raise RuntimeError(f"Kategori klasörü yok: {sketches_dir}")

    turkish_by_quickdraw = load_quickdraw_translations()
    categories: list[dict[str, object]] = []
    total_svg_bytes = 0
    total_valid = 0
    total_invalid = 0
    unmatched: list[str] = []

    for category_dir in sorted(path for path in sketches_dir.iterdir() if path.is_dir()):
        invalid_names = read_invalid_names(category_dir)
        svg_paths = sorted(category_dir.glob("*.svg"))
        valid_paths = [path for path in svg_paths if path.name not in invalid_names]
        svg_bytes = sum(path.stat().st_size for path in svg_paths)
        total_svg_bytes += svg_bytes
        total_valid += len(valid_paths)
        total_invalid += len(svg_paths) - len(valid_paths)
        turkish_words = turkish_words_for_category(category_dir.name, turkish_by_quickdraw)
        if not turkish_words:
            unmatched.append(category_dir.name)
        samples = [
            inspect_svg(path) | {"file": path.name} for path in valid_paths[:SVG_SAMPLE_COUNT]
        ]
        categories.append(
            {
                "category": category_dir.name,
                "turkish_words": turkish_words,
                "svg_count": len(svg_paths),
                "valid_count": len(valid_paths),
                "invalid_count": len(svg_paths) - len(valid_paths),
                "svg_bytes": svg_bytes,
                "samples": samples,
            }
        )

    extracted_file_count = sum(1 for path in EXTRACT_ROOT.rglob("*") if path.is_file())
    content_md5 = directory_md5(EXTRACT_ROOT)
    index = {
        "source": "https://cislab.hkust-gz.edu.cn/projects/sketchkit/datasets/Sketchy/sketches-06-04.7z",
        "archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "extracted_file_count": extracted_file_count,
        "content_md5": content_md5,
        "sketchkit_dir_md5": SKETCHKIT_DIR_MD5,
        "content_md5_matches_sketchkit": content_md5 == SKETCHKIT_DIR_MD5,
        "category_count": len(categories),
        "svg_count": sum(int(item["svg_count"]) for item in categories),
        "valid_svg_count": total_valid,
        "invalid_svg_count": total_invalid,
        "svg_bytes": total_svg_bytes,
        "unmatched_categories": unmatched,
        "categories": categories,
    }
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"İndeks: {len(categories)} kategori, {index['svg_count']} SVG, "
        f"geçerli {total_valid}, geçersiz {total_invalid}, "
        f"{total_svg_bytes / 1024**2:.1f} MB"
    )
    print(f"Çıkartılan dosya: {extracted_file_count}")
    print(f"İçerik MD5: {content_md5} eşleşme={content_md5 == SKETCHKIT_DIR_MD5}")
    print(f"Eşleşmeyen kategori: {len(unmatched)} {unmatched}")
    export_extension_subset(turkish_by_quickdraw)


def refresh_translations_and_export() -> None:
    turkish_by_quickdraw = load_quickdraw_translations()
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    unmatched: list[str] = []
    for item in index["categories"]:
        words = turkish_words_for_category(str(item["category"]), turkish_by_quickdraw)
        item["turkish_words"] = words
        if not words:
            unmatched.append(str(item["category"]))
    index["unmatched_categories"] = unmatched
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Eşleşmeyen kategori: {len(unmatched)} {unmatched}")
    export_extension_subset(turkish_by_quickdraw)


def main() -> None:
    if "--export-only" in sys.argv:
        refresh_translations_and_export()
        return
    verify_archive_hash()
    extract_archive()
    build_index()


if __name__ == "__main__":
    main()
