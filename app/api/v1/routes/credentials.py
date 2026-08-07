import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.db.models import LlmCredential, User
from app.schemas.credentials import AddLlmCredentialRequest, LlmCredentialResponse
from app.services import credentials_service

router = APIRouter(prefix="/me/llm-credentials", tags=["llm-credentials"])


def _to_response(credential: LlmCredential) -> LlmCredentialResponse:
    return LlmCredentialResponse(
        id=credential.id,
        provider=credential.provider,
        label=credential.label,
        is_valid=credential.is_valid,
        created_at=credential.created_at,
        last_validated_at=credential.last_validated_at,
    )


@router.post("", response_model=LlmCredentialResponse, status_code=201)
async def add_credential(
    body: AddLlmCredentialRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> LlmCredentialResponse:
    credential = await credentials_service.add_credential(session, user.id, body)
    return _to_response(credential)


@router.get("", response_model=list[LlmCredentialResponse])
async def list_credentials(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
) -> list[LlmCredentialResponse]:
    credentials = await credentials_service.list_credentials(session, user.id)
    return [_to_response(c) for c in credentials]


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await credentials_service.delete_credential(session, user.id, credential_id)
