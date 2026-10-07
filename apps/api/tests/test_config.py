from orin_api.config import Settings


def test_comma_separated_cors_origins_are_normalized() -> None:
    settings = Settings(cors_origins="http://localhost:5173, https://orin.example")

    assert settings.allowed_cors_origins == [
        "http://localhost:5173",
        "https://orin.example",
    ]
