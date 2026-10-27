"""Safe handling of user-uploaded files.

Files are streamed to disk in chunks with a hard size limit, stored under a
server-generated name (``<uuid><validated extension>``) and never under the
client-supplied filename.
"""

import logging
import os
import uuid
from collections.abc import Collection

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
_MAX_DISPLAY_NAME = 255


def display_filename(file: UploadFile) -> str:
    """Return a sanitised, length-limited client filename for metadata only.

    Never use the result to build filesystem paths.
    """
    name = os.path.basename((file.filename or "").replace("\\", "/"))
    name = "".join(ch for ch in name if ch.isprintable())
    return name[:_MAX_DISPLAY_NAME] or "upload"


async def save_upload(
    file: UploadFile,
    directory: str,
    allowed_extensions: Collection[str],
    *,
    magic: bytes | None = None,
    invalid_type_detail: str,
    invalid_content_detail: str = "File content does not match its type.",
) -> str:
    """Validate and store an upload, returning the path it was written to.

    Args:
        file: The uploaded file.
        directory: Destination directory (created if missing).
        allowed_extensions: Lower-case extensions including the dot, e.g. ``{".ris"}``.
        magic: Required leading bytes of the file, if any (e.g. ``b"%PDF-"``).
        invalid_type_detail: 400 message when the extension is not allowed.
        invalid_content_detail: 400 message when the magic bytes do not match.

    Raises:
        HTTPException: 400 for a bad extension or content, 413 if the file exceeds
            ``max_upload_mb``. Partially written files are removed.
    """
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail=invalid_type_detail)

    too_large = HTTPException(
        status_code=413,
        detail=f"File too large. Maximum size is {get_settings().max_upload_mb} MB.",
    )
    if file.size is not None and file.size > max_bytes:
        raise too_large

    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{uuid.uuid4()}{extension}")
    written = 0
    try:
        with open(path, "wb") as buffer:
            while chunk := await file.read(_CHUNK_SIZE):
                if magic is not None and written == 0 and not chunk.startswith(magic):
                    raise HTTPException(status_code=400, detail=invalid_content_detail)
                written += len(chunk)
                if written > max_bytes:
                    raise too_large
                buffer.write(chunk)
        if magic is not None and written == 0:
            raise HTTPException(status_code=400, detail=invalid_content_detail)
    except BaseException:
        remove_file(path)
        raise
    return path


def remove_file(path: str) -> None:
    """Delete ``path`` if it exists, logging (not raising) on failure."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Could not remove temporary file %s", path, exc_info=True)
