"""Tests for MeetingInsightsService, topic timelines, action items, diarization fallback, and endpoints."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.transcript import Transcript
from app.models.user import User
from app.schemas.audio import MeetingInsights
from app.services.meeting_insights import get_meeting_insights_service
from app.services.search_service import get_search_service


@pytest.fixture
def auth_headers(db: Session) -> dict[str, str]:
    """Create test user and return auth headers."""
    user = User(email="meeting_tester@vault.com", hashed_password="hashedpassword123")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def test_meeting_insights_schema_and_timeline_ordering() -> None:
    """Verify meeting insights JSON schema, timeline bounds, and chronological order."""
    service = get_meeting_insights_service()

    sample_transcript = (
        "Project Lead: Welcome everyone to the quarterly operational meeting. "
        "Alice: The budget for Q3 marketing is formally approved at fifty thousand dollars. "
        "Bob: Engineering will deploy the database optimizations by next Tuesday. "
        "Carol: We still have unresolved questions regarding server licensing costs."
    )
    sample_segments = [
        {
            "start": 0.0,
            "end": 30.0,
            "text": "Welcome everyone to the quarterly operational meeting.",
        },
        {
            "start": 30.0,
            "end": 90.0,
            "text": "The budget for Q3 marketing is formally approved.",
        },
        {
            "start": 90.0,
            "end": 150.0,
            "text": "Engineering will deploy database optimizations.",
        },
        {
            "start": 150.0,
            "end": 210.0,
            "text": "Unresolved questions regarding server licensing.",
        },
    ]
    total_duration = 210.0

    insights = service.generate_meeting_insights(
        transcript_text=sample_transcript,
        segments=sample_segments,
        total_duration=total_duration,
        audio_path=None,  # No pyannote diarization path
    )

    # 1. Validate Pydantic schema
    assert isinstance(insights, MeetingInsights)
    assert len(insights.inferred_agenda) > 0
    assert len(insights.decisions) > 0
    assert len(insights.action_items) > 0
    assert len(insights.unresolved_questions) > 0
    assert len(insights.per_topic_timeline) > 0
    assert len(insights.talk_time) > 0
    assert len(insights.topic_timeline) > 0
    assert len(insights.executive_summary.splitlines()) >= 3

    # 2. Assert timeline segments are chronologically ordered and bounded
    prev_start = -1.0
    for seg in insights.per_topic_timeline:
        assert seg.start >= prev_start
        assert seg.start >= 0.0
        assert seg.end <= total_duration
        assert seg.end >= seg.start
        assert len(seg.summary) > 0
        prev_start = seg.start


def test_diarization_absence_graceful_fallback() -> None:
    """Verify that when pyannote / HF_TOKEN is absent, no error occurs and fallback talk time is returned."""
    service = get_meeting_insights_service()
    insights = service.generate_meeting_insights(
        transcript_text="Speaker 1: Hello. Speaker 2: World.",
        segments=[{"start": 0.0, "end": 10.0, "text": "Speaker 1: Hello"}],
        total_duration=10.0,
        audio_path=Path("non_existent_audio.wav"),
    )
    assert isinstance(insights, MeetingInsights)
    assert len(insights.talk_time) > 0
    total_pct = sum(t.percentage for t in insights.talk_time)
    assert 99.0 <= total_pct <= 101.0  # Around 100%


@pytest.mark.asyncio
async def test_meeting_insights_api_endpoints(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: Session,
) -> None:
    """Verify GET and POST /api/v1/audio/{attachment_id}/meeting endpoints and vault indexing."""
    user = db.query(User).filter(User.email == "meeting_tester@vault.com").first()
    assert user is not None

    conv = Conversation(user_id=user.id, title="Meeting Audio Turn")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    msg = Message(conversation_id=conv.id, role="user", content="Uploaded team standup recording")
    db.add(msg)
    db.commit()
    db.refresh(msg)

    att = Attachment(
        user_id=user.id,
        message_id=msg.id,
        type="audio",
        path="audio/team_meeting.wav",
        mime="audio/wav",
        size=4096,
        duration_sec=180.0,  # 3 minutes (longer than MEETING_MIN_DURATION_SEC)
        metadata_={"original_filename": "team_meeting.wav"},
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    transcript = Transcript(
        attachment_id=att.id,
        language="en",
        text="Alice: We finalized the sprint objectives. Bob: I will submit the pull request by Friday.",
        segments=[
            {
                "start": 0.0,
                "end": 90.0,
                "text": "Alice: We finalized the sprint objectives.",
            },
            {
                "start": 90.0,
                "end": 180.0,
                "text": "Bob: I will submit the pull request by Friday.",
            },
        ],
    )
    db.add(transcript)
    db.commit()
    db.refresh(transcript)

    # 1. GET /api/v1/audio/{att.id}/meeting generates insights on demand
    get_res = await client.get(f"/api/v1/audio/{att.id}/meeting", headers=auth_headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert "inferred_agenda" in data
    assert "decisions" in data
    assert "action_items" in data
    assert "per_topic_timeline" in data
    assert "executive_summary" in data
    assert len(data["per_topic_timeline"]) > 0

    # 2. Verify decisions and action items were indexed into Knowledge Vault
    search_svc = get_search_service()
    vault_res = search_svc.search_vault(
        query="sprint objectives pull request", user_id=user.id, top_k=5
    )
    assert len(vault_res) > 0
    assert any(r.attachment_id == att.id for r in vault_res)

    # 3. POST /api/v1/audio/{att.id}/meeting forces regeneration
    post_res = await client.post(f"/api/v1/audio/{att.id}/meeting", headers=auth_headers)
    assert post_res.status_code == 200
    post_data = post_res.json()
    assert "per_topic_timeline" in post_data
    assert len(post_data["per_topic_timeline"]) > 0


@pytest.mark.asyncio
async def test_long_audio_triggers_auto_insights_in_orchestration(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: Session,
) -> None:
    """Verify that an audio file longer than MEETING_MIN_DURATION_SEC auto-generates meeting insights."""
    user = db.query(User).filter(User.email == "meeting_tester@vault.com").first()
    assert user is not None

    conv = Conversation(user_id=user.id, title="Auto Meeting Turn")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    # Send a message with audio
    import wave

    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000 * 2)  # 2s silent audio in mock
    wav_bytes = wav_buf.getvalue()

    # Note: in mock mode or test, probe_audio_duration_seconds or mock ASR duration
    # Setting MEETING_MIN_DURATION_SEC temporarily to 1.0 ensures auto-triggering
    orig_min_dur = settings.MEETING_MIN_DURATION_SEC
    try:
        settings.MEETING_MIN_DURATION_SEC = 1.0  # Lower threshold for unit test

        events: list[str] = []
        async with client.stream(
            "POST",
            f"/api/v1/conversations/{conv.id}/messages",
            data={"content": "Please transcribe this meeting discussion"},
            files={"audio": ("annual_sync.wav", wav_bytes, "audio/wav")},
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    events.append(line.replace("event: ", "").strip())

        assert "transcript" in events
        assert "done" in events

        # Verify meeting insights were stored in transcript record
        att = (
            db.query(Attachment)
            .join(Message, Attachment.message_id == Message.id)
            .filter(Message.conversation_id == conv.id, Attachment.type == "audio")
            .first()
        )
        assert att is not None
        transcript = db.query(Transcript).filter(Transcript.attachment_id == att.id).first()
        assert transcript is not None
        assert transcript.insights is not None
        assert "per_topic_timeline" in transcript.insights
    finally:
        settings.MEETING_MIN_DURATION_SEC = orig_min_dur
