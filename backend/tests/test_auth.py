"""Tests for authentication and user endpoints."""

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    """Test successful user registration."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@example.com", "password": "securePassword123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "hashed_password" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: User) -> None:
    """Test that duplicate email registration returns 400 Bad Request."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": test_user.email, "password": "newPassword123"},
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient) -> None:
    """Test that passwords shorter than 8 characters are rejected."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "shortpwd@example.com", "password": "short"},
    )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User) -> None:
    """Test successful user login returning valid JWT."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "Password123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: User) -> None:
    """Test login with incorrect password returns 401 Unauthorized."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "WrongPassword123"},
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient) -> None:
    """Test login with unregistered email returns 401 Unauthorized."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "SomePassword123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Test GET /auth/me returns current user profile when authenticated."""
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == test_user.email


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient) -> None:
    """Test GET /auth/me returns 401 when no token is provided."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token(client: AsyncClient) -> None:
    """Test GET /auth/me returns 401 when a malformed token is provided."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.signature"},
    )
    assert response.status_code == 401
