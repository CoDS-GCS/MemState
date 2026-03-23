from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np


class EmbeddingProvider(ABC):
    dimension: int

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text (L2-normalized for cosine KNN)."""


def _normalize(v: np.ndarray) -> list[float]:
    n = np.linalg.norm(v) or 1.0
    return (v / n).astype(np.float64).tolist()


class HashEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic pseudo-embeddings from text (no external API).
    Suitable for dev/tests; swap for HTTP OpenAI-compatible embedder in production.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            seed = int(hashlib.sha256(t.encode("utf-8")).hexdigest()[:16], 16)
            rng = np.random.default_rng(seed)
            v = rng.standard_normal(self.dimension).astype(np.float64)
            out.append(_normalize(v))
        return out
