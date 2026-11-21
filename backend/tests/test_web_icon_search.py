from collections.abc import Sequence

from gartic_helper.services.web_icon_search import WebIconSearch, icon_name_matches_query


def test_icon_name_must_contain_query_words() -> None:
    assert icon_name_matches_query("fluent:sport-16-filled", "sport")
    assert icon_name_matches_query("mdi:doctors-bag", "doctor")
    assert icon_name_matches_query("game-icons:firefighter", "fire fighter")
    assert icon_name_matches_query("mdi:fairy", "fairy")
    assert not icon_name_matches_query("healthicons:blister-pills-oval-x1", "bliss")
    assert not icon_name_matches_query("mdi:sportscar", "sport")


class OfflineWebIconSearch(WebIconSearch):
    """Ağ isteği yerine sabit sonuçlar döndürür."""

    def __init__(self, icons_by_query: dict[str, list[str]], **kwargs) -> None:
        super().__init__(timeout_seconds=1, max_results=12, **kwargs)
        self._icons_by_query = icons_by_query
        self.searched_queries: list[str] = []

    def _translate_to_english(self, word: str) -> list[str]:
        return ["athlete"]

    def _search_icons(self, query: str) -> list[str]:
        self.searched_queries.append(query)
        return self._icons_by_query.get(query, [])

    def _find_related_words(self, english_word: str) -> list[str]:
        return ["jock", "gym", "swimmer"]


def test_related_words_are_ranked_and_searched_when_no_direct_icon() -> None:
    def rank_by_preference(word: str, related_words: Sequence[str]) -> list[str]:
        return sorted(related_words, key=lambda related: related != "swimmer")

    icon_search = OfflineWebIconSearch(
        {"swimmer": ["mdi:swim"], "gym": ["mdi:dumbbell"]}, related_word_ranker=rank_by_preference
    )

    icons = icon_search.find_icons("sporcu")

    assert icons == ["mdi:swim", "mdi:dumbbell"]
    assert icon_search.searched_queries == ["athlete", "sporcu", "swimmer", "jock", "gym"]
    assert icon_search.related_query_for("mdi:swim") == "swimmer"


def test_related_words_are_not_used_when_direct_icon_exists() -> None:
    icon_search = OfflineWebIconSearch({"athlete": ["mdi:run"]})

    assert icon_search.find_icons("sporcu") == ["mdi:run"]
    assert icon_search.related_query_for("mdi:run") is None
    assert icon_search.searched_queries == ["athlete", "sporcu"]
