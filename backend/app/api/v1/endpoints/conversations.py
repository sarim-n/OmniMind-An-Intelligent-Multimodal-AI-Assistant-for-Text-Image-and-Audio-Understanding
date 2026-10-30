"""Conversation CRUD and message endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

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
from app.services.storage_service import delete_file, save_upload

router = APIRouter()


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
    description="Delete conversation, cascading delete to messages and disk attachments.",
)
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete conversation and remove its associated files from disk."""
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

    # Find attachments linked to messages in this conversation
    msg_ids = [m.id for m in conv.messages]
    if msg_ids:
        attachments = db.query(Attachment).filter(Attachment.message_id.in_(msg_ids)).all()
        for att in attachments:
            delete_file(att.path)

    # Delete conversation (triggers cascade delete in DB)
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
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create message",
    description="Append a new message to a conversation.",
)
def create_message(
    conversation_id: str,
    msg_in: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Message:
    """Create a new message in the conversation and update conversation timestamp."""
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

    msg = Message(
        conversation_id=conversation_id,
        role=msg_in.role,
        content=msg_in.content,
        language=msg_in.language,
        modalities=msg_in.modalities,
    )
    db.add(msg)
    conv.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(msg)
    return msg


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
