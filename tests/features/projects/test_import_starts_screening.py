"""Imported articles go straight to title/abstract screening.

Covers the import flows, dedup leaving existing articles alone, the
``start-screening`` endpoint's idempotency and the data migration that releases
articles left in ``imported`` by older versions.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

from app.features.projects.flows import parse_pubmed_file_flow, parse_ris_file_flow
from app.features.projects.models import Project
from app.features.research.models import Article, ArticleStatus
from app.features.screening.models import ScreeningStage
from app.features.users.models import User

API = "api/v1/projects"
REPO_ROOT = Path(__file__).resolve().parents[3]


class _Ctx:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


@pytest.fixture
def use_test_session(session, monkeypatch):
    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session", lambda: _Ctx(session)
    )


def _ris(tmp_path, entries, name="x.ris"):
    lines = []
    for e in entries:
        lines += ["TY  - JOUR", f"TI  - {e['title']}"]
        if e.get("year"):
            lines.append(f"PY  - {e['year']}")
        if e.get("doi"):
            lines.append(f"DO  - {e['doi']}")
        lines += ["ER  - ", ""]
    path = tmp_path / f"abc_{name}"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _articles(session, project_id):
    return session.exec(select(Article).where(Article.project_id == project_id)).all()


@pytest.mark.usefixtures("use_test_session")
def test_ris_import_creates_articles_in_screening(tmp_path, a_project, session):
    project = a_project()
    entries = [
        {"title": "Paper one", "year": 2020, "doi": "10.1/one"},
        {"title": "Paper two", "year": 2021, "doi": "10.1/two"},
    ]
    result = parse_ris_file_flow(_ris(tmp_path, entries), project.id)

    assert result["articles_created"] == 2
    arts = _articles(session, project.id)
    assert len(arts) == 2
    assert all(a.status == ArticleStatus.screening for a in arts)
    assert all(a.current_stage == ScreeningStage.title_abstract for a in arts)


@pytest.mark.usefixtures("use_test_session")
def test_pubmed_import_creates_articles_in_screening(tmp_path, a_project, session):
    project = a_project()
    path = tmp_path / "abc_p.txt"
    path.write_text(
        "PMID- 111\nTI  - Pubmed paper\nDP  - 2020\nAB  - Abstract.\n\n"
        "PMID- 222\nTI  - Another paper\nDP  - 2021\nAB  - Abstract.\n\n",
        encoding="utf-8",
    )
    result = parse_pubmed_file_flow(str(path), project.id)

    assert result["articles_created"] == 2
    arts = _articles(session, project.id)
    assert {a.status for a in arts} == {ArticleStatus.screening}
    assert {a.current_stage for a in arts} == {ScreeningStage.title_abstract}


@pytest.mark.usefixtures("use_test_session")
def test_dedup_leaves_existing_articles_status_alone(
    tmp_path, a_project, an_article_in, session
):
    project = a_project()
    excluded = an_article_in(
        project,
        title="Excluded paper",
        doi="10.1/ex",
        status=ArticleStatus.excluded,
        current_stage=ScreeningStage.completed,
    )
    legacy = an_article_in(
        project, title="Legacy paper", doi="10.1/legacy", status=ArticleStatus.imported
    )
    entries = [
        {"title": "Excluded paper", "year": 2020, "doi": "10.1/ex"},
        {"title": "Legacy paper", "year": 2020, "doi": "10.1/legacy"},
        {"title": "Fresh paper", "year": 2020, "doi": "10.1/new"},
    ]
    result = parse_ris_file_flow(_ris(tmp_path, entries), project.id)

    assert result["articles_created"] == 1
    assert result["duplicates"] == 2
    session.refresh(excluded)
    session.refresh(legacy)
    assert excluded.status == ArticleStatus.excluded
    assert excluded.current_stage == ScreeningStage.completed
    assert legacy.status == ArticleStatus.imported
    fresh = session.exec(select(Article).where(Article.doi == "10.1/new")).one()
    assert fresh.status == ArticleStatus.screening


def test_upload_endpoint_makes_articles_screenable(
    auth_as, a_project, session, monkeypatch
):
    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session", lambda: _Ctx(session)
    )
    client, user = auth_as()
    project = a_project(user)
    with open("./tests/docs/test.ris", "rb") as f:
        res = client.post(
            f"{API}/{project.id}/upload/ris", files={"file": ("test.ris", f.read())}
        )
    assert res.status_code == 200
    created = res.json()["result"]["articles_created"]
    assert created > 0

    stats = client.get(f"{API}/{project.id}/screening/stats").json()
    assert stats["imported_not_started"] == 0
    assert stats["title_abstract_total"] == created


def test_start_screening_is_idempotent(auth_as, a_project, an_article_in, session):
    client, user = auth_as()
    project = a_project(user)
    a1 = an_article_in(project, status=ArticleStatus.imported)
    a2 = an_article_in(project, status=ArticleStatus.imported)
    an_article_in(project)  # already screening

    first = client.post(f"{API}/{project.id}/articles/start-screening")
    assert first.status_code == 200
    assert first.json()["count"] == 2
    for a in (a1, a2):
        session.refresh(a)
        assert a.status == ArticleStatus.screening
        assert a.current_stage == ScreeningStage.title_abstract

    second = client.post(f"{API}/{project.id}/articles/start-screening")
    assert second.status_code == 200
    assert second.json()["count"] == 0


def test_migration_moves_imported_articles_to_screening(tmp_path):
    """Run the data migration against a fresh SQLite DB at the previous revision.

    The historical migrations are PostgreSQL-only (``CREATE TYPE``), so the schema
    is built from the models and stamped at the parent revision; Alembic then
    runs only this migration. It runs in a subprocess so Alembic's logging setup
    does not leak into the test process.
    """
    db = tmp_path / "migrate.db"
    url = f"sqlite:///{db}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(email="m@example.com", name="m", hashed_password="x")
        s.add(user)
        s.flush()
        project = Project(name="p", description="d", owner_id=user.id)
        s.add(project)
        s.flush()
        s.add_all(
            [
                Article(project_id=project.id, title="stuck", doi="10.1/a"),
                Article(
                    project_id=project.id,
                    title="decided",
                    doi="10.1/b",
                    status=ArticleStatus.excluded,
                    current_stage=ScreeningStage.completed,
                ),
            ]
        )
        s.commit()
    engine.dispose()

    env = {**os.environ, "DATABASE_URL": url}

    def alembic(*args):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=REPO_ROOT,
            env=env,
            check=True,
            capture_output=True,
        )

    alembic("stamp", "f2b8d4e6a1c3")
    alembic("upgrade", "a9c4e2f7d1b6")  # this migration only, not later ones

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = dict(
            conn.execute(
                text("SELECT title, status || '/' || current_stage FROM article")
            )
            .tuples()
            .all()
        )
        assert rows == {
            "stuck": "screening/title_abstract",
            "decided": "excluded/completed",
        }
        # Downgrade is a documented no-op for the data.
    alembic("downgrade", "f2b8d4e6a1c3")
    with engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM article WHERE title = 'stuck'")
        ).scalar_one()
    assert status == "screening"
    engine.dispose()
