"""Authenticated GitHub App OAuth, repository context, and read-only operations."""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from orin_api.auth import get_current_user
from orin_api.config import Settings, get_settings
from orin_api.database import get_session
from orin_api.integration_secrets import IntegrationSecretError, decrypt_credential, encrypt_credential, rotate_credential
from orin_api.integrations import GitHubAppClient, IntegrationProvider, IntegrationProviderError, ProviderCredentials
from orin_api.models import (
    ActivityType,
    IntegrationConnection,
    IntegrationOAuthState,
    Project,
    ProjectIntegrationSource,
    User,
)
from orin_api.services import add_activity

router = APIRouter(prefix="/api/v1/integrations/github", tags=["integrations"])
_OAUTH_STATE_TTL = timedelta(minutes=10)


class RepositorySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_resource_id: str = Field(min_length=1, max_length=120)


def _provider(settings: Settings) -> IntegrationProvider:
    if not settings.github_app_client_id or not settings.github_app_client_secret or not settings.github_app_callback_url:
        raise HTTPException(status_code=503, detail="GitHub integration is not configured by the server administrator.")
    return GitHubAppClient(settings.github_app_client_id, settings.github_app_client_secret.get_secret_value())


def _encryption_key(settings: Settings) -> str:
    if settings.integration_encryption_key is None:
        raise HTTPException(status_code=503, detail="Integration credential encryption is not configured.")
    return settings.integration_encryption_key.get_secret_value()


def _connection(session: Session, user_id: uuid.UUID) -> IntegrationConnection:
    row = session.scalar(select(IntegrationConnection).where(
        IntegrationConnection.user_id == user_id, IntegrationConnection.provider == "github"))
    if row is None:
        raise HTTPException(status_code=404, detail="GitHub is not connected.")
    return row


def _token(row: IntegrationConnection, settings: Settings) -> str:
    try:
        decoded = decrypt_credential(_encryption_key(settings), row.credential_ciphertext)
        payload = json.loads(decoded)
        if isinstance(payload, dict) and isinstance(payload.get("access_token"), str):
            return payload["access_token"]
        raise ValueError("invalid credential payload")
    except IntegrationSecretError as exc:
        raise HTTPException(status_code=409, detail="GitHub credentials cannot be decrypted. Disconnect and reconnect GitHub.") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="GitHub credentials are invalid. Disconnect and reconnect GitHub.") from exc


def _credential_payload(credentials: ProviderCredentials) -> str:
    return json.dumps({"access_token": credentials.access_token,
        "refresh_token": credentials.refresh_token,
        "refresh_expires_at": credentials.refresh_expires_at.isoformat() if credentials.refresh_expires_at else None})


def _token_with_refresh(session: Session, row: IntegrationConnection, settings: Settings,
                        provider: IntegrationProvider) -> str:
    try:
        decoded = decrypt_credential(_encryption_key(settings), row.credential_ciphertext)
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
            raise ValueError("invalid credential payload")
    except IntegrationSecretError as exc:
        raise HTTPException(status_code=409, detail="GitHub credentials cannot be decrypted. Disconnect and reconnect GitHub.") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="GitHub credentials are invalid. Disconnect and reconnect GitHub.") from exc
    rotated = rotate_credential(_encryption_key(settings), row.credential_ciphertext)
    if rotated != row.credential_ciphertext:
        row.credential_ciphertext = rotated
        session.flush()
    now = datetime.now(timezone.utc)
    if row.credential_expires_at is None or _utc(row.credential_expires_at) > now + timedelta(minutes=2):
        return payload["access_token"]
    refresh_token = payload.get("refresh_token")
    refresh_expiry = payload.get("refresh_expires_at")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise IntegrationProviderError("reauth_required", "GitHub authorization expired. Reconnect the GitHub App.")
    if isinstance(refresh_expiry, str):
        try:
            if _utc(datetime.fromisoformat(refresh_expiry)) <= now:
                raise IntegrationProviderError("reauth_required", "GitHub refresh authorization expired. Reconnect the GitHub App.")
        except ValueError as exc:
            raise IntegrationProviderError("invalid_response", "Stored GitHub refresh expiration is invalid.") from exc
    credentials = provider.refresh_credentials(refresh_token)
    row.credential_ciphertext = encrypt_credential(_encryption_key(settings), _credential_payload(credentials))
    row.credential_expires_at = credentials.access_expires_at
    if credentials.scopes:
        row.granted_scopes = list(credentials.scopes)
    session.commit()
    return credentials.access_token


