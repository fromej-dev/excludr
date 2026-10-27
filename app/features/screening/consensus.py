"""Pure consensus and agreement logic for dual independent screening.

Nothing in this module touches the database: it operates on lightweight
:class:`Vote` tuples so the rules can be unit-tested exhaustively.
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from .models import ScreeningDecisionType

INCLUDE = ScreeningDecisionType.include
EXCLUDE = ScreeningDecisionType.exclude
UNCERTAIN = ScreeningDecisionType.uncertain


@dataclass(frozen=True)
class Vote:
    """A human decision reduced to what consensus needs."""

    decision_id: int
    reviewer_id: Optional[int]
    decision: ScreeningDecisionType
    is_resolution: bool = False


@dataclass(frozen=True)
class StageState:
    """Consensus state of one article at one screening stage.

    Attributes:
        outcome: Final include/exclude, or None while pending or in conflict.
        deciding_id: Id of the decision that determined the outcome (for reasons).
        is_resolution: True when the outcome came from an owner resolution.
        conflict: True when enough reviewers decided but cannot be reconciled.
        votes: Each reviewer's current (latest) vote.
    """

    outcome: Optional[ScreeningDecisionType]
    deciding_id: Optional[int]
    is_resolution: bool
    conflict: bool
    votes: tuple[Vote, ...]


def latest_vote_per_reviewer(votes: Iterable[Vote]) -> list[Vote]:
    """Latest (highest id) non-resolution vote of each reviewer, ordered by id."""
    latest: dict[Optional[int], Vote] = {}
    for vote in sorted(votes, key=lambda v: v.decision_id):
        if not vote.is_resolution:
            latest[vote.reviewer_id] = vote
    return sorted(latest.values(), key=lambda v: v.decision_id)


def evaluate_stage(votes: Sequence[Vote], required_reviewers: int) -> StageState:
    """Decide the consensus state of an article at a stage.

    Rules:
    * An owner resolution (the latest one) always settles the article.
    * With ``required_reviewers == 1`` the latest include/exclude human vote
      settles it; an ``uncertain`` vote leaves it pending.
    * With ``required_reviewers >= 2`` nothing happens until that many distinct
      reviewers have voted; then they must all give the same include/exclude
      answer. Anything else (a split, or unanimous ``uncertain``) is a conflict
      that the owner must resolve.
    """
    resolutions = [v for v in votes if v.is_resolution]
    current = latest_vote_per_reviewer(votes)
    if resolutions:
        final = max(resolutions, key=lambda v: v.decision_id)
        return StageState(
            final.decision, final.decision_id, True, False, tuple(current)
        )

    if required_reviewers <= 1:
        if current and current[-1].decision != UNCERTAIN:
            last = current[-1]
            return StageState(
                last.decision, last.decision_id, False, False, tuple(current)
            )
        return StageState(None, None, False, False, tuple(current))

    if len(current) < required_reviewers:
        return StageState(None, None, False, False, tuple(current))
    answers = {v.decision for v in current}
    if len(answers) == 1 and UNCERTAIN not in answers:
        return StageState(
            current[-1].decision, current[-1].decision_id, False, False, tuple(current)
        )
    return StageState(None, None, False, True, tuple(current))


def percent_agreement(pairs: Sequence[tuple[object, object]]) -> Optional[float]:
    """Share of pairs where both raters gave the same label (None if no pairs)."""
    if not pairs:
        return None
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def cohens_kappa(pairs: Sequence[tuple[object, object]]) -> Optional[float]:
    """Cohen's kappa for two raters over nominal labels.

    ``kappa = (po - pe) / (1 - pe)`` where ``po`` is observed agreement and
    ``pe`` the agreement expected by chance from each rater's label marginals.

    Returns None when there are no pairs. When chance agreement is 1 (both raters
    used one single label throughout) kappa is undefined; this returns 1.0 if the
    raters agree on everything, which is the only way that case can occur.
    """
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    labels = {a for a, _ in pairs} | {b for _, b in pairs}
    pe = sum(
        (sum(1 for a, _ in pairs if a == label) / n)
        * (sum(1 for _, b in pairs if b == label) / n)
        for label in labels
    )
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


@dataclass(frozen=True)
class BinaryMetrics:
    """Binary classification metrics, with ``include`` as the positive class."""

    n: int
    tp: int
    fp: int
    tn: int
    fn: int
    accuracy: Optional[float]
    sensitivity: Optional[float]
    specificity: Optional[float]
    kappa: Optional[float]


def _ratio(num: int, den: int) -> Optional[float]:
    return num / den if den else None


def binary_metrics(pairs: Sequence[tuple[bool, bool]]) -> BinaryMetrics:
    """Compare predictions to a reference.

    Args:
        pairs: ``(predicted_include, reference_include)`` per article.
    """
    tp = sum(1 for p, r in pairs if p and r)
    fp = sum(1 for p, r in pairs if p and not r)
    tn = sum(1 for p, r in pairs if not p and not r)
    fn = sum(1 for p, r in pairs if not p and r)
    n = len(pairs)
    return BinaryMetrics(
        n=n,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        accuracy=_ratio(tp + tn, n),
        sensitivity=_ratio(tp, tp + fn),
        specificity=_ratio(tn, tn + fp),
        kappa=cohens_kappa(list(pairs)),
    )
