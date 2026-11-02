"""Stopping rule for prioritized title/abstract screening (streak, apply, reopen).

The streak is "settled title/abstract excludes since the last thing that could
signal a relevant record", over the project's human title/abstract decisions only
(AI decisions, full-text decisions, records that skipped title/abstract and
records closed by the rule are ignored). Decision ids give the order.

- **Window.** Only decisions made at or after ``counting_since`` count: the latest of
  ``Project.prioritized_screening_enabled_at``, ``Project.stopping_rule_applied_at``
  and the project's newest ``ImportBatch`` that added new records to title/abstract
  screening (not a duplicates-only or ``title_abstract_screened`` import). So applying the rule or importing more
  records restarts the count (the new records need a fresh streak, or ``force``),
  and reopening clears ``stopping_rule_applied_at`` (an undo).
- **Reset events.** An article resets the streak when it has a *current* vote (each
  reviewer's latest, non-resolution; looked up over all time, not just the window) or
  an owner resolution that is ``include`` or ``uncertain``. That covers settled
  includes, uncertain votes, conflicts, and (dual screening) an include vote that
  still waits for the second reviewer. The reset sits at the article's latest
  in-window decision (an article with none is ignored), so a vote from before the
  window still counts once the other reviewer votes inside it. A superseded
  include/uncertain vote no longer resets.
- **Exclude events.** Articles whose title/abstract stage settled as an exclude
  (excluded, completed, no human full-text decision), positioned at the id of the
  decision that settled them. Single votes in dual screening add nothing until the
  article settles ("agreed outcomes, not votes").

The streak is the number of exclude events after the last reset. It depends only on
decisions, not on the current ``required_reviewers``, so a settings change cannot
rewrite it. Approximations: when ``required_reviewers`` drops from 2 to 1, articles
settle at their last vote's position; on SQLite a decision in the same wall-clock
second as the cutoff, but after it, can be missed (its ``now()`` has no sub-second part;
PostgreSQL compares properly).

``apply_rule`` closes only records at title/abstract with no human title/abstract
decision at all. Partly reviewed, conflicted and uncertain records stay open
(reported as ``left_open``), and legacy ``imported`` records are not touched. A
vote racing the UPDATE can land on a record that has just closed; later votes are
then rejected by the stage check. ``reopen`` puts every closed record back.

Statistical rule (``Project.stopping_rule_type == "statistical"``). Callaghan and
Mueller-Hansen (2020), "Statistical stopping criteria for automated screening in
systematic reviews", Syst Rev 9:273, doi:10.1186/s13643-020-01521-4, "ranked
quasi-sampling" as in ``buscarpy.calculate_h0`` (bias 1). The null hypothesis is that
recall is below ``recall_target``. The last ``n`` settled records are treated as a
random sample of the ``n`` plus the still unscreened ``U`` records; with ``k`` relevant
in the sample, ``r`` relevant found in total and ``m0 = floor(r / target) + 1 - r`` (the
fewest relevant records that must remain unseen under H0), the p-value is
``P(X <= k)`` for ``X ~ Hypergeometric(U + n, k + m0, n)`` (``recall_test``). The rule is
met when the smallest p over all ``n`` is below ``stopping_alpha`` (strictly) and at
least one relevant record was found. Only records settled since ``counting_since`` can
be part of a sample (earlier ones were not served by relevance, or could not have drawn
the records imported since); all relevant records found count towards ``r``. Settled
means agreed or resolved outcomes (as for the streak); records with open votes,
conflicts or uncertain outcomes are unscreened. Records that skipped title/abstract
are outside the population. Approximation: open records (a pending include vote, conflicts,
uncertain) count as unscreened although humans will still screen them, which only makes the
test more conservative. ``scipy`` is imported inside the functions that need it.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any, Literal, Optional, Sequence

import numpy as np
from sqlalchemy import and_, case, or_, true, update
from sqlalchemy.orm import aliased
from sqlmodel import Session, func, select

from app.features.projects.models import ImportBatch, Project, StoppingRuleType
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
    RecallTestRead,
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


@dataclass(frozen=True)
class RecallTest:
    """Result of the hypergeometric recall test (see the module docstring)."""

    p_value: Optional[float]  # None when there is no sample
    met: bool  # p_value < alpha and relevant_found >= 1
    recall_target: float
    alpha: float
    relevant_found: int  # all relevant records found so far
    screened: int  # all settled records in the sequence
    sample_size: int  # settled records inside the counting window
    unscreened: int
    min_missed_under_h0: int  # fewest relevant records left unseen under H0
    best_sample: Optional[int]  # size of the sample window giving the smallest p
    reason: Literal["ok", "no_relevant", "no_sample", "nothing_left"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def is_statistical(project: Project) -> bool:
    return project.stopping_rule_type == StoppingRuleType.statistical


def rule_enabled(project: Project) -> bool:
    """Prioritized, and a statistical rule or a consecutive threshold is set."""
    return bool(project.prioritized_screening) and (
        is_statistical(project) or project.stop_after_consecutive_excludes is not None
    )


def counting_since(session: Session, project: Project) -> Optional[datetime]:
    """Start of the streak window (tz-aware UTC); None when no date is set."""
    last_import = session.exec(
        select(func.max(ImportBatch.created_at)).where(
            ImportBatch.project_id == project.id,
            # only imports that put new records into title/abstract screening
            ImportBatch.imported > 0,
            ImportBatch.title_abstract_screened.is_(False),
        )
    ).one()
    dates = [
        _utc(d)
        for d in (
            project.prioritized_screening_enabled_at,
            project.stopping_rule_applied_at,
            last_import,
        )
        if d is not None
    ]
    return max(dates) if dates else None


def _base_conds(project_id: int) -> list[Any]:
    return [
        Article.project_id == project_id,
        SD.stage == ScreeningStage.title_abstract,
        SD.source == DecisionSource.human,
        Article.title_abstract_skipped.is_(False),
        Article.not_screened_stopping_rule.is_(False),
    ]


def compute_streak(session: Session, project: Project) -> Streak:
    """Consecutive settled excludes since the last reset (0, no queries, if not prioritized)."""
    if not project.prioritized_screening:
        return Streak(0, None, None)
    since = counting_since(session, project)
    base = _base_conds(project.id)
    conds = base if since is None else [*base, SD.created_at >= since]

    # current votes over all time, so a vote from before the window still counts
    current_votes = (
        select(func.max(SD.id))
        .join(Article, SD.article_id == Article.id)
        .where(*base, SD.is_resolution.is_(False))
        .group_by(SD.article_id, SD.reviewer_id)
    )
    reset_articles = (
        select(SD.article_id)
        .join(Article, SD.article_id == Article.id)
        .where(
            *base,
            SD.decision != ScreeningDecisionType.exclude,
            or_(SD.is_resolution.is_(True), SD.id.in_(current_votes)),
        )
    )
    last_reset = session.exec(
        select(func.max(SD.id))
        .join(Article, SD.article_id == Article.id)
        .where(*conds, SD.article_id.in_(reset_articles))
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
        # >=: an article that reset the streak and then settled as an exclude counts
        query = query.where(settled.c.sid >= last_reset)
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


def min_missed_under_h0(relevant_found: int, recall_target: float) -> int:
    """Fewest relevant records that must remain unseen for recall < target.

    ``floor(r / target) + 1 - r`` in integer arithmetic (``recall_target`` is read as
    its decimal string, so 19 found at 0.95 gives 2, not a float-rounding accident).
    """
    t = Fraction(str(recall_target))
    return (relevant_found * t.denominator) // t.numerator + 1 - relevant_found


def _window_arrays(
    window: Sequence[int] | np.ndarray,
    relevant_before: int,
    unscreened: int,
    recall_target: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Candidate sample windows as ``(starts, n, k, M, K, m0)`` arrays.

    The p-value never increases when a window grows backwards over an exclude, so the
    minimum is at the first record of the window or right after an include.
    """
    w = np.asarray(window, dtype=np.int64)
    length = len(w)
    relevant = relevant_before + int(w.sum())
    m0 = min_missed_under_h0(relevant, recall_target)
    if length == 0:  # an empty sample, to be grown by appended excludes
        zero = np.zeros(1, dtype=np.int64)
        return zero, zero, zero, zero + unscreened, zero + m0, m0
    starts = np.unique(np.concatenate(([0], np.flatnonzero(w) + 1)))
    starts = starts[starts < length]
    suffix = np.concatenate((np.cumsum(w[::-1])[::-1], [0]))
    n = length - starts
    k = suffix[starts]
    return starts, n, k, unscreened + n, k + m0, m0


