"""File storage service: validates uploads, sniffs mime types, detects audio duration, and enforces path security."""

import os
import re
import shutil
import subprocess
import uuid
import wave
from pathlib import Path
from typing import Literal

import anyio
import filetype  # type: ignore[import-untyped]
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.attachment import Attachment

logger = get_logger("app.services.storage_service")

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"}

ALLOWED_IMAGE_MIMES = {
    "image/png",
    "image/jpeg",
    "image/webp",
}
ALLOWED_AUDIO_MIMES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/webm",
    "video/webm",  # WebM audio frequently tagged as video/webm
}


def get_storage_root() -> Path:
    """Return the resolved storage root directory based on application configuration."""
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    if settings.STORAGE_DIR.is_absolute():
        storage_root = settings.STORAGE_DIR.resolve()
    else:
        storage_root = (root_dir / settings.STORAGE_DIR).resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root


def resolve_safe_path(relative_or_absolute_path: str | Path) -> Path:
    """Resolve a path and ensure it is strictly confined within the storage directory."""
    storage_root = get_storage_root()
    path_obj = Path(relative_or_absolute_path)

    if path_obj.is_absolute():
        resolved = path_obj.resolve()
    else:
        resolved = (storage_root / path_obj).resolve()

    try:
        resolved.relative_to(storage_root)
    except ValueError as exc:
        logger.warning(
            "Path traversal attempt detected",
            attempted_path=str(relative_or_absolute_path),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal attempt blocked",
        ) from exc

    return resolved


def sanitize_filename(filename: str | None) -> str:
    """Sanitize a filename by removing path separators, control characters, and dangerous sequences."""
    if not filename:
        return f"upload_{uuid.uuid4().hex[:8]}"

    # Strip directory components
    base = os.path.basename(filename)
    # Remove null bytes and non-printable characters
    cleaned = re.sub(r"[\x00-\x1f\x7f/\\]", "", base)
    # Strip leading/trailing dots or spaces that could trigger traversal or hiding
    cleaned = cleaned.strip(". ")
    return cleaned or f"upload_{uuid.uuid4().hex[:8]}"


def validate_media_upload(
    filename: str,
    content: bytes,
    allowed_type: Literal["image", "audio"],
) -> None:
    """Validate uploaded media file size, extension, and sniffed MIME type."""
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size {len(content)} exceeds limit of {settings.MAX_UPLOAD_SIZE_BYTES} bytes",
        )

    safe_filename = sanitize_filename(filename)
    ext = Path(safe_filename).suffix.lower()

    allowed_extensions = (
        ALLOWED_IMAGE_EXTENSIONS if allowed_type == "image" else ALLOWED_AUDIO_EXTENSIONS
    )
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension '{ext}' not allowed for {allowed_type} uploads. Allowed: {sorted(allowed_extensions)}",
        )

    sniffed = filetype.guess(content)
    sniffed_mime = sniffed.mime if sniffed else None

    if not sniffed_mime and ext == ".webm" and content.startswith(b"\x1a\x45\xdf\xa3"):
        sniffed_mime = "audio/webm"

    allowed_mimes = ALLOWED_IMAGE_MIMES if allowed_type == "image" else ALLOWED_AUDIO_MIMES
    if not sniffed_mime or sniffed_mime not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME verification failed. Detected '{sniffed_mime}', expected a valid {allowed_type} format.",
        )


