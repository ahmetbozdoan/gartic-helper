"""
Quick Draw'da olmayan kelimeler için internetten çizim kılavuzu (simge) arama.

Iconify (https://iconify.design) 200 binden fazla açık lisanslı simgeyi anahtarsız bir API ile
sunar; arama İngilizce çalıştığı için kelime önce İngilizceye çevrilir (Google Translate'in
anahtarsız ucu, ulaşılamazsa MyMemory).
"""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence

from gartic_helper.utils.logging_utils import get_logger

logger = get_logger(__name__)

GOOGLE_TRANSLATE_URL = (
    "https://translate.googleapis.com/translate_a/single"
    "?client=gtx&sl=tr&tl=en&dt=t&dt=bd&q={query}"
)
MAX_DICTIONARY_ALTERNATIVES = 3
MYMEMORY_TRANSLATE_URL = "https://api.mymemory.translated.net/get?q={query}&langpair=tr|en"
ICON_SEARCH_URL = "https://api.iconify.design/search?query={query}&limit=64"
ICON_SVG_URL = "https://api.iconify.design/{prefix}/{name}.svg?height=256"
USER_AGENT = "gartic-helper/0.1"
# Marka/uygulama logoları çizim kılavuzu olarak işe yaramaz.
EXCLUDED_COLLECTION_CATEGORIES = frozenset({"Logos"})
ENGLISH_ARTICLES = ("the ", "a ", "an ")
# Datamuse: anahtarsız İngilizce "anlamca yakın" kelime servisi (https://www.datamuse.com/api/).
RELATED_WORDS_URL = "https://api.datamuse.com/words?max=20&ml={query}"
# Her sorgu bir ağ isteği olduğu için yakın kelime araması sınırlı tutulur.
MAX_RELATED_QUERIES = 6
MAX_ICON_NAME_SUFFIX_LENGTH = 2

# (kelime, yakın kelimeler) → kelimeye benzerliğe göre sıralı yakın kelimeler
RelatedWordRanker = Callable[[str, Sequence[str]], list[str]]


def icon_name_matches_query(icon_name: str, query: str) -> bool:
    """
    Iconify gevşek eşleşme yaptığı için "bliss" araması "blister-pills" getirebilir. Her sorgu
    kelimesi simge adındaki bir parçayla aynı olmalı veya en fazla 2 harflik ekle ("sport" →
    "sports") uzamalı; çok kelimeli sorgularda bitişik yazım da kabul edilir ("firefighter").
    """
    name_tokens = icon_name.split(":", 1)[-1].lower().split("-")
    query_tokens = query.lower().replace("-", " ").split()
    if all(
        any(
            name_token.startswith(query_token)
            and len(name_token) - len(query_token) <= MAX_ICON_NAME_SUFFIX_LENGTH
            for name_token in name_tokens
        )
        for query_token in query_tokens
    ):
        return True
    return len(query_tokens) > 1 and "".join(query_tokens) in "".join(name_tokens)


class WebIconSearchError(RuntimeError):
    """Çeviri veya simge servisine ulaşılamazsa fırlatılır."""


