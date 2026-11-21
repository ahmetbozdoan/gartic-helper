"""Tur sonunda açıklanan cevapları kalıcı olarak öğrenir."""

from gartic_helper.models.schemas import LearnWordResponse
from gartic_helper.services.learned_word_store import LearnedWordStore
from gartic_helper.services.word_matcher import WordMatcher
from gartic_helper.utils.logging_utils import get_logger

logger = get_logger(__name__)


class WordLearningService:
    def __init__(self, learned_word_store: LearnedWordStore, word_matcher: WordMatcher) -> None:
        self._learned_word_store = learned_word_store
        self._word_matcher = word_matcher

    def learn(self, word: str) -> LearnWordResponse:
        normalized_word, seen_count = self._learned_word_store.record(word)
        is_new_word = self._word_matcher.add_word(normalized_word)
        logger.info(
            "Kelime öğrenildi: word=%r count=%d new=%s", normalized_word, seen_count, is_new_word
        )
        return LearnWordResponse(word=normalized_word, seen_count=seen_count, is_new=is_new_word)
