from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, get_settings


class DecryptionError(Exception):
    """The ciphertext didn't decrypt -- wrong key (e.g. SECRET_ENCRYPTION_KEY
    was rotated without re-encrypting stored credentials) or corrupted data.
    Callers should treat a stored LlmCredential as unusable, not crash."""


def encrypt_secret(plaintext: str, settings: Settings | None = None) -> str:
    """Encrypts a third-party LLM provider API key before it touches the
    database (see app.db.models.LlmCredential). Fernet is symmetric and
    authenticated (AES-128-CBC + HMAC) -- appropriate here because, unlike a
    password, we must be able to recover the *plaintext* key later to
    actually call the provider on the user's behalf; hashing (one-way)
    would not work for this use case."""
    settings = settings or get_settings()
    fernet = Fernet(settings.secret_encryption_key.encode("utf-8"))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    fernet = Fernet(settings.secret_encryption_key.encode("utf-8"))
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError("Stored credential could not be decrypted") from exc
