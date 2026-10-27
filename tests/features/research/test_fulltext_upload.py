"""Tests for the full-text PDF upload endpoint hardening."""

import os

import pytest

from app.core.config import get_settings
from app.features.research.models import Article

PDF_BYTES = b"%PDF-1.4\n%fake pdf body\n"


@pytest.fixture
def pdf_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "pdf_storage_path", str(tmp_path))
    return tmp_path


@pytest.fixture
def article_for(session):
    def _make(project):
        article = Article(project_id=project.id, title="T")
        session.add(article)
        session.commit()
        session.refresh(article)
        return article

    return _make


def _url(project, article):
    return f"api/v1/projects/{project.id}/articles/{article.id}/fulltext/upload"


def test_pdf_upload_ok_uses_uuid_filename(auth_as, a_project, article_for, pdf_dir):
    client, user = auth_as()
    project = a_project(user)
    article = article_for(project)

    res = client.post(
        _url(project, article), files={"file": ("../../evil name.pdf", PDF_BYTES)}
    )
    assert res.status_code == 200
    stored = list(pdf_dir.iterdir())
    assert len(stored) == 1
    assert stored[0].suffix == ".pdf"
    assert "evil" not in stored[0].name
    assert "path" not in res.json()


def test_pdf_upload_rejects_bad_magic_bytes(auth_as, a_project, article_for, pdf_dir):
    client, user = auth_as()
    project = a_project(user)
    article = article_for(project)

    res = client.post(
        _url(project, article), files={"file": ("x.pdf", b"<html>not a pdf</html>")}
    )
    assert res.status_code == 400
    assert "PDF" in res.json()["detail"]
    assert os.listdir(pdf_dir) == []


def test_pdf_upload_rejects_wrong_extension(auth_as, a_project, article_for, pdf_dir):
    client, user = auth_as()
    project = a_project(user)
    article = article_for(project)

    res = client.post(_url(project, article), files={"file": ("x.exe", PDF_BYTES)})
    assert res.status_code == 400


def test_pdf_upload_too_large_returns_413(
    auth_as, a_project, article_for, pdf_dir, monkeypatch
):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    client, user = auth_as()
    project = a_project(user)
    article = article_for(project)

    res = client.post(
        _url(project, article),
        files={"file": ("big.pdf", PDF_BYTES + b"x" * (1024 * 1024))},
    )
    assert res.status_code == 413
    assert os.listdir(pdf_dir) == []
