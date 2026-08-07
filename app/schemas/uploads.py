import uuid
from datetime import datetime

from pydantic import BaseModel


class UploadedFileResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    extracted_chars: int
    created_at: datetime
