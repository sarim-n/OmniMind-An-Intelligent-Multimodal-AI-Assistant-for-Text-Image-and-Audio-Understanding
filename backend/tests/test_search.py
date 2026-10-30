"""Tests for Knowledge Vault cross-modal semantic search, RRF fusion, filters, and user isolation."""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.image_embedding_service import get_image_embedding_service
from app.services.search_service import get_search_service


@pytest.fixture
def auth_headers_user_a(db: Session) -> dict[str, str]:
    """Create User A and return auth headers."""
    user = User(email="usera@vault.com", hashed_password="hashedpassword123")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_b(db: Session) -> dict[str, str]:
    """Create User B and return auth headers."""
    user = User(email="userb@vault.com", hashed_password="hashedpassword123")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_knowledge_vault_mixed_modalities_and_search(
    client: AsyncClient,
    auth_headers_user_a: dict[str, str],
    auth_headers_user_b: dict[str, str],
    db: Session,
) -> None:
    """Index 5+ mixed items and verify text->audio, text->image, cross-lingual, and isolation."""
    search_svc = get_search_service()
    user_a = db.query(User).filter(User.email == "usera@vault.com").first()
    assert user_a is not None
    user_a_id = user_a.id

    # Create conversation and attachments for User A
    conv = Conversation(user_id=user_a_id, title="Vault Conversation")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    # 1. Index 5+ mixed modality items for User A
    # Item 1: Audio transcript segment about budget approval
    search_svc.index_transcript(
        user_id=user_a_id,
        conversation_id=conv.id,
        attachment_id="att_aud_budget",
        transcript_data={
            "text": "The executive committee approved the fifty thousand marketing budget.",
            "language": "en",
            "segments": [
                {
                    "start": 12.0,
                    "end": 28.0,
                    "text": "The executive committee approved the fifty thousand marketing budget.",
                }
            ],
            "insights": {
                "meeting_insights": {
                    "decisions": ["Marketing budget of fifty thousand approved for Q3"],
                    "action_items": [
                        {
                            "owner": "Alice",
                            "task": "Allocate marketing spend",
                            "deadline": "Friday",
                        }
                    ],
                }
            },
        },
    )

    # Item 2: Image analysis with caption of a red car
    search_svc.index_image_analysis(
        user_id=user_a_id,
        conversation_id=conv.id,
        attachment_id="att_img_car",
        analysis_data={
            "caption": "A bright red sports car parked in front of modern glass skyscraper",
            "ocr_text": "Speedster 2024",
        },
        image_path="red_sports_car.png",
    )

    # Item 3: Image analysis of architecture diagram
    search_svc.index_image_analysis(
        user_id=user_a_id,
        conversation_id=conv.id,
        attachment_id="att_img_diag",
        analysis_data={
            "caption": "Software architecture diagram illustrating FastAPI microservices and ChromaDB",
            "ocr_text": "Microservices Arch",
        },
        image_path="architecture_diagram.png",
    )

    # Item 4: Text message about kubernetes
    search_svc.index_message(
        user_id=user_a_id,
        conversation_id=conv.id,
        message_id="msg_k8s",
        content="Kubernetes cluster production upgrade is scheduled for Sunday midnight.",
        role="assistant",
        language="en",
    )

    # Item 5: Cross-lingual Hindi item about solar power
    search_svc.index_message(
        user_id=user_a_id,
        conversation_id=conv.id,
        message_id="msg_solar_hi",
        content="सौर ऊर्जा ग्रिड परियोजना का निर्माण मुख्यालय में सफलतापूर्वक पूरा हुआ।",  # Solar energy grid project completed
        role="user",
        language="hi",
    )

    # -------------------------------------------------------------------------
    # Verification 1: text -> audio segment retrieval
    # -------------------------------------------------------------------------
    res_audio = await client.post(
        "/api/v1/search",
        json={"query": "approved marketing budget fifty thousand", "top_k": 5},
        headers=auth_headers_user_a,
    )
    assert res_audio.status_code == 200
    data_audio = res_audio.json()
    assert data_audio["total_results"] > 0
    top_audio = data_audio["results"][0]
    assert top_audio["modality"] == "audio"
    assert top_audio["attachment_id"] == "att_aud_budget"
    assert "conversations" in top_audio["deep_link"]

    # -------------------------------------------------------------------------
    # Verification 2: text -> image retrieval
    # -------------------------------------------------------------------------
    res_image = await client.post(
        "/api/v1/search",
        json={"query": "red sports car glass skyscraper", "top_k": 5},
        headers=auth_headers_user_a,
    )
    assert res_image.status_code == 200
    data_image = res_image.json()
    assert data_image["total_results"] > 0
    top_img = data_image["results"][0]
    assert top_img["modality"] == "image"
    assert top_img["attachment_id"] == "att_img_car"

    # -------------------------------------------------------------------------
    # Verification 3: Cross-lingual query retrieval
    # -------------------------------------------------------------------------
    # Hindi query for solar energy retrieves the solar item
    res_xl = await client.post(
        "/api/v1/search",
        json={"query": "सौर ऊर्जा परियोजना", "top_k": 5},
        headers=auth_headers_user_a,
    )
    assert res_xl.status_code == 200
    data_xl = res_xl.json()
    assert data_xl["total_results"] > 0
    found_solar = any(
        "solar" in r["id"].lower() or "सौर" in r["snippet"] for r in data_xl["results"]
    )
    assert found_solar

    # -------------------------------------------------------------------------
    # Verification 4: Filters (modality, conversation_id, date)
    # -------------------------------------------------------------------------
    # Filter by modality == 'audio'
    res_filter_mod = await client.post(
        "/api/v1/search",
        json={"query": "budget car kubernetes", "modalities": ["audio"], "top_k": 10},
        headers=auth_headers_user_a,
    )
    assert res_filter_mod.status_code == 200
    for r in res_filter_mod.json()["results"]:
        assert r["modality"] == "audio"

    # Filter by conversation_id
    res_filter_conv = await client.post(
        "/api/v1/search",
        json={"query": "budget", "conversation_id": conv.id, "top_k": 5},
        headers=auth_headers_user_a,
    )
    assert res_filter_conv.status_code == 200
    assert res_filter_conv.json()["total_results"] > 0

    # Filter by non-existent conversation_id
    res_filter_fake = await client.post(
        "/api/v1/search",
        json={"query": "budget", "conversation_id": "non-existent-conv-id", "top_k": 5},
        headers=auth_headers_user_a,
    )
    assert res_filter_fake.status_code == 200
    assert res_filter_fake.json()["total_results"] == 0

    # Filter by future date range
    future_date = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    res_filter_date = await client.post(
        "/api/v1/search",
        json={"query": "budget", "date_from": future_date, "top_k": 5},
        headers=auth_headers_user_a,
    )
    assert res_filter_date.status_code == 200
    assert res_filter_date.json()["total_results"] == 0

    # -------------------------------------------------------------------------
    # Verification 5: User Isolation (User B never sees User A's items)
    # -------------------------------------------------------------------------
    res_user_b = await client.post(
        "/api/v1/search",
        json={"query": "marketing budget fifty thousand", "top_k": 10},
        headers=auth_headers_user_b,
    )
    assert res_user_b.status_code == 200
    assert res_user_b.json()["total_results"] == 0

    stats_b = await client.get("/api/v1/search/stats", headers=auth_headers_user_b)
    assert stats_b.status_code == 200
    assert stats_b.json()["total"] == 0

    # -------------------------------------------------------------------------
    # Verification 6: Search Stats for User A
    # -------------------------------------------------------------------------
    stats_a = await client.get("/api/v1/search/stats", headers=auth_headers_user_a)
    assert stats_a.status_code == 200
    data_stats_a = stats_a.json()
    assert data_stats_a["total"] >= 5
    assert data_stats_a["audio"] >= 1
    assert data_stats_a["image"] >= 1
    assert data_stats_a["text"] >= 1

    # -------------------------------------------------------------------------
    # Verification 7: Search by Image (multipart upload)
    # -------------------------------------------------------------------------
    img_byte_io = io.BytesIO()
    Image.new("RGB", (64, 64), color="red").save(img_byte_io, format="PNG")
    img_bytes = img_byte_io.getvalue()

    res_by_img = await client.post(
        "/api/v1/search/by-image",
        files={"file": ("query_car.png", img_bytes, "image/png")},
        data={"top_k": "5"},
        headers=auth_headers_user_a,
    )
    assert res_by_img.status_code == 200
    data_by_img = res_by_img.json()
    assert data_by_img["total_results"] > 0
    assert data_by_img["results"][0]["modality"] == "image"

    # -------------------------------------------------------------------------
    # Verification 8: Deletion removes index entries
    # -------------------------------------------------------------------------
    # Delete individual attachment
    search_svc.delete_attachment_entries("att_img_car")
    res_after_att_del = await client.post(
        "/api/v1/search",
        json={"query": "red sports car glass skyscraper", "top_k": 5},
        headers=auth_headers_user_a,
    )
    assert res_after_att_del.status_code == 200
    found_car = any(
        r.get("attachment_id") == "att_img_car" for r in res_after_att_del.json()["results"]
    )
    assert not found_car

    # Delete conversation
    search_svc.delete_conversation_entries(conv.id)
    res_after_conv_del = await client.post(
        "/api/v1/search",
        json={"query": "marketing budget", "top_k": 5},
        headers=auth_headers_user_a,
    )
    assert res_after_conv_del.status_code == 200
    assert res_after_conv_del.json()["total_results"] == 0


