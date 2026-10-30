"""Unit tests for LLM service in mock mode and JSON extraction."""

import pytest
from pydantic import BaseModel, Field

from app.services.llm_service import (
    MockLLM,
    extract_json_from_text,
    get_llm_service,
)


class SampleAnalysisSchema(BaseModel):
    summary: str
    score: int = Field(..., ge=0, le=100)
    tags: list[str] = Field(default_factory=list)


def test_extract_json_from_text() -> None:
    # Markdown json fence
    raw1 = 'Here is your response:\n```json\n{"key": "value"}\n```\nHope it helps!'
    assert extract_json_from_text(raw1) == '{"key": "value"}'

    # Generic code fence
    raw2 = "```\n[1, 2, 3]\n```"
    assert extract_json_from_text(raw2) == "[1, 2, 3]"

    # Raw braces
    raw3 = 'Some leading text {"nested": true} and trailing text.'
    assert extract_json_from_text(raw3) == '{"nested": true}'


def test_mock_llm_generate() -> None:
    llm = MockLLM(model_id="test-model")
    messages = [{"role": "user", "content": "What is the capital of France?"}]
    text = llm.generate(messages)
    assert isinstance(text, str)
    assert len(text) > 0
    assert "OmniMind" in text or "capital of France" in text


@pytest.mark.asyncio
async def test_mock_llm_stream_generate() -> None:
    llm = MockLLM(model_id="test-model")
    messages = [{"role": "user", "content": "Tell me a short joke."}]
    tokens: list[str] = []
    async for token in llm.stream_generate(messages):
        tokens.append(token)

    assert len(tokens) > 1
    reconstructed = "".join(tokens)
    assert len(reconstructed) > 0


def test_llm_service_singleton_generate() -> None:
    service = get_llm_service()
    text, timing_ms = service.generate([{"role": "user", "content": "Explain gravity"}])
    assert isinstance(text, str)
    assert timing_ms >= 0


def test_llm_service_generate_json() -> None:
    service = get_llm_service()
    result, timing_ms = service.generate_json(
        prompt="Analyze the quarterly performance.",
        pydantic_schema=SampleAnalysisSchema,
    )
    assert isinstance(result, SampleAnalysisSchema)
    assert timing_ms >= 0


def test_llm_service_infer_unified_method() -> None:
    service = get_llm_service()
    res_str, timing1 = service.infer("Direct prompt string")
    assert isinstance(res_str, str)
    assert timing1 >= 0

    res_list, timing2 = service.infer([{"role": "user", "content": "List message"}])
    assert isinstance(res_list, str)
    assert timing2 >= 0
