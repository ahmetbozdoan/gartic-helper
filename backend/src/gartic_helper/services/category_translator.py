"""Quick Draw İngilizce kategorileri <-> Türkçe kelimeler."""

import json
from pathlib import Path

from gartic_helper.utils.text_utils import normalize_turkish


class CategoryTranslator:
    def __init__(self, translations_path: Path) -> None:
        raw_translations: dict[str, list[str]] = json.loads(
            translations_path.read_text(encoding="utf-8")
        )
        self._turkish_by_category = {
            category: [normalize_turkish(word) for word in turkish_words]
            for category, turkish_words in raw_translations.items()
        }
        self._categories_by_turkish: dict[str, list[str]] = {}
        for category, turkish_words in self._turkish_by_category.items():
            for turkish_word in turkish_words:
                self._categories_by_turkish.setdefault(turkish_word, []).append(category)

    def to_turkish(self, category: str) -> list[str]:
        return self._turkish_by_category.get(category, [])

    def all_turkish_words(self) -> list[str]:
        return list(self._categories_by_turkish)

    def categories_for_word(self, word: str) -> list[str]:
        """
        Önce kelimenin tamamı aranır; bulunamazsa kelimenin parçaları denenir
        (örn. 'yeşil elma' -> 'elma' -> apple).
        """
        normalized_word = normalize_turkish(word)
        exact_categories = self._categories_by_turkish.get(normalized_word)
        if exact_categories:
            return exact_categories
        partial_categories: list[str] = []
        for word_part in normalized_word.split(" "):
            for category in self._categories_by_turkish.get(word_part, []):
                if category not in partial_categories:
                    partial_categories.append(category)
        return partial_categories
