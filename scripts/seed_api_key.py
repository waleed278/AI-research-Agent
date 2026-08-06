"""Creates a dev API key with a known plaintext value (from DEV_SEED_API_KEY,
default "dev-local-key") so local/manual testing doesn't require generating
and copying a random key. Safe to run repeatedly -- it's a no-op if a key
with that hash already exists.

Usage: uv run python scripts/seed_api_key.py
"""

import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import hash_api_key
from app.db.models import ApiKey
from app.db.session import get_session_factory

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    raw_key = settings.dev_seed_api_key
    key_hash = hash_api_key(raw_key)

    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        if existing.scalar_one_or_none() is not None:
            logger.info("dev_api_key_already_exists", key=raw_key)
            return

        session.add(ApiKey(name="dev-seed-key", key_hash=key_hash))
        await session.commit()
        logger.info("dev_api_key_created", key=raw_key)


if __name__ == "__main__":
    asyncio.run(main())
