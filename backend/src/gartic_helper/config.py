"""Ortam değişkenlerinden okunan uygulama ayarları."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    word_list_path: Path = BACKEND_ROOT / "data" / "words_tr.json"
    learned_words_path: Path = BACKEND_ROOT / "data" / "learned_words.json"
    category_translations_path: Path = BACKEND_ROOT / "data" / "quickdraw_categories_tr.json"
    guide_drawings_path: Path = BACKEND_ROOT / "data" / "quickdraw" / "guide_drawings.json"
    classifier_model_path: Path = BACKEND_ROOT / "models" / "quickdraw_cnn.onnx"
    classifier_labels_path: Path = BACKEND_ROOT / "models" / "quickdraw_labels.json"
    classifier_top_k: int = 20
    # Quick Draw'da olmayan kelimeler için çok dilli CLIP (Türkçe metni doğrudan anlar).
    clip_enabled: bool = True
    clip_model_name: str = "xlm-roberta-base-ViT-B-32"
    clip_pretrained: str = "laion5b_s13b_b90k"
    clip_prompt_template: str = "bir {word} çizimi"
    clip_top_k: int = 10
    clip_embedding_cache_path: Path = BACKEND_ROOT / "models" / "clip_text_embeddings.npz"
    # Quick Draw'da olmayan kelimelerin kılavuzu için internetten simge araması (Iconify).
    web_icon_search_enabled: bool = True
    web_icon_search_timeout_seconds: float = 8.0
    web_icon_search_max_results: int = 12
    allowed_origin_regex: str = r"chrome-extension://.*"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
