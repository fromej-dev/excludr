def test_alive(client):
    res = client.get("/ping")
    assert res.status_code == 200
    assert res.json() == "pong"
