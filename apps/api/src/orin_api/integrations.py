"""Provider-neutral integration contract and the read-only GitHub App adapter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from typing import Protocol
from urllib.parse import quote

import httpx


class IntegrationProviderError(Exception):
    def __init__(self, category: str, message: str, *, retry_after: int | None = None):
        super().__init__(message)
        self.category = category
        self.retry_after = retry_after


@dataclass(frozen=True)
class ProviderCapabilities:
    identity: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class ProviderCredentials:
    access_token: str
    refresh_token: str | None
    access_expires_at: datetime | None
    refresh_expires_at: datetime | None
    scopes: tuple[str, ...]


class IntegrationProvider(Protocol):
    capabilities: ProviderCapabilities

    def exchange_code(self, code: str, callback_url: str) -> ProviderCredentials: ...
    def refresh_credentials(self, refresh_token: str) -> ProviderCredentials: ...
    def revoke(self, access_token: str) -> None: ...
    def account(self, access_token: str) -> dict[str, str]: ...
    def list_repositories(self, access_token: str) -> list[dict[str, object]]: ...
    def list_issues(self, access_token: str, owner: str, repository: str) -> list[dict[str, object]]: ...
    def list_pull_requests(self, access_token: str, owner: str, repository: str) -> list[dict[str, object]]: ...


class GitHubAppClient:
    """GitHub App user OAuth adapter. App permissions must be read-only."""

    capabilities = ProviderCapabilities(
        identity="github",
        capabilities=("repositories.read", "issues.read", "pull_requests.read"),
    )
    _api = "https://api.github.com"
    _oauth = "https://github.com/login/oauth"
    _max_pages = 20

    def __init__(self, client_id: str, client_secret: str, *, transport: httpx.BaseTransport | None = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport

    def _request(self, method: str, url: str, *, token: str | None = None,
                 json_body: dict[str, object] | None = None,
                 params: dict[str, object] | None = None,
                 auth: tuple[str, str] | None = None,
                 accept: str = "application/vnd.github+json") -> dict[str, object] | list[object]:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        retryable = method == "GET"
        response = None
        last_error: httpx.RequestError | None = None
        for attempt in range(2 if retryable else 1):
            try:
                with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0), transport=self._transport) as client:
                    response = client.request(method, url, headers=headers, json=json_body, params=params, auth=auth)
                if response.status_code < 500 or attempt == 1:
                    break
            except httpx.RequestError as exc:
                last_error = exc
                if attempt == 1:
                    break
            time.sleep(0.1 * (attempt + 1))
        if response is None:
            if isinstance(last_error, httpx.TimeoutException):
                raise IntegrationProviderError("timeout", "GitHub did not respond before the request timed out.") from last_error
            raise IntegrationProviderError("unavailable", "GitHub could not be reached. Retry the operation.") from last_error

        if response.status_code == 429 or (response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"):
            retry_after = response.headers.get("Retry-After")
            try:
                reset = response.headers.get("X-RateLimit-Reset")
                retry_seconds = max(1, int(retry_after)) if retry_after else max(1, int(reset) - int(time.time())) if reset else None
            except ValueError:
                retry_seconds = None
            raise IntegrationProviderError("rate_limited", "GitHub rate limited this request. Retry later.", retry_after=retry_seconds)
        if response.status_code in {401, 403}:
            raise IntegrationProviderError("permission_denied", "GitHub denied this operation. Check the App installation and granted permissions.")
        if response.status_code == 404:
            raise IntegrationProviderError("not_found", "The GitHub resource is no longer available to this connection.")
        if response.status_code >= 500:
            raise IntegrationProviderError("unavailable", "GitHub is temporarily unavailable. Retry the operation.")
        if not response.is_success:
            raise IntegrationProviderError("provider_error", "GitHub rejected the request. Check the connection and try again.")
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise IntegrationProviderError("invalid_response", "GitHub returned an invalid response.") from exc
        if not isinstance(payload, (dict, list)):
            raise IntegrationProviderError("invalid_response", "GitHub returned an invalid response.")
        return payload

    @staticmethod
    def _credentials(payload: dict[str, object]) -> ProviderCredentials:
        access = payload.get("access_token")
        if not isinstance(access, str):
            raise IntegrationProviderError("oauth_denied", "GitHub did not grant the requested connection.")
        now = datetime.now(timezone.utc)
        try:
            access_lifetime = payload.get("expires_in")
            refresh_lifetime = payload.get("refresh_token_expires_in")
            access_expiry = now + timedelta(seconds=int(access_lifetime)) if access_lifetime is not None else None
            refresh_expiry = now + timedelta(seconds=int(refresh_lifetime)) if refresh_lifetime is not None else None
        except (TypeError, ValueError, OverflowError) as exc:
            raise IntegrationProviderError("invalid_response", "GitHub returned invalid credential expiration data.") from exc
        refresh = payload.get("refresh_token")
        scopes = payload.get("scope", "")
        scope_values = tuple(item for item in scopes.split(",") if item) if isinstance(scopes, str) else ()
        return ProviderCredentials(access, refresh if isinstance(refresh, str) else None,
                                   access_expiry, refresh_expiry, scope_values)

    def exchange_code(self, code: str, callback_url: str) -> ProviderCredentials:
        payload = self._request("POST", f"{self._oauth}/access_token", json_body={
            "client_id": self._client_id, "client_secret": self._client_secret,
            "code": code, "redirect_uri": callback_url,
        }, accept="application/json")
        if not isinstance(payload, dict):
            raise IntegrationProviderError("oauth_denied", "GitHub did not grant the requested connection.")
        return self._credentials(payload)

    def refresh_credentials(self, refresh_token: str) -> ProviderCredentials:
        payload = self._request("POST", f"{self._oauth}/access_token", json_body={
            "client_id": self._client_id, "client_secret": self._client_secret,
            "grant_type": "refresh_token", "refresh_token": refresh_token,
        }, accept="application/json")
        if not isinstance(payload, dict):
            raise IntegrationProviderError("invalid_response", "GitHub returned invalid refreshed credentials.")
        return self._credentials(payload)

    def revoke(self, access_token: str) -> None:
        self._request("DELETE", f"{self._api}/applications/{quote(self._client_id, safe='')}/token",
                      json_body={"access_token": access_token}, auth=(self._client_id, self._client_secret))

    def account(self, access_token: str) -> dict[str, str]:
        payload = self._request("GET", f"{self._api}/user", token=access_token)
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), int) or not isinstance(payload.get("login"), str):
            raise IntegrationProviderError("invalid_response", "GitHub did not return account information.")
        return {"id": str(payload["id"]), "login": payload["login"]}

    def list_repositories(self, access_token: str) -> list[dict[str, object]]:
        installations = self._list_pages(access_token, f"{self._api}/user/installations", "installations")
        repos: list[dict[str, object]] = []
        for installation in installations:
            if not isinstance(installation, dict) or not isinstance(installation.get("id"), int):
                raise IntegrationProviderError("invalid_response", "GitHub returned invalid App installation data.")
            repos.extend(self._list_pages(access_token,
                f"{self._api}/user/installations/{installation['id']}/repositories", "repositories"))
        result = []
        for repo in repos:
            if not isinstance(repo, dict) or not isinstance(repo.get("id"), int) or not isinstance(repo.get("full_name"), str):
                raise IntegrationProviderError("invalid_response", "GitHub returned invalid repository data.")
            owner, _, name = repo["full_name"].partition("/")
            if not owner or not name:
                continue
            result.append({"id": str(repo["id"]), "full_name": repo["full_name"], "owner": owner,
                "name": name, "private": bool(repo.get("private")),
                "html_url": repo.get("html_url") if isinstance(repo.get("html_url"), str) else None,
                "default_branch": repo.get("default_branch") if isinstance(repo.get("default_branch"), str) else None})
        return result

    def _list_pages(self, token: str, endpoint: str, key: str) -> list[object]:
        collected: list[object] = []
        for page in range(1, self._max_pages + 1):
            payload = self._request("GET", endpoint, token=token,
                params={"per_page": 100, "page": page})
            if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
                raise IntegrationProviderError("invalid_response", "GitHub returned an invalid list response.")
            batch = payload[key]
            collected.extend(batch)
            if len(batch) < 100:
                return collected
        raise IntegrationProviderError("too_many_results", "This GitHub account has too many repositories to list in one request.")

    @staticmethod
    def _safe_records(payload: dict[str, object] | list[object], *, is_pull: bool) -> list[dict[str, object]]:
        rows = payload if isinstance(payload, list) else payload.get("items", [])
        if not isinstance(rows, list):
            raise IntegrationProviderError("invalid_response", "GitHub returned an invalid issue response.")
        safe: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("number"), int) or not isinstance(row.get("title"), str):
                continue
            # GitHub's issues endpoint also includes pull requests. Keep issue and PR types distinct.
            if not is_pull and "pull_request" in row:
                continue
            safe.append({"number": row["number"], "title": row["title"][:240],
                "state": row.get("state") if isinstance(row.get("state"), str) else "unknown",
                "url": row.get("html_url") if isinstance(row.get("html_url"), str) else None,
                "updated_at": row.get("updated_at") if isinstance(row.get("updated_at"), str) else None,
                "draft": bool(row.get("draft")) if is_pull else False})
        return safe

    def list_issues(self, access_token: str, owner: str, repository: str) -> list[dict[str, object]]:
        path = f"{self._api}/repos/{quote(owner, safe='')}/{quote(repository, safe='')}/issues"
        payload = self._request("GET", path, token=access_token, params={"state": "all", "per_page": 100})
        return self._safe_records(payload, is_pull=False)

    def list_pull_requests(self, access_token: str, owner: str, repository: str) -> list[dict[str, object]]:
        path = f"{self._api}/repos/{quote(owner, safe='')}/{quote(repository, safe='')}/pulls"
        payload = self._request("GET", path, token=access_token, params={"state": "all", "per_page": 100})
        return self._safe_records(payload, is_pull=True)
