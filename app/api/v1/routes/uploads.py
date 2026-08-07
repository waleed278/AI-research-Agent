from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.db.models import User
from app.schemas.uploads import UploadedFileResponse
from app.services.uploads_service import save_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=UploadedFileResponse, status_code=201)
async def upload_file(
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UploadedFileResponse:
    """Uploads happen before a job exists (see `attachment_ids` on
    `POST /research-jobs`) -- this just stores and text-extracts the file
    and returns an id to reference from job creation."""
    file_bytes = await file.read()
    uploaded = await save_upload(
        session,
        user.id,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=file_bytes,
    )
    return UploadedFileResponse(
        id=uploaded.id,
        filename=uploaded.filename,
        content_type=uploaded.content_type,
        size_bytes=uploaded.size_bytes,
        extracted_chars=uploaded.extracted_chars,
        created_at=uploaded.created_at,
    )
