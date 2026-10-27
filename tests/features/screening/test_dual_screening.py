"""Dual independent screening, conflicts, resolution, blinding and agreement."""

import pytest

from app.features.projects.models import ProjectRole
from app.features.research.models import Article, ArticleStatus
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)

BASE = "api/v1/projects"
TA = "title_abstract"


@pytest.fixture
def team(auth_as, a_project, a_member, session):
    """Owner + two reviewers on a project requiring two reviewers."""
    client, owner = auth_as()
    project = a_project(owner)
    project.required_reviewers = 2
    session.add(project)
    session.commit()
    r1 = a_member(project, ProjectRole.reviewer)
    r2 = a_member(project, ProjectRole.reviewer)

    class Team:
        pass

    t = Team()
    t.client, t.owner, t.project, t.r1, t.r2 = client, owner, project, r1, r2
    t.as_ = lambda user: auth_as(user)
    return t


def _post(client, project, article, decision, stage=TA, **extra):
    return client.post(
        f"{BASE}/{project.id}/screening/articles/{article.id}/decisions",
        json={"stage": stage, "decision": decision, "source": "human", **extra},
    )


def _refresh(session, article):
    session.expire_all()
    return session.get(Article, article.id)


def test_required_reviewers_setting(auth_as, a_project):
    client, owner = auth_as()
    project = a_project(owner)
    assert client.get(f"{BASE}/{project.id}").json()["required_reviewers"] == 1
    res = client.patch(f"{BASE}/{project.id}", json={"required_reviewers": 2})
    assert res.status_code == 200 and res.json()["required_reviewers"] == 2
    assert (
        client.patch(f"{BASE}/{project.id}", json={"required_reviewers": 3}).status_code
        == 422
    )
    assert (
        client.patch(f"{BASE}/{project.id}", json={"required_reviewers": 0}).status_code
        == 422
    )


def test_single_reviewer_mode_advances_immediately(team, an_article_in, session):
    team.project.required_reviewers = 1
    session.add(team.project)
    session.commit()
    a = an_article_in(team.project)
    team.as_(team.r1)
    assert _post(team.client, team.project, a, "include").status_code == 201
    assert _refresh(session, a).status == ArticleStatus.awaiting_full_text


def test_agreement_advances_only_after_second_reviewer(team, an_article_in, session):
    a = an_article_in(team.project)
    team.as_(team.r1)
    assert _post(team.client, team.project, a, "include").status_code == 201
    assert _refresh(session, a).status == ArticleStatus.screening
    team.as_(team.r2)
    assert _post(team.client, team.project, a, "include").status_code == 201
    a = _refresh(session, a)
    assert a.status == ArticleStatus.awaiting_full_text
    assert a.current_stage == ScreeningStage.full_text


def test_agreed_exclusion_excludes(team, an_article_in, session):
    a = an_article_in(team.project)
    for user in (team.r1, team.r2):
        team.as_(user)
        _post(team.client, team.project, a, "exclude", primary_exclusion_reason="E1")
    a = _refresh(session, a)
    assert a.status == ArticleStatus.excluded
    assert a.current_stage == ScreeningStage.completed


