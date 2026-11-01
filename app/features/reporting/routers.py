import re
from datetime import date
from typing import Annotated, Iterator, Literal, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.database import SessionDep
from app.features.audit import services as audit
from app.features.projects.permissions import OwnerAccess, ViewerAccess
from app.features.research.models import ArticleStatus
from .schemas import PrismaFlow
from .services import ReportingServiceDep

router = APIRouter(tags=["Reporting"], prefix="/projects/{project_id}")

MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "ris": "application/x-research-info-systems; charset=utf-8",
}


def _filename(project_name: str, fmt: str) -> str:
    """ASCII-only, header-safe download name: ``<slug>-export-<date>.<fmt>``."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", project_name).strip("-").lower() or "project"
    return f"{slug[:60]}-export-{date.today().isoformat()}.{fmt}"


@router.get("/prisma", response_model=PrismaFlow)
def get_prisma_flow(access: ViewerAccess, rs: ReportingServiceDep):
    """PRISMA 2020 flow counts.

    * identified / duplicates come from the persisted import batches (or the article
      count when a project has none);
    * screened = articles that left ``imported``, minus those screened at
      title/abstract elsewhere (``records_screened_elsewhere``: imported with
      ``title_abstract_screened`` or moved by ``skip-title-abstract``) and those
      closed by the stopping rule; excluded at title/abstract =
      excluded articles whose deciding decision was at that stage;
    * marked ineligible by automation tools = records closed by the stopping rule
      without screening; they are part of neither ``records_screened`` nor
      ``records_excluded``;
    * sought = articles past title/abstract; not retrieved = still
      ``awaiting_full_text``; assessed = sought - not retrieved;
    * full-text exclusions are grouped by the deciding decision's
      ``primary_exclusion_reason`` (or its first met exclusion criterion code);
    * ``screening_method``: a suggested methods sentence (null unless prioritized
      screening was used).
    """
    return rs.prisma(access.project)


@router.get("/export")
def export_articles(
    access: OwnerAccess,
    rs: ReportingServiceDep,
    session: SessionDep,
    format: Annotated[Literal["csv", "ris"], Query()] = "csv",
    status: Annotated[Optional[ArticleStatus], Query()] = None,
):
    """Download the project's articles with decisions as CSV or RIS (owner only).

    Records closed by the stopping rule have the exclusion reason "Not screened
    (stopping rule)". ``relevance_score`` (CSV column; an ``N1`` note in RIS) is the
    record's predicted title/abstract relevance from the last ranking before it left
    the queue (prioritized screening); empty when never ranked. Scores of different
    ranking runs are not on a common scale.
    """
    project = access.project
    records = rs.export_records(project, status)
    audit.record_event(
        session,
        project.id,
        audit.EXPORT_CREATED,
        "export",
        None,
        access.user.id,
        {
            "format": format,
            "status": status.value if status else None,
            "records": len(records),
        },
    )
    body: Iterator[str] = (
        rs.iter_csv(records) if format == "csv" else rs.iter_ris(records)
    )
    return StreamingResponse(
        body,
        media_type=MEDIA_TYPES[format],
        headers={
            "Content-Disposition": f'attachment; filename="{_filename(project.name, format)}"'
        },
    )
