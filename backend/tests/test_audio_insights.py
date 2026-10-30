"""Unit tests for AudioInsightsService and Map-Reduce synthesis."""

import pytest

from app.schemas.audio import AudioInsights
from app.services.audio_insights import (
    chunk_text,
    get_audio_insights_service,
)
from app.services.llm_service import get_llm_service


def test_chunk_text_utility() -> None:
    text = "word " * 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=200)
    assert len(chunks) >= 3


def test_audio_insights_single_pass() -> None:
    service = get_audio_insights_service()
    transcript = (
        "In today's meeting, John proposed migrating our database to PostgreSQL by next month. "
        "Sarah agreed to take ownership of the schema migration scripts. "
        "We decided to schedule a follow-up review on Friday. "
        "Open question: How will we handle historical analytics data?"
    )

    insights = service.extract_insights(transcript, output_language="English")
    assert isinstance(insights, AudioInsights)
    assert len(insights.short_summary) > 0
    assert len(insights.detailed_summary) > 0
    assert isinstance(insights.key_points, list)
    assert isinstance(insights.topics, list)
    assert isinstance(insights.action_items, list)


def test_audio_insights_map_reduce_long_transcript() -> None:
    service = get_audio_insights_service()
    # Build long transcript exceeding 1000 words to trigger map-reduce branch
    paragraphs = [
        f"Section {i}: The engineering team discussed architecture scalability and backend performance benchmarks. "
        f"Engineer_{i} committed to optimizing query index patterns before release date. "
        for i in range(120)
    ]
    long_transcript = " ".join(paragraphs)

    insights = service.extract_insights(long_transcript, output_language="English")
    assert isinstance(insights, AudioInsights)
    assert len(insights.short_summary) > 0
    assert len(insights.detailed_summary) > 0
    assert len(insights.key_points) > 0


def test_audio_insights_error_handling_returns_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    service = get_audio_insights_service()
    llm = get_llm_service()

    # Simulate LLM failure
    def mock_fail_json(*args: object, **kwargs: object) -> tuple[None, float]:
        raise RuntimeError("LLM inference unavailable")

    monkeypatch.setattr(llm, "generate_json", mock_fail_json)

    transcript = "This is a test transcript for error handling verification."
    insights = service.extract_insights(transcript)

    assert isinstance(insights, AudioInsights)
    assert insights.errors is not None
    assert len(insights.errors) > 0
    assert "LLM inference unavailable" in insights.errors[0]
    assert len(insights.short_summary) > 0  # Still returns partial result, never crashes with 500
