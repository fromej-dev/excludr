"""Queue order of ``GET /screening/next`` and ``pending_for_me``."""

import pytest
from sqlalchemy.dialects import postgresql
from sqlmodel import select

from app.features.projects.models import ProjectRole
from app.features.research.models import Article, ArticleStatus
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)
from app.features.screening.queue import (
    RANDOM_MOD,
    QueueMode,
    queue_order,
    random_key,
    random_key_expr,
    ranked_clauses,
)

BASE = "api/v1/projects"
TA = ScreeningStage.title_abstract


def _prioritize(session, project, min_random=0):
    project.prioritized_screening = True
    project.ranking_min_random = min_random
    session.add(project)
    session.commit()


def _human(session, article, user, decision="exclude", stage=TA):
    session.add(
        ScreeningDecision(
            article_id=article.id,
            reviewer_id=user.id,
            stage=stage,
            decision=ScreeningDecisionType(decision),
            source=DecisionSource.human,
        )
    )
    session.commit()


def _settle(session, article, user):
    _human(session, article, user)
    article.status = ArticleStatus.excluded
    article.current_stage = ScreeningStage.completed
    session.add(article)
    session.commit()


def _scored(an_article_in, project, scores, **kwargs):
    return [
        an_article_in(project, title=f"T{i}", relevance_score=s, **kwargs)
        for i, s in enumerate(scores)
    ]


def _next(client, project, stage="title_abstract"):
    res = client.get(f"{BASE}/{project.id}/screening/next", params={"stage": stage})
    assert res.status_code == 200
    return res.json()


def _queue(client, project, **params):
    res = client.get(
        f"{BASE}/{project.id}/articles", params={"pending_for_me": True, **params}
    )
    assert res.status_code == 200
    return [a["id"] for a in res.json()["data"]]


def _ids(articles):
    return [a.id for a in articles]


def test_random_key_sql_matches_python(auth_as, a_project, an_article_in, session):
    _, owner = auth_as()
    project = a_project(owner)
    for _ in range(8):
        an_article_in(project)
    rows = session.exec(select(Article.id, random_key_expr(project.id))).all()
    assert len(rows) == 8
    for article_id, key in rows:
        assert key == random_key(project.id, article_id)


def test_random_key_scrambles_and_depends_on_project():
    ids = list(range(1, 41))
    assert sorted(ids, key=lambda i: random_key(1, i)) != ids
    assert sorted(ids, key=lambda i: random_key(1, i)) != ids[::-1]
    assert sorted(ids, key=lambda i: random_key(1, i)) != sorted(
        ids, key=lambda i: random_key(2, i)
    )
    assert random_key(1, 7) == random_key(1, 7)
    assert all(0 <= random_key(3, i) < RANDOM_MOD for i in ids)
    # large ids stay within 64-bit arithmetic
    assert 0 <= random_key(10**6, 10**9) < RANDOM_MOD


def test_order_sql_postgres():
    dialect = postgresql.dialect()
    ranked = str(select(Article).order_by(*ranked_clauses()).compile(dialect=dialect))
    assert "relevance_score DESC NULLS LAST, article.id" in ranked
    rand = str(random_key_expr(1).compile(dialect=dialect))
    assert "CAST(article.id AS BIGINT)" in rand


@pytest.mark.parametrize(
    "prioritized, stage, min_random, settled, mode, remaining",
    [
        (False, TA, 2, 0, QueueMode.id, 0),
        (True, ScreeningStage.full_text, 0, 0, QueueMode.id, 0),
        (True, ScreeningStage.completed, 0, 0, QueueMode.id, 0),
        (True, TA, 0, 0, QueueMode.ranked, 0),
        (True, TA, 2, 1, QueueMode.random_start, 1),
        (True, TA, 2, 2, QueueMode.ranked, 0),
    ],
)
def test_queue_order_modes(
    auth_as,
    a_project,
    an_article_in,
    session,
    prioritized,
    stage,
    min_random,
    settled,
    mode,
    remaining,
):
    _, owner = auth_as()
    project = a_project(owner)
    for _ in range(settled):
        _settle(session, an_article_in(project), owner)
    project.prioritized_screening = prioritized
    project.ranking_min_random = min_random
    session.add(project)
    session.commit()
    order = queue_order(session, project, stage)
    assert order.mode == mode
    assert order.random_start_remaining == remaining


def test_off_serves_id_order(auth_as, a_project, an_article_in, session):
    client, owner = auth_as()
    project = a_project(owner)
    project.ranking_min_random = 5
    session.add(project)
    session.commit()
    a1, a2, a3 = _scored(an_article_in, project, [0.1, 0.9, 0.5])
    body = _next(client, project)
    assert body["article"]["id"] == a1.id
    assert body["queue_order"] == "id"
    assert body["random_start_remaining"] == 0
    assert _queue(client, project) == _ids([a1, a2, a3])


@pytest.fixture
def ranked(auth_as, a_project, an_article_in, session):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project)
    arts = _scored(an_article_in, project, [0.2, 0.9, None, 0.5, 0.9])
    return client, owner, project, arts


def test_ranked_next_and_pending_for_me(ranked):
    client, _, project, (a1, a2, a3, a4, a5) = ranked
    # the a2/a5 tie goes by id, NULL comes last
    assert _queue(client, project) == _ids([a2, a5, a4, a1, a3])
    body = _next(client, project)
    assert body["article"]["id"] == a2.id
    assert body["queue_order"] == "ranked"

    res = client.post(
        f"{BASE}/{project.id}/screening/articles/{a2.id}/decisions",
        json={"stage": "title_abstract", "decision": "exclude", "source": "human"},
    )
    assert res.status_code == 201
    assert _next(client, project)["article"]["id"] == a5.id
    assert _queue(client, project) == _ids([a5, a4, a1, a3])


