"""Ranking engine: labels, text, scoring, retrain rule, writing, lock."""

import random
from contextlib import nullcontext
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlmodel import select

from app.core.config import get_settings
from app.features.criteria.models import Criterion, CriterionType
from app.features.research.models import Article, ArticleStatus
from app.features.screening import ranking
from app.features.screening.consensus import Vote
from app.features.screening.models import (
    DecisionSource,
    RankingRun,
    ScreeningDecision,
    ScreeningDecisionType as D,
    ScreeningStage,
)

TA = ScreeningStage.title_abstract


def _votes(*specs):
    """Specs are (reviewer_id, decision) or (reviewer_id, decision, True) for resolutions."""
    return [
        Vote(n, spec[0], spec[1], len(spec) > 2 and spec[2])
        for n, spec in enumerate(specs, start=1)
    ]


def _decide(
    session,
    article,
    reviewer,
    decision,
    resolution=False,
    source=DecisionSource.human,
    stage=TA,
):
    row = ScreeningDecision(
        article_id=article.id,
        reviewer_id=reviewer.id if reviewer else None,
        stage=stage,
        decision=decision,
        source=source,
        is_resolution=resolution,
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def ranking_on(session, monkeypatch):
    monkeypatch.setattr(ranking, "Session", lambda _engine: nullcontext(session))
    monkeypatch.setattr(get_settings(), "ranking_auto_retrain", True)
    monkeypatch.setattr(ranking, "run_inline", True)
    ranking.clear()
    yield session
    ranking.clear()


@pytest.fixture
def notifier(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(ranking.NotificationService, "notify_room", mock)
    return mock


# --- labels ---------------------------------------------------------------


@pytest.mark.parametrize(
    "specs,expected",
    [
        ([(1, D.include)], True),
        ([(1, D.exclude)], False),
        ([(1, D.uncertain)], None),
        ([(1, D.include), (1, D.exclude)], False),
    ],
)
def test_label_single_reviewer(specs, expected):
    assert ranking.label_from_votes(_votes(*specs), 1) is expected


def test_label_dual_agreement_and_pending():
    assert ranking.label_from_votes(_votes((1, D.include), (2, D.include)), 2) is True
    assert ranking.label_from_votes(_votes((1, D.exclude)), 2) is False
    assert ranking.label_from_votes(_votes((1, D.uncertain)), 2) is None
    assert (
        ranking.label_from_votes(_votes((1, D.exclude)), 2, settled_only=True) is None
    )


def test_label_dual_conflict_is_none():
    assert ranking.label_from_votes(_votes((1, D.include), (2, D.exclude)), 2) is None
    assert (
        ranking.label_from_votes(_votes((1, D.uncertain), (2, D.uncertain)), 2) is None
    )


def test_label_resolution_wins():
    votes = _votes((1, D.include), (2, D.exclude), (9, D.include, True))
    assert ranking.label_from_votes(votes, 2) is True


def test_collect_labels_rules(a_user, a_project, an_article_in, session):
    owner, r1, r2 = a_user(), a_user(), a_user()
    project = a_project(owner)
    project.required_reviewers = 2
    session.add(project)
    session.commit()

    def article(**kw):
        return an_article_in(project, status=ArticleStatus.awaiting_full_text, **kw)

    agreed_inc, agreed_exc = article(), article()
    conflict, uncertain, resolved = article(), article(), article()
    ai_only, skipped, ft_excluded = article(), article(), article()
    unsettled = an_article_in(project)  # still screening, one vote
    for a, d in ((agreed_inc, D.include), (agreed_exc, D.exclude)):
        _decide(session, a, r1, d)
        _decide(session, a, r2, d)
    _decide(session, conflict, r1, D.include)
    _decide(session, conflict, r2, D.exclude)
    _decide(session, uncertain, r1, D.uncertain)
    _decide(session, resolved, r1, D.include)
    _decide(session, resolved, r2, D.exclude)
    _decide(session, resolved, owner, D.exclude, resolution=True)
    _decide(session, ai_only, None, D.include, source=DecisionSource.ai_agent)
    skipped.title_abstract_skipped = True
    session.add(skipped)
    session.commit()
    _decide(session, skipped, r1, D.include)
    _decide(session, ft_excluded, r1, D.include)
    _decide(session, ft_excluded, r2, D.include)
    ft_excluded.status = ArticleStatus.excluded
    ft_excluded.current_stage = ScreeningStage.full_text
    session.add(ft_excluded)
    session.commit()
    _decide(session, ft_excluded, r1, D.exclude, stage=ScreeningStage.full_text)
    _decide(session, unsettled, r1, D.include)

    labels = ranking.collect_labels(session, project)
    assert labels == {
        agreed_inc.id: True,
        agreed_exc.id: False,
        resolved.id: False,
        ft_excluded.id: True,
    }


def test_collect_labels_single_reviewer_uses_unsettled_free_path(
    a_user, a_project, an_article_in, session
):
    owner = a_user()
    project = a_project(owner)
    a = an_article_in(project, status=ArticleStatus.awaiting_full_text)
    _decide(session, a, owner, D.include)
    assert ranking.collect_labels(session, project) == {a.id: True}


def test_collect_labels_dual_blinds_unsettled_in_screening(
    a_user, a_project, an_article_in, session
):
    owner, r1 = a_user(), a_user()
    project = a_project(owner)
    project.required_reviewers = 2
    session.add(project)
    session.commit()
    a = an_article_in(project)
    _decide(session, a, r1, D.include)
    assert ranking.collect_labels(session, project) == {}


# --- text -----------------------------------------------------------------


def test_article_text_handles_missing_fields():
    assert ranking.article_text(None, None, None, None) == ""
    assert ranking.article_text("", "", [], []) == ""
    text = ranking.article_text("T", "A", ["k1", "k2"], ["m1"])
    assert text == "T\nA\nk1; k2\nm1"


def test_query_text_uses_question_and_active_inclusion_criteria(a_project, session):
    project = a_project()
    project.review_question = "Does X help Y?"
    crit = [
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I2",
            description="second",
            order=2,
        ),
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="first",
            order=1,
        ),
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I3",
            description="inactive",
            order=3,
            is_active=False,
        ),
        Criterion(
            project_id=project.id,
            type=CriterionType.exclusion,
            code="E1",
            description="exclusion",
            order=0,
        ),
    ]
    assert ranking.query_text(project, crit) == "Does X help Y?\nfirst\nsecond"
    project.review_question = None
    assert ranking.query_text(project, []) == ""


