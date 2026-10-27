from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(SQLModel, table=True):
    """Append-only record of something that happened in a project.

    Rows are only ever inserted; there is no update or delete code path (they are
    removed only by the database cascade when the whole project is deleted).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True, ondelete="CASCADE")
    user_id: Optional[int] = Field(
        default=None, foreign_key="user.id", index=True, ondelete="SET NULL"
    )
    action: str = Field(index=True, max_length=100)
    entity_type: str = Field(index=True, max_length=50)
    entity_id: Optional[int] = Field(default=None)
    details: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        nullable=False,
        index=True,
    )
