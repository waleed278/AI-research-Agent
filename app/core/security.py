import hashlib
import hmac
import secrets


def generate_api_key() -> str:
    """Returns a new plaintext API key. Shown to the caller exactly once at
    creation time -- only its hash is ever persisted."""
    return f"ra_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    """SHA-256 is sufficient here (unlike passwords, API keys are already
    high-entropy random tokens, not user-chosen secrets) -- no need for a
    slow KDF like bcrypt/argon2."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), key_hash)
