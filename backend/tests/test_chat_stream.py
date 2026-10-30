"""Integration tests for chat streaming (SSE) and sync endpoints."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message


@pytest.mark.asyncio
async def test_chat_sse_streaming(
    client: AsyncClient, auth_headers: dict[str, str], db: Session
) -> None:
    # 1. Create a conversation
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "New Conversation"},
        headers=auth_headers,
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    # 2. Post a message with streaming (default)
    events: list[str] = []
    tokens: list[str] = []
    done_payload: dict | None = None

    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "What is the airspeed velocity of an unladen swallow?"},
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        current_event: str = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                current_event = line.replace("event: ", "").strip()
                events.append(current_event)
            elif line.startswith("data: "):
                raw_data = line.replace("data: ", "").strip()
                data_obj = json.loads(raw_data)
                if current_event == "token":
                    tokens.append(data_obj.get("token", ""))
                elif current_event == "done":
                    done_payload = data_obj

    # 3. Verify event flow
    assert "status" in events
    assert "token" in events
    assert "done" in events
    assert len(tokens) > 0
    assert done_payload is not None
    assert done_payload["role"] == "assistant"
    assert len(done_payload["content"]) > 0

    # 4. Verify DB persistence of both user and assistant messages
    msgs = db.query(Message).filter(Message.conversation_id == conv_id).all()
    assert len(msgs) == 2
    roles = {m.role for m in msgs}
    assert "user" in roles
    assert "assistant" in roles

    # 5. Verify auto-titling happened
    updated_conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    assert updated_conv is not None
    assert updated_conv.title != "New Conversation"


@pytest.mark.asyncio
async def test_chat_sync_non_streaming(
    client: AsyncClient, auth_headers: dict[str, str], db: Session
) -> None:
    # 1. Create a conversation
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Sync Test"},
        headers=auth_headers,
    )
    conv_id = conv_res.json()["id"]

    # 2. Post with ?stream=false
    msg_res = await client.post(
        f"/api/v1/conversations/{conv_id}/messages?stream=false",
        json={"content": "Can you summarize machine learning?"},
        headers=auth_headers,
    )
    assert msg_res.status_code == 201
    data = msg_res.json()
    assert data["role"] == "assistant"
    assert len(data["content"]) > 0
    assert data["conversation_id"] == conv_id
