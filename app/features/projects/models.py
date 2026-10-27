from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from pydantic import computed_field
from sqlalchemy import DateTime, UniqueConstraint, event, func, insert
from sqlmodel import SQLModel, Field, Relationship


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class ProjectRole(str, Enum):
    """Role of a user within a project (ordered: viewer < reviewer < owner)."""

    owner = "owner"
    reviewer = "reviewer"
    viewer = "viewer"


class ProjectBase(SQLModel):
    name: str = Field(index=True, min_length=3, max_length=50)
    description: Optional[str] = Field(default=None)
    review_question: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="The research question guiding the systematic review",
    )


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ProjectBase):
    name: Optional[str] = Field(
        min_length=3, max_length=50, default=None, nullable=True
    )
    description: Optional[str] = Field(default=None, nullable=True)
    required_reviewers: Optional[int] = Field(
        default=None,
        ge=1,
        le=2,
        description="Human reviewers required per article and stage (1 or 2)",
    )


class Project(ProjectBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )
    updated_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )
    owner_id: int = Field(foreign_key="user.id")
    required_reviewers: int = Field(
        default=1,
        ge=1,
        le=2,
        sa_column_kwargs={"server_default": "1", "nullable": False},
        description="Human reviewers required per article and stage (1 or 2)",
    )

    owner: "User" = Relationship(back_populates="projects")  # noqa: F821
    articles: List["Article"] = Relationship(  # noqa: F821
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    criteria: List["Criterion"] = Relationship(  # noqa: F821
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @computed_field
    @property
    def number_of_articles(self) -> int:
        """Calculates the number of articles in the project."""
        return len(self.articles)


class ProjectMember(SQLModel, table=True):
    """Membership of a user in a project, with a role.

    The project owner (``Project.owner_id``) always has an ``owner`` membership.
    """

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_projectmember_project_user"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True, ondelete="CASCADE")
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    role: ProjectRole = Field(index=True)
    created_at: datetime = Field(
        default_factory=_utcnow, sa_type=DateTime(timezone=True), nullable=False
    )


class ImportBatch(SQLModel, table=True):
    """One file import into a project (feeds the PRISMA "identification" counts)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True, ondelete="CASCADE")
    filename: str = Field(max_length=500)
    format: str = Field(max_length=20, description="ris | pubmed_txt | pubmed_csv")
    records_found: int = Field(default=0, description="Records present in the file")
    imported: int = Field(default=0, description="New articles created")
    duplicates: int = Field(
        default=0, description="Records matching an article already in the project"
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_type=DateTime(timezone=True), nullable=False
    )
    created_by: Optional[int] = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )


@event.listens_for(Project, "after_insert")
def _create_owner_membership(mapper, connection, project: Project) -> None:  # noqa: ANN001
    """Every new project gets an ``owner`` membership for its owner."""
    connection.execute(
        insert(ProjectMember.__table__).values(
            project_id=project.id,
            user_id=project.owner_id,
            role=ProjectRole.owner,
            created_at=_utcnow(),
        )
    )
