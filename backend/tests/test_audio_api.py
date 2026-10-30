"""Integration tests for audio transcription and insights API endpoints."""

import asyncio
import io
import math
import struct
import wave

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.transcript import Transcript


def make_test_wav_bytes(duration_sec: float = 2.0, sample_rate: int = 16000) -> bytes:
    """Generate in-memory WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(duration_sec * sample_rate)
        frames = bytearray()
        for i in range(num_frames):
            t = float(i) / sample_rate
            val = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * 440.0 * t))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(frames)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_audio_transcribe_upload_and_poll_job(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: Session,
) -> None:
    wav_bytes = make_test_wav_bytes(duration_sec=2.0)

    # 1. Post upload to transcribe
    upload_res = await client.post(
        "/api/v1/audio/transcribe",
        files={"file": ("meeting_speech.wav", wav_bytes, "audio/wav")},
        data={"language": "en", "word_timestamps": "true"},
        headers=auth_headers,
    )
    assert upload_res.status_code == 202
    job_data = upload_res.json()
    job_id = job_data["id"]
    assert job_data["status"] in ("queued", "running", "done")

    # 2. Wait a moment for background task to complete and poll job
    for _ in range(150):
        await asyncio.sleep(0.1)
        poll_res = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        assert poll_res.status_code == 200
        status_data = poll_res.json()
        if status_data["status"] in ("done", "failed"):
            break

    assert status_data["status"] == "done"
    result = status_data["result"]
    assert result is not None
    assert "transcript_id" in result
    assert "text" in result
    assert result["language"] == "en"

    attachment_id = result["attachment_id"]

    # 3. Retrieve transcript
    trans_res = await client.get(f"/api/v1/audio/{attachment_id}/transcript", headers=auth_headers)
    assert trans_res.status_code == 200
    trans_data = trans_res.json()
    assert trans_data["attachment_id"] == attachment_id
    assert len(trans_data["text"]) > 0
    assert isinstance(trans_data["segments"], list)
    assert len(trans_data["segments"]) > 0

    # 4. Request insights on transcript
    insights_res = await client.post(
        f"/api/v1/audio/{attachment_id}/insights",
        json={"output_language": "English"},
        headers=auth_headers,
    )
    assert insights_res.status_code == 200
    insights_data = insights_res.json()
    assert len(insights_data["short_summary"]) > 0
    assert len(insights_data["detailed_summary"]) > 0
    assert isinstance(insights_data["key_points"], list)
    assert isinstance(insights_data["action_items"], list)

    # Verify transcript in DB has summary and insights persisted
    db_trans = db.query(Transcript).filter(Transcript.attachment_id == attachment_id).first()
    assert db_trans is not None
    assert db_trans.summary == insights_data["short_summary"]
    assert db_trans.insights is not None


@pytest.mark.asyncio
async def test_audio_endpoints_cross_user_isolation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_b: dict[str, str],
) -> None:
    wav_bytes = make_test_wav_bytes(duration_sec=1.5)

    # User A uploads audio
    res = await client.post(
        "/api/v1/audio/transcribe",
        files={"file": ("private_audio.wav", wav_bytes, "audio/wav")},
        headers=auth_headers,
    )
    assert res.status_code == 202
    job_id = res.json()["id"]

    # Wait for completion
    for _ in range(100):
        await asyncio.sleep(0.1)
        j_res = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        if j_res.json()["status"] == "done":
            break

    att_id = j_res.json()["result"]["attachment_id"]

    # User B tries to fetch User A's transcript -> 404
    trans_b = await client.get(f"/api/v1/audio/{att_id}/transcript", headers=auth_headers_b)
    assert trans_b.status_code == 404

    # User B tries to request insights on User A's audio -> 404
    insights_b = await client.post(
        f"/api/v1/audio/{att_id}/insights",
        json={"output_language": "English"},
        headers=auth_headers_b,
    )
    assert insights_b.status_code == 404


@pytest.mark.asyncio
async def test_audio_transcribe_rejects_exceeded_duration(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wav_bytes = make_test_wav_bytes(duration_sec=3.0)

    # Set MAX_AUDIO_DURATION_SEC to 1 second
    monkeypatch.setattr(settings, "MAX_AUDIO_DURATION_SEC", 1)

    res = await client.post(
        "/api/v1/audio/transcribe",
        files={"file": ("too_long.wav", wav_bytes, "audio/wav")},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "exceeds maximum allowed limit" in res.json()["detail"]
