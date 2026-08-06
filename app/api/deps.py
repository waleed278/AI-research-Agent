from arq import ArqRedis
from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import RateLimitedError, UnauthorizedError
from app.db.models import ApiKey
from app.db.repositories import ApiKeyRepository
from app.db.session import get_db as get_db_session


def get_arq_redis(request: Request) -> ArqRedis:
    return request.app.state.arq_redis


def get_rate_limit_redis(request: Request) -> Redis:
    return request.app.state.rate_limit_redis


async def get_current_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(get_db_session),
) -> ApiKey:
    api_key = await ApiKeyRepository(session).get_by_raw_key(x_api_key)
    if api_key is None:
        raise UnauthorizedError("Missing or invalid API key")
    return api_key


async def enforce_rate_limit(
    api_key: ApiKey = Depends(get_current_api_key),
    redis: Redis = Depends(get_rate_limit_redis),
    settings: Settings = Depends(get_settings),
) -> None:
    """Fixed-window token-bucket-lite: one counter per API key per 60s
    window, held in Redis so it's correct across multiple API replicas
    (an in-process counter would reset per-pod and let a caller multiply
    their effective limit by the replica count)."""
    key = f"rate_limit:{api_key.id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > settings.api_key_rate_limit_per_minute:
        raise RateLimitedError(
            f"Rate limit of {settings.api_key_rate_limit_per_minute} requests/minute exceeded"
        )