def _record_operation(session: Session, user_id: uuid.UUID, operation: str, *, result: str,
                      severity: str = "info", correlation_id: str | None = None) -> None:
    add_activity(session, user_id=user_id, actor_user_id=user_id,
        activity_type=ActivityType.INTEGRATION_OPERATION,
        summary=f"GitHub {operation}", result_status=result, severity=severity,
        source="integration", correlation_id=correlation_id,
        metadata={"provider": "github", "status": result})


def _provider_failure(session: Session, user_id: uuid.UUID, operation: str,
                      exc: IntegrationProviderError, *, correlation_id: str | None = None) -> None:
    _record_operation(session, user_id, f"{operation} failed", result=exc.category,
        severity="warning", correlation_id=correlation_id)
    session.commit()
    status_code = 429 if exc.category == "rate_limited" else 409 if exc.category in {"permission_denied", "not_found", "reauth_required"} else 502
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    raise HTTPException(status_code=status_code, detail={"code": exc.category, "message": str(exc)}, headers=headers) from exc


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.post("/connect")
def begin_github_connect(user: User = Depends(get_current_user), session: Session = Depends(get_session),
                         settings: Settings = Depends(get_settings)) -> dict[str, object]:
    _provider(settings)
    _encryption_key(settings)
    session.execute(delete(IntegrationOAuthState).where(
        IntegrationOAuthState.expires_at < datetime.now(timezone.utc) - timedelta(days=1)))
    state = secrets.token_urlsafe(32)
    row = IntegrationOAuthState(user_id=user.id, state_hash=_state_hash(state),
        expires_at=datetime.now(timezone.utc) + _OAUTH_STATE_TTL)
    session.add(row)
    session.commit()
    query = urlencode({"client_id": settings.github_app_client_id,
                       "redirect_uri": settings.github_app_callback_url,
                       "state": state})
    return {"authorization_url": f"https://github.com/login/oauth/authorize?{query}",
            "expires_in": int(_OAUTH_STATE_TTL.total_seconds())}


