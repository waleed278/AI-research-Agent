import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    name: str = Field(
        min_length=1, max_length=255, description="A label to help you remember what this key is for."
    )


class ApiKeyCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    raw_key: str = Field(description="Shown only once -- store it now, it cannot be retrieved again.")
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
