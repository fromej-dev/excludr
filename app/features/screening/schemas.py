"""Request/response schemas for dual screening, conflicts and agreement."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import field_validator, model_validator
from sqlmodel import Field, SQLModel

from .models import (  # noqa: F401
    ScreeningDecisionType,
    ScreeningStage,
    StoppingRuleSummary,
)


class ResolveRequest(SQLModel):
    """Owner's final decision for an article whose reviewers disagree."""

    decision: ScreeningDecisionType
    reason: str = Field(min_length=1, max_length=2000)
    primary_exclusion_reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("decision")
    @classmethod
    def _final_only(cls, value: ScreeningDecisionType) -> ScreeningDecisionType:
        if value == ScreeningDecisionType.uncertain:
            raise ValueError("A resolution must be 'include' or 'exclude'")
        return value


class ReviewerDecisionRead(SQLModel):
    decision_id: int
    reviewer_id: Optional[int]
    reviewer_name: Optional[str]
    decision: ScreeningDecisionType
    reasoning: Optional[str]
    primary_exclusion_reason: Optional[str]
    confidence_score: Optional[float]
    created_at: Optional[datetime]


class ConflictRead(SQLModel):
    article_id: int
    title: Optional[str]
    stage: ScreeningStage
    decisions: list[ReviewerDecisionRead]


class AIDecisionSummary(SQLModel):
    decision_id: int
    decision: ScreeningDecisionType
    confidence_score: Optional[float]
    reasoning: Optional[str]


class AIDisagreementRead(SQLModel):
    article_id: int
    title: Optional[str]
    stage: ScreeningStage
    ai: AIDecisionSummary
    human_decision: ScreeningDecisionType
    human_is_resolution: bool


class HumanAgreementRead(SQLModel):
    reviewers: list[int]
    n_articles: int
    percent_agreement: Optional[float]
    cohens_kappa: Optional[float]


class AIAgreementRead(SQLModel):
    n_articles: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    accuracy: Optional[float]
    sensitivity: Optional[float]
    specificity: Optional[float]
    cohens_kappa: Optional[float]
    ai_uncertain: int
    without_ai_decision: int


class AgreementRead(SQLModel):
    stage: ScreeningStage
    required_reviewers: int
    human_vs_human: Optional[HumanAgreementRead]
    ai_vs_human: AIAgreementRead


MAX_RUN_AI_ARTICLE_IDS = 10


class RunAIRequest(SQLModel):
    """Optional body of ``POST .../screening/run-ai``.

    ``article_ids`` limits the batch to a small subset (the screening view uses it to
    keep the AI a few articles ahead of the reviewer). Ids that are not in the
    project or not eligible are skipped.
    """

    article_ids: Optional[list[int]] = Field(
        default=None, min_length=1, max_length=MAX_RUN_AI_ARTICLE_IDS
    )


class RankingRunRead(SQLModel):
    """One relevance-ranking run (read shape of ``RankingRun``)."""

    id: int
    created_at: datetime
    model_version: str
    method: str
    trigger: str
    triggered_by: Optional[int] = None
    labelled_includes: int
    labelled_excludes: int
    scored: int
    duration_ms: int


class RerankResponse(SQLModel):
    """Answer to a manual rerank request (the state before the request)."""

    status: Literal["scheduled", "queued"]  # queued = runs right after the current run
    last_run: Optional[RankingRunRead] = None


class StoppingRuleStatus(SQLModel):
    """Answer of ``GET .../screening/stopping-rule``."""

    enabled: bool  # prioritized and a threshold is set
    prioritized: bool
    threshold: Optional[int]
    consecutive_excludes: int  # 0 when not prioritized
    met: bool
    remaining: int  # records at title/abstract screening, with or without votes
    closable: int  # of those, with no human title/abstract decision (what apply closes)
    screened: int  # settled human title/abstract outcomes, all time
    not_screened: int  # records currently closed by the rule
    last_ranked_at: Optional[datetime]
    applied_at: Optional[datetime]
    counting_since: Optional[datetime]  # start of the streak window
    last_run: Optional[RankingRunRead] = None


class ApplyStoppingRuleRequest(SQLModel):
    force: bool = False
    reason: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _reason_when_forced(self) -> "ApplyStoppingRuleRequest":
        if self.force and not (self.reason or "").strip():
            raise ValueError(
                "A reason is required to apply the stopping rule before it is met"
            )
        self.reason = self.reason.strip() if self.reason else None
        return self


class ApplyStoppingRuleResult(SQLModel):
    closed: int
    left_open: (
        int  # at title/abstract with human votes (partly reviewed, conflict, uncertain)
    )
    not_started: int  # legacy 'imported' records, untouched
    screened: int
    threshold: int
    consecutive_excludes: int
    forced: bool  # True only when the rule was not met
    reason: Optional[str]
    applied_at: datetime
    counting_since: Optional[datetime]
    ranking_run_id: Optional[int]
    model_version: Optional[str]
    ranking_method: Optional[str]


class ReopenNotScreenedResult(SQLModel):
    reopened: int
    previous_applied_at: Optional[datetime]
