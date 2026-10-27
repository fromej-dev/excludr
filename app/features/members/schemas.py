from datetime import datetime

from sqlmodel import SQLModel

from app.features.projects.models import ProjectRole


class MemberAdd(SQLModel):
    """Add an existing user to a project by email."""

    email: str
    role: ProjectRole = ProjectRole.reviewer


class MemberRoleUpdate(SQLModel):
    role: ProjectRole


class MemberRead(SQLModel):
    user_id: int
    email: str
    name: str
    role: ProjectRole
    created_at: datetime
