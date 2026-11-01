"""Stopping rule for prioritized title/abstract screening (streak, apply, reopen).

The streak is "settled title/abstract excludes since the last thing that could
signal a relevant record", over the project's human title/abstract decisions only
(AI decisions, full-text decisions, records that skipped title/abstract and
records closed by the rule are ignored). Decision ids give the order.

- **Window.** Only decisions made at or after ``counting_since`` count: the later of
  ``Project.prioritized_screening_enabled_at`` and ``Project.stopping_rule_applied_at``.
  So applying the rule restarts the count (a later import needs a fresh streak, or
  ``force``), and reopening clears ``stopping_rule_applied_at`` (an undo).
- **Reset events.** Every *current* vote (each reviewer's latest, non-resolution) and
  every owner resolution that is ``include`` or ``uncertain``. That covers settled
  includes, uncertain votes, conflicts, and (dual screening) an include vote that
  still waits for the second reviewer. A superseded include/uncertain vote no
  longer resets.
- **Exclude events.** Articles whose title/abstract stage settled as an exclude
  (excluded, completed, no human full-text decision), positioned at the id of the
  decision that settled them. Single votes in dual screening add nothing until the
  article settles ("agreed outcomes, not votes").

The streak is the number of exclude events after the last reset. It depends only on
decisions, not on the current ``required_reviewers``, so a settings change cannot
rewrite it. Approximations: when ``required_reviewers`` drops from 2 to 1, articles
settle at their last vote's position; on SQLite a decision in the same wall-clock
second as the cutoff, but after it, can be missed (PostgreSQL compares properly).

``apply_rule`` closes only records at title/abstract with no human title/abstract
decision at all. Partly reviewed, conflicted and uncertain records stay open
(reported as ``left_open``), and legacy ``imported`` records are not touched. A
vote racing the UPDATE can land on a record that has just closed; later votes are
then rejected by the stage check. ``reopen`` puts every closed record back.

This module imports models only (no scikit-learn, no ``services``).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, case, or_, update
from sqlalchemy.orm import aliased
from sqlmodel import Session, func, select

from app.features.projects.models import Project
from app.features.research.models import Article, ArticleStatus, FinalDecision
from app.features.websocket.schemas import NotificationLevel
from app.features.websocket.services import NotificationService

from .models import (
    DecisionSource,
    RankingRun,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
    StoppingRuleSummary,
)
from .schemas import (
    ApplyStoppingRuleResult,
    RankingRunRead,
    ReopenNotScreenedResult,
    StoppingRuleStatus,
)

logger = logging.getLogger(__name__)

SD = ScreeningDecision


class StoppingRuleError(Exception):
    """Domain error carrying the HTTP status the router should return."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class Streak:
    consecutive_excludes: int
    last_reset_decision_id: Optional[int]
    counting_since: Optional[datetime]  # tz-aware UTC


@dataclass(frozen=True)
class RecordCounts:
    remaining: int  # status 'screening' (title/abstract), with or without votes
    closable: int  # of those, no human title/abstract decision
    not_screened: int  # closed by the rule
    not_started: int  # legacy 'imported'
    screened: int  # settled human title/abstract outcomes, all time


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def rule_enabled(project: Project) -> bool:
    return (
        bool(project.prioritized_screening)
        and project.stop_after_consecutive_excludes is not None
    )


def counting_since(project: Project) -> Optional[datetime]:
    """Start of the streak window (tz-aware UTC); None when neither date is set."""
    dates = [
        _utc(d)
        for d in (
            project.prioritized_screening_enabled_at,
            project.stopping_rule_applied_at,
        )
        if d is not None
    ]
    return max(dates) if dates else None


def _base_conds(project_id: int, since: Optional[datetime]) -> list[Any]:
    conds = [
        Article.project_id == project_id,
        SD.stage == ScreeningStage.title_abstract,
        SD.source == DecisionSource.human,
        Article.title_abstract_skipped.is_(False),
        Article.not_screened_stopping_rule.is_(False),
    ]
    if since is not None:
        # floor to the second: SQLite's now() has no sub-second part
        conds.append(SD.created_at >= since.replace(microsecond=0))
    return conds