def test_disagreement_creates_conflict_and_owner_resolves(team, an_article_in, session):
    a = an_article_in(team.project, title="Disputed")
    team.as_(team.r1)
    _post(team.client, team.project, a, "include", reasoning="looks right")
    team.as_(team.r2)
    _post(team.client, team.project, a, "exclude", reasoning="wrong population")
    assert _refresh(session, a).status == ArticleStatus.screening

    # reviewers cannot see the conflict list; owner can
    assert (
        team.client.get(f"{BASE}/{team.project.id}/screening/conflicts").status_code
        == 403
    )
    team.as_(team.owner)
    res = team.client.get(f"{BASE}/{team.project.id}/screening/conflicts")
    assert res.status_code == 200
    (conflict,) = res.json()
    assert conflict["article_id"] == a.id and conflict["title"] == "Disputed"
    got = {d["reviewer_id"]: d["decision"] for d in conflict["decisions"]}
    assert got == {team.r1.id: "include", team.r2.id: "exclude"}

    # resolve: reviewers forbidden, validation, then success
    url = f"{BASE}/{team.project.id}/screening/articles/{a.id}/resolve"
    team.as_(team.r1)
    assert (
        team.client.post(url, json={"decision": "include", "reason": "x"}).status_code
        == 403
    )
    team.as_(team.owner)
    assert (
        team.client.post(url, json={"decision": "uncertain", "reason": "x"}).status_code
        == 422
    )
    assert team.client.post(url, json={"decision": "include"}).status_code == 422
    res = team.client.post(
        url,
        json={
            "decision": "exclude",
            "reason": "population mismatch",
            "primary_exclusion_reason": "E2",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_resolution"] is True and body["source"] == "human"
    assert (
        body["reviewer_id"] == team.owner.id
        and body["reasoning"] == "population mismatch"
    )
    a = _refresh(session, a)
    assert a.status == ArticleStatus.excluded and a.final_decision.value == "excluded"
    assert team.client.get(f"{BASE}/{team.project.id}/screening/conflicts").json() == []


def test_resolve_requires_conflict(team, an_article_in):
    a = an_article_in(team.project)
    res = team.client.post(
        f"{BASE}/{team.project.id}/screening/articles/{a.id}/resolve",
        json={"decision": "include", "reason": "r"},
    )
    assert res.status_code == 409
    missing = team.client.post(
        f"{BASE}/{team.project.id}/screening/articles/99999/resolve",
        json={"decision": "include", "reason": "r"},
    )
    assert missing.status_code == 404


def test_reviewer_changing_their_decision_supersedes_it(team, an_article_in, session):
    a = an_article_in(team.project)
    team.as_(team.r1)
    first = _post(team.client, team.project, a, "include")
    assert first.status_code == 201
    second = _post(team.client, team.project, a, "exclude", reasoning="changed my mind")
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    # history is kept, but only the latest counts for r1
    rows = session.query(ScreeningDecision).filter_by(article_id=a.id).all()
    assert len(rows) == 2
    # the replaced decision can flip a conflict into agreement
    team.as_(team.r2)
    _post(team.client, team.project, a, "include")  # conflict now
    team.as_(team.owner)
    (conflict,) = team.client.get(
        f"{BASE}/{team.project.id}/screening/conflicts"
    ).json()
    assert len(conflict["decisions"]) == 2  # superseded rows are not listed
    team.as_(team.r1)
    _post(team.client, team.project, a, "include")  # r1 agrees again
    assert _refresh(session, a).status == ArticleStatus.awaiting_full_text


def test_ai_decisions_never_count_as_reviewers(team, an_article_in, session):
    a = an_article_in(team.project)
    session.add(
        ScreeningDecision(
            article_id=a.id,
            stage=ScreeningStage.title_abstract,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
        )
    )
    session.commit()
    team.as_(team.r1)
    _post(team.client, team.project, a, "include")
    assert _refresh(session, a).status == ArticleStatus.screening


def test_reviewer_cannot_post_ai_source_decisions(team, an_article_in):
    a = an_article_in(team.project)
    team.as_(team.r1)
    res = team.client.post(
        f"{BASE}/{team.project.id}/screening/articles/{a.id}/decisions",
        json={"stage": TA, "decision": "include", "source": "ai_agent"},
    )
    assert res.status_code == 403


def test_viewer_cannot_decide(team, a_member, an_article_in):
    viewer = a_member(team.project, ProjectRole.viewer)
    a = an_article_in(team.project)
    team.as_(viewer)
    assert _post(team.client, team.project, a, "include").status_code == 403


def test_decision_must_match_article_stage(team, an_article_in):
    a = an_article_in(team.project)
    team.as_(team.r1)
    assert (
        _post(team.client, team.project, a, "include", stage="full_text").status_code
        == 409
    )


def test_next_skips_own_decisions_and_is_blind(team, an_article_in):
    a1 = an_article_in(team.project, title="one")
    a2 = an_article_in(team.project, title="two")
    team.as_(team.r1)
    url = f"{BASE}/{team.project.id}/screening/next"
    assert team.client.get(url).json()["article"]["id"] == a1.id
    _post(team.client, team.project, a1, "include")
    assert team.client.get(url).json()["article"]["id"] == a2.id
    _post(team.client, team.project, a2, "exclude")
    assert team.client.get(url).json()["article"] is None

    # r2 still gets a1, with no sign of r1's decision
    team.as_(team.r2)
    body = team.client.get(url).json()
    assert body["article"]["id"] == a1.id
    assert set(body) == {"article"}
    assert "screening_decisions" not in body["article"]


def test_next_not_offered_to_third_reviewer_once_two_decided(
    team, a_member, an_article_in
):
    a = an_article_in(team.project)
    for user, d in ((team.r1, "include"), (team.r2, "exclude")):
        team.as_(user)
        _post(team.client, team.project, a, d)
    third = a_member(team.project, ProjectRole.reviewer)
    team.as_(third)
    assert (
        team.client.get(f"{BASE}/{team.project.id}/screening/next").json()["article"]
        is None
    )


def test_decision_list_hides_other_reviewers_until_stage_done(team, an_article_in):
    a = an_article_in(team.project)
    team.as_(team.r1)
    _post(team.client, team.project, a, "include")
    team.as_(team.r2)
    url = f"{BASE}/{team.project.id}/screening/articles/{a.id}/decisions"
    assert team.client.get(url).json()["meta"]["pagination"]["total_items"] == 0
    _post(team.client, team.project, a, "include")  # agree -> article leaves stage
    assert team.client.get(url).json()["meta"]["pagination"]["total_items"] == 2
    team.as_(team.owner)
    assert team.client.get(url).json()["meta"]["pagination"]["total_items"] == 2


def test_changing_required_reviewers_reevaluates(team, an_article_in, session):
    a = an_article_in(team.project)
    team.as_(team.r1)
    _post(team.client, team.project, a, "exclude")
    assert _refresh(session, a).status == ArticleStatus.screening
    team.as_(team.owner)
    team.client.patch(f"{BASE}/{team.project.id}", json={"required_reviewers": 1})
    assert _refresh(session, a).status == ArticleStatus.excluded


def _ai(session, article, decision, stage=ScreeningStage.title_abstract, conf=0.8):
    session.add(
        ScreeningDecision(
            article_id=article.id,
            stage=stage,
            decision=decision,
            source=DecisionSource.ai_agent,
            confidence_score=conf,
            reasoning="ai says",
        )
    )
    session.commit()


def test_ai_disagreements(team, an_article_in, session):
    team.project.required_reviewers = 1
    session.add(team.project)
    session.commit()
    agree = an_article_in(team.project, title="agree")
    differ = an_article_in(team.project, title="differ")
    unscreened = an_article_in(team.project, title="no human")
    _ai(session, agree, ScreeningDecisionType.include)
    _ai(session, differ, ScreeningDecisionType.include)
    _ai(session, unscreened, ScreeningDecisionType.exclude)
    team.as_(team.r1)
    _post(team.client, team.project, agree, "include")
    _post(team.client, team.project, differ, "exclude")
    team.as_(team.owner)
    res = team.client.get(f"{BASE}/{team.project.id}/screening/ai-disagreements")
    assert res.status_code == 200
    (row,) = res.json()
    assert row["article_id"] == differ.id
    assert row["ai"]["decision"] == "include" and row["human_decision"] == "exclude"
    assert row["ai"]["confidence_score"] == 0.8
    team.as_(team.r1)
    assert (
        team.client.get(
            f"{BASE}/{team.project.id}/screening/ai-disagreements"
        ).status_code
        == 403
    )


def test_agreement_stats_human_and_ai(team, an_article_in, session):
    # 4 articles, reviewers: agree, agree, disagree (resolved include), agree
    plan = [
        ("include", "include", None, ScreeningDecisionType.include),
        ("exclude", "exclude", None, ScreeningDecisionType.exclude),
        ("include", "exclude", "include", ScreeningDecisionType.exclude),
        ("exclude", "exclude", None, ScreeningDecisionType.include),
    ]
    for i, (d1, d2, resolution, ai) in enumerate(plan):
        a = an_article_in(team.project, title=f"a{i}")
        _ai(session, a, ai)
        team.as_(team.r1)
        _post(team.client, team.project, a, d1)
        team.as_(team.r2)
        _post(team.client, team.project, a, d2)
        if resolution:
            team.as_(team.owner)
            team.client.post(
                f"{BASE}/{team.project.id}/screening/articles/{a.id}/resolve",
                json={"decision": resolution, "reason": "r"},
            )
    team.as_(team.owner)
    res = team.client.get(f"{BASE}/{team.project.id}/screening/agreement?stage={TA}")
    assert res.status_code == 200
    body = res.json()
    assert body["required_reviewers"] == 2
    hh = body["human_vs_human"]
    assert hh["n_articles"] == 4 and hh["percent_agreement"] == pytest.approx(0.75)
    # r1: i,e,i,e  r2: i,e,e,e -> po=.75, pe=.5*.25+.5*.75=.5 -> kappa .5
    assert hh["cohens_kappa"] == pytest.approx(0.5)
    ai = body["ai_vs_human"]
    # human final: inc, exc, inc(resolved), exc ; ai: inc, exc, exc, inc
    assert (ai["true_positives"], ai["true_negatives"]) == (1, 1)
    assert (ai["false_positives"], ai["false_negatives"]) == (1, 1)
    assert ai["accuracy"] == pytest.approx(0.5)
    assert ai["sensitivity"] == pytest.approx(0.5)
    assert ai["specificity"] == pytest.approx(0.5)
    assert ai["cohens_kappa"] == pytest.approx(0.0)


def test_agreement_single_reviewer_has_no_human_section(team, an_article_in, session):
    team.project.required_reviewers = 1
    session.add(team.project)
    session.commit()
    a = an_article_in(team.project)
    team.as_(team.owner)
    res = team.client.get(f"{BASE}/{team.project.id}/screening/agreement")
    assert res.status_code == 200
    assert res.json()["human_vs_human"] is None
    assert res.json()["ai_vs_human"]["n_articles"] == 0
    assert a.id  # keep fixture used
    assert (
        team.client.get(
            f"{BASE}/{team.project.id}/screening/agreement?stage=completed"
        ).status_code
        == 400
    )
