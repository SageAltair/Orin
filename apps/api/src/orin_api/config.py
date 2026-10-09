from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    database_url: PostgresDsn = "postgresql+psycopg://orin:orin@localhost:5432/orin"
    cors_origins: str = "http://localhost:5173"
    auth_secret_key: SecretStr | None = Field(default=None, min_length=64)
    access_token_lifetime_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_lifetime_days: int = Field(default=30, ge=1, le=90)
    auth_refresh_cookie_secure: bool = True
    ai_provider: str = ""
    ai_model: str = ""
    openai_api_key: str | None = Field(default=None, repr=False)
    mistral_api_key: str | None = Field(default=None, repr=False)
    google_api_key: str | None = Field(default=None, repr=False)
    openrouter_api_key: str | None = Field(default=None, repr=False)
    qwen_api_key: str | None = Field(default=None, repr=False)
    groq_api_key: str | None = Field(default=None, repr=False)
    cerebras_api_key: str | None = Field(default=None, repr=False)
    cloudflare_api_key: str | None = Field(default=None, repr=False)
    cloudflare_account_id: str | None = Field(default=None, repr=False)
    integration_encryption_key: SecretStr | None = Field(default=None, repr=False)
    github_app_client_id: str | None = None
    github_app_client_secret: SecretStr | None = Field(default=None, repr=False)
    github_app_callback_url: str | None = None
    web_app_url: str = "http://localhost:5173"

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> Settings:
        production = self.app_env.lower() in {"production", "prod"}
        if production:
            if self.auth_secret_key is None:
                raise ValueError("AUTH_SECRET_KEY must be configured in production")
            if not {"database_url", "cors_origins", "web_app_url"}.issubset(self.model_fields_set):
                raise ValueError("DATABASE_URL, CORS_ORIGINS, and WEB_APP_URL must be explicitly configured in production")
            if not self.allowed_cors_origins or any(urlsplit(origin).scheme != "https" for origin in self.allowed_cors_origins):
                raise ValueError("CORS_ORIGINS must contain HTTPS origins in production")
            if urlsplit(self.web_app_url).scheme != "https":
                raise ValueError("WEB_APP_URL must use HTTPS in production")
            if not self.auth_refresh_cookie_secure:
                raise ValueError("AUTH_REFRESH_COOKIE_SECURE must be enabled in production")
        if "*" in self.allowed_cors_origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins")
        secret_set = bool(self.github_app_client_secret and self.github_app_client_secret.get_secret_value())
        encryption_set = bool(self.integration_encryption_key and self.integration_encryption_key.get_secret_value())
        client_id_set = bool(self.github_app_client_id and self.github_app_client_id.strip())
        callback_set = bool(self.github_app_callback_url and self.github_app_callback_url.strip())
        github_configured = any((client_id_set, secret_set, callback_set))
        if github_configured and not all((client_id_set, secret_set, callback_set, encryption_set)):
            raise ValueError("GitHub integration requires its client ID, client secret, callback URL, and INTEGRATION_ENCRYPTION_KEY")
        if github_configured:
            from cryptography.fernet import Fernet, InvalidToken
            try:
                keys = [item.strip() for item in self.integration_encryption_key.get_secret_value().split(",") if item.strip()]
                if not keys:
                    raise ValueError("no keys")
                for key in keys:
                    Fernet(key.encode("ascii"))
            except (ValueError, TypeError, UnicodeEncodeError, InvalidToken) as exc:
                raise ValueError("INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key") from exc
            callback = urlsplit(self.github_app_callback_url or "")
            if callback.scheme != "https" and not (self.app_env.lower() not in {"production", "prod"} and callback.hostname in {"localhost", "127.0.0.1"}):
                raise ValueError("GITHUB_APP_CALLBACK_URL must use HTTPS outside local development")
            web = urlsplit(self.web_app_url)
            if web.scheme != "https" and not (self.app_env.lower() not in {"production", "prod"} and web.hostname in {"localhost", "127.0.0.1"}):
                raise ValueError("WEB_APP_URL must use HTTPS outside local development")
        return self

    def require_auth_secret(self) -> str:
        if self.auth_secret_key is None:
            raise RuntimeError("AUTH_SECRET_KEY is required to issue or verify authentication tokens")
        return self.auth_secret_key.get_secret_value()

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