def test_random_score_stable_and_in_range():
    a = ranking.random_score(1, 1)
    assert a == ranking.random_score(1, 1)
    assert 0 <= a < 1
    assert a != ranking.random_score(1, 2)
    assert a != ranking.random_score(2, 1)


# --- scoring --------------------------------------------------------------

POOL_A = "aerobic exercise depressive symptoms randomised trial adults mood".split()
OTHER_POOLS = [
    "cardiac stent myocardial infarction coronary artery surgery".split(),
    "dental caries enamel fluoride toothpaste children molar".split(),
    "school curriculum teachers pupils literacy classroom reform".split(),
    "crop yield wheat irrigation soil fertiliser harvest".split(),
]
FILLER = "study results methods conclusion patients group analysis data".split()


def _corpus():
    rng = random.Random(42)
    texts, relevant = {}, set()
    for i in range(1, 201):
        if i <= 30:
            words = rng.choices(POOL_A, k=25)
            relevant.add(i)
        else:
            words = rng.choices(OTHER_POOLS[i % 4], k=25)
        texts[i] = " ".join(words + rng.choices(FILLER, k=8))
    return texts, relevant


def test_synthetic_corpus_ranks_relevant_first():
    texts, relevant = _corpus()
    labels = {i: True for i in (1, 2, 3)} | {i: False for i in (31, 32, 33, 34, 35)}
    pending = [i for i in texts if i not in labels]
    scores = ranking.compute_scores(7, texts, pending, labels, "")
    assert scores.method == ranking.METHOD_MODEL
    ranked = sorted(pending, key=lambda i: -scores.by_article[i])
    pending_relevant = relevant - set(labels)
    assert len(pending_relevant) == 27
    assert len(set(ranked[:27]) & pending_relevant) >= 24
    rel = [scores.by_article[i] for i in pending_relevant]
    irr = [scores.by_article[i] for i in pending if i not in relevant]
    assert sum(rel) / len(rel) > sum(irr) / len(irr)
    worst_rank = max(ranked.index(i) for i in pending_relevant)
    assert worst_rank < 60


