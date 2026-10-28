import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.core.prefect_config import run_flow_in_background
from app.features.audit import services as audit
from app.features.billing import services as billing
from app.features.projects.models import ProjectRole
from app.features.projects.permissions import (
    OwnerAccess,
    ReviewerAccess,
    ViewerAccess,
)
from app.features.research.flows import schedule_auto_retrieval
from app.features.research.models import ArticleStatus
from app.features.research.services import ArticleServiceDep
from app.features.research.agent import (
    AIScreeningNotConfiguredError,
    ensure_ai_configured,
    screen_article,
)
from app.features.criteria.models import Criterion
from app.features.criteria.services import CriterionServiceDep
from .schemas import (
    AIDisagreementRead,
    AgreementRead,
    ConflictRead,
    ResolveRequest,
    RunAIRequest,
)
from .models import (
    ScreeningDecision,
    ScreeningDecisionCreate,
    ScreeningStage,
    ScreeningStats,
    DecisionSource,
)
from .services import ScreeningError, ScreeningServiceDep, ScreeningService
from .flows import batch_ai_screening_flow
from . import inflight
from sqlmodel import and_, or_, select

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Screening"], prefix="/projects/{project_id}/screening")


@router.get("/stats", response_model=ScreeningStats)
def get_screening_stats(
    project_id: int,
    access: ViewerAccess,
    ss: ScreeningServiceDep,
):
    """Get screening statistics for a project."""
    return ss.get_screening_stats(project_id)


@router.get("/stale-ai-decisions")
def get_stale_ai_decisions(
    project_id: int,
    access: ViewerAccess,
    ss: ScreeningServiceDep,
    cs: CriterionServiceDep,
):
    """List articles whose latest AI decision used outdated criteria.

    An AI decision is stale when its criteria snapshot (``{code: version}``)
    differs from the project's current active criteria.
    """
    ids = ss.get_stale_ai_article_ids(project_id, cs.get_active_snapshot(project_id))
    return {"article_ids": ids, "count": len(ids)}


@router.get("/next")
def get_next_article(
    project_id: int,
    access: ReviewerAccess,
    ss: ScreeningServiceDep,
    stage: Annotated[ScreeningStage, Query()] = ScreeningStage.title_abstract,
):
    """Get the next article this reviewer has not yet screened at the given stage.

    The response never includes other reviewers' decisions (blind screening).
    """
    article = ss.get_next_article_for_screening(
        project_id,
        stage,
        reviewer_id=access.user.id,
        required_reviewers=access.project.required_reviewers,
    )
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
    access: ViewerAccess,
    session: SessionDep,
    article_service: ArticleServiceDep,
    ss: ScreeningServiceDep,
    fsp: Annotated[FSPManager, Depends()],
):
    """Get all screening decisions for an article."""
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    # With dual screening, non-owners must not see other reviewers' decisions
    # while the article is still being screened at that stage.
    blind = access.project.required_reviewers >= 2 and access.role != ProjectRole.owner
    query = ss.get_decisions_for_article(
        article_id,
        blind_for_user_id=access.user.id if blind else None,
        blind_stage=article.current_stage,
    )
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
    access: ReviewerAccess,
    session: SessionDep,
    article_service: ArticleServiceDep,
    ss: ScreeningServiceDep,
    background_tasks: BackgroundTasks,
):
    """Create the caller's human screening decision for an article.

    A reviewer has one effective decision per article and stage: posting again
    supersedes the earlier one (the old row stays as history; only the latest counts).
    The article advances only once the project's required
    number of reviewers have decided and agree; otherwise it is left in conflict
    for the owner to resolve. Decisions with ``source=ai_agent`` are owner-only,
    are stored as-is and never affect article status. An article that moves on
    to wait for its full text gets full-text retrieval started in the background.
    """
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")

    if data.source != DecisionSource.human:
        if access.role != ProjectRole.owner:
            raise HTTPException(
                status_code=403, detail="Only the owner can record AI decisions"
            )
        return ss.create_decision(article_id, data, None)

    was_waiting = article.status == ArticleStatus.awaiting_full_text
    try:
        decision, replaced = ss.submit_human_decision(
            access.project, article, data, access.user.id
        )
    except ScreeningError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if not was_waiting:
        schedule_auto_retrieval(background_tasks, [article], access.user.id)
    audit.record_event(
        session,
        project_id,
        audit.DECISION_UPDATED if replaced else audit.DECISION_CREATED,
        "decision",
        decision.id,
        access.user.id,
        {
            "article_id": article_id,
            "stage": data.stage.value,
            "decision": data.decision.value,
        },
    )
    session.refresh(decision)  # the audit commit expired it
    return decision


