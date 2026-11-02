"""Statistical stopping rule: the pure hypergeometric recall test (no database).

The oracle is a port of ``buscarpy.calculate_h0`` (bias = 1, buscarpy 0.0.2,
https://github.com/mcallaghan/buscarpy) of Callaghan and Mueller-Hansen (2020), doi
10.1186/s13643-020-01521-4, with the one fix described in the design (H0 impossible
where K_tar exceeds the population gives p = 0 instead of NaN).
"""

import time

import numpy as np
import pytest
from scipy.stats import hypergeom

from app.features.screening.stopping import (
    excludes_needed,
    min_missed_under_h0,
    recall_test,
)


def buscar_h0(labels, n_total, recall_target=0.95):
    """Port of ``buscarpy.calculate_h0`` (all windows of the last n records)."""
    labels = np.array(labels, dtype=np.int64)
    r_seen = labels.sum()
    urns = labels[::-1]
    sizes = np.arange(urns.shape[0]) + 1
    k_hat = np.floor(r_seen / recall_target + 1 - (r_seen - urns.cumsum()))
    population = n_total - (urns.shape[0] - sizes)
    p = np.where(
        k_hat > population,
        0.0,
        hypergeom.cdf(urns.cumsum(), population, np.minimum(k_hat, population), sizes),
    )
    return float(p.min()), p


def brute(window, before, seen_before, unscreened, target, alpha=0.05):
    """All windows through ``recall_test`` pieces, without the include-anchored pruning."""
    w = np.asarray(window)
    labels = np.concatenate(
        (np.ones(before, int), np.zeros(seen_before - before, int), w)
    )
    total = len(labels) + unscreened
    _, p = buscar_h0(labels, total, target)
    return float(p[: len(w)].min()) if len(w) else None


def kwargs(window=(), before=0, seen_before=0, unscreened=0, target=0.95, alpha=0.05):
    return dict(
        relevant_before=before,
        screened_before=seen_before,
        unscreened=unscreened,
        recall_target=target,
        alpha=alpha,
    )


def seq(includes, excludes, includes_first=True):
    inc, exc = [1] * includes, [0] * excludes
    return np.array(inc + exc if includes_first else exc + inc)


def test_min_missed_matches_paper_examples():
    assert min_missed_under_h0(45, 0.95) == 3  # Radjenovic: "3 or more"
    assert min_missed_under_h0(231, 0.95) == 13  # Proton Beam: "a minimum of 13"
    assert min_missed_under_h0(19, 0.95) == 2  # exact boundary: 19/20 is not < 0.95
    assert min_missed_under_h0(20, 0.95) == 2
    assert min_missed_under_h0(10, 0.95) == 1
    assert min_missed_under_h0(100, 0.90) == 12
    assert min_missed_under_h0(1, 0.95) == 1


def test_closed_form_one_missing():
    w = seq(10, 500)
    res = recall_test(w, **kwargs(unscreened=1000))
    assert res.p_value == pytest.approx(1000 / 1500, rel=1e-9)
    assert not res.met and res.reason == "ok"
    assert excludes_needed(w, **kwargs(unscreened=1000)) == 926


def test_closed_form_two_missing():
    w = seq(20, 900)
    res = recall_test(w, **kwargs(unscreened=100))
    assert res.p_value == pytest.approx(100 * 99 / (1000 * 999), rel=1e-9)
    assert res.met and res.min_missed_under_h0 == 2
    assert excludes_needed(w, **kwargs(unscreened=100)) == 0


def test_matches_buscarpy_cases():
    w = seq(19, 281)
    res = recall_test(w, **kwargs(unscreened=700))
    assert res.p_value == pytest.approx(0.508955875928353, rel=1e-9)
    assert excludes_needed(w, **kwargs(unscreened=700)) == 481

    w = seq(3, 60)
    res = recall_test(w, **kwargs(unscreened=37))
    assert res.p_value == pytest.approx(0.38144329896907214, rel=1e-9)
    assert excludes_needed(w, **kwargs(unscreened=37)) == 33

    rng = np.random.default_rng(1)
    a = np.zeros(1000, int)
    a[rng.choice(300, 30, replace=False)] = 1
    b = np.zeros(400, int)
    b[:20] = 1
    b[-1] = 1
    for labels, total in ((a, 5000), (b, 2000)):
        res = recall_test(labels, **kwargs(unscreened=total - len(labels)))
        assert res.p_value == pytest.approx(buscar_h0(labels, total)[0], rel=1e-9)


