from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, func, false as sa_false, Column, JSON
from sqlmodel import SQLModel, Field, Relationship

from app.features.projects.models import StoppingRuleType


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

    # True for the owner's final decision resolving a reviewer conflict
    is_resolution: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": sa_false(), "nullable": False},
        description="Owner decision that resolves a conflict between reviewers",
    )

    # Provenance for AI decisions (null for human decisions)
    model_name: Optional[str] = Field(default=None, max_length=200)
    prompt_version: Optional[str] = Field(default=None, max_length=50)

    # {criterion code: criterion version} of the active criteria an AI decision
    # was made against (null for human decisions / decisions predating versioning)
    criteria_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    created_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )

    article: "Article" = Relationship(back_populates="screening_decisions")  # noqa: F821
    reviewer: Optional["User"] = Relationship()  # noqa: F821


class StoppingRuleSummary(SQLModel):
    """Stopping-rule progress in short form (inside ``ScreeningStats``)."""

    enabled: bool
    threshold: Optional[int] = None
    consecutive_excludes: int = 0
    met: bool = False
    applied_at: Optional[datetime] = None
    rule_type: StoppingRuleType = StoppingRuleType.consecutive
    recall_target: Optional[float] = None  # statistical rule only, as below
    alpha: Optional[float] = None
    p_value: Optional[float] = None
    relevant_found: Optional[int] = None
    test_reason: Optional[str] = None  # ok | no_relevant | no_sample | nothing_left


class ScreeningStats(SQLModel):
    """Response schema for screening statistics.

    Every count is a number of articles. Human decisions are the ones that count
    (AI decisions never advance an article); "decided" fields count articles with
    at least one human vote, "completed" fields count articles whose stage is
    settled. Invariants (for consistent data)::

        title_abstract_total = awaiting_screening + title_abstract_completed
        title_abstract_completed = excluded_title_abstract + not_screened_stopping_rule
                                   + full_text_eligible
        full_text_eligible = awaiting_full_text + awaiting_full_text_screening
                             + full_text_completed
        full_text_retrieved = full_text_eligible - awaiting_full_text
        full_text_completed = included + excluded_full_text
        excluded = excluded_title_abstract + excluded_full_text
    """

    # --- Legacy fields (kept for compatibility) -----------------------------
    total_articles: int = Field(default=0, description="All articles in the project")
    screened_title_abstract: int = Field(
        default=0,
        description="Articles with at least one title/abstract decision of any "
        "source (AI included). Prefer title_abstract_completed for progress.",
    )
    screened_full_text: int = Field(
        default=0,
        description="Articles with at least one full-text decision of any source "
        "(AI included). Prefer full_text_completed for progress.",
    )
    included: int = Field(default=0, description="Articles finally included")
    excluded: int = Field(
        default=0,
        description="Articles finally excluded by reviewers (at either stage). "
        "Records closed by the stopping rule are counted in "
        "not_screened_stopping_rule instead",
    )
    uncertain: int = Field(
        default=0,
        description="Open articles (at title/abstract or full text) where at least "
        "one reviewer's current human decision at that stage is 'uncertain'",
    )
    awaiting_screening: int = Field(
        default=0,
        description="Articles in title/abstract screening (status 'screening')",
    )
    awaiting_full_text: int = Field(
        default=0,
        description="Articles that passed title/abstract and still need a full "
        "text (status 'awaiting_full_text')",
    )

    # --- Exact per-stage fields -------------------------------------------
    imported_not_started: int = Field(
        default=0,
        description="Imported articles not yet released for screening "
        "(status 'imported')",
    )
    title_abstract_total: int = Field(
        default=0,
        description="Articles that entered title/abstract screening "
        "(every status except 'imported')",
    )
    title_abstract_decided: int = Field(
        default=0,
        description="Articles with at least one human title/abstract decision "
        "(includes articles still waiting for a second reviewer or in conflict)",
    )
    title_abstract_completed: int = Field(
        default=0,
        description="Articles whose title/abstract stage is settled: advanced to "
        "full text, excluded at title/abstract or closed by the stopping rule",
    )
    excluded_title_abstract: int = Field(
        default=0, description="Articles excluded by reviewers at title/abstract"
    )
    title_abstract_skipped: int = Field(
        default=0,
        description="Eligible articles that skipped title/abstract screening "
        "because they were screened elsewhere (counted in title_abstract_total "
        "and title_abstract_completed)",
    )
    not_screened_stopping_rule: int = Field(
        default=0,
        description="Articles closed at title/abstract without screening by the "
        "stopping rule (prioritized screening). Counted in title_abstract_total and "
        "title_abstract_completed; not in excluded or excluded_title_abstract",
    )
    full_text_eligible: int = Field(
        default=0,
        description="Articles that passed title/abstract (at the full-text stage "
        "or later included/excluded at full text)",
    )
    full_text_retrieved: int = Field(
        default=0,
        description="Eligible articles past full-text retrieval "
        "(full_text_eligible minus awaiting_full_text)",
    )
    awaiting_full_text_screening: int = Field(
        default=0,
        description="Articles with a full text waiting for a full-text decision "
        "(status 'full_text_retrieved')",
    )
    full_text_decided: int = Field(
        default=0,
        description="Eligible articles with at least one human full-text decision",
    )
    full_text_completed: int = Field(
        default=0,
        description="Articles whose full-text stage is settled (included or "
        "excluded at full text)",
    )
    excluded_full_text: int = Field(
        default=0, description="Articles excluded at full text"
    )

    # --- Prioritized screening ---------------------------------------------
    stopping_rule: Optional[StoppingRuleSummary] = Field(
        default=None,
        description="Stopping-rule progress (null unless prioritized screening is on)",
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RankingRun(SQLModel, table=True):
    """One retraining of a project's title/abstract relevance model."""

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True, ondelete="CASCADE")
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    model_version: str = Field(max_length=50, description="e.g. tfidf-logreg-v1")
    method: str = Field(max_length=20, description="model | similarity | random")
    trigger: str = Field(max_length=20, description="auto | manual")
    triggered_by: Optional[int] = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    labelled_includes: int = Field(default=0)
    labelled_excludes: int = Field(default=0)
    scored: int = Field(default=0, description="Records given a relevance_score")
    duration_ms: int = Field(default=0)
