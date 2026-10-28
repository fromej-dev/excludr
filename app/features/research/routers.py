from typing import Annotated, Optional

import os
from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Depends,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlmodel import select
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.core.prefect_config import run_flow_in_background
from app.features.audit import services as audit
from app.features.projects.permissions import OwnerAccess, ViewerAccess
from .models import Article, ArticleStatus, ScreeningStage
from .flows import retrieve_fulltext_flow, schedule_auto_retrieval
from .fulltext_retrieval import eligible_for_retrieval, retrieve_full_text
from . import pdf_bulk_upload
from .schemas import (
    FullTextRetrievalResult,
    PdfBulkConfirmRequest,
    PdfBulkConfirmResponse,
    PdfMatchResult,
    RetrieveFullTextRequest,
    SkipTitleAbstractRequest,
    SkipTitleAbstractResult,
)
from .services import ArticleServiceDep, skip_title_abstract
from app.features.screening.services import ScreeningServiceDep

router = APIRouter(tags=["Articles"], prefix="/projects/{project_id}/articles")


@router.get("", response_model=PaginatedResponse[Article])
def get_articles(
    project_id: int,
    access: ViewerAccess,
    session: SessionDep,
    article_service: ArticleServiceDep,
    fsp: Annotated[FSPManager, Depends()],
    ss: ScreeningServiceDep,
    status: Annotated[Optional[ArticleStatus], Query()] = None,
    stage: Annotated[Optional[ScreeningStage], Query()] = None,
    pending_for_me: Annotated[
        bool,
        Query(
            description="Screening queue: articles at `stage` (default "
            "title_abstract) that the caller has not decided yet"
        ),
    ] = False,
    has_full_text: Annotated[Optional[bool], Query()] = None,
):
    """Get all articles for a project with optional filtering.

    ``pending_for_me`` uses the same rules as ``GET /screening/next``: the article
    must be waiting for screening at ``stage`` (``screening`` status for
    title_abstract, ``full_text_retrieved`` for full_text), not yet decided by the
    caller, and not already covered by enough reviewers in dual-screening mode.
    """

    if pending_for_me:
        if stage == ScreeningStage.completed:
            raise HTTPException(
                status_code=422, detail="pending_for_me needs a screening stage"
            )
        query = ss.pending_articles_query(
            project_id,
            stage or ScreeningStage.title_abstract,
            reviewer_id=access.user.id,
            required_reviewers=access.project.required_reviewers,
        )
    elif status:
        query = article_service.get_articles_by_status(project_id, status)
    elif stage:
        query = article_service.get_articles_by_stage(project_id, stage)
    else:
        query = article_service.get_articles_for_project(project_id)

    if has_full_text is not None:
        query = query.where(Article.full_text_retrieved.is_(has_full_text))

    return fsp.generate_response(query, session)


@router.get("/stats")
def get_article_stats(
    project_id: int,
    access: ViewerAccess,
    session: SessionDep,
):
    """Get article statistics for a project."""
    from sqlmodel import select, func

    # Total count
    total = session.exec(
        select(func.count(Article.id)).where(Article.project_id == project_id)
    ).one()

    # Count by status
    status_counts = session.exec(
        select(Article.status, func.count(Article.id))
        .where(Article.project_id == project_id)
        .group_by(Article.status)
    ).all()

    # Count by stage
    stage_counts = session.exec(
        select(Article.current_stage, func.count(Article.id))
        .where(Article.project_id == project_id)
        .group_by(Article.current_stage)
    ).all()

    return {
        "total": total,
        "by_status": {s.value: c for s, c in status_counts},
        "by_stage": {s.value: c for s, c in stage_counts},
    }


@router.post("/fulltext/bulk/match", response_model=list[PdfMatchResult])
async def bulk_pdf_match(
    project_id: int,
    files: list[UploadFile],
    access: OwnerAccess,
    session: SessionDep,
):
    """Stage full-text PDFs and propose the article each one belongs to.

    Nothing is attached yet: confirm the matches with ``/fulltext/bulk/confirm``.
    Matching uses the DOI/PMID/PMCID in the PDF metadata, filename or first pages,
    then the article title (confirmed by first author and year). Files that are
    not PDFs are reported per file. Staged files expire after 24 hours.
    """
    return await pdf_bulk_upload.stage_and_match(session, project_id, files)


@router.post("/fulltext/bulk/confirm", response_model=PdfBulkConfirmResponse)
def bulk_pdf_confirm(
    project_id: int,
    body: PdfBulkConfirmRequest,
    access: OwnerAccess,
    session: SessionDep,
):
    """Attach staged PDFs to articles and discard the rest.

    An article that already has a full text is skipped unless ``replace`` is set.
    """
    return pdf_bulk_upload.confirm(
        session, project_id, access.user.id, body.attach, body.discard
    )


@router.get("/{article_id}", response_model=Article)
def get_article(
    project_id: int,
    article_id: int,
    access: ViewerAccess,
    article_service: ArticleServiceDep,
):
    """Get a single article by ID."""
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.delete("/{article_id}", status_code=204)
def delete_article(
    project_id: int,
    article_id: int,
    access: OwnerAccess,
    article_service: ArticleServiceDep,
):
    """Delete an article."""
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    article_service.delete_article(article)
    return


@router.post("/start-screening")
def start_screening(
    project_id: int,
    access: OwnerAccess,
    article_service: ArticleServiceDep,
):
    """Move all imported articles to screening status."""
    count = article_service.start_screening(project_id)
    return {"message": f"Started screening for {count} articles", "count": count}


