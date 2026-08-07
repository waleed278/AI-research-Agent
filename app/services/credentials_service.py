import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.crypto import encrypt_secret
from app.core.exceptions import InvalidRequestError, NotFoundError
from app.db.models import LlmCredential
from app.db.repositories import LlmCredentialRepository
from app.llm.base import InvalidCredentialError
from app.llm.factory import build_provider
from app.schemas.credentials import AddLlmCredentialRequest


async def add_credential(
    session: AsyncSession,
    user_id: uuid.UUID,
    request: AddLlmCredentialRequest,
    settings: Settings | None = None,
) -> LlmCredential:
    """Validates the key against the real provider (a cheap, zero/near-zero
    -cost call -- see each adapter's `validate()`) before ever storing it.
    A key that doesn't work is rejected here, not discovered later when a
    job using it fails."""
    settings = settings or get_settings()
    provider_client = build_provider(request.provider, request.api_key, settings)
    try:
        await provider_client.validate()
    except InvalidCredentialError as exc:
        raise InvalidRequestError(str(exc)) from exc

    encrypted_key = encrypt_secret(request.api_key, settings)
    return await LlmCredentialRepository(session).upsert(
        user_id, request.provider, encrypted_key, request.label
    )


async def list_credentials(session: AsyncSession, user_id: uuid.UUID) -> list[LlmCredential]:
    return await LlmCredentialRepository(session).list_for_user(user_id)


async def delete_credential(session: AsyncSession, user_id: uuid.UUID, credential_id: uuid.UUID) -> None:
    credentials = LlmCredentialRepository(session)
    credential = await credentials.get(credential_id, user_id)
    if credential is None:
        raise NotFoundError(f"No credential with id {credential_id}")
    await credentials.delete(credential)
