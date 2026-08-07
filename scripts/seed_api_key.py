"""Creates a dev user (if needed) and a dev API key with a known plaintext
value (from DEV_SEED_API_KEY, default "dev-local-key") so local/manual
testing doesn't require going through the signup flow or generating and
copying a random key. Safe to run repeatedly -- it's a no-op if a key with
that hash already exists.

Usage: uv run python scripts/seed_api_key.py
"""

import asyncio
import secrets

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import hash_api_key, hash_password
from app.db.models import ApiKey, User
from app.db.session import get_session_factory

logger = get_logger(__name__)

DEV_SEED_EMAIL = "dev@example.com"


async def main() -> None:
    settings = get_settings()
    raw_key = settings.dev_seed_api_key
    key_hash = hash_api_key(raw_key)

    session_factory = get_session_factory()
    async with session_factory() as session:
        existing_key = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        if existing_key.scalar_one_or_none() is not None:
            logger.info("dev_api_key_already_exists", key=raw_key)
            return

        existing_user = await session.execute(select(User).where(User.email == DEV_SEED_EMAIL))
        user = existing_user.scalar_one_or_none()
        if user is None:
            # The password is unused by this script's purpose (the API key is
            # what grants access) -- randomized rather than a fixed dev
            # password so a leaked seed script doesn't also leak a login.
            user = User(email=DEV_SEED_EMAIL, password_hash=hash_password(secrets.token_urlsafe(32)))
            session.add(user)
            await session.flush()
            logger.info("dev_user_created", email=DEV_SEED_EMAIL)

        session.add(ApiKey(user_id=user.id, name="dev-seed-key", key_hash=key_hash))
        await session.commit()
        logger.info("dev_api_key_created", key=raw_key, user_email=DEV_SEED_EMAIL)


if __name__ == "__main__":
    asyncio.run(main())
