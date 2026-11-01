"""Suggested methods sentence on prioritized screening and the stopping rule.

``screening_method_sentence`` is a pure function over ``MethodInputs`` so every
variant is unit-tested without a database; ``load_method_inputs`` gathers the
inputs (at most four cheap queries).

The stopping-rule numbers come from the latest ``screening.stopping_rule_applied``
audit event (an at-apply snapshot; the audit log is append-only, and the project
setting can change after applying). The event is read only while records closed
by the rule exist: reopening clears every flag and a re-apply writes a newer event,
so the latest event is always the application in effect. A missing or malformed
payload falls back to generic wording, never an error.

Known limits: several applications are summarised by the latest one (the number of
records not screened is the current total); ``min_random``, ``prioritized`` and the
threshold used when there is no event are today's settings; turning prioritization
off part-way is not described. The text is a suggestion the author edits.

This module does not import ``screening.ranking`` (scikit-learn).
"""

from dataclasses import dataclass
from typing import Any, Optional

from sqlmodel import Session, func, select

from app.features.audit import services as audit
from app.features.audit.models import AuditEvent
from app.features.projects.models import Project
from app.features.screening.models import RankingRun

# keep in sync with screening.ranking.MODEL_VERSION (a test checks it)
MODEL_DESCRIPTIONS = {
    "tfidf-logreg-v1": "a logistic regression classifier on TF-IDF features of "
    "titles, abstracts and keywords",
}
GENERIC_MODEL = "a machine-learning model"


