"""Multimodal user intent classifier: rules-first with LLM fallback."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger(__name__)

IntentType = Literal[
    "qa_about_image",
    "summarise_audio",
    "compare_image_and_audio",
    "generate_report",
    "search",
    "general_chat",
]


class IntentClassificationResult(BaseModel):
    """Pydantic schema for LLM structured intent output."""

    intent: IntentType = Field(
        ...,
        description="Classified user intent: qa_about_image, summarise_audio, compare_image_and_audio, generate_report, search, or general_chat.",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


def classify_intent(
    query: str,
    has_image: bool = False,
    has_audio: bool = False,
    has_prior_image: bool = False,
    has_prior_audio: bool = False,
) -> IntentType:
    """Classify user intent using robust rule patterns first, falling back to LLM if ambiguous.

    Logs intent only, never user content or PII.
    """
    clean_query = query.strip().lower()
    intent: IntentType = "general_chat"

    # Rule 1: Report generation
    report_patterns = [
        r"\b(?:generate|create|export|make|build|write|download)\s+(?:a\s+)?report\b",
        r"\breport\s+on\b",
        r"\bpdf\s+report\b",
    ]
    if any(re.search(pat, clean_query) for pat in report_patterns):
        intent = "generate_report"
        logger.info("Classified message intent", intent=intent, method="rule_report")
        return intent

    # Rule 2: Explicit Search / Document retrieval
    search_patterns = [
        r"\bsearch\s+(?:for|in|documents|knowledge|files|notes)\b",
        r"\bfind\s+(?:in\s+documents|in\s+files|relevant\s+documents)\b",
        r"\blook\s+up\s+in\b",
    ]
    if any(re.search(pat, clean_query) for pat in search_patterns):
        intent = "search"
        logger.info("Classified message intent", intent=intent, method="rule_search")
        return intent

    # Rule 3: Cross-modal comparison (Image + Audio)
    has_both_modalities = (has_image or has_prior_image) and (has_audio or has_prior_audio)
    compare_patterns = [
        r"\bcompare\b",
        r"\bmatch\b",
        r"\bdiffer(?:ence|ent)?\b",
        r"\bcorrelat(?:e|ion)\b",
        r"\bdoes\s+(?:what\s+)?the\s+speaker\s+say\s+match\b",
        r"\bdoes\s+the\s+audio\s+match\b",
        r"\brelat(?:e|ionship)\b",
        r"\bboth\s+(?:the\s+)?(?:image|picture|photo)\s+and\s+(?:the\s+)?(?:audio|recording|speaker)\b",
    ]
    if has_both_modalities and (
        not clean_query or any(re.search(pat, clean_query) for pat in compare_patterns)
    ):
        intent = "compare_image_and_audio"
        logger.info("Classified message intent", intent=intent, method="rule_compare")
        return intent

    # Rule 4: Visual QA / Image Understanding
    image_active = has_image or has_prior_image
    image_patterns = [
        r"\b(?:what|who|where|how\s+many|what\s+colour|what\s+color)\b",
        r"\b(?:picture|image|photo|chart|diagram|screen|object|car|person|dog|cat)\b",
        r"\b(?:look\s+at|in\s+the\s+picture|in\s+the\s+image|describe)\b",
        r"\b(?:read|text|label|signage|ocr)\b",
    ]
    if has_image and (
        not clean_query or any(re.search(pat, clean_query) for pat in image_patterns)
    ):
        intent = "qa_about_image"
        logger.info("Classified message intent", intent=intent, method="rule_image_direct")
        return intent

    if (
        image_active
        and any(re.search(pat, clean_query) for pat in image_patterns)
        and not has_audio
    ):
        intent = "qa_about_image"
        logger.info("Classified message intent", intent=intent, method="rule_image_followup")
        return intent

    # Rule 5: Audio summarization / transcript QA
    audio_active = has_audio or has_prior_audio
    audio_patterns = [
        r"\b(?:summaris|summariz|summary|transcript|transcribe|recording|audio|speech)\b",
        r"\b(?:what\s+did\s+(?:he|she|they|the\s+speaker)\s+say)\b",
        r"\b(?:speaker|meeting|discussion|podcast|listen)\b",
        r"\b(?:said\s+about|talked\s+about|mentioned|budget|topic)\b",
    ]
    if has_audio and (
        not clean_query or any(re.search(pat, clean_query) for pat in audio_patterns)
    ):
        intent = "summarise_audio"
        logger.info("Classified message intent", intent=intent, method="rule_audio_direct")
        return intent

    if (
        audio_active
        and any(re.search(pat, clean_query) for pat in audio_patterns)
        and not has_image
    ):
        intent = "summarise_audio"
        logger.info("Classified message intent", intent=intent, method="rule_audio_followup")
        return intent

    # Ambiguity check: if query is non-empty and modalities are present, fall back to LLM if needed
    if (image_active or audio_active) and clean_query:
        try:
            from app.services.llm_service import get_llm_service

            llm = get_llm_service()
            prompt = (
                "You are an intent classification system for a multimodal assistant. "
                "Classify the user intent into exactly one of: "
                "qa_about_image, summarise_audio, compare_image_and_audio, generate_report, search, general_chat.\n"
                f"Available modalities: has_image={image_active}, has_audio={audio_active}.\n"
                f"User Query:\n<<<QUERY>>>\n{query}\n<<<QUERY>>>\n"
                "Return a JSON object conforming to the schema with field 'intent'."
            )
            parsed, _ = llm.generate_json(prompt, IntentClassificationResult)
            if parsed and parsed.intent:
                intent = parsed.intent
                logger.info("Classified message intent", intent=intent, method="llm")
                return intent
        except Exception:
            pass

    # Default fallback
    if has_image and not has_audio:
        intent = "qa_about_image"
    elif has_audio and not has_image:
        intent = "summarise_audio"
    else:
        intent = "general_chat"

    logger.info("Classified message intent", intent=intent, method="default")
    return intent