@router.post(
    "/articles/{article_id}/resolve",
    response_model=ScreeningDecision,
)
def resolve_conflict(
    project_id: int,
    article_id: int,
    data: ResolveRequest,
    access: OwnerAccess,
    session: SessionDep,
    article_service: ArticleServiceDep,
    ss: ScreeningServiceDep,
    background_tasks: BackgroundTasks,
):
    """Resolve a reviewer conflict with the owner's final decision (owner only)."""
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")
    was_waiting = article.status == ArticleStatus.awaiting_full_text
    try:
        decision = ss.resolve_conflict(
            access.project,
            article,
            access.user.id,
            data.decision,
            data.reason,
            data.primary_exclusion_reason,
        )
    except ScreeningError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if not was_waiting:
        schedule_auto_retrieval(background_tasks, [article], access.user.id)
    audit.record_event(
        session,
        project_id,
        audit.DECISION_RESOLVED,
        "decision",
        decision.id,
        access.user.id,
        {
            "article_id": article_id,
            "stage": decision.stage.value,
            "decision": decision.decision.value,
            "reason": data.reason,
        },
    )
    session.refresh(decision)
    return decision


@router.get("/conflicts", response_model=list[ConflictRead])
def get_conflicts(access: OwnerAccess, ss: ScreeningServiceDep):
    """List articles whose reviewers disagree, with each reviewer's decision (owner only)."""
    return ss.list_conflicts(access.project)


@router.get("/ai-disagreements", response_model=list[AIDisagreementRead])
def get_ai_disagreements(
    access: OwnerAccess,
    ss: ScreeningServiceDep,
    stage: Annotated[ScreeningStage | None, Query()] = None,
):
    """Articles where the latest AI include/exclude differs from the human outcome."""
    if stage == ScreeningStage.completed:
        raise HTTPException(status_code=400, detail="Invalid stage")
    return ss.list_ai_disagreements(access.project, stage)


@router.get("/agreement", response_model=AgreementRead)
def get_agreement(
    access: OwnerAccess,
    ss: ScreeningServiceDep,
    stage: Annotated[ScreeningStage, Query()] = ScreeningStage.title_abstract,
):
    """Cohen's kappa / percent agreement between reviewers, and AI-vs-human metrics."""
    if stage == ScreeningStage.completed:
        raise HTTPException(
            status_code=400, detail="Stage must be title_abstract or full_text"
        )
    return ss.get_agreement(access.project, stage)


@router.post(
    "/articles/{article_id}/screen-ai",
    response_model=ScreeningDecision,
    status_code=200,
)
async def screen_article_with_ai(
    project_id: int,
    article_id: int,
    access: ReviewerAccess,
    session: SessionDep,
    article_service: ArticleServiceDep,
):
    """Screen a single article using the AI agent.

    This endpoint:
    - Verifies the caller has the reviewer role
    - Fetches the article and active criteria
    - Runs the AI screening agent
    - Returns the screening decision
    """
    project = access.project

    # Fetch article
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")

    # Without extracted text the agent would only see the title and abstract and
    # record a title/abstract verdict for an article that is at full text.
    if (
        article.current_stage == ScreeningStage.full_text
        and not (article.full_text_content or "").strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="This article has no full text yet. Retrieve or upload it before screening with AI.",
        )

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

    try:
        billing.check_can_ai_screen(session, project, article)
    except billing.BillingError as e:
        raise HTTPException(status_code=402, detail=str(e)) from e

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
    access: ViewerAccess,
    session: SessionDep,
    article_service: ArticleServiceDep,
    stage: Annotated[ScreeningStage | None, Query()] = None,
):
    """Get the latest AI screening decision for an article.

    Args:
        stage: Only consider AI decisions made at this stage. The screening view
            passes its stage so a title/abstract verdict is never shown as the
            AI's opinion on the full text.

    Returns:
        The most recent AI-generated screening decision, or 404 if none exists.
    """
    # Verify article belongs to project
    article = article_service.get_article_by_id(article_id)
    if article is None or article.project_id != project_id:
        raise HTTPException(status_code=404, detail="Article not found")

    # Get latest AI decision
    query = select(ScreeningDecision).where(
        ScreeningDecision.article_id == article_id,
        ScreeningDecision.source == DecisionSource.ai_agent,
    )
    if stage is not None:
        query = query.where(ScreeningDecision.stage == stage)
    ai_decision = session.exec(
        query.order_by(ScreeningDecision.created_at.desc(), ScreeningDecision.id.desc())
    ).first()

    if ai_decision is None:
        raise HTTPException(
            status_code=404, detail="No AI decision found for this article"
        )

    return ai_decision