def _p_values(
    k: np.ndarray, population: np.ndarray, k_tar: np.ndarray, n: np.ndarray
) -> np.ndarray:
    """``P(X <= k)`` for ``X ~ Hypergeometric(population, k_tar, n)``; 0 where H0 is
    impossible (``k_tar`` above the population)."""
    from scipy.stats import hypergeom

    impossible = k_tar > population
    p = hypergeom.cdf(k, population, np.minimum(k_tar, population), n)
    return np.where(impossible, 0.0, p)


def recall_test(
    window: Sequence[int] | np.ndarray,
    *,
    relevant_before: int,
    screened_before: int,
    unscreened: int,
    recall_target: float,
    alpha: float,
) -> RecallTest:
    """Ranked quasi-sampling recall test (module docstring).

    Args:
        window: Settled records usable as a sample, in screening order (1 = relevant).
        relevant_before: Relevant records settled before the window.
        screened_before: Records settled before the window.
        unscreened: Records not screened yet (the unseen part of the population).
        recall_target: Recall to demonstrate, e.g. 0.95.
        alpha: Significance level; the rule is met when ``p < alpha``.
    """
    length = len(window)
    relevant = relevant_before + int(np.asarray(window, dtype=np.int64).sum())
    base = {
        "recall_target": recall_target,
        "alpha": alpha,
        "relevant_found": relevant,
        "screened": screened_before + length,
        "sample_size": length,
        "unscreened": unscreened,
        "min_missed_under_h0": min_missed_under_h0(relevant, recall_target),
    }
    if length == 0:
        return RecallTest(
            p_value=None, met=False, best_sample=None, reason="no_sample", **base
        )
    _, n, k, population, k_tar, _ = _window_arrays(
        window, relevant_before, unscreened, recall_target
    )
    p = _p_values(k, population, k_tar, n)
    best = int(np.argmin(p))
    p_min = 0.0 if unscreened == 0 else float(p[best])
    if relevant == 0:
        reason = "no_relevant"
    elif unscreened == 0:
        reason = "nothing_left"
    else:
        reason = "ok"
    return RecallTest(
        p_value=p_min,
        met=relevant >= 1 and p_min < alpha,
        best_sample=int(n[best]),
        reason=reason,
        **base,
    )