@router.get("/callback")
def github_callback(code: str | None = Query(default=None, max_length=2000),
                    state: str = Query(min_length=20, max_length=200),
                    error: str | None = Query(default=None, max_length=100),
                    session: Session = Depends(get_session),
                    settings: Settings = Depends(get_settings)) -> Response:
    now = datetime.now(timezone.utc)
    consumed = session.execute(update(IntegrationOAuthState).where(
        IntegrationOAuthState.state_hash == _state_hash(state),
        IntegrationOAuthState.consumed_at.is_(None),
        IntegrationOAuthState.expires_at > now,
    ).values(consumed_at=now).returning(IntegrationOAuthState.id, IntegrationOAuthState.user_id)).one_or_none()
    if consumed is None:
        raise HTTPException(status_code=400, detail="GitHub authorization state is invalid or expired. Start again from Orin.")
    state_id, state_user_id = consumed
    session.commit()
    if error or not code:
        _record_operation(session, state_user_id, "authorization denied", result="denied",
                          severity="warning", correlation_id=str(state_id))
        session.commit()
        raise HTTPException(status_code=400, detail="GitHub authorization was denied. You can retry from Orin settings.")

    provider = _provider(settings)
    try:
        credentials = provider.exchange_code(code, settings.github_app_callback_url or "")
        account = provider.account(credentials.access_token)
        encrypted = encrypt_credential(_encryption_key(settings), _credential_payload(credentials))
        existing = session.scalar(select(IntegrationConnection).where(
            IntegrationConnection.user_id == state_user_id,
            IntegrationConnection.provider == "github").with_for_update())
        if existing is not None:
            old_token = _token_with_refresh(session, existing, settings, provider)
            if existing.external_account_id != account["id"]:
                try:
                    provider.revoke(old_token)
                except IntegrationProviderError as exc:
                    try:
                        provider.revoke(credentials.access_token)
                    except IntegrationProviderError:
                        pass
                    _provider_failure(session, state_user_id, "reconnect", exc,
                                      correlation_id=str(existing.id))
                session.execute(delete(ProjectIntegrationSource).where(
                    ProjectIntegrationSource.connection_id == existing.id))
            else:
                try:
                    provider.revoke(old_token)
                except IntegrationProviderError as exc:
                    try:
                        provider.revoke(credentials.access_token)
                    except IntegrationProviderError:
                        pass
                    _provider_failure(session, state_user_id, "reconnect", exc,
                                      correlation_id=str(existing.id))
            existing.external_account_id = account["id"]
            existing.account_login = account["login"]
            existing.credential_ciphertext = encrypted
            existing.granted_scopes = list(credentials.scopes)
            existing.credential_expires_at = credentials.access_expires_at
            connection = existing
        else:
            connection = IntegrationConnection(user_id=state_user_id, provider="github",
                external_account_id=account["id"], account_login=account["login"],
                credential_ciphertext=encrypted, granted_scopes=list(credentials.scopes),
                credential_expires_at=credentials.access_expires_at)
            session.add(connection)
        session.flush()
        _record_operation(session, state_user_id, "connected", result="connected",
                          correlation_id=str(connection.id))
        session.commit()
    except IntegrationProviderError as exc:
        _provider_failure(session, state_user_id, "connect", exc)
    except IntegrationSecretError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(url=f"{settings.web_app_url.rstrip('/')}/?integration=github_connected#settings", status_code=303)


