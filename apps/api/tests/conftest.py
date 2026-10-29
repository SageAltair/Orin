import os


# Tests use a throwaway signing key; production deployments must provide their own.
os.environ.setdefault("AUTH_SECRET_KEY", "test-only-signing-key-" + "x" * 64)
os.environ.setdefault("AUTH_REFRESH_COOKIE_SECURE", "false")
