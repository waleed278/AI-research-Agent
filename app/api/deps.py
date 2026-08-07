from arq import ArqRedis
from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import RateLimitedError, UnauthorizedError
from app.core.jwt import InvalidTokenError, decode_access_token
from app.db.models import User
from app.db.repositories import ApiKeyRepository, UserRepository
from app.db.session import get_db as get_db_session


def get_arq_redis(request: Request) -> ArqRedis:
    return request.app.state.arq_redis


def get_rate_limit_redis(request: Request) -> Redis:
    return request.app.state.rate_limit_redis


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Two ways to authenticate, both resolving to the same `User`:

    1. `Authorization: Bearer <jwt>` -- what the web app uses, issued by
       `POST /auth/login` or `/auth/signup`.
    2. `X-API-Key: <key>` -- a self-service developer credential
       (`app/api/v1/routes/api_keys.py`) for programmatic/script access.

    Every route downstream only ever deals with `user_id`, never caring
    which method was used -- see docs/decisions/0008-accounts-and-dual-auth.md.
    Both header params are optional at the FastAPI level (a *required*
    `Header(...)` would make a missing header a 422 validation error before
    this function runs, but "no credentials supplied" is a 401, not a
    malformed request).
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[len("Bearer ") :]
        try:
            claims = decode_access_token(token, settings)
        except InvalidTokenError as exc:
            raise UnauthorizedError("Invalid or expired access token") from exc
        user = await UserRepository(session).get(claims.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Invalid or expired access token")
        return user

    if x_api_key:
        api_key = await ApiKeyRepository(session).get_by_raw_key(x_api_key)
        if api_key is None:
            raise UnauthorizedError("Missing or invalid API key")
        user = await UserRepository(session).get(api_key.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Missing or invalid API key")
        return user

    raise UnauthorizedError(
        "Missing credentials -- provide an 'Authorization: Bearer <token>' or 'X-API-Key' header"
    )


async def enforce_rate_limit(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_rate_limit_redis),
    settings: Settings = Depends(get_settings),
) -> None:
    """Fixed-window token-bucket-lite: one counter per user per 60s window,
    held in Redis so it's correct across multiple API replicas (an
    in-process counter would reset per-pod and let a caller multiply their
    effective limit by the replica count). Keyed on `user.id` rather than
    the credential used, so a caller can't multiply their limit by mixing
    a JWT and an API key across requests."""
    key = f"rate_limit:{user.id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > settings.api_key_rate_limit_per_minute:
        raise RateLimitedError(
            f"Rate limit of {settings.api_key_rate_limit_per_minute} requests/minute exceeded"
        )


async def enforce_login_rate_limit(
    request: Request,
    redis: Redis = Depends(get_rate_limit_redis),
    settings: Settings = Depends(get_settings),
) -> None:
    """IP-keyed brute-force guard on /auth/login and /auth/signup, ahead of
    any credential check (there is no user to key on yet). `request.client`
    is the direct TCP peer -- behind a reverse proxy that's the proxy's own
    address unless it forwards the real client IP (e.g. via
    `X-Forwarded-For`) and uvicorn is run with `--proxy-headers`, which this
    project's Docker Compose setup does not currently configure. Good
    enough to slow down casual brute forcing locally; noted as a gap for a
    real internet-facing deployment."""
    client_host = request.client.host if request.client else "unknown"
    key = f"rate_limit:login:{client_host}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > settings.login_rate_limit_per_minute:
        raise RateLimitedError(
            f"Rate limit of {settings.login_rate_limit_per_minute} attempts/minute exceeded"
        )
