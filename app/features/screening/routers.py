from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.features.auth.services import get_current_user
from app.features.users.models import User
from app.features.projects.services import ProjectServiceDep
from app.features.research.services import ArticleServiceDep
from .models import (
    ScreeningDecision,
    ScreeningDecisionCreate,
    ScreeningStage,
    ScreeningStats,
)
from .services import ScreeningServiceDep

router = APIRouter(tags=["Screening"], prefix="/projects/{project_id}/screening")


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


@router.get("/stats", response_model=ScreeningStats)
def get_screening_stats(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    ss: ScreeningServiceDep,
):
    """Get screening statistics for a project."""
    verify_project_ownership(project_id, current_user, ps)
    return ss.get_screening_stats(project_id)


@router.get("/next")
def get_next_article(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    ss: ScreeningServiceDep,
    stage: Annotated[ScreeningStage, Query()] = ScreeningStage.title_abstract,
):
    """Get the next article to screen at the given stage."""
    verify_project_ownership(project_id, current_user, ps)
    article = ss.get_next_article_for_screening(project_id, stage)
    if article is None:
        return {"message": "No more articles to screen at this stage", "article": None}
    return {"article": article}


@router.get(
    "/articles/{article_id}/decisions",
    response_model=PaginatedResponse[ScreeningDecision],
)
def get_article_decisions(
    project_id: int,
    article_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
    ss: ScreeningServiceDep,
    fsp: Annotated[FSPManager, Depends()],
):
    """Get all screening decisions for an article."""
    verify_project_ownership(project_id, current_user, ps)
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    query = ss.get_decisions_for_article(article_id)
    return fsp.generate_response(query, session)


@router.post(
    "/articles/{article_id}/decisions",
    response_model=ScreeningDecision,
    status_code=201,
)
def create_decision(
    project_id: int,
    article_id: int,
    data: ScreeningDecisionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
    ss: ScreeningServiceDep,
):
    """Create a screening decision for an article."""
    verify_project_ownership(project_id, current_user, ps)
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")

    # Set reviewer_id for human decisions
    reviewer_id = current_user.id if data.source.value == "human" else None

    decision = ss.create_decision(article_id, data, reviewer_id)

    # Update article status based on decision
    article_service.update_article_status_from_decision(
        article, data.stage, data.decision
    )

    return decision
