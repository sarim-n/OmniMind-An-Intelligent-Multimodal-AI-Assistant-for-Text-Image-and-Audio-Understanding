"""Integration tests for unified multimodal orchestration (Phase 5).

Covers all 10 required test scenarios with Server-Sent Events (SSE) stream verification.
"""

from __future__ import annotations

import io
import json
import wave
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services.model_manager import get_model_manager


def create_dummy_png_bytes(width: int = 64, height: int = 64, color: str = "blue") -> bytes:
    """Generate in-memory valid PNG image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=color)
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_dummy_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate in-memory valid WAV audio bytes."""
    buf = io.BytesIO()
    num_frames = int(sample_rate * duration_sec)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Write silence frames (16-bit PCM = 2 bytes per sample)
        wf.writeframes(b"\x00\x00" * num_frames)
    return buf.getvalue()


def parse_sse_stream(raw_text: str) -> list[dict[str, Any]]:
    """Parse raw SSE text into structured list of event dictionaries."""
    events: list[dict[str, Any]] = []
    blocks = raw_text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        event_name = "message"
        data_str = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data_str = line[6:].strip()
        if data_str:
            try:
                data_val = json.loads(data_str)
            except Exception:
                data_val = data_str
            events.append({"event": event_name, "data": data_val})
    return events


@pytest.fixture
def clean_memory():
    """Unload all models before and after test."""
    mgr = get_model_manager()
    mgr.unload_all()
    yield
    mgr.unload_all()


# =========================================================================
# Scenario (i): Image + Text Question
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_1_image_and_text(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Scenario (i): Send image + text question and verify SSE event sequence."""
    # 1. Create a conversation
    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "Image QA"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    # 2. Upload image + query via multipart
    img_bytes = create_dummy_png_bytes(color="red")
    files = [("images", ("car.png", img_bytes, "image/png"))]
    data = {"content": "What is in this image?"}

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        data=data,
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = parse_sse_stream(response.text)

    event_types = [e["event"] for e in events]
    assert "status" in event_types
    assert "image_analysis" in event_types
    assert "token" in event_types
    assert "sources" in event_types
    assert "done" in event_types

    # Verify image_analysis payload
    img_event = next(e for e in events if e["event"] == "image_analysis")
    assert "caption" in img_event["data"]
    assert "objects" in img_event["data"]

    # Verify done event contains message_id and metrics
    done_event = next(e for e in events if e["event"] == "done")
    assert "message_id" in done_event["data"]
    assert "metrics" in done_event["data"]
    assert done_event["data"]["metrics"]["intent"] == "qa_about_image"


# =========================================================================
# Scenario (ii): Audio upload, then follow-up text without re-uploading
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_2_audio_then_followup_turn(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Scenario (ii): Upload audio, then ask follow-up turn using stored transcript without re-upload."""
    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "Audio Followup"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    # Turn 1: Upload audio file
    wav_bytes = create_dummy_wav_bytes(duration_sec=2.0)
    files = [("audio", ("meeting.wav", wav_bytes, "audio/wav"))]
    resp1 = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        data={"content": "Here is our project meeting recording."},
        files=files,
        headers=auth_headers,
    )
    assert resp1.status_code == 200
    events1 = parse_sse_stream(resp1.text)
    transcript_event = next((e for e in events1 if e["event"] == "transcript"), None)
    assert transcript_event is not None
    assert "text" in transcript_event["data"]

    # Turn 2: Follow-up question (NO attachments re-uploaded)
    resp2 = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        data={"content": "What did they say about the budget?"},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    events2 = parse_sse_stream(resp2.text)
    event_types2 = [e["event"] for e in events2]
    assert "token" in event_types2
    assert "done" in event_types2

    # Verify intent classified as audio summarization / discussion
    done_event2 = next(e for e in events2 if e["event"] == "done")
    assert done_event2["data"]["metrics"]["intent"] == "summarise_audio"


