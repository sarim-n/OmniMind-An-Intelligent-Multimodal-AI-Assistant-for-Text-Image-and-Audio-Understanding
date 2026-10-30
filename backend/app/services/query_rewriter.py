"""Query rewriter for conversational anaphora and reference resolution."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.services.llm_service import get_llm_service

logger = get_logger(__name__)

# Reference regex patterns indicating context-dependent queries
REFERENCE_PATTERNS = [
    re.compile(r"\b(it|its|that|this|these|those|them|they|him|her|he|she)\b", re.IGNORECASE),
    re.compile(
        r"\b(the former|the latter|the first one|the second one|the last one|the previous one|the same)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(what about|how about|why\??|why so\??|tell me more|expand on that|elaborate|and then|more info)\b",
        re.IGNORECASE,
    ),
]


class RewrittenQuerySchema(BaseModel):
    """Pydantic schema for structured query rewriting output."""

    rewritten_query: str = Field(
        ...,
        description="The self-contained, unambiguous standalone search query resolving all references.",
    )
    has_reference: bool = Field(
        ...,
        description="True if references/pronouns in the query were resolved using conversation history.",
    )


def has_conversational_reference(query: str) -> bool:
    """Detect whether a query depends on previous conversation context."""
    clean = query.strip()
    if not clean:
        return False

    # Short follow-ups often carry implicit references
    words = clean.split()
    if len(words) <= 3 and any(p.search(clean) for p in REFERENCE_PATTERNS):
        return True

    return any(p.search(clean) for p in REFERENCE_PATTERNS)


def rewrite_query_if_needed(
    query: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Rewrite a query into a standalone query if conversational references are detected.

    Maintains strict prompt hygiene (treating history and query as untrusted data)
    and structured logging without logging full user text or PII.
    """
    clean_query = query.strip()
    if not clean_query:
        return query

    # If no conversational history or no reference detected, return original query immediately
    if not history or not has_conversational_reference(clean_query):
        logger.info(
            "Query rewrite evaluation",
            has_reference=False,
            query_len=len(clean_query),
        )
        return clean_query

    # Take the last 4 turns for compact resolution context
    recent_history = history[-4:]
    history_repr: list[str] = []
    for m in recent_history:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        # Sanitize / trim content to avoid massive context
        trimmed = content[:300].replace("\n", " ")
        history_repr.append(f"{role.upper()}: {trimmed}")

    formatted_history = "\n".join(history_repr)

    prompt = (
        "Given the recent conversation history and a follow-up query, determine if the query "
        "contains ambiguous references (e.g. 'it', 'that', 'the second one', 'why?') and rewrite "
        "it into a clear, standalone search query in the same language.\n\n"
        "Recent Conversation:\n"
        f"<<<CONVERSATION_HISTORY>>>\n{formatted_history}\n<<<CONVERSATION_HISTORY>>>\n\n"
        "Follow-up Query:\n"
        f"<<<USER_CONTENT>>>\n{clean_query}\n<<<USER_CONTENT>>>\n\n"
        'Respond with a JSON object matching the schema: {"rewritten_query": "...", "has_reference": true/false}.'
    )

    llm = get_llm_service()
    try:
        result, _ = llm.generate_json(prompt, RewrittenQuerySchema)
        rewritten = result.rewritten_query.strip() or clean_query
        logger.info(
            "Query rewrite evaluation",
            has_reference=result.has_reference,
            original_len=len(clean_query),
            rewritten_len=len(rewritten),
        )
        return rewritten
    except Exception as e:
        logger.warning(
            "Failed to rewrite query; falling back to original query",
            query_len=len(clean_query),
            error=str(e),
        )
        return clean_query
