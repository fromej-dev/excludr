"""Export and PRISMA 2020 reporting built on top of screening outcomes."""

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass
from typing import Annotated, Iterator, Optional

import rispy
from fastapi import Depends
from sqlmodel import Session, select

from app.core.database import SessionDep
from app.features.criteria.models import Criterion, CriterionType
from app.features.projects.models import ImportBatch, Project
from app.features.research.models import Article, ArticleStatus
from app.features.screening.consensus import EXCLUDE
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningStage,
)
from app.features.screening.services import ScreeningService
from .schemas import (
    ExclusionReasonCount,
    PrismaEligibility,
    PrismaFlow,
    PrismaIdentification,
    PrismaIncluded,
    PrismaRetrieval,
    PrismaScreening,
    PrismaSource,
)

CSV_COLUMNS = [
    "id",
    "title",
    "authors",
    "year",
    "journal",
    "doi",
    "pmid",
    "status",
    "current_stage",
    "final_decision",
    "exclusion_reason",
    "ai_decision",
    "ai_confidence",
]

UNSPECIFIED_REASON = "Unspecified"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_RIS_TYPE = re.compile(r"^[A-Z]{3,5}$")


@dataclass(frozen=True)
class ExportRecord:
    """An article with the screening information exported alongside it."""

    article: Article
    exclusion_reason: Optional[str]
    ai_decision: Optional[str]
    ai_confidence: Optional[float]


