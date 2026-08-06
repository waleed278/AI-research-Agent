from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_rate_limit_redis

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    """Process is up. Does not check dependencies -- used by the
    orchestrator (k8s/compose) to decide whether to restart the container."""
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_rate_limit_redis),
) -> dict[str, str]:
    """Dependencies are reachable. Used to decide whether to route traffic
    to this instance -- a live-but-not-ready pod should not receive requests."""
    checks = {"database": "ok", "redis": "ok"}
    healthy = True

    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - reported in the response body, not raised
        checks["database"] = f"error: {exc}"
        healthy = False

    try:
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"
        healthy = False

    response.status_code = 200 if healthy else 503
    return checks