async def _run_batch_and_release(
    keys: list[inflight.InFlightKey], flow_fn, *args
) -> None:
    """Run the batch flow, then free its in-flight claims (also when it fails)."""
    try:
        await run_flow_in_background(flow_fn, *args)
    finally:
        inflight.release(keys)


@router.post("/run-ai")
async def run_batch_ai_screening(
    project_id: int,
    access: ReviewerAccess,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    stage: Annotated[ScreeningStage | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
    rescreen_stale: Annotated[bool, Query()] = False,
    body: RunAIRequest | None = None,
):
    """Run AI screening on multiple articles in the background.

    Args:
        project_id: ID of the project
        stage: Optional screening stage filter (title_abstract or full_text)
        limit: Optional maximum number of articles to screen
        rescreen_stale: Also screen articles whose latest AI decision was made
            against criteria that have since changed
        body: Optional ``{"article_ids": [...]}`` (at most 10) to screen only that
            subset; ids outside the project or not eligible are skipped silently

    Articles already queued or being screened by another running batch (see
    ``inflight``) are never queued twice.

    Returns:
        A message, the number of articles queued and their ids
    """
    from app.features.research.models import Article, ArticleStatus

    requested_ids = (
        list(dict.fromkeys(body.article_ids)) if body and body.article_ids else None
    )

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
    eligible_unscreened = ~already_screened
    if rescreen_stale:
        stale_ids = ScreeningService(session).get_stale_ai_article_ids(
            project_id,
            {
                c.code: c.version
                for c in session.exec(
                    select(Criterion).where(
                        Criterion.project_id == project_id,
                        Criterion.is_active.is_(True),
                    )
                )
            },
        )
        if stale_ids:
            eligible_unscreened = or_(eligible_unscreened, Article.id.in_(stale_ids))
    query = (
        select(Article.id, Article.current_stage)
        .where(
            Article.project_id == project_id,
            Article.status.in_(
                [ArticleStatus.screening, ArticleStatus.full_text_retrieved]
            ),
            eligible_unscreened,
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
    if requested_ids is not None:
        query = query.where(Article.id.in_(requested_ids))
    if stage:
        query = query.where(Article.current_stage == stage)
    if limit:
        query = query.limit(limit)

    candidates = list(session.exec(query).all())
    # Only queue what the plan's AI allowance still covers.
    skipped = 0
    if candidates:
        try:
            allowed, skipped = billing.split_by_allowance(
                session, access.project, [article_id for article_id, _ in candidates]
            )
        except billing.BillingError as e:
            raise HTTPException(status_code=402, detail=str(e)) from e
        allowed_ids = set(allowed)
        candidates = [c for c in candidates if c[0] in allowed_ids]
    # Skip articles another running batch already has queued at this stage
    keys = inflight.claim(
        (project_id, article_id, ScreeningStage(article_stage).value)
        for article_id, article_stage in candidates
    )
    article_ids = [article_id for _, article_id, _ in keys]
    article_count = len(article_ids)

    if article_count == 0:
        return {
            "message": "No eligible articles to screen",
            "article_count": 0,
            "article_ids": [],
            "skipped_over_allowance": skipped,
        }

    try:
        audit.record_event(
            session,
            project_id,
            audit.AI_BATCH_STARTED,
            "ai_batch",
            None,
            access.user.id,
            {
                "article_count": article_count,
                "stage": stage.value if stage else None,
                "rescreen_stale": rescreen_stale,
                "skipped_over_allowance": skipped,
                **({"article_ids": article_ids} if requested_ids is not None else {}),
            },
        )

        # Schedule the flow with primitive ids only: it opens its own session.
        # A caller-picked subset is "targeted" (its events are tagged for the UI).
        flow_args: tuple = (project_id, article_ids, access.user.id)
        if requested_ids is not None:
            flow_args += (True,)
        background_tasks.add_task(
            _run_batch_and_release, keys, batch_ai_screening_flow, *flow_args
        )
    except BaseException:
        inflight.release(keys)
        raise

    return {
        "message": "AI screening started",
        "article_count": article_count,
        "article_ids": article_ids,
        "skipped_over_allowance": skipped,
    }
