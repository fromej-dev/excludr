from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlmodel import SQLModel, Field, Relationship


class ProjectBase(SQLModel):
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)


class ProjectCreate(ProjectBase):
    pass


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
