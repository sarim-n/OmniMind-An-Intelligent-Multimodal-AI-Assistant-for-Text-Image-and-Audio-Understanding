"""Tests for storage service and media upload validation."""

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_upload_valid_image(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test uploading a valid PNG image."""
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Image Test Conv"},
        headers=auth_headers,
    )
    conv_id = conv_res.json()["id"]

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/attachments?kind=image",
        files={"file": ("photo.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["mime"] == "image/png"
    assert data["type"] == "image"
    assert "uploads/images/" in data["path"]


@pytest.mark.asyncio
async def test_upload_valid_audio(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test uploading a valid WAV audio file."""
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Audio Test Conv"},
        headers=auth_headers,
    )
    conv_id = conv_res.json()["id"]

    # Minimal valid 44-byte standard PCM 1-second WAV
    # Sample rate 8000, 1 channel, 8-bit PCM (8000 bytes data)
    num_samples = 8000
    wav_header = bytearray(
        b"RIFF\x24\x1f\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"\x40\x1f\x00\x00\x40\x1f\x00\x00\x01\x00\x08\x00data\x00\x1f\x00\x00"
    )
    wav_bytes = bytes(wav_header) + (b"\x80" * num_samples)

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/attachments?kind=audio",
        files={"file": ("recording.wav", wav_bytes, "audio/wav")},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "audio"
    assert "uploads/audio/" in data["path"]
    # If duration detected via wave or ffprobe
    if data["duration_sec"] is not None:
        assert abs(data["duration_sec"] - 1.0) < 0.1


@pytest.mark.asyncio
async def test_upload_file_too_large(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test that files exceeding MAX_UPLOAD_SIZE_BYTES are rejected with 413."""
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Size Test Conv"},
        headers=auth_headers,
    )
    conv_id = conv_res.json()["id"]

    orig_limit = settings.MAX_UPLOAD_SIZE_BYTES
    try:
        settings.MAX_UPLOAD_SIZE_BYTES = 100  # Set limit to 100 bytes for test
        oversized_content = b"\x89PNG\r\n\x1a\n" + b"X" * 200

        response = await client.post(
            f"/api/v1/conversations/{conv_id}/attachments?kind=image",
            files={"file": ("large.png", oversized_content, "image/png")},
            headers=auth_headers,
        )
        assert response.status_code == 413
    finally:
        settings.MAX_UPLOAD_SIZE_BYTES = orig_limit


@pytest.mark.asyncio
async def test_upload_wrong_extension(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test that unauthorized extensions are rejected with 400 Bad Request."""
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Extension Test Conv"},
        headers=auth_headers,
    )
    conv_id = conv_res.json()["id"]

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/attachments?kind=image",
        files={"file": ("script.exe", b"binary content", "application/octet-stream")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_spoofed_extension(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Test that a text file renamed with .png is caught by magic-byte sniffing and rejected."""
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Spoofing Test Conv"},
        headers=auth_headers,
    )
    conv_id = conv_res.json()["id"]

    fake_png_content = b"Plain text payload pretending to be a png file"

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/attachments?kind=image",
        files={"file": ("fake_image.png", fake_png_content, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "mime verification failed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_path_traversal_filename(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Test that filenames attempting path traversal are rejected."""
    conv_res = await client.post(
        "/api/v1/conversations",
        json={"title": "Traversal Test Conv"},
        headers=auth_headers,
    )
    conv_id = conv_res.json()["id"]

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/attachments?kind=image",
        files={"file": ("../../etc/passwd.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "traversal" in response.json()["detail"].lower()
