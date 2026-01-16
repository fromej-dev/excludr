from datetime import datetime
from typing import Optional, List

from pydantic import computed_field
from sqlalchemy import func
from sqlmodel import SQLModel, Field, Relationship


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


class Project(ProjectBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )
    updated_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )
    owner_id: int = Field(foreign_key="user.id")

    owner: "User" = Relationship(back_populates="projects")  # noqa: F821
    articles: List["Article"] = Relationship(back_populates="project")  # noqa: F821
    criteria: List["Criterion"] = Relationship(back_populates="project")  # noqa: F821

    @computed_field
    @property
    def number_of_articles(self) -> int:
        """Calculates the number of articles in the project."""
        return len(self.articles)