@router.get("")
def github_status(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict[str, object]:
    row = session.scalar(select(IntegrationConnection).where(
        IntegrationConnection.user_id == user.id, IntegrationConnection.provider == "github"))
    return {"connected": row is not None, "provider": "github",
        "account_login": row.account_login if row else None,
        "granted_scopes": row.granted_scopes if row else [],
        "capabilities": list(GitHubAppClient.capabilities.capabilities),
        "last_successful_sync_at": row.last_successful_sync_at if row else None}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
def disconnect_github(user: User = Depends(get_current_user), session: Session = Depends(get_session),
                      settings: Settings = Depends(get_settings)) -> Response:
    row = session.scalar(select(IntegrationConnection).where(
        IntegrationConnection.user_id == user.id, IntegrationConnection.provider == "github").with_for_update())
    if row is None:
        return Response(status_code=204)
    provider = _provider(settings)
    try:
        provider.revoke(_token_with_refresh(session, row, settings, provider))
    except IntegrationProviderError as exc:
        _provider_failure(session, user.id, "disconnect failed", exc, correlation_id=str(row.id))
    connection_id = row.id
    session.delete(row)
    _record_operation(session, user.id, "disconnected", result="disconnected", correlation_id=str(connection_id))
    session.commit()
    return Response(status_code=204)


@router.get("/repositories")
def github_repositories(user: User = Depends(get_current_user), session: Session = Depends(get_session),
                        settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    connection = _connection(session, user.id)
    provider = _provider(settings)
    try:
        repositories = provider.list_repositories(_token_with_refresh(session, connection, settings, provider))
    except IntegrationProviderError as exc:
        _provider_failure(session, user.id, "repository list", exc, correlation_id=str(connection.id))
    connection.last_successful_sync_at = datetime.now(timezone.utc)
    _record_operation(session, user.id, "repositories listed", result="succeeded", correlation_id=str(connection.id))
    session.commit()
    selected_rows = session.execute(select(ProjectIntegrationSource.provider_resource_id,
        ProjectIntegrationSource.project_id).where(ProjectIntegrationSource.user_id == user.id,
        ProjectIntegrationSource.provider == "github")).all()
    selected: dict[str, list[str]] = {}
    for resource_id, selected_project_id in selected_rows:
        selected.setdefault(resource_id, []).append(str(selected_project_id))
    return [{**repo, "selected_project_ids": selected.get(str(repo.get("id")), [])} for repo in repositories]


@router.put("/projects/{project_id}/repository")
def select_project_repository(project_id: uuid.UUID, data: RepositorySelection,
                              user: User = Depends(get_current_user), session: Session = Depends(get_session),
                              settings: Settings = Depends(get_settings)) -> dict[str, object]:
    project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    connection = _connection(session, user.id)
    provider = _provider(settings)
    try:
        repositories = provider.list_repositories(_token_with_refresh(session, connection, settings, provider))
    except IntegrationProviderError as exc:
        _provider_failure(session, user.id, "repository validation", exc, correlation_id=str(connection.id))
    repository = next((item for item in repositories if str(item.get("id")) == data.provider_resource_id), None)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository is not available to this GitHub connection.")
    row = session.scalar(select(ProjectIntegrationSource).where(
        ProjectIntegrationSource.project_id == project.id, ProjectIntegrationSource.provider == "github").with_for_update())
    owner = str(repository["owner"])
    name = str(repository["name"])
    if row is None:
        row = ProjectIntegrationSource(user_id=user.id, project_id=project.id,
            connection_id=connection.id, provider="github", provider_resource_id=data.provider_resource_id,
            resource_owner=owner, resource_name=name)
        session.add(row)
    else:
        row.connection_id = connection.id
        row.provider_resource_id = data.provider_resource_id
        row.resource_owner = owner
        row.resource_name = name
    _record_operation(session, user.id, "repository selected", result="succeeded",
                      correlation_id=str(connection.id))
    session.commit()
    return {"project_id": str(project.id), "repository_id": row.provider_resource_id,
            "full_name": f"{row.resource_owner}/{row.resource_name}"}


@router.get("/projects/{project_id}/issues")
def project_github_context(project_id: uuid.UUID, user: User = Depends(get_current_user),
                           session: Session = Depends(get_session),
                           settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    source = session.scalar(select(ProjectIntegrationSource).where(
        ProjectIntegrationSource.project_id == project_id,
        ProjectIntegrationSource.user_id == user.id, ProjectIntegrationSource.provider == "github"))
    if source is None:
        raise HTTPException(status_code=404, detail="This project has no GitHub repository selected.")
    connection = session.scalar(select(IntegrationConnection).where(
        IntegrationConnection.id == source.connection_id, IntegrationConnection.user_id == user.id,
        IntegrationConnection.provider == "github"))
    if connection is None:
        raise HTTPException(status_code=409, detail="Reconnect GitHub to access this project source.")
    provider = _provider(settings)
    try:
        token = _token_with_refresh(session, connection, settings, provider)
        issues = provider.list_issues(token, source.resource_owner, source.resource_name)
        pulls = provider.list_pull_requests(token, source.resource_owner, source.resource_name)
    except IntegrationProviderError as exc:
        _provider_failure(session, user.id, "project sync", exc, correlation_id=str(connection.id))
    connection.last_successful_sync_at = datetime.now(timezone.utc)
    _record_operation(session, user.id, "project synchronized", result="succeeded",
                      correlation_id=str(connection.id))
    session.commit()
    return {"repository": f"{source.resource_owner}/{source.resource_name}",
            "issues": issues, "pull_requests": pulls,
            "last_successful_sync_at": connection.last_successful_sync_at}


@router.delete("/projects/{project_id}/repository", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response, response_model=None)
def remove_project_repository(project_id: uuid.UUID, user: User = Depends(get_current_user),
                              session: Session = Depends(get_session)) -> Response:
    project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    row = session.scalar(select(ProjectIntegrationSource).where(
        ProjectIntegrationSource.project_id == project_id, ProjectIntegrationSource.user_id == user.id,
        ProjectIntegrationSource.provider == "github"))
    if row:
        session.delete(row)
        _record_operation(session, user.id, "repository removed from project", result="disconnected",
                          correlation_id=str(row.connection_id))
        session.commit()
    return Response(status_code=204)
