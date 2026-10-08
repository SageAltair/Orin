from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
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
)
from orin_api.config import Settings, get_settings
from orin_api.database import get_session
from orin_api.models import User
from orin_api.schemas import AuthTokenResponse, LoginRequest, RegisterRequest, UserRead

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