@router.post("/skip-title-abstract", response_model=SkipTitleAbstractResult)
def skip_title_abstract_bulk(
    project_id: int,
    access: OwnerAccess,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    body: Optional[SkipTitleAbstractRequest] = None,
):
    """Send articles waiting for title/abstract screening straight to full text.

    For records that already passed title/abstract screening elsewhere. Without
    ``article_ids`` every article still waiting for title/abstract moves; with
    ids, only those among them. Articles past title/abstract are left alone.
    Earlier title/abstract votes are kept but no longer count. Full-text
    retrieval starts for the moved articles.
    """
    query = select(Article).where(
        Article.project_id == project_id,
        Article.current_stage == ScreeningStage.title_abstract,
    )
    if body is not None and body.article_ids is not None:
        query = query.where(Article.id.in_(body.article_ids))
    articles = session.exec(query.order_by(Article.id)).all()
    moved = [a for a in articles if skip_title_abstract(a)]
    if not moved:
        return SkipTitleAbstractResult(moved=0, retrieval_queued=0)
    session.add_all(moved)
    session.commit()
    audit.record_event(
        session,
        project_id,
        audit.TITLE_ABSTRACT_SKIPPED,
        "project",
        project_id,
        access.user.id,
        {"count": len(moved), "article_ids": [a.id for a in moved]},
    )
    queued = schedule_auto_retrieval(background_tasks, moved, access.user.id)
    return SkipTitleAbstractResult(moved=len(moved), retrieval_queued=len(queued))


@router.post("/retrieve-fulltext")
def retrieve_fulltext_bulk(
    project_id: int,
    access: OwnerAccess,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    body: Optional[RetrieveFullTextRequest] = None,
):
    """Start background full-text retrieval (Unpaywall, PMC, Europe PMC).

    Without ``article_ids`` every article awaiting full text that has none yet is
    processed; with ids, only those among them that are eligible. Progress is
    broadcast on the project websocket room (``fulltext_progress`` /
    ``fulltext_complete``). Failures stay in ``awaiting_full_text`` with the
    error stored on the article.
    """
    query = select(Article.id).where(
        Article.project_id == project_id,
        Article.status == ArticleStatus.awaiting_full_text,
        Article.full_text_retrieved.is_(False),
    )
    if body is not None and body.article_ids is not None:
        query = query.where(Article.id.in_(body.article_ids))
    article_ids = list(session.exec(query.order_by(Article.id)).all())
    if not article_ids:
        return {"message": "No eligible articles", "count": 0}

    # Primitive ids only: the flow opens its own session.
    background_tasks.add_task(
        run_flow_in_background,
        retrieve_fulltext_flow,
        project_id,
        article_ids,
        access.user.id,
    )
    return {"message": "Full-text retrieval started", "count": len(article_ids)}


@router.post("/{article_id}/retrieve-fulltext", response_model=FullTextRetrievalResult)
async def retrieve_fulltext_single(
    project_id: int,
    article_id: int,
    access: OwnerAccess,
    session: SessionDep,
    article_service: ArticleServiceDep,
):
    """Retrieve one article's full text now and report which sources were tried."""
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    if not eligible_for_retrieval(article):
        raise HTTPException(
            status_code=409,
            detail="Article is not awaiting full text or already has one",
        )
    return await retrieve_full_text(session, article)


@router.get("/{article_id}/fulltext/pdf")
def get_fulltext_pdf(
    project_id: int,
    article_id: int,
    access: ViewerAccess,
    article_service: ArticleServiceDep,
):
    """Serve the stored full-text PDF inline."""
    from app.core.config import get_settings

    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    if not article.full_text_path:
        raise HTTPException(status_code=404, detail="No PDF stored for this article")

    storage = os.path.realpath(get_settings().pdf_storage_path)
    path = os.path.realpath(article.full_text_path)
    if os.path.commonpath([storage, path]) != storage or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="No PDF stored for this article")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"article-{article.id}.pdf",
        content_disposition_type="inline",
    )


@router.post("/{article_id}/fulltext/upload")
async def upload_fulltext(
    project_id: int,
    article_id: int,
    file: UploadFile,
    access: OwnerAccess,
    article_service: ArticleServiceDep,
):
    """Upload a full-text PDF for an article and extract text content."""
    from app.core.config import get_settings
    from app.core.uploads import remove_file, save_upload
    from .pdf_extraction import extract_text_from_pdf_safe

    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")

    file_path: str | None = None
    try:
        # Validates extension, %PDF- magic bytes and size; stored as <uuid>.pdf
        file_path = await save_upload(
            file,
            get_settings().pdf_storage_path,
            {".pdf"},
            magic=b"%PDF-",
            invalid_type_detail="Invalid file type. Please upload a .pdf file.",
            invalid_content_detail="Invalid PDF: file does not start with %PDF-.",
        )

        # Extract text from the PDF
        extracted_text = extract_text_from_pdf_safe(file_path)

        # Update article with file path and extracted text
        article_service.set_full_text_retrieved(article, file_path, extracted_text)

        return {
            "message": "Full text uploaded successfully",
            "text_extracted": extracted_text is not None,
            "text_length": len(extracted_text) if extracted_text else 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        # Clean up the file if something went wrong
        if file_path:
            remove_file(file_path)
        raise HTTPException(status_code=500, detail="Failed to upload file") from e
    finally:
        await file.close()
