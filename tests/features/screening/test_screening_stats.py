"""Exact per-stage screening statistics (GET /screening/stats)."""

import pytest

from app.core.config import get_settings
from app.features.projects.models import ProjectRole
from app.features.research.models import Article, ArticleStatus
from app.features.research.services import ArticleService
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)

BASE = "api/v1/projects"
TA = "title_abstract"
FT = "full_text"
PDF_BYTES = b"%PDF-1.4\n%fake pdf body\n"


def _post(client, project, article, decision, stage=TA):
    res = client.post(
        f"{BASE}/{project.id}/screening/articles/{article.id}/decisions",
        json={"stage": stage, "decision": decision, "source": "human"},
    )
    assert res.status_code == 201, res.text
    return res


def _stats(client, project):
    res = client.get(f"{BASE}/{project.id}/screening/stats")
    assert res.status_code == 200
    return res.json()


def _retrieve(session, article):
    """Give an article awaiting full text its full text (as retrieval would)."""
    session.expire_all()
    article = session.get(Article, article.id)
    assert article.status == ArticleStatus.awaiting_full_text
    ArticleService(session).set_full_text_retrieved(
        article, None, "full text", source="europepmc"
    )


def _assert_invariants(s):
    assert s["title_abstract_total"] == s["total_articles"] - s["imported_not_started"]
    assert (
        s["title_abstract_total"]
        == s["awaiting_screening"] + s["title_abstract_completed"]
    )
    assert (
        s["title_abstract_completed"]
        == s["excluded_title_abstract"] + s["full_text_eligible"]
    )
    assert s["full_text_eligible"] == (
        s["awaiting_full_text"]
        + s["awaiting_full_text_screening"]
        + s["full_text_completed"]
    )
    assert s["full_text_retrieved"] == s["full_text_eligible"] - s["awaiting_full_text"]
    assert s["full_text_completed"] == s["included"] + s["excluded_full_text"]
    assert s["excluded"] == s["excluded_title_abstract"] + s["excluded_full_text"]


def _assert_matches_prisma(client, project, s):
    prisma = client.get(f"{BASE}/{project.id}/prisma").json()
    assert prisma["screening"] == {
        "records_screened": s["title_abstract_total"] - s["title_abstract_skipped"],
        "records_excluded": s["excluded_title_abstract"],
        "records_screened_elsewhere": s["title_abstract_skipped"],
    }
    assert prisma["retrieval"] == {
        "reports_sought": s["full_text_eligible"],
        "reports_not_retrieved": s["awaiting_full_text"],
    }
    assert prisma["eligibility"]["reports_assessed"] == s["full_text_retrieved"]
    assert prisma["eligibility"]["reports_excluded"] == s["excluded_full_text"]
    assert prisma["included"]["studies_included"] == s["included"]


def test_empty_project_has_zero_stats(auth_as, a_project):
    client, owner = auth_as()
    project = a_project(owner)
    s = _stats(client, project)
    assert set(s.values()) == {0}


def test_single_reviewer_pipeline(auth_as, a_project, an_article_in, session):
    client, owner = auth_as()
    project = a_project(owner)
    new = lambda: an_article_in(project)  # noqa: E731

    an_article_in(project, status=ArticleStatus.imported)
    ai_only, untouched, ta_excluded, unsure = new(), new(), new(), new()
    awaiting, retrieved, included, ft_excluded = new(), new(), new(), new()

    # AI decisions count as "screened" (legacy) but never as decided/completed
    session.add(
        ScreeningDecision(
            article_id=ai_only.id,
            stage=ScreeningStage.title_abstract,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
        )
    )
    session.commit()

    _post(client, project, ta_excluded, "exclude")
    _post(client, project, unsure, "uncertain")
    for a in (awaiting, retrieved, included, ft_excluded):
        _post(client, project, a, "include")
    for a in (retrieved, included, ft_excluded):
        _retrieve(session, a)
    _post(client, project, included, "include", stage=FT)
    _post(client, project, ft_excluded, "exclude", stage=FT)

    s = _stats(client, project)
    assert s == {
        "total_articles": 9,
        "screened_title_abstract": 7,
        "screened_full_text": 2,
        "included": 1,
        "excluded": 2,
        "uncertain": 1,
        "awaiting_screening": 3,  # ai_only, untouched, unsure
        "awaiting_full_text": 1,
        "imported_not_started": 1,
        "title_abstract_total": 8,
        "title_abstract_decided": 6,
        "title_abstract_completed": 5,
        "excluded_title_abstract": 1,
        "title_abstract_skipped": 0,
        "full_text_eligible": 4,
        "full_text_retrieved": 3,
        "awaiting_full_text_screening": 1,
        "full_text_decided": 2,
        "full_text_completed": 2,
        "excluded_full_text": 1,
    }
    _assert_invariants(s)
    _assert_matches_prisma(client, project, s)
    assert untouched  # only part of the setup


