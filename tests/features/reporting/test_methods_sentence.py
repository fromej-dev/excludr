"""Methods sentence on prioritized screening (pure function, no database)."""

from dataclasses import replace

import pytest

from app.features.projects.models import StoppingRuleType
from app.features.reporting.methods import (
    CALLAGHAN_2020_REFERENCE,
    MODEL_DESCRIPTIONS,
    AppliedRule,
    MethodInputs,
    screening_method_reference,
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
        + " Screening stopped when the stopping rule was met after 2 records had "
        "been screened: the last 2 consecutive records were excluded (rule: 2 "
        "consecutive exclusions). The remaining 1 record was " + REMAINING
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
    i = replace(BASE, not_screened=0, applied=None, awaiting_screening=4)
    assert screening_method_sentence(i).endswith(
        "A stopping rule (2 consecutive exclusions) was set but has not been applied."
    )
    off = screening_method_sentence(replace(i, prioritized=False))
    assert off.endswith("(Excludr ranking model tfidf-logreg-v1).")
    none = screening_method_sentence(replace(i, threshold=None))
    assert none.endswith("(Excludr ranking model tfidf-logreg-v1).")


def test_rule_not_mentioned_when_screening_finished():
    i = replace(BASE, not_screened=0, applied=None, awaiting_screening=0)
    assert screening_method_sentence(i) == PART_A


def test_several_applications_noted():
    s = screening_method_sentence(replace(BASE, applications=3))
    assert s.endswith(
        "(The rule was applied 3 times; figures are from the last application.)"
    )


def test_fallback_ignores_threshold_when_prioritization_off():
    i = replace(BASE, applied=None, not_screened=3, prioritized=False)
    assert "Screening stopped early. The remaining 3 records" in (
        screening_method_sentence(i)
    )


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


# --- statistical stopping criterion ---------------------------------------

STAT = replace(
    BASE,
    rule_type=StoppingRuleType.statistical,
    threshold=None,
    not_screened=9188,
    applied=AppliedRule(
        None,
        0,
        4812,
        False,
        None,
        rule_type=StoppingRuleType.statistical,
        recall_target=0.95,
        alpha=0.05,
        p_value=0.031,
        relevant_found=312,
    ),
)
STAT_REMAINING = (
    "The remaining 9,188 records were not screened (reported as marked ineligible "
    "by automation tools in the PRISMA flow diagram)."
)


def test_statistical_met_sentence():
    assert screening_method_sentence(STAT) == (
        PART_A
        + " Screening stopped when the statistical stopping criterion of Callaghan "
        "and Müller-Hansen (2020) was met after 4,812 records had been screened "
        "(312 included at title and abstract): treating the most recently screened "
        "records as if they were a random sample of the records not yet screened "
        "(ranked quasi-sampling), the null hypothesis that "
        "title and abstract screening had reached a recall below 95% was rejected "
        "at a significance level of 0.05 (p = 0.031). " + STAT_REMAINING
    )


def test_statistical_forced_sentence():
    applied = replace(
        STAT.applied, forced=True, p_value=0.21, screened=2104, reason="Out of time."
    )
    assert screening_method_sentence(replace(STAT, applied=applied)) == (
        PART_A
        + " Screening stopped before the statistical stopping criterion of Callaghan "
        "and Müller-Hansen (2020) was met (null hypothesis of recall below 95%, "
        "significance level 0.05: p = 0.21), after 2,104 screened records "
        "(reason: Out of time). " + STAT_REMAINING
    )


def test_statistical_set_not_applied_sentence():
    i = replace(STAT, not_screened=0, applied=None, awaiting_screening=5)
    assert screening_method_sentence(i) == (
        PART_A
        + " A statistical stopping criterion (Callaghan and Müller-Hansen, 2020; "
        "recall target 95%, significance level 0.05) was set but has not been "
        "applied."
    )


def test_statistical_fallback_without_event():
    i = replace(STAT, applied=None)
    assert screening_method_sentence(i) == (
        PART_A + " Screening stopped early using a statistical stopping criterion "
        "(Callaghan and Müller-Hansen, 2020; recall target 95%, significance level "
        "0.05). " + STAT_REMAINING
    )


def test_statistical_event_wins_over_current_setting():
    i = replace(STAT, rule_type=StoppingRuleType.consecutive)
    assert "Callaghan" in screening_method_sentence(i)
    consecutive = replace(BASE, rule_type=StoppingRuleType.statistical)
    assert "Callaghan" not in screening_method_sentence(consecutive)


def test_statistical_multiple_applications_suffix():
    text = screening_method_sentence(replace(STAT, applications=3))
    assert text.endswith(
        "(The rule was applied 3 times; figures are from the last application.)"
    )


@pytest.mark.parametrize(
    "p,expected",
    [
        (0.0004, "p < 0.001"),
        (0.0, "p < 0.001"),
        (0.031, "p = 0.031"),
        (0.21, "p = 0.21"),
        (0.0099, "p = 0.0099"),
    ],
)
def test_p_formatting(p, expected):
    applied = replace(STAT.applied, p_value=p)
    assert f"({expected})." in screening_method_sentence(replace(STAT, applied=applied))


@pytest.mark.parametrize(
    "target,expected", [(0.95, "95%"), (0.975, "97.5%"), (0.8, "80%")]
)
def test_target_formatting(target, expected):
    applied = replace(STAT.applied, recall_target=target)
    text = screening_method_sentence(replace(STAT, applied=applied))
    assert f"recall below {expected} was rejected" in text


def test_applied_rule_parses_statistical_details_defensively():
    good = AppliedRule.from_details(
        {
            "rule_type": "statistical",
            "recall_target": 0.9,
            "alpha": 0.01,
            "p_value": 0.5,
            "relevant_found": 7,
        }
    )
    assert good.rule_type == StoppingRuleType.statistical
    assert (good.recall_target, good.alpha, good.p_value, good.relevant_found) == (
        0.9,
        0.01,
        0.5,
        7,
    )
    bad = AppliedRule.from_details(
        {
            "rule_type": "other",
            "recall_target": True,
            "alpha": "0.05",
            "p_value": float("nan"),
            "relevant_found": True,
        }
    )
    assert bad.rule_type == StoppingRuleType.consecutive
    assert bad.recall_target is bad.alpha is bad.p_value is bad.relevant_found is None
    out = AppliedRule.from_details(
        {"recall_target": 7, "p_value": -0.1, "alpha": float("inf")}
    )
    assert out.recall_target is out.p_value is out.alpha is None
    old = AppliedRule.from_details({"threshold": 5, "forced": False})
    assert old.rule_type == StoppingRuleType.consecutive


def test_reference_present_only_for_statistical():
    assert screening_method_reference(STAT) == CALLAGHAN_2020_REFERENCE
    assert "10.1186/s13643-020-01521-4" in CALLAGHAN_2020_REFERENCE
    assert screening_method_reference(BASE) is None
    assert (
        screening_method_reference(replace(BASE, ranking_runs=0, not_screened=0))
        is None
    )


def test_p_never_rounds_across_alpha():
    for p, expected in (
        (0.04995, "p = 0.04995"),
        (0.0499, "p = 0.0499"),
        (0.0501, "p = 0.05"),
    ):
        applied = replace(STAT.applied, p_value=p)
        text = screening_method_sentence(replace(STAT, applied=applied))
        assert f"({expected})." in text, text
