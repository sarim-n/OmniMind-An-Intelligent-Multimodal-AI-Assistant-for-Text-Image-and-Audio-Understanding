"""Pydantic schemas for audio transcription, insights extraction, and jobs."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionItem(BaseModel):
    """Action item identified within spoken conversation."""

    owner: str = Field(default="Unassigned", description="Person or entity responsible")
    task: str = Field(..., description="Actionable task description")
    deadline: str | None = Field(default=None, description="Due date or timeframe, if mentioned")


class Entities(BaseModel):
    """Named entities categorized by type."""

    people: list[str] = Field(default_factory=list, description="Names of individuals")
    orgs: list[str] = Field(default_factory=list, description="Organizations and companies")
    dates: list[str] = Field(default_factory=list, description="Dates, times, or milestones")
    places: list[str] = Field(default_factory=list, description="Locations, cities, or venues")


class AudioInsights(BaseModel):
    """Structured analytical insights derived from an audio transcript."""

    short_summary: str = Field(..., description="One or two sentence executive overview")
    detailed_summary: str = Field(..., description="Comprehensive paragraph summary")
    key_points: list[str] = Field(default_factory=list, description="Core takeaways")
    topics: list[str] = Field(default_factory=list, description="Main themes discussed")
    entities: Entities = Field(default_factory=Entities, description="Extracted named entities")
    action_items: list[ActionItem] = Field(
        default_factory=list, description="Assigned action items"
    )
    decisions: list[str] = Field(
        default_factory=list, description="Agreements and decisions reached"
    )
    open_questions: list[str] = Field(
        default_factory=list, description="Unresolved topics or questions"
    )
    sentiment: str = Field(default="neutral", description="Overall conversational tone")
    errors: list[str] | None = Field(
        default=None, description="Diagnostic errors if partial results returned"
    )


class AudioTranscribeRequest(BaseModel):
    """Payload to initiate an audio transcription job."""

    attachment_id: str | None = Field(default=None, description="ID of existing audio attachment")
    language: str | None = Field(
        default=None, description="Forced language code (e.g. 'en', 'hi', 'ta')"
    )
    translate: bool = Field(
        default=False, description="Whether to translate non-English speech to English"
    )
    word_timestamps: bool = Field(
        default=False, description="Whether to return granular word-level timestamps"
    )


class AudioInsightsRequest(BaseModel):
    """Payload to request insights extraction on an audio transcript."""

    output_language: str | None = Field(
        default=None,
        description="Preferred language for output insights (defaults to transcript language)",
    )


class TranscriptRead(BaseModel):
    """Transcript response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    attachment_id: str
    language: str | None = None
    text: str
    segments: list[dict[str, Any]] | None = None
    summary: str | None = None
    insights: dict[str, Any] | None = None
