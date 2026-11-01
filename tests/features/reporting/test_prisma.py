from datetime import datetime, timedelta, timezone

import pytest

from app.features.audit.models import AuditEvent

from app.features.projects.models import ImportBatch, ProjectRole
from app.features.research.models import ArticleStatus, FinalDecision
from app.features.screening.models import (
    DecisionSource,
    RankingRun,
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
    assert ident["marked_ineligible_by_automation"] == 0
    assert body["screening_method"] is None


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


# -- stopping rule / prioritized screening ---------------------------------


def _close_by_rule(an_article_in, project, **kw):
    return an_article_in(
        project,
        status=ArticleStatus.excluded,
        current_stage=S.completed,
        final_decision=FinalDecision.excluded,
        not_screened_stopping_rule=True,
        **kw,
    )


def _batch(session, project, owner, found):
    session.add(
        ImportBatch(
            project_id=project.id,
            filename="a.ris",
            format="ris",
            records_found=found,
            imported=found,
            duplicates=0,
            created_by=owner.id,
        )
    )
    session.commit()


def _excluded(an_article_in, project, **kw):
    return an_article_in(
        project,
        status=ArticleStatus.excluded,
        current_stage=S.completed,
        final_decision=FinalDecision.excluded,
        **kw,
    )


def test_prisma_marks_stopping_rule_records_ineligible_by_automation(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _batch(session, project, owner, 8)
    for _ in range(2):
        a = _excluded(an_article_in, project)
        _human(session, a, owner, S.title_abstract, D.exclude, "E1")
    inc = an_article_in(
        project,
        status=ArticleStatus.included,
        current_stage=S.completed,
        final_decision=FinalDecision.included,
        full_text_retrieved=True,
    )
    _human(session, inc, owner, S.title_abstract, D.include)
    _human(session, inc, owner, S.full_text, D.include)
    ft = _excluded(an_article_in, project, full_text_retrieved=True)
    _human(session, ft, owner, S.title_abstract, D.include)
    _human(session, ft, owner, S.full_text, D.exclude, "E2")
    for _ in range(3):
        _close_by_rule(an_article_in, project)
    an_article_in(project)

    body = client.get(f"{BASE}/{project.id}/prisma").json()
    ident, scr = body["identification"], body["screening"]
    assert ident["marked_ineligible_by_automation"] == 3
    assert ident["records_after_duplicates_removed"] == 8
    assert scr["records_screened"] == 5
    assert scr["records_excluded"] == 2
    assert body["retrieval"]["reports_sought"] == 2
    assert body["eligibility"]["exclusion_reasons"] == [{"reason": "E2", "count": 1}]
    # identities: I3 and I2
    assert 8 == scr["records_screened"] + scr["records_screened_elsewhere"] + 3
    assert scr["records_screened"] == 1 + 2 + 2 - 0


def test_prisma_stopping_rule_combined_with_skipped(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _batch(session, project, owner, 6)
    an_article_in(
        project,
        status=ArticleStatus.awaiting_full_text,
        current_stage=S.full_text,
        title_abstract_skipped=True,
    )
    sk2 = _excluded(
        an_article_in, project, title_abstract_skipped=True, full_text_retrieved=True
    )
    _human(session, sk2, owner, S.full_text, D.exclude, "E2")
    for _ in range(2):
        _close_by_rule(an_article_in, project)
    ta = _excluded(an_article_in, project)
    _human(session, ta, owner, S.title_abstract, D.exclude, "E1")
    an_article_in(project)

    body = client.get(f"{BASE}/{project.id}/prisma").json()
    scr, ret, el = body["screening"], body["retrieval"], body["eligibility"]
    assert scr["records_screened"] == 2
    assert scr["records_screened_elsewhere"] == 2
    assert body["identification"]["marked_ineligible_by_automation"] == 2
    assert scr["records_excluded"] == 1
    assert ret["reports_sought"] == 2 and ret["reports_not_retrieved"] == 1
    assert el["reports_excluded"] == 1
    stats = client.get(f"{BASE}/{project.id}/screening/stats").json()
    assert 2 + 2 + 2 == 6 == stats["title_abstract_total"]  # I1
    assert (
        scr["records_screened"] == 1 + 1 + 2 - 2
    )  # I2: open + excluded + sought - elsewhere
    assert 6 == 2 + 2 + 2  # I3


CANONICAL_METHOD = (
    "Title and abstract screening was prioritized with active learning: records were "
    "presented in order of predicted relevance, estimated by a logistic regression "
    "classifier on TF-IDF features of titles, abstracts and keywords that was "
    "retrained on the reviewers' title and abstract decisions during screening "
    "(Excludr ranking model tfidf-logreg-v1). Screening stopped when the stopping "
    "rule was met: 2 consecutive records were excluded (rule: 2 consecutive "
    "exclusions) after 2 records had been screened. The remaining 1 record was not "
    "screened (reported as marked ineligible by automation tools in the PRISMA flow "
    "diagram)."
)


def _prioritize(session, project, threshold):
    project.prioritized_screening = True
    project.stop_after_consecutive_excludes = threshold
    project.prioritized_screening_enabled_at = datetime.now(timezone.utc) - timedelta(
        days=1
    )
    session.add(project)
    session.commit()


def test_prisma_screening_method_after_apply_and_reopen(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project, 2)
    session.add(
        RankingRun(
            project_id=project.id,
            model_version="tfidf-logreg-v1",
            method="model",
            trigger="auto",
        )
    )
    session.commit()
    arts = [an_article_in(project) for _ in range(3)]
    for a in arts[:2]:
        res = client.post(
            f"{BASE}/{project.id}/screening/articles/{a.id}/decisions",
            json={"stage": "title_abstract", "decision": "exclude", "source": "human"},
        )
        assert res.status_code == 201, res.text
    assert (
        client.post(f"{BASE}/{project.id}/screening/apply-stopping-rule").status_code
        == 200
    )

    body = client.get(f"{BASE}/{project.id}/prisma").json()
    assert body["screening_method"] == CANONICAL_METHOD
    assert body["identification"]["marked_ineligible_by_automation"] == 1
    assert body["screening"]["records_screened"] == 2

    res = client.post(f"{BASE}/{project.id}/screening/reopen-not-screened")
    assert res.status_code == 200
    body = client.get(f"{BASE}/{project.id}/prisma").json()
    assert body["identification"]["marked_ineligible_by_automation"] == 0
    assert body["screening"]["records_screened"] == 3
    method = body["screening_method"]
    assert method.startswith(CANONICAL_METHOD.split(" Screening stopped")[0])
    assert method.endswith(
        "A stopping rule (2 consecutive exclusions) was set but has not been applied."
    )


def test_prisma_screening_method_null_without_ranking(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project, 100)
    an_article_in(project)
    body = client.get(f"{BASE}/{project.id}/prisma").json()
    assert body["screening_method"] is None


def test_prisma_screening_method_uses_latest_application(
    auth_as, a_project, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    _prioritize(session, project, 3)
    _close_by_rule(an_article_in, project)
    session.add(
        RankingRun(
            project_id=project.id,
            model_version="tfidf-logreg-v1",
            method="model",
            trigger="auto",
        )
    )
    for details in (
        {
            "threshold": 5,
            "consecutive_excludes": 1,
            "screened": 4,
            "forced": True,
            "reason": "x",
        },
        {
            "threshold": 3,
            "consecutive_excludes": 3,
            "screened": 9,
            "forced": False,
            "reason": None,
        },
    ):
        session.add(
            AuditEvent(
                project_id=project.id,
                user_id=owner.id,
                action="screening.stopping_rule_applied",
                entity_type="project",
                entity_id=project.id,
                details=details,
            )
        )
    session.commit()
    method = client.get(f"{BASE}/{project.id}/prisma").json()["screening_method"]
    assert (
        "Screening stopped when the stopping rule was met: 3 consecutive records "
        "were excluded (rule: 3 consecutive exclusions) after 9 records had been "
        "screened." in method
    )
    assert "reason: x" not in method
