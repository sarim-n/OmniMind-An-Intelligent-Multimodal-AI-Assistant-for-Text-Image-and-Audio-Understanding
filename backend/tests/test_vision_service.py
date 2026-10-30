"""Unit tests for VisionService, VLM backends, and MockVLM."""

from __future__ import annotations

from PIL import Image
from pydantic import BaseModel, Field

from app.services.vision_service import MockVLM, get_vision_service


class DummyVisualData(BaseModel):
    category: str = Field(default="general")
    tags: list[str] = Field(default_factory=lambda: ["test", "image"])


def test_mock_vlm_describe_brief_and_detailed() -> None:
    vlm = MockVLM()
    img = Image.new("RGB", (300, 200), (100, 150, 200))

    brief_desc = vlm.describe(img, detail_level="brief")
    assert "300x200" in brief_desc
    assert len(brief_desc) > 10

    detailed_desc = vlm.describe(img, detail_level="detailed")
    assert "300x200" in detailed_desc
    assert len(detailed_desc) > len(brief_desc)


def test_mock_vlm_answer_with_conversation_history() -> None:
    vlm = MockVLM()
    img = Image.new("RGB", (200, 200), (200, 100, 50))

    history = [
        {"role": "user", "content": "What is in this picture?"},
        {"role": "assistant", "content": "It shows a colored image."},
    ]

    answer = vlm.answer(img, "Can you confirm the main item?", history=history)
    assert len(answer) > 0
    assert "Context from 2 previous turns" in answer


def test_mock_vlm_multilingual_responses() -> None:
    vlm = MockVLM()
    img = Image.new("RGB", (100, 100), (50, 50, 50))

    # Hindi question
    hindi_ans = vlm.answer(img, "इस तस्वीर में क्या दिखाई दे रहा है?")
    assert "छवि" in hindi_ans

    # Tamil question
    tamil_ans = vlm.answer(img, "இந்த படத்தில் என்ன இருக்கிறது?")
    assert "படத்தின்" in tamil_ans


def test_mock_vlm_extract_text() -> None:
    vlm = MockVLM()
    img = Image.new("RGB", (180, 120), (255, 255, 255))
    text = vlm.extract_text(img)
    assert len(text) > 0
    assert "180" in text


def test_mock_vlm_structured_extract() -> None:
    vlm = MockVLM()
    img = Image.new("RGB", (100, 100), (10, 10, 10))
    structured = vlm.structured_extract(img, DummyVisualData)
    assert isinstance(structured, DummyVisualData)
    assert structured.category == "general"


def test_vision_service_singleton_and_infer() -> None:
    service = get_vision_service()
    img = Image.new("RGB", (150, 150), (100, 100, 100))

    result, timing_ms = service.infer(img)
    assert isinstance(result, str)
    assert len(result) > 0
    assert timing_ms >= 0.0
