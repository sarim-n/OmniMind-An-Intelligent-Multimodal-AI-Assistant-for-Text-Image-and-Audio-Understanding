"""Conversation CRUD and LLM chat streaming endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.attachment import AttachmentRead
from app.schemas.conversation import (
    ConversationCreate,
    ConversationList,
    ConversationRead,
    ConversationUpdate,
)
from app.schemas.message import MessageList, MessageRead
from app.services.llm_service import get_llm_service
from app.services.memory_service import get_memory_service
from app.services.storage_service import delete_file, save_upload

logger = get_logger(__name__)
router = APIRouter()


class ConversationTitleSchema(BaseModel):
    title: str


def _auto_title_conversation(conversation: Conversation, first_message: str, db: Session) -> None:
    """Generate and set a concise title for a new conversation based on initial prompt."""
    if conversation.title not in ("New Conversation", "", None):
        return

    prompt = (
        "Generate a brief, engaging conversation title (strictly 3 to 5 words, without quotes) "
        f"for this initial user inquiry:\n<<<USER_CONTENT>>>{first_message[:200]}<<<USER_CONTENT>>>"
    )
    try:
        llm = get_llm_service()
        result, _ = llm.generate_json(prompt, ConversationTitleSchema)
        clean_title = result.title.strip().strip('"').strip("'")
        if clean_title:
            conversation.title = clean_title[:80]
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
    except Exception as e:
        logger.warning("Failed to auto-generate conversation title", error=str(e))
        words = first_message.strip().split()
        if words:
            conversation.title = " ".join(words[:5])[:60]
            db.add(conversation)
            db.commit()


@router.post(
    "",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create conversation",
    description="Create a new conversation session scoped to the authenticated user.",
)
def create_conversation(
    conv_in: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    """Create a new conversation for the current user."""
    conv = Conversation(
        user_id=current_user.id,
        title=conv_in.title,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get(
    "",
    response_model=ConversationList,
    summary="List conversations",
    description="Retrieve paginated list of conversations belonging to the current user.",
)
def list_conversations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationList:
    """Return paginated conversations ordered by last updated."""
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(Conversation.updated_at.desc()).offset(offset).limit(page_size).all()
    return ConversationList(
        items=[ConversationRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationRead,
    summary="Get conversation details",
    description="Fetch a specific conversation by ID (returns 404 if not found or unauthorized).",
)
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    """Fetch conversation by ID, strictly scoped to current user."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conv


