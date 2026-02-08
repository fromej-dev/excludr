from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import func, Column, JSON
from sqlmodel import SQLModel, Field, Relationship


class ScreeningStage(str, Enum):
    """Stage of screening."""

    title_abstract = "title_abstract"
    full_text = "full_text"
    completed = "completed"


class ScreeningDecisionType(str, Enum):
    """Type of screening decision."""

    include = "include"
    exclude = "exclude"
    uncertain = "uncertain"


class DecisionSource(str, Enum):
    """Source of the decision (AI or human)."""

    ai_agent = "ai_agent"
    human = "human"


class ScreeningDecisionBase(SQLModel):
    """Base schema for ScreeningDecision."""

    stage: ScreeningStage = Field(index=True)
    decision: ScreeningDecisionType = Field(index=True)
    source: DecisionSource = Field(index=True)
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default=None, max_length=2000)
    primary_exclusion_reason: Optional[str] = Field(default=None, max_length=500)


class ScreeningDecisionCreate(SQLModel):
    """Schema for creating a screening decision."""

    stage: ScreeningStage
    decision: ScreeningDecisionType
    source: DecisionSource = Field(default=DecisionSource.human)
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(default=None, max_length=2000)
    primary_exclusion_reason: Optional[str] = Field(default=None, max_length=500)
    criteria_evaluations: Optional[dict] = Field(default=None)


class ScreeningDecision(ScreeningDecisionBase, table=True):
    """Database model for screening decisions (AI and human)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="article.id", index=True)
    reviewer_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)

    # JSON field for per-criterion evaluations
    # Structure: {"I1": {"met": true, "reasoning": "..."}, "E1": {"met": false, "reasoning": "..."}}
    criteria_evaluations: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    created_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )

    article: "Article" = Relationship(back_populates="screening_decisions")  # noqa: F821
    reviewer: Optional["User"] = Relationship()  # noqa: F821


class ScreeningStats(SQLModel):
    """Response schema for screening statistics."""

    total_articles: int = 0
    screened_title_abstract: int = 0
    screened_full_text: int = 0
    included: int = 0
    excluded: int = 0
    uncertain: int = 0
    awaiting_screening: int = 0
    awaiting_full_text: int = 0
