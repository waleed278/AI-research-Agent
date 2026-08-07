import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import BaseModel

from app.core.config import Settings, get_settings


class InvalidTokenError(Exception):
    """Raised for any token problem (expired, malformed, wrong signature) --
    callers don't need to distinguish why, only that the caller isn't
    authenticated (see app/api/deps.py::get_current_user)."""


class AccessTokenClaims(BaseModel):
    user_id: uuid.UUID
    email: str


def create_access_token(user_id: uuid.UUID, email: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings | None = None) -> AccessTokenClaims:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    try:
        return AccessTokenClaims(user_id=uuid.UUID(payload["sub"]), email=payload["email"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("Token payload missing required claims") from exc
