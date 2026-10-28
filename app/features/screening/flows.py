"""Prefect flows for AI screening background work."""

import logging
from typing import Any

from prefect import flow
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.core.database import engine
from app.features.ai_usage.models import AIActivity
from app.features.audit import services as audit
from app.features.billing import services as billing
from app.features.criteria.models import Criterion
from app.features.projects.models import Project
from app.features.research.agent import screen_article
from app.features.research.models import Article
from app.features.websocket.schemas import NotificationLevel
from app.features.websocket.services import NotificationService

logger = logging.getLogger(__name__)

DEFAULT_REVIEW_QUESTION = "No specific review question provided"


async def _notify(
    project_id: int,
    message: str,
    data: dict[str, Any],
    level: NotificationLevel = NotificationLevel.INFO,
    user_id: int | None = None,
) -> None:
    """Send a progress notification; never let a websocket problem break the batch."""
    try:
        await NotificationService.notify_room(
            room_name=f"project_{project_id}",
            message=message,
            level=level,
            data=data,
        )
        if user_id is not None:
            await NotificationService.notify_user_in_room(
                user_id=user_id, message=message, level=level, data=data
            )
    except Exception:
        logger.exception("Failed to send AI screening notification")


@flow(name="batch_ai_screening", log_prints=True)
async def batch_ai_screening_flow(
    project_id: int, article_ids: list[int], user_id: int, targeted: bool = False
) -> dict[str, int]:
    """Screen many articles with the AI agent, isolating per-article failures.

    Only primitive ids cross the process boundary; the flow opens its own database
    session and re-loads the project, criteria and articles itself.

    Progress is pushed to the ``project_{project_id}`` websocket room after every
    article, and a completion message goes to the project room and to the
    requesting user's personal room.

    Args:
        project_id: Project whose articles are screened.
        article_ids: Articles to screen, in order.
        user_id: User who started the batch (receives the completion message).
        targeted: The caller picked these articles (the screening view's lookahead)
            rather than "everything eligible"; events carry ``targeted: true`` so the
            UI can keep such small batches out of the project-wide batch progress.

    Returns:
        ``{"total", "screened", "errors", "skipped"}`` counts.
    """
    total = len(article_ids)
    screened = 0
    errors = 0
    skipped = 0  # refused by the plan (allowance used up, or project read-only)
    activity = (
        AIActivity.screening_lookahead if targeted else AIActivity.screening_batch
    )

    with Session(engine) as session:
        project = session.get(Project, project_id)
        criteria = list(
            session.exec(
                select(Criterion).where(
                    Criterion.project_id == project_id,
                    Criterion.is_active.is_(True),
                )
            ).all()
        )
        review_question = (
            project.review_question if project and project.review_question else None
        ) or DEFAULT_REVIEW_QUESTION

        for article_id in article_ids:
            data: dict[str, Any] = {"project_id": project_id, "article_id": article_id}
            if targeted:
                data["targeted"] = True
            try:
                article = session.get(Article, article_id)
                if article is None or article.project_id != project_id:
                    raise LookupError(f"Article {article_id} not found in project")
                if not criteria:
                    raise LookupError("No active criteria")
                if project is not None:
                    billing.check_can_ai_screen(session, project, article)
                decision = await screen_article(
                    article=article,
                    criteria=criteria,
                    review_question=review_question,
                    session=session,
                    reviewer_id=None,
                    activity=activity,
                    triggered_by=user_id,
                )
                screened += 1
                data.update(
                    type="ai_screening_progress",
                    decision=decision.decision.value,
                    confidence=decision.confidence_score,
                )
                level = NotificationLevel.INFO
            except billing.BillingError as exc:
                skipped += 1
                data.update(type="ai_screening_skipped", error=str(exc))
                level = NotificationLevel.WARNING
            except Exception as exc:
                logger.exception(
                    "AI screening failed for article %s in project %s",
                    article_id,
                    project_id,
                )
                if isinstance(exc, SQLAlchemyError):
                    session.rollback()  # session unusable until rolled back
                errors += 1
                data.update(type="ai_screening_error", error="AI screening failed")
                level = NotificationLevel.WARNING

            data.update(screened=screened, errors=errors, skipped=skipped, total=total)
            await _notify(
                project_id,
                f"AI screening progress: {screened + errors + skipped}/{total}",
                data,
                level,
            )

    summary = {
        "total": total,
        "screened": screened,
        "errors": errors,
        "skipped": skipped,
    }
    try:
        with Session(engine) as audit_session:
            audit.record_event(
                audit_session,
                project_id,
                audit.AI_BATCH_FINISHED,
                "ai_batch",
                None,
                user_id,
                summary,
            )
    except Exception:
        logger.exception("Failed to record AI batch audit event")
    await _notify(
        project_id,
        f"AI screening complete: {screened} screened, {errors} failed"
        + (f", {skipped} over the plan's allowance" if skipped else ""),
        {
            "type": "ai_screening_complete",
            "project_id": project_id,
            **({"targeted": True, "article_ids": article_ids} if targeted else {}),
            **summary,
        },
        NotificationLevel.WARNING if errors or skipped else NotificationLevel.SUCCESS,
        user_id=user_id,
    )
    return summary
