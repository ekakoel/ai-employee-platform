"""Job 26 — Embedding provider interface + fake/hash implementations."""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Sequence

from app.core.config import settings


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic bag-of-tokens embedding for tests (no external API)."""

    def __init__(self, dims: int | None = None):
        self._dims = dims or settings.embedding_dims

    @property
    def model_name(self) -> str:
        return f"fake-emb-{self._dims}"

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dims
        tokens = re.findall(r"[a-zA-Z0-9_]{2,}", (text or "").lower())
        if not tokens:
            return vec
        for tok in tokens:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            idx = h % self._dims
            sign = 1.0 if (h // self._dims) % 2 == 0 else -1.0
            vec[idx] += sign
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class HashEmbeddingProvider(FakeEmbeddingProvider):
    """Alias — same deterministic algorithm, different model name."""

    @property
    def model_name(self) -> str:
        return f"hash-emb-{self._dims}"


def get_embedding_provider() -> EmbeddingProvider:
    from app.core.config import settings as live

    name = (live.embedding_provider or "fake").lower().strip()
    dims = live.embedding_dims
    if name in ("hash", "hash-emb"):
        return HashEmbeddingProvider(dims=dims)
    return FakeEmbeddingProvider(dims=dims)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
