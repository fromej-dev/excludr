"""Automatic and manual re-ranking through the HTTP API."""

import pytest
from sqlmodel import select

from app.core.config import get_settings
from app.features.audit.models import AuditEvent
from app.features.criteria.models import Criterion, CriterionType
from app.features.projects.models import ProjectRole
from app.features.research.models import Article, ArticleStatus
from app.features.screening import ranking
from app.features.screening.models import RankingRun, ScreeningStage

from .test_ranking import notifier, ranking_on  # noqa: F401

BASE = "api/v1/projects"
TOPICS = ["exercise mood", "dental caries", "wheat yield", "school reform"]


@pytest.fixture
def setup(auth_as, a_project, an_article_in, session, ranking_on, notifier):  # noqa: F811
    client, owner = auth_as()
    project = a_project(owner)
    project.prioritized_screening = True
    project.review_question = "Exercise for mood"
    session.add(project)
    session.add(
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="exercise intervention",
        )
    )
    session.commit()

    class S:
        pass

    s = S()
    s.client, s.owner, s.project = client, owner, project
    s.articles = [
        an_article_in(
            project, title=f"{TOPICS[n % 4]} {n}", abstract=f"{TOPICS[n % 4]} study"
        )
        for n in range(16)
    ]
    s.notifier = notifier
    return s


def _decide(s, article, decision, stage="title_abstract", source="human"):
    return s.client.post(
        f"{BASE}/{s.project.id}/screening/articles/{article.id}/decisions",
        json={"stage": stage, "decision": decision, "source": source},
    )


def _runs(session, project):
    session.expire_all()
    return session.exec(
        select(RankingRun)
        .where(RankingRun.project_id == project.id)
        .order_by(RankingRun.id)
    ).all()


def test_first_decision_creates_run(setup, session):
    assert _decide(setup, setup.articles[0], "exclude").status_code == 201
    (run,) = _runs(session, setup.project)
    assert run.trigger == "auto" and run.triggered_by == setup.owner.id
    pending = session.exec(
        select(Article).where(
            Article.project_id == setup.project.id,
            Article.status == ArticleStatus.screening,
        )
    ).all()
    assert pending and all(a.relevance_score is not None for a in pending)
    data = setup.notifier.await_args.kwargs["data"]
    assert data["type"] == "ranking_updated" and data["auto"] is True


def test_retrain_throttled_every_five_labels_or_on_include(setup, session):
    a = setup.articles
    _decide(setup, a[0], "exclude")
    assert len(_runs(session, setup.project)) == 1
    for i in range(1, 5):
        _decide(setup, a[i], "exclude")
    assert len(_runs(session, setup.project)) == 1
    _decide(setup, a[5], "include")
    runs = _runs(session, setup.project)
    assert len(runs) == 2 and runs[-1].method == "model"
    for i in range(6, 10):
        _decide(setup, a[i], "exclude")
    assert len(_runs(session, setup.project)) == 2
    _decide(setup, a[10], "exclude")
    assert len(_runs(session, setup.project)) == 3
    _decide(setup, a[11], "include")
    assert len(_runs(session, setup.project)) == 4


def test_full_text_decision_does_not_trigger(setup, session):
    article = setup.articles[0]
    article.status = ArticleStatus.full_text_retrieved
    article.current_stage = ScreeningStage.full_text
    session.add(article)
    session.commit()
    assert _decide(setup, article, "include", stage="full_text").status_code == 201
    assert _runs(session, setup.project) == []


def test_ai_decision_does_not_trigger(setup, session):
    assert (
        _decide(setup, setup.articles[0], "include", source="ai_agent").status_code
        == 201
    )
    assert _runs(session, setup.project) == []


def test_resolution_triggers(setup, session, a_member, auth_as):
    setup.project.required_reviewers = 2
    session.add(setup.project)
    session.commit()
    r1 = a_member(setup.project, ProjectRole.reviewer)
    r2 = a_member(setup.project, ProjectRole.reviewer)
    article, agreed = setup.articles[0], setup.articles[1]
    for reviewer in (r1, r2):
        auth_as(reviewer)
        _decide(setup, agreed, "exclude")
    auth_as(r1)
    _decide(setup, article, "include")
    auth_as(r2)
    _decide(setup, article, "exclude")
    before = len(_runs(session, setup.project))
    auth_as(setup.owner)
    res = setup.client.post(
        f"{BASE}/{setup.project.id}/screening/articles/{article.id}/resolve",
        json={"decision": "include", "reason": "relevant"},
    )
    assert res.status_code == 200
    runs = _runs(session, setup.project)
    assert len(runs) == before + 1
    assert (runs[-1].labelled_includes, runs[-1].labelled_excludes) == (1, 1)


def test_not_prioritized_no_run(setup, session):
    setup.project.prioritized_screening = False
    session.add(setup.project)
    session.commit()
    _decide(setup, setup.articles[0], "exclude")
    assert _runs(session, setup.project) == []


def test_auto_setting_off_no_run(setup, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "ranking_auto_retrain", False)
    _decide(setup, setup.articles[0], "exclude")
    assert _runs(session, setup.project) == []


