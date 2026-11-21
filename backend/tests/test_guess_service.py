import base64
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from gartic_helper.models.schemas import GuessRequest
from gartic_helper.services.category_translator import CategoryTranslator
from gartic_helper.services.guess_service import GuessService
from gartic_helper.services.learned_word_store import LearnedWordStore
from gartic_helper.services.quickdraw_classifier import (
    CategoryPrediction,
    ClassifierUnavailableError,
)
from gartic_helper.services.word_matcher import WordMatcher


def build_drawing_data_url() -> str:
    image = Image.new("RGB", (384, 224), "white")
    ImageDraw.Draw(image).ellipse((120, 40, 260, 180), outline="black", width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


class FakeClassifier:
    def __init__(self, categories: list[str], is_ready: bool = True) -> None:
        self._categories = categories
        self.is_ready = is_ready
        self.received_input_shape: tuple[int, ...] | None = None

    def predict(self, model_input: np.ndarray, top_k: int) -> list[CategoryPrediction]:
        if not self.is_ready:
            raise ClassifierUnavailableError("model yok")
        self.received_input_shape = model_input.shape
        return [CategoryPrediction(category, 0.1) for category in self._categories[:top_k]]


class FakeClipRanker:
    def __init__(self, ranked_words: list[str] | None = None) -> None:
        self._ranked_words = ranked_words or []
        self.received_candidates: list[str] | None = None

    def rank(self, image_bytes: bytes, candidate_words: list[str], top_k: int) -> list[str]:
        self.received_candidates = list(candidate_words)
        return [word for word in self._ranked_words if word in candidate_words][:top_k]


@pytest.fixture
def category_translator(tmp_path: Path) -> CategoryTranslator:
    translations_path = tmp_path / "translations.json"
    translations_path.write_text(
        json.dumps({"lion": ["aslan"], "pear": ["armut"], "clock": ["saat"]}), encoding="utf-8"
    )
    return CategoryTranslator(translations_path)


@pytest.fixture
def word_matcher(tmp_path: Path) -> WordMatcher:
    word_list_path = tmp_path / "words.json"
    word_list_path.write_text(json.dumps(["ayran", "kedi", "kuzu"]), encoding="utf-8")
    return WordMatcher(word_list_path, extra_words=("aslan", "armut", "saat"))


@pytest.fixture
def learned_word_store(tmp_path: Path) -> LearnedWordStore:
    return LearnedWordStore(tmp_path / "learned.json")


def build_guess_service(
    word_matcher: WordMatcher,
    classifier: FakeClassifier,
    category_translator: CategoryTranslator,
    learned_word_store: LearnedWordStore,
    clip_ranker: FakeClipRanker | None = None,
) -> GuessService:
    return GuessService(
        word_matcher=word_matcher,
        classifier=classifier,  # type: ignore[arg-type]
        category_translator=category_translator,
        learned_word_store=learned_word_store,
        classifier_top_k=20,
        clip_ranker=clip_ranker or FakeClipRanker(),  # type: ignore[arg-type]
        clip_top_k=10,
    )


def test_model_guesses_are_filtered_by_pattern_and_merged(
    word_matcher: WordMatcher,
    category_translator: CategoryTranslator,
    learned_word_store: LearnedWordStore,
) -> None:
    fake_classifier = FakeClassifier(["clock", "lion", "pear"])
    guess_service = build_guess_service(
        word_matcher, fake_classifier, category_translator, learned_word_store
    )

    response = guess_service.guess(
        GuessRequest(
            image_data_url=build_drawing_data_url(), hint_pattern="A____", excluded_words=["armut"]
        )
    )

    assert response.candidates == ["aslan", "ayran"]
    assert response.used_model is True
    assert fake_classifier.received_input_shape == (1, 1, 28, 28)


def test_without_pattern_returns_model_order(
    word_matcher: WordMatcher,
    category_translator: CategoryTranslator,
    learned_word_store: LearnedWordStore,
) -> None:
    guess_service = build_guess_service(
        word_matcher, FakeClassifier(["clock", "lion"]), category_translator, learned_word_store
    )

    response = guess_service.guess(GuessRequest(image_data_url=build_drawing_data_url()))

    assert response.candidates == ["saat", "aslan"]


def test_falls_back_to_pattern_matches_when_model_missing(
    word_matcher: WordMatcher,
    category_translator: CategoryTranslator,
    learned_word_store: LearnedWordStore,
) -> None:
    guess_service = build_guess_service(
        word_matcher, FakeClassifier([], is_ready=False), category_translator, learned_word_store
    )

    response = guess_service.guess(
        GuessRequest(image_data_url=build_drawing_data_url(), hint_pattern="k___")
    )

    assert response.candidates == ["kedi", "kuzu"]
    assert response.used_model is False
    assert response.warning is not None


def test_frequently_seen_words_are_suggested_first(
    word_matcher: WordMatcher,
    category_translator: CategoryTranslator,
    learned_word_store: LearnedWordStore,
) -> None:
    learned_word_store.record("kuzu")
    learned_word_store.record("kuzu")
    guess_service = build_guess_service(
        word_matcher, FakeClassifier([]), category_translator, learned_word_store
    )

    response = guess_service.guess(GuessRequest(hint_pattern="k___"))

    assert response.candidates == ["kuzu", "kedi"]


def test_clip_guesses_are_interleaved_with_model_guesses(
    word_matcher: WordMatcher,
    category_translator: CategoryTranslator,
    learned_word_store: LearnedWordStore,
) -> None:
    guess_service = build_guess_service(
        word_matcher,
        FakeClassifier(["clock", "lion"]),
        category_translator,
        learned_word_store,
        clip_ranker=FakeClipRanker(["kedi", "saat", "kuzu"]),
    )

    response = guess_service.guess(GuessRequest(image_data_url=build_drawing_data_url()))

    assert response.candidates == ["saat", "kedi", "aslan", "kuzu"]
    assert response.used_model is True


def test_clip_only_ranks_pattern_matches_when_hint_is_known(
    word_matcher: WordMatcher,
    category_translator: CategoryTranslator,
    learned_word_store: LearnedWordStore,
) -> None:
    fake_clip_ranker = FakeClipRanker(["kuzu", "kedi"])
    guess_service = build_guess_service(
        word_matcher, FakeClassifier([]), category_translator, learned_word_store, fake_clip_ranker
    )

    response = guess_service.guess(
        GuessRequest(image_data_url=build_drawing_data_url(), hint_pattern="k___")
    )

    assert fake_clip_ranker.received_candidates == ["kedi", "kuzu"]
    assert response.candidates == ["kuzu", "kedi"]


def test_words_similar_to_close_guesses_are_suggested_first(
    word_matcher: WordMatcher,
    category_translator: CategoryTranslator,
    learned_word_store: LearnedWordStore,
) -> None:
    guess_service = build_guess_service(
        word_matcher, FakeClassifier(["clock"]), category_translator, learned_word_store
    )

    response = guess_service.guess(
        GuessRequest(image_data_url=build_drawing_data_url(), close_guesses=["KUZI"])
    )

    assert response.candidates == ["kuzu", "kedi", "saat"]