def _int_or_none(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@dataclass(frozen=True)
class AppliedRule:
    """Snapshot of the latest ``screening.stopping_rule_applied`` audit event."""

    threshold: Optional[int]
    consecutive_excludes: Optional[int]
    screened: Optional[int]
    forced: bool
    reason: Optional[str]

    @classmethod
    def from_details(cls, details: Optional[dict]) -> "AppliedRule":
        """Defensive parse: ints only (bool excluded), ``forced`` only if ``True``,
        ``reason`` only a non-blank string."""
        d = details if isinstance(details, dict) else {}
        reason = d.get("reason")
        reason = reason.strip() if isinstance(reason, str) else None
        return cls(
            threshold=_int_or_none(d.get("threshold")),
            consecutive_excludes=_int_or_none(d.get("consecutive_excludes")),
            screened=_int_or_none(d.get("screened")),
            forced=d.get("forced") is True,
            reason=reason or None,
        )


@dataclass(frozen=True)
class MethodInputs:
    ranking_runs: int  # RankingRun rows of the project
    model_version: Optional[str]  # of the latest run with method "model"
    cold_start_method: Optional[str]  # latest run's method when no "model" run
    min_random: int  # Project.ranking_min_random (current value)
    prioritized: bool  # Project.prioritized_screening (current)
    threshold: Optional[int]  # Project.stop_after_consecutive_excludes (current)
    not_screened: int  # stats.not_screened_stopping_rule (current)
    applied: Optional[AppliedRule]  # only loaded when not_screened > 0


def load_method_inputs(
    session: Session, project: Project, not_screened: int
) -> MethodInputs:
    """Collect the inputs of the methods sentence for a project."""
    runs = session.exec(
        select(func.count(RankingRun.id)).where(RankingRun.project_id == project.id)
    ).one()
    model_version = cold_start = None
    if runs:
        latest = select(RankingRun).where(RankingRun.project_id == project.id)
        model_run = session.exec(
            latest.where(RankingRun.method == "model")
            .order_by(RankingRun.id.desc())
            .limit(1)
        ).first()
        if model_run is not None:
            model_version = model_run.model_version
        else:
            last = session.exec(latest.order_by(RankingRun.id.desc()).limit(1)).first()
            cold_start = last.method if last is not None else None
    applied = None
    if not_screened > 0:
        event = session.exec(
            select(AuditEvent)
            .where(
                AuditEvent.project_id == project.id,
                AuditEvent.action == audit.SCREENING_STOPPING_RULE_APPLIED,
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        ).first()
        if event is not None:
            applied = AppliedRule.from_details(event.details)
    return MethodInputs(
        ranking_runs=runs,
        model_version=model_version,
        cold_start_method=cold_start,
        min_random=project.ranking_min_random or 0,
        prioritized=bool(project.prioritized_screening),
        threshold=project.stop_after_consecutive_excludes,
        not_screened=not_screened,
        applied=applied,
    )


def _n(k: int, noun: str) -> str:
    return f"{k} {noun}" if k == 1 else f"{k} {noun}s"


def _was(k: int) -> str:
    return "was" if k == 1 else "were"


def _part_a(i: MethodInputs) -> Optional[str]:
    if i.ranking_runs <= 0:
        return None
    if i.model_version is not None:
        desc = MODEL_DESCRIPTIONS.get(i.model_version, GENERIC_MODEL)
        if i.min_random == 0:
            order = "records were presented"
        else:
            k = i.min_random
            order = (
                f"after the first {_n(k, 'record')}, which {_was(k)} presented in "
                "random order, records were presented"
            )
        return (
            "Title and abstract screening was prioritized with active learning: "
            f"{order} in order of predicted relevance, estimated by {desc} that was "
            "retrained on the reviewers' title and abstract decisions during "
            f"screening (Excludr ranking model {i.model_version})."
        )
    how = (
        "in order of text similarity to the review question and inclusion criteria"
        if i.cold_start_method == "similarity"
        else "in random order"
    )
    return (
        "Title and abstract screening used prioritized ordering, but no relevance "
        "model could be trained (this needs at least one included and one excluded "
        f"record), so records were presented {how}."
    )


def _part_b(i: MethodInputs, lead: str) -> Optional[str]:
    n = i.not_screened
    if n > 0:
        remaining = (
            f"The remaining {_n(n, 'record')} {_was(n)} not screened (reported as "
            "marked ineligible by automation tools in the PRISMA flow diagram)."
        )
        a = i.applied
        if a is None:
            if i.threshold is None:
                return f"{lead} stopped early. {remaining}"
            return (
                f"{lead} stopped early using a stopping rule "
                f"({_n(i.threshold, 'consecutive exclusion')}). {remaining}"
            )
        threshold = a.threshold if a.threshold is not None else i.threshold
        c, s = a.consecutive_excludes, a.screened
        if a.forced:
            rule = (
                f" ({_n(threshold, 'consecutive exclusion')})"
                if threshold is not None
                else ""
            )
            phrases = []
            if c is not None:
                phrases.append(_n(c, "consecutive exclusion"))
            if s is not None:
                phrases.append(_n(s, "screened record"))
            after = f", after {' and '.join(phrases)}" if phrases else ""
            reason = a.reason.rstrip(".").strip() if a.reason else ""
            reason_part = f" (reason: {reason})" if reason else ""
            return (
                f"{lead} stopped before the stopping rule{rule} was met"
                f"{after}{reason_part}. {remaining}"
            )
        met = (
            f"{_n(c, 'consecutive record')} {_was(c)} excluded"
            if c is not None
            else "the required run of consecutive exclusions was reached"
        )
        rule = (
            f" (rule: {_n(threshold, 'consecutive exclusion')})"
            if threshold is not None
            else ""
        )
        after = f" after {_n(s, 'record')} had been screened" if s is not None else ""
        return (
            f"{lead} stopped when the stopping rule was met: {met}{rule}{after}. "
            f"{remaining}"
        )
    if i.prioritized and i.threshold is not None:
        return (
            f"A stopping rule ({_n(i.threshold, 'consecutive exclusion')}) was set "
            "but has not been applied."
        )
    return None


def screening_method_sentence(i: MethodInputs) -> Optional[str]:
    """Suggested methods text; ``None`` when prioritization was never used (no
    ranking ran and nothing was closed by the rule)."""
    if i.ranking_runs == 0 and i.not_screened == 0:
        return None
    a = _part_a(i)
    b = _part_b(i, "Screening" if a else "Title and abstract screening")
    return " ".join(p for p in (a, b) if p)