@router.patch(
    "/{conversation_id}",
    response_model=ConversationRead,
    summary="Update conversation",
    description="Rename or update summary for a conversation.",
)
def update_conversation(
    conversation_id: str,
    conv_in: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    """Update title or summary for a conversation."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conv_in.title is not None:
        conv.title = conv_in.title
    if conv_in.summary is not None:
        conv.summary = conv_in.summary

    conv.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(conv)
    return conv


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete conversation",
    description="Delete conversation, cascading delete to messages, attachments, and vector memories.",
)
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete conversation, disk attachments, and ChromaDB vector collection."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # 1. Unlink and remove disk attachments
    msg_ids = [m.id for m in conv.messages]
    if msg_ids:
        attachments = db.query(Attachment).filter(Attachment.message_id.in_(msg_ids)).all()
        for att in attachments:
            delete_file(att.path)

    # 2. Purge ChromaDB long-term memory
    get_memory_service().delete_conversation_memory(conversation_id)

    # 3. Delete conversation (triggers DB cascade delete of messages)
    db.delete(conv)
    db.commit()


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageList,
    summary="List messages",
    description="Get paginated list of messages for a given conversation.",
)
def list_messages(
    conversation_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageList:
    """List messages for a conversation scoped to the current user."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    query = db.query(Message).filter(Message.conversation_id == conversation_id)
    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(Message.created_at.asc()).offset(offset).limit(page_size).all()

    return MessageList(
        items=[MessageRead.model_validate(msg) for msg in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{conversation_id}/messages",
    summary="Send multimodal message and receive assistant reply",
    description="Send user message (text, images[], audio[]) and receive SSE stream (default) or JSON message object if ?stream=false.",
    responses={
        200: {"description": "SSE stream or completed assistant message"},
        201: {"model": MessageRead, "description": "Message created"},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Text prompt or question"},
                            "language": {
                                "type": "string",
                                "description": "Optional ISO language code",
                            },
                            "images": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "Image attachments",
                            },
                            "audio": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "Audio attachments",
                            },
                        },
                    }
                },
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "language": {"type": "string"},
                            "role": {"type": "string", "default": "user"},
                        },
                        "required": ["content"],
                    }
                },
            }
        }
    },
)
async def create_message(
    conversation_id: str,
    request: Request,
    stream: bool = Query(True, description="Whether to stream assistant response via SSE"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Process user message with multimodal orchestrator and stream SSE events or return JSON."""
    from starlette.datastructures import UploadFile as StarletteUploadFile

    from app.services.orchestrator import orchestrate_message

    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    content_type = request.headers.get("content-type", "").lower()
    user_text = ""
    language = None
    images: list[UploadFile] = []
    audio_list: list[UploadFile] = []

    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        raw_content = form.get("content")
        if isinstance(raw_content, str):
            user_text = raw_content.strip()
        raw_lang = form.get("language")
        if isinstance(raw_lang, str) and raw_lang.strip():
            language = raw_lang.strip()

        for key in ("images", "images[]", "image"):
            for item in form.getlist(key):
                if isinstance(item, (UploadFile, StarletteUploadFile)):
                    images.append(item)  # type: ignore[arg-type]

        for key in ("audio", "audio[]"):
            for item in form.getlist(key):
                if isinstance(item, (UploadFile, StarletteUploadFile)):
                    audio_list.append(item)  # type: ignore[arg-type]

    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                user_text = str(body.get("content") or "").strip()
                raw_lang = body.get("language")
                language = str(raw_lang).strip() if raw_lang else None
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed request payload",
            )

    if not user_text and not images and not audio_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message must contain either text content or at least one attachment",
        )

    # Validate file limits before starting response stream
    total_files = len(images) + len(audio_list)
    if total_files > settings.MAX_FILES_PER_MESSAGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number of uploaded files ({total_files}) exceeds limit of {settings.MAX_FILES_PER_MESSAGE}",
        )

    # 1. Streaming response (default)
    if stream:
        return StreamingResponse(
            orchestrate_message(
                conversation_id=conversation_id,
                user=current_user,
                content=user_text,
                language=language,
                images=images,
                audio=audio_list,
                db=db,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 2. Synchronous mode (?stream=false)
    last_message_id = ""
    async for event_line in orchestrate_message(
        conversation_id=conversation_id,
        user=current_user,
        content=user_text,
        language=language,
        images=images,
        audio=audio_list,
        db=db,
    ):
        if "event: done" in event_line:
            try:
                for line in event_line.splitlines():
                    if line.startswith("data: "):
                        parsed = json.loads(line[6:].strip())
                        last_message_id = parsed.get("message_id", "")
            except Exception:
                pass

    assistant_msg = (
        db.query(Message).filter(Message.id == last_message_id).first() if last_message_id else None
    )
    if not assistant_msg:
        assistant_msg = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id, Message.role == "assistant")
            .order_by(Message.created_at.desc())
            .first()
        )

    if not assistant_msg:
        raise HTTPException(status_code=500, detail="Failed to retrieve assistant reply")

    return JSONResponse(
        content=MessageRead.model_validate(assistant_msg).model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
    )


@router.post(
    "/{conversation_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload media attachment",
    description="Upload and sniff image or audio attachment linked to a conversation.",
)
async def upload_attachment(
    conversation_id: str,
    file: UploadFile,
    kind: str = Query(..., description="'image' or 'audio'"),
    message_id: str | None = Query(None, description="Optional associated message ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Attachment:
    """Save an uploaded media file, verifying ownership of the conversation."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if message_id:
        msg = (
            db.query(Message)
            .filter(Message.id == message_id, Message.conversation_id == conversation_id)
            .first()
        )
        if not msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found in this conversation",
            )

    attachment = await save_upload(
        file=file,
        kind="image" if kind == "image" else "audio",
        user_id=current_user.id,
        message_id=message_id,
        db=db,
    )
    return attachment