class WebIconSearch:
    def __init__(
        self,
        timeout_seconds: float,
        max_results: int,
        related_word_ranker: RelatedWordRanker | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        # Arama sonuçları alakaya göre sıralı geldiği için yalnızca ilk sonuçlar arasından seçilir.
        self._max_results = max_results
        self._related_word_ranker = related_word_ranker
        self._icons_by_word: dict[str, list[str]] = {}
        self._related_query_by_icon: dict[str, str] = {}
        self._cache_lock = threading.Lock()

    def find_icons(self, word: str) -> list[str]:
        """Kelimeye uygun simge adlarını ("prefix:name") döndürür; sonuçlar önbelleğe alınır."""
        with self._cache_lock:
            cached_icons = self._icons_by_word.get(word)
        if cached_icons is not None:
            return cached_icons

        translations = self._translate_to_english(word)
        queries: dict[str, None] = {}
        for english_word in translations:
            queries.setdefault(english_word, None)
            # Çeviri bazen çoğul döner ("doctors"); simge adları tekil olduğundan tekili de aranır.
            if english_word.endswith("s") and len(english_word) > 3:
                queries.setdefault(english_word[:-1], None)
        queries.setdefault(word, None)
        query_by_icon = self._collect_icons(list(queries))

        related_queries: list[str] = []
        if not query_by_icon and translations:
            # Birebir simge yoksa (örn. "athlete") yakın anlamlı kelimeler (marathoner, swimmer...)
            # CLIP ile kelimeye benzerliğe göre sıralanıp sırayla aranır.
            related_words = self._find_related_words(translations[0])
            if self._related_word_ranker and related_words:
                related_words = self._related_word_ranker(word, related_words)
            related_queries = related_words[:MAX_RELATED_QUERIES]
            query_by_icon = self._collect_icons(related_queries)
            with self._cache_lock:
                self._related_query_by_icon.update(query_by_icon)

        found_icons = list(query_by_icon)
        logger.info(
            "İnternette simge arandı: word=%r queries=%s related_queries=%s found=%d",
            word,
            list(queries),
            related_queries,
            len(found_icons),
        )
        # Boş sonuç geçici bir ağ hatasından da gelebilir; bir sonraki istekte yeniden denensin.
        if found_icons:
            with self._cache_lock:
                self._icons_by_word[word] = found_icons
        return found_icons

    def related_query_for(self, icon_name: str) -> str | None:
        """Simge yakın anlamlı bir kelimeyle bulunduysa o kelimeyi döndürür."""
        with self._cache_lock:
            return self._related_query_by_icon.get(icon_name)

    def _collect_icons(self, queries: Sequence[str]) -> dict[str, str]:
        """Sorguları sırayla arar; simge adı → onu bulan sorgu."""
        query_by_icon: dict[str, str] = {}
        icon_count_by_collection: dict[str, int] = {}
        for query in queries:
            if len(query_by_icon) >= self._max_results:
                break
            for icon_name in self._search_icons(query):
                # Aynı simgenin boyut/kalınlık varyantları sonuçları doldurmasın diye koleksiyon
                # başına sınır uygulanır.
                collection = icon_name.split(":", 1)[0]
                if icon_name in query_by_icon or icon_count_by_collection.get(collection, 0) >= 2:
                    continue
                if len(query_by_icon) >= self._max_results:
                    break
                icon_count_by_collection[collection] = (
                    icon_count_by_collection.get(collection, 0) + 1
                )
                query_by_icon[icon_name] = query
        return query_by_icon

    def _find_related_words(self, english_word: str) -> list[str]:
        try:
            response = json.loads(
                self._request(RELATED_WORDS_URL.format(query=urllib.parse.quote(english_word)))
            )
            return [str(entry["word"]) for entry in response]
        except (WebIconSearchError, json.JSONDecodeError, KeyError, TypeError) as error:
            logger.warning(
                "Yakın anlamlı kelimeler alınamadı: word=%r error=%s", english_word, error
            )
            return []

    def fetch_icon_svg(self, icon_name: str) -> bytes:
        prefix, name = icon_name.split(":", 1)
        return self._request(
            ICON_SVG_URL.format(prefix=urllib.parse.quote(prefix), name=urllib.parse.quote(name))
        )

    def _translate_to_english(self, word: str) -> list[str]:
        """Ana çeviri ve sözlükteki eş anlamlılar (örn. sporcu → athlete, sportsman)."""
        quoted_word = urllib.parse.quote(word)
        try:
            # Yanıt biçimi: [[["athlete", "sporcu", ...]], [["noun", ["athlete", ...], ...]]]
            response = json.loads(self._request(GOOGLE_TRANSLATE_URL.format(query=quoted_word)))
            translations = ["".join(str(segment[0]) for segment in response[0])]
            for dictionary_entry in response[1] or []:
                translations.extend(
                    str(term) for term in dictionary_entry[1][:MAX_DICTIONARY_ALTERNATIVES]
                )
        except (WebIconSearchError, json.JSONDecodeError, IndexError, TypeError) as google_error:
            logger.warning("Google çevirisi başarısız: word=%r error=%s", word, google_error)
            try:
                response = json.loads(
                    self._request(MYMEMORY_TRANSLATE_URL.format(query=quoted_word))
                )
                translations = [str(response["responseData"]["translatedText"])]
            except (WebIconSearchError, json.JSONDecodeError, KeyError, TypeError) as error:
                # Çeviri olmadan da Türkçe kelimeyle arama denenir.
                logger.warning("Kelime çevrilemedi: word=%r error=%s", word, error)
                return []

        cleaned_translations: dict[str, None] = {}
        for translation in translations:
            cleaned_translation = translation.strip().lower()
            for article in ENGLISH_ARTICLES:
                cleaned_translation = cleaned_translation.removeprefix(article)
            if cleaned_translation and cleaned_translation != word:
                cleaned_translations.setdefault(cleaned_translation, None)
        return list(cleaned_translations)

    def _search_icons(self, query: str) -> list[str]:
        try:
            response = json.loads(
                self._request(ICON_SEARCH_URL.format(query=urllib.parse.quote(query)))
            )
        except json.JSONDecodeError as error:
            raise WebIconSearchError(f"Simge araması okunamadı: query={query!r}") from error
        collections = response.get("collections", {})
        return [
            icon_name
            for icon_name in response.get("icons", [])
            if collections.get(icon_name.split(":", 1)[0], {}).get("category")
            not in EXCLUDED_COLLECTION_CATEGORIES
            and icon_name_matches_query(icon_name, query)
        ]

    def _request(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise WebIconSearchError(f"İnternet araması başarısız: {url} ({error})") from error
