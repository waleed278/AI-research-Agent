import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_arq_redis, get_db_session, get_rate_limit_redis
from app.core.security import generate_api_key, hash_api_key
from app.db.base import Base
from app.db.models import ApiKey
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://agent:agent@localhost:5432/research_agent_test"
)


class NoOpArqRedis:
    """Stands in for the real arq/Redis pool. `enqueue_job` intentionally
    does nothing -- these tests simulate the worker picking the job up by
    calling `run_research_job` directly, which is a more accurate model of
    the real system (API process and worker process are separate; a
    same-process eager call would hide cross-process bugs, e.g. reading
    a not-yet-committed row)."""

    async def enqueue_job(self, *_args: object, **_kwargs: object) -> None:
        return None


class FakeRateLimitRedis:
    """In-memory stand-in for the Redis client used by the rate limiter, so
    integration tests only need Postgres, not a Redis instance too."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def ping(self) -> bool:
        return True


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect():
            pass
    except Exception as exc:
        db_name = TEST_DATABASE_URL.rsplit("/", 1)[-1]
        pytest.skip(
            f"Postgres not reachable at {TEST_DATABASE_URL}. Run `docker compose "
            f"-f infra/docker-compose.yml up -d postgres` and create a '{db_name}' "
            f"database to run integration tests. ({exc})"
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def test_session_factory(db_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _worker_uses_test_database(monkeypatch: pytest.MonkeyPatch, test_session_factory) -> None:
    """`run_research_job` looks up its own session factory (it's a separate
    process from the API in production, see workers/worker.py) -- point it
    at the same test database the API layer is using for this test."""
    monkeypatch.setattr("app.workers.worker.get_session_factory", lambda: test_session_factory)


@pytest_asyncio.fixture
async def db_session(test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest_asyncio.fixture
async def api_key(db_session: AsyncSession) -> tuple[ApiKey, str]:
    raw_key = generate_api_key()
    key = ApiKey(id=uuid.uuid4(), name="test-key", key_hash=hash_api_key(raw_key))
    db_session.add(key)
    await db_session.commit()
    await db_session.refresh(key)
    return key, raw_key


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_arq_redis] = lambda: NoOpArqRedis()
    app.dependency_overrides[get_rate_limit_redis] = lambda: FakeRateLimitRedis()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
