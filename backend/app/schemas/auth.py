"""Pydantic schemas for authentication and user accounts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Registration request payload."""

    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")


class UserLogin(BaseModel):
    """Login request payload."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """Public user response payload."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    """Access token response schema."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str | None = None
    exp: int | None = None
