"""Sketchy SVG arşivini paralel indirir ve beklenen bayt sayısıyla doğrular."""

from __future__ import annotations

import hashlib
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

URL = "https://cislab.hkust-gz.edu.cn/projects/sketchkit/datasets/Sketchy/sketches-06-04.7z"
EXPECTED_SIZE = 1_054_609_993
ARCHIVE_PATH = Path(__file__).resolve().parents[1] / "data" / "sketchy" / "sketches-06-04.7z"
CHUNK_BYTES = 4 * 1024 * 1024
WORKER_COUNT = 16
SEVEN_ZIP_MAGIC = bytes.fromhex("377ABCAF271C")


def _fetch_range(start: int, end: int) -> bytes:
    request = urllib.request.Request(
        URL,
        headers={"Range": f"bytes={start}-{end}", "User-Agent": "gartic-helper"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        if response.status != 206:
            raise RuntimeError(f"Aralık yanıtı 206 değil: {response.status} ({start}-{end})")
        payload = response.read()
    expected_length = end - start + 1
    if len(payload) != expected_length:
        raise RuntimeError(
            f"Aralık eksik: {start}-{end}, gelen {len(payload)}, beklenen {expected_length}"
        )
    return payload


def download_archive() -> None:
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing_size = ARCHIVE_PATH.stat().st_size if ARCHIVE_PATH.exists() else 0
    if existing_size > EXPECTED_SIZE:
        raise RuntimeError(f"Arşiv beklenenden büyük: {existing_size}")
    if existing_size == EXPECTED_SIZE:
        print(f"Arşiv zaten tam: {existing_size} bayt")
        return

    ranges = [
        (start, min(start + CHUNK_BYTES, EXPECTED_SIZE) - 1)
        for start in range(existing_size, EXPECTED_SIZE, CHUNK_BYTES)
    ]
    if not ARCHIVE_PATH.exists():
        ARCHIVE_PATH.write_bytes(b"")

    completed_bytes = existing_size
    started_at = time.perf_counter()
    progress_lock = threading.Lock()

    def store_range(span: tuple[int, int]) -> int:
        start, end = span
        payload = _fetch_range(start, end)
        with ARCHIVE_PATH.open("r+b") as archive_file:
            archive_file.seek(start)
            archive_file.write(payload)
        return len(payload)

    print(f"İndiriliyor: {len(ranges)} parça, {existing_size} bayttan devam")
    with ThreadPoolExecutor(max_workers=WORKER_COUNT) as pool:
        futures = [pool.submit(store_range, span) for span in ranges]
        for future in as_completed(futures):
            written = future.result()
            with progress_lock:
                completed_bytes += written
                elapsed = time.perf_counter() - started_at
                rate = (completed_bytes - existing_size) / elapsed if elapsed else 0
                print(
                    f"{completed_bytes / EXPECTED_SIZE:.1%} "
                    f"{completed_bytes / 1024**2:.1f} MB "
                    f"{rate / 1024:.0f} KB/s",
                    flush=True,
                )

    final_size = ARCHIVE_PATH.stat().st_size
    if final_size != EXPECTED_SIZE:
        raise RuntimeError(f"Boyut uyuşmuyor: {final_size} != {EXPECTED_SIZE}")


def verify_archive() -> str:
    size = ARCHIVE_PATH.stat().st_size
    if size != EXPECTED_SIZE:
        raise RuntimeError(f"Boyut uyuşmuyor: {size} != {EXPECTED_SIZE}")
    digest = hashlib.sha256()
    with ARCHIVE_PATH.open("rb") as archive_file:
        header = archive_file.read(6)
        if header != SEVEN_ZIP_MAGIC:
            raise RuntimeError(f"7z imzası geçersiz: {header.hex()}")
        digest.update(header)
        while True:
            block = archive_file.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    checksum = digest.hexdigest()
    print(f"Boyut doğrulandı: {size} bayt")
    print(f"SHA-256: {checksum}")
    return checksum


def main() -> None:
    download_archive()
    verify_archive()


if __name__ == "__main__":
    main()
