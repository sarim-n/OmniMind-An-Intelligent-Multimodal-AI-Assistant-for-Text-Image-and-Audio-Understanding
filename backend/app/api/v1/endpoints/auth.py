"""Authentication endpoints: register, login, and current user profile."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserRead

router = APIRouter()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Create a new user account with unique email and password.",
)
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    """Register a new user account."""
    if len(user_in.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )

    existing_user = db.query(User).filter(User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="User login",
    description="Authenticate user with OAuth2 form data (username=email, password) or JSON body to receive a JWT access token.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "username": {
                                "type": "string",
                                "description": "User email address",
                            },
                            "password": {"type": "string", "format": "password"},
                            "grant_type": {"type": "string"},
                            "scope": {"type": "string"},
                            "client_id": {"type": "string"},
                            "client_secret": {"type": "string"},
                        },
                        "required": ["username", "password"],
                    }
                },
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "format": "email"},
                            "username": {"type": "string"},
                            "password": {"type": "string"},
                        },
                        "required": ["password"],
                    }
                },
            }
        }
    },
)
async def login(
    request: Request,
    db: Session = Depends(get_db),
) -> Token:
    """Authenticate credentials (OAuth2 form data or JSON body) and generate a JWT access token."""
    content_type = request.headers.get("content-type", "").lower()
    email_or_user = ""
    password = ""

    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        email_or_user = str(form.get("username") or form.get("email") or "").strip()
        password = str(form.get("password") or "")
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                email_or_user = str(body.get("email") or body.get("username") or "").strip()
                password = str(body.get("password") or "")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed login request payload",
            )

    if not email_or_user or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both email/username and password are required",
        )

    user = db.query(User).filter(User.email == email_or_user).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current user profile",
    description="Fetch profile data of the currently authenticated user.",
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return authenticated user profile."""
    return current_user
