from app.features.audit.models import AuditEvent
from app.features.projects.models import ProjectRole

BASE = "api/v1/projects"


def _actions(client, pid):
    res = client.get(f"{BASE}/{pid}/audit")
    assert res.status_code == 200
    return [e["action"] for e in res.json()["data"]]


def test_audit_owner_only_and_paginated(auth_as, a_project, a_member):
    client, owner = auth_as()
    project = a_project(owner)
    for i in range(3):
        client.post(
            f"{BASE}/{project.id}/criteria",
            json={"type": "inclusion", "code": f"I{i}", "description": "d"},
        )
    res = client.get(f"{BASE}/{project.id}/audit")
    assert res.json()["meta"]["pagination"]["total_items"] == 3
    reviewer = a_member(project, ProjectRole.reviewer)
    auth_as(reviewer)
    assert client.get(f"{BASE}/{project.id}/audit").status_code == 403


def test_criteria_and_member_changes_are_audited(auth_as, a_project, a_user):
    client, owner = auth_as()
    project = a_project(owner)
    c = client.post(
        f"{BASE}/{project.id}/criteria",
        json={"type": "inclusion", "code": "I1", "description": "d"},
    ).json()
    client.patch(f"{BASE}/{project.id}/criteria/{c['id']}", json={"description": "e"})
    client.delete(f"{BASE}/{project.id}/criteria/{c['id']}")
    other = a_user()
    client.post(f"{BASE}/{project.id}/members", json={"email": other.email})
    client.patch(f"{BASE}/{project.id}/members/{other.id}", json={"role": "viewer"})
    client.delete(f"{BASE}/{project.id}/members/{other.id}")
    assert _actions(client, project.id) == [
        "member.removed",
        "member.role_changed",
        "member.added",
        "criterion.deleted",
        "criterion.updated",
        "criterion.created",
    ]
    events = client.get(f"{BASE}/{project.id}/audit").json()["data"]
    assert events[0]["user_id"] == owner.id
    updated = [e for e in events if e["action"] == "criterion.updated"][0]
    assert updated["details"]["changes"]["description"]["to"] == "e"


def test_audit_events_have_no_write_endpoints(auth_as, a_project):
    client, owner = auth_as()
    project = a_project(owner)
    assert client.post(f"{BASE}/{project.id}/audit", json={}).status_code == 405
    assert client.delete(f"{BASE}/{project.id}/audit").status_code == 405


def test_project_settings_audited(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    client.patch(f"{BASE}/{project.id}", json={"required_reviewers": 2})
    event = session.query(AuditEvent).filter_by(project_id=project.id).one()
    assert event.action == "project.settings_updated"
    assert event.details == {"required_reviewers": 2}


def test_decisions_and_resolutions_are_audited(
    auth_as, a_project, a_member, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    project.required_reviewers = 2
    session.add(project)
    session.commit()
    r1 = a_member(project, ProjectRole.reviewer)
    r2 = a_member(project, ProjectRole.reviewer)
    article = an_article_in(project)
    url = f"{BASE}/{project.id}/screening/articles/{article.id}"
    auth_as(r1)
    client.post(
        f"{url}/decisions", json={"stage": "title_abstract", "decision": "include"}
    )
    client.post(
        f"{url}/decisions", json={"stage": "title_abstract", "decision": "exclude"}
    )
    auth_as(r2)
    client.post(
        f"{url}/decisions", json={"stage": "title_abstract", "decision": "include"}
    )
    auth_as(owner)
    client.post(f"{url}/resolve", json={"decision": "include", "reason": "fits"})
    events = (
        session.query(AuditEvent)
        .filter_by(project_id=project.id)
        .order_by(AuditEvent.id)
        .all()
    )
    assert [e.action for e in events] == [
        "decision.created",
        "decision.updated",
        "decision.created",
        "decision.resolved",
    ]
    assert events[0].user_id == r1.id and events[3].user_id == owner.id
    assert events[3].details["reason"] == "fits"


def test_ai_batch_start_and_finish_are_audited(
    auth_as, a_project, session, monkeypatch, an_article_in
):
    from contextlib import nullcontext
    from unittest.mock import AsyncMock

    from app.core.config import Settings
    from app.features.criteria.models import Criterion, CriterionType
    from app.features.screening import flows

    monkeypatch.setattr(
        "app.features.research.agent.get_settings",
        lambda: Settings(_env_file=None, secret_key="x", anthropic_api_key="k"),
    )
    monkeypatch.setattr(
        "app.features.screening.routers.batch_ai_screening_flow", AsyncMock()
    )
    client, owner = auth_as()
    project = a_project(owner)
    an_article_in(project)
    session.add(
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="d",
        )
    )
    session.commit()
    assert client.post(f"{BASE}/{project.id}/screening/run-ai").status_code == 200
    started = session.query(AuditEvent).filter_by(action="ai_batch.started").one()
    assert started.details["article_count"] == 1 and started.user_id == owner.id

    # the flow records its own completion event
    monkeypatch.setattr(flows, "Session", lambda _engine: nullcontext(session))
    monkeypatch.setattr(flows.NotificationService, "notify_room", AsyncMock())
    monkeypatch.setattr(flows.NotificationService, "notify_user_in_room", AsyncMock())

    async def run():
        return await flows.batch_ai_screening_flow.fn(project.id, [], owner.id)

    import asyncio

    asyncio.run(run())
    finished = session.query(AuditEvent).filter_by(action="ai_batch.finished").one()
    assert finished.details == {"total": 0, "screened": 0, "errors": 0, "skipped": 0}


def test_deleting_project_removes_members_and_audit(
    auth_as, a_project, a_member, session
):
    from app.features.projects.models import ProjectMember

    client, owner = auth_as()
    project = a_project(owner)
    a_member(project)
    client.post(
        f"{BASE}/{project.id}/criteria",
        json={"type": "inclusion", "code": "I1", "description": "d"},
    )
    pid = project.id
    assert client.delete(f"{BASE}/{pid}").status_code == 204
    assert session.query(ProjectMember).filter_by(project_id=pid).count() == 0
    assert session.query(AuditEvent).filter_by(project_id=pid).count() == 0
