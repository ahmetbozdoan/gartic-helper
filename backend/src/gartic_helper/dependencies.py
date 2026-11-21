"""Servislerin tekil (singleton) örnekleri; FastAPI Depends ile enjekte edilir."""

from functools import lru_cache

from gartic_helper.config import get_settings
from gartic_helper.services.category_translator import CategoryTranslator
from gartic_helper.services.clip_word_ranker import ClipWordRanker
from gartic_helper.services.guess_service import GuessService
from gartic_helper.services.guide_service import GuideService
from gartic_helper.services.learned_word_store import LearnedWordStore
from gartic_helper.services.quickdraw_classifier import QuickDrawClassifier
from gartic_helper.services.web_icon_search import WebIconSearch
from gartic_helper.services.word_learning_service import WordLearningService
from gartic_helper.services.word_matcher import WordMatcher


@lru_cache
def get_category_translator() -> CategoryTranslator:
    return CategoryTranslator(get_settings().category_translations_path)


@lru_cache
def get_quickdraw_classifier() -> QuickDrawClassifier:
    settings = get_settings()
    return QuickDrawClassifier(settings.classifier_model_path, settings.classifier_labels_path)


@lru_cache
def get_clip_word_ranker() -> ClipWordRanker:
    settings = get_settings()
    return ClipWordRanker(
        model_name=settings.clip_model_name,
        pretrained=settings.clip_pretrained,
        prompt_template=settings.clip_prompt_template,
        embedding_cache_path=settings.clip_embedding_cache_path,
        enabled=settings.clip_enabled,
    )


@lru_cache
def get_learned_word_store() -> LearnedWordStore:
    return LearnedWordStore(get_settings().learned_words_path)


@lru_cache
def get_word_matcher() -> WordMatcher:
    return WordMatcher(
        get_settings().word_list_path,
        extra_words=(
            *get_category_translator().all_turkish_words(),
            *get_learned_word_store().words(),
        ),
    )


@lru_cache
def get_guess_service() -> GuessService:
    return GuessService(
        word_matcher=get_word_matcher(),
        classifier=get_quickdraw_classifier(),
        category_translator=get_category_translator(),
        learned_word_store=get_learned_word_store(),
        classifier_top_k=get_settings().classifier_top_k,
        clip_ranker=get_clip_word_ranker(),
        clip_top_k=get_settings().clip_top_k,
    )


@lru_cache
def get_web_icon_search() -> WebIconSearch:
    settings = get_settings()
    return WebIconSearch(
        timeout_seconds=settings.web_icon_search_timeout_seconds,
        max_results=settings.web_icon_search_max_results,
        related_word_ranker=get_clip_word_ranker().rank_related_words,
    )


@lru_cache
def get_guide_service() -> GuideService:
    settings = get_settings()
    return GuideService(
        category_translator=get_category_translator(),
        guide_drawings_path=settings.guide_drawings_path,
        web_icon_search=get_web_icon_search() if settings.web_icon_search_enabled else None,
        word_matcher=get_word_matcher(),
    )


@lru_cache
def get_word_learning_service() -> WordLearningService:
    return WordLearningService(
        learned_word_store=get_learned_word_store(), word_matcher=get_word_matcher()
    )
