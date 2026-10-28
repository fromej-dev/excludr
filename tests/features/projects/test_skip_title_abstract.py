"""Skipping title/abstract screening for records screened elsewhere.

Covers the ``title_abstract_screened`` import option, the owner's
``skip-title-abstract`` bulk action, and how skipped articles are counted in the
screening statistics and the PRISMA flow.
"""

import pytest
from sqlmodel import select

from app.core.config import get_settings
from app.features.audit.models import AuditEvent
from app.features.projects.flows import parse_pubmed_file_flow
from app.features.projects.models import ImportBatch, ProjectRole
from app.features.research import flows as research_flows
from app.features.research.models import Article, ArticleStatus, FinalDecision
from app.features.screening.models import ScreeningStage

API = "api/v1/projects"


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


@pytest.fixture
def use_test_session(session, monkeypatch):
    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session", lambda: _Ctx(session)
    )


@pytest.fixture
def scheduled(monkeypatch):
    """Turn automatic retrieval on and record the runs it queues."""
    monkeypatch.setattr(get_settings(), "fulltext_auto_retrieval", True)
    calls = []

    async def fake_flow(project_id, article_ids, user_id, trigger="manual"):
        calls.append((project_id, article_ids, user_id, trigger))

    monkeypatch.setattr(research_flows, "retrieve_fulltext_flow", fake_flow)
    return calls


def _ris(*entries):
    lines = []
    for title, doi in entries:
        lines += ["TY  - JOUR", f"TI  - {title}", "PY  - 2020", f"DO  - {doi}"]
        lines += ["ER  - ", ""]
    return "\n".join(lines).encode()


def _upload_ris(client, project, content, **data):
    res = client.post(
        f"{API}/{project.id}/upload/ris",
        files={"file": ("included.ris", content)},
        data=data,
    )
    assert res.status_code == 200, res.text
    return res.json()["result"]


def _by_doi(session, project):
    session.expire_all()
    articles = session.exec(select(Article).where(Article.project_id == project.id))
    return {a.doi: a for a in articles}


@pytest.mark.usefixtures("use_test_session")
def test_import_flag_sends_records_to_full_text(
    auth_as, a_project, an_article_in, session, scheduled
):
    client, user = auth_as()
    project = a_project(user)
    waiting = an_article_in(project, title="Waiting", doi="10.1/waiting")
    excluded = an_article_in(
        project,
        title="Excluded",
        doi="10.1/excluded",
        status=ArticleStatus.excluded,
        current_stage=ScreeningStage.completed,
        final_decision=FinalDecision.excluded,
    )

    result = _upload_ris(
        client,
        project,
        _ris(
            ("New one", "10.1/new"),
            ("Waiting", "10.1/waiting"),
            ("Excluded", "10.1/excluded"),
        ),
        title_abstract_screened="true",
    )

    assert result["articles_created"] == 1
    assert result["title_abstract_skipped"] == 2
    assert "skipped_article_ids" not in result
    articles = _by_doi(session, project)
    for doi in ("10.1/new", "10.1/waiting"):
        assert articles[doi].status == ArticleStatus.awaiting_full_text
        assert articles[doi].current_stage == ScreeningStage.full_text
    # Already decided articles keep their decision.
    assert articles["10.1/excluded"].status == ArticleStatus.excluded

    batch = session.exec(
        select(ImportBatch).where(ImportBatch.project_id == project.id)
    ).one()
    assert batch.title_abstract_screened is True
    event = session.exec(
        select(AuditEvent).where(AuditEvent.action == "import.completed")
    ).one()
    assert event.details["title_abstract_skipped"] == 2

    assert len(scheduled) == 1
    assert scheduled[0][0] == project.id
    assert sorted(scheduled[0][1]) == sorted([articles["10.1/new"].id, waiting.id])
    assert scheduled[0][3] == "auto"
    assert excluded.id not in scheduled[0][1]


@pytest.mark.usefixtures("use_test_session")
def test_import_without_flag_keeps_title_abstract(
    auth_as, a_project, session, scheduled
):
    client, user = auth_as()
    project = a_project(user)

    result = _upload_ris(client, project, _ris(("New one", "10.1/new")))

    assert result["title_abstract_skipped"] == 0
    article = _by_doi(session, project)["10.1/new"]
    assert article.status == ArticleStatus.screening
    assert article.current_stage == ScreeningStage.title_abstract
    assert scheduled == []
    batch = session.exec(
        select(ImportBatch).where(ImportBatch.project_id == project.id)
    ).one()
    assert batch.title_abstract_screened is False


