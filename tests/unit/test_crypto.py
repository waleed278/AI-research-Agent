import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.core.crypto import DecryptionError, decrypt_secret, encrypt_secret


def _settings(key: bytes | None = None) -> Settings:
    return Settings(secret_encryption_key=(key or Fernet.generate_key()).decode("utf-8"))


def test_decrypt_recovers_the_original_plaintext() -> None:
    settings = _settings()
    ciphertext = encrypt_secret("sk-super-secret-provider-key", settings)

    assert decrypt_secret(ciphertext, settings) == "sk-super-secret-provider-key"


def test_ciphertext_does_not_contain_the_plaintext() -> None:
    settings = _settings()
    ciphertext = encrypt_secret("sk-super-secret-provider-key", settings)

    assert "sk-super-secret-provider-key" not in ciphertext


def test_decrypt_fails_with_the_wrong_key() -> None:
    ciphertext = encrypt_secret("sk-super-secret-provider-key", _settings())

    with pytest.raises(DecryptionError):
        decrypt_secret(ciphertext, _settings())  # a different, freshly generated key


def test_encrypting_the_same_plaintext_twice_gives_different_ciphertext() -> None:
    settings = _settings()
    first = encrypt_secret("same-key", settings)
    second = encrypt_secret("same-key", settings)

    assert first != second  # Fernet includes a random IV per encryption
    assert decrypt_secret(first, settings) == decrypt_secret(second, settings) == "same-key"
