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

import math
from dataclasses import dataclass
from typing import Any, Optional

from sqlmodel import Session, func, select

from app.features.audit import services as audit
from app.features.audit.models import AuditEvent
from app.features.projects.models import Project, StoppingRuleType
from app.features.screening.models import RankingRun

# keep in sync with screening.ranking.MODEL_VERSION (a test checks it)
MODEL_DESCRIPTIONS = {
    "tfidf-logreg-v1": "a logistic regression classifier on TF-IDF features of "
    "titles, abstracts and keywords",
}
GENERIC_MODEL = "a machine-learning model"
CALLAGHAN_2020 = "Callaghan and Müller-Hansen, 2020"
CALLAGHAN_2020_REFERENCE = (
    "Callaghan MW, Müller-Hansen F. Statistical stopping criteria for automated "
    "screening in systematic reviews. Syst Rev. 2020;9:273. "
    "doi:10.1186/s13643-020-01521-4"
)


def _int_or_none(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float_in(value: Any, low: float, high: float) -> Optional[float]:
    """A finite float (int allowed, bool not) within ``[low, high]``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and low <= value <= high else None


@dataclass(frozen=True)
class AppliedRule:
    """Snapshot of the latest ``screening.stopping_rule_applied`` audit event."""

    threshold: Optional[int]
    consecutive_excludes: Optional[int]
    screened: Optional[int]
    forced: bool
    reason: Optional[str]
    rule_type: StoppingRuleType = StoppingRuleType.consecutive
    recall_target: Optional[float] = None
    alpha: Optional[float] = None
    p_value: Optional[float] = None
    relevant_found: Optional[int] = None

    @classmethod
    def from_details(cls, details: Optional[dict]) -> "AppliedRule":
        """Defensive parse: ints only (bool excluded), ``forced`` only if ``True``,
        ``reason`` only a non-blank string, ``rule_type`` one of the two known
        strings (old events: consecutive), floats finite and in range."""
        d = details if isinstance(details, dict) else {}
        reason = d.get("reason")
        reason = reason.strip() if isinstance(reason, str) else None
        return cls(
            threshold=_int_or_none(d.get("threshold")),
            consecutive_excludes=_int_or_none(d.get("consecutive_excludes")),
            screened=_int_or_none(d.get("screened")),
            forced=d.get("forced") is True,
            reason=reason or None,
            rule_type=(
                StoppingRuleType.statistical
                if d.get("rule_type") == StoppingRuleType.statistical.value
                else StoppingRuleType.consecutive
            ),
            recall_target=_float_in(d.get("recall_target"), 0.0, 1.0),
            alpha=_float_in(d.get("alpha"), 0.0, 1.0),
            p_value=_float_in(d.get("p_value"), 0.0, 1.0),
            relevant_found=_int_or_none(d.get("relevant_found")),
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
    awaiting_screening: int = 0  # records still open at title/abstract
    applications: int = 1  # applications since the last reopen (when applied)
    rule_type: StoppingRuleType = StoppingRuleType.consecutive  # current setting
    recall_target: float = 0.95  # Project.recall_target (current)
    alpha: float = 0.05  # Project.stopping_alpha (current)


def load_method_inputs(
    session: Session,
    project: Project,
    not_screened: int,
    awaiting_screening: int = 0,
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
    applications = 1
    if not_screened > 0:
        reverted = session.exec(
            select(func.max(AuditEvent.id)).where(
                AuditEvent.project_id == project.id,
                AuditEvent.action == audit.SCREENING_STOPPING_RULE_REVERTED,
            )
        ).one()
        applications = max(
            1,
            session.exec(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.project_id == project.id,
                    AuditEvent.action == audit.SCREENING_STOPPING_RULE_APPLIED,
                    AuditEvent.id > (reverted or 0),
                )
            ).one(),
        )
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
        awaiting_screening=awaiting_screening,
        applications=applications,
        rule_type=StoppingRuleType(project.stopping_rule_type),
        recall_target=project.recall_target,
        alpha=project.stopping_alpha,
    )


def _n(k: int, noun: str, commas: bool = False) -> str:
    num = f"{k:,}" if commas else str(k)
    return f"{num} {noun}" if k == 1 else f"{num} {noun}s"


def _was(k: int) -> str:
    return "was" if k == 1 else "were"


def _target(recall_target: float) -> str:
    return f"{round(recall_target * 100, 2):g}%"


def _p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.2g}"


def _statistical_part_b(i: MethodInputs, lead: str, remaining: str) -> str:
    a = i.applied
    target = _target(a.recall_target if a and a.recall_target else i.recall_target)
    alpha = f"{a.alpha if a and a.alpha else i.alpha:.3g}"
    cite = "the statistical stopping criterion of Callaghan and Müller-Hansen (2020)"
    s = a.screened if a else None
    if a is None:
        return (
            f"{lead} stopped early using a statistical stopping criterion "
            f"({CALLAGHAN_2020}; recall target {target}, significance level "
            f"{alpha}). {remaining}"
        )
    if a.forced:
        hypothesis = (
            f"null hypothesis of recall below {target}, significance level {alpha}"
        )
        p = f": {_p(a.p_value)}" if a.p_value is not None else ""
        after = f", after {_n(s, 'screened record', True)}" if s is not None else ""
        reason = a.reason.rstrip(".").strip() if a.reason else ""
        reason_part = f" (reason: {reason})" if reason else ""
        return (
            f"{lead} stopped before {cite} was met ({hypothesis}{p})"
            f"{after}{reason_part}. {remaining}"
        )
    included = (
        f" ({a.relevant_found:,} included)" if a.relevant_found is not None else ""
    )
    after = (
        f" after {_n(s, 'record', True)} had been screened{included}"
        if s is not None
        else ""
    )
    p = f" ({_p(a.p_value)})" if a.p_value is not None else ""
    times = (
        f" (The rule was applied {i.applications} times; figures are from the "
        "last application.)"
        if i.applications > 1
        else ""
    )
    return (
        f"{lead} stopped when {cite} was met{after}: treating the most recently "
        "screened records as a sample of the remaining records (ranked "
        "quasi-sampling), the null hypothesis that title and abstract screening had "
        f"reached a recall below {target} was rejected at a significance level of "
        f"{alpha}{p}. {remaining}{times}"
    )


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
        statistical = (
            i.applied.rule_type if i.applied is not None else i.rule_type
        ) == StoppingRuleType.statistical
        remaining = (
            f"The remaining {_n(n, 'record', statistical)} {_was(n)} not screened (reported as "
            "marked ineligible by automation tools in the PRISMA flow diagram)."
        )
        a = i.applied
        if statistical and (a is not None or i.prioritized):
            return _statistical_part_b(i, lead, remaining)
        if a is None:
            if i.threshold is None or not i.prioritized:
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
        rule = (
            f" (rule: {_n(threshold, 'consecutive exclusion')})"
            if threshold is not None
            else ""
        )
        after = f" after {_n(s, 'record')} had been screened" if s is not None else ""
        last = (
            f": the last {_n(c, 'consecutive record')} {_was(c)} excluded{rule}"
            if c is not None
            else rule
        )
        times = (
            f" (The rule was applied {i.applications} times; figures are from the "
            "last application.)"
            if i.applications > 1
            else ""
        )
        return (
            f"{lead} stopped when the stopping rule was met{after}{last}. "
            f"{remaining}{times}"
        )
    if (
        i.prioritized
        and i.rule_type == StoppingRuleType.statistical
        and i.awaiting_screening > 0
    ):
        return (
            f"A statistical stopping criterion ({CALLAGHAN_2020}; recall target "
            f"{_target(i.recall_target)}, significance level {i.alpha:.3g}) was set "
            "but has not been applied."
        )
    if (
        i.prioritized
        and i.rule_type == StoppingRuleType.consecutive
        and i.threshold is not None
        and i.awaiting_screening > 0
    ):
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


def screening_method_reference(i: MethodInputs) -> Optional[str]:
    """Full reference to print under the methods text; only when it names the
    statistical criterion."""
    sentence = screening_method_sentence(i)
    return CALLAGHAN_2020_REFERENCE if sentence and "Callaghan" in sentence else None
