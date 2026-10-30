"""Tests for conversation and message endpoints, including cross-user isolation and cascade deletes."""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.storage_service import get_storage_root


@pytest.mark.asyncio
async def test_create_conversation(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test creating a conversation."""
    response = await client.post(
        "/api/v1/conversations",
        json={"title": "Multimodal Project Planning"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Multimodal Project Planning"
    assert "id" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_list_conversations_paginated(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Test listing conversations with pagination."""
    for i in range(5):
        await client.post(
            "/api/v1/conversations",
            json={"title": f"Conversation {i}"},
            headers=auth_headers,
        )

    response = await client.get("/api/v1/conversations?page=1&page_size=3", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    assert len(data["items"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 3


@pytest.mark.asyncio
async def test_get_and_patch_conversation(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Test getting and updating a conversation."""
    create_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Initial Title"},
        headers=auth_headers,
    )
    conv_id = create_res.json()["id"]

    # Get conversation
    get_res = await client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Initial Title"

    # Patch conversation
    patch_res = await client.patch(
        f"/api/v1/conversations/{conv_id}",
        json={"title": "Updated Title", "summary": "Short summary of discussion"},
        headers=auth_headers,
    )
    assert patch_res.status_code == 200
    updated_data = patch_res.json()
    assert updated_data["title"] == "Updated Title"
    assert updated_data["summary"] == "Short summary of discussion"


@pytest.mark.asyncio
async def test_cross_user_isolation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_b: dict[str, str],
) -> None:
    """Test that User B cannot read, update, delete, or list messages for User A's conversation (returns 404)."""
    # User A creates a conversation
    create_res = await client.post(
        "/api/v1/conversations",
        json={"title": "User A Private Conversation"},
        headers=auth_headers,
    )
    conv_id = create_res.json()["id"]

    # User B attempts to access it -> 404
    get_res = await client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers_b)
    assert get_res.status_code == 404

    # User B attempts to patch it -> 404
    patch_res = await client.patch(
        f"/api/v1/conversations/{conv_id}",
        json={"title": "Hacked Title"},
        headers=auth_headers_b,
    )
    assert patch_res.status_code == 404

    # User B attempts to list messages -> 404
    msg_res = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers_b)
    assert msg_res.status_code == 404

    # User B attempts to delete it -> 404
    del_res = await client.delete(f"/api/v1/conversations/{conv_id}", headers=auth_headers_b)
    assert del_res.status_code == 404


@pytest.mark.asyncio
async def test_messages_crud(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test appending and listing messages inside a conversation."""
    create_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Chat Session"},
        headers=auth_headers,
    )
    conv_id = create_res.json()["id"]

    # Create message with stream=false
    msg_res = await client.post(
        f"/api/v1/conversations/{conv_id}/messages?stream=false",
        json={
            "role": "user",
            "content": "Please analyze this audio recording.",
            "language": "en",
            "modalities": ["text", "audio"],
        },
        headers=auth_headers,
    )
    assert msg_res.status_code == 201
    msg_data = msg_res.json()
    assert msg_data["role"] == "assistant"
    assert "mock" in msg_data["content"].lower() or len(msg_data["content"]) > 0

    # List messages (should include both user message and assistant reply)
    list_res = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    assert list_res.status_code == 200
    list_data = list_res.json()
    user_item = next(m for m in list_data["items"] if m["role"] == "user")
    assert user_item["content"] == "Please analyze this audio recording."


@pytest.mark.asyncio
async def test_cascade_delete_removes_files_and_db_records(
    client: AsyncClient, auth_headers: dict[str, str], db: Session
) -> None:
    """Test that deleting a conversation cascades to messages, attachments, and unlinks files from disk."""
    # 1. Create conversation
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Conversation to Delete"},
        headers=auth_headers,
    )
    conv_id = conv_res.json()["id"]

    # 2. Create message
    msg_res = await client.post(
        f"/api/v1/conversations/{conv_id}/messages?stream=false",
        json={"role": "user", "content": "Sample message"},
        headers=auth_headers,
    )
    msg_id = msg_res.json()["id"]

    # 3. Upload a small valid PNG attachment
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload_res = await client.post(
        f"/api/v1/conversations/{conv_id}/attachments?kind=image&message_id={msg_id}",
        files={"file": ("test.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    assert upload_res.status_code == 201
    att_data = upload_res.json()
    att_path_rel = att_data["path"]

    # Verify file physically exists on disk
    storage_root = get_storage_root()
    physical_file = storage_root / att_path_rel
    assert physical_file.is_file(), f"Expected file {physical_file} to exist on disk"

    # 4. Delete the conversation
    del_res = await client.delete(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # 5. Verify conversation and message are deleted from DB
    assert db.query(Conversation).filter(Conversation.id == conv_id).first() is None
    assert db.query(Message).filter(Message.id == msg_id).first() is None
    assert db.query(Attachment).filter(Attachment.id == att_data["id"]).first() is None

    # 6. Verify file is deleted from disk
    assert not physical_file.exists(), f"Expected file {physical_file} to be deleted from disk"
