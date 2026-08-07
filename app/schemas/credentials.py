import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import LlmProvider


class AddLlmCredentialRequest(BaseModel):
    provider: LlmProvider
    api_key: str = Field(min_length=1, max_length=500, description="Your own API key for this provider.")
    label: str | None = Field(default=None, max_length=255)


class LlmCredentialResponse(BaseModel):
    """Never includes the key itself, encrypted or otherwise -- once
    submitted, a credential can be replaced or deleted, but not read back."""

    id: uuid.UUID
    provider: LlmProvider
    label: str | None
    is_valid: bool
    created_at: datetime
    last_validated_at: datetime | None
