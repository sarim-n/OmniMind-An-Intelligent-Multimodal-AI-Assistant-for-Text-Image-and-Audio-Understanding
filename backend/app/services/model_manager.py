"""Model Memory Manager: hardware-aware model registry, LRU eviction, and inference concurrency control."""

from __future__ import annotations

import asyncio
import gc
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services.metrics_service import track

logger = get_logger(__name__)

# Estimated memory sizes in MB per model and hardware profile
MODEL_SIZE_ESTIMATES_MB: dict[str, dict[str, int]] = {
    "cpu": {
        "llm": 1500,
        "vlm": 1200,
        "asr": 300,
        "detector": 200,
        "embedder": 250,
        "image_embedder": 400,
    },
    "gpu_low": {
        "llm": 2000,
        "vlm": 2500,
        "asr": 500,
        "detector": 250,
        "embedder": 1000,
        "image_embedder": 500,
    },
    "gpu_mid": {
        "llm": 4500,
        "vlm": 4000,
        "asr": 1500,
        "detector": 400,
        "embedder": 1500,
        "image_embedder": 600,
    },
    "gpu_high": {
        "llm": 6000,
        "vlm": 5000,
        "asr": 2000,
        "detector": 500,
        "embedder": 1500,
        "image_embedder": 600,
    },
}


@dataclass
class LoadedModelEntry:
    """Metadata entry for a loaded heavy model."""

    key: str
    instance: Any
    unload_fn: Callable[[], None]
    loaded_at: float
    last_used_at: float
    estimated_size_mb: int


class ModelMemoryManager:
    """Central singleton managing loaded heavy models, LRU unloads, and inference semaphores."""

    _instance: ModelMemoryManager | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._loaded_models: OrderedDict[str, LoadedModelEntry] = OrderedDict()
        self._sync_semaphore = threading.Semaphore(settings.MAX_CONCURRENT_INFERENCES)
        self._async_semaphore: asyncio.Semaphore | None = None
        self._registry_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> ModelMemoryManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def async_semaphore(self) -> asyncio.Semaphore:
        """Lazily initialize asyncio.Semaphore on active event loop."""
        if self._async_semaphore is None:
            self._async_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_INFERENCES)
        return self._async_semaphore

    def get_estimated_size_mb(self, model_key: str) -> int:
        """Return estimated size in MB for given model under current profile."""
        profile = settings.PROFILE
        profile_estimates = MODEL_SIZE_ESTIMATES_MB.get(profile, MODEL_SIZE_ESTIMATES_MB["cpu"])
        return profile_estimates.get(model_key, 500)

    def is_loaded(self, model_key: str) -> bool:
        """Check if model is currently loaded in memory."""
        with self._registry_lock:
            return model_key in self._loaded_models

    def get_loaded_models(self) -> list[str]:
        """Return list of keys of all currently loaded models."""
        with self._registry_lock:
            return list(self._loaded_models.keys())

    def mark_used(self, model_key: str) -> None:
        """Update last_used_at timestamp and move model to most-recently-used position."""
        with self._registry_lock:
            entry = self._loaded_models.get(model_key)
            if entry:
                entry.last_used_at = time.time()
                self._loaded_models.move_to_end(model_key)

    def prepare_for_load(self, model_key: str) -> None:
        """Ensure memory headroom by evicting LRU model if MAX_LOADED_MODELS limit would be exceeded."""
        with self._registry_lock:
            if model_key in self._loaded_models:
                return

            # LRU eviction applies to cpu and gpu_low profiles, or whenever MAX_LOADED_MODELS is bounded
            should_evict = settings.PROFILE in ("cpu", "gpu_low") or settings.MAX_LOADED_MODELS > 0
            if not should_evict:
                return

            while len(self._loaded_models) >= settings.MAX_LOADED_MODELS:
                # Least recently used is the first item in OrderedDict
                lru_key, lru_entry = next(iter(self._loaded_models.items()))
                self._unload_entry(lru_key, lru_entry)

    def _unload_entry(self, key: str, entry: LoadedModelEntry) -> None:
        """Safely execute unload callback, garbage collection, and CUDA cache release."""
        logger.info(
            "Evicting model to conserve memory",
            evicted_model=key,
            profile=settings.PROFILE,
            estimated_freed_mb=entry.estimated_size_mb,
        )
        try:
            entry.unload_fn()
        except Exception as e:
            logger.error("Error invoking model unload function", model=key, error=str(e))

        if key in self._loaded_models:
            del self._loaded_models[key]

        # Force Python garbage collection
        gc.collect()

        # Free PyTorch CUDA cache if available
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        with track("model_manager", f"unload_{key}") as tracker:
            tracker.extra["freed_mb"] = entry.estimated_size_mb

    def register_loaded(
        self,
        model_key: str,
        instance: Any,
        unload_fn: Callable[[], None],
    ) -> None:
        """Register newly loaded model in the memory manager registry."""
        with self._registry_lock:
            est_mb = self.get_estimated_size_mb(model_key)
            now = time.time()
            self._loaded_models[model_key] = LoadedModelEntry(
                key=model_key,
                instance=instance,
                unload_fn=unload_fn,
                loaded_at=now,
                last_used_at=now,
                estimated_size_mb=est_mb,
            )
            logger.info(
                "Model registered in memory manager",
                model=model_key,
                loaded_count=len(self._loaded_models),
                active_models=list(self._loaded_models.keys()),
            )

    def unload_model(self, model_key: str) -> bool:
        """Explicitly unload a specific model by key."""
        with self._registry_lock:
            entry = self._loaded_models.get(model_key)
            if entry:
                self._unload_entry(model_key, entry)
                return True
            return False

    def unload_all(self) -> None:
        """Unload all currently registered models."""
        with self._registry_lock:
            keys = list(self._loaded_models.keys())
            for k in keys:
                entry = self._loaded_models.get(k)
                if entry:
                    self._unload_entry(k, entry)

    @contextmanager
    def track_load(self, model_key: str) -> Generator[None, None, None]:
        """Context manager preparing memory and recording model load latency."""
        self.prepare_for_load(model_key)
        start = time.perf_counter()
        with track("model_manager", f"load_{model_key}"):
            yield
        duration_ms = (time.perf_counter() - start) * 1000.0
        logger.info(
            "Model load finished",
            model=model_key,
            duration_ms=round(duration_ms, 2),
        )

    @contextmanager
    def acquire_inference_sync(self) -> Generator[None, None, None]:
        """Synchronous context manager enforcing inference concurrency limit."""
        with self._sync_semaphore:
            yield

    @asynccontextmanager
    async def acquire_inference(self) -> Any:
        """Asynchronous context manager enforcing inference concurrency limit."""
        async with self.async_semaphore:
            yield


def get_model_manager() -> ModelMemoryManager:
    """Retrieve singleton ModelMemoryManager."""
    return ModelMemoryManager.get_instance()
