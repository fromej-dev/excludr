"""Project members, roles and shared permission checks."""

import pytest

from app.features.projects.models import ProjectMember, ProjectRole

BASE = "api/v1/projects"


def _login(client, token_for, user):
    client.headers["Authorization"] = f"Bearer {token_for(user)}"


def test_creating_project_creates_owner_membership(auth_client, session):
    res = auth_client.post(BASE, json={"name": "Review one"})
    assert res.status_code == 201
    members = session.query(ProjectMember).filter_by(project_id=res.json()["id"]).all()
    assert [(m.user_id, m.role) for m in members] == [
        (members[0].user_id, ProjectRole.owner)
    ]


def test_list_members_any_member(auth_as, a_project, a_member, token_for):
    client, owner = auth_as()
    project = a_project(owner)
    viewer = a_member(project, ProjectRole.viewer)
    res = client.get(f"{BASE}/{project.id}/members")
    assert res.status_code == 200
    assert [m["role"] for m in res.json()] == ["owner", "viewer"]
    assert res.json()[0]["email"] == owner.email

    _login(client, token_for, viewer)
    assert client.get(f"{BASE}/{project.id}/members").status_code == 200


def test_list_members_non_member_forbidden(auth_as, a_project):
    client, _ = auth_as()
    project = a_project()
    assert client.get(f"{BASE}/{project.id}/members").status_code == 403


def test_add_member_by_email_owner_only(
    auth_as, a_project, a_user, a_member, token_for
):
    client, owner = auth_as()
    project = a_project(owner)
    newbie = a_user()
    res = client.post(
        f"{BASE}/{project.id}/members", json={"email": newbie.email, "role": "reviewer"}
    )
    assert res.status_code == 201
    assert res.json()["user_id"] == newbie.id and res.json()["role"] == "reviewer"

    # duplicate -> 409, unknown -> 404, owner role -> 422
    assert (
        client.post(
            f"{BASE}/{project.id}/members", json={"email": newbie.email}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{BASE}/{project.id}/members", json={"email": owner.email}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{BASE}/{project.id}/members", json={"email": "nobody@example.com"}
        ).status_code
        == 404
    )
    other = a_user()
    assert (
        client.post(
            f"{BASE}/{project.id}/members", json={"email": other.email, "role": "owner"}
        ).status_code
        == 422
    )

    # a reviewer cannot add members
    _login(client, token_for, newbie)
    assert (
        client.post(
            f"{BASE}/{project.id}/members", json={"email": other.email}
        ).status_code
        == 403
    )


def test_change_role_and_remove(auth_as, a_project, a_member, session, token_for):
    client, owner = auth_as()
    project = a_project(owner)
    reviewer = a_member(project, ProjectRole.reviewer)

    res = client.patch(
        f"{BASE}/{project.id}/members/{reviewer.id}", json={"role": "viewer"}
    )
    assert res.status_code == 200 and res.json()["role"] == "viewer"

    # cannot touch the owner
    assert (
        client.patch(
            f"{BASE}/{project.id}/members/{owner.id}", json={"role": "viewer"}
        ).status_code
        == 400
    )
    assert client.delete(f"{BASE}/{project.id}/members/{owner.id}").status_code == 400

    # non-owners cannot change or remove
    _login(client, token_for, reviewer)
    assert client.delete(f"{BASE}/{project.id}/members/{owner.id}").status_code == 403

    _login(client, token_for, owner)
    assert (
        client.delete(f"{BASE}/{project.id}/members/{reviewer.id}").status_code == 204
    )
    assert (
        client.delete(f"{BASE}/{project.id}/members/{reviewer.id}").status_code == 404
    )
    # removed member loses access
    _login(client, token_for, reviewer)
    assert client.get(f"{BASE}/{project.id}").status_code == 403


def test_projects_list_includes_member_projects(auth_as, a_project, a_member):
    client, user = auth_as()
    mine = a_project(user)
    shared = a_project()
    a_member(shared, ProjectRole.viewer, user=user)
    a_project()  # unrelated
    res = client.get(BASE)
    ids = {p["id"] for p in res.json()["data"]}
    assert ids == {mine.id, shared.id}


@pytest.mark.parametrize(
    "role,method,path,expected",
    [
        (ProjectRole.viewer, "get", "", 200),
        (ProjectRole.viewer, "get", "/criteria", 200),
        (ProjectRole.viewer, "get", "/articles", 200),
        (ProjectRole.viewer, "get", "/screening/stats", 200),
        (ProjectRole.viewer, "post", "/criteria", 403),
        (ProjectRole.viewer, "patch", "", 403),
        (ProjectRole.viewer, "delete", "", 403),
        (ProjectRole.viewer, "post", "/screening/run-ai", 403),
        (ProjectRole.reviewer, "get", "", 200),
        (ProjectRole.reviewer, "post", "/criteria", 403),
        (ProjectRole.reviewer, "patch", "", 403),
        (ProjectRole.reviewer, "post", "/articles/start-screening", 403),
        (ProjectRole.reviewer, "get", "/audit", 403),
        (ProjectRole.reviewer, "get", "/export?format=csv", 403),
    ],
)
def test_role_matrix(auth_as, a_project, a_member, role, method, path, expected):
    client, owner = auth_as()
    project = a_project(owner)
    user = a_member(project, role)
    _, _ = auth_as(user)
    kwargs = (
        {"json": {"type": "inclusion", "code": "I1", "description": "d"}}
        if (method == "post" and path == "/criteria")
        else {}
    )
    if method == "patch":
        kwargs = {"json": {"description": "new"}}
    res = getattr(client, method)(f"{BASE}/{project.id}{path}", **kwargs)
    assert res.status_code == expected


def test_missing_project_is_404(auth_client):
    assert auth_client.get(f"{BASE}/99999/members").status_code == 404


def test_websocket_room_allowed_for_members(session, a_project, a_member, a_user):
    from app.features.websocket.routers import can_join_room

    owner = a_user()
    project = a_project(owner)
    viewer = a_member(project, ProjectRole.viewer)
    stranger = a_user()
    room = f"project_{project.id}"
    assert can_join_room(owner, room, session)
    assert can_join_room(viewer, room, session)
    assert not can_join_room(stranger, room, session)
