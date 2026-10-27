"""Tests for the retrieval Prefect flow and the full-text related endpoints."""

from contextlib import nullcontext
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlmodel import select

from app.core.config import get_settings
from app.features.audit.models import AuditEvent
from app.features.research import flows
from app.features.research.models import ArticleStatus
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)
from .fulltext_helpers import PDF_BYTES, pdf_response

NO_DOI_HIT = httpx.Response(404)


def unpaywall(doi: str) -> str:
    return f"api.unpaywall.org/v2/{doi}"


def oa_pdf(doi: str, host: str = "oa.example.org"):
    return httpx.Response(
        200, json={"best_oa_location": {"url_for_pdf": f"https://{host}/{doi}.pdf"}}
    )


@pytest.fixture
def notifier(monkeypatch):
    room = AsyncMock(return_value=1)
    user = AsyncMock(return_value=True)
    monkeypatch.setattr(flows.NotificationService, "notify_room", room)
    monkeypatch.setattr(flows.NotificationService, "notify_user_in_room", user)
    return room, user


@pytest.fixture
def flow_session(session, monkeypatch):
    monkeypatch.setattr(flows, "Session", lambda _engine: nullcontext(session))
    return session


@pytest.fixture
def awaiting(an_article_in):
    def _make(project, **kw):
        return an_article_in(
            project,
            status=ArticleStatus.awaiting_full_text,
            current_stage=ScreeningStage.full_text,
            **kw,
        )

    return _make


# --------------------------------------------------------------------- flow


@pytest.mark.asyncio
async def test_flow_isolates_failures_and_notifies(
    flow_session, a_user, a_project, awaiting, web, notifier, session
):
    user = a_user()
    project = a_project(user)
    good = awaiting(project, doi="10.1/good")
    bad = awaiting(project, doi="10.1/bad")
    boom = awaiting(project, doi="10.1/boom")
    web.add(unpaywall("10.1/good"), oa_pdf("good"))
    web.add("oa.example.org/good.pdf", pdf_response())
    web.add(unpaywall("10.1/bad"), NO_DOI_HIT)
    web.add("www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/", httpx.Response(200, json={}))

    def explode(request):
        raise RuntimeError("secret internals")

    web.add(unpaywall("10.1/boom"), explode)

    result = await flows.retrieve_fulltext_flow.fn(
        project.id, [good.id, bad.id, boom.id, 99999], user.id
    )

    assert result == {"total": 4, "retrieved": 1, "failed": 3}
    for a in (good, bad, boom):
        session.refresh(a)
    assert good.status == ArticleStatus.full_text_retrieved
    assert bad.status == ArticleStatus.awaiting_full_text
    assert bad.full_text_retrieval_error
    assert boom.status == ArticleStatus.awaiting_full_text
    assert boom.full_text_retrieval_error

    room, user_notify = notifier
    payloads = [c.kwargs["data"] for c in room.await_args_list]
    assert all(
        c.kwargs["room_name"] == f"project_{project.id}" for c in room.await_args_list
    )
    progress = [p for p in payloads if p["type"] == "fulltext_progress"]
    assert len(progress) == 4
    assert progress[0]["article_id"] == good.id and progress[0]["success"] is True
    assert progress[0]["source"] == "unpaywall"
    assert progress[1]["success"] is False
    assert "secret" not in str(payloads)
    # Every message names its project so clients can ignore other projects' events
    assert all(p["project_id"] == project.id for p in payloads)
    final = payloads[-1]
    assert final["type"] == "fulltext_complete"
    assert (final["retrieved"], final["errors"], final["total"]) == (1, 3, 4)
    user_notify.assert_awaited_once()
    assert user_notify.await_args.kwargs["data"]["type"] == "fulltext_complete"
    assert user_notify.await_args.kwargs["data"]["project_id"] == project.id

    actions = [
        e.action
        for e in session.exec(
            select(AuditEvent).where(AuditEvent.project_id == project.id)
        ).all()
    ]
    assert "fulltext_batch.started" in actions
    assert "fulltext_batch.finished" in actions


@pytest.mark.asyncio
async def test_flow_ignores_articles_of_other_projects(
    flow_session, a_user, a_project, awaiting, web, notifier
):
    user = a_user()
    mine, other = a_project(user), a_project(user)
    foreign = awaiting(other, doi="10.1/foreign")

    result = await flows.retrieve_fulltext_flow.fn(mine.id, [foreign.id], user.id)

    assert result["failed"] == 1 and web.requests == []


# ---------------------------------------------------------------- endpoints


def _base(project):
    return f"api/v1/projects/{project.id}/articles"


