"""Tests for ModelMemoryManager registry, LRU eviction, and inference semaphore."""

from collections.abc import Generator

import pytest

from app.core.config import settings
from app.services.audio_service import get_audio_service
from app.services.llm_service import get_llm_service
from app.services.model_manager import get_model_manager
from app.services.vision_service import get_vision_service


@pytest.fixture(autouse=True)
def clean_model_manager() -> Generator[None, None, None]:
    """Ensure clean model manager state before and after each test."""
    manager = get_model_manager()
    manager.unload_all()
    yield
    manager.unload_all()


def test_model_manager_estimates_and_registration() -> None:
    """Verify estimated model sizes and registration tracking."""
    manager = get_model_manager()
    llm_size = manager.get_estimated_size_mb("llm")
    assert llm_size > 0
    assert manager.get_estimated_size_mb("vlm") > 0
    assert manager.get_estimated_size_mb("asr") > 0

    assert not manager.is_loaded("custom_test_model")
    unloaded = False

    def dummy_unload() -> None:
        nonlocal unloaded
        unloaded = True

    manager.register_loaded("custom_test_model", instance=None, unload_fn=dummy_unload)
    assert manager.is_loaded("custom_test_model")
    assert "custom_test_model" in manager.get_loaded_models()

    # Explicit unload
    assert manager.unload_model("custom_test_model")
    assert unloaded
    assert not manager.is_loaded("custom_test_model")


def test_model_manager_lru_eviction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify LRU model eviction when MAX_LOADED_MODELS limit is reached."""
    # Force MAX_LOADED_MODELS to 2 for deterministic eviction testing
    monkeypatch.setattr(settings, "MAX_LOADED_MODELS", 2)
    monkeypatch.setattr(settings, "PROFILE", "cpu")

    manager = get_model_manager()

    evicted: list[str] = []

    def make_unloader(name: str):
        def unloader() -> None:
            evicted.append(name)

        return unloader

    # Load model A
    manager.prepare_for_load("model_a")
    manager.register_loaded("model_a", instance=None, unload_fn=make_unloader("model_a"))
    assert manager.get_loaded_models() == ["model_a"]

    # Load model B
    manager.prepare_for_load("model_b")
    manager.register_loaded("model_b", instance=None, unload_fn=make_unloader("model_b"))
    assert manager.get_loaded_models() == ["model_a", "model_b"]

    # Mark model A as recently used (so B becomes LRU)
    manager.mark_used("model_a")

    # Load model C -> limit is 2, so model B should be evicted!
    manager.prepare_for_load("model_c")
    manager.register_loaded("model_c", instance=None, unload_fn=make_unloader("model_c"))

    assert "model_b" in evicted
    assert manager.get_loaded_models() == ["model_a", "model_c"]
    assert not manager.is_loaded("model_b")
    assert manager.is_loaded("model_a")
    assert manager.is_loaded("model_c")


def test_services_wire_through_model_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that calling load on existing services automatically registers them with ModelMemoryManager."""
    monkeypatch.setattr(settings, "MAX_LOADED_MODELS", 2)
    monkeypatch.setattr(settings, "PROFILE", "cpu")

    manager = get_model_manager()
    llm = get_llm_service()
    asr = get_audio_service()
    vision = get_vision_service()

    # Load LLM
    llm.load()
    assert manager.is_loaded("llm")

    # Load ASR
    asr.load()
    assert manager.is_loaded("asr")
    assert len(manager.get_loaded_models()) == 2

    # Now load Vision -> LLM was loaded first, so it should be evicted
    vision.load()
    assert manager.is_loaded("vision") or manager.is_loaded("vlm")
    # Total loaded models should not exceed 2
    assert len(manager.get_loaded_models()) <= 2
    assert not llm._loaded


@pytest.mark.asyncio
async def test_inference_semaphore_concurrency() -> None:
    """Verify sync and async semaphore acquisition."""
    manager = get_model_manager()

    with manager.acquire_inference_sync():
        pass

    async with manager.acquire_inference():
        pass
