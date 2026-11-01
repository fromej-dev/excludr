"""Methods sentence on prioritized screening (pure function, no database)."""

from dataclasses import replace

import pytest

from app.features.reporting.methods import (
    MODEL_DESCRIPTIONS,
    AppliedRule,
    MethodInputs,
    screening_method_sentence,
)

BASE = MethodInputs(
    ranking_runs=3,
    model_version="tfidf-logreg-v1",
    cold_start_method=None,
    min_random=0,
    prioritized=True,
    threshold=2,
    not_screened=1,
    applied=AppliedRule(2, 2, 2, False, None),
)

PART_A = (
    "Title and abstract screening was prioritized with active learning: records were "
    "presented in order of predicted relevance, estimated by a logistic regression "
    "classifier on TF-IDF features of titles, abstracts and keywords that was "
    "retrained on the reviewers' title and abstract decisions during screening "
    "(Excludr ranking model tfidf-logreg-v1)."
)
REMAINING = (
    "not screened (reported as marked ineligible by automation tools in the PRISMA "
    "flow diagram)."
)
COLD = (
    "Title and abstract screening used prioritized ordering, but no relevance model "
    "could be trained (this needs at least one included and one excluded record), "
    "so records were presented "
)


def test_canonical_sentence():
    assert screening_method_sentence(BASE) == (
        PART_A
        + " Screening stopped when the stopping rule was met: 2 consecutive records "
        "were excluded (rule: 2 consecutive exclusions) after 2 records had been "
        "screened. The remaining 1 record was " + REMAINING
    )


@pytest.mark.parametrize("prioritized", [True, False])
def test_none_when_never_used(prioritized):
    i = replace(BASE, ranking_runs=0, not_screened=0, prioritized=prioritized)
    assert screening_method_sentence(i) is None


@pytest.mark.parametrize(
    "k,text",
    [
        (
            50,
            "after the first 50 records, which were presented in random order, "
            "records were presented in order of predicted relevance",
        ),
        (1, "after the first 1 record, which was presented in random order"),
    ],
)
def test_min_random_prefix(k, text):
    assert text in screening_method_sentence(replace(BASE, min_random=k))


def test_unknown_model_version():
    s = screening_method_sentence(replace(BASE, model_version="x-v9"))
    assert "estimated by a machine-learning model that was retrained" in s
    assert "(Excludr ranking model x-v9)" in s


@pytest.mark.parametrize(
    "method,how",
    [
        (
            "similarity",
            "in order of text similarity to the review question and inclusion criteria.",
        ),
        ("random", "in random order."),
    ],
)
def test_cold_start_variants(method, how):
    i = replace(
        BASE,
        model_version=None,
        cold_start_method=method,
        not_screened=0,
        applied=None,
        prioritized=False,
    )
    assert screening_method_sentence(i) == COLD + how


def test_forced_with_reason():
    i = replace(
        BASE,
        applied=AppliedRule(100, 0, 10, True, "Time-boxed review."),
        not_screened=5,
    )
    s = screening_method_sentence(i)
    assert s.endswith(
        "Screening stopped before the stopping rule (100 consecutive exclusions) was "
        "met, after 0 consecutive exclusions and 10 screened records (reason: "
        "Time-boxed review). The remaining 5 records were " + REMAINING
    )


def test_rule_set_not_applied():
    i = replace(BASE, not_screened=0, applied=None)
    assert screening_method_sentence(i).endswith(
        "A stopping rule (2 consecutive exclusions) was set but has not been applied."
    )
    off = screening_method_sentence(replace(i, prioritized=False))
    assert off.endswith("(Excludr ranking model tfidf-logreg-v1).")
    none = screening_method_sentence(replace(i, threshold=None))
    assert none.endswith("(Excludr ranking model tfidf-logreg-v1).")


def test_fallback_without_event():
    i = replace(BASE, applied=None, not_screened=3)
    assert (
        "Screening stopped early using a stopping rule (2 consecutive exclusions). "
        "The remaining 3 records were not screened"
    ) in screening_method_sentence(i)
    assert "Screening stopped early. The remaining 3 records" in (
        screening_method_sentence(replace(i, threshold=None))
    )


def test_stopping_only_without_ranking_runs():
    i = replace(BASE, ranking_runs=0, model_version=None)
    assert screening_method_sentence(i).startswith(
        "Title and abstract screening stopped when the stopping rule was met"
    )


def test_applied_rule_from_malformed_details():
    bad = {
        "threshold": "x",
        "consecutive_excludes": True,
        "forced": "yes",
        "reason": "  ",
    }
    for details in (bad, None):
        assert AppliedRule.from_details(details) == AppliedRule(
            None, None, None, False, None
        )
    s = screening_method_sentence(replace(BASE, applied=AppliedRule.from_details(bad)))
    assert "(rule: 2 consecutive exclusions)" in s
    assert "had been screened" not in s


def test_model_descriptions_cover_current_version():
    from app.features.screening import ranking

    assert ranking.MODEL_VERSION in MODEL_DESCRIPTIONS