def test_cold_start_similarity_ranks_question_matches_first():
    texts, relevant = _corpus()
    pending = sorted(texts)
    query = "Aerobic exercise for depressive symptoms in adults"
    scores = ranking.compute_scores(7, texts, pending, {}, query)
    assert scores.method == ranking.METHOD_SIMILARITY
    ranked = sorted(pending, key=lambda i: -scores.by_article[i])
    assert len(set(ranked[:30]) & relevant) >= 25


@pytest.mark.parametrize(
    "texts,pending,labels",
    [
        ({}, [], {}),
        ({1: "alpha beta", 2: "beta gamma"}, [], {1: True, 2: False}),
        ({1: "alpha beta", 2: "beta gamma", 3: "delta"}, [1], {2: True, 3: False}),
        ({1: "apple pear", 2: "zebra lion"}, [1, 2], {}),
        ({1: "", 2: "", 3: ""}, [1, 2, 3], {}),
        ({1: "the and of", 2: "a an the"}, [1, 2], {}),
    ],
)
def test_compute_scores_tiny_corpora_do_not_crash(texts, pending, labels):
    scores = ranking.compute_scores(1, texts, pending, labels, "apple zebra")
    assert set(scores.by_article) == set(pending)
    assert scores.method in {
        ranking.METHOD_MODEL,
        ranking.METHOD_SIMILARITY,
        ranking.METHOD_RANDOM,
    }


def test_compute_scores_all_empty_is_random():
    scores = ranking.compute_scores(1, {1: "", 2: ""}, [1, 2], {}, "")
    assert scores.method == ranking.METHOD_RANDOM


def test_compute_scores_single_class_uses_similarity():
    texts = {
        1: "exercise depression adults trial",
        2: "dental caries fluoride",
        3: "wheat crop yield",
        4: "school curriculum",
    }
    scores = ranking.compute_scores(
        1, texts, [1, 2, 3], {4: False}, "exercise depression"
    )
    assert scores.method == ranking.METHOD_SIMILARITY
    assert max(scores.by_article, key=scores.by_article.get) == 1


def test_compute_scores_no_query_falls_back_to_random():
    texts = {1: "alpha beta", 2: "gamma delta"}
    scores = ranking.compute_scores(3, texts, [1, 2], {}, "")
    assert scores.method == ranking.METHOD_RANDOM
    assert scores.by_article == {
        1: ranking.random_score(3, 1),
        2: ranking.random_score(3, 2),
    }


def test_compute_scores_query_without_overlap_falls_back_to_random():
    texts = {1: "alpha beta", 2: "gamma delta"}
    scores = ranking.compute_scores(3, texts, [1, 2], {}, "completely unrelated words")
    assert scores.method == ranking.METHOD_RANDOM


# --- retrain rule ---------------------------------------------------------


def _run(method, inc, exc):
    return RankingRun(
        project_id=1,
        model_version="v",
        method=method,
        trigger="auto",
        labelled_includes=inc,
        labelled_excludes=exc,
    )