def test_window_equals_buscarpy_restricted():
    rng = np.random.default_rng(1)
    labels = np.zeros(1000, int)
    labels[rng.choice(300, 30, replace=False)] = 1
    _, p = buscar_h0(labels, 5000)
    window = labels[600:]
    res = recall_test(
        window,
        **kwargs(before=int(labels[:600].sum()), seen_before=600, unscreened=4000),
    )
    assert res.p_value == pytest.approx(float(p[:400].min()), rel=1e-9)
    assert res.p_value == pytest.approx(0.8264274938519085, rel=1e-9)
    assert res.sample_size == 400 and res.screened == 1000


def test_pruning_equals_brute_force():
    rng = np.random.default_rng(7)
    for _ in range(500):
        length = int(rng.integers(1, 301))
        window = (rng.random(length) < rng.uniform(0, 0.3)).astype(int)
        seen_before = int(rng.integers(0, 200))
        before = int(rng.integers(0, seen_before + 1)) if seen_before else 0
        unscreened = int(rng.integers(0, 2001))
        target = float(rng.choice([0.8, 0.9, 0.95, 0.99]))
        if before + window.sum() == 0:
            continue
        res = recall_test(
            window,
            **kwargs(
                before=before,
                seen_before=seen_before,
                unscreened=unscreened,
                target=target,
            ),
        )
        expected = brute(window, before, seen_before, unscreened, target)
        assert res.p_value == pytest.approx(
            0.0 if unscreened == 0 else expected, abs=1e-12
        )


def test_zero_relevant_not_met():
    w = np.zeros(300, int)
    res = recall_test(w, **kwargs(unscreened=100))
    assert res.p_value == pytest.approx(0.25)
    assert res.met is False and res.reason == "no_relevant"
    assert excludes_needed(w, **kwargs(unscreened=100)) is None


def test_empty_window():
    res = recall_test([], **kwargs(before=5, seen_before=50, unscreened=10))
    assert res.p_value is None and res.met is False and res.reason == "no_sample"
    assert res.relevant_found == 5 and res.screened == 50 and res.sample_size == 0


def test_nothing_left():
    res = recall_test(seq(10, 90), **kwargs(unscreened=0))
    assert res.p_value == 0 and res.met is True and res.reason == "nothing_left"


def test_k_tar_above_population_is_zero_not_nan():
    res = recall_test([0], **kwargs(before=100, seen_before=100, unscreened=1))
    assert res.p_value == 0.0 and res.met is True


def test_alpha_is_strict():
    window = np.zeros(19, int)
    base = kwargs(before=10, seen_before=10, unscreened=1)
    res = recall_test(window, **base)
    assert res.p_value == pytest.approx(1 / 20, abs=1e-12)
    strict = recall_test(window, **{**base, "alpha": res.p_value})
    assert strict.met is False
    looser = recall_test(window, **{**base, "alpha": res.p_value + 1e-9})
    assert looser.met is True


@pytest.mark.parametrize(
    "window,before,seen_before,unscreened",
    [
        (seq(5, 120), 0, 0, 800),
        (np.array([1, 0] * 20 + [0] * 150), 8, 60, 500),
        (np.concatenate((seq(30, 30), seq(1, 90, False))), 3, 100, 1500),
    ],
)
def test_excludes_needed_is_minimal_and_monotone(
    window, before, seen_before, unscreened
):
    kw = kwargs(before=before, seen_before=seen_before, unscreened=unscreened)

    def exact(m):
        """Unrestricted p after appending m excludes."""
        w = np.concatenate((window, np.zeros(m, int)))
        return brute(w, before, seen_before, unscreened - m, 0.95)

    needed = excludes_needed(window, **kw)
    assert exact(needed) < 0.05
    assert needed == 0 or exact(needed - 1) >= 0.05  # exact when few includes
    assert needed >= min(m for m in range(unscreened + 1) if exact(m) < 0.05)


def test_excludes_needed_over_estimates_with_many_includes():
    window = np.concatenate(
        (np.ones(60, int), np.zeros(5, int), np.ones(40, int), np.zeros(10, int))
    )
    kw = kwargs(unscreened=400)
    restricted = excludes_needed(window, **kw, max_candidates=2)
    full = excludes_needed(window, **kw, max_candidates=1000)
    assert restricted >= full


def test_performance_50k():
    rng = np.random.default_rng(3)
    labels = np.zeros(50_000, int)
    labels[rng.choice(5000, 400, replace=False)] = 1
    recall_test(labels[:10], **kwargs(unscreened=10))  # warm scipy import
    start = time.perf_counter()
    res = recall_test(labels, **kwargs(unscreened=10_000))
    needed = excludes_needed(labels, **kwargs(unscreened=10_000))
    assert time.perf_counter() - start < 2.0
    assert res.p_value is not None and needed is not None
