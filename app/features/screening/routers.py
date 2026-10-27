import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.features.auth.services import get_current_user
from app.features.users.models import User
from app.features.projects.services import ProjectServiceDep
from app.features.research.services import ArticleServiceDep
from app.features.research.agent import (
    AIScreeningNotConfiguredError,
    ensure_ai_configured,
    screen_article,
)
from app.features.criteria.models import Criterion
from .models import (
    ScreeningDecision,
    ScreeningDecisionCreate,
    ScreeningStage,
    ScreeningStats,
    DecisionSource,
)
from .services import ScreeningServiceDep
from .flows import batch_ai_screening_flow
from sqlmodel import and_, or_, select

logger = logging.getLogger(__name__)

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


@router.post(
    "/articles/{article_id}/screen-ai",
    response_model=ScreeningDecision,
    status_code=200,
)
async def screen_article_with_ai(
    project_id: int,
    article_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
):
    """Screen a single article using the AI agent.

    This endpoint:
    - Verifies project ownership
    - Fetches the article and active criteria
    - Runs the AI screening agent
    - Returns the screening decision
    """
    # Verify project ownership
    project = verify_project_ownership(project_id, current_user, ps)

    # Fetch article
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")

    # Fetch active criteria
    criteria = session.exec(
        select(Criterion).where(
            Criterion.project_id == project_id, Criterion.is_active.is_(True)
        )
    ).all()

    if not criteria:
        raise HTTPException(
            status_code=400,
            detail="No active criteria found for this project. Please add criteria before screening.",
        )

    # Get review question
    review_question = project.review_question or "No specific review question provided"

    try:
        ensure_ai_configured()
    except AIScreeningNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    # Run AI screening
    try:
        decision = await screen_article(
            article=article,
            criteria=criteria,
            review_question=review_question,
            session=session,
            reviewer_id=None,
        )
        return decision
    except Exception as e:
        logger.exception(
            "AI screening failed for article %s in project %s", article_id, project_id
        )
        raise HTTPException(
            status_code=500, detail="AI screening failed. Please try again later."
        ) from e


@router.get(
    "/articles/{article_id}/ai-decision",
    response_model=ScreeningDecision,
)
def get_ai_decision(
    project_id: int,
    article_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    ps: ProjectServiceDep,
    article_service: ArticleServiceDep,
):
    """Get the latest AI screening decision for an article.

    Returns:
        The most recent AI-generated screening decision, or 404 if none exists.
    """
    # Verify project ownership
    verify_project_ownership(project_id, current_user, ps)

    # Verify article belongs to project
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")

    # Get latest AI decision
    ai_decision = session.exec(
        select(ScreeningDecision)
        .where(
            ScreeningDecision.article_id == article_id,
            ScreeningDecision.source == DecisionSource.ai_agent,
        )
        .order_by(ScreeningDecision.created_at.desc())
    ).first()

    if ai_decision is None:
        raise HTTPException(
            status_code=404, detail="No AI decision found for this article"
        )

    return ai_decision


@router.post("/run-ai")
async def run_batch_ai_screening(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    ps: ProjectServiceDep,
    background_tasks: BackgroundTasks,
    stage: Annotated[ScreeningStage | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
):
    """Run AI screening on multiple articles in the background.

    Args:
        project_id: ID of the project
        stage: Optional screening stage filter (title_abstract or full_text)
        limit: Optional maximum number of articles to screen

    Returns:
        A message indicating screening has started and the number of articles queued
    """
    from app.features.research.models import Article, ArticleStatus

    verify_project_ownership(project_id, current_user, ps)

    has_criteria = session.exec(
        select(Criterion.id)
        .where(Criterion.project_id == project_id, Criterion.is_active.is_(True))
        .limit(1)
    ).first()
    if has_criteria is None:
        raise HTTPException(
            status_code=400,
            detail="No active criteria found for this project. Please add criteria before screening.",
        )

    try:
        ensure_ai_configured()
    except AIScreeningNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    # Eligible: status is 'screening' or 'full_text_retrieved', no AI decision yet
    # for the article's current stage (single NOT EXISTS query), and, for
    # full_text-stage articles, extracted full text is available.
    already_screened = (
        select(ScreeningDecision.id)
        .where(
            ScreeningDecision.article_id == Article.id,
            ScreeningDecision.source == DecisionSource.ai_agent,
            ScreeningDecision.stage == Article.current_stage,
        )
        .exists()
    )
    query = (
        select(Article.id)
        .where(
            Article.project_id == project_id,
            Article.status.in_(
                [ArticleStatus.screening, ArticleStatus.full_text_retrieved]
            ),
            ~already_screened,
            or_(
                Article.current_stage != ScreeningStage.full_text,
                and_(
                    Article.full_text_content.is_not(None),
                    Article.full_text_content != "",
                ),
            ),
        )
        .order_by(Article.id)
    )
    if stage:
        query = query.where(Article.current_stage == stage)
    if limit:
        query = query.limit(limit)

    article_ids = list(session.exec(query).all())
    article_count = len(article_ids)

    if article_count == 0:
        return {
            "message": "No eligible articles to screen",
            "article_count": 0,
        }

    # Schedule the flow with primitive ids only: it opens its own session.
    background_tasks.add_task(
        batch_ai_screening_flow, project_id, article_ids, current_user.id
    )

    return {
        "message": "AI screening started",
        "article_count": article_count,
    }