def compute_streak(session: Session, project: Project) -> Streak:
    """Consecutive settled excludes since the last reset (0, no queries, if not prioritized)."""
    if not project.prioritized_screening:
        return Streak(0, None, counting_since(project))
    since = counting_since(project)
    conds = _base_conds(project.id, since)

    current_votes = (
        select(func.max(SD.id))
        .join(Article, SD.article_id == Article.id)
        .where(*conds, SD.is_resolution.is_(False))
        .group_by(SD.article_id, SD.reviewer_id)
    )
    last_reset = session.exec(
        select(func.max(SD.id))
        .join(Article, SD.article_id == Article.id)
        .where(
            *conds,
            SD.decision != ScreeningDecisionType.exclude,
            or_(SD.is_resolution.is_(True), SD.id.in_(current_votes)),
        )
    ).one()

    ft = aliased(SD)
    ft_human = (
        select(ft.id)
        .where(
            ft.article_id == Article.id,
            ft.stage == ScreeningStage.full_text,
            ft.source == DecisionSource.human,
        )
        .exists()
    )
    settled = (
        select(SD.article_id, func.max(SD.id).label("sid"))
        .join(Article, SD.article_id == Article.id)
        .where(
            *conds,
            Article.status == ArticleStatus.excluded,
            Article.current_stage == ScreeningStage.completed,
            ~ft_human,
        )
        .group_by(SD.article_id)
        .subquery()
    )
    query = select(func.count()).select_from(settled)
    if last_reset is not None:
        query = query.where(settled.c.sid > last_reset)
    return Streak(session.exec(query).one(), last_reset, since)


def closable_filter(project_id: int) -> tuple[Any, ...]:
    """Records ``apply_rule`` closes: at title/abstract with no human title/abstract decision."""
    no_human_ta = (
        ~select(SD.id)
        .where(
            SD.article_id == Article.id,
            SD.stage == ScreeningStage.title_abstract,
            SD.source == DecisionSource.human,
        )
        .exists()
    )
    return (
        Article.project_id == project_id,
        Article.status == ArticleStatus.screening,
        Article.current_stage == ScreeningStage.title_abstract,
        no_human_ta,
    )


def record_counts(session: Session, project_id: int) -> RecordCounts:
    """All record counts in one query.

    ``screened`` is the all-time form of ``queue.settled_title_abstract_count``.
    """
    human_ta = (
        select(SD.id)
        .where(
            SD.article_id == Article.id,
            SD.stage == ScreeningStage.title_abstract,
            SD.source == DecisionSource.human,
        )
        .exists()
    )

    def count(*conds: Any) -> Any:
        return func.coalesce(func.sum(case((and_(*conds), 1), else_=0)), 0)

    remaining = Article.status == ArticleStatus.screening
    row = session.exec(
        select(
            count(remaining),
            count(*closable_filter(project_id)),
            count(Article.not_screened_stopping_rule.is_(True)),
            count(Article.status == ArticleStatus.imported),
            count(
                Article.status.notin_(
                    (ArticleStatus.imported, ArticleStatus.screening)
                ),
                Article.title_abstract_skipped.is_(False),
                Article.not_screened_stopping_rule.is_(False),
                human_ta,
            ),
        ).where(Article.project_id == project_id)
    ).one()
    return RecordCounts(*(int(n) for n in row))


def latest_run(session: Session, project_id: int) -> Optional[RankingRun]:
    """The project's most recent ranking run (same query as ``ranking.last_run``)."""
    return session.exec(
        select(RankingRun)
        .where(RankingRun.project_id == project_id)
        .order_by(RankingRun.created_at.desc(), RankingRun.id.desc())
    ).first()


def status(session: Session, project: Project) -> StoppingRuleStatus:
    """Payload of ``GET .../screening/stopping-rule``."""
    streak = compute_streak(session, project)
    counts = record_counts(session, project.id)
    run = latest_run(session, project.id)
    threshold = project.stop_after_consecutive_excludes
    enabled = rule_enabled(project)
    return StoppingRuleStatus(
        enabled=enabled,
        prioritized=bool(project.prioritized_screening),
        threshold=threshold,
        consecutive_excludes=streak.consecutive_excludes,
        met=enabled and streak.consecutive_excludes >= threshold,
        remaining=counts.remaining,
        closable=counts.closable,
        screened=counts.screened,
        not_screened=counts.not_screened,
        last_ranked_at=run.created_at if run else None,
        applied_at=project.stopping_rule_applied_at,
        counting_since=streak.counting_since,
        last_run=RankingRunRead.model_validate(run, from_attributes=True)
        if run
        else None,
    )


