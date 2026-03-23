from __future__ import annotations

from typing import Sequence

import numpy as np

from memstate.embeddings.base import EmbeddingProvider, _normalize

# sentence-transformers/all-MiniLM-L6-v2: strong speed/quality tradeoff on CPU, 384-dim.
_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class FastEmbedProvider(EmbeddingProvider):
    """Text embeddings via fastembed (ONNX); lazy-loads model on first use."""

    def __init__(self, model_name: str | None = None) -> None:
        try:
            from fastembed import TextEmbedding  # type: ignore import-not-found
        except ImportError as e:
            raise ImportError(
                "FastEmbedProvider requires the 'fastembed' package. "
                "Install with: pip install memstate[embedding]"
            ) from e
        self._model_name = model_name or _DEFAULT_MODEL
        self._TextEmbedding = TextEmbedding
        self._model = None
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._ensure_model()
        assert self._dimension is not None
        return self._dimension

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        self._model = self._TextEmbedding(model_name=self._model_name)
        probe = list(self._model.embed(["."], batch_size=1))
        arr = np.asarray(probe[0], dtype=np.float64).reshape(-1)
        self._dimension = int(arr.size)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self._ensure_model()
        assert self._model is not None
        docs = [t if (t or "").strip() else " " for t in texts]
        raw = list(self._model.embed(docs))
        return [_normalize(np.asarray(v, dtype=np.float64).reshape(-1)) for v in raw]


def try_fastembed(model_name: str | None = None) -> FastEmbedProvider | None:
    try:
        return FastEmbedProvider(model_name=model_name)
    except ImportError:
        return None
