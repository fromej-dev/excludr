"""
E2E integration test fixtures.

These fixtures provide high-level helpers for testing complete user flows
through the API, building on top of the base test infrastructure.
"""

import uuid
from typing import Callable

import pytest
from faker import Faker
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.core.config import get_settings
from app.core.database import get_session
from app.features.auth.services import create_access_token
from app.features.criteria.models import Criterion, CriterionType
from app.features.projects.models import Project
from app.features.research.models import Article, ArticleStatus
from app.features.screening.models import ScreeningStage
from app.features.users.models import User
from app.features.users.services import UserService
from app.main import app

settings = get_settings()
API = settings.api_prefix


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
    SQLModel.metadata.create_all(engine)
    connection = engine.connect()
    try:
        yield connection
    finally:
        connection.close()
        SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(db_connection):
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


# ---------------------------------------------------------------------------
# Low-level factories
# ---------------------------------------------------------------------------


@pytest.fixture(name="a_user")
def a_user_fixture(session: Session, faker, hashed_password) -> Callable[[], User]:
    """Factory that creates and persists a new user."""

    def _a_user():
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
def token_for_fixture() -> Callable[[User], str]:
    def _token_for(user: User) -> str:
        return create_access_token(data={"sub": user.email})

    return _token_for


@pytest.fixture(name="a_project")
def a_project_fixture(
    session: Session, faker, a_user
) -> Callable[[User | None], Project]:
    def _a_project(user: User | None = None):
        if user is None:
            user = a_user()
        project = Project(
            name=faker.catch_phrase()[:50],
            description=faker.text(),
            review_question="What is the effect of X on Y?",
            owner_id=user.id,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        return project

    return _a_project


# ---------------------------------------------------------------------------
# High-level E2E helpers
# ---------------------------------------------------------------------------


@pytest.fixture(name="auth_as")
def auth_as_fixture(client, a_user, token_for):
    """Returns (client, user) with Authorization header set."""

    def _auth_as(user: User | None = None):
        if user is None:
            user = a_user()
        token = token_for(user)
        client.headers["Authorization"] = f"Bearer {token}"
        return client, user

    return _auth_as


@pytest.fixture(name="auth_client")
def auth_client_fixture(client, a_user, token_for):
    user = a_user()
    token = token_for(user)
    client.headers["Authorization"] = f"Bearer {token}"
    try:
        yield client
    finally:
        client.headers.pop("Authorization", None)


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


@pytest.fixture(name="an_article")
def an_article_fixture(session: Session, faker) -> Callable:
    """Factory that creates an article directly in the database."""

    def _an_article(
        project_id: int,
        status: ArticleStatus = ArticleStatus.imported,
        stage: ScreeningStage = ScreeningStage.title_abstract,
        title: str | None = None,
        abstract: str | None = None,
    ) -> Article:
        article = Article(
            project_id=project_id,
            title=title or faker.sentence(),
            abstract=abstract or faker.paragraph(nb_sentences=5),
            authors=[faker.name(), faker.name()],
            journal=faker.company(),
            year=faker.random_int(min=2000, max=2025),
            doi=f"10.1234/{uuid.uuid4().hex[:12]}",
            status=status,
            current_stage=stage,
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        return article

    return _an_article


@pytest.fixture(name="a_criterion")
def a_criterion_fixture(session: Session) -> Callable:
    """Factory that creates a criterion directly in the database."""

    def _a_criterion(
        project_id: int,
        criterion_type: CriterionType = CriterionType.inclusion,
        code: str | None = None,
        description: str = "Test criterion",
        is_active: bool = True,
        order: int = 0,
    ) -> Criterion:
        if code is None:
            prefix = "I" if criterion_type == CriterionType.inclusion else "E"
            code = f"{prefix}{uuid.uuid4().hex[:3]}"
        criterion = Criterion(
            project_id=project_id,
            type=criterion_type,
            code=code,
            description=description,
            rationale="Test rationale",
            order=order,
            is_active=is_active,
        )
        session.add(criterion)
        session.commit()
        session.refresh(criterion)
        return criterion

    return _a_criterion


@pytest.fixture(name="project_with_articles")
def project_with_articles_fixture(a_project, an_article, a_user):
    """Creates a project with a set of articles in imported status."""

    def _project_with_articles(
        user: User | None = None, article_count: int = 5
    ) -> tuple[Project, User, list[Article]]:
        if user is None:
            user = a_user()
        project = a_project(user)
        articles = [an_article(project.id) for _ in range(article_count)]
        return project, user, articles

    return _project_with_articles


@pytest.fixture(name="project_with_criteria")
def project_with_criteria_fixture(a_project, a_criterion, a_user):
    """Creates a project with inclusion and exclusion criteria."""

    def _project_with_criteria(
        user: User | None = None,
    ) -> tuple[Project, User, list[Criterion]]:
        if user is None:
            user = a_user()
        project = a_project(user)
        criteria = [
            a_criterion(project.id, CriterionType.inclusion, "I1", "Population includes adults"),
            a_criterion(project.id, CriterionType.inclusion, "I2", "Study is an RCT", order=1),
            a_criterion(project.id, CriterionType.exclusion, "E1", "Non-English language"),
            a_criterion(project.id, CriterionType.exclusion, "E2", "Animal studies only", order=1),
        ]
        return project, user, criteria

    return _project_with_criteria


@pytest.fixture(name="screening_ready_project")
def screening_ready_project_fixture(
    a_project, an_article, a_criterion, a_user, token_for, client
):
    """Creates a project with articles in screening status and active criteria."""

    def _screening_ready(
        user: User | None = None,
        article_count: int = 3,
    ) -> tuple[Project, User, list[Article], list[Criterion]]:
        if user is None:
            user = a_user()
        project = a_project(user)

        # Create articles in screening status
        articles = [
            an_article(
                project.id,
                status=ArticleStatus.screening,
                stage=ScreeningStage.title_abstract,
            )
            for _ in range(article_count)
        ]

        # Create criteria
        criteria = [
            a_criterion(project.id, CriterionType.inclusion, "I1", "Population includes adults"),
            a_criterion(project.id, CriterionType.exclusion, "E1", "Non-English language"),
        ]

        return project, user, articles, criteria

    return _screening_ready
