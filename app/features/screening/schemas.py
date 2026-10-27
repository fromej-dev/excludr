"""Request/response schemas for dual screening, conflicts and agreement."""

from datetime import datetime
from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from .models import ScreeningDecisionType, ScreeningStage


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
