import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.security import generate_api_key, hash_api_key
from app.db.models import ApiKey
from app.db.repositories import ApiKeyRepository


async def create_api_key(session: AsyncSession, user_id: uuid.UUID, name: str) -> tuple[ApiKey, str]:
    raw_key = generate_api_key()
    api_key = await ApiKeyRepository(session).create(user_id, name, hash_api_key(raw_key))
    return api_key, raw_key


async def list_api_keys(session: AsyncSession, user_id: uuid.UUID) -> list[ApiKey]:
    return await ApiKeyRepository(session).list_for_user(user_id)


async def revoke_api_key(session: AsyncSession, user_id: uuid.UUID, key_id: uuid.UUID) -> None:
    api_keys = ApiKeyRepository(session)
    api_key = await api_keys.get(key_id, user_id)
    if api_key is None:
        raise NotFoundError(f"No API key with id {key_id}")
    await api_keys.revoke(api_key)