def summary(session: Session, project: Project) -> Optional[StoppingRuleSummary]:
    """Short form for ``ScreeningStats``; None unless prioritized screening is on."""
    if not project.prioritized_screening:
        return None
    streak = compute_streak(session, project)
    threshold = project.stop_after_consecutive_excludes
    enabled = rule_enabled(project)
    return StoppingRuleSummary(
        enabled=enabled,
        threshold=threshold,
        consecutive_excludes=streak.consecutive_excludes,
        met=enabled and streak.consecutive_excludes >= threshold,
        applied_at=project.stopping_rule_applied_at,
    )


def apply_rule(
    session: Session, project: Project, *, force: bool, reason: Optional[str]
) -> ApplyStoppingRuleResult:
    """Close the records nobody has screened (see the module docstring).

    Raises:
        StoppingRuleError: 409 if prioritization is off, no threshold is set,
            nothing is closable, or the rule is not met and ``force`` is false.
    """
    if not project.prioritized_screening:
        raise StoppingRuleError(409, "Prioritized screening is off for this project")
    threshold = project.stop_after_consecutive_excludes
    if threshold is None:
        raise StoppingRuleError(409, "No stopping rule is set for this project")
    streak = compute_streak(session, project)
    counts = record_counts(session, project.id)
    if counts.closable == 0:
        raise StoppingRuleError(409, "No unscreened records left at title/abstract")
    met = streak.consecutive_excludes >= threshold
    if not met and not force:
        raise StoppingRuleError(
            409,
            f"The stopping rule is not met ({streak.consecutive_excludes} of "
            f"{threshold} consecutive excludes)",
        )

    closed = session.exec(
        update(Article)
        .where(*closable_filter(project.id))
        .values(
            status=ArticleStatus.excluded,
            current_stage=ScreeningStage.completed,
            final_decision=FinalDecision.excluded,
            not_screened_stopping_rule=True,
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    applied_at = datetime.now(timezone.utc)
    project.stopping_rule_applied_at = applied_at
    session.add(project)
    session.commit()
    session.refresh(project)

    run = latest_run(session, project.id)
    return ApplyStoppingRuleResult(
        closed=closed,
        left_open=counts.remaining - counts.closable,
        not_started=counts.not_started,
        screened=counts.screened,
        threshold=threshold,
        consecutive_excludes=streak.consecutive_excludes,
        forced=not met,
        reason=reason,
        applied_at=applied_at,
        counting_since=streak.counting_since,
        ranking_run_id=run.id if run else None,
        model_version=run.model_version if run else None,
        ranking_method=run.method if run else None,
    )


def reopen(session: Session, project: Project) -> ReopenNotScreenedResult:
    """Put every record closed by the rule back to title/abstract screening (an undo).

    Works whether or not prioritization is still on. ``relevance_score`` is kept.

    Raises:
        StoppingRuleError: 409 if no record is closed.
    """
    flagged = (
        Article.project_id == project.id,
        Article.not_screened_stopping_rule.is_(True),
    )
    if not session.exec(
        select(func.count()).select_from(Article).where(*flagged)
    ).one():
        raise StoppingRuleError(409, "No records were closed by the stopping rule")
    reopened = session.exec(
        update(Article)
        .where(*flagged)
        .values(
            status=ArticleStatus.screening,
            current_stage=ScreeningStage.title_abstract,
            final_decision=FinalDecision.pending,
            not_screened_stopping_rule=False,
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    previous = project.stopping_rule_applied_at
    project.stopping_rule_applied_at = None
    session.add(project)
    session.commit()
    session.refresh(project)
    return ReopenNotScreenedResult(reopened=reopened, previous_applied_at=previous)


async def notify(project_id: int, message: str, data: dict[str, Any]) -> None:
    """Tell the project room; a websocket problem never fails the request."""
    try:
        await NotificationService.notify_room(
            room_name=f"project_{project_id}",
            message=message,
            level=NotificationLevel.INFO,
            data=data,
        )
    except Exception:
        logger.exception("Failed to send stopping rule notification")
