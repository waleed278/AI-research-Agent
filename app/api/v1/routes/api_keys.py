import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.db.models import ApiKey, User
from app.schemas.api_keys import ApiKeyCreateResponse, ApiKeyResponse, CreateApiKeyRequest
from app.services import api_keys_service

router = APIRouter(prefix="/me/api-keys", tags=["api-keys"])


def _to_response(api_key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id, name=api_key.name, is_active=api_key.is_active, created_at=api_key.created_at
    )


@router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_key(
    body: CreateApiKeyRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyCreateResponse:
    api_key, raw_key = await api_keys_service.create_api_key(session, user.id, body.name)
    return ApiKeyCreateResponse(
        id=api_key.id, name=api_key.name, raw_key=raw_key, created_at=api_key.created_at
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_keys(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
) -> list[ApiKeyResponse]:
    keys = await api_keys_service.list_api_keys(session, user.id)
    return [_to_response(k) for k in keys]


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    key_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await api_keys_service.revoke_api_key(session, user.id, key_id)