def test_ranked_pagination_follows_order(ranked):
    client, _, project, (a1, _a2, _a3, a4, _a5) = ranked
    res = client.get(
        f"{BASE}/{project.id}/articles",
        params={"pending_for_me": True, "per_page": 2, "page": 2},
    )
    assert [a["id"] for a in res.json()["data"]] == [a4.id, a1.id]
    assert res.json()["meta"]["pagination"]["total_items"] == 5


def test_explicit_sort_overrides_queue_order(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project)
    # scores run opposite to the titles
    arts = [
        an_article_in(project, title=t, relevance_score=s)
        for t, s in [("a", 0.1), ("b", 0.5), ("c", 0.9)]
    ]
    assert _queue(client, project) == _ids(arts[::-1])
    assert _queue(client, project, sort_by="title", order="asc") == _ids(arts)
    assert _queue(client, project, sort_by="id", order="desc") == _ids(arts[::-1])


def test_full_text_unaffected_by_ranking(auth_as, a_project, an_article_in, session):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project)
    low, high = [
        an_article_in(
            project,
            status=ArticleStatus.full_text_retrieved,
            current_stage=ScreeningStage.full_text,
            relevance_score=s,
        )
        for s in (0.1, 0.9)
    ]
    body = _next(client, project, "full_text")
    assert body["article"]["id"] == low.id
    assert body["queue_order"] == "id"
    assert _queue(client, project, stage="full_text") == _ids([low, high])


def test_ranked_respects_dual_screening_exclusions(
    auth_as, a_project, a_member, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    project.required_reviewers = 2
    _prioritize(session, project)
    r1 = a_member(project, ProjectRole.reviewer)
    r2 = a_member(project, ProjectRole.reviewer)
    a_full, a_mine, a_other, a_low = _scored(
        an_article_in, project, [0.95, 0.9, 0.8, 0.1]
    )
    _human(session, a_full, r1, "include")
    _human(session, a_full, r2, "include")
    _human(session, a_mine, owner, "include")
    _human(session, a_other, r1, "include")

    assert _next(client, project)["article"]["id"] == a_other.id
    assert _queue(client, project) == _ids([a_other, a_low])
    auth_as(r1)
    assert _queue(client, project) == _ids([a_mine, a_low])


def test_random_start_order_same_in_next_and_list(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project, min_random=3)
    arts = _scored(an_article_in, project, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    expected = sorted(_ids(arts), key=lambda i: (random_key(project.id, i), i))
    assert _queue(client, project) == expected
    body = _next(client, project)
    assert body["article"]["id"] == expected[0]
    assert body["queue_order"] == "random_start"
    assert body["random_start_remaining"] == 3
    assert _queue(client, project) == expected


def test_random_start_ends_after_n_settled_project_wide(
    auth_as, a_project, a_member, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project, min_random=2)
    reviewer = a_member(project, ProjectRole.reviewer)
    a1, a2, a3, a4 = _scored(an_article_in, project, [0.1, 0.2, 0.3, 0.9])

    _settle(session, a1, owner)
    auth_as(reviewer)
    body = _next(client, project)
    assert body["queue_order"] == "random_start"
    assert body["random_start_remaining"] == 1

    _settle(session, a2, owner)
    body = _next(client, project)
    assert body["queue_order"] == "ranked"
    assert body["random_start_remaining"] == 0
    assert body["article"]["id"] == a4.id


def test_random_start_counts_only_settled_human_title_abstract(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project, min_random=1)

    ai_only = an_article_in(project, status=ArticleStatus.excluded)
    session.add(
        ScreeningDecision(
            article_id=ai_only.id,
            stage=TA,
            decision=ScreeningDecisionType.exclude,
            source=DecisionSource.ai_agent,
        )
    )
    uncertain = an_article_in(project)
    _human(session, uncertain, owner, "uncertain")
    one_vote = an_article_in(project)
    _human(session, one_vote, owner, "include")
    skipped = an_article_in(
        project, status=ArticleStatus.awaiting_full_text, title_abstract_skipped=True
    )
    _human(session, skipped, owner, "include")
    closed = an_article_in(
        project, status=ArticleStatus.excluded, not_screened_stopping_rule=True
    )
    _human(session, closed, owner, "exclude")
    full_text_only = an_article_in(project, status=ArticleStatus.included)
    _human(session, full_text_only, owner, "include", stage=ScreeningStage.full_text)
    session.commit()

    order = queue_order(session, project, TA)
    assert order.mode == QueueMode.random_start
    assert order.random_start_remaining == 1

    _settle(session, an_article_in(project), owner)
    assert queue_order(session, project, TA).mode == QueueMode.ranked


def test_random_start_counts_decisions_from_before_enabling(
    auth_as, a_project, an_article_in, session
):
    _, owner = auth_as()
    project = a_project(owner)
    _settle(session, an_article_in(project), owner)
    _settle(session, an_article_in(project), owner)
    _prioritize(session, project, min_random=2)
    assert queue_order(session, project, TA).mode == QueueMode.ranked


def test_next_empty_queue_reports_mode(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project)
    body = _next(client, project)
    assert body["article"] is None
    assert body["message"]
    assert body["queue_order"] == "ranked"
    assert body["random_start_remaining"] == 0