@pytest.mark.parametrize(
    "inc,exc,last,unscored,expected",
    [
        (0, 0, None, False, True),
        (0, 0, _run("random", 0, 0), True, True),
        (0, 7, _run("similarity", 0, 0), False, False),
        (1, 3, _run("similarity", 0, 3), False, True),
        (2, 3, _run("model", 1, 3), False, True),
        (0, 4, _run("model", 1, 3), False, True),
        (0, 4, _run("similarity", 0, 3), False, False),
        (1, 7, _run("model", 1, 3), False, False),
        (1, 8, _run("model", 1, 3), False, True),
        (1, 3, _run("model", 1, 3), False, False),
    ],
)
def test_should_retrain(inc, exc, last, unscored, expected):
    assert ranking.should_retrain(inc, exc, last, unscored) is expected


# --- orchestration --------------------------------------------------------


def _prioritized(a_project, session, owner=None):
    project = a_project(owner)
    project.prioritized_screening = True
    session.add(project)
    session.commit()
    return project


def test_rerank_project_scores_only_pending_ta(
    a_user, a_project, an_article_in, session
):
    owner = a_user()
    project = _prioritized(a_project, session, owner)
    other = _prioritized(a_project, session)
    pending = [
        an_article_in(project, title=f"title {n}", abstract=f"abs {n}")
        for n in range(4)
    ]
    waiting = an_article_in(
        project, status=ArticleStatus.awaiting_full_text, relevance_score=0.5
    )
    foreign = an_article_in(other)
    _decide(session, pending[0], owner, D.include)
    _decide(session, pending[1], owner, D.exclude)

    run = ranking.rerank_project(session, project.id, force=True)

    session.expire_all()
    assert run.model_version == "tfidf-logreg-v1"
    assert run.trigger == "auto"
    assert (run.labelled_includes, run.labelled_excludes) == (1, 1)
    assert run.scored == 4 and run.duration_ms >= 0
    assert all(session.get(Article, a.id).relevance_score is not None for a in pending)
    assert session.get(Article, waiting.id).relevance_score == 0.5
    assert session.get(Article, foreign.id).relevance_score is None


def test_rerank_project_skips_when_not_prioritized(a_project, an_article_in, session):
    project = a_project()
    an_article_in(project)
    assert ranking.rerank_project(session, project.id, force=True) is None
    assert session.exec(select(RankingRun)).all() == []


def test_rerank_project_no_pending_returns_none(a_project, session):
    project = _prioritized(a_project, session)
    assert ranking.rerank_project(session, project.id, force=True) is None


def test_rerank_project_throttled_returns_none_without_force(
    a_project, an_article_in, session
):
    project = _prioritized(a_project, session)
    an_article_in(project)
    assert ranking.rerank_project(session, project.id) is not None
    assert ranking.rerank_project(session, project.id) is None
    assert len(session.exec(select(RankingRun)).all()) == 1
    assert ranking.rerank_project(session, project.id, force=True) is not None
    assert len(session.exec(select(RankingRun)).all()) == 2


def test_write_scores_chunks_on_sqlite(a_project, an_article_in, session, monkeypatch):
    monkeypatch.setattr(ranking, "WRITE_CHUNK", 2)
    project = a_project()
    articles = [an_article_in(project) for _ in range(5)]
    ranking.write_scores(session, project.id, {a.id: a.id / 100 for a in articles})
    session.commit()
    session.expire_all()
    for a in articles:
        assert session.get(Article, a.id).relevance_score == pytest.approx(a.id / 100)


