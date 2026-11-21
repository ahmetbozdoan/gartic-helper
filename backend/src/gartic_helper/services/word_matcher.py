"""İpucu kalıbına göre kelime listesi filtreleme."""

import json
import threading
from pathlib import Path

from gartic_helper.utils.logging_utils import get_logger
from gartic_helper.utils.text_utils import normalize_turkish

logger = get_logger(__name__)

UNKNOWN_LETTER_CHARS = frozenset({"_", "?", "*"})
# Gartic harfleri JS toUpperCase ile büyüttüğü için "i" de "I" olarak görünür; normalize edilince
# "ı" olan karakter aslında "i" de olabilir.
AMBIGUOUS_DOTLESS_I = "ı"


def normalize_hint_pattern(raw_pattern: str) -> str:
    return normalize_turkish(raw_pattern)


def word_matches_pattern(word: str, pattern: str) -> bool:
    """
    Kelime, kalıpla birebir aynı uzunlukta olmalı. Kalıptaki '_' herhangi bir harfi
    (boşluk hariç) karşılar; kalıptaki 'ı' hem 'ı' hem 'i' olabilir; diğer karakterler
    (açılmış harfler, boşluk, tire) birebir eşleşmelidir.
    """
    normalized_word = normalize_turkish(word)
    if len(normalized_word) != len(pattern):
        return False
    for word_char, pattern_char in zip(normalized_word, pattern, strict=True):
        if pattern_char in UNKNOWN_LETTER_CHARS:
            if word_char == " ":
                return False
        elif word_char != pattern_char and not (
            pattern_char == AMBIGUOUS_DOTLESS_I and word_char == "i"
        ):
            return False
    return True


def edit_distance(first_word: str, second_word: str) -> int:
    """Levenshtein uzaklığı: bir kelimeyi diğerine çeviren en az ekleme/silme/değiştirme sayısı."""
    previous_row = list(range(len(second_word) + 1))
    for first_index, first_char in enumerate(first_word, start=1):
        current_row = [first_index]
        for second_index, second_char in enumerate(second_word, start=1):
            current_row.append(
                min(
                    previous_row[second_index] + 1,
                    current_row[second_index - 1] + 1,
                    previous_row[second_index - 1] + (first_char != second_char),
                )
            )
        previous_row = current_row
    return previous_row[-1]


class WordMatcher:
    def __init__(self, word_list_path: Path, extra_words: tuple[str, ...] = ()) -> None:
        self._word_list_path = word_list_path
        self._extra_words = extra_words
        self._words: tuple[str, ...] | None = None
        self._add_lock = threading.Lock()

    @property
    def words(self) -> tuple[str, ...]:
        if self._words is None:
            self._words = self._load_words()
        return self._words

    def add_word(self, word: str) -> bool:
        """Kelimeyi çalışma sırasında listeye ekler; zaten varsa False döner."""
        normalized_word = normalize_turkish(word)
        with self._add_lock:
            if not normalized_word or normalized_word in self.words:
                return False
            # Tuple yeniden oluşturulur; eşzamanlı filtreleme eski tuple üzerinde güvenle sürer.
            self._words = (*self.words, normalized_word)
        return True

    def _load_words(self) -> tuple[str, ...]:
        try:
            raw_words = json.loads(self._word_list_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.error("Kelime listesi okunamadı: path=%s error=%s", self._word_list_path, error)
            raw_words = []

        unique_words: dict[str, None] = {}
        for raw_word in [*raw_words, *self._extra_words]:
            if isinstance(raw_word, str) and raw_word.strip():
                unique_words.setdefault(normalize_turkish(raw_word), None)
        logger.info(
            "Kelime listesi yüklendi: %d kelime (%s)", len(unique_words), self._word_list_path
        )
        return tuple(unique_words)

    def filter_by_pattern(self, pattern: str) -> list[str]:
        return [word for word in self.words if word_matches_pattern(word, pattern)]

    def find_similar_words(self, word: str, max_distance: int) -> list[str]:
        """Yazımca en fazla max_distance harf farklı kelimeler, en yakından uzağa sıralı."""
        normalized_word = normalize_turkish(word)
        # Büyük "I" normalize edilince "ı" olduğundan "ı" ile "i" eşit sayılır.
        folded_word = normalized_word.replace(AMBIGUOUS_DOTLESS_I, "i")
        distances = {
            candidate: edit_distance(folded_word, candidate.replace(AMBIGUOUS_DOTLESS_I, "i"))
            for candidate in self.words
            # Uzunluk farkı uzaklığın alt sınırıdır; gereksiz hesaplama yapılmaz.
            if abs(len(candidate) - len(normalized_word)) <= max_distance
        }
        similar_words = [
            candidate
            for candidate, distance in distances.items()
            if candidate != normalized_word and distance <= max_distance
        ]
        return sorted(similar_words, key=lambda candidate: distances[candidate])
