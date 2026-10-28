"""API tests for bulk full-text PDF upload (stage, match, confirm)."""

import os
import time

import fitz
import pytest
from sqlmodel import select

from app.core.config import get_settings
from app.features.audit.models import AuditEvent
from app.features.research import pdf_bulk_upload
from app.features.research.models import ArticleStatus

TITLE = "Parenting stress and child anxiety: a longitudinal cohort study"


def make_pdf(text: str = "", *, title: str = "", subject: str = "") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_textbox(fitz.Rect(50, 50, 550, 800), text, fontsize=10)
    doc.set_metadata({"title": title, "subject": subject})
    data = doc.tobytes()
    doc.close()
    return data


def _match_url(project):
    return f"api/v1/projects/{project.id}/articles/fulltext/bulk/match"


def _confirm_url(project):
    return f"api/v1/projects/{project.id}/articles/fulltext/bulk/confirm"


def _staged(project) -> list[str]:
    directory = pdf_bulk_upload.staging_dir(project.id)
    return os.listdir(directory) if os.path.isdir(directory) else []


@pytest.fixture
def owner_project(auth_as, a_project):
    client, user = auth_as()
    return client, a_project(user)


def _awaiting(an_article_in, project, **kwargs):
    return an_article_in(project, status=ArticleStatus.awaiting_full_text, **kwargs)