def test_write_scores_postgres_statement():
    stmt = ranking._pg_update_stmt(1, [(1, 0.5), (2, 0.25)])
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FROM (VALUES" in sql
    assert "article.project_id" in sql


# --- lock -----------------------------------------------------------------


def test_claim_coalesces_follow_ups():
    ranking.clear()
    auto = ranking.RerankRequest()
    assert ranking.claim(1, auto) is True
    assert ranking.claim(1, auto) is False
    manual = ranking.RerankRequest(ranking.TRIGGER_MANUAL, 7, True)
    assert ranking.claim(1, manual) is False
    assert ranking.next_request(1) == manual
    assert ranking.next_request(1) is None
    assert ranking.is_running(1) is False


@pytest.mark.asyncio
async def test_background_runs_follow_up_once(ranking_on, notifier, monkeypatch):
    calls = []

    def fake(project_id, request):
        calls.append(request)
        if len(calls) == 1:
            ranking.claim(project_id, ranking.RerankRequest())  # decision mid-run
        return None

    monkeypatch.setattr(ranking, "_run_once", fake)
    await ranking.rerank_in_background(5)
    assert len(calls) == 2
    assert ranking.is_running(5) is False


@pytest.mark.asyncio
async def test_background_failure_releases_and_notifies(
    ranking_on, notifier, monkeypatch
):
    def boom(project_id, request):
        raise RuntimeError("nope")

    monkeypatch.setattr(ranking, "_run_once", boom)
    await ranking.rerank_in_background(5)
    assert ranking.is_running(5) is False
    assert notifier.await_args.kwargs["data"]["type"] == "ranking_failed"


def test_write_scores_leaves_updated_at_and_other_projects(
    a_project, an_article_in, session
):
    from datetime import datetime, timezone

    project, other = a_project(), a_project()
    mine, foreign = an_article_in(project), an_article_in(other)
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for a in (mine, foreign):
        a.updated_at = old
        session.add(a)
    session.commit()
    ranking.write_scores(session, project.id, {mine.id: 0.7, foreign.id: 0.9})
    session.commit()
    session.expire_all()
    assert session.get(Article, mine.id).relevance_score == pytest.approx(0.7)
    assert session.get(Article, mine.id).updated_at == old
    assert session.get(Article, foreign.id).relevance_score is None  # project guard


def test_matrix_cache_reused_until_corpus_changes(monkeypatch):
    ranking.clear()
    calls = []
    real = ranking._fit_matrix
    monkeypatch.setattr(
        ranking, "_fit_matrix", lambda docs: calls.append(1) or real(docs)
    )
    texts = {1: "alpha beta", 2: "beta gamma", 3: "gamma delta", 4: "delta alpha"}
    first = ranking.compute_scores(1, texts, [3, 4], {1: True, 2: False}, "")
    second = ranking.compute_scores(1, texts, [3, 4], {1: False, 2: True}, "")
    assert len(calls) == 1 and first.method == second.method == ranking.METHOD_MODEL
    ranking.compute_scores(
        1, {**texts, 4: "changed text"}, [3, 4], {1: True, 2: False}, ""
    )
    assert len(calls) == 2
    for pid in range(10, 20):
        ranking.compute_scores(pid, texts, [3, 4], {1: True, 2: False}, "")
    assert len(ranking._matrix_cache) == ranking.MATRIX_CACHE_SIZE


@pytest.mark.asyncio
async def test_background_hands_off_without_blocking(ranking_on, notifier, monkeypatch):
    import asyncio
    import threading

    monkeypatch.setattr(ranking, "run_inline", False)
    gate, used = threading.Event(), []

    def fake(project_id, request):
        used.append(threading.current_thread().name)
        gate.wait(5)
        return None

    monkeypatch.setattr(ranking, "_run_once", fake)
    await ranking.rerank_in_background(5)  # returns before the worker finishes
    assert ranking.is_running(5) and not gate.is_set()
    gate.set()
    await asyncio.gather(*list(ranking._tasks))
    assert ranking.is_running(5) is False and used


def test_run_once_opens_its_own_session(a_project, an_article_in, session, monkeypatch):
    opened = []

    def factory(bind):
        opened.append(bind)
        return nullcontext(session)

    monkeypatch.setattr(ranking, "Session", factory)
    project = a_project()
    project.prioritized_screening = True
    session.add(project)
    session.commit()
    an_article_in(project)
    assert ranking._run_once(project.id, ranking.RerankRequest()) is not None
    assert opened == [ranking.engine]
