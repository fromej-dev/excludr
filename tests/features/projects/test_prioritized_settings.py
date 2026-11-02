"""Prioritized screening settings: defaults, PATCH rules, audit, cleanup, migration."""

import os
from datetime import datetime, timezone
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from app.features.audit.models import AuditEvent
from app.features.projects.models import Project, ProjectRole
from app.features.research.models import Article
from app.features.screening.models import RankingRun
from app.features.users.models import User

API = "api/v1/projects"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _events(session, project, action):
    return session.exec(
        select(AuditEvent).where(
            AuditEvent.project_id == project.id, AuditEvent.action == action
        )
    ).all()


def test_defaults_exposed_on_project(auth_as, a_project):
    client, owner = auth_as()
    project = a_project(owner)
    body = client.get(f"{API}/{project.id}").json()
    assert body["prioritized_screening"] is False
    assert body["stop_after_consecutive_excludes"] == 100
    assert body["ranking_min_random"] == 0
    assert body["prioritized_screening_enabled_at"] is None
    assert body["stopping_rule_applied_at"] is None


def test_article_new_fields_defaults(a_project, an_article_in):
    article = an_article_in(a_project())
    assert article.relevance_score is None
    assert article.not_screened_stopping_rule is False


def test_owner_updates_screening_rule(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    r = client.patch(
        f"{API}/{project.id}",
        json={
            "prioritized_screening": True,
            "stop_after_consecutive_excludes": 50,
            "ranking_min_random": 20,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["prioritized_screening"] is True
    assert body["stop_after_consecutive_excludes"] == 50
    assert body["ranking_min_random"] == 20
    assert body["prioritized_screening_enabled_at"] is not None
    session.refresh(project)
    assert project.prioritized_screening is True
    assert project.stop_after_consecutive_excludes == 50
    assert project.ranking_min_random == 20


def test_enabled_at_set_only_on_off_to_on(auth_as, a_project, session):
    client, owner = auth_as()
    url = f"{API}/{a_project(owner).id}"
    first = client.patch(url, json={"prioritized_screening": True}).json()[
        "prioritized_screening_enabled_at"
    ]
    assert first is not None
    same = client.patch(url, json={"stop_after_consecutive_excludes": 30}).json()
    assert same["prioritized_screening_enabled_at"] == first
    resend = client.patch(url, json={"prioritized_screening": True}).json()
    assert resend["prioritized_screening_enabled_at"] == first
    off = client.patch(url, json={"prioritized_screening": False}).json()
    assert off["prioritized_screening_enabled_at"] == first
    project = session.get(Project, int(url.rsplit("/", 1)[1]))
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    project.prioritized_screening_enabled_at = old
    session.add(project)
    session.commit()
    again = client.patch(url, json={"prioritized_screening": True}).json()
    new = datetime.fromisoformat(again["prioritized_screening_enabled_at"])
    assert new.replace(tzinfo=timezone.utc) > old


def test_threshold_can_be_cleared(auth_as, a_project):
    client, owner = auth_as()
    url = f"{API}/{a_project(owner).id}"
    r = client.patch(url, json={"stop_after_consecutive_excludes": None})
    assert r.status_code == 200
    assert r.json()["stop_after_consecutive_excludes"] is None
    r = client.patch(url, json={"name": "Renamed project"})
    assert r.json()["name"] == "Renamed project"
    assert r.json()["stop_after_consecutive_excludes"] is None


def test_null_does_not_clear_other_fields(auth_as, a_project):
    client, owner = auth_as()
    url = f"{API}/{a_project(owner).id}"
    client.patch(url, json={"prioritized_screening": True, "ranking_min_random": 5})
    r = client.patch(
        url, json={"ranking_min_random": None, "prioritized_screening": None}
    )
    assert r.status_code == 200
    assert r.json()["ranking_min_random"] == 5
    assert r.json()["prioritized_screening"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"stop_after_consecutive_excludes": 0},
        {"stop_after_consecutive_excludes": -1},
        {"stop_after_consecutive_excludes": 100001},
        {"ranking_min_random": -1},
        {"ranking_min_random": 10001},
        {"prioritized_screening": "maybe"},
    ],
)
def test_validation(auth_as, a_project, payload):
    client, owner = auth_as()
    r = client.patch(f"{API}/{a_project(owner).id}", json=payload)
    assert r.status_code == 422


def test_client_cannot_set_timestamps(auth_as, a_project):
    client, owner = auth_as()
    r = client.patch(
        f"{API}/{a_project(owner).id}",
        json={
            "stopping_rule_applied_at": "2026-01-01T00:00:00Z",
            "prioritized_screening_enabled_at": "2026-01-01T00:00:00Z",
        },
    )
    assert r.status_code == 200
    assert r.json()["stopping_rule_applied_at"] is None
    assert r.json()["prioritized_screening_enabled_at"] is None


@pytest.mark.parametrize("role", [ProjectRole.reviewer, ProjectRole.viewer])
def test_reviewer_and_viewer_cannot_update(auth_as, a_project, a_member, session, role):
    client, owner = auth_as()
    project = a_project(owner)
    member = a_member(project, role)
    auth_as(member)
    r = client.patch(f"{API}/{project.id}", json={"prioritized_screening": True})
    assert r.status_code == 403
    session.refresh(project)
    assert project.prioritized_screening is False


def test_screening_rule_change_audited(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    client.patch(
        f"{API}/{project.id}",
        json={"prioritized_screening": True, "stop_after_consecutive_excludes": 50},
    )
    (event,) = _events(session, project, "project.screening_rule_updated")
    assert event.user_id == owner.id
    assert event.details == {
        "changes": {
            "prioritized_screening": {"from": False, "to": True},
            "stop_after_consecutive_excludes": {"from": 100, "to": 50},
        }
    }
    assert _events(session, project, "project.settings_updated") == []


def test_unchanged_screening_rule_not_audited(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    r = client.patch(f"{API}/{project.id}", json={"ranking_min_random": 0})
    assert r.status_code == 200
    assert session.exec(select(AuditEvent)).all() == []


def test_mixed_update_emits_both_events(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    client.patch(
        f"{API}/{project.id}", json={"name": "New name", "ranking_min_random": 20}
    )
    (settings,) = _events(session, project, "project.settings_updated")
    assert settings.details == {"name": "New name"}
    (rule,) = _events(session, project, "project.screening_rule_updated")
    assert rule.details == {"changes": {"ranking_min_random": {"from": 0, "to": 20}}}


def test_project_delete_removes_ranking_runs(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    session.add(
        RankingRun(
            project_id=project.id,
            model_version="tfidf-logreg-v1",
            method="model",
            trigger="auto",
        )
    )
    session.commit()
    assert client.delete(f"{API}/{project.id}").status_code == 204
    assert session.exec(select(RankingRun)).all() == []


def test_statistical_rule_migration_round_trip(tmp_path):
    """Down- and upgrade the statistical-rule revision; existing rows get defaults."""
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(email="m@example.com", name="m", hashed_password="x")
        s.add(user)
        s.flush()
        s.add(Project(name="proj", description="d", owner_id=user.id))
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

    alembic("stamp", "e5b2d8f4a7c1")
    alembic("downgrade", "d7e3a9c1f5b2")
    engine = create_engine(url)
    cols = {c["name"] for c in inspect(engine).get_columns("project")}
    assert not cols & {"stopping_rule_type", "recall_target", "stopping_alpha"}
    engine.dispose()

    alembic("upgrade", "e5b2d8f4a7c1")
    engine = create_engine(url)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT stopping_rule_type, recall_target, stopping_alpha FROM project"
            )
        ).one()
    assert tuple(row) == ("consecutive", 0.95, 0.05)
    engine.dispose()


def test_migration_adds_prioritized_screening_schema(tmp_path):
    """Down- and upgrade this revision on a SQLite DB built from the models.

    Historical migrations are PostgreSQL-only, so the schema is created from the
    models and stamped; Alembic runs in a subprocess (see test_import_starts_screening).
    """
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(email="m@example.com", name="m", hashed_password="x")
        s.add(user)
        s.flush()
        project = Project(name="proj", description="d", owner_id=user.id)
        s.add(project)
        s.flush()
        s.add(Article(project_id=project.id, title="a"))
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

    alembic("stamp", "d7e3a9c1f5b2")
    alembic("downgrade", "c4d8a2f6e1b9")
    engine = create_engine(url)
    insp = inspect(engine)
    assert "rankingrun" not in insp.get_table_names()
    project_cols = {c["name"] for c in insp.get_columns("project")}
    assert "prioritized_screening" not in project_cols
    article_cols = {c["name"] for c in insp.get_columns("article")}
    assert "relevance_score" not in article_cols
    engine.dispose()

    alembic("upgrade", "d7e3a9c1f5b2")
    engine = create_engine(url)
    insp = inspect(engine)
    assert "rankingrun" in insp.get_table_names()
    assert "ix_article_project_relevance" in {
        i["name"] for i in insp.get_indexes("article")
    }
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT prioritized_screening, stop_after_consecutive_excludes, "
                "ranking_min_random FROM project"
            )
        ).one()
        assert tuple(row) == (0, 100, 0)
        row = conn.execute(
            text("SELECT not_screened_stopping_rule, relevance_score FROM article")
        ).one()
        assert tuple(row) == (0, None)
    engine.dispose()


# --- statistical stopping rule settings -----------------------------------


def test_statistical_defaults_exposed(auth_as, a_project):
    client, owner = auth_as()
    body = client.get(f"{API}/{a_project(owner).id}").json()
    assert body["stopping_rule_type"] == "consecutive"
    assert body["recall_target"] == 0.95
    assert body["stopping_alpha"] == 0.05


def test_patch_rule_type_and_targets(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    r = client.patch(
        f"{API}/{project.id}",
        json={
            "stopping_rule_type": "statistical",
            "recall_target": 0.9,
            "stopping_alpha": 0.01,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stopping_rule_type"] == "statistical"
    assert body["recall_target"] == 0.9 and body["stopping_alpha"] == 0.01
    assert body["stop_after_consecutive_excludes"] == 100  # kept
    session.refresh(project)
    assert project.stopping_rule_type == "statistical"


@pytest.mark.parametrize("role", [ProjectRole.reviewer, ProjectRole.viewer])
def test_patch_rule_type_owner_only(auth_as, a_project, a_member, session, role):
    client, owner = auth_as()
    project = a_project(owner)
    auth_as(a_member(project, role))
    r = client.patch(f"{API}/{project.id}", json={"stopping_rule_type": "statistical"})
    assert r.status_code == 403
    session.refresh(project)
    assert project.stopping_rule_type == "consecutive"


@pytest.mark.parametrize(
    "payload",
    [
        {"recall_target": 0.79},
        {"recall_target": 1.0},
        {"recall_target": 0.995},
        {"recall_target": "NaN"},
        {"stopping_alpha": 0},
        {"stopping_alpha": 0.21},
        {"stopping_alpha": "NaN"},
        {"stopping_rule_type": "random"},
        {"stopping_rule_type": ""},
    ],
)
def test_statistical_validation(auth_as, a_project, payload):
    client, owner = auth_as()
    r = client.patch(f"{API}/{a_project(owner).id}", json=payload)
    assert r.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"recall_target": 0.8},
        {"recall_target": 0.99},
        {"stopping_alpha": 0.001},
        {"stopping_alpha": 0.2},
    ],
)
def test_statistical_bounds_accepted(auth_as, a_project, payload):
    client, owner = auth_as()
    r = client.patch(f"{API}/{a_project(owner).id}", json=payload)
    assert r.status_code == 200
    assert {k: r.json()[k] for k in payload} == payload


def test_targets_rounded_to_four_decimals(auth_as, a_project):
    client, owner = auth_as()
    r = client.patch(
        f"{API}/{a_project(owner).id}",
        json={"recall_target": 0.912345678, "stopping_alpha": 0.0123456},
    )
    assert r.json()["recall_target"] == 0.9123
    assert r.json()["stopping_alpha"] == 0.0123


def test_screening_rule_updated_audit_includes_new_fields(auth_as, a_project, session):
    client, owner = auth_as()
    project = a_project(owner)
    client.patch(
        f"{API}/{project.id}",
        json={
            "stopping_rule_type": "statistical",
            "recall_target": 0.9,
            "stopping_alpha": 0.05,  # unchanged: not in the diff
        },
    )
    (event,) = _events(session, project, "project.screening_rule_updated")
    assert event.details == {
        "changes": {
            "stopping_rule_type": {"from": "consecutive", "to": "statistical"},
            "recall_target": {"from": 0.95, "to": 0.9},
        }
    }
    assert _events(session, project, "project.settings_updated") == []


def test_rule_type_and_targets_not_clearable(auth_as, a_project):
    client, owner = auth_as()
    url = f"{API}/{a_project(owner).id}"
    client.patch(url, json={"stopping_rule_type": "statistical", "recall_target": 0.9})
    r = client.patch(
        url,
        json={
            "stopping_rule_type": None,
            "recall_target": None,
            "stopping_alpha": None,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stopping_rule_type"] == "statistical"
    assert body["recall_target"] == 0.9
    assert body["stopping_alpha"] == 0.05
