from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AIActivity(str, Enum):
    """What an AI run was for."""

    screening_single = "screening_single"  # screen-ai on one article
    screening_batch = "screening_batch"  # run-ai over the eligible articles
    screening_lookahead = "screening_lookahead"  # run-ai on picked articles


class AIUsage(SQLModel, table=True):
    """Tokens and estimated cost of one AI run (all its model requests, output
    retries included), successful or not.

    This is the AI cost record: rows stay when the project, article, decision or
    user goes (the link is cleared instead).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    activity: str = Field(max_length=40, index=True, description="AIActivity")
    stage: Optional[str] = Field(
        default=None, max_length=20, index=True, description="ScreeningStage"
    )
    model_name: str = Field(max_length=200, index=True)
    project_id: Optional[int] = Field(
        default=None, foreign_key="project.id", index=True, ondelete="SET NULL"
    )
    article_id: Optional[int] = Field(
        default=None, foreign_key="article.id", index=True, ondelete="SET NULL"
    )
    decision_id: Optional[int] = Field(
        default=None, foreign_key="screeningdecision.id", ondelete="SET NULL"
    )
    user_id: Optional[int] = Field(
        default=None,
        foreign_key="user.id",
        index=True,
        ondelete="SET NULL",
        description="Who started the run",
    )
    succeeded: bool = Field(default=True)
    requests: int = Field(default=0)
    input_tokens: int = Field(default=0, description="Cache reads/writes included")
    output_tokens: int = Field(default=0)
    cache_read_tokens: int = Field(default=0)
    cache_write_tokens: int = Field(default=0)
    cost_usd: Optional[float] = Field(
        default=None, description="Estimate; null when the model could not be priced"
    )
