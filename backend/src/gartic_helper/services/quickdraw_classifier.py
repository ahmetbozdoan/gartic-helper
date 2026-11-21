"""Eğitilmiş Quick Draw CNN modeli (ONNX) ile çizim sınıflandırma."""

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime

from gartic_helper.utils.logging_utils import get_logger

logger = get_logger(__name__)


class ClassifierUnavailableError(RuntimeError):
    """Model dosyası yoksa veya yüklenemediyse fırlatılır."""


@dataclass(frozen=True)
class CategoryPrediction:
    category: str
    probability: float


class QuickDrawClassifier:
    def __init__(self, model_path: Path, labels_path: Path) -> None:
        self._model_path = model_path
        self._labels_path = labels_path
        self._session: onnxruntime.InferenceSession | None = None
        self._labels: list[str] = []
        self._load_lock = threading.Lock()

    @property
    def is_ready(self) -> bool:
        return self._model_path.exists() and self._labels_path.exists()

    def _ensure_loaded(self) -> onnxruntime.InferenceSession:
        if self._session is not None:
            return self._session
        with self._load_lock:
            if self._session is None:
                if not self.is_ready:
                    raise ClassifierUnavailableError(
                        f"Model bulunamadı: {self._model_path}. "
                        "scripts/train_quickdraw_classifier.py ile eğitin."
                    )
                self._labels = json.loads(self._labels_path.read_text(encoding="utf-8"))
                self._session = onnxruntime.InferenceSession(
                    str(self._model_path), providers=["CPUExecutionProvider"]
                )
                logger.info(
                    "Quick Draw modeli yüklendi: %s (%d kategori)",
                    self._model_path,
                    len(self._labels),
                )
        return self._session

    def predict(self, model_input: np.ndarray, top_k: int) -> list[CategoryPrediction]:
        session = self._ensure_loaded()
        logits = session.run(None, {"input": model_input})[0][0]
        exponentials = np.exp(logits - logits.max())
        probabilities = exponentials / exponentials.sum()
        top_indices = np.argsort(probabilities)[::-1][:top_k]
        return [
            CategoryPrediction(self._labels[index], float(probabilities[index]))
            for index in top_indices
        ]
