"""Bulk full-text PDF upload: stage, match, then attach on confirmation.

Uploaded PDFs are first stored in a per-project staging directory under
``settings.pdf_storage_path`` (``staging/<project_id>/<upload_id>.pdf``) and
matched to articles (:mod:`.pdf_matching`). Nothing changes on an article until
the owner confirms; confirmed files are moved into the PDF storage directory and
attached like a single manual upload. Staged files left behind are removed after
:data:`STAGING_TTL_SECONDS`.
"""

import logging
import os
import re
import time
from typing import Optional

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.uploads import display_filename, remove_file, save_upload
from app.features.audit import services as audit
from .models import Article, FullTextSource
from .pdf_extraction import extract_text_from_pdf_safe
from .pdf_matching import (
    ArticleIndex,
    Candidate,
    MatchOutcome,
    match_pdf,
    read_fingerprint,
)
from .schemas import (
    PdfAttachItem,
    PdfAttachResult,
    PdfBulkConfirmResponse,
    PdfMatchCandidate,
    PdfMatchResult,
)
from .services import ArticleService

logger = logging.getLogger(__name__)

MAX_FILES_PER_REQUEST = 25
STAGING_TTL_SECONDS = 24 * 3600

_UPLOAD_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def staging_dir(project_id: int) -> str:
    return os.path.join(get_settings().pdf_storage_path, "staging", str(project_id))


def _staged_path(project_id: int, upload_id: str) -> Optional[str]:
    """Path of a staged upload, or None for a malformed id or a missing file."""
    if not _UPLOAD_ID_RE.match(upload_id):
        return None
    path = os.path.join(staging_dir(project_id), f"{upload_id}.pdf")
    return path if os.path.isfile(path) else None


def sweep_staging(project_id: int, now: Optional[float] = None) -> None:
    """Remove this project's staged uploads older than the TTL."""
    directory = staging_dir(project_id)
    if not os.path.isdir(directory):
        return
    cutoff = (now if now is not None else time.time()) - STAGING_TTL_SECONDS
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                remove_file(path)
        except OSError:
            continue


def _candidate_out(candidate: Candidate, index: ArticleIndex) -> PdfMatchCandidate:
    ref = index.refs[candidate.article_id]
    return PdfMatchCandidate(
        article_id=ref.id,
        title=ref.title,
        year=ref.year,
        first_author=ref.first_author,
        has_full_text=ref.has_full_text,
        method=candidate.method,
        confidence=candidate.confidence,
    )


def _result(
    upload_id: str,
    filename: str,
    has_text: bool,
    outcome: MatchOutcome,
    index: ArticleIndex,
) -> PdfMatchResult:
    return PdfMatchResult(
        upload_id=upload_id,
        filename=filename,
        text_extracted=has_text,
        match=_candidate_out(outcome.match, index) if outcome.match else None,
        candidates=[_candidate_out(c, index) for c in outcome.candidates],
    )


async def stage_and_match(
    session: Session, project_id: int, files: list[UploadFile]
) -> list[PdfMatchResult]:
    """Stage each PDF and propose the article it belongs to.

    A file that is rejected (not a PDF, too large, unreadable) is reported with
    an ``error`` and not staged; the other files are unaffected.
    """
    if not files:
        raise HTTPException(status_code=422, detail="No files uploaded")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=422,
            detail=f"Upload at most {MAX_FILES_PER_REQUEST} files per request",
        )

    sweep_staging(project_id)
    articles = session.exec(select(Article).where(Article.project_id == project_id))
    index = ArticleIndex(articles.all())

    results: list[PdfMatchResult] = []
    for file in files:
        filename = display_filename(file)
        path: Optional[str] = None
        try:
            path = await save_upload(
                file,
                staging_dir(project_id),
                {".pdf"},
                magic=b"%PDF-",
                invalid_type_detail="Not a .pdf file",
                invalid_content_detail="Not a PDF (file does not start with %PDF-)",
            )
            fingerprint = await run_in_threadpool(read_fingerprint, path, filename)
            outcome = match_pdf(fingerprint, index)
        except HTTPException as exc:
            results.append(PdfMatchResult(filename=filename, error=str(exc.detail)))
            continue
        except Exception:
            logger.warning("Could not read uploaded PDF %s", filename, exc_info=True)
            if path:
                remove_file(path)
            results.append(
                PdfMatchResult(
                    filename=filename, error="File could not be read as a PDF"
                )
            )
            continue
        finally:
            await file.close()
        upload_id = os.path.splitext(os.path.basename(path))[0]
        results.append(
            _result(upload_id, filename, fingerprint.has_text, outcome, index)
        )
    return results


