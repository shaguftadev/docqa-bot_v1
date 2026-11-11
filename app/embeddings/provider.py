from __future__ import annotations

from functools import lru_cache
from threading import Lock
from typing import Protocol

import numpy as np

from app.core.config import get_settings


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class EmbeddingProviderError(RuntimeError):
    """Raised when the embedding backend cannot encode a document or query."""


class FastEmbedProvider:
    """CPU-friendly FastEmbed wrapper around the configured BGE model."""

    def __init__(self, model_name: str, expected_dimension: int) -> None:
        self._model_name = model_name
        self._expected_dimension = expected_dimension
        self._model = None
        self._model_lock = Lock()

    def _get_model(self):
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(model_name=self._model_name, lazy_load=True, threads=4)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = [np.asarray(vector, dtype=np.float32) for vector in self._get_model().passage_embed(texts)]
            return self._check(vectors)
        except Exception as exc:
            raise EmbeddingProviderError("The embedding model failed to encode document chunks") from exc

    def embed_query(self, text: str) -> list[float]:
        try:
            vector = next(self._get_model().query_embed(text))
            return self._check([np.asarray(vector, dtype=np.float32)])[0]
        except Exception as exc:
            raise EmbeddingProviderError("The embedding model failed to encode the query") from exc

    def _check(self, vectors: list[np.ndarray]) -> list[list[float]]:
        checked: list[list[float]] = []
        for vector in vectors:
            if vector.ndim != 1 or vector.size != self._expected_dimension:
                raise ValueError(
                    f"Embedding model returned dimension {vector.size}; expected {self._expected_dimension}"
                )
            if not np.isfinite(vector).all():
                raise ValueError("Embedding model returned non-finite values")
            checked.append(vector.tolist())
        return checked


@lru_cache(maxsize=1)
def get_embedder() -> FastEmbedProvider:
    settings = get_settings()
    return FastEmbedProvider(settings.embedding_model, settings.embedding_dimension)
