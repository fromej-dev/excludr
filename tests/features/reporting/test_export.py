import csv
import io

import rispy

from app.features.projects.models import ProjectRole
from app.features.research.models import ArticleStatus, FinalDecision
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType as D,
    ScreeningStage as S,
)

BASE = "api/v1/projects"


def _setup(auth_as, a_project, an_article_in, session):
    client, owner = auth_as()
    project = a_project(owner)
    project.name = "My Review: Ä/ö"
    session.add(project)
    inc = an_article_in(
        project,
        title="Included one",
        doi="10.1/a",
        pmid="1",
        year=2020,
        authors=["Smith J", "Doe A"],
        journal="J Test",
        status=ArticleStatus.included,
        current_stage=S.completed,
        final_decision=FinalDecision.included,
    )
    exc = an_article_in(
        project,
        title="=Excluded one",
        doi="10.1/b",
        year=2021,
        status=ArticleStatus.excluded,
        current_stage=S.completed,
        final_decision=FinalDecision.excluded,
    )
    pending = an_article_in(project, title="Pending")
    session.add_all(
        [
            ScreeningDecision(
                article_id=exc.id,
                stage=S.title_abstract,
                decision=D.exclude,
                source=DecisionSource.human,
                reviewer_id=owner.id,
                primary_exclusion_reason="E1 wrong population",
            ),
            ScreeningDecision(
                article_id=exc.id,
                stage=S.title_abstract,
                decision=D.exclude,
                source=DecisionSource.ai_agent,
                confidence_score=0.91,
            ),
            ScreeningDecision(
                article_id=inc.id,
                stage=S.title_abstract,
                decision=D.include,
                source=DecisionSource.ai_agent,
                confidence_score=0.7,
            ),
        ]
    )
    session.commit()
    return client, owner, project, inc, exc, pending


def test_csv_export(auth_as, a_project, an_article_in, session):
    client, owner, project, inc, exc, pending = _setup(
        auth_as, a_project, an_article_in, session
    )
    res = client.get(f"{BASE}/{project.id}/export?format=csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    disp = res.headers["content-disposition"]
    assert disp.startswith('attachment; filename="') and disp.endswith('.csv"')
    assert all(ord(c) < 128 for c in disp)
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert len(rows) == 3
    by_id = {int(r["id"]): r for r in rows}
    assert by_id[inc.id]["final_decision"] == "included"
    assert (
        by_id[inc.id]["ai_decision"] == "include"
        and by_id[inc.id]["ai_confidence"] == "0.7"
    )
    assert by_id[inc.id]["exclusion_reason"] == ""
    assert by_id[exc.id]["exclusion_reason"] == "E1 wrong population"
    assert by_id[exc.id]["ai_confidence"] == "0.91"
    assert by_id[exc.id]["title"] == "'=Excluded one"  # CSV formula injection guard
    assert by_id[pending.id]["final_decision"] == "pending"
    assert by_id[inc.id]["authors"] == "Smith J; Doe A"


def test_csv_status_filter_and_audit(auth_as, a_project, an_article_in, session):
    client, owner, project, inc, exc, pending = _setup(
        auth_as, a_project, an_article_in, session
    )
    res = client.get(f"{BASE}/{project.id}/export?format=csv&status=excluded")
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert [int(r["id"]) for r in rows] == [exc.id]
    assert (
        client.get(f"{BASE}/{project.id}/export?format=csv&status=bogus").status_code
        == 422
    )
    audit = client.get(f"{BASE}/{project.id}/audit").json()["data"]
    assert audit[0]["action"] == "export.created"
    assert (
        audit[0]["details"]["format"] == "csv"
        and audit[0]["details"]["status"] == "excluded"
    )


def test_ris_export_round_trips(auth_as, a_project, an_article_in, session):
    client, owner, project, inc, exc, pending = _setup(
        auth_as, a_project, an_article_in, session
    )
    res = client.get(f"{BASE}/{project.id}/export?format=ris&status=included")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-research-info-systems")
    assert res.headers["content-disposition"].endswith('.ris"')
    entries = rispy.loads(res.text)
    assert len(entries) == 1
    e = entries[0]
    assert e["title"] == "Included one" and e["doi"] == "10.1/a"
    assert e["authors"] == ["Smith J", "Doe A"]
    assert e["year"] == "2020"
    assert any("included" in n for n in e["notes"])


def test_export_format_validation_and_owner_only(auth_as, a_project, a_member):
    client, owner = auth_as()
    project = a_project(owner)
    assert (
        client.get(f"{BASE}/{project.id}/export").status_code == 200
    )  # defaults to csv
    assert client.get(f"{BASE}/{project.id}/export?format=pdf").status_code == 422
    auth_as(a_member(project, ProjectRole.reviewer))
    assert client.get(f"{BASE}/{project.id}/export?format=csv").status_code == 403