def test_single_retrieve_success_and_failure(auth_as, a_project, awaiting, web):
    client, user = auth_as()
    project = a_project(user)
    ok = awaiting(project, doi="10.1/ok")
    nope = awaiting(project, doi="10.1/nope")
    web.add(unpaywall("10.1/ok"), oa_pdf("ok")).add(
        "oa.example.org/ok.pdf", pdf_response()
    )
    web.add(unpaywall("10.1/nope"), NO_DOI_HIT)
    web.add("www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/", httpx.Response(200, json={}))

    res = client.post(f"{_base(project)}/{ok.id}/retrieve-fulltext")
    assert res.status_code == 200
    body = res.json()
    assert body["retrieved"] is True and body["source"] == "unpaywall"
    assert body["attempts"][0] == {
        "source": "unpaywall",
        "status": "success",
        "detail": None,
    }

    res = client.post(f"{_base(project)}/{nope.id}/retrieve-fulltext")
    assert res.status_code == 200
    assert res.json()["retrieved"] is False and res.json()["error"]


def test_single_retrieve_conflict_notfound_and_permissions(
    auth_as, a_user, a_project, a_member, awaiting, an_article_in, web
):
    client, user = auth_as()
    project = a_project(user)
    screening = an_article_in(project)  # status=screening
    assert (
        client.post(f"{_base(project)}/{screening.id}/retrieve-fulltext").status_code
        == 409
    )
    assert client.post(f"{_base(project)}/9999/retrieve-fulltext").status_code == 404

    pending = awaiting(project, doi="10.1/x")
    reviewer = a_member(project)
    rclient, _ = auth_as(reviewer)
    assert (
        rclient.post(f"{_base(project)}/{pending.id}/retrieve-fulltext").status_code
        == 403
    )
    assert rclient.post(f"{_base(project)}/retrieve-fulltext").status_code == 403
    assert web.requests == []


def test_bulk_retrieve_schedules_flow_with_ids_only(
    auth_as, a_project, awaiting, an_article_in, monkeypatch, session
):
    client, user = auth_as()
    project = a_project(user)
    a1 = awaiting(project)
    a2 = awaiting(project)
    has_text = awaiting(project, full_text_retrieved=True)
    other_status = an_article_in(project)
    calls = []

    async def fake_flow(project_id, article_ids, user_id):
        calls.append((project_id, article_ids, user_id))

    from app.features.research import routers

    monkeypatch.setattr(routers, "retrieve_fulltext_flow", fake_flow)

    res = client.post(f"{_base(project)}/retrieve-fulltext")
    assert res.status_code == 200 and res.json()["count"] == 2
    assert calls == [(project.id, [a1.id, a2.id], user.id)]

    calls.clear()
    res = client.post(
        f"{_base(project)}/retrieve-fulltext",
        json={"article_ids": [a2.id, has_text.id, other_status.id]},
    )
    assert res.json()["count"] == 1
    assert calls == [(project.id, [a2.id], user.id)]

    calls.clear()
    res = client.post(f"{_base(project)}/retrieve-fulltext", json={"article_ids": []})
    assert res.json()["count"] == 0 and calls == []


# ---------------------------------------------------------------- pdf serve


def _stored_pdf(awaiting, project, session, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PDF_BYTES)
    article = awaiting(project, full_text_path=str(path), full_text_retrieved=True)
    return article


