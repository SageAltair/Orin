"""Authenticated encryption for integration credentials at rest."""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class IntegrationSecretError(Exception):
    pass


def _cipher(key: str) -> MultiFernet:
    try:
        keys = [Fernet(item.strip().encode("ascii")) for item in key.split(",") if item.strip()]
        if not keys:
            raise ValueError("no Fernet key configured")
        return MultiFernet(keys)
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise IntegrationSecretError("INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_credential(key: str, credential: str) -> str:
    if not credential:
        raise IntegrationSecretError("Provider credential is empty.")
    return _cipher(key).encrypt(credential.encode("utf-8")).decode("ascii")


def decrypt_credential(key: str, ciphertext: str) -> str:
    try:
        return _cipher(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError) as exc:
        raise IntegrationSecretError("Stored integration credential cannot be decrypted; reconnect the provider.") from exc


def rotate_credential(key: str, ciphertext: str) -> str:
    """Re-encrypt with the first (current) key; remaining keys are decrypt-only."""
    try:
        return _cipher(key).rotate(ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeEncodeError) as exc:
        raise IntegrationSecretError("Stored integration credential cannot be rotated; reconnect the provider.") from exc
