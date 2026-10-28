from typing import Callable

import pytest
from faker import Faker
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.core.database import get_session
from app.features.auth.services import create_access_token
from app.features.projects.models import Project
from app.features.users.models import User
from app.features.users.services import UserService
from app.main import app


@pytest.fixture(autouse=True)
def reset_login_rate_limiter():
    """Keep the in-memory login rate limiter from leaking between tests."""
    from app.core.rate_limit import login_rate_limiter

    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()


@pytest.fixture(autouse=True)
def no_external_lookups(monkeypatch):
    """Keep imports and screening decisions off the network.

    Automatic full-text retrieval is off and PubMed lookups get a 503 (the
    service treats that as "no abstracts"). Tests that cover these turn them
    back on with their own fakes.
    """
    import httpx

    from app.core.config import get_settings
    from app.features.research.pubmed_service import PubMedService

    monkeypatch.setattr(get_settings(), "fulltext_auto_retrieval", False)
    offline = httpx.MockTransport(lambda request: httpx.Response(503))
    monkeypatch.setattr(
        PubMedService, "_client", lambda self: httpx.Client(transport=offline)
    )


@pytest.fixture(name="faker", scope="session")
def faker_fixture():
    return Faker()


@pytest.fixture(name="engine", scope="session")
def engine_fixture():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


@pytest.fixture(name="db_connection", scope="session")
def db_connection_fixture(engine):
    # Create schema once for the whole session; drop once at the end.
    SQLModel.metadata.create_all(engine)
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()
        SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(db_connection):
    # Start a transaction per test; roll back to keep tests isolated and fast.
    trans = db_connection.begin()
    try:
        with Session(db_connection) as session:
            yield session
            session.rollback()
    finally:
        trans.rollback()


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override

    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(name="hashed_password", scope="session")
def hashed_password_fixture():
    return UserService.hash_password("test_password")


@pytest.fixture(name="a_user")
def a_user_fixture(session: Session, faker, hashed_password) -> Callable[[], User]:
    """Factory that creates and persists a new user."""
    import uuid

    def _a_user():
        # Use uuid to ensure unique emails across test runs
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            name=faker.name(),
            email=f"{unique_id}_{faker.email()}",
            hashed_password=hashed_password,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    return _a_user


@pytest.fixture(name="token_for")
def token_for_fixture(client) -> Callable[[User], str]:
    """Issue an access token for a given user."""

    def _token_for(user: User) -> str:
        return create_access_token(data={"sub": user.email})

    return _token_for


@pytest.fixture(name="auth_client")
def auth_client_fixture(client, a_user, token_for):
    user = a_user()
    token = token_for(user)
    client.headers["Authorization"] = f"Bearer {token}"
    try:
        yield client
    finally:
        client.headers.pop("Authorization", None)


@pytest.fixture(name="auth_as")
def auth_as_fixture(client, a_user, token_for):
    def _auth_as(user: User | None = None):
        if user is None:
            user = a_user()
        token = token_for(user)
        client.headers["Authorization"] = f"Bearer {token}"
        return client, user

    return _auth_as


@pytest.fixture(name="admin_client")
def admin_client_fixture(client, a_user, token_for, session: Session):
    user = a_user()
    user.is_superuser = True
    session.add(user)
    session.commit()
    session.refresh(user)

    token = token_for(user)
    client.headers["Authorization"] = f"Bearer {token}"
    try:
        yield client
    finally:
        client.headers.pop("Authorization", None)


@pytest.fixture(name="a_project")
def a_project_fixture(
    session: Session, faker, a_user
) -> Callable[[User | None], Project]:
    """Factory that creates and persists a new project."""

    def _a_project(user: User | None = None):
        if user is None:
            user = a_user()
        project = Project(
            name=faker.name(),
            description=faker.text(),
            owner_id=user.id,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        return project

    return _a_project


@pytest.fixture(name="a_member")
def a_member_fixture(session: Session, a_user):
    """Factory: add a (new or given) user to a project with a role."""
    from app.features.projects.models import ProjectMember, ProjectRole

    def _a_member(project, role=ProjectRole.reviewer, user: User | None = None):
        user = user or a_user()
        session.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
        session.commit()
        return user

    return _a_member


@pytest.fixture(name="an_article_in")
def an_article_in_fixture(session: Session):
    """Factory: create an article in a project (screening/title_abstract by default)."""
    from app.features.research.models import Article, ArticleStatus
    from app.features.screening.models import ScreeningStage

    def _an_article(project, **kwargs):
        defaults = {
            "title": "An article",
            "abstract": "Abstract",
            "status": ArticleStatus.screening,
            "current_stage": ScreeningStage.title_abstract,
        }
        defaults.update(kwargs)
        article = Article(project_id=project.id, **defaults)
        session.add(article)
        session.commit()
        session.refresh(article)
        return article

    return _an_article
