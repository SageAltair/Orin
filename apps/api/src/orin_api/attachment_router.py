"""Private, bounded uploads for task sessions."""
from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from pypdf import PdfReader

from orin_api.auth import get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import get_session
from orin_api.models import Conversation, FileAttachment, Task, User
from orin_api.schemas import AttachmentRead

router = APIRouter(prefix="/api/v1/attachments", tags=["attachments"])
TEXT_TYPES = {
    ".txt": "text/plain", ".md": "text/markdown", ".markdown": "text/markdown",
    ".csv": "text/csv", ".json": "application/json", ".yaml": "text/yaml", ".yml": "text/yaml",
    ".py": "text/x-python", ".ts": "text/typescript", ".tsx": "text/typescript",
    ".js": "text/javascript", ".jsx": "text/javascript", ".html": "text/html",
    ".css": "text/css", ".sql": "text/x-sql", ".sh": "text/x-shellscript",
    ".toml": "application/toml", ".xml": "application/xml", ".log": "text/plain",
    ".c": "text/x-c", ".h": "text/x-c", ".cpp": "text/x-c++", ".rs": "text/x-rust",
    ".go": "text/x-go", ".java": "text/x-java", ".kt": "text/x-kotlin", ".swift": "text/x-swift",
}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MAX_EXTRACTED_CHARS = 200_000


def _file_path(settings: Settings, attachment: FileAttachment) -> Path:
    root = Path(settings.attachment_storage_path).resolve()
    path = (root / attachment.storage_key).resolve()
    if path.parent != root:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    return path


def _extract_text(name: str, media_type: str, content: bytes) -> str | None:
    if media_type in IMAGE_TYPES.values():
        if media_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("This image is not a valid PNG file.")
        if media_type == "image/jpeg" and not content.startswith(b"\xff\xd8\xff"):
            raise ValueError("This image is not a valid JPEG file.")
        if media_type == "image/webp" and not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
            raise ValueError("This image is not a valid WebP file.")
        return None
    if media_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("This file is not a valid PDF.")
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
        except Exception as exc:
            raise ValueError("This PDF could not be parsed.") from exc
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs cannot be read. Upload an unlocked copy.")
        if len(reader.pages) > 200:
            raise ValueError("PDFs are limited to 200 pages.")
        extracted = "\n\n".join((page.extract_text() or "") for page in reader.pages)[:MAX_EXTRACTED_CHARS]
        if not extracted.strip():
            raise ValueError("This PDF has no selectable text. Use OCR to create a text-readable copy first.")
        return extracted
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("This text document is not valid UTF-8.") from exc
    if "\x00" in text:
        raise ValueError("Binary content is not supported for this file type.")
    return text[:MAX_EXTRACTED_CHARS]


def _read(row: FileAttachment) -> AttachmentRead:
    return AttachmentRead(id=row.id, conversation_id=row.conversation_id, task_id=row.task_id,
        filename=row.filename, media_type=row.media_type, size_bytes=row.size_bytes, created_at=row.created_at)


@router.post("", response_model=list[AttachmentRead], status_code=status.HTTP_201_CREATED)
async def upload_attachments(files: list[UploadFile] = File(..., max_length=5),
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings)) -> list[AttachmentRead]:
    if not files or len(files) > 5:
        raise HTTPException(status_code=422, detail="Attach between one and five files at a time.")
    root = Path(settings.attachment_storage_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    created: list[FileAttachment] = []
    total_size = 0
    try:
        for upload in files:
            raw_name = (upload.filename or "").replace("\\", "/").split("/")[-1].strip()
            suffix = Path(raw_name).suffix.casefold()
            media_type = IMAGE_TYPES.get(suffix) or ("application/pdf" if suffix == ".pdf" else TEXT_TYPES.get(suffix))
            if not raw_name or len(raw_name) > 255 or any(ord(char) < 32 for char in raw_name) or media_type is None:
                raise HTTPException(status_code=415, detail=f"{raw_name or 'This file'} has an unsupported file type.")
            content = await upload.read(settings.attachment_max_size_bytes + 1)
            total_size += len(content)
            if len(content) > settings.attachment_max_size_bytes:
                raise HTTPException(status_code=413, detail=f"{raw_name} exceeds the configured file size limit.")
            if total_size > 20_971_520:
                raise HTTPException(status_code=413, detail="Attachments in one request may total no more than 20 MB.")
            try:
                extracted = _extract_text(raw_name, media_type, content)
            except (ValueError, OSError) as exc:
                raise HTTPException(status_code=422, detail=f"Could not read {raw_name}: {exc}") from exc
            file_id = uuid.uuid4()
            storage_key = str(uuid.uuid4())
            target = (root / storage_key).resolve()
            if target.parent != root:
                raise HTTPException(status_code=400, detail="Invalid attachment path.")
            target.write_bytes(content)
            row = FileAttachment(id=file_id, owner_id=user.id, filename=raw_name, media_type=media_type,
                size_bytes=len(content), storage_key=storage_key, sha256=hashlib.sha256(content).hexdigest(),
                extracted_text=extracted)
            session.add(row)
            created.append(row)
        session.commit()
        return [_read(row) for row in created]
    except Exception:
        session.rollback()
        for row in created:
            _file_path(settings, row).unlink(missing_ok=True)
        raise


@router.get("", response_model=list[AttachmentRead])
def list_attachments(conversation_id: uuid.UUID | None = None, user: User = Depends(get_current_user),
    session: Session = Depends(get_session)) -> list[AttachmentRead]:
    statement = select(FileAttachment).where(FileAttachment.owner_id == user.id)
    if conversation_id is not None:
        if session.scalar(select(Conversation.id).where(Conversation.id == conversation_id,
            Conversation.user_id == user.id)) is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        statement = statement.where(FileAttachment.conversation_id == conversation_id)
    rows = session.scalars(statement.order_by(FileAttachment.created_at.asc()).limit(100)).all()
    return [_read(row) for row in rows]


@router.get("/{attachment_id}/content")
def download_attachment(attachment_id: uuid.UUID, user: User = Depends(get_current_user),
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> FileResponse:
    row = session.scalar(select(FileAttachment).where(FileAttachment.id == attachment_id,
        FileAttachment.owner_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    path = _file_path(settings, row)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment content is no longer available.")
    return FileResponse(path, media_type=row.media_type, filename=row.filename,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/{attachment_id}", status_code=status.HTTP_200_OK)
def delete_attachment(attachment_id: uuid.UUID, user: User = Depends(get_current_user),
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> None:
    row = session.scalar(select(FileAttachment).where(FileAttachment.id == attachment_id,
        FileAttachment.owner_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    if row.conversation_id is not None:
        raise HTTPException(status_code=409, detail="Files already used in a work session cannot be removed from its history.")
    path = _file_path(settings, row)
    session.delete(row)
    session.commit()
    path.unlink(missing_ok=True)
