"""Multilingual Embedding Service with profile awareness and mock fallback."""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services.metrics_service import track

logger = get_logger(__name__)


def _deterministic_mock_vector(text: str, dim: int = 384) -> list[float]:
    """Generate a deterministic normalized unit vector for mock embeddings."""
    seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()
    raw_vals: list[float] = []

    # Deterministically derive `dim` floats from hashes
    current_hash = seed_bytes
    while len(raw_vals) < dim:
        for i in range(0, len(current_hash) - 1, 2):
            val = ((current_hash[i] << 8) | current_hash[i + 1]) / 65535.0 - 0.5
            raw_vals.append(val)
            if len(raw_vals) >= dim:
                break
        current_hash = hashlib.sha256(current_hash).digest()

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in raw_vals)) or 1.0
    return [round(v / norm, 6) for v in raw_vals]


class MockEmbedder:
    """Deterministic mock embedder producing unit vectors without downloading weights."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def encode(
        self,
        texts: list[str] | str,
        normalize_embeddings: bool = True,
        **kwargs: Any,
    ) -> list[list[float]] | list[float]:
        if isinstance(texts, str):
            return _deterministic_mock_vector(texts, dim=self.dim)
        return [_deterministic_mock_vector(t, dim=self.dim) for t in texts]


class EmbeddingService:
    """Multilingual text embedding service supporting multilingual-e5 and bge-m3."""

    _instance: EmbeddingService | None = None

    def __init__(self) -> None:
        self.model_name: str = settings.effective_text_embedding_model
        self.is_e5: bool = "e5" in self.model_name.lower()
        self.dim: int = 1024 if "bge-m3" in self.model_name.lower() else 384
        self.model: Any = None
        self._loaded: bool = False
        self.device: str = "cpu"

    @classmethod
    def get_instance(cls) -> EmbeddingService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def unload(self) -> None:
        """Unload SentenceTransformer embedding model weights from memory."""
        self.model = None
        self._loaded = False
        logger.info(
            "Unloaded SentenceTransformer embedder weights from memory", model=self.model_name
        )

    def load(self) -> None:
        """Lazy model loader respecting MOCK_MODELS and hardware profile."""
        from app.services.model_manager import get_model_manager

        model_mgr = get_model_manager()
        if self._loaded:
            model_mgr.mark_used("embedder")
            return

        with model_mgr.track_load("embedder"):
            if settings.MOCK_MODELS:
                logger.info("Initializing MockEmbedder", model=self.model_name, dim=self.dim)
                self.model = MockEmbedder(dim=self.dim)
                self.device = "mock"
                self._loaded = True
                model_mgr.register_loaded("embedder", self, self.unload)
                return

            logger.info("Loading SentenceTransformer model", model=self.model_name)
            try:
                import torch
                from sentence_transformers import SentenceTransformer

                if settings.PROFILE != "cpu" and torch.cuda.is_available():
                    self.device = "cuda"
                else:
                    self.device = "cpu"

                self.model = SentenceTransformer(self.model_name, device=self.device)
                # Retrieve exact embedding dimension if available
                if hasattr(self.model, "get_sentence_embedding_dimension"):
                    self.dim = self.model.get_sentence_embedding_dimension() or self.dim
                self._loaded = True
                model_mgr.register_loaded("embedder", self, self.unload)
                logger.info(
                    "SentenceTransformer loaded successfully",
                    model=self.model_name,
                    device=self.device,
                )
            except Exception as e:
                logger.error(
                    "Failed to load SentenceTransformer model, falling back to mock", error=str(e)
                )
                self.model = MockEmbedder(dim=self.dim)
                self.device = "mock"
                self._loaded = True
                model_mgr.register_loaded("embedder", self, self.unload)

    def _prepare_text(self, text: str, is_query: bool) -> str:
        """Prepend required prefixes for e5 family models."""
        if not self.is_e5:
            return text
        prefix = "query: " if is_query else "passage: "
        if text.startswith(prefix):
            return text
        return f"{prefix}{text}"

    def embed_texts(self, texts: list[str]) -> tuple[list[list[float]], float]:
        """Embed a batch of document/passage texts. Returns (embeddings, timing_ms)."""
        from app.services.model_manager import get_model_manager

        self.load()
        get_model_manager().mark_used("embedder")
        start = time.perf_counter()
        with track("embedding", "embed_texts") as tracker:
            prepared = [self._prepare_text(t, is_query=False) for t in texts]
            if settings.MOCK_MODELS or self.device == "mock":
                embeddings: list[list[float]] = self.model.encode(prepared)
            else:
                raw = self.model.encode(prepared, normalize_embeddings=True)
                embeddings = [v.tolist() if hasattr(v, "tolist") else list(v) for v in raw]
            timing_ms = (time.perf_counter() - start) * 1000.0
            tracker.set_tokens(count=len(texts))
        return embeddings, round(timing_ms, 2)

    def embed_query(self, query: str) -> tuple[list[float], float]:
        """Embed a single search query. Returns (embedding, timing_ms)."""
        from app.services.model_manager import get_model_manager

        self.load()
        get_model_manager().mark_used("embedder")
        start = time.perf_counter()
        with track("embedding", "embed_query") as tracker:
            prepared = self._prepare_text(query, is_query=True)
            if settings.MOCK_MODELS or self.device == "mock":
                embedding: list[float] = self.model.encode(prepared)
            else:
                raw = self.model.encode(prepared, normalize_embeddings=True)
                embedding = raw.tolist() if hasattr(raw, "tolist") else list(raw)
            timing_ms = (time.perf_counter() - start) * 1000.0
            tracker.set_tokens(count=1)
        return embedding, round(timing_ms, 2)

    def infer(self, input_data: list[str] | str) -> tuple[list[list[float]] | list[float], float]:
        """Unified inference interface returning (result, timing_ms)."""
        if isinstance(input_data, str):
            return self.embed_query(input_data)
        return self.embed_texts(input_data)


def get_embedding_service() -> EmbeddingService:
    """Retrieve singleton EmbeddingService instance."""
    return EmbeddingService.get_instance()
