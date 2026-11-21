"""
Çok dilli CLIP modeliyle çizimi kelime listesine göre sıralama (sıfır-atış, eğitim gerektirmez).

Quick Draw modeli yalnızca 345 kategoriyi bilir; CLIP ise görseli her kelimenin metin temsiliyle
karşılaştırdığı için listedeki her kelimeyi (örn. "palyaço") tahmin edebilir. Model ilk açılışta
indirilir (~1 GB) ve yüklenmesi uzun sürdüğü için arka planda yüklenir; hazır olana kadar boş döner.
"""

import io
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from gartic_helper.utils.logging_utils import get_logger

logger = get_logger(__name__)


class ClipWordRanker:
    def __init__(
        self,
        model_name: str,
        pretrained: str,
        prompt_template: str,
        embedding_cache_path: Path,
        enabled: bool = True,
    ) -> None:
        self._model_name = model_name
        self._pretrained = pretrained
        self._prompt_template = prompt_template
        self._embedding_cache_path = embedding_cache_path
        self._enabled = enabled
        # Önbellek, model veya kalıp değişince geçersiz sayılsın diye imza ile saklanır.
        self._cache_signature = f"{model_name}|{pretrained}|{prompt_template}"

        self._torch: Any = None
        self._model: Any = None
        self._preprocess: Any = None
        self._tokenizer: Any = None
        self._text_embeddings: dict[str, np.ndarray] = {}
        self._start_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._loading_thread: threading.Thread | None = None
        self._load_failed = False

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def start_loading(self, words: Sequence[str]) -> None:
        """Modeli ve kelimelerin metin temsillerini arka planda hazırlar (tekrar çağrılabilir)."""
        if not self._enabled or self._load_failed:
            return
        with self._start_lock:
            if self._loading_thread is None:
                self._loading_thread = threading.Thread(
                    target=self._load, args=(tuple(words),), name="clip-loader", daemon=True
                )
                self._loading_thread.start()

    def rank(self, image_bytes: bytes, candidate_words: Sequence[str], top_k: int) -> list[str]:
        """Aday kelimeleri çizime benzerliğe göre sıralar; model hazır değilse boş liste döner."""
        if not self.is_ready:
            self.start_loading(candidate_words)
            return []
        if not candidate_words:
            return []

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        with self._inference_lock, self._torch.no_grad():
            missing_words = [word for word in candidate_words if word not in self._text_embeddings]
            if missing_words:
                self._embed_words(missing_words)
                self._write_embedding_cache()
            image_features = self._model.encode_image(self._preprocess(image).unsqueeze(0))
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        image_vector = image_features[0].numpy()
        text_matrix = np.stack([self._text_embeddings[word] for word in candidate_words])
        similarities = text_matrix @ image_vector
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [candidate_words[index] for index in top_indices]

    def rank_related_words(self, word: str, related_words: Sequence[str]) -> list[str]:
        """Yakın anlamlı kelimeleri (Türkçe/İngilizce karışık olabilir) kelimeye benzerliğe göre
        sıralar; model hazır değilse sırayı değiştirmeden döndürür."""
        if not self.is_ready or not related_words:
            return list(related_words)
        with self._inference_lock, self._torch.no_grad():
            embeddings = self._encode_prompts([word, *related_words])
        similarities = embeddings[1:] @ embeddings[0]
        return [related_words[index] for index in np.argsort(similarities)[::-1]]

    def _load(self, words: tuple[str, ...]) -> None:
        try:
            import open_clip
            import torch
        except ImportError as error:
            self._load_failed = True
            logger.warning("CLIP devre dışı, paketler eksik (rye sync --features clip): %s", error)
            return

        try:
            started_at = time.perf_counter()
            model, _, preprocess = open_clip.create_model_and_transforms(
                self._model_name, pretrained=self._pretrained
            )
            model.eval()
            self._torch = torch
            self._preprocess = preprocess
            self._tokenizer = open_clip.get_tokenizer(self._model_name)
            self._text_embeddings = self._read_embedding_cache()

            with self._inference_lock, torch.no_grad():
                self._model = model
                missing_words = [word for word in words if word not in self._text_embeddings]
                if missing_words:
                    self._embed_words(missing_words)
                    self._write_embedding_cache()
            logger.info(
                "CLIP modeli hazır: %s/%s (%d kelime, %.1f sn)",
                self._model_name,
                self._pretrained,
                len(self._text_embeddings),
                time.perf_counter() - started_at,
            )
        except Exception:
            # İndirme/disk/bellek hataları sunucuyu düşürmemeli; Quick Draw modeli çalışmaya devam
            # eder.
            self._model = None
            self._load_failed = True
            logger.exception(
                "CLIP modeli yüklenemedi: model=%s pretrained=%s",
                self._model_name,
                self._pretrained,
            )

    def _embed_words(self, words: Sequence[str], batch_size: int = 64) -> None:
        """_inference_lock ve no_grad altında çağrılmalıdır."""
        for start in range(0, len(words), batch_size):
            batch_words = words[start : start + batch_size]
            for word, embedding in zip(batch_words, self._encode_prompts(batch_words), strict=True):
                self._text_embeddings[word] = embedding

    def _encode_prompts(self, words: Sequence[str]) -> np.ndarray:
        """_inference_lock ve no_grad altında çağrılmalıdır; satırlar birim uzunluktadır."""
        prompts = [self._prompt_template.format(word=word) for word in words]
        text_features = self._model.encode_text(self._tokenizer(prompts))
        return (text_features / text_features.norm(dim=-1, keepdim=True)).numpy()

    def _read_embedding_cache(self) -> dict[str, np.ndarray]:
        if not self._embedding_cache_path.exists():
            return {}
        try:
            with np.load(self._embedding_cache_path) as cache:
                if str(cache["signature"]) != self._cache_signature:
                    return {}
                return dict(zip(cache["words"].tolist(), cache["embeddings"], strict=True))
        except (OSError, KeyError, ValueError) as error:
            logger.warning(
                "CLIP önbelleği okunamadı: path=%s error=%s", self._embedding_cache_path, error
            )
            return {}

    def _write_embedding_cache(self) -> None:
        words = list(self._text_embeddings)
        temporary_path = self._embedding_cache_path.with_suffix(".tmp.npz")
        try:
            self._embedding_cache_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(
                temporary_path,
                signature=np.array(self._cache_signature),
                words=np.array(words),
                embeddings=np.stack([self._text_embeddings[word] for word in words]),
            )
            temporary_path.replace(self._embedding_cache_path)
        except OSError as error:
            logger.warning(
                "CLIP önbelleği yazılamadı: path=%s error=%s", self._embedding_cache_path, error
            )
