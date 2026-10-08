from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orin_api.config import Settings, get_settings
from orin_api.database import get_session
from orin_api.models import AuthSession, RefreshToken, User
from orin_api.schemas import AuthTokenResponse, LoginRequest, RegisterRequest, UserRead
from orin_api.services import ensure_user_preferences

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "orin-api"
JWT_AUDIENCE = "orin-api"
REFRESH_COOKIE_NAME = "orin_refresh"
PASSWORD_HASHER = PasswordHash.recommended()
# A random dummy hash keeps unknown-account login attempts on the Argon2 path.
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


@dataclass(frozen=True)
class AuthenticatedUser:
    user: User
    auth_session: AuthSession
    token_id: uuid.UUID


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _auth_secret(settings: Settings) -> str:
    try:
        return settings.require_auth_secret()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        ) from exc


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _set_refresh_cookie(response: Response, token: str, settings: Settings, expires_at: datetime) -> None:
    expires_at = _as_utc(expires_at)
    max_age = max(0, int((expires_at - _now()).total_seconds()))
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age,
        expires=expires_at,
        httponly=True,
        secure=settings.auth_refresh_cookie_secure,
        samesite="strict",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.auth_refresh_cookie_secure,
        samesite="strict",
        path="/api/v1/auth",
    )


def _issue_access_token(user: User, auth_session: AuthSession, settings: Settings) -> AuthTokenResponse:
    now = _now()
    expires_at = now + timedelta(minutes=settings.access_token_lifetime_minutes)
    token_id = uuid.uuid4()
    encoded = jwt.encode(
        {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "sub": str(user.id),
            "sid": str(auth_session.id),
            "jti": str(token_id),
            "typ": "access",
            "iat": now,
            "exp": expires_at,
        },
        _auth_secret(settings),
        algorithm=JWT_ALGORITHM,
    )
    return AuthTokenResponse(
        access_token=encoded,
        expires_in=settings.access_token_lifetime_minutes * 60,
    )


def _new_session(session: Session, user: User, settings: Settings) -> tuple[AuthSession, str]:
    now = _now()
    expires_at = now + timedelta(days=settings.refresh_token_lifetime_days)
    auth_session = AuthSession(user_id=user.id, expires_at=expires_at, last_used_at=now)
    session.add(auth_session)
    session.flush()
    raw_token = _new_refresh_token()
    session.add(
        RefreshToken(
            session_id=auth_session.id,
            token_hash=_hash_refresh_token(raw_token),
            expires_at=expires_at,
        )
    )
    return auth_session, raw_token


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _invalid_auth_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def register_user(
    data: RegisterRequest,
    session: Session,
) -> UserRead:
    normalized_email = str(data.email).casefold()
    password_hash = PASSWORD_HASHER.hash(data.password)
    user = User(
        email=normalized_email,
        password_hash=password_hash,
        display_name=data.display_name,
    )
    session.add(user)
    try:
        session.flush()
        ensure_user_preferences(session, user)
        session.commit()
        session.refresh(user)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Unable to register with these account details") from exc
    return UserRead.model_validate(user)


def authenticate_user(
    data: LoginRequest,
    response: Response,
    session: Session,
    settings: Settings,
) -> AuthTokenResponse:
    user = session.scalar(select(User).where(User.email == str(data.email).casefold()))
    hash_to_check = user.password_hash if user is not None and user.password_hash is not None else DUMMY_PASSWORD_HASH
    try:
        password_matches, upgraded_hash = PASSWORD_HASHER.verify_and_update(data.password, hash_to_check)
    except UnknownHashError:
        password_matches, upgraded_hash = False, None
    if user is None or user.password_hash is None or not password_matches:
        raise _invalid_credentials()
    if upgraded_hash is not None:
        user.password_hash = upgraded_hash

    auth_session, refresh_token = _new_session(session, user, settings)
    session.commit()
    _set_refresh_cookie(response, refresh_token, settings, auth_session.expires_at)
    return _issue_access_token(user, auth_session, settings)


def get_current_authentication(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _invalid_auth_token()
    try:
        claims = jwt.decode(
            credentials.credentials,
            _auth_secret(settings),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["iss", "aud", "sub", "sid", "jti", "iat", "exp", "typ"]},
        )
        if claims.get("typ") != "access":
            raise InvalidTokenError("Wrong token type")
        user_id = uuid.UUID(claims["sub"])
        session_id = uuid.UUID(claims["sid"])
        token_id = uuid.UUID(claims["jti"])
    except (InvalidTokenError, KeyError, TypeError, ValueError, HTTPException) as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise _invalid_auth_token() from exc

    now = _now()
    auth_session = session.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    user = session.get(User, user_id)
    if auth_session is None or user is None:
        raise _invalid_auth_token()
    return AuthenticatedUser(user=user, auth_session=auth_session, token_id=token_id)


def get_current_user(authenticated: AuthenticatedUser = Depends(get_current_authentication)) -> User:
    return authenticated.user


def rotate_refresh_token(
    raw_token: str | None,
    response: Response,
    session: Session,
    settings: Settings,
) -> AuthTokenResponse:
    if raw_token is None or len(raw_token) > 200:
        raise _invalid_auth_token()
    token = session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == _hash_refresh_token(raw_token))
        .with_for_update()
    )
    if token is None:
        raise _invalid_auth_token()
    auth_session = session.scalar(
        select(AuthSession).where(AuthSession.id == token.session_id).with_for_update()
    )
    now = _now()
    if auth_session is None:
        raise _invalid_auth_token()
    if token.consumed_at is not None:
        # A rotated token was replayed. Revoke the whole token family immediately.
        auth_session.revoked_at = now
        session.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == auth_session.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        session.commit()
        raise _invalid_auth_token()
    if (
        token.revoked_at is not None
        or _as_utc(token.expires_at) <= now
        or auth_session.revoked_at is not None
        or _as_utc(auth_session.expires_at) <= now
    ):
        session.rollback()
        raise _invalid_auth_token()

    user = session.get(User, auth_session.user_id)
    if user is None:
        session.rollback()
        raise _invalid_auth_token()
    replacement_value = _new_refresh_token()
    replacement = RefreshToken(
        session_id=auth_session.id,
        token_hash=_hash_refresh_token(replacement_value),
        expires_at=auth_session.expires_at,
    )
    session.add(replacement)
    session.flush()
    token.consumed_at = now
    token.replaced_by_id = replacement.id
    auth_session.last_used_at = now
    session.commit()

    _set_refresh_cookie(response, replacement_value, settings, auth_session.expires_at)
    return _issue_access_token(user, auth_session, settings)


def revoke_session(
    authenticated: AuthenticatedUser,
    response: Response,
    session: Session,
    settings: Settings,
) -> None:
    now = _now()
    authenticated.auth_session.revoked_at = now
    session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.session_id == authenticated.auth_session.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.commit()
    _clear_refresh_cookie(response, settings)
