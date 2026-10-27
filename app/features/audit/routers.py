from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.features.projects.permissions import OwnerAccess
from .models import AuditEvent
from .services import get_events_query

router = APIRouter(tags=["Audit"], prefix="/projects/{project_id}/audit")


@router.get("", response_model=PaginatedResponse[AuditEvent])
def get_audit_events(
    access: OwnerAccess,
    session: SessionDep,
    fsp: Annotated[FSPManager, Depends()],
):
    """List the project's audit trail, newest first (owner only)."""
    return fsp.generate_response(get_events_query(access.project.id), session)
