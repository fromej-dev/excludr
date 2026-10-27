"""Criterion versioning."""

from app.features.criteria.models import Criterion, CriterionType

BASE = "api/v1/projects"


def _make(client, pid, **kw):
    body = {"type": "inclusion", "code": "I1", "description": "d", "rationale": "r"}
    body.update(kw)
    res = client.post(f"{BASE}/{pid}/criteria", json=body)
    assert res.status_code == 201
    return res.json()


def test_new_criterion_version_is_1(auth_as, a_project):
    client, user = auth_as()
    p = a_project(user)
    assert _make(client, p.id)["version"] == 1


def test_version_increments_on_content_changes(auth_as, a_project):
    client, user = auth_as()
    p = a_project(user)
    c = _make(client, p.id)
    url = f"{BASE}/{p.id}/criteria/{c['id']}"
    expected = 1
    for patch in (
        {"description": "new d"},
        {"rationale": "new r"},
        {"code": "I9"},
        {"type": "exclusion"},
        {"is_active": False},
        {"is_active": True},
    ):
        res = client.patch(url, json=patch)
        assert res.status_code == 200
        expected += 1
        assert res.json()["version"] == expected, patch


def test_version_unchanged_for_noop_and_order(auth_as, a_project):
    client, user = auth_as()
    p = a_project(user)
    c = _make(client, p.id)
    url = f"{BASE}/{p.id}/criteria/{c['id']}"
    # Same description again: no real change
    assert client.patch(url, json={"description": "d"}).json()["version"] == 1
    # Order change via patch
    assert client.patch(url, json={"order": 5}).json()["version"] == 1


def test_reorder_does_not_bump_version(auth_as, a_project):
    client, user = auth_as()
    p = a_project(user)
    a = _make(client, p.id, code="I1")
    b = _make(client, p.id, code="I2")
    res = client.post(
        f"{BASE}/{p.id}/criteria/reorder",
        json={"criterion_ids": [b["id"], a["id"]]},
    )
    assert res.status_code == 200
    assert {c["version"] for c in res.json()} == {1}


def test_version_default_on_model(session, a_project):
    p = a_project()
    c = Criterion(
        project_id=p.id, type=CriterionType.inclusion, code="X", description="d"
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    assert c.version == 1