def test_match_then_confirm_attaches_pdf(owner_project, an_article_in, session):
    client, project = owner_project
    by_doi = _awaiting(an_article_in, project, title="Other", doi="10.1000/abc.123")
    by_title = _awaiting(
        an_article_in, project, title=TITLE, authors=["Smith, John"], year=2020
    )

    res = client.post(
        _match_url(project),
        files=[
            ("files", ("a.pdf", make_pdf("Body text", subject="doi:10.1000/abc.123"))),
            ("files", ("b.pdf", make_pdf(f"{TITLE}\nJohn Smith\nPublished 2020"))),
            ("files", ("c.pdf", make_pdf("Nothing to see here"))),
        ],
    )
    assert res.status_code == 200, res.text
    results = res.json()
    assert [r["filename"] for r in results] == ["a.pdf", "b.pdf", "c.pdf"]
    assert results[0]["match"]["article_id"] == by_doi.id
    assert results[0]["match"]["method"] == "doi_metadata"
    assert results[1]["match"]["article_id"] == by_title.id
    assert results[1]["match"]["confidence"] == "high"
    assert results[1]["match"]["title"] == TITLE
    assert results[1]["text_extracted"] is True
    assert results[2]["match"] is None
    assert len(_staged(project)) == 3

    # Nothing is attached before confirming
    session.refresh(by_doi)
    assert by_doi.full_text_retrieved is False

    res = client.post(
        _confirm_url(project),
        json={
            "attach": [
                {"upload_id": results[0]["upload_id"], "article_id": by_doi.id},
                {"upload_id": results[1]["upload_id"], "article_id": by_title.id},
            ],
            "discard": [results[2]["upload_id"]],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["attached"] == 2
    assert {r["status"] for r in body["results"]} == {"attached"}
    assert _staged(project) == []

    for article in (by_doi, by_title):
        session.refresh(article)
        assert article.full_text_retrieved is True
        assert article.full_text_source == "manual"
        assert article.status == ArticleStatus.full_text_retrieved
        assert (
            os.path.dirname(article.full_text_path) == get_settings().pdf_storage_path
        )
        assert os.path.isfile(article.full_text_path)
    session.refresh(by_title)
    assert TITLE.split(":")[0] in by_title.full_text_content

    event = session.exec(
        select(AuditEvent).where(AuditEvent.action == "fulltext.pdfs_uploaded")
    ).one()
    assert event.details["attached"] == 2


def test_non_pdf_files_are_reported_per_file(owner_project, an_article_in):
    client, project = owner_project
    res = client.post(
        _match_url(project),
        files=[
            ("files", ("notes.txt", b"hello")),
            ("files", ("fake.pdf", b"<html>")),
            ("files", ("broken.pdf", b"%PDF-1.4 garbage")),
            ("files", ("ok.pdf", make_pdf("text"))),
        ],
    )
    assert res.status_code == 200
    results = res.json()
    assert [r["error"] is not None for r in results] == [True, True, True, False]
    assert all(r["upload_id"] is None for r in results[:3])
    assert len(_staged(project)) == 1


def test_existing_full_text_is_skipped_unless_replaced(
    owner_project, an_article_in, session
):
    client, project = owner_project
    storage = get_settings().pdf_storage_path
    os.makedirs(storage, exist_ok=True)
    old_path = os.path.join(storage, "old.pdf")
    with open(old_path, "wb") as fh:
        fh.write(b"%PDF-1.4 old")
    article = an_article_in(
        project,
        doi="10.1000/xyz",
        status=ArticleStatus.full_text_retrieved,
        full_text_retrieved=True,
        full_text_path=old_path,
    )

    def stage():
        res = client.post(
            _match_url(project),
            files=[("files", ("10.1000_xyz.pdf", make_pdf("New version")))],
        )
        result = res.json()[0]
        assert result["match"]["has_full_text"] is True
        return result["upload_id"]

    upload_id = stage()
    res = client.post(
        _confirm_url(project),
        json={"attach": [{"upload_id": upload_id, "article_id": article.id}]},
    )
    assert res.json()["results"][0]["status"] == "skipped"
    session.refresh(article)
    assert article.full_text_path == old_path

    res = client.post(
        _confirm_url(project),
        json={
            "attach": [
                {"upload_id": upload_id, "article_id": article.id, "replace": True}
            ]
        },
    )
    assert res.json()["results"][0]["status"] == "attached"
    session.refresh(article)
    assert article.full_text_path != old_path
    assert "New version" in article.full_text_content
    assert not os.path.exists(old_path)


def test_confirm_rejects_two_files_for_one_article(owner_project, an_article_in):
    client, project = owner_project
    article = _awaiting(an_article_in, project)
    res = client.post(
        _confirm_url(project),
        json={
            "attach": [
                {"upload_id": "a", "article_id": article.id},
                {"upload_id": "b", "article_id": article.id},
            ]
        },
    )
    assert res.status_code == 422


def test_confirm_unknown_upload_or_foreign_article(
    owner_project, an_article_in, a_project, session
):
    client, project = owner_project
    own_article = an_article_in(project)
    other_article = an_article_in(a_project())
    res = client.post(
        _match_url(project), files=[("files", ("x.pdf", make_pdf("text")))]
    )
    upload_id = res.json()[0]["upload_id"]

    res = client.post(
        _confirm_url(project),
        json={
            "attach": [
                {"upload_id": "../../etc/passwd", "article_id": own_article.id},
                {"upload_id": upload_id, "article_id": other_article.id},
            ]
        },
    )
    statuses = [(r["status"], r["detail"]) for r in res.json()["results"]]
    assert statuses[0][0] == "error" and "not found" in statuses[0][1].lower()
    assert statuses[1] == ("error", "Article not found")
    session.refresh(other_article)
    assert other_article.full_text_retrieved is False


def test_staged_files_of_another_project_cannot_be_attached(
    auth_as, a_project, an_article_in
):
    client, user = auth_as()
    first, second = a_project(user), a_project(user)
    article = an_article_in(second)
    res = client.post(_match_url(first), files=[("files", ("x.pdf", make_pdf("t")))])
    upload_id = res.json()[0]["upload_id"]
    res = client.post(
        _confirm_url(second),
        json={"attach": [{"upload_id": upload_id, "article_id": article.id}]},
    )
    assert res.json()["results"][0]["status"] == "error"


def test_old_staged_files_are_swept(owner_project):
    client, project = owner_project
    client.post(_match_url(project), files=[("files", ("x.pdf", make_pdf("t")))])
    assert len(_staged(project)) == 1
    pdf_bulk_upload.sweep_staging(
        project.id, now=time.time() + pdf_bulk_upload.STAGING_TTL_SECONDS + 1
    )
    assert _staged(project) == []


def test_too_many_files(owner_project, monkeypatch):
    client, project = owner_project
    monkeypatch.setattr(pdf_bulk_upload, "MAX_FILES_PER_REQUEST", 1)
    pdf = make_pdf("t")
    res = client.post(
        _match_url(project),
        files=[("files", ("a.pdf", pdf)), ("files", ("b.pdf", pdf))],
    )
    assert res.status_code == 422
    assert _staged(project) == []


def test_reviewers_cannot_bulk_upload(auth_as, a_project, a_member, token_for):
    owner_client, owner = auth_as()
    project = a_project(owner)
    reviewer = a_member(project)
    owner_client.headers["Authorization"] = f"Bearer {token_for(reviewer)}"
    res = owner_client.post(
        _match_url(project), files=[("files", ("a.pdf", make_pdf("t")))]
    )
    assert res.status_code == 403
    res = owner_client.post(_confirm_url(project), json={"attach": []})
    assert res.status_code == 403


def test_matching_ignores_other_projects_articles(
    owner_project, an_article_in, a_project
):
    client, project = owner_project
    an_article_in(a_project(), doi="10.1000/elsewhere")
    res = client.post(
        _match_url(project),
        files=[("files", ("10.1000_elsewhere.pdf", make_pdf("text")))],
    )
    assert res.json()[0]["match"] is None
    assert res.json()[0]["candidates"] == []
