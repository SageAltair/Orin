"""Account-level portability and explicit deletion, without exporting credentials."""
import json
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from orin_api.auth import PASSWORD_HASHER, REFRESH_COOKIE_NAME, get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import Base, get_session
from orin_api.models import FileAttachment, User
from orin_api.rate_limit import enforce_user_limit

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])
PRIVATE_COLUMNS = {"password_hash", "credential_hash", "credential_ciphertext", "token_hash",
                   "state_hash", "storage_key", "nonce"}
SKIP_TABLES = {"auth_sessions", "refresh_tokens", "request_rate_windows", "anonymous_rate_windows",
               "integration_oauth_states"}


@router.get("/export")
def export_account(user: User = Depends(get_current_user), session: Session = Depends(get_session),
                   settings: Settings = Depends(get_settings)) -> StreamingResponse:
    enforce_user_limit(session, user.id, "privacy.export", limit=2)
    payload = {"exported_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
    exported_ids = {}
    for table in Base.metadata.sorted_tables:
        if table.name in SKIP_TABLES:
            continue
        ownership = [table.c[key] == user.id for key in ("user_id", "owner_id", "requested_by_id") if key in table.c]
        if table.name == "users":
            ownership = [table.c.id == user.id]
        if not ownership:
            for key in table.foreign_keys:
                owned = exported_ids.get(key.column.table.name, [])
                if key.column.name == "id" and owned:
                    ownership.append(key.parent.in_(owned))
        if not ownership:
            continue
        rows = list(session.execute(select(table).where(or_(*ownership))).mappings())
        exported_ids[table.name] = [row["id"] for row in rows if "id" in row]
        payload["tables"][table.name] = [
            {key: value for key, value in dict(row).items() if key not in PRIVATE_COLUMNS} for row in rows
        ]
    archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("account.json", json.dumps(payload, default=str, ensure_ascii=False))
            root = Path(settings.attachment_storage_path).resolve()
            for row in session.scalars(select(FileAttachment).where(FileAttachment.owner_id == user.id)):
                path = (root / row.storage_key).resolve()
                if path.parent == root and path.is_file():
                    bundle.write(path, "attachments/" + str(row.id) + "/" + Path(row.filename).name)
        archive.seek(0)
    except Exception:
        archive.close()
        raise

    def chunks():
        try:
            while chunk := archive.read(65536):
                yield chunk
        finally:
            archive.close()
    return StreamingResponse(chunks(), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="orin-account.zip"', "Cache-Control": "no-store"})


class DeleteAccount(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    confirmation: str


@router.delete("/account", status_code=204)
def delete_account(data: DeleteAccount, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> Response:
    if data.confirmation != "DELETE":
        raise HTTPException(status_code=422, detail="Type DELETE to confirm account deletion")
    try:
        valid = bool(user.password_hash and PASSWORD_HASHER.verify(data.current_password, user.password_hash))
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    root = Path(settings.attachment_storage_path).resolve()
    paths = [(root / key).resolve() for key in session.scalars(
        select(FileAttachment.storage_key).where(FileAttachment.owner_id == user.id))]
    # All user-owned tables use cascading foreign keys. Core deletion bypasses ORM nulling relationships.
    session.execute(delete(User).where(User.id == user.id))
    session.commit()
    for path in paths:
        if path.parent == root:
            path.unlink(missing_ok=True)
    response = Response(status_code=204)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth", httponly=True,
                           secure=settings.auth_refresh_cookie_secure, samesite="strict")
    return response