def detect_audio_duration(file_path: Path) -> float | None:
    """Detect the duration of an audio file using ffprobe if available, with a wave fallback."""
    ffprobe_cmd = shutil.which("ffprobe")
    if ffprobe_cmd:
        try:
            cmd = [
                ffprobe_cmd,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.SubprocessError, ValueError, OSError) as e:
            logger.debug("ffprobe duration detection failed", error=str(e), file=str(file_path))

    # Fallback for standard WAV files using Python's standard library
    if file_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(file_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return float(frames) / float(rate)
        except (wave.Error, OSError, EOFError) as e:
            logger.debug("wave module fallback failed", error=str(e), file=str(file_path))

    # Graceful degradation when duration cannot be probed
    return None


def _write_bytes_to_disk(target_path: Path, content: bytes) -> None:
    """Synchronous file write helper to run inside threadpool."""
    with open(target_path, "wb") as f:
        f.write(content)


async def save_upload(
    file: UploadFile,
    kind: Literal["image", "audio"],
    user_id: str,
    message_id: str | None = None,
    db: Session | None = None,
) -> Attachment:
    """Validate, sniff, and safely persist an uploaded media file."""
    if kind not in ("image", "audio"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid upload kind: {kind}. Expected 'image' or 'audio'.",
        )

    # 1. Validate filename and extension
    raw_filename = file.filename or "file"
    if (
        raw_filename.startswith(("../", "..\\"))
        or "/../" in raw_filename
        or "\\..\\" in raw_filename
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal in filename blocked",
        )

    safe_filename = sanitize_filename(raw_filename)
    ext = Path(safe_filename).suffix.lower()

    allowed_extensions = ALLOWED_IMAGE_EXTENSIONS if kind == "image" else ALLOWED_AUDIO_EXTENSIONS
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension '{ext}' not allowed for {kind} uploads. Allowed: {sorted(allowed_extensions)}",
        )

    # 2. Read and enforce size limit
    content = await file.read()
    file_size = len(content)
    if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size {file_size} exceeds limit of {settings.MAX_UPLOAD_SIZE_BYTES} bytes",
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # 3. Sniff real MIME type using magic bytes
    sniffed = filetype.guess(content)
    sniffed_mime = sniffed.mime if sniffed else None

    # Fallback check for webm/audio or specific container formats
    if not sniffed_mime and ext == ".webm" and content.startswith(b"\x1a\x45\xdf\xa3"):
        sniffed_mime = "audio/webm"

    allowed_mimes = ALLOWED_IMAGE_MIMES if kind == "image" else ALLOWED_AUDIO_MIMES
    if not sniffed_mime or sniffed_mime not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME verification failed. Detected '{sniffed_mime}', but expected a valid {kind} format.",
        )

    # 4. Generate destination path: storage/uploads/{images|audio}/{user_id}/{uuid}.{ext}
    subfolder = "images" if kind == "image" else "audio"
    unique_filename = f"{uuid.uuid4()}{ext}"
    rel_destination = Path("uploads") / subfolder / user_id / unique_filename

    target_path = resolve_safe_path(rel_destination)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 5. Write content to disk off the main event loop
    await anyio.to_thread.run_sync(_write_bytes_to_disk, target_path, content)

    # 6. Read duration for audio
    duration_sec: float | None = None
    if kind == "audio":
        duration_sec = await anyio.to_thread.run_sync(detect_audio_duration, target_path)

    # Store normalized path relative to storage root
    storage_root = get_storage_root()
    stored_rel_path = target_path.relative_to(storage_root).as_posix()

    attachment = Attachment(
        user_id=user_id,
        message_id=message_id,
        type=kind,
        path=stored_rel_path,
        mime=sniffed_mime,
        size=file_size,
        duration_sec=duration_sec,
        metadata_={
            "original_filename": safe_filename,
            "extension": ext,
        },
    )

    if db is not None:
        db.add(attachment)
        db.commit()
        db.refresh(attachment)

    return attachment


def delete_file(relative_or_absolute_path: str | Path) -> bool:
    """Safely delete a stored file from disk."""
    try:
        safe_path = resolve_safe_path(relative_or_absolute_path)
        if safe_path.is_file():
            safe_path.unlink()
            return True
    except (OSError, ValueError) as e:
        logger.error("Failed to delete file", error=str(e), path=str(relative_or_absolute_path))
    return False
