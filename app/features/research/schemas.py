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


class SourceAttempt(BaseModel):
    """Outcome of trying one full-text source."""

    source: str = Field(description="unpaywall, pmc or europepmc")
    status: Literal["success", "not_configured", "not_available", "error"]
    detail: str | None = None


class FullTextRetrievalResult(BaseModel):
    """Outcome of an automatic full-text retrieval for one article."""

    article_id: int
    retrieved: bool
    source: str | None = None
    error: str | None = None
    attempts: list[SourceAttempt] = Field(default_factory=list)


class RetrieveFullTextRequest(BaseModel):
    """Optional body for the bulk retrieval endpoint."""

    article_ids: list[int] | None = Field(
        default=None,
        description="Articles to retrieve; default: all awaiting full text",
    )


MatchConfidence = Literal["high", "medium", "low"]


class PdfMatchCandidate(BaseModel):
    """An article an uploaded PDF may belong to."""

    article_id: int
    title: str | None = None
    year: int | None = None
    first_author: str | None = None
    has_full_text: bool = False
    method: str = Field(
        description="How it matched, e.g. doi_metadata, doi_filename, doi_text, "
        "pmid_filename, pmcid_text, title_text, title_filename, article_id_filename"
    )
    confidence: MatchConfidence


class PdfMatchResult(BaseModel):
    """One staged PDF and its proposed article."""

    upload_id: str | None = Field(
        default=None, description="Staged upload to confirm or discard; None on error"
    )
    filename: str
    error: str | None = None
    text_extracted: bool = False
    match: PdfMatchCandidate | None = None
    candidates: list[PdfMatchCandidate] = Field(default_factory=list)


class PdfAttachItem(BaseModel):
    """Attach a staged PDF to an article."""

    upload_id: str
    article_id: int
    replace: bool = Field(
        default=False, description="Replace a full text the article already has"
    )


class PdfBulkConfirmRequest(BaseModel):
    """Attach staged PDFs and drop the ones not wanted."""

    attach: list[PdfAttachItem] = Field(default_factory=list)
    discard: list[str] = Field(default_factory=list)


class PdfAttachResult(BaseModel):
    """Outcome of attaching one staged PDF."""

    upload_id: str
    article_id: int
    status: Literal["attached", "skipped", "error"]
    detail: str | None = None
    text_extracted: bool = False


class PdfBulkConfirmResponse(BaseModel):
    """Per-file outcomes of a bulk confirm."""

    attached: int
    results: list[PdfAttachResult]
