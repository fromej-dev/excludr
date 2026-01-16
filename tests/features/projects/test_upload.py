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
