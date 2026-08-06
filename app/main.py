from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import from_url as redis_from_url
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.middleware import RequestContextMiddleware
from app.api.v1.router import api_router
from app.api.v1.routes import health
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    app.state.arq_redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    app.state.rate_limit_redis = redis_from_url(settings.redis_url)

    logger.info("app_startup", environment=settings.environment)
    yield

    await app.state.arq_redis.close()
    await app.state.rate_limit_redis.aclose()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Research & Report Agent",
        description=(
            "Async, tool-using research agent with an OpenAI-backed "
            "planner/critic/synthesizer pipeline."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # Only needed for a frontend calling this API directly from a different
    # origin (e.g. local `vite dev`) -- the Docker Compose frontend instead
    # reverse-proxies /api through its own nginx, so the browser never
    # crosses origins there (see frontend/nginx.conf).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "type": "https://errors.research-agent.dev/InternalServerError",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected error occurred.",
                "instance": str(request.url.path),
            },
            media_type="application/problem+json",
        )

    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
