"""Prefect flows for research (article) background work."""

import logging
from typing import Any

from fastapi import BackgroundTasks
from prefect import flow
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import engine
from app.core.prefect_config import run_flow_in_background
from app.features.audit import services as audit
from app.features.websocket.schemas import NotificationLevel
from app.features.websocket.services import NotificationService
from .fulltext_retrieval import (
    build_client,
    eligible_for_retrieval,
    record_failure,
    retrieve_full_text,
)
from .models import Article

logger = logging.getLogger(__name__)


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
        logger.exception("Failed to send full-text retrieval notification")


def _audit(project_id: int, action: str, user_id: int, details: dict[str, Any]) -> None:
    try:
        with Session(engine) as audit_session:
            audit.record_event(
                audit_session,
                project_id,
                action,
                "fulltext_batch",
                None,
                user_id,
                details,
            )
    except Exception:
        logger.exception("Failed to record full-text audit event %s", action)


@flow(name="retrieve_fulltext", log_prints=True)
async def retrieve_fulltext_flow(
    project_id: int, article_ids: list[int], user_id: int, trigger: str = "manual"
) -> dict[str, int]:
    """Retrieve open-access full texts for many articles.

    Only primitive ids cross the process boundary; the flow opens its own
    database session. A failure for one article never stops the batch: the
    article stays in ``awaiting_full_text`` with the error recorded on it.

    Progress (``fulltext_progress``) is pushed to the ``project_{project_id}``
    room after every article and ``fulltext_complete`` goes to the project room
    and the requesting user, mirroring the AI screening batch messages.
    Automatic runs (``trigger="auto"``) only tell the project room, marked
    ``auto`` so clients can refresh without showing a notification.

    An article that is no longer eligible when its turn comes (a full text was
    uploaded or retrieved meanwhile, or it moved on) is skipped and not counted
    as a failure.

    Returns:
        ``{"total", "retrieved", "failed"}`` counts.
    """
    total = len(article_ids)
    retrieved = 0
    failed = 0
    auto = trigger == "auto"
    _audit(
        project_id,
        audit.FULLTEXT_BATCH_STARTED,
        user_id,
        {"article_count": total, "trigger": trigger},
    )

    with Session(engine) as session:
        async with build_client() as client:
            for article_id in article_ids:
                data: dict[str, Any] = {
                    "project_id": project_id,
                    "article_id": article_id,
                }
                try:
                    article = session.get(Article, article_id)
                    if article is None or article.project_id != project_id:
                        raise LookupError(f"Article {article_id} not found in project")
                    if not eligible_for_retrieval(article):
                        total -= 1
                        continue
                    result = await retrieve_full_text(session, article, client)
                    data.update(
                        type="fulltext_progress",
                        success=result.retrieved,
                        source=result.source,
                        error=result.error,
                    )
                    if result.retrieved:
                        retrieved += 1
                        level = NotificationLevel.INFO
                    else:
                        failed += 1
                        level = NotificationLevel.WARNING
                except Exception as exc:
                    logger.exception(
                        "Full-text retrieval failed for article %s in project %s",
                        article_id,
                        project_id,
                    )
                    if isinstance(exc, SQLAlchemyError):
                        session.rollback()
                    failed += 1
                    error = "Full-text retrieval failed"
                    try:
                        found = session.get(Article, article_id)
                        if found is not None and found.project_id == project_id:
                            record_failure(session, found, error)
                    except Exception:
                        logger.exception("Could not record retrieval error")
                        session.rollback()
                    data.update(
                        type="fulltext_progress",
                        success=False,
                        source=None,
                        error=error,
                    )
                    level = NotificationLevel.WARNING

                data.update(retrieved=retrieved, errors=failed, total=total, auto=auto)
                await _notify(
                    project_id,
                    f"Full-text retrieval progress: {retrieved + failed}/{total}",
                    data,
                    level,
                )

    summary = {"total": total, "retrieved": retrieved, "failed": failed}
    _audit(
        project_id,
        audit.FULLTEXT_BATCH_FINISHED,
        user_id,
        {**summary, "trigger": trigger},
    )
    await _notify(
        project_id,
        f"Full-text retrieval complete: {retrieved} retrieved, {failed} failed",
        {
            "type": "fulltext_complete",
            "project_id": project_id,
            "retrieved": retrieved,
            "errors": failed,
            "auto": auto,
            **summary,
        },
        NotificationLevel.WARNING if failed else NotificationLevel.SUCCESS,
        user_id=None if auto else user_id,
    )
    return summary


def schedule_auto_retrieval(
    background_tasks: BackgroundTasks,
    articles: list[Article],
    user_id: int,
) -> list[int]:
    """Queue full-text retrieval for articles that just started waiting for one.

    Called after a screening decision moved articles to ``awaiting_full_text``;
    does nothing when ``fulltext_auto_retrieval`` is off. ``articles`` must
    belong to one project. Returns the ids that were queued.
    """
    if not get_settings().fulltext_auto_retrieval:
        return []
    eligible = [a for a in articles if eligible_for_retrieval(a)]
    if not eligible:
        return []
    article_ids = [a.id for a in eligible]
    # Primitive ids only: the flow opens its own session.
    background_tasks.add_task(
        run_flow_in_background,
        retrieve_fulltext_flow,
        eligible[0].project_id,
        article_ids,
        user_id,
        "auto",
    )
    return article_ids
