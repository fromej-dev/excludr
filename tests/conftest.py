from typing import Callable

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.core.database import get_session
from app.features.users.models import User
from app.features.users.services import UserService
from app.main import app


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="a_user")
def a_user_fixture(session: Session, faker) -> Callable[[], User]:
    """A fixture that provides a new user"""

    def _a_user():
        user = User(
            name=faker.name(),
            email=faker.email(),
            hashed_password=UserService.hash_password("test_password"),
        )
        session.add(user)
        session.commit()
        return user

    return _a_user


@pytest.fixture(name="auth_client")
def auth_client_fixture(client, a_user):
    user = a_user()
    response = client.post(
        "api/v1/auth/token",
        data={"username": user.email, "password": "test_password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    client.headers.pop("Authorization")


@pytest.fixture(name="admin_client")
def admin_client_fixture(client, a_user):
    user = a_user()
    user.is_superuser = True

    response = client.post(
        "api/v1/auth/token",
        data={"username": user.email, "password": "test_password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    client.headers.pop("Authorization")
