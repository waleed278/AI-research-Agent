import hashlib
import hmac
import secrets

import bcrypt


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


# bcrypt has a hard 72-byte input limit (silently truncates beyond it in
# some implementations) -- encoding as UTF-8 first and truncating there
# means a password with multi-byte characters can't be cut mid-codepoint.
_BCRYPT_MAX_BYTES = 72


def hash_password(raw_password: str) -> str:
    """Unlike API keys, passwords are user-chosen and low-entropy, so this
    deliberately uses a slow, salted KDF (bcrypt) rather than a fast hash --
    the whole point is to make brute-forcing a stolen hash expensive."""
    truncated = raw_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(raw_password: str, password_hash: str) -> bool:
    truncated = raw_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(truncated, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed/foreign hash format -- fail closed, not with a 500.
        return False