def test_serve_pdf_inline_for_viewer(
    auth_as, a_user, a_project, a_member, awaiting, session
):
    from app.features.projects.models import ProjectRole

    client, owner = auth_as()
    project = a_project(owner)
    storage = get_settings().pdf_storage_path
    from pathlib import Path

    article = _stored_pdf(awaiting, project, session, Path(storage) / "a.pdf")
    viewer = a_member(project, ProjectRole.viewer)
    vclient, _ = auth_as(viewer)

    res = vclient.get(f"{_base(project)}/{article.id}/fulltext/pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].startswith("inline")
    assert res.content == PDF_BYTES


def test_serve_pdf_404_when_missing_or_foreign_or_non_member(
    auth_as, a_project, awaiting, tmp_path, session
):
    client, owner = auth_as()
    project = a_project(owner)
    none = awaiting(project)
    assert client.get(f"{_base(project)}/{none.id}/fulltext/pdf").status_code == 404
    assert client.get(f"{_base(project)}/9999/fulltext/pdf").status_code == 404

    outsider, _ = auth_as()
    assert outsider.get(f"{_base(project)}/{none.id}/fulltext/pdf").status_code == 403


def test_serve_pdf_refuses_paths_outside_storage(
    auth_as, a_project, awaiting, tmp_path, session
):
    client, owner = auth_as()
    project = a_project(owner)
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(PDF_BYTES)
    outside = awaiting(project, full_text_path=str(secret))
    traversal = awaiting(
        project,
        full_text_path=f"{get_settings().pdf_storage_path}/../secret.pdf",
    )
    sibling = tmp_path / "pdfs-evil"
    sibling.mkdir()
    (sibling / "x.pdf").write_bytes(PDF_BYTES)
    prefix_trick = awaiting(project, full_text_path=str(sibling / "x.pdf"))

    for article in (outside, traversal, prefix_trick):
        res = client.get(f"{_base(project)}/{article.id}/fulltext/pdf")
        assert res.status_code == 404


# ---------------------------------------------------------------- manual


def test_manual_upload_sets_source_manual(auth_as, a_project, awaiting):
    client, user = auth_as()
    project = a_project(user)
    article = awaiting(project, full_text_retrieval_error="earlier failure")

    res = client.post(
        f"{_base(project)}/{article.id}/fulltext/upload",
        files={"file": ("x.pdf", PDF_BYTES)},
    )
    assert res.status_code == 200
    got = client.get(f"{_base(project)}/{article.id}").json()
    assert got["full_text_source"] == "manual"
    assert got["full_text_retrieval_error"] is None


# ------------------------------------------------------------------ /me


def test_me_returns_role(auth_as, a_project, a_member):
    from app.features.projects.models import ProjectRole

    client, owner = auth_as()
    project = a_project(owner)
    res = client.get(f"api/v1/projects/{project.id}/me")
    assert res.status_code == 200
    assert res.json() == {
        "project_id": project.id,
        "user_id": owner.id,
        "role": "owner",
    }
    viewer = a_member(project, ProjectRole.viewer)
    vclient, _ = auth_as(viewer)
    assert vclient.get(f"api/v1/projects/{project.id}/me").json()["role"] == "viewer"
    stranger, _ = auth_as()
    assert stranger.get(f"api/v1/projects/{project.id}/me").status_code == 403


# ------------------------------------------------------------ list filters


def _ids(res):
    assert res.status_code == 200, res.text
    return sorted(a["id"] for a in res.json()["data"])


def test_list_has_full_text_filter(auth_as, a_project, awaiting):
    client, user = auth_as()
    project = a_project(user)
    without = awaiting(project)
    with_text = awaiting(project, full_text_retrieved=True)

    assert _ids(client.get(f"{_base(project)}?has_full_text=true")) == [with_text.id]
    assert _ids(client.get(f"{_base(project)}?has_full_text=false")) == [without.id]
    assert _ids(client.get(_base(project))) == sorted([without.id, with_text.id])


def test_pending_for_me_matches_screening_next(
    auth_as, a_project, a_member, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    mine_done = an_article_in(project)
    todo = an_article_in(project)
    other_done = an_article_in(project)
    ft_ready = an_article_in(
        project,
        status=ArticleStatus.full_text_retrieved,
        current_stage=ScreeningStage.full_text,
    )
    an_article_in(project, status=ArticleStatus.included)
    reviewer = a_member(project)

    def decide(article, user, stage=ScreeningStage.title_abstract, ai=False):
        session.add(
            ScreeningDecision(
                article_id=article.id,
                stage=stage,
                decision=ScreeningDecisionType.include,
                source=DecisionSource.ai_agent if ai else DecisionSource.human,
                reviewer_id=None if ai else user.id,
            )
        )
        session.commit()

    decide(mine_done, reviewer)
    decide(other_done, owner)  # decided by someone else: still pending for me
    decide(todo, reviewer, ai=True)  # AI decisions do not count

    rclient, _ = auth_as(reviewer)
    url = _base(project)
    assert _ids(rclient.get(f"{url}?pending_for_me=true")) == sorted(
        [todo.id, other_done.id]
    )
    assert _ids(
        rclient.get(f"{url}?pending_for_me=true&stage=title_abstract")
    ) == sorted([todo.id, other_done.id])
    assert _ids(rclient.get(f"{url}?pending_for_me=true&stage=full_text")) == [
        ft_ready.id
    ]
    assert rclient.get(f"{url}?pending_for_me=true&stage=completed").status_code == 422
    # without the flag the old behaviour is unchanged
    assert len(_ids(rclient.get(url))) == 5
    # the first pending article is what /screening/next serves
    nxt = rclient.get(f"api/v1/projects/{project.id}/screening/next").json()
    assert nxt["article"]["id"] == min(todo.id, other_done.id)


def test_pending_for_me_respects_dual_screening(
    auth_as, a_project, a_member, an_article_in, session
):
    client, owner = auth_as()
    project = a_project(owner)
    project.required_reviewers = 2
    session.add(project)
    session.commit()
    article = an_article_in(project)
    r1, r2 = a_member(project), a_member(project)
    for r in (r1, r2):
        session.add(
            ScreeningDecision(
                article_id=article.id,
                stage=ScreeningStage.title_abstract,
                decision=ScreeningDecisionType.include,
                source=DecisionSource.human,
                reviewer_id=r.id,
            )
        )
    session.commit()

    c3, _ = auth_as(owner)
    assert _ids(c3.get(f"{_base(project)}?pending_for_me=true")) == []
