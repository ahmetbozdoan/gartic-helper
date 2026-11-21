"""Çizilecek kelime için Quick Draw veri setinden line-art kılavuz üretimi."""

import json
import random
from pathlib import Path

from gartic_helper.models.schemas import GuideResponse
from gartic_helper.services.category_translator import CategoryTranslator
from gartic_helper.services.web_icon_search import WebIconSearch
from gartic_helper.services.word_matcher import AMBIGUOUS_DOTLESS_I, WordMatcher
from gartic_helper.utils.image_utils import encode_image_data_url
from gartic_helper.utils.logging_utils import get_logger
from gartic_helper.utils.text_utils import normalize_turkish

logger = get_logger(__name__)

# Quick Draw sadeleştirilmiş çizimleri 0-255 koordinat aralığındadır.
SVG_VIEWBOX = "-12 -12 280 280"
SVG_STROKE_WIDTH = 4

# Tek çizim: [[xs, ys], [xs, ys], ...] (her eleman bir fırça darbesi)
Drawing = list[list[list[int]]]


class GuideNotFoundError(LookupError):
    """Kelimeye karşılık gelen Quick Draw çizimi yoksa fırlatılır."""


def render_drawing_svg(drawing: Drawing) -> str:
    polylines = "".join(
        '<polyline points="' + " ".join(f"{x},{y}" for x, y in zip(xs, ys, strict=True)) + '"/>'
        for xs, ys in drawing
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{SVG_VIEWBOX}">'
        f'<g fill="none" stroke="#000" stroke-width="{SVG_STROKE_WIDTH}" '
        f'stroke-linecap="round" stroke-linejoin="round">{polylines}</g></svg>'
    )


class GuideService:
    def __init__(
        self,
        category_translator: CategoryTranslator,
        guide_drawings_path: Path,
        web_icon_search: WebIconSearch | None = None,
        word_matcher: WordMatcher | None = None,
    ) -> None:
        self._category_translator = category_translator
        self._guide_drawings_path = guide_drawings_path
        self._web_icon_search = web_icon_search
        self._word_matcher = word_matcher
        self._drawings_by_category: dict[str, list[Drawing]] | None = None

    @property
    def drawings_by_category(self) -> dict[str, list[Drawing]]:
        if self._drawings_by_category is None:
            try:
                self._drawings_by_category = json.loads(
                    self._guide_drawings_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as error:
                logger.error(
                    "Kılavuz çizimleri okunamadı: path=%s error=%s",
                    self._guide_drawings_path,
                    error,
                )
                self._drawings_by_category = {}
        return self._drawings_by_category

    def get_guide(self, word: str) -> GuideResponse:
        """Her çağrıda rastgele bir örnek seçilir; tekrar istemek farklı bir çizim getirir."""
        normalized_word = normalize_turkish(word)
        spelling_candidates = self._spelling_candidates(normalized_word)
        for candidate_word in spelling_candidates:
            candidate_drawings = [
                (category, drawing)
                for category in self._category_translator.categories_for_word(candidate_word)
                for drawing in self.drawings_by_category.get(category, [])
            ]
            if candidate_drawings:
                category, drawing = random.choice(candidate_drawings)
                svg_markup = render_drawing_svg(drawing)
                return GuideResponse(
                    word=candidate_word,
                    category=category,
                    image_data_url=encode_image_data_url(
                        svg_markup.encode("utf-8"), "image/svg+xml"
                    ),
                )
        return self._get_web_icon_guide(normalized_word, spelling_candidates)

    def _spelling_candidates(self, normalized_word: str) -> list[str]:
        """
        Gartic çizilecek kelimeyi JS toUpperCase ile gösterdiği için "PIL" hem "pil" hem "pıl"
        olabilir; önce kelime listesinde bilinen yazımlar, sonra olduğu gibi, sonra 'ı'→'i' denenir.
        """
        if AMBIGUOUS_DOTLESS_I not in normalized_word:
            return [normalized_word]
        known_spellings = (
            self._word_matcher.filter_by_pattern(normalized_word) if self._word_matcher else []
        )
        candidates = [
            *known_spellings,
            normalized_word,
            normalized_word.replace(AMBIGUOUS_DOTLESS_I, "i"),
        ]
        return list(dict.fromkeys(candidates))

    def _get_web_icon_guide(
        self, normalized_word: str, spelling_candidates: list[str]
    ) -> GuideResponse:
        """WebIconSearchError (ağ hatası) çağırana iletilir."""
        if self._web_icon_search:
            for candidate_word in spelling_candidates:
                icon_names = self._web_icon_search.find_icons(candidate_word)
                if icon_names:
                    icon_name = random.choice(icon_names)
                    related_query = self._web_icon_search.related_query_for(icon_name)
                    source_label = (
                        f"internet, yakın anlam '{related_query}'" if related_query else "internet"
                    )
                    return GuideResponse(
                        word=candidate_word,
                        category=f"{source_label}: {icon_name}",
                        image_data_url=encode_image_data_url(
                            self._web_icon_search.fetch_icon_svg(icon_name), "image/svg+xml"
                        ),
                    )
        raise GuideNotFoundError(f"'{normalized_word}' için çizim bulunamadı")