def _remove_previous_pdf(path: Optional[str]) -> None:
    """Delete a replaced PDF if it lives in the PDF storage directory."""
    if not path:
        return
    storage = os.path.realpath(get_settings().pdf_storage_path)
    real = os.path.realpath(path)
    if os.path.dirname(real) == storage and os.path.isfile(real):
        remove_file(real)


def _attach_one(
    service: ArticleService, project_id: int, item: PdfAttachItem
) -> PdfAttachResult:
    def outcome(status, detail=None, text_extracted=False) -> PdfAttachResult:
        return PdfAttachResult(
            upload_id=item.upload_id,
            article_id=item.article_id,
            status=status,
            detail=detail,
            text_extracted=text_extracted,
        )

    staged = _staged_path(project_id, item.upload_id)
    if staged is None:
        return outcome("error", "Upload not found or expired; upload the file again")
    article = service.get_article_by_id(item.article_id)
    if article is None or article.project_id != project_id:
        return outcome("error", "Article not found")
    if article.full_text_retrieved and not item.replace:
        return outcome("skipped", "Article already has a full text")

    storage = get_settings().pdf_storage_path
    final_path = os.path.join(storage, os.path.basename(staged))
    previous = article.full_text_path
    try:
        os.replace(staged, final_path)
        text = extract_text_from_pdf_safe(final_path)
        service.set_full_text_retrieved(
            article, final_path, text, FullTextSource.manual.value
        )
    except Exception:
        logger.exception("Attaching staged PDF %s failed", item.upload_id)
        service.session.rollback()
        remove_file(final_path)
        return outcome("error", "Failed to attach the PDF")
    if previous and previous != final_path:
        _remove_previous_pdf(previous)
    return outcome("attached", text_extracted=text is not None and bool(text.strip()))


def confirm(
    session: Session,
    project_id: int,
    user_id: int,
    attach: list[PdfAttachItem],
    discard: list[str],
) -> PdfBulkConfirmResponse:
    """Attach the chosen staged PDFs and delete the discarded ones."""
    article_ids = [item.article_id for item in attach]
    if len(set(article_ids)) != len(article_ids):
        raise HTTPException(
            status_code=422, detail="Each article can receive only one PDF"
        )
    upload_ids = [item.upload_id for item in attach]
    if len(set(upload_ids)) != len(upload_ids):
        raise HTTPException(status_code=422, detail="Each upload can be attached once")

    service = ArticleService(session)
    results = [_attach_one(service, project_id, item) for item in attach]
    # Attached files were moved already; skipped or failed ones may be discarded
    for upload_id in discard:
        if path := _staged_path(project_id, upload_id):
            remove_file(path)

    attached = sum(1 for r in results if r.status == "attached")
    if attached:
        audit.record_event(
            session,
            project_id,
            audit.FULLTEXT_PDFS_UPLOADED,
            "project",
            project_id,
            user_id=user_id,
            details={
                "attached": attached,
                "replaced": sum(
                    1
                    for item, r in zip(attach, results, strict=True)
                    if r.status == "attached" and item.replace
                ),
                "article_ids": [
                    r.article_id for r in results if r.status == "attached"
                ],
            },
        )
    return PdfBulkConfirmResponse(attached=attached, results=results)