@pytest.mark.asyncio
async def test_search_intent_in_chat_streams_answer_and_citations(
    client: AsyncClient,
    auth_headers_user_a: dict[str, str],
    db: Session,
) -> None:
    """Verify that a search intent in a chat turn answers using Knowledge Vault with citations."""
    user = db.query(User).filter(User.email == "usera@vault.com").first()
    assert user is not None
    user_id = user.id

    # Create conversation and attachment
    conv = Conversation(user_id=user_id, title="Vault Citations Chat")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    msg = Message(
        conversation_id=conv.id,
        role="user",
        content="Here is the quarterly report audio.",
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    att = Attachment(
        user_id=user_id,
        message_id=msg.id,
        type="audio",
        path="audio/q3_report.mp3",
        mime="audio/mpeg",
        size=1024,
        metadata_={"original_filename": "q3_report.mp3"},
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    # Index into Knowledge Vault
    search_svc = get_search_service()
    search_svc.index_transcript(
        user_id=user_id,
        conversation_id=conv.id,
        attachment_id=att.id,
        transcript_data={
            "text": "The marketing spend was formally approved at fifty thousand dollars for Q3.",
            "language": "en",
            "segments": [
                {
                    "start": 5.0,
                    "end": 20.0,
                    "text": "The marketing spend was formally approved at fifty thousand dollars for Q3.",
                }
            ],
            "insights": {
                "meeting_insights": {
                    "decisions": ["Approved fifty thousand dollars marketing spend"],
                    "action_items": [],
                }
            },
        },
    )

    # Send search message
    events: list[str] = []
    tokens: list[str] = []
    sources_data: list[dict] = []
    import json

    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conv.id}/messages",
        json={"content": "Search my vault for the marketing spend approval"},
        headers=auth_headers_user_a,
    ) as response:
        assert response.status_code == 200
        current_event = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                current_event = line.replace("event: ", "").strip()
                events.append(current_event)
            elif line.startswith("data: "):
                raw_data = line.replace("data: ", "").strip()
                data = json.loads(raw_data)
                if current_event == "token":
                    tokens.append(data.get("text", ""))
                elif current_event == "sources":
                    sources_data = data.get("items", [])

    assert "status" in events
    assert "token" in events
    assert "sources" in events
    assert "done" in events
    assert len(tokens) > 0
    assert isinstance(sources_data, list)


