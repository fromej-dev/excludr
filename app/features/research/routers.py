from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.features.auth.services import get_current_user
from app.features.users.models import User
from app.features.projects.services import ProjectServiceDep
from .models import Article, ArticleStatus, ScreeningStage
from .services import ArticleServiceDep

router = APIRouter(tags=["Articles"], prefix="/projects/{project_id}/articles")


def verify_project_ownership(
    project_id: int, current_user: User, ps: ProjectServiceDep
):
    """Helper to verify project exists and user owns it."""
    project = ps.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the owner of the project"
        )
    return project


@router.get("", response_model=PaginatedResponse[Article])
def get_articles(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
    fsp: Annotated[FSPManager, Depends()],
    status: Annotated[Optional[ArticleStatus], Query()] = None,
    stage: Annotated[Optional[ScreeningStage], Query()] = None,
):
    """Get all articles for a project with optional filtering."""
    verify_project_ownership(project_id, current_user, ps)

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
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    ps: ProjectServiceDep,
):
    """Get article statistics for a project."""
    from sqlmodel import select, func

    verify_project_ownership(project_id, current_user, ps)

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
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
):
    """Get a single article by ID."""
    verify_project_ownership(project_id, current_user, ps)
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.delete("/{article_id}", status_code=204)
def delete_article(
    project_id: int,
    article_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
):
    """Delete an article."""
    verify_project_ownership(project_id, current_user, ps)
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    article_service.delete_article(article)
    return


@router.post("/start-screening")
def start_screening(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
):
    """Move all imported articles to screening status."""
    verify_project_ownership(project_id, current_user, ps)
    count = article_service.start_screening(project_id)
    return {"message": f"Started screening for {count} articles", "count": count}


@router.post("/{article_id}/fulltext/upload")
async def upload_fulltext(
    project_id: int,
    article_id: int,
    file: UploadFile,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
):
    """Upload a full-text PDF for an article."""
    import os
    import shutil
    import uuid
    from app.core.config import get_settings

    verify_project_ownership(project_id, current_user, ps)
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Please upload a .pdf file."
        )

    settings = get_settings()
    pdf_dir = getattr(settings, "pdf_storage_path", "/tmp/pdfs")
    os.makedirs(pdf_dir, exist_ok=True)

    safe_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(pdf_dir, safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        article_service.set_full_text_retrieved(article, file_path)

        return {"message": "Full text uploaded successfully", "path": file_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to upload file") from e
    finally:
        await file.close()
