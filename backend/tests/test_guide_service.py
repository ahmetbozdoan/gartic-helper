import base64
import json
from pathlib import Path

import pytest

from gartic_helper.services.category_translator import CategoryTranslator
from gartic_helper.services.guide_service import GuideNotFoundError, GuideService
from gartic_helper.services.word_matcher import WordMatcher


@pytest.fixture
def guide_service(tmp_path: Path) -> GuideService:
    translations_path = tmp_path / "translations.json"
    translations_path.write_text(json.dumps({"apple": ["elma"]}), encoding="utf-8")
    drawings_path = tmp_path / "drawings.json"
    drawings_path.write_text(
        json.dumps({"apple": [[[[0, 100, 200], [0, 255, 0]]]]}), encoding="utf-8"
    )
    return GuideService(CategoryTranslator(translations_path), drawings_path)


def test_guide_renders_svg_for_exact_and_partial_words(guide_service: GuideService) -> None:
    for word in ["Elma", "yeşil elma"]:
        response = guide_service.get_guide(word)
        assert response.category == "apple"
        prefix = "data:image/svg+xml;base64,"
        assert response.image_data_url.startswith(prefix)
        svg_markup = base64.b64decode(response.image_data_url[len(prefix) :]).decode()
        assert '<polyline points="0,0 100,255 200,0"/>' in svg_markup


def test_unknown_word_raises(guide_service: GuideService) -> None:
    with pytest.raises(GuideNotFoundError):
        guide_service.get_guide("sonbahar")


class FakeWebIconSearch:
    def __init__(self, icons_by_word: dict[str, list[str]]) -> None:
        self._icons_by_word = icons_by_word

    def find_icons(self, word: str) -> list[str]:
        return self._icons_by_word.get(word, [])

    def related_query_for(self, icon_name: str) -> str | None:
        return None

    def fetch_icon_svg(self, icon_name: str) -> bytes:
        return f'<svg data-icon="{icon_name}"/>'.encode()


def test_falls_back_to_web_icon_when_quickdraw_has_no_drawing(tmp_path: Path) -> None:
    translations_path = tmp_path / "translations.json"
    translations_path.write_text(json.dumps({}), encoding="utf-8")
    drawings_path = tmp_path / "drawings.json"
    drawings_path.write_text(json.dumps({}), encoding="utf-8")
    guide_service = GuideService(
        CategoryTranslator(translations_path),
        drawings_path,
        FakeWebIconSearch({"evren": ["tabler:universe"]}),  # type: ignore[arg-type]
    )

    response = guide_service.get_guide("Evren")

    assert response.category == "internet: tabler:universe"
    prefix = "data:image/svg+xml;base64,"
    assert base64.b64decode(response.image_data_url[len(prefix) :]) == (
        b'<svg data-icon="tabler:universe"/>'
    )
    with pytest.raises(GuideNotFoundError):
        guide_service.get_guide("sonbahar")


def test_uppercase_gartic_word_resolves_dotted_i_spelling(tmp_path: Path) -> None:
    translations_path = tmp_path / "translations.json"
    translations_path.write_text(json.dumps({}), encoding="utf-8")
    drawings_path = tmp_path / "drawings.json"
    drawings_path.write_text(json.dumps({}), encoding="utf-8")
    word_list_path = tmp_path / "words.json"
    word_list_path.write_text(json.dumps(["pil"]), encoding="utf-8")
    guide_service = GuideService(
        CategoryTranslator(translations_path),
        drawings_path,
        FakeWebIconSearch({"pil": ["mdi:battery"]}),  # type: ignore[arg-type]
        WordMatcher(word_list_path),
    )

    response = guide_service.get_guide("PIL")

    assert response.word == "pil"
    assert response.category == "internet: mdi:battery"