def test_full_text_uncertain_counts_while_open(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    a = an_article_in(project)
    _post(client, project, a, "include")
    _retrieve(session, a)
    _post(client, project, a, "uncertain", stage=FT)
    s = _stats(client, project)
    assert s["uncertain"] == 1
    assert s["full_text_decided"] == 1 and s["full_text_completed"] == 0
    assert s["awaiting_full_text_screening"] == 1
    _post(client, project, a, "include", stage=FT)
    s = _stats(client, project)
    assert s["uncertain"] == 0 and s["included"] == 1
    _assert_invariants(s)


def test_dual_screening_conflicts_and_resolution(
    auth_as, a_project, a_member, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    project.required_reviewers = 2
    session.add(project)
    session.commit()
    r1 = a_member(project, ProjectRole.reviewer)
    r2 = a_member(project, ProjectRole.reviewer)

    one_vote, split, agreed, resolved, unsure_split, changed_mind, ft_out = (
        an_article_in(project) for _ in range(7)
    )

    auth_as(r1)
    _post(client, project, one_vote, "include")
    _post(client, project, split, "include")
    _post(client, project, agreed, "include")
    _post(client, project, resolved, "include")
    _post(client, project, unsure_split, "uncertain")
    _post(client, project, changed_mind, "uncertain")
    _post(client, project, changed_mind, "include")  # supersedes the uncertain
    _post(client, project, ft_out, "include")
    auth_as(r2)
    _post(client, project, split, "exclude")
    _post(client, project, agreed, "include")
    _post(client, project, resolved, "exclude")
    _post(client, project, unsure_split, "include")
    _post(client, project, ft_out, "include")

    auth_as(owner)
    res = client.post(
        f"{BASE}/{project.id}/screening/articles/{resolved.id}/resolve",
        json={"decision": "exclude", "reason": "out of scope"},
    )
    assert res.status_code == 200

    _retrieve(session, ft_out)
    for user in (r1, r2):
        auth_as(user)
        _post(client, project, ft_out, "exclude", stage=FT)

    s = _stats(client, project)
    # In conflict / waiting for a second reviewer: still at title/abstract
    assert s["awaiting_screening"] == 4  # one_vote, split, unsure_split, changed_mind
    assert s["title_abstract_total"] == 7
    assert s["title_abstract_decided"] == 7
    assert s["title_abstract_completed"] == 3  # agreed, resolved, ft_out
    assert s["excluded_title_abstract"] == 1  # resolved
    assert s["full_text_eligible"] == 2  # agreed, ft_out
    assert s["awaiting_full_text"] == 1
    assert s["full_text_retrieved"] == 1
    assert s["full_text_decided"] == 1
    assert s["full_text_completed"] == 1
    assert s["excluded_full_text"] == 1
    assert s["excluded"] == 2
    assert s["uncertain"] == 1  # unsure_split; changed_mind's uncertain was replaced
    _assert_invariants(s)
    _assert_matches_prisma(client, project, s)


@pytest.fixture
def pdf_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "pdf_storage_path", str(tmp_path))
    return tmp_path


def _upload(client, project, article):
    res = client.post(
        f"{BASE}/{project.id}/articles/{article.id}/fulltext/upload",
        files={"file": ("x.pdf", PDF_BYTES)},
    )
    assert res.status_code == 200


def test_upload_before_title_abstract_does_not_skip_the_stage(
    auth_as, a_project, an_article_in, session, pdf_dir
):
    client, owner = auth_as()
    project = a_project(owner)
    a = an_article_in(project)
    _upload(client, project, a)
    session.expire_all()
    a = session.get(Article, a.id)
    assert a.status == ArticleStatus.screening and a.full_text_retrieved
    assert _stats(client, project)["full_text_eligible"] == 0

    # Passing title/abstract goes straight to full-text screening
    _post(client, project, a, "include")
    session.expire_all()
    assert session.get(Article, a.id).status == ArticleStatus.full_text_retrieved
    s = _stats(client, project)
    assert s["full_text_eligible"] == s["full_text_retrieved"] == 1
    assert s["awaiting_full_text"] == 0
    _assert_invariants(s)


def test_upload_after_decision_keeps_the_outcome(
    auth_as, a_project, an_article_in, session, pdf_dir
):
    client, owner = auth_as()
    project = a_project(owner)
    a = an_article_in(project)
    _post(client, project, a, "include")
    _retrieve(session, a)
    _post(client, project, a, "include", stage=FT)
    _upload(client, project, a)
    session.expire_all()
    assert session.get(Article, a.id).status == ArticleStatus.included
    s = _stats(client, project)
    assert s["included"] == s["full_text_completed"] == 1
    _assert_invariants(s)


def test_stats_are_per_project(auth_as, a_project, an_article_in):
    client, owner = auth_as()
    mine, other = a_project(owner), a_project(owner)
    an_article_in(other)
    an_article_in(other, status=ArticleStatus.awaiting_full_text)
    an_article_in(mine)
    s = _stats(client, mine)
    assert s["total_articles"] == 1 and s["awaiting_full_text"] == 0