@pytest.mark.asyncio
async def test_reindex_job_completion(
    client: AsyncClient,
    auth_headers_user_a: dict[str, str],
    db: Session,
) -> None:
    """Verify POST /api/v1/search/reindex launches and completes."""
    res = await client.post("/api/v1/search/reindex", headers=auth_headers_user_a)
    assert res.status_code == 202
    data = res.json()
    assert "job_id" in data
    assert data["status"] == "queued"

    job_id = data["job_id"]
    # Poll job status
    for _ in range(20):
        await asyncio.sleep(0.1)
        job_res = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers_user_a)
        if job_res.status_code == 200 and job_res.json()["status"] in (
            "done",
            "failed",
        ):
            assert job_res.json()["status"] == "done"
            break


@pytest.mark.slow
def test_real_siglip_and_embedder_smoke() -> None:
    """Opt-in real model test for SigLIP and multilingual embedder."""
    try:
        import urllib.request

        urllib.request.urlopen("https://huggingface.co", timeout=3.0)
    except Exception:
        pytest.skip("Offline or Hugging Face unreachable; skipping real model test")

    orig_mock = settings.MOCK_MODELS
    try:
        settings.MOCK_MODELS = False
        img_embedder = get_image_embedding_service()
        img_embedder.load()

        test_img = Image.new("RGB", (224, 224), color="blue")
        vectors, timing_ms = img_embedder.embed_images([test_img])
        assert len(vectors) == 1
        assert len(vectors[0]) == 768
        assert timing_ms >= 0

        text_vectors, _ = img_embedder.embed_text_for_images(["blue sky"])
        assert len(text_vectors) == 1
        assert len(text_vectors[0]) == 768
    finally:
        settings.MOCK_MODELS = orig_mock
