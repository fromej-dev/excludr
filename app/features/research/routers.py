from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.features.projects.permissions import OwnerAccess, ViewerAccess
from .models import Article, ArticleStatus, ScreeningStage
from .services import ArticleServiceDep

router = APIRouter(tags=["Articles"], prefix="/projects/{project_id}/articles")


@router.get("", response_model=PaginatedResponse[Article])
def get_articles(
    project_id: int,
    access: ViewerAccess,
    session: SessionDep,
    article_service: ArticleServiceDep,
    fsp: Annotated[FSPManager, Depends()],
    status: Annotated[Optional[ArticleStatus], Query()] = None,
    stage: Annotated[Optional[ScreeningStage], Query()] = None,
):
    """Get all articles for a project with optional filtering."""

    if status:
        query = article_service.get_articles_by_status(project_id, status)
    elif stage:
        query = article_service.get_articles_by_stage(project_id, stage)
    else:
        query = article_service.get_articles_for_project(project_id)

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
