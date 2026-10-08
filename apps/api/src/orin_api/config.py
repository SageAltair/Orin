from __future__ import annotations

from functools import lru_cache

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

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> Settings:
        if self.app_env.lower() in {"production", "prod"} and self.auth_secret_key is None:
            raise ValueError("AUTH_SECRET_KEY must be configured in production")
        if "*" in self.allowed_cors_origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins")
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
