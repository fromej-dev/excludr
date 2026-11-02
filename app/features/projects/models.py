from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from pydantic import computed_field, field_validator
from sqlalchemy import DateTime, String, UniqueConstraint, event, func, insert
from sqlalchemy import false as sa_false
from sqlmodel import SQLModel, Field, Relationship


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class ProjectRole(str, Enum):
    """Role of a user within a project (ordered: viewer < reviewer < owner)."""

    owner = "owner"
    reviewer = "reviewer"
    viewer = "viewer"


class StoppingRuleType(str, Enum):
    """How the stopping rule of prioritized screening decides to stop."""

    consecutive = "consecutive"  # N consecutive title/abstract excludes
    statistical = "statistical"  # recall target shown by a hypergeometric test


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
    prioritized_screening: Optional[bool] = Field(
        default=None,
        description="Serve the title/abstract queue by predicted relevance",
    )
    stop_after_consecutive_excludes: Optional[int] = Field(
        default=None,
        ge=1,
        le=100000,
        description="Stopping rule: consecutive title/abstract excludes after which "
        "the owner may close the rest (null clears it)",
    )
    ranking_min_random: Optional[int] = Field(
        default=None,
        ge=0,
        le=10000,
        description="Title/abstract decisions served in random order before ranking",
    )
    stopping_rule_type: Optional[StoppingRuleType] = Field(
        default=None,
        description="Stopping rule: consecutive excludes or statistical recall test",
    )
    recall_target: Optional[float] = Field(
        default=None,
        ge=0.80,
        le=0.99,
        description="Statistical stopping rule: recall to demonstrate (0.80-0.99)",
    )
    stopping_alpha: Optional[float] = Field(
        default=None,
        ge=0.001,
        le=0.20,
        description="Statistical stopping rule: significance level (0.001-0.20)",
    )

    @field_validator("recall_target", "stopping_alpha")
    @classmethod
    def _round_4dp(cls, value: Optional[float]) -> Optional[float]:
        """Four decimals keep the exact fraction in the recall test small."""
        return None if value is None else round(value, 4)


# Settings of prioritized screening; changes to them get their own audit event.
SCREENING_RULE_FIELDS = (
    "prioritized_screening",
    "stop_after_consecutive_excludes",
    "ranking_min_random",
    "stopping_rule_type",
    "recall_target",
    "stopping_alpha",
)
# Fields a client may clear by sending an explicit null.
CLEARABLE_FIELDS = frozenset({"stop_after_consecutive_excludes"})


def update_values(data: ProjectUpdate) -> dict:
    """Fields a ``ProjectUpdate`` sets: unset and null ones are dropped, except
    the clearable fields, which accept an explicit null."""
    return {
        k: v
        for k, v in data.model_dump(exclude_unset=True).items()
        if v is not None or k in CLEARABLE_FIELDS
    }


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
    prioritized_screening: bool = Field(
        default=False,
        description="Serve the title/abstract queue by predicted relevance",
        sa_column_kwargs={"server_default": sa_false(), "nullable": False},
    )
    stop_after_consecutive_excludes: Optional[int] = Field(
        default=100,
        ge=1,
        le=100000,
        description="Stopping rule: consecutive title/abstract excludes after which "
        "the owner may close the rest (null = no stopping rule)",
        sa_column_kwargs={"server_default": "100", "nullable": True},
    )
    ranking_min_random: int = Field(
        default=0,
        ge=0,
        le=10000,
        description="Title/abstract decisions served in random order before ranking",
        sa_column_kwargs={"server_default": "0", "nullable": False},
    )
    stopping_rule_type: StoppingRuleType = Field(
        default=StoppingRuleType.consecutive,
        sa_type=String(20),
        description="Stopping rule: consecutive excludes or statistical recall test",
        sa_column_kwargs={"server_default": "consecutive", "nullable": False},
    )
    recall_target: float = Field(
        default=0.95,
        ge=0.80,
        le=0.99,
        description="Statistical stopping rule: recall to demonstrate",
        sa_column_kwargs={"server_default": "0.95", "nullable": False},
    )
    stopping_alpha: float = Field(
        default=0.05,
        ge=0.001,
        le=0.20,
        description="Statistical stopping rule: significance level",
        sa_column_kwargs={"server_default": "0.05", "nullable": False},
    )
    prioritized_screening_enabled_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="When prioritized screening was last switched on (set by the server)",
    )
    stopping_rule_applied_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        description="When the stopping rule last closed the remaining records",
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
    title_abstract_screened: bool = Field(
        default=False,
        description="Records already passed title/abstract screening elsewhere",
        sa_column_kwargs={"server_default": sa_false(), "nullable": False},
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
