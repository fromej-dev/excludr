BASE_API = "api/v1/projects"


# get list of projects
def test_get_projects(auth_as, a_project):
    client, user = auth_as()
    project = a_project(user)
    res = client.get(BASE_API)
    assert res.status_code == 200
    assert len(res.json()["data"]) == 1
    assert res.json()["meta"]["pagination"]["total_items"] == 1

    [a_project(user) for _ in range(10)]
    res = client.get(BASE_API)
    assert res.status_code == 200
    assert len(res.json()["data"]) == 10
    assert res.json()["meta"]["pagination"]["total_items"] == 11

    # add projects of different users
    [a_project() for _ in range(10)]
    res = client.get(BASE_API)
    assert res.status_code == 200
    assert len(res.json()["data"]) == 10
    assert res.json()["meta"]["pagination"]["total_items"] == 11

    # test filtering
    res = client.get(
        f"{BASE_API}?field=name&operator=contains&value={project.name[2:5]}"
    )
    assert res.status_code == 200
    assert res.json()
    assert len(res.json()["data"]) == 1
    assert res.json()["data"][0]["name"] == project.name
    assert res.json()["meta"]["pagination"]["total_items"] == 1


# Tests for retrieving a project by id
def test_get_project_by_id_owner(auth_as, a_project):
    client, user = auth_as()
    project = a_project(user)
    res = client.get(f"{BASE_API}/{project.id}")
    assert res.status_code == 200
    assert res.json()["id"] == project.id


def test_get_project_by_id_not_owner(auth_as, a_project):
    client, user = auth_as()
    project = a_project()
    res = client.get(f"{BASE_API}/{project.id}")
    assert res.status_code == 403
    assert res.json()["detail"] == "You are not the owner of the project"


def test_get_project_by_id_not_existing(auth_client):
    res = auth_client.get(f"{BASE_API}/1")
    assert res.status_code == 404
    assert res.json()["detail"] == "Project not found"


# tests for creating a project
def test_create_project(auth_as, a_user, faker):
    client, user = auth_as()
    data = {"name": faker.name(), "description": faker.text()}
    res = client.post(BASE_API, json=data)
    assert res.status_code == 201
    assert res.json()["name"] == data["name"]
    assert res.json()["description"] == data["description"]
    assert res.json()["owner_id"] == user.id

    # test creating a project with only name
    data = {"name": faker.name()}
    res = client.post(BASE_API, json=data)
    assert res.status_code == 201
    assert res.json()["name"] == data["name"]
    assert res.json()["description"] is None

    # test creating a project with invalid data
    data = {"name": ""}
    res = client.post(BASE_API, json=data)
    assert res.status_code == 422
    assert res.json()["detail"][0]["msg"] == "String should have at least 3 characters"
    assert res.json()["detail"][0]["type"] == "string_too_short"


# Tests for updating a project
def test_update_project(auth_as, a_project, faker):
    client, user = auth_as()
    project = a_project(user)
    data = {"name": faker.word(), "description": faker.text()}
    res = client.patch(f"{BASE_API}/{project.id}", json=data)
    assert res.status_code == 200
    assert res.json()["name"] == data["name"]
    assert res.json()["description"] == data["description"]

    # update only name
    data1 = {"name": faker.word()}
    res = client.patch(f"{BASE_API}/{project.id}", json=data1)
    assert res.status_code == 200
    assert res.json()["name"] == data1["name"]
    assert res.json()["description"] == data["description"]

    # update only description
    data2 = {"description": faker.text()}
    res = client.patch(f"{BASE_API}/{project.id}", json=data2)
    assert res.status_code == 200
    assert res.json()["name"] == data1["name"]
    assert res.json()["description"] == data2["description"]


def test_update_project_not_owner(auth_as, a_project, faker):
    client, user = auth_as()
    project = a_project()
    data = {"name": faker.word(), "description": faker.text()}
    res = client.patch(f"{BASE_API}/{project.id}", json=data)
    assert res.status_code == 403
    assert res.json()["detail"] == "You are not the owner of the project"


def test_update_project_not_existing(auth_client):
    res = auth_client.patch(f"{BASE_API}/1", json={"name": "test"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Project not found"
