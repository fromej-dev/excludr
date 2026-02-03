from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum
from sqlmodel import Field, SQLModel, Column, JSON, Text, Relationship

from app.features.projects.models import Project

if TYPE_CHECKING:
    from app.features.screening.models import ScreeningDecision

# Import ScreeningStage from screening to avoid duplication
from app.features.screening.models import ScreeningStage


class ArticleStatus(str, Enum):
    """Status of an article in the screening pipeline."""

    imported = "imported"
    screening = "screening"
    awaiting_full_text = "awaiting_full_text"
    full_text_retrieved = "full_text_retrieved"
    included = "included"
    excluded = "excluded"


class FinalDecision(str, Enum):
    """Final decision for an article."""

    pending = "pending"
    included = "included"
    excluded = "excluded"


class Article(SQLModel, table=True):
    """
    Represents an article with comprehensive details for processing and analysis.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    # --- Foreign Key to Project ---
    project_id: Optional[int] = Field(
        default=None, foreign_key="project.id", index=True
    )
    project: Optional[Project] = Relationship(back_populates="articles")

    # --- Core Bibliographic Information ---
    title: Optional[str] = Field(index=True)
    authors: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSON))
    abstract: Optional[str] = Field(default=None, sa_column=Column(Text))
    publication_date: Optional[str] = Field(
        default=None,
        description="Flexible date format (e.g., 'Spring 2023', '2023-09-15')",
    )
    year: Optional[int] = Field(default=None, index=True)

    # --- Journal & Publication Details ---
    journal: Optional[str] = Field(default=None, index=True)
    volume: Optional[str] = Field(default=None)
    issue: Optional[str] = Field(default=None)
    pages: Optional[str] = Field(default=None)
    publication_type: Optional[str] = Field(
        default=None,
        description="e.g., Journal Article, Conference Paper, Book Chapter",
    )

    # --- Standard Identifiers ---
    doi: Optional[str] = Field(default=None, unique=True, index=True)
    pmid: Optional[str] = Field(
        default=None, unique=True, index=True, description="PubMed ID"
    )
    pmcid: Optional[str] = Field(
        default=None,
        unique=True,
        index=True,
        description="PubMed Central ID for full-text",
    )
    issn: Optional[str] = Field(
        default=None, index=True, description="International Standard Serial Number"
    )

    # --- Keywords & Topics ---
    keywords: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSON))
    mesh_terms: Optional[List[str]] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Medical Subject Headings",
    )

    # --- Links for Full-Text Retrieval ---
    article_url: Optional[str] = Field(
        default=None, description="URL to the article's landing page"
    )
    full_text_url: Optional[str] = Field(
        default=None, description="Direct link to the full text (e.g., a PDF)"
    )
    urls: Optional[List[str]] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="A collection of all other URLs found in the source file",
    )

    # --- Full Text & AI Agent Processing Pipeline ---
    # These fields will be updated by your future Celery tasks.
    full_text_retrieved: bool = Field(
        default=False,
        index=True,
        description="Flag indicating if the full text has been successfully downloaded",
    )
    full_text_path: Optional[str] = Field(
        default=None,
        description="Local file system path to the stored full text content",
    )
    full_text_content: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="Extracted text content from the full-text PDF",
    )

    ai_check_status: Optional[str] = Field(
        default="pending",
        index=True,
        description="Status of the AI check (e.g., pending, in_progress, completed, error)",
    )
    ai_check_result: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Structured results from the AI agent's analysis",
    )
    last_ai_check: Optional[datetime] = Field(
        default=None, description="Timestamp of the last completed AI check"
    )

    # --- Screening Status & Stage ---
    status: ArticleStatus = Field(
        default=ArticleStatus.imported,
        index=True,
        description="Current status in the screening pipeline",
    )
    current_stage: ScreeningStage = Field(
        default=ScreeningStage.title_abstract,
        index=True,
        description="Current screening stage",
    )
    final_decision: FinalDecision = Field(
        default=FinalDecision.pending,
        index=True,
        description="Final screening decision",
    )

    # --- Screening Decisions Relationship ---
    screening_decisions: List["ScreeningDecision"] = Relationship(
        back_populates="article"
    )

    # --- Provenance & Timestamps ---
    source_filename: Optional[str] = Field(
        default=None,
        description="The name of the RIS file this article originated from",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"onupdate": datetime.utcnow},
    )
