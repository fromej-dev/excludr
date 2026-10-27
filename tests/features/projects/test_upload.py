import os
import uuid

BASE_API = "api/v1/projects"


def test_upload_file(auth_as, a_project, session, monkeypatch):
    # Mock the Prefect session to use the test session (preserves test isolation)
    class MockContextManager:
        def __init__(self, test_session):
            self.test_session = test_session

        def __enter__(self):
            return self.test_session

        def __exit__(self, exc_type, exc_val, exc_tb):
            # Don't commit or rollback - let the test fixture handle it
            return False

    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session",
        lambda: MockContextManager(session),
    )

    client, user = auth_as()
    project = a_project(user)
    file_bytes = None
    with open("./tests/docs/test.ris", "rb") as f:
        file_bytes = f.read()
    res = client.post(
        f"{BASE_API}/{project.id}/upload/ris", files={"file": ("test.ris", file_bytes)}
    )
    # Flow runs synchronously so we get 200 (successful) instead of 202 (accepted)
    assert res.status_code == 200
    result = res.json()
    assert result["message"] == "File processing complete."
    assert result["result"]["status"] == "Success"


def test_upload_file_unauthorized(client, a_project, a_user):
    """Test that unauthenticated users cannot upload files."""
    user = a_user()
    project = a_project(user)
    with open("./tests/docs/test.ris", "rb") as f:
        file_bytes = f.read()
    res = client.post(
        f"{BASE_API}/{project.id}/upload/ris", files={"file": ("test.ris", file_bytes)}
    )
    assert res.status_code == 401


def test_upload_file_wrong_owner(auth_as, a_project, a_user):
    """Test that users cannot upload to projects they don't own."""
    client, user = auth_as()
    other_user = a_user()
    project = a_project(other_user)  # Project owned by different user
    with open("./tests/docs/test.ris", "rb") as f:
        file_bytes = f.read()
    res = client.post(
        f"{BASE_API}/{project.id}/upload/ris", files={"file": ("test.ris", file_bytes)}
    )
    assert res.status_code == 403


def test_upload_invalid_file_type(auth_as, a_project):
    """Test that only .ris files can be uploaded."""
    client, user = auth_as()
    project = a_project(user)
    res = client.post(
        f"{BASE_API}/{project.id}/upload/ris",
        files={"file": ("test.txt", b"invalid content")},
    )
    assert res.status_code == 400
    assert "Invalid file type" in res.json()["detail"]


# --- Hardening: size limits, filenames, cleanup --------------------------------------


def _use_test_session(session, monkeypatch):
    class Ctx:
        def __enter__(self):
            return session

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "app.features.projects.flows.get_prefect_session", lambda: Ctx()
    )


def _ris_bytes():
    with open("./tests/docs/test.ris", "rb") as f:
        return f.read()


def test_upload_too_large_returns_413(auth_as, a_project, monkeypatch, tmp_path):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "upload_directory", str(tmp_path))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    client, user = auth_as()
    project = a_project(user)

    big = b"TY  - JOUR\n" + b"x" * (1024 * 1024 + 1)
    res = client.post(
        f"{BASE_API}/{project.id}/upload/ris", files={"file": ("big.ris", big)}
    )
    assert res.status_code == 413
    assert list(tmp_path.iterdir()) == []  # partial file removed


def test_pubmed_upload_too_large_returns_413(auth_as, a_project, monkeypatch, tmp_path):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "upload_directory", str(tmp_path))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    client, user = auth_as()
    project = a_project(user)

    res = client.post(
        f"{BASE_API}/{project.id}/upload/pubmed",
        files={"file": ("big.txt", b"x" * (1024 * 1024 + 1))},
    )
    assert res.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_upload_stored_path_ignores_client_filename(
    auth_as, a_project, session, monkeypatch, tmp_path
):
    """The client filename never reaches the filesystem path; temp file is cleaned up."""
    from app.core.config import get_settings

    _use_test_session(session, monkeypatch)
    monkeypatch.setattr(get_settings(), "upload_directory", str(tmp_path))
    seen: list[str] = []

    from app.features.projects import flows

    real_parse = flows.parse_ris_entries

    def spy(file_path, project_id, original_filename):
        seen.append(file_path)
        return real_parse(file_path, project_id, original_filename)

    monkeypatch.setattr(flows, "parse_ris_entries", spy)

    client, user = auth_as()
    project = a_project(user)
    evil = "../../etc/pass wd;$(rm -rf).ris"
    res = client.post(
        f"{BASE_API}/{project.id}/upload/ris", files={"file": (evil, _ris_bytes())}
    )
    assert res.status_code == 200
    assert len(seen) == 1
    stored = seen[0]
    assert os.path.dirname(stored) == str(tmp_path)
    assert os.path.basename(stored).endswith(".ris")
    assert "pass" not in stored and ".." not in stored
    uuid.UUID(os.path.splitext(os.path.basename(stored))[0])
    # temp file removed after parsing
    assert list(tmp_path.iterdir()) == []


def test_upload_temp_file_removed_after_parse_pubmed(
    auth_as, a_project, session, monkeypatch, tmp_path
):
    from app.core.config import get_settings

    _use_test_session(session, monkeypatch)
    monkeypatch.setattr(get_settings(), "upload_directory", str(tmp_path))
    client, user = auth_as()
    project = a_project(user)
    content = b"PMID- 12345678\nTI  - A title\nAB  - An abstract\nDP  - 2020\n\n"
    res = client.post(
        f"{BASE_API}/{project.id}/upload/pubmed",
        files={"file": ("../weird.txt", content)},
    )
    assert res.status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_upload_temp_file_removed_when_flow_fails(
    auth_as, a_project, monkeypatch, tmp_path
):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_directory", str(tmp_path))

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("app.features.projects.routers.parse_ris_file_flow", boom)
    client, user = auth_as()
    project = a_project(user)
    res = client.post(
        f"{BASE_API}/{project.id}/upload/ris", files={"file": ("a.ris", _ris_bytes())}
    )
    assert res.status_code == 500
    assert "secret internal detail" not in res.text
    assert list(tmp_path.iterdir()) == []
