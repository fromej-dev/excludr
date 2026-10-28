from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class PrismaSource(SQLModel):
    filename: str
    format: str
    records_found: int
    imported: int
    duplicates: int
    imported_at: Optional[datetime]


class PrismaIdentification(SQLModel):
    sources: list[PrismaSource]
    records_identified: int
    duplicates_removed: int
    records_after_duplicates_removed: int


class PrismaScreening(SQLModel):
    records_screened: int
    records_excluded: int
    records_screened_elsewhere: int = Field(
        default=0,
        description="Records that skipped title/abstract screening here because "
        "they were screened elsewhere (not part of records_screened)",
    )


class PrismaRetrieval(SQLModel):
    reports_sought: int
    reports_not_retrieved: int


class ExclusionReasonCount(SQLModel):
    reason: str
    count: int


class PrismaEligibility(SQLModel):
    reports_assessed: int
    reports_excluded: int
    exclusion_reasons: list[ExclusionReasonCount]


class PrismaIncluded(SQLModel):
    studies_included: int


class PrismaFlow(SQLModel):
    """PRISMA 2020 flow diagram counts for a project."""

    identification: PrismaIdentification
    screening: PrismaScreening
    retrieval: PrismaRetrieval
    eligibility: PrismaEligibility
    included: PrismaIncluded
