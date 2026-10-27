"""Unit tests for the pure consensus / agreement maths."""

import pytest

from app.features.screening.consensus import (
    Vote,
    binary_metrics,
    cohens_kappa,
    evaluate_stage,
    percent_agreement,
)
from app.features.screening.models import ScreeningDecisionType as D


def _v(i, reviewer, decision, resolution=False):
    return Vote(i, reviewer, decision, resolution)


def test_kappa_known_value_wikipedia_example():
    # 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> po=0.7, pe=0.5, kappa=0.4
    pairs = [("y", "y")] * 20 + [("y", "n")] * 5 + [("n", "y")] * 10 + [("n", "n")] * 15
    assert cohens_kappa(pairs) == pytest.approx(0.4)
    assert percent_agreement(pairs) == pytest.approx(0.7)


def test_kappa_perfect_chance_and_opposite():
    assert cohens_kappa([("a", "a"), ("b", "b"), ("a", "a")]) == pytest.approx(1.0)
    assert cohens_kappa(
        [("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")]
    ) == pytest.approx(0.0)
    assert cohens_kappa([("a", "b"), ("b", "a")]) == pytest.approx(-1.0)


def test_kappa_three_categories():
    # confusion: aa=2 ab=1 ba=0 bb=3 cc=2 (n=8): po=7/8
    pairs = [("a", "a")] * 2 + [("a", "b")] + [("b", "b")] * 3 + [("c", "c")] * 2
    # marginals rater1: a=3 b=3 c=2 ; rater2: a=2 b=4 c=2 -> pe=(6+12+4)/64
    pe = 22 / 64
    assert cohens_kappa(pairs) == pytest.approx((7 / 8 - pe) / (1 - pe))


def test_kappa_degenerate_cases():
    assert cohens_kappa([]) is None
    assert percent_agreement([]) is None
    assert cohens_kappa([("a", "a")] * 4) == 1.0  # single label, full agreement


def test_binary_metrics_known_values():
    pairs = (
        [(True, True)] * 40
        + [(True, False)] * 10
        + [(False, False)] * 30
        + [(False, True)] * 20
    )
    m = binary_metrics(pairs)
    assert (m.tp, m.fp, m.tn, m.fn, m.n) == (40, 10, 30, 20, 100)
    assert m.accuracy == pytest.approx(0.7)
    assert m.sensitivity == pytest.approx(40 / 60)
    assert m.specificity == pytest.approx(0.75)
    assert m.kappa == pytest.approx(0.4)


def test_binary_metrics_empty_and_undefined_denominators():
    m = binary_metrics([])
    assert m.accuracy is None and m.kappa is None
    only_pos = binary_metrics([(True, True)])
    assert only_pos.sensitivity == 1.0
    assert only_pos.specificity is None


def test_single_reviewer_include_settles():
    s = evaluate_stage([_v(1, 10, D.include)], 1)
    assert s.outcome == D.include and not s.conflict and s.deciding_id == 1


def test_single_reviewer_uncertain_stays_pending():
    s = evaluate_stage([_v(1, 10, D.uncertain)], 1)
    assert s.outcome is None and not s.conflict


def test_dual_waits_for_second_reviewer():
    s = evaluate_stage([_v(1, 10, D.include)], 2)
    assert s.outcome is None and not s.conflict


def test_dual_agreement_settles():
    s = evaluate_stage([_v(1, 10, D.exclude), _v(2, 11, D.exclude)], 2)
    assert s.outcome == D.exclude and s.deciding_id == 2 and not s.conflict


def test_dual_disagreement_is_conflict():
    s = evaluate_stage([_v(1, 10, D.include), _v(2, 11, D.exclude)], 2)
    assert s.outcome is None and s.conflict


def test_dual_both_uncertain_is_conflict():
    s = evaluate_stage([_v(1, 10, D.uncertain), _v(2, 11, D.uncertain)], 2)
    assert s.conflict


def test_only_latest_vote_per_reviewer_counts():
    votes = [_v(1, 10, D.include), _v(2, 11, D.exclude), _v(3, 11, D.include)]
    s = evaluate_stage(votes, 2)
    assert s.outcome == D.include and not s.conflict


def test_resolution_settles_a_conflict():
    votes = [_v(1, 10, D.include), _v(2, 11, D.exclude), _v(3, 99, D.exclude, True)]
    s = evaluate_stage(votes, 2)
    assert s.outcome == D.exclude and s.is_resolution and not s.conflict
