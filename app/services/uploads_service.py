import io
import uuid
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidRequestError
from app.core.logging import get_logger
from app.db.models import UploadedFile
from app.db.repositories import UploadedFileRepository

logger = get_logger(__name__)


def _validate_upload(filename: str, size_bytes: int, settings: Settings) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in settings.allowed_upload_extensions:
        allowed = ", ".join(settings.allowed_upload_extensions)
        raise InvalidRequestError(f"Unsupported file type '{extension}'. Allowed: {allowed}")
    if size_bytes > settings.max_upload_bytes:
        max_mb = settings.max_upload_bytes / (1024 * 1024)
        raise InvalidRequestError(f"File is too large ({size_bytes} bytes). Max is {max_mb:.0f} MB.")
    return extension


def _extract_text(file_bytes: bytes, extension: str) -> str:
    if extension == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:  # noqa: BLE001 - a malformed/encrypted PDF shouldn't fail the whole upload
            logger.warning("pdf_text_extraction_failed", exc_info=True)
            return ""
    # .txt / .md / .csv: decode leniently -- an upload with a stray non-UTF-8
    # byte shouldn't hard-fail; replace it and keep the rest of the content.
    return file_bytes.decode("utf-8", errors="replace")


async def save_upload(
    session: AsyncSession,
    user_id: uuid.UUID,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    settings: Settings | None = None,
) -> UploadedFile:
    settings = settings or get_settings()
    extension = _validate_upload(filename, len(file_bytes), settings)

    extracted_text = _extract_text(file_bytes, extension)[: settings.max_extracted_chars_per_file]

    # Generated up front (rather than left to the DB layer's default) so the
    # same id names both the DB row and the on-disk file.
    upload_id = uuid.uuid4()
    user_dir = Path(settings.upload_dir) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    storage_path = user_dir / f"{upload_id}_{filename}"
    storage_path.write_bytes(file_bytes)

    return await UploadedFileRepository(session).create(
        upload_id=upload_id,
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(file_bytes),
        storage_path=str(storage_path),
        extracted_text=extracted_text,
    )
