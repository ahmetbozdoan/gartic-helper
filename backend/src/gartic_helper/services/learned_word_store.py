"""Oyunda çıkan kelimeleri ve kaç kez çıktıklarını diskte saklar."""

import json
import threading
from pathlib import Path

from gartic_helper.utils.logging_utils import get_logger
from gartic_helper.utils.text_utils import normalize_turkish

logger = get_logger(__name__)


class LearnedWordStore:
    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path
        self._lock = threading.Lock()
        self._counts: dict[str, int] = self._load()

    def _load(self) -> dict[str, int]:
        if not self._store_path.exists():
            return {}
        try:
            raw_counts = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.error(
                "Öğrenilen kelimeler okunamadı, boş başlanıyor: path=%s error=%s",
                self._store_path,
                error,
            )
            return {}
        return {
            normalize_turkish(word): int(count)
            for word, count in raw_counts.items()
            if isinstance(word, str) and word.strip()
        }

    def _save(self) -> None:
        # Yarım yazılmış dosya kalmasın diye önce geçici dosyaya yazılıp yerine taşınır.
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._store_path.with_suffix(".tmp")
        sorted_counts = dict(sorted(self._counts.items(), key=lambda item: (-item[1], item[0])))
        temporary_path.write_text(
            json.dumps(sorted_counts, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        temporary_path.replace(self._store_path)

    def record(self, word: str) -> tuple[str, int]:
        """Kelimenin görülme sayısını artırır; (normalize kelime, yeni sayı) döner."""
        normalized_word = normalize_turkish(word)
        with self._lock:
            new_count = self._counts.get(normalized_word, 0) + 1
            self._counts[normalized_word] = new_count
            self._save()
        return normalized_word, new_count

    def count_of(self, word: str) -> int:
        return self._counts.get(word, 0)

    def words(self) -> list[str]:
        return list(self._counts)