def excludes_needed(
    window: Sequence[int] | np.ndarray,
    *,
    relevant_before: int,
    screened_before: int,
    unscreened: int,
    recall_target: float,
    alpha: float,
    max_candidates: int = 32,
) -> Optional[int]:
    """About how many more excludes in a row would meet the rule (None: no include yet).

    Binary search on ``m``: appending ``m`` excludes leaves each candidate's population
    and ``K`` unchanged and grows its sample, so ``p`` only falls. Only the window start
    and the starts after the last ``max_candidates`` includes are tried, which can only
    over-estimate (an upper bound).
    """
    w = np.asarray(window, dtype=np.int64)
    if relevant_before + int(w.sum()) == 0:
        return None
    starts, n, k, population, k_tar, m0 = _window_arrays(
        w, relevant_before, unscreened, recall_target
    )
    if len(w) == 0:  # no candidate yet; only the appended excludes can form one
        n = k = population = k_tar = np.zeros(0, dtype=np.int64)
    else:
        tail = np.arange(max(1, len(starts) - max_candidates), len(starts))
        keep = np.unique(np.concatenate(([0], tail)))
        n, k, population, k_tar = n[keep], k[keep], population[keep], k_tar[keep]
    # a sample made only of the appended excludes (starts after a last include)
    only_new = np.array([m0], dtype=np.int64)
    only_pop = np.array([unscreened], dtype=np.int64)
    zero = np.zeros(1, dtype=np.int64)

    def met(m: int) -> bool:
        p = _p_values(k, population, k_tar, n + m)
        if m > 0:
            p = np.append(p, _p_values(zero, only_pop, only_new, zero + m))
        return len(p) > 0 and float(p.min()) < alpha

    lo, hi = 0, unscreened  # met(unscreened) is true: every record seen, p = 0
    while lo < hi:
        mid = (lo + hi) // 2
        if met(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


@dataclass(frozen=True)
class _Sequence:
    window: np.ndarray
    relevant_before: int
    screened_before: int


def _recall_sequence(
    session: Session, project: Project, since: Optional[datetime]
) -> _Sequence:
    """Settled title/abstract outcomes in settlement order (see the module docstring)."""
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
    irrelevant = and_(
        Article.status == ArticleStatus.excluded,
        Article.current_stage == ScreeningStage.completed,
        ~ft_human,
    )
    settled = (
        select(
            SD.article_id.label("article_id"),
            func.max(SD.id).label("sid"),
            case((irrelevant, 0), else_=1).label("relevant"),
        )
        .join(Article, SD.article_id == Article.id)
        .where(
            *_base_conds(project.id),
            Article.status.notin_((ArticleStatus.imported, ArticleStatus.screening)),
        )
        .group_by(SD.article_id, Article.status, Article.current_stage, Article.id)
        .subquery()
    )
    last = aliased(SD)
    in_window = true() if since is None else last.created_at >= since
    rows = session.exec(
        select(settled.c.relevant, in_window)
        .select_from(settled)
        .join(last, last.id == settled.c.sid)
        .order_by(settled.c.sid)
    ).all()
    labels = np.array([int(r[0]) for r in rows], dtype=np.int64)
    inside = np.array([bool(r[1]) for r in rows], dtype=bool)
    before = labels[~inside]
    return _Sequence(labels[inside], int(before.sum()), len(before))


def compute_recall_test(
    session: Session,
    project: Project,
    counts: Optional["RecordCounts"] = None,
    since: Optional[datetime] = None,
    seq: Optional["_Sequence"] = None,
) -> Optional[RecallTest]:
    """Recall test on the project's settled records; None unless prioritized."""
    if not project.prioritized_screening:
        return None
    counts = counts or record_counts(session, project.id)
    since = since or counting_since(session, project)
    seq = seq or _recall_sequence(session, project, since)
    return recall_test(
        seq.window,
        relevant_before=seq.relevant_before,
        screened_before=seq.screened_before,
        unscreened=counts.remaining + counts.not_started + counts.not_screened,
        recall_target=project.recall_target,
        alpha=project.stopping_alpha,
    )


def _excludes_needed_for(
    project: Project, counts: "RecordCounts", seq: "_Sequence"
) -> Optional[int]:
    return excludes_needed(
        seq.window,
        relevant_before=seq.relevant_before,
        screened_before=seq.screened_before,
        unscreened=counts.remaining + counts.not_started + counts.not_screened,
        recall_target=project.recall_target,
        alpha=project.stopping_alpha,
    )


def latest_run(session: Session, project_id: int) -> Optional[RankingRun]:
    """The project's most recent ranking run (same query as ``ranking.last_run``)."""
    return session.exec(
        select(RankingRun)
        .where(RankingRun.project_id == project_id)
        .order_by(RankingRun.created_at.desc(), RankingRun.id.desc())
    ).first()


def _consecutive_met(project: Project, streak: Streak) -> bool:
    threshold = project.stop_after_consecutive_excludes
    return threshold is not None and streak.consecutive_excludes >= threshold


def _is_met(project: Project, streak: Streak, test: Optional[RecallTest]) -> bool:
    if not rule_enabled(project):
        return False
    if is_statistical(project):
        return test is not None and test.met
    return _consecutive_met(project, streak)


def status(session: Session, project: Project) -> StoppingRuleStatus:
    """Payload of ``GET .../screening/stopping-rule``."""
    streak = compute_streak(session, project)
    counts = record_counts(session, project.id)
    run = latest_run(session, project.id)
    threshold = project.stop_after_consecutive_excludes
    enabled = rule_enabled(project)
    seq = (
        _recall_sequence(session, project, streak.counting_since)
        if is_statistical(project) and project.prioritized_screening
        else None
    )
    test = (
        compute_recall_test(session, project, counts, streak.counting_since, seq)
        if seq is not None
        else None
    )
    met = _is_met(project, streak, test)
    return StoppingRuleStatus(
        enabled=enabled,
        prioritized=bool(project.prioritized_screening),
        threshold=threshold,
        consecutive_excludes=streak.consecutive_excludes,
        met=met,
        can_apply=met and counts.closable > 0,
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
        rule_type=project.stopping_rule_type,
        recall_target=project.recall_target,
        alpha=project.stopping_alpha,
        statistical=RecallTestRead(
            **{
                k: v
                for k, v in asdict(test).items()
                if k in RecallTestRead.model_fields
            },
            excludes_needed=_excludes_needed_for(project, counts, seq),
        )
        if test is not None
        else None,
    )


def summary(session: Session, project: Project) -> Optional[StoppingRuleSummary]:
    """Short form for ``ScreeningStats``; None unless prioritized screening is on."""
    if not project.prioritized_screening:
        return None
    streak = compute_streak(session, project)
    test = compute_recall_test(session, project) if is_statistical(project) else None
    return StoppingRuleSummary(
        enabled=rule_enabled(project),
        threshold=project.stop_after_consecutive_excludes,
        consecutive_excludes=streak.consecutive_excludes,
        met=_is_met(project, streak, test),
        applied_at=project.stopping_rule_applied_at,
        rule_type=project.stopping_rule_type,
        recall_target=project.recall_target if test else None,
        alpha=project.stopping_alpha if test else None,
        p_value=test.p_value if test else None,
        relevant_found=test.relevant_found if test else None,
        test_reason=test.reason if test else None,
    )


def _not_met_message(
    streak: Streak, threshold: Optional[int], test: Optional[RecallTest]
) -> str:
    if test is None:
        return (
            f"The stopping rule is not met ({streak.consecutive_excludes} of "
            f"{threshold} consecutive excludes)"
        )
    if test.reason == "no_relevant":
        return "The stopping rule is not met: no relevant record has been found yet"
    target = f"{test.recall_target * 100:g}%"
    if test.p_value is None:
        return (
            f"The stopping rule is not met: no record was screened since "
            f"the counting window started (recall target {target})"
        )
    return (
        f"The stopping rule is not met (p = {test.p_value:.2g} for recall below "
        f"{target}; needs p < {test.alpha:g})"
    )


def apply_rule(
    session: Session, project: Project, *, force: bool, reason: Optional[str]
) -> ApplyStoppingRuleResult:
    """Close the records nobody has screened (see the module docstring).

    Raises:
        StoppingRuleError: 409 if prioritization is off, no rule is set,
            nothing is closable, or the rule is not met and ``force`` is false.
    """
    # serialize applications (and reopen) per project; no-op on SQLite
    session.refresh(project, with_for_update=True)
    if not project.prioritized_screening:
        raise StoppingRuleError(409, "Prioritized screening is off for this project")
    if not rule_enabled(project):
        raise StoppingRuleError(409, "No stopping rule is set for this project")
    threshold = project.stop_after_consecutive_excludes
    statistical = is_statistical(project)
    streak = compute_streak(session, project)
    counts = record_counts(session, project.id)
    if counts.closable == 0:
        raise StoppingRuleError(409, "No unscreened records left at title/abstract")
    test = (
        compute_recall_test(session, project, counts, streak.counting_since)
        if statistical
        else None
    )
    met = _is_met(project, streak, test)
    if not met and not force:
        raise StoppingRuleError(409, _not_met_message(streak, threshold, test))

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
    if closed == 0:  # a vote or another application got there first
        session.rollback()
        raise StoppingRuleError(409, "No unscreened records left at title/abstract")
    left_open = session.exec(
        select(func.count())
        .select_from(Article)
        .where(
            Article.project_id == project.id,
            Article.status == ArticleStatus.screening,
        )
    ).one()
    applied_at = datetime.now(timezone.utc)
    project.stopping_rule_applied_at = applied_at
    session.add(project)
    session.commit()
    session.refresh(project)

    run = latest_run(session, project.id)
    return ApplyStoppingRuleResult(
        closed=closed,
        left_open=left_open,
        not_started=counts.not_started,
        screened=counts.screened,
        threshold=None if statistical else threshold,
        consecutive_excludes=streak.consecutive_excludes,
        forced=not met,
        reason=reason,
        applied_at=applied_at,
        counting_since=streak.counting_since,
        ranking_run_id=run.id if run else None,
        model_version=run.model_version if run else None,
        ranking_method=run.method if run else None,
        rule_type=project.stopping_rule_type,
        recall_target=project.recall_target if test else None,
        alpha=project.stopping_alpha if test else None,
        p_value=test.p_value if test else None,
        relevant_found=test.relevant_found if test else None,
        sample_size=test.sample_size if test else None,
        unscreened=test.unscreened if test else None,
    )


def reopen(session: Session, project: Project) -> ReopenNotScreenedResult:
    """Put every record closed by the rule back to title/abstract screening (an undo).

    Works whether or not prioritization is still on. ``relevance_score`` is kept.

    Raises:
        StoppingRuleError: 409 if no record is closed.
    """
    session.refresh(project, with_for_update=True)
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
