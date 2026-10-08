from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status, HTTPException
from sqlalchemy.orm import Session

from orin_api.auth import (
    AuthenticatedUser,
    REFRESH_COOKIE_NAME,
    _auth_secret,
    authenticate_user,
    get_current_authentication,
    get_current_user,
    register_user,
    revoke_session,
    rotate_refresh_token,
    PASSWORD_HASHER,
)
from orin_api.config import Settings, get_settings
from orin_api.database import get_session
from orin_api.models import User, AuthSession, RefreshToken
from orin_api.schemas import AuthTokenResponse, LoginRequest, RegisterRequest, UserRead, ProfileUpdate, PasswordChange, EmailChange
from sqlalchemy import select
from datetime import UTC, datetime

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def _disable_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserRead:
    _auth_secret(settings)
    return register_user(data, session)


@router.post("/login", response_model=AuthTokenResponse)
def login(
    data: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse:
    _auth_secret(settings)
    token = authenticate_user(data, response, session, settings)
    _disable_caching(response)
    return token


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh(
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse:
    _auth_secret(settings)
    token = rotate_refresh_token(refresh_token, response, session, settings)
    _disable_caching(response)
    return token


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    authenticated: AuthenticatedUser = Depends(get_current_authentication),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    revoke_session(authenticated, response, session, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserRead)
def update_profile(data: ProfileUpdate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> User:
    user.display_name = data.display_name
    session.commit()
    return user


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(data: PasswordChange, response: Response, user: User = Depends(get_current_user), session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> Response:
    try:
        valid = bool(user.password_hash and PASSWORD_HASHER.verify(data.current_password, user.password_hash))
    except Exception:
        valid = False
    if not valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = PASSWORD_HASHER.hash(data.new_password)
    now = datetime.now(UTC)
    sessions = session.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))).all()
    for auth_session in sessions:
        auth_session.revoked_at = now
    session.commit()
    response.delete_cookie(key=REFRESH_COOKIE_NAME, httponly=True, secure=settings.auth_refresh_cookie_secure, samesite="strict", path="/api/v1/auth")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/sessions")
def list_sessions(authenticated: AuthenticatedUser = Depends(get_current_authentication), session: Session = Depends(get_session)) -> list[dict[str, object]]:
    now = datetime.now(UTC)
    rows = session.scalars(select(AuthSession).where(AuthSession.user_id == authenticated.user.id).order_by(AuthSession.created_at.desc())).all()
    return [{"id": row.id, "created_at": row.created_at, "last_used_at": row.last_used_at,
             "expires_at": row.expires_at, "revoked_at": row.revoked_at,
             "active": row.revoked_at is None and (row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at) > now,
             "current": row.id == authenticated.auth_session.id} for row in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_session(session_id: uuid.UUID, response: Response, authenticated: AuthenticatedUser = Depends(get_current_authentication), session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> Response:
    row = session.scalar(select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == authenticated.user.id).with_for_update())
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        tokens = session.scalars(select(RefreshToken).where(RefreshToken.session_id == row.id, RefreshToken.revoked_at.is_(None))).all()
        for token in tokens:
            token.revoked_at = datetime.now(UTC)
        session.commit()
    if row.id == authenticated.auth_session.id:
        response.delete_cookie(key=REFRESH_COOKIE_NAME, httponly=True, secure=settings.auth_refresh_cookie_secure, samesite="strict", path="/api/v1/auth")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/email", response_model=UserRead)
def change_email(data: EmailChange, response: Response, user: User = Depends(get_current_user), session: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> User:
    try:
        valid = bool(user.password_hash and PASSWORD_HASHER.verify(data.current_password, user.password_hash))
    except Exception:
        valid = False
    if not valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    email = str(data.new_email).casefold()
    if session.scalar(select(User.id).where(User.email == email, User.id != user.id)):
        raise HTTPException(status_code=409, detail="Email address is already in use")
    user.email = email
    now = datetime.now(UTC)
    sessions = session.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))).all()
    for auth_session in sessions:
        auth_session.revoked_at = now
    session.commit()
    response.delete_cookie(key=REFRESH_COOKIE_NAME, httponly=True, secure=settings.auth_refresh_cookie_secure, samesite="strict", path="/api/v1/auth")
    return user
