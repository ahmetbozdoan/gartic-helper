"""Türkçe metin normalizasyon yardımcıları."""

import re

# str.lower() 'I' -> 'i' ve 'İ' -> 'i̇' (birleşik nokta) üretir; Türkçe için önce elle çevrilir.
TURKISH_UPPER_TO_LOWER = str.maketrans({"I": "ı", "İ": "i"})
WHITESPACE_REGEX = re.compile(r"\s+")


def normalize_turkish(text: str) -> str:
    """Türkçe kurallarıyla küçük harfe çevirir, baştaki/sondaki ve çoklu boşlukları sadeleştirir."""
    lowered_text = text.translate(TURKISH_UPPER_TO_LOWER).lower()
    return WHITESPACE_REGEX.sub(" ", lowered_text).strip()
