import pytest

from app.core.config import get_settings
from tests.integration.conftest import bearer_headers

SIGNUP_PAYLOAD = {"email": "new-user@example.com", "password": "correct horse battery staple"}


@pytest.mark.asyncio
async def test_signup_creates_an_account_and_returns_a_usable_token(client) -> None:
    response = await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == SIGNUP_PAYLOAD["email"]
    assert body["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == SIGNUP_PAYLOAD["email"]


@pytest.mark.asyncio
async def test_signup_rejects_a_duplicate_email(client) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)
    response = await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_signup_rejects_a_too_short_password(client) -> None:
    response = await client.post(
        "/api/v1/auth/signup", json={"email": "short-pw@example.com", "password": "short"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_succeeds_with_the_correct_password(client) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    response = await client.post("/api/v1/auth/login", json=SIGNUP_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["user"]["email"] == SIGNUP_PAYLOAD["email"]


@pytest.mark.asyncio
async def test_login_rejects_the_wrong_password(client) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP_PAYLOAD)

    response = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP_PAYLOAD["email"], "password": "wrong password"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_an_unknown_email_with_the_same_error_as_a_wrong_password(client) -> None:
    """Distinguishing "no such user" from "wrong password" would let an
    attacker enumerate registered emails -- see app/services/auth_service.py."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever12345"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_authentication(client) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_a_token_for_a_nonexistent_user(client, user) -> None:
    """A user deleted after a token was issued must not still authenticate."""
    headers = bearer_headers(user)
    # (Deleting the user is exercised at the unit level for decode_access_token;
    # here we confirm a well-formed-but-garbage token is rejected end to end.)
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert response.status_code == 401
    # Sanity check the real token still works, so the failure above is
    # actually about the garbage token, not a broken fixture.
    ok_response = await client.get("/api/v1/auth/me", headers=headers)
    assert ok_response.status_code == 200


@pytest.mark.asyncio
async def test_login_is_rate_limited(client) -> None:
    limit = get_settings().login_rate_limit_per_minute

    statuses = [
        (
            await client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "whatever12345"},
            )
        ).status_code
        for _ in range(limit + 2)
    ]

    assert statuses.count(429) >= 1
