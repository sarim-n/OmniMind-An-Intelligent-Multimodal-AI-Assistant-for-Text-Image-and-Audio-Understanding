"""Test health check endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_200(client: AsyncClient) -> None:
    """Test that root GET /health returns 200 and expected payload structure."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "profile" in data
    assert "mock_models" in data
    assert "version" in data
    assert "timestamp" in data
    assert "models" in data
    assert isinstance(data["models"], dict)
    assert "llm" in data["models"]
    assert "vlm" in data["models"]
    assert "asr" in data["models"]
    assert "detector" in data["models"]
    assert "text_embedding" in data["models"]
    assert "image_embedding" in data["models"]


@pytest.mark.asyncio
async def test_api_v1_health_check_returns_200(client: AsyncClient) -> None:
    """Test that /api/v1/health returns 200 and matches root health check."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
