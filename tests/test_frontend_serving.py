from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


def _client(tmp_path) -> TestClient:
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "favicon.ico").write_bytes(b"ico")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")

    app = FastAPI()

    @app.get("/api/v1/thing")
    def thing():
        return {"ok": True}

    mount_frontend(app, str(tmp_path))
    return TestClient(app)


def test_serves_index_at_root(tmp_path):
    res = _client(tmp_path).get("/")
    assert res.status_code == 200
    assert "spa" in res.text


def test_client_side_routes_fall_back_to_index(tmp_path):
    res = _client(tmp_path).get("/projects/3/screening")
    assert res.status_code == 200
    assert "spa" in res.text


def test_serves_static_files(tmp_path):
    client = _client(tmp_path)
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.ico").content == b"ico"


def test_api_routes_still_win_and_unknown_api_paths_404(tmp_path):
    client = _client(tmp_path)
    assert client.get("/api/v1/thing").json() == {"ok": True}
    res = client.get("/api/v1/nope")
    assert res.status_code == 404
    assert "spa" not in res.text


def test_paths_outside_dist_are_not_served(tmp_path):
    (tmp_path.parent / "secret.txt").write_text("secret")
    res = _client(tmp_path).get("/..%2Fsecret.txt")
    assert "secret" not in res.text