def safe_csv_cell(value: object) -> str:
    """Render a value for CSV, neutralising spreadsheet formula injection."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


class ReportingService:
    """Builds export rows and the PRISMA flow for a project."""

    def __init__(self, session: Session):
        self.session = session
        self.screening = ScreeningService(session)

    # -- shared helpers -------------------------------------------------

    def _exclusion_codes(self, project_id: int) -> set[str]:
        return set(
            self.session.exec(
                select(Criterion.code).where(
                    Criterion.project_id == project_id,
                    Criterion.type == CriterionType.exclusion,
                )
            ).all()
        )

    @staticmethod
    def _reason_of(
        decision: Optional[ScreeningDecision], exclusion_codes: set[str]
    ) -> Optional[str]:
        """Exclusion reason of a deciding decision: explicit reason, else the first
        met exclusion criterion in its per-criterion evaluations."""
        if decision is None:
            return None
        if decision.primary_exclusion_reason:
            return decision.primary_exclusion_reason
        for code, evaluation in (decision.criteria_evaluations or {}).items():
            if (
                code in exclusion_codes
                and isinstance(evaluation, dict)
                and evaluation.get("met") is True
            ):
                return code
        return None

    def _exclusion_outcomes(
        self, project: Project
    ) -> dict[int, tuple[ScreeningStage, Optional[ScreeningDecision]]]:
        """For each article with a settled *exclude* outcome: its stage and the
        deciding decision. Full-text exclusions win over title/abstract ones."""
        outcomes = self.screening.get_final_outcomes(project)
        decisions = {d.id: d for d in self.screening.human_decisions(project.id)}
        result: dict[int, tuple[ScreeningStage, Optional[ScreeningDecision]]] = {}
        for stage in (ScreeningStage.title_abstract, ScreeningStage.full_text):
            for (article_id, st), state in outcomes.items():
                if st == stage and state.outcome == EXCLUDE:
                    result[article_id] = (stage, decisions.get(state.deciding_id))
        return result

    # -- export ---------------------------------------------------------

    def export_records(
        self, project: Project, status: Optional[ArticleStatus] = None
    ) -> list[ExportRecord]:
        """Articles (optionally filtered by status) with decision information."""
        query = select(Article).where(Article.project_id == project.id)
        if status is not None:
            query = query.where(Article.status == status)
        articles = self.session.exec(query.order_by(Article.id)).all()

        exclusions = self._exclusion_outcomes(project)
        codes = self._exclusion_codes(project.id)
        ai_latest: dict[int, ScreeningDecision] = {}
        for d in self.session.exec(
            select(ScreeningDecision)
            .join(Article, ScreeningDecision.article_id == Article.id)
            .where(
                Article.project_id == project.id,
                ScreeningDecision.source == DecisionSource.ai_agent,
            )
            .order_by(ScreeningDecision.created_at, ScreeningDecision.id)
        ):
            ai_latest[d.article_id] = d

        records = []
        for a in articles:
            reason = None
            if a.status == ArticleStatus.excluded and a.id in exclusions:
                reason = self._reason_of(exclusions[a.id][1], codes)
            ai = ai_latest.get(a.id)
            records.append(
                ExportRecord(
                    article=a,
                    exclusion_reason=reason,
                    ai_decision=ai.decision.value if ai else None,
                    ai_confidence=ai.confidence_score if ai else None,
                )
            )
        return records

    @staticmethod
    def iter_csv(records: list[ExportRecord]) -> Iterator[str]:
        """Yield the CSV export line by line."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def flush() -> str:
            data = buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            return data

        writer.writerow(CSV_COLUMNS)
        yield flush()
        for r in records:
            a = r.article
            writer.writerow(
                [
                    safe_csv_cell(v)
                    for v in (
                        a.id,
                        a.title,
                        "; ".join(a.authors or []),
                        a.year,
                        a.journal,
                        a.doi,
                        a.pmid,
                        a.status.value,
                        a.current_stage.value,
                        a.final_decision.value,
                        r.exclusion_reason,
                        r.ai_decision,
                        r.ai_confidence,
                    )
                ]
            )
            yield flush()

    @staticmethod
    def ris_entry(r: ExportRecord) -> dict:
        """Map an exported article to a ``rispy`` entry."""
        a = r.article
        ref_type = (
            a.publication_type
            if a.publication_type and _RIS_TYPE.match(a.publication_type)
            else "JOUR"
        )
        notes = [
            f"Excludr status: {a.status.value}",
            f"Excludr final decision: {a.final_decision.value}",
        ]
        if r.exclusion_reason:
            notes.append(f"Exclusion reason: {r.exclusion_reason}")
        if r.ai_decision:
            conf = f" ({r.ai_confidence:.2f})" if r.ai_confidence is not None else ""
            notes.append(f"AI decision: {r.ai_decision}{conf}")
        entry: dict = {
            "type_of_reference": ref_type,
            "title": a.title,
            "authors": list(a.authors or []),
            "abstract": a.abstract,
            "year": str(a.year) if a.year else None,
            "journal_name": a.journal,
            "volume": a.volume,
            "number": a.issue,
            "doi": a.doi,
            "accession_number": a.pmid,
            "issn": a.issn,
            "keywords": list(a.keywords or []),
            "urls": [u for u in [a.article_url, *(a.urls or [])] if u],
            "notes": notes,
        }
        if a.pages:
            start, _, end = a.pages.partition("-")
            entry["start_page"] = start
            if end:
                entry["end_page"] = end
        return {k: v for k, v in entry.items() if v not in (None, "", [])}

    def iter_ris(self, records: list[ExportRecord]) -> Iterator[str]:
        """Yield the RIS export one reference at a time."""
        for r in records:
            yield rispy.dumps([self.ris_entry(r)]) + "\n"

    # -- PRISMA ---------------------------------------------------------

    def prisma(self, project: Project) -> PrismaFlow:
        """PRISMA 2020 flow counts (see the endpoint docs for the definitions)."""
        batches = self.session.exec(
            select(ImportBatch)
            .where(ImportBatch.project_id == project.id)
            .order_by(ImportBatch.created_at, ImportBatch.id)
        ).all()
        # Stage counts share one definition with the screening stats endpoint.
        stats = self.screening.get_screening_stats(project.id)

        if batches:
            identified = sum(b.records_found for b in batches)
            duplicates = sum(b.duplicates for b in batches)
        else:  # articles added without a tracked import
            identified, duplicates = stats.total_articles, 0

        exclusions = self._exclusion_outcomes(project)
        codes = self._exclusion_codes(project.id)
        excluded_ids = self.session.exec(
            select(Article.id).where(
                Article.project_id == project.id,
                Article.status == ArticleStatus.excluded,
            )
        ).all()
        reasons: Counter[str] = Counter()
        for article_id in excluded_ids:
            ex = exclusions.get(article_id)
            if ex is not None and ex[0] == ScreeningStage.full_text:
                reasons[self._reason_of(ex[1], codes) or UNSPECIFIED_REASON] += 1

        # Records screened elsewhere skip this box and go straight to retrieval.
        screened = stats.title_abstract_total - stats.title_abstract_skipped
        excluded_ta = stats.excluded_title_abstract
        sought = stats.full_text_eligible
        not_retrieved = stats.awaiting_full_text
        excluded_ft = stats.excluded_full_text
        included = stats.included

        return PrismaFlow(
            identification=PrismaIdentification(
                sources=[
                    PrismaSource(
                        filename=b.filename,
                        format=b.format,
                        records_found=b.records_found,
                        imported=b.imported,
                        duplicates=b.duplicates,
                        imported_at=b.created_at,
                    )
                    for b in batches
                ],
                records_identified=identified,
                duplicates_removed=duplicates,
                records_after_duplicates_removed=identified - duplicates,
            ),
            screening=PrismaScreening(
                records_screened=screened,
                records_excluded=excluded_ta,
                records_screened_elsewhere=stats.title_abstract_skipped,
            ),
            retrieval=PrismaRetrieval(
                reports_sought=sought, reports_not_retrieved=not_retrieved
            ),
            eligibility=PrismaEligibility(
                reports_assessed=sought - not_retrieved,
                reports_excluded=excluded_ft,
                exclusion_reasons=[
                    ExclusionReasonCount(reason=reason, count=count)
                    for reason, count in sorted(
                        reasons.items(), key=lambda kv: (-kv[1], kv[0])
                    )
                ],
            ),
            included=PrismaIncluded(studies_included=included),
        )


def get_reporting_service(session: SessionDep) -> ReportingService:
    return ReportingService(session=session)


ReportingServiceDep = Annotated[ReportingService, Depends(get_reporting_service)]