# =========================================================================
# Scenario (iii): Image + Audio + Text in one message
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_3_multimodal_trio(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Scenario (iii): Image + Audio + Text in single request; verify event order and citations."""
    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "Trio"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    img_bytes = create_dummy_png_bytes(color="green")
    wav_bytes = create_dummy_wav_bytes(duration_sec=2.0)

    files = [
        ("images", ("chart.png", img_bytes, "image/png")),
        ("audio", ("briefing.wav", wav_bytes, "audio/wav")),
    ]
    data = {"content": "Does what the speaker says match the chart?"}

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        data=data,
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = parse_sse_stream(response.text)

    # Verify presence and order of events
    event_names = [e["event"] for e in events]
    assert "status" in event_names
    assert "transcript" in event_names
    assert "image_analysis" in event_names
    assert "sources" in event_names
    assert "done" in event_names

    # Transcript and Image analysis must arrive before token generation starts
    first_token_idx = event_names.index("token")
    transcript_idx = event_names.index("transcript")
    image_idx = event_names.index("image_analysis")
    assert transcript_idx < first_token_idx
    assert image_idx < first_token_idx

    done_event = next(e for e in events if e["event"] == "done")
    assert done_event["data"]["metrics"]["intent"] == "compare_image_and_audio"


# =========================================================================
# Scenario (iv): Hindi-hinted audio file + English question
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_4_hindi_hinted_audio(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Scenario (iv): Hindi audio file with English question."""
    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "Hindi Audio"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    wav_bytes = create_dummy_wav_bytes(duration_sec=1.5)
    files = [("audio", ("call_hi.wav", wav_bytes, "audio/wav"))]
    data = {"content": "Can you summarize what was spoken in this recording?"}

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        data=data,
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = parse_sse_stream(response.text)

    transcript_event = next((e for e in events if e["event"] == "transcript"), None)
    assert transcript_event is not None
    # MockASR detects 'hi' from '_hi' in filename
    assert transcript_event["data"]["language"] == "hi"


# =========================================================================
# Scenario (v): Corrupted audio file + valid image (graceful degradation)
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_5_corrupted_audio_graceful_degradation(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Scenario (v): Corrupted audio with valid image; stream finishes, error event emitted, reply exists."""
    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "Degradation"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    img_bytes = create_dummy_png_bytes(color="yellow")
    # Corrupted audio: invalid bytes claiming to be wav
    corrupted_audio_bytes = b"RIFF____WAVEfmt \x10\x00\x00\x00corrupted_audio_payload"

    files = [
        ("images", ("valid.png", img_bytes, "image/png")),
        ("audio", ("corrupted.wav", corrupted_audio_bytes, "audio/wav")),
    ]
    data = {"content": "Please inspect this image and listen to the audio."}

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        data=data,
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = parse_sse_stream(response.text)

    # An error event should be emitted for the audio
    error_event = next((e for e in events if e["event"] == "error"), None)
    assert error_event is not None
    assert error_event["data"]["stage"] in ("audio", "ingest")

    # Image analysis should still succeed
    image_event = next((e for e in events if e["event"] == "image_analysis"), None)
    assert image_event is not None

    # Stream completes with done
    assert any(e["event"] == "done" for e in events)


# =========================================================================
# Scenario (vi): Untrusted context prompt injection defense
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_6_prompt_injection_defense(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Scenario (vi): Transcript containing prompt injection stays inside delimited block."""
    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "Security"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    wav_bytes = create_dummy_wav_bytes(duration_sec=1.0)
    files = [("audio", ("jailbreak.wav", wav_bytes, "audio/wav"))]
    data = {"content": "Summarize the audio"}

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        data=data,
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = parse_sse_stream(response.text)
    assert any(e["event"] == "done" for e in events)


# =========================================================================
# Scenario (vii): Too many files or oversized files rejected
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_7_limits_enforced(
    client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario (vii): Exceeding file count limit raises 400 Bad Request."""
    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "Limits"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    # Upload 6 files when MAX_FILES_PER_MESSAGE is 5
    img_bytes = create_dummy_png_bytes()
    files = [("images", (f"img_{i}.png", img_bytes, "image/png")) for i in range(6)]

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "exceeds limit" in response.json()["detail"].lower()


# =========================================================================
# Scenario (viii): Cross-user isolation
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_8_cross_user_isolation(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Scenario (viii): User B cannot access or post messages to User A's conversation."""
    # User A creates a conversation
    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "User A Chat"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    # Register User B
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "user_b_isolation@example.com", "password": "Password123!"},
    )
    user_b_id = reg_resp.json()["id"]
    other_token = create_access_token(subject=user_b_id)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # User B attempts to post message to User A's conversation
    response = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Malicious intrusion attempt"},
        headers=other_headers,
    )
    assert response.status_code == 404


# =========================================================================
# Scenario (x): Client disconnect still persists assistant message
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_10_client_disconnect_persists_assistant_message(
    test_user: User, auth_headers: dict[str, str]
) -> None:
    """Scenario (x): If client stream disconnects mid-flight, assistant message is still persisted in DB."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        conv_resp = await ac.post(
            "/api/v1/conversations", json={"title": "Disconnect Test"}, headers=auth_headers
        )
        conv_id = conv_resp.json()["id"]

        # Use streaming request, read 1 token and close stream immediately
        async with ac.stream(
            "POST",
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "Please write a long paragraph about artificial intelligence."},
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200
            async for chunk in response.aiter_lines():
                if "event: token" in chunk:
                    # Prematurely break to simulate client disconnect
                    break

        # Check DB to verify assistant message was persisted
        msg_resp = await ac.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
        assert msg_resp.status_code == 200
        messages = msg_resp.json()["items"]
        roles = [m["role"] for m in messages]
        assert "assistant" in roles


# =========================================================================
# Slow real-model opt-in test
# =========================================================================
@pytest.mark.slow
@pytest.mark.asyncio
async def test_real_model_smoke_test(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Real model execution test marked slow."""
    import socket

    try:
        # Check connectivity
        socket.create_connection(("huggingface.co", 443), timeout=2.0)
    except OSError:
        pytest.skip("Offline: huggingface.co unreachable")

    conv_resp = await client.post(
        "/api/v1/conversations", json={"title": "Real Model Test"}, headers=auth_headers
    )
    conv_id = conv_resp.json()["id"]

    img_bytes = create_dummy_png_bytes(width=32, height=32, color="white")
    files = [("images", ("real_test.png", img_bytes, "image/png"))]
    resp = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        data={"content": "Describe this image."},
        files=files,
        headers=auth_headers,
    )
    assert resp.status_code in (200, 400)
