"""Pydantic schemas for Knowledge Vault cross-modal semantic search."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Payload for text-based semantic search across Knowledge Vault."""

    query: str = Field(..., min_length=1, description="Natural language search query")
    modalities: list[str] | None = Field(
        default=None,
        description="Filter by media modalities: 'text', 'audio', 'image'",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Optional filter by conversation ID",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of ranked results to return",
    )
    rerank: bool = Field(
        default=False,
        description="Whether to perform LLM relevance reranking on top candidates",
    )
    date_from: datetime | None = Field(
        default=None,
        description="Optional ISO timestamp filter start",
    )
    date_to: datetime | None = Field(
        default=None,
        description="Optional ISO timestamp filter end",
    )
    language: str | None = Field(
        default=None,
        description="Optional language code filter (e.g. 'en', 'hi', 'ta')",
    )


class SearchResult(BaseModel):
    """Individual item retrieved across Knowledge Vault."""

    id: str = Field(..., description="Unique entry identifier")
    modality: str = Field(..., description="Media modality: 'text', 'audio', or 'image'")
    score: float = Field(..., description="Relevance score (higher is more relevant)")
    snippet: str = Field(..., description="Preview snippet or textual representation")
    attachment_id: str | None = Field(
        default=None, description="Linked attachment ID if applicable"
    )
    conversation_id: str | None = Field(
        default=None, description="Linked conversation ID if applicable"
    )
    start: float | None = Field(
        default=None, description="Start timestamp in seconds (for audio/transcripts)"
    )
    end: float | None = Field(
        default=None, description="End timestamp in seconds (for audio/transcripts)"
    )
    deep_link: str = Field(
        ...,
        description="Client navigation deep link (e.g. /conversations/{id}?attachment={att_id}&t={start})",
    )


class SearchResponse(BaseModel):
    """List of retrieved search results and query execution metadata."""

    query: str
    total_results: int
    results: list[SearchResult]
    latency_ms: float


class SearchStats(BaseModel):
    """Summary counts of indexed items in Knowledge Vault."""

    total: int = Field(default=0, description="Total indexed items")
    text: int = Field(default=0, description="Indexed text messages and notes")
    audio: int = Field(default=0, description="Indexed audio transcript segments")
    image: int = Field(default=0, description="Indexed images and captions")


class ReindexResponse(BaseModel):
    """Response returned upon initiating a vault reindex job."""

    job_id: str
    status: str
    message: str
