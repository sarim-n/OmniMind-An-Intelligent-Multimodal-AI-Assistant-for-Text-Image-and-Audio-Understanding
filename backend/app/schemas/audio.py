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


class MeetingActionItem(BaseModel):
    """Action item derived specifically from meeting audio with provenance timestamp."""

    owner: str = Field(default="Unassigned", description="Task owner or responsible party")
    task: str = Field(..., description="Actionable deliverable")
    deadline: str | None = Field(default=None, description="Target completion timeframe")
    source_timestamp: str | None = Field(
        default=None, description="Audio timestamp reference (e.g. 01:23 or 83.5s)"
    )


class TopicTimelineItem(BaseModel):
    """Segment within a chronological topic timeline."""

    topic: str = Field(..., description="Topic label")
    start: float = Field(..., ge=0.0, description="Start timestamp in seconds")
    end: float = Field(..., ge=0.0, description="End timestamp in seconds")
    summary: str = Field(..., description="Overview of discussion in this segment")


class TalkTimeItem(BaseModel):
    """Speaker or segment speech time distribution for visual charts."""

    speaker: str = Field(..., description="Speaker label or channel identifier")
    duration_sec: float = Field(..., ge=0.0, description="Total speech duration in seconds")
    percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of total talk time")


class TopicTimelineChartItem(BaseModel):
    """Simplified timeline entry tailored for chart visualizations."""

    topic: str
    start: float
    end: float


class MeetingInsights(BaseModel):
    """Comprehensive analytical meeting insights structured for executive review and charts."""

    inferred_agenda: list[str] = Field(
        default_factory=list, description="Inferred meeting agenda items"
    )
    decisions: list[str] = Field(
        default_factory=list, description="Decisions and consensus reached"
    )
    action_items: list[MeetingActionItem] = Field(
        default_factory=list, description="Table of assigned action items"
    )
    unresolved_questions: list[str] = Field(
        default_factory=list, description="Unresolved topics or parking lot items"
    )
    per_topic_timeline: list[TopicTimelineItem] = Field(
        default_factory=list, description="Ordered chronological topic segments"
    )
    executive_summary: str = Field(
        ..., description="Cohesive 5-line executive summary of meeting outcomes"
    )
    talk_time: list[TalkTimeItem] = Field(
        default_factory=list,
        description="Talk-time dataset for speaker distribution charts",
    )
    topic_timeline: list[TopicTimelineChartItem] = Field(
        default_factory=list,
        description="Topic-timeline dataset for progression charts",
    )
    errors: list[str] | None = Field(
        default=None, description="Diagnostic messages or warnings if partial"
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
