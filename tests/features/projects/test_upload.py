BASE_API = "api/v1/projects"


def test_upload_file(auth_as, a_project, engine, monkeypatch):
    monkeypatch.setattr("app.core.celery.engine", engine)

    client, user = auth_as()
    project = a_project(user)
    file_bytes = None
    with open("./tests/docs/test.ris", "rb") as f:
        file_bytes = f.read()
    res = client.post(
        f"{BASE_API}/{project.id}/upload/ris", files={"file": ("test.ris", file_bytes)}
    )
    assert res.status_code == 200
    assert res.json()["task_id"]
