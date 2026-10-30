"""API integration tests for image analysis, VQA, and annotated image serving."""

from __future__ import annotations

import asyncio
import io
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.orm import Session


def make_test_image_bytes(
    width: int = 250,
    height: int = 200,
    color: tuple[int, int, int] = (60, 140, 220),
) -> bytes:
    """Generate in-memory JPEG bytes for API upload tests."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_image_analyze_upload_and_poll_job(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    img_bytes = make_test_image_bytes(width=280, height=210)

    # 1. Post image to analyze
    upload_res = await client.post(
        "/api/v1/images/analyze",
        files={"file": ("office_desk.jpg", img_bytes, "image/jpeg")},
        data={"enhance": "true"},
        headers=auth_headers,
    )
    assert upload_res.status_code == 202
    job_data = upload_res.json()
    job_id = job_data["id"]
    assert job_data["status"] in ("queued", "running", "done")

    # 2. Poll job until completion
    status_data: dict[str, Any] = {}
    for _ in range(50):
        await asyncio.sleep(0.1)
        poll_res = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        assert poll_res.status_code == 200
        status_data = poll_res.json()
        if status_data["status"] in ("done", "failed"):
            break

    assert status_data["status"] == "done"
    result = status_data["result"]
    assert result is not None
    assert "caption" in result
    assert "objects" in result
    assert "annotated_path" in result
    attachment_id = result["attachment_id"]

    # 3. Retrieve analysis from image endpoint
    analysis_res = await client.get(
        f"/api/v1/images/{attachment_id}/analysis",
        headers=auth_headers,
    )
    assert analysis_res.status_code == 200
    analysis_data = analysis_res.json()
    assert analysis_data["attachment_id"] == attachment_id
    assert len(analysis_data["caption"]) > 0
    assert len(analysis_data["objects"]) >= 2
    assert "person" in analysis_data["counts"]
    assert len(analysis_data["dominant_colors"]) > 0

    # 4. Fetch annotated image artifact
    annotated_res = await client.get(
        f"/api/v1/images/{attachment_id}/annotated",
        headers=auth_headers,
    )
    assert annotated_res.status_code == 200
    assert "image/jpeg" in annotated_res.headers.get("content-type", "")
    assert len(annotated_res.content) > 0


@pytest.mark.asyncio
async def test_image_vqa_ask_endpoint(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: Session,
) -> None:
    img_bytes = make_test_image_bytes(width=200, height=200)

    # Upload and analyze
    upload_res = await client.post(
        "/api/v1/images/analyze",
        files={"file": ("vqa_sample.jpg", img_bytes, "image/jpeg")},
        headers=auth_headers,
    )
    assert upload_res.status_code == 202
    job_id = upload_res.json()["id"]

    for _ in range(50):
        await asyncio.sleep(0.1)
        poll_res = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        if poll_res.json()["status"] in ("done", "failed"):
            break

    attachment_id = poll_res.json()["result"]["attachment_id"]

    # Ask question without history
    ask_res = await client.post(
        f"/api/v1/images/{attachment_id}/ask",
        json={"question": "What colors are dominant in this picture?"},
        headers=auth_headers,
    )
    assert ask_res.status_code == 200
    ask_data = ask_res.json()
    assert len(ask_data["answer"]) > 0
    assert ask_data["timing_ms"] >= 0.0

    # Ask question with linked conversation
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "VQA Chat"},
        headers=auth_headers,
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    ask_with_conv = await client.post(
        f"/api/v1/images/{attachment_id}/ask",
        json={
            "question": "Can you describe the central object?",
            "conversation_id": conv_id,
        },
        headers=auth_headers,
    )
    assert ask_with_conv.status_code == 200
    assert len(ask_with_conv.json()["answer"]) > 0


@pytest.mark.asyncio
async def test_image_endpoints_cross_user_isolation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_b: dict[str, str],
) -> None:
    img_bytes = make_test_image_bytes(width=200, height=200)

    # User A uploads and starts analysis
    upload_res = await client.post(
        "/api/v1/images/analyze",
        files={"file": ("private_photo.jpg", img_bytes, "image/jpeg")},
        headers=auth_headers,
    )
    assert upload_res.status_code == 202
    job_id = upload_res.json()["id"]

    for _ in range(50):
        await asyncio.sleep(0.1)
        poll_res = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
        if poll_res.json()["status"] in ("done", "failed"):
            break

    attachment_id = poll_res.json()["result"]["attachment_id"]

    # User B attempts to access User A's analysis -> 404
    other_analysis = await client.get(
        f"/api/v1/images/{attachment_id}/analysis",
        headers=auth_headers_b,
    )
    assert other_analysis.status_code == 404

    # User B attempts VQA on User A's image -> 404
    other_ask = await client.post(
        f"/api/v1/images/{attachment_id}/ask",
        json={"question": "What is in this private image?"},
        headers=auth_headers_b,
    )
    assert other_ask.status_code == 404

    # User B attempts to download User A's annotated image -> 404
    other_annotated = await client.get(
        f"/api/v1/images/{attachment_id}/annotated",
        headers=auth_headers_b,
    )
    assert other_annotated.status_code == 404
