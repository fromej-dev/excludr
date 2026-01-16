from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import func
from sqlmodel import SQLModel, Field, Relationship


class CriterionType(str, Enum):
    """Type of screening criterion."""

    inclusion = "inclusion"
    exclusion = "exclusion"


class CriterionBase(SQLModel):
    """Base schema for Criterion with shared fields."""

    type: CriterionType = Field(index=True)
    code: str = Field(min_length=1, max_length=10, description="Short code like I1, E1")
    description: str = Field(min_length=1, max_length=500)
    rationale: Optional[str] = Field(default=None, max_length=1000)
    order: int = Field(default=0, description="Display order within type")
    is_active: bool = Field(default=True, index=True)


class CriterionCreate(SQLModel):
    """Schema for creating a new criterion."""

    type: CriterionType
    code: str = Field(min_length=1, max_length=10)
    description: str = Field(min_length=1, max_length=500)
    rationale: Optional[str] = Field(default=None, max_length=1000)
    order: Optional[int] = Field(default=0)
    is_active: Optional[bool] = Field(default=True)


class CriterionUpdate(SQLModel):
    """Schema for updating a criterion."""

    type: Optional[CriterionType] = Field(default=None)
    code: Optional[str] = Field(default=None, min_length=1, max_length=10)
    description: Optional[str] = Field(default=None, min_length=1, max_length=500)
    rationale: Optional[str] = Field(default=None, max_length=1000)
    order: Optional[int] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)


class Criterion(CriterionBase, table=True):
    """Database model for inclusion/exclusion criteria."""

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    created_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
    )

    project: "Project" = Relationship(back_populates="criteria")  # noqa: F821


class CriterionReorder(SQLModel):
    """Schema for reordering criteria."""

    criterion_ids: list[int] = Field(description="Ordered list of criterion IDs")