@pytest.mark.usefixtures("use_test_session")
def test_pubmed_flow_with_flag(tmp_path, a_project, session):
    project = a_project()
    path = tmp_path / "abc_x.txt"
    path.write_text(
        "PMID- 111\nTI  - Pubmed paper\nDP  - 2020\nAB  - Abstract.\n\n",
        encoding="utf-8",
    )

    result = parse_pubmed_file_flow(
        str(path), project.id, "x.txt", None, title_abstract_screened=True
    )

    assert result["title_abstract_skipped"] == 1
    article = session.exec(
        select(Article).where(Article.project_id == project.id)
    ).one()
    assert article.status == ArticleStatus.awaiting_full_text
    assert article.current_stage == ScreeningStage.full_text


def test_bulk_skip_moves_only_title_abstract_articles(
    auth_as, a_project, an_article_in, session, scheduled
):
    client, user = auth_as()
    project = a_project(user)
    plain = an_article_in(project, title="Plain")
    with_pdf = an_article_in(project, title="Has PDF", full_text_retrieved=True)
    later = an_article_in(
        project,
        title="Later",
        status=ArticleStatus.full_text_retrieved,
        current_stage=ScreeningStage.full_text,
    )
    untouched = an_article_in(project, title="Not selected")

    res = client.post(
        f"{API}/{project.id}/articles/skip-title-abstract",
        json={"article_ids": [plain.id, with_pdf.id, later.id]},
    )

    assert res.status_code == 200, res.text
    assert res.json() == {"moved": 2, "retrieval_queued": 1}
    session.expire_all()
    assert session.get(Article, plain.id).status == ArticleStatus.awaiting_full_text
    assert session.get(Article, with_pdf.id).status == ArticleStatus.full_text_retrieved
    for article in (plain, with_pdf):
        assert (
            session.get(Article, article.id).current_stage == ScreeningStage.full_text
        )
    assert session.get(Article, untouched.id).status == ArticleStatus.screening
    assert scheduled == [(project.id, [plain.id], user.id, "auto")]

    event = session.exec(
        select(AuditEvent).where(AuditEvent.action == "articles.title_abstract_skipped")
    ).one()
    assert event.details == {"count": 2, "article_ids": [plain.id, with_pdf.id]}

    # Without ids every remaining title/abstract article moves.
    res = client.post(f"{API}/{project.id}/articles/skip-title-abstract")
    assert res.json()["moved"] == 1
    res = client.post(f"{API}/{project.id}/articles/skip-title-abstract")
    assert res.json() == {"moved": 0, "retrieval_queued": 0}


def test_bulk_skip_is_owner_only(auth_as, a_project, an_article_in, a_user, session):
    from app.features.projects.models import ProjectMember

    owner = a_user()
    project = a_project(owner)
    article = an_article_in(project)
    reviewer = a_user()
    session.add(
        ProjectMember(
            project_id=project.id, user_id=reviewer.id, role=ProjectRole.reviewer
        )
    )
    session.commit()
    client, _ = auth_as(reviewer)

    res = client.post(f"{API}/{project.id}/articles/skip-title-abstract")

    assert res.status_code == 403
    session.expire_all()
    assert session.get(Article, article.id).status == ArticleStatus.screening


def test_skipped_articles_in_stats_and_prisma(
    auth_as, a_project, an_article_in, session
):
    client, user = auth_as()
    project = a_project(user)
    screened_here = an_article_in(project, title="Screened here")
    skipped = an_article_in(project, title="Skipped", full_text_retrieved=True)
    an_article_in(project, title="Still waiting")

    def decide(article, stage, decision):
        res = client.post(
            f"{API}/{project.id}/screening/articles/{article.id}/decisions",
            json={"stage": stage, "decision": decision, "source": "human"},
        )
        assert res.status_code == 201, res.text

    decide(screened_here, "title_abstract", "exclude")
    res = client.post(
        f"{API}/{project.id}/articles/skip-title-abstract",
        json={"article_ids": [skipped.id]},
    )
    assert res.json()["moved"] == 1
    decide(skipped, "full_text", "exclude")

    stats = client.get(f"{API}/{project.id}/screening/stats").json()
    assert stats["title_abstract_total"] == 3
    assert stats["title_abstract_skipped"] == 1
    assert stats["excluded_title_abstract"] == 1
    assert stats["excluded_full_text"] == 1
    assert stats["full_text_eligible"] == 1

    prisma = client.get(f"{API}/{project.id}/prisma").json()
    assert prisma["screening"]["records_screened"] == 2
    assert prisma["screening"]["records_excluded"] == 1
    assert prisma["screening"]["records_screened_elsewhere"] == 1
    assert prisma["retrieval"]["reports_sought"] == 1
    assert prisma["eligibility"]["reports_excluded"] == 1
