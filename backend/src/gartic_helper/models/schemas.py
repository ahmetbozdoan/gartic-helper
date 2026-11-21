"""API istek ve yanıt modelleri."""

from pydantic import BaseModel, Field


class GuessRequest(BaseModel):
    image_data_url: str | None = Field(
        default=None, description="Canvas görüntüsü, 'data:image/png;base64,...' biçiminde"
    )
    hint_pattern: str | None = Field(
        default=None,
        description="İpucu kalıbı: '_' bilinmeyen harf, boşluk kelime ayırıcı. Örn: '__a__ ___'",
    )
    excluded_words: list[str] = Field(
        default_factory=list, description="Daha önce denenmiş yanlış tahminler"
    )
    close_guesses: list[str] = Field(
        default_factory=list, description="Oyunun 'çok yakın!' dediği yanlış tahminler"
    )
    max_candidates: int = Field(default=5, ge=1, le=20)


class GuessResponse(BaseModel):
    candidates: list[str]
    pattern_match_count: int
    used_model: bool
    warning: str | None = None


class LearnWordRequest(BaseModel):
    word: str = Field(min_length=1, max_length=60)


class LearnWordResponse(BaseModel):
    word: str
    seen_count: int
    is_new: bool = Field(description="Kelime listede daha önce yoksa True")


class GuideRequest(BaseModel):
    word: str = Field(min_length=1, max_length=60)


class GuideResponse(BaseModel):
    word: str
    category: str = Field(
        description="Kullanılan Quick Draw kategorisi veya 'internet: <simge adı>'"
    )
    image_data_url: str
