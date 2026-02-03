"""Pydantic schemas for AI agent screening results."""

from typing import Literal
from pydantic import BaseModel, Field


class CriterionEvaluation(BaseModel):
    """Evaluation of a single criterion against an article.

    Attributes:
        criterion_code: The criterion code (e.g., "I1", "E1")
        criterion_type: Type of criterion - "inclusion" or "exclusion"
        met: True if criterion is met, False if not met, None if unable to determine
        confidence: Confidence score from 0.0 to 1.0
        reasoning: Explanation of why this judgment was made
    """

    criterion_code: str = Field(description="Criterion code (e.g., I1, E1)")
    criterion_type: str = Field(description="inclusion or exclusion")
    met: bool | None = Field(
        description="True=met, False=not met, None=unable to determine"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    reasoning: str = Field(description="Reasoning for this judgment")


class ScreeningResult(BaseModel):
    """Overall screening result from the AI agent.

    Attributes:
        decision: Overall decision - include, exclude, or uncertain
        confidence: Overall confidence score from 0.0 to 1.0
        criteria_evaluations: List of per-criterion evaluations
        primary_exclusion_reason: The main reason for exclusion (if applicable)
        summary_reasoning: Overall summary of the screening decision
    """

    decision: Literal["include", "exclude", "uncertain"] = Field(
        description="Overall screening decision"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence score 0.0-1.0"
    )
    criteria_evaluations: list[CriterionEvaluation] = Field(
        description="Per-criterion evaluations"
    )
    primary_exclusion_reason: str | None = Field(
        default=None, description="Main reason for exclusion if excluded"
    )
    summary_reasoning: str = Field(description="Overall summary reasoning")
