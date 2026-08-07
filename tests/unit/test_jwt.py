import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from app.core.config import Settings
from app.core.jwt import InvalidTokenError, create_access_token, decode_access_token


def _settings(**overrides) -> Settings:
    # 32+ chars to avoid PyJWT's InsecureKeyLengthWarning noise in test output.
    overrides.setdefault("jwt_secret_key", "test-secret-key-at-least-32-bytes-long")
    return Settings(**overrides)


def test_decode_recovers_the_same_claims_that_were_encoded() -> None:
    settings = _settings()
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "user@example.com", settings)

    claims = decode_access_token(token, settings)

    assert claims.user_id == user_id
    assert claims.email == "user@example.com"


def test_decode_rejects_a_token_signed_with_a_different_secret() -> None:
    token = create_access_token(
        uuid.uuid4(), "user@example.com", _settings(jwt_secret_key="a" * 32)
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, _settings(jwt_secret_key="b" * 32))


def test_decode_rejects_an_expired_token() -> None:
    settings = _settings()
    expired_payload = {
        "sub": str(uuid.uuid4()),
        "email": "user@example.com",
        "iat": datetime.now(UTC) - timedelta(days=2),
        "exp": datetime.now(UTC) - timedelta(days=1),
    }
    expired_token = pyjwt.encode(expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidTokenError):
        decode_access_token(expired_token, settings)


def test_decode_rejects_garbage_input() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.jwt", _settings())


def test_decode_rejects_a_token_missing_required_claims() -> None:
    settings = _settings()
    incomplete_token = pyjwt.encode(
        {"iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(incomplete_token, settings)
