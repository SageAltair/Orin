import pytest
from pydantic import ValidationError

from orin_api.config import Settings


def test_comma_separated_cors_origins_are_normalized() -> None:
    settings = Settings(cors_origins="http://localhost:5173, https://orin.example")

    assert settings.allowed_cors_origins == [
        "http://localhost:5173",
        "https://orin.example",
    ]


def test_auth_secret_is_required_in_production_and_must_be_long() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", auth_secret_key=None)
    with pytest.raises(ValidationError):
        Settings(auth_secret_key="too-short")


def test_production_requires_explicit_database_and_https_web_configuration() -> None:
    shared = {"app_env": "production", "auth_secret_key": "a" * 64}
    with pytest.raises(ValidationError, match="must be explicitly configured"):
        Settings(**shared)
    with pytest.raises(ValidationError, match="CORS_ORIGINS must contain HTTPS"):
        Settings(**shared, database_url="postgresql+psycopg://orin:change-me@db:5432/orin",
                 cors_origins="http://orin.example", web_app_url="https://orin.example")
    with pytest.raises(ValidationError, match="WEB_APP_URL must use HTTPS"):
        Settings(**shared, database_url="postgresql+psycopg://orin:change-me@db:5432/orin",
                 cors_origins="https://orin.example", web_app_url="http://orin.example")
    with pytest.raises(ValidationError, match="AUTH_REFRESH_COOKIE_SECURE"):
        Settings(**shared, database_url="postgresql+psycopg://orin:change-me@db:5432/orin",
                 cors_origins="https://orin.example", web_app_url="https://orin.example",
                 auth_refresh_cookie_secure=False)
    settings = Settings(**shared, database_url="postgresql+psycopg://orin:change-me@db:5432/orin",
                        cors_origins="https://orin.example", web_app_url="https://orin.example",
                        auth_refresh_cookie_secure=True)
    assert settings.allowed_cors_origins == ["https://orin.example"]


def test_credentialed_cors_rejects_wildcard_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins="*")
