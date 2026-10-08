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


def test_credentialed_cors_rejects_wildcard_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins="*")
