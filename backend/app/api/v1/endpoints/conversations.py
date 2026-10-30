"""Conversation CRUD and LLM chat streaming endpoints."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
from app.schemas.message import MessageCreate, MessageList, MessageRead
from app.services.llm_service import get_llm_service
from app.services.memory_service import get_memory_service
from app.services.metrics_service import MetricTracker, persist_metric
from app.services.storage_service import delete_file, save_upload
from app.utils.lang import detect_language

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
    summary="Send message and receive assistant reply",
    description="Send user message and stream reply via SSE (default) or return JSON message object if ?stream=false.",
    responses={
        200: {"description": "SSE stream or completed assistant message"},
        201: {"model": MessageRead, "description": "Message created"},
    },
)
async def create_message(
    conversation_id: str,
    msg_in: MessageCreate,
    request: Request,
    stream: bool = Query(True, description="Whether to stream assistant response via SSE"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Process user message with 3-tier memory context and stream/generate LLM response."""
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

    # 1. Detect language if not provided
    detected_lang = msg_in.language or detect_language(msg_in.content)

    # 2. Persist the incoming message
    user_msg = Message(
        conversation_id=conversation_id,
        role=msg_in.role or "user",
        content=msg_in.content,
        language=detected_lang,
        modalities=msg_in.modalities or ["text"],
    )
    db.add(user_msg)
    conv.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user_msg)

    # If incoming message is not from user (e.g. system turn), return immediately
    if user_msg.role != "user":
        return JSONResponse(
            content=MessageRead.model_validate(user_msg).model_dump(mode="json"),
            status_code=status.HTTP_201_CREATED,
        )

    # 3. Index user message into ChromaDB memory
    memory_service = get_memory_service()
    memory_service.add_message_memory(conversation_id, user_msg.id, user_msg.content, "user")

    # 4. Auto-title conversation on first turn if needed
    _auto_title_conversation(conv, user_msg.content, db)

    # 5. Build 3-tier prompt context
    context_messages = memory_service.build_context(conversation_id, user_msg.content, db)

    # 6. Synchronous mode (?stream=false)
    if not stream:
        llm = get_llm_service()
        assistant_content, _ = llm.generate(context_messages)
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            language=detect_language(assistant_content),
            modalities=["text"],
        )
        db.add(assistant_msg)
        conv.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(assistant_msg)

        # Index assistant reply in memory
        memory_service.add_message_memory(
            conversation_id, assistant_msg.id, assistant_msg.content, "assistant"
        )

        return JSONResponse(
            content=MessageRead.model_validate(assistant_msg).model_dump(mode="json"),
            status_code=status.HTTP_201_CREATED,
        )

    # 7. SSE Streaming mode (default)
    async def sse_event_stream() -> AsyncGenerator[str, None]:
        accumulated_text = ""
        assistant_msg_id = str(uuid.uuid4())
        tracker = MetricTracker(component="llm", operation="stream_generate")

        try:
            # Emit status event
            yield 'event: status\ndata: {"status": "thinking"}\n\n'

            llm = get_llm_service()
            async for token in llm.stream_generate(context_messages):
                # Disconnect check
                if await request.is_disconnected():
                    logger.info(
                        "Client disconnected during stream", conversation_id=conversation_id
                    )
                    break

                tracker.record_token()
                accumulated_text += token
                token_data = json.dumps({"token": token})
                yield f"event: token\ndata: {token_data}\n\n"

            # Generation complete: save assistant message to DB
            if accumulated_text:
                assistant_msg = Message(
                    id=assistant_msg_id,
                    conversation_id=conversation_id,
                    role="assistant",
                    content=accumulated_text,
                    language=detect_language(accumulated_text),
                    modalities=["text"],
                )
                db.add(assistant_msg)
                conv.updated_at = datetime.now(UTC)
                db.commit()

                # Update vector memory
                memory_service.add_message_memory(
                    conversation_id, assistant_msg_id, accumulated_text, "assistant"
                )

            done_data = json.dumps(
                {
                    "message_id": assistant_msg_id,
                    "content": accumulated_text,
                    "role": "assistant",
                }
            )
            yield f"event: done\ndata: {done_data}\n\n"

        except Exception as e:
            logger.error(
                "Error during SSE streaming", conversation_id=conversation_id, error=str(e)
            )
            err_data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {err_data}\n\n"

            # Save partial output if available
            if accumulated_text:
                try:
                    assistant_msg = Message(
                        id=assistant_msg_id,
                        conversation_id=conversation_id,
                        role="assistant",
                        content=accumulated_text,
                        language=detect_language(accumulated_text),
                        modalities=["text"],
                    )
                    db.add(assistant_msg)
                    db.commit()
                except Exception:
                    pass
        finally:
            tracker.finalize()
            persist_metric(
                component=tracker.component,
                operation=tracker.operation,
                latency_ms=tracker.latency_ms,
                extra=tracker.extra,
                db=db,
            )

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
