import pytest

from app.features.projects.models import ImportBatch, ProjectRole
from app.features.research.models import ArticleStatus, FinalDecision
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType as D,
    ScreeningStage as S,
)

BASE = "api/v1/projects"


def _human(session, article, user, stage, decision, reason=None, evals=None):
    d = ScreeningDecision(
        article_id=article.id,
        stage=stage,
        decision=decision,
        source=DecisionSource.human,
        reviewer_id=user.id,
        primary_exclusion_reason=reason,
        criteria_evaluations=evals,
    )
    session.add(d)
    session.commit()
    return d


def test_prisma_flow_counts(auth_as, a_project, an_article_in, session, a_user):
    client, owner = auth_as()
    project = a_project(owner)
    session.add_all(
        [
            ImportBatch(
                project_id=project.id,
                filename="pubmed.txt",
                format="pubmed_txt",
                records_found=10,
                imported=8,
                duplicates=2,
                created_by=owner.id,
            ),
            ImportBatch(
                project_id=project.id,
                filename="embase.ris",
                format="ris",
                records_found=5,
                imported=4,
                duplicates=1,
                created_by=owner.id,
            ),
        ]
    )
    session.commit()

    # 1 still to be screened (imported)
    an_article_in(project, status=ArticleStatus.imported)
    # 1 in T/A screening
    an_article_in(project)
    # 2 excluded at T/A
    for _ in range(2):
        a = an_article_in(
            project,
            status=ArticleStatus.excluded,
            current_stage=S.completed,
            final_decision=FinalDecision.excluded,
        )
        _human(session, a, owner, S.title_abstract, D.exclude, "E1")
    # 1 awaiting full text (sought, not retrieved)
    an_article_in(
        project, status=ArticleStatus.awaiting_full_text, current_stage=S.full_text
    )
    # 1 retrieved, not yet decided
    an_article_in(
        project,
        status=ArticleStatus.full_text_retrieved,
        current_stage=S.full_text,
        full_text_retrieved=True,
    )
    # 3 excluded at full text: 2x E2, 1x via criteria evaluation (E3)
    for reason in ("E2", "E2", None):
        a = an_article_in(
            project,
            status=ArticleStatus.excluded,
            current_stage=S.completed,
            final_decision=FinalDecision.excluded,
            full_text_retrieved=True,
        )
        _human(session, a, owner, S.title_abstract, D.include)
        _human(
            session,
            a,
            owner,
            S.full_text,
            D.exclude,
            reason,
            evals={"I1": {"met": True}, "E3": {"met": True}}
            if reason is None
            else None,
        )
    # 2 included
    for _ in range(2):
        a = an_article_in(
            project,
            status=ArticleStatus.included,
            current_stage=S.completed,
            final_decision=FinalDecision.included,
            full_text_retrieved=True,
        )
        _human(session, a, owner, S.title_abstract, D.include)
        _human(session, a, owner, S.full_text, D.include)
    from app.features.criteria.models import Criterion, CriterionType

    session.add_all(
        [
            Criterion(
                project_id=project.id,
                type=CriterionType.exclusion,
                code="E3",
                description="x",
            ),
            Criterion(
                project_id=project.id,
                type=CriterionType.inclusion,
                code="I1",
                description="x",
            ),
        ]
    )
    session.commit()

    res = client.get(f"{BASE}/{project.id}/prisma")
    assert res.status_code == 200
    body = res.json()
    ident = body["identification"]
    assert ident["records_identified"] == 15
    assert ident["duplicates_removed"] == 3
    assert ident["records_after_duplicates_removed"] == 12
    assert {s["filename"]: s["records_found"] for s in ident["sources"]} == {
        "pubmed.txt": 10,
        "embase.ris": 5,
    }
    scr = body["screening"]
    assert (
        scr["records_screened"] == 1 + 2 + 1 + 1 + 3 + 2
    )  # everything past 'imported'
    assert scr["records_excluded"] == 2
    ret = body["retrieval"]
    assert ret["reports_sought"] == 1 + 1 + 3 + 2
    assert ret["reports_not_retrieved"] == 1
    el = body["eligibility"]
    assert el["reports_assessed"] == 6
    assert el["reports_excluded"] == 3
    assert {r["reason"]: r["count"] for r in el["exclusion_reasons"]} == {
        "E2": 2,
        "E3": 1,
    }
    assert body["included"]["studies_included"] == 2


def test_prisma_without_import_batches_falls_back_to_article_count(
    auth_as, a_project, an_article_in
):
    client, owner = auth_as()
    project = a_project(owner)
    an_article_in(project)
    an_article_in(project)
    body = client.get(f"{BASE}/{project.id}/prisma").json()
    assert body["identification"]["records_identified"] == 2
    assert body["identification"]["duplicates_removed"] == 0


def test_prisma_unspecified_reason_and_viewer_access(
    auth_as, a_project, an_article_in, session, a_member
):
    client, owner = auth_as()
    project = a_project(owner)
    a = an_article_in(
        project,
        status=ArticleStatus.excluded,
        current_stage=S.completed,
        final_decision=FinalDecision.excluded,
    )
    _human(session, a, owner, S.full_text, D.exclude)
    viewer = a_member(project, ProjectRole.viewer)
    auth_as(viewer)
    body = client.get(f"{BASE}/{project.id}/prisma").json()
    assert body["eligibility"]["exclusion_reasons"] == [
        {"reason": "Unspecified", "count": 1}
    ]


def test_prisma_forbidden_for_strangers(auth_as, a_project):
    client, _ = auth_as()
    assert client.get(f"{BASE}/{a_project().id}/prisma").status_code == 403


@pytest.mark.parametrize("fmt", ["ris", "pubmed"])
def test_import_flow_records_batch_and_lists_imports(
    fmt, auth_as, a_project, session, monkeypatch, tmp_path
):
    from app.core.config import get_settings

    class Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session", lambda: Ctx()
    )
    monkeypatch.setattr(get_settings(), "upload_directory", str(tmp_path))
    client, owner = auth_as()
    project = a_project(owner)
    if fmt == "ris":
        content = (
            b"TY  - JOUR\nTI  - First paper\nPY  - 2020\nER  - \n"
            b"TY  - JOUR\nTI  - First paper\nPY  - 2020\nER  - \n"
            b"TY  - JOUR\nPY  - 2021\nER  - \n"
        )
        res = client.post(
            f"{BASE}/{project.id}/upload/ris", files={"file": ("a.ris", content)}
        )
    else:
        content = b"PMID- 111\nTI  - A title\nAB  - abs\nDP  - 2020\n\nPMID- 111\nTI  - A title\nDP  - 2020\n\n"
        res = client.post(
            f"{BASE}/{project.id}/upload/pubmed", files={"file": ("p.txt", content)}
        )
    assert res.status_code == 200
    batches = client.get(f"{BASE}/{project.id}/imports").json()
    assert len(batches) == 1
    b = batches[0]
    assert b["created_by"] == owner.id
    assert b["records_found"] == (3 if fmt == "ris" else 2)
    assert b["imported"] == 1 and b["duplicates"] == 1
    assert b["format"] == ("ris" if fmt == "ris" else "pubmed_txt")
    # audit trail records the import
    audit = client.get(f"{BASE}/{project.id}/audit").json()["data"]
    assert [e["action"] for e in audit] == ["import.completed"]
