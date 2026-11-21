import json
from pathlib import Path

from gartic_helper.services.word_matcher import WordMatcher, word_matches_pattern
from gartic_helper.utils.text_utils import normalize_turkish


def test_normalize_turkish_handles_dotted_and_dotless_i() -> None:
    assert normalize_turkish("  IŞIK  İNEK ") == "ışık inek"


def test_pattern_with_unknown_letters() -> None:
    assert word_matches_pattern("aslan", "_s__n")
    assert not word_matches_pattern("aslan", "_s__")
    assert not word_matches_pattern("kaplan", "_s___n")


def test_pattern_with_space_between_words() -> None:
    assert word_matches_pattern("su aygırı", "__ ______")
    assert not word_matches_pattern("su aygırı", "_________")


def test_uppercase_i_from_gartic_matches_both_i_and_dotless_i() -> None:
    gartic_pattern = normalize_turkish("PIL")
    assert word_matches_pattern("pil", gartic_pattern)
    assert word_matches_pattern("ışık", normalize_turkish("I___"))
    assert not word_matches_pattern("pil", normalize_turkish("P_L_"))
    assert not word_matches_pattern("pıl", "pil")


def test_word_matcher_filters_and_deduplicates(tmp_path: Path) -> None:
    word_list_path = tmp_path / "words.json"
    word_list_path.write_text(json.dumps(["Elma", "elma", "Armut", "erik"]), encoding="utf-8")
    word_matcher = WordMatcher(word_list_path)

    assert word_matcher.words == ("elma", "armut", "erik")
    assert word_matcher.filter_by_pattern("e___") == ["elma", "erik"]


def test_word_matcher_returns_empty_on_missing_file(tmp_path: Path) -> None:
    assert WordMatcher(tmp_path / "missing.json").filter_by_pattern("____") == []