def test_enabling_prioritization_ranks_immediately(setup, session):
    setup.project.prioritized_screening = False
    session.add(setup.project)
    session.commit()
    res = setup.client.patch(
        f"{BASE}/{setup.project.id}", json={"prioritized_screening": True}
    )
    assert res.status_code == 200
    (run,) = _runs(session, setup.project)
    assert run.scored == len(setup.articles)


def test_required_reviewers_change_schedules_rerank(setup, session, a_member, auth_as):
    setup.project.required_reviewers = 2
    session.add(setup.project)
    session.commit()
    r1 = a_member(setup.project, ProjectRole.reviewer)
    r2 = a_member(setup.project, ProjectRole.reviewer)
    agreed, lone = setup.articles[0], setup.articles[1]
    for reviewer in (r1, r2):
        auth_as(reviewer)
        _decide(setup, agreed, "exclude")
    auth_as(r1)
    _decide(setup, lone, "include")  # blinded while dual screening
    before = _runs(session, setup.project)
    assert before and before[-1].labelled_includes == 0
    auth_as(setup.owner)
    res = setup.client.patch(
        f"{BASE}/{setup.project.id}", json={"required_reviewers": 1}
    )
    assert res.status_code == 200
    runs = _runs(session, setup.project)
    assert len(runs) == len(before) + 1 and runs[-1].labelled_includes == 1


def test_import_into_prioritized_project_scores_new_records(
    setup, session, monkeypatch
):
    class Ctx:
        def __enter__(self):
            return session

        def __exit__(self, exc_type, *a):
            if exc_type is None:
                session.commit()
            return False

    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session", lambda: Ctx()
    )
    ris = (
        "TY  - JOUR\nTI  - Exercise and mood trial\nAB  - Exercise helps mood.\nER  -\n"
    )
    res = setup.client.post(
        f"{BASE}/{setup.project.id}/upload/ris",
        files={"file": ("a.ris", ris.encode(), "application/x-research-info-systems")},
    )
    assert res.status_code == 200
    session.expire_all()
    new = session.exec(
        select(Article).where(
            Article.project_id == setup.project.id,
            Article.title == "Exercise and mood trial",
        )
    ).one()
    assert new.relevance_score is not None
    assert len(_runs(session, setup.project)) == 1


def test_start_screening_triggers_rerank(setup, session, an_article_in):
    imported = an_article_in(setup.project, status=ArticleStatus.imported)
    res = setup.client.post(f"{BASE}/{setup.project.id}/articles/start-screening")
    assert res.status_code == 200
    session.expire_all()
    assert session.get(Article, imported.id).relevance_score is not None


def test_rerank_endpoint_owner(setup, session):
    url = f"{BASE}/{setup.project.id}/screening/rerank"
    res = setup.client.post(url)
    assert res.status_code == 202
    assert res.json()["status"] == "scheduled" and res.json()["last_run"] is None
    (run,) = _runs(session, setup.project)
    assert run.trigger == "manual" and run.triggered_by == setup.owner.id
    events = session.exec(
        select(AuditEvent).where(AuditEvent.action == "screening.rerank_requested")
    ).all()
    assert len(events) == 1
    res = setup.client.post(url)
    assert res.status_code == 202 and res.json()["last_run"]["id"] == run.id
    assert len(_runs(session, setup.project)) == 2


def test_rerank_endpoint_ignores_auto_setting(setup, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "ranking_auto_retrain", False)
    setup.client.post(f"{BASE}/{setup.project.id}/screening/rerank")
    assert len(_runs(session, setup.project)) == 1


def test_rerank_endpoint_queued_when_running(setup, monkeypatch):
    monkeypatch.setattr(ranking, "is_running", lambda project_id: True)
    res = setup.client.post(f"{BASE}/{setup.project.id}/screening/rerank")
    assert res.status_code == 202 and res.json()["status"] == "queued"


def test_rerank_endpoint_409_when_off(setup, session):
    setup.project.prioritized_screening = False
    session.add(setup.project)
    session.commit()
    res = setup.client.post(f"{BASE}/{setup.project.id}/screening/rerank")
    assert res.status_code == 409


@pytest.mark.parametrize("role", [ProjectRole.reviewer, ProjectRole.viewer])
def test_rerank_endpoint_forbidden(setup, a_member, auth_as, role):
    member = a_member(setup.project, role)
    auth_as(member)
    res = setup.client.post(f"{BASE}/{setup.project.id}/screening/rerank")
    assert res.status_code == 403


def test_rerank_endpoint_402_when_pass_expired(setup, session, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.core.config import Settings
    from app.features.billing.models import PlanSource, ProjectPlan

    now = datetime.now(timezone.utc)
    session.add(
        ProjectPlan(
            project_id=setup.project.id,
            tier="pass_250",
            fulltext_limit=250,
            activated_at=now - timedelta(days=400),
            expires_at=now - timedelta(days=1),
            source=PlanSource.admin,
        )
    )
    session.commit()
    settings = Settings(_env_file=None, secret_key="x", billing_enabled=True)
    for target in (
        "app.features.billing.services.get_settings",
        "app.features.billing.routers.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    res = setup.client.post(f"{BASE}/{setup.project.id}/screening/rerank")
    assert res.status_code == 402
