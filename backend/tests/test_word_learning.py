import json
from pathlib import Path

from fastapi.testclient import TestClient

from gartic_helper.dependencies import get_word_learning_service
from gartic_helper.main import app
from gartic_helper.services.learned_word_store import LearnedWordStore
from gartic_helper.services.word_learning_service import WordLearningService
from gartic_helper.services.word_matcher import WordMatcher


def build_learning_service(tmp_path: Path) -> tuple[WordLearningService, WordMatcher, Path]:
    word_list_path = tmp_path / "words.json"
    word_list_path.write_text(json.dumps(["elma"]), encoding="utf-8")
    store_path = tmp_path / "learned.json"
    word_matcher = WordMatcher(word_list_path)
    return WordLearningService(LearnedWordStore(store_path), word_matcher), word_matcher, store_path


def test_learning_adds_new_word_and_counts_repeats(tmp_path: Path) -> None:
    learning_service, word_matcher, store_path = build_learning_service(tmp_path)

    first_response = learning_service.learn("Sonbahar")
    second_response = learning_service.learn("sonbahar")

    assert (first_response.is_new, first_response.seen_count) == (True, 1)
    assert (second_response.is_new, second_response.seen_count) == (False, 2)
    assert word_matcher.filter_by_pattern("s_______") == ["sonbahar"]
    assert json.loads(store_path.read_text(encoding="utf-8")) == {"sonbahar": 2}


def test_learned_words_survive_restart(tmp_path: Path) -> None:
    store_path = tmp_path / "learned.json"
    LearnedWordStore(store_path).record("yeşil elma")

    reloaded_store = LearnedWordStore(store_path)

    assert reloaded_store.words() == ["yeşil elma"]
    assert reloaded_store.count_of("yeşil elma") == 1


def test_learn_endpoint(tmp_path: Path) -> None:
    learning_service, _, _ = build_learning_service(tmp_path)
    app.dependency_overrides[get_word_learning_service] = lambda: learning_service
    try:
        response = TestClient(app).post("/words/learn", json={"word": "SPORCU"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"word": "sporcu", "seen_count": 1, "is_new": True}
