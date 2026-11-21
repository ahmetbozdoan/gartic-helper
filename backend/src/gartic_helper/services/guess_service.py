"""Quick Draw sınıflandırıcısı, CLIP sıralaması ve ipucu eşleştirmesini birleştiren servis."""

from itertools import zip_longest

from gartic_helper.models.schemas import GuessRequest, GuessResponse
from gartic_helper.services.category_translator import CategoryTranslator
from gartic_helper.services.clip_word_ranker import ClipWordRanker
from gartic_helper.services.drawing_preprocessor import EmptyDrawingError, preprocess_drawing
from gartic_helper.services.learned_word_store import LearnedWordStore
from gartic_helper.services.quickdraw_classifier import (
    ClassifierUnavailableError,
    QuickDrawClassifier,
)
from gartic_helper.services.word_matcher import (
    WordMatcher,
    normalize_hint_pattern,
    word_matches_pattern,
)
from gartic_helper.utils.image_utils import decode_image_data_url
from gartic_helper.utils.logging_utils import get_logger
from gartic_helper.utils.text_utils import normalize_turkish

logger = get_logger(__name__)

# Gartic "çok yakın!" mesajını cevaptan bir-iki harf farklı tahminlerde gösterir.
CLOSE_GUESS_MAX_DISTANCE = 2


class GuessService:
    def __init__(
        self,
        word_matcher: WordMatcher,
        classifier: QuickDrawClassifier,
        category_translator: CategoryTranslator,
        learned_word_store: LearnedWordStore,
        classifier_top_k: int,
        clip_ranker: ClipWordRanker,
        clip_top_k: int,
    ) -> None:
        self._word_matcher = word_matcher
        self._classifier = classifier
        self._category_translator = category_translator
        self._learned_word_store = learned_word_store
        # İpucu kalıbı modelin ilk tahminlerini eleyebileceği için geniş bir aday havuzu istenir.
        self._classifier_top_k = classifier_top_k
        self._clip_ranker = clip_ranker
        self._clip_top_k = clip_top_k

    def guess(self, request: GuessRequest) -> GuessResponse:
        hint_pattern = (
            normalize_hint_pattern(request.hint_pattern) if request.hint_pattern else None
        )
        close_guesses = [normalize_turkish(word) for word in request.close_guesses]
        excluded_words = {
            *(normalize_turkish(word) for word in request.excluded_words),
            *close_guesses,
        }
        close_matches = [
            word
            for close_guess in close_guesses
            for word in self._word_matcher.find_similar_words(close_guess, CLOSE_GUESS_MAX_DISTANCE)
            if not hint_pattern or word_matches_pattern(word, hint_pattern)
        ]

        pattern_matches = (
            [
                word
                for word in self._word_matcher.filter_by_pattern(hint_pattern)
                if word not in excluded_words
            ]
            if hint_pattern
            else []
        )
        # Oyunda sık çıkan kelimeler önce önerilir; eşit sayıda olanların sırası korunur.
        pattern_matches.sort(key=lambda word: -self._learned_word_store.count_of(word))

        model_guesses: list[str] = []
        clip_guesses: list[str] = []
        warning: str | None = None
        if request.image_data_url:
            is_empty_drawing = False
            try:
                model_guesses = self._classify_drawing(request.image_data_url)
            except EmptyDrawingError:
                is_empty_drawing = True
            except (ClassifierUnavailableError, ValueError, OSError) as error:
                logger.warning("Çizim sınıflandırılamadı: pattern=%r error=%s", hint_pattern, error)
                warning = str(error)
            if not is_empty_drawing:
                # İpucu varsa CLIP yalnızca kalıba uyan kelimeler arasında seçim yapar.
                clip_candidate_words = (
                    pattern_matches if hint_pattern else list(self._word_matcher.words)
                )
                clip_guesses = self._rank_with_clip(request.image_data_url, clip_candidate_words)

        if hint_pattern:
            # İpucu kesin bilgi olduğu için kalıba uymayan model tahminleri elenir.
            model_guesses = [
                guess for guess in model_guesses if word_matches_pattern(guess, hint_pattern)
            ]

        # Quick Draw kendi kategorilerinde çok daha isabetli olduğu için öne alınır; CLIP önerileri
        # araya serpiştirilerek Quick Draw'da olmayan kelimeler de ilk sıralarda görünür.
        interleaved_guesses = [
            word
            for guess_pair in zip_longest(model_guesses, clip_guesses)
            for word in guess_pair
            if word is not None
        ]
        candidates: dict[str, None] = {}
        # Oyunun "çok yakın" dediği tahmine yazımca benzeyen kelimeler en güçlü ipucudur.
        for word in [*close_matches, *interleaved_guesses, *pattern_matches]:
            if word not in excluded_words:
                candidates.setdefault(word, None)

        return GuessResponse(
            candidates=list(candidates)[: request.max_candidates],
            pattern_match_count=len(pattern_matches),
            used_model=bool(model_guesses or clip_guesses),
            warning=warning,
        )

    def _rank_with_clip(self, image_data_url: str, candidate_words: list[str]) -> list[str]:
        try:
            image_bytes, _ = decode_image_data_url(image_data_url)
            return self._clip_ranker.rank(image_bytes, candidate_words, top_k=self._clip_top_k)
        except (ValueError, OSError) as error:
            logger.warning(
                "CLIP sıralaması yapılamadı: candidates=%d error=%s", len(candidate_words), error
            )
            return []

    def _classify_drawing(self, image_data_url: str) -> list[str]:
        image_bytes, _ = decode_image_data_url(image_data_url)
        model_input = preprocess_drawing(image_bytes)
        predictions = self._classifier.predict(model_input, top_k=self._classifier_top_k)
        return [
            turkish_word
            for prediction in predictions
            for turkish_word in self._category_translator.to_turkish(prediction.category)
        ]
