def test_get_projects(auth_as, a_project):
    client, user = auth_as()
    project = a_project(user)
    res = client.get("api/v1/projects")
    assert res.status_code == 200
    assert len(res.json()["data"]) == 1
    assert res.json()["meta"]["pagination"]["total_items"] == 1

    [a_project(user) for _ in range(10)]
    res = client.get("api/v1/projects")
    assert res.status_code == 200
    assert len(res.json()["data"]) == 10
    assert res.json()["meta"]["pagination"]["total_items"] == 11

    # add projects of different users
    [a_project() for _ in range(10)]
    res = client.get("api/v1/projects")
    assert res.status_code == 200
    assert len(res.json()["data"]) == 10
    assert res.json()["meta"]["pagination"]["total_items"] == 11

    # test filtering
    res = client.get(
        f"api/v1/projects?field=name&operator=contains&value={project.name[2:5]}"
    )
    assert res.status_code == 200
    assert res.json()
    assert len(res.json()["data"]) == 1
    assert res.json()["data"][0]["name"] == project.name
    assert res.json()["meta"]["pagination"]["total_items"] == 1
