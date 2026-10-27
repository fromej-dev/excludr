from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.features.audit import services as audit
from app.features.projects.permissions import OwnerAccess, ViewerAccess
from .models import Criterion, CriterionCreate, CriterionUpdate, CriterionReorder
from .services import CriterionServiceDep


def _plain(value):
    """JSON-friendly form of a criterion field value (enums -> their value)."""
    return getattr(value, "value", value)


router = APIRouter(tags=["Criteria"], prefix="/projects/{project_id}/criteria")


@router.get("", response_model=PaginatedResponse[Criterion])
def get_criteria(
    project_id: int,
    access: ViewerAccess,
    session: SessionDep,
    cs: CriterionServiceDep,
    fsp: Annotated[FSPManager, Depends()],
    active_only: bool = False,
):
    """Get all criteria for a project."""
    if active_only:
        query = cs.get_active_criteria_for_project(project_id)
    else:
        query = cs.get_criteria_for_project(project_id)
    return fsp.generate_response(query, session)


@router.get("/{criterion_id}", response_model=Criterion)
def get_criterion(
    project_id: int,
    criterion_id: int,
    access: ViewerAccess,
    cs: CriterionServiceDep,
):
    """Get a single criterion by ID."""
    criterion = cs.get_criterion_by_id(criterion_id)
    if criterion is None or criterion.project_id != project_id:
        raise HTTPException(status_code=404, detail="Criterion not found")
    return criterion


@router.post("", response_model=Criterion, status_code=201)
def create_criterion(
    project_id: int,
    data: CriterionCreate,
    access: OwnerAccess,
    cs: CriterionServiceDep,
    session: SessionDep,
):
    """Create a new criterion for a project."""
    criterion = cs.create_criterion(project_id, data)
    audit.record_event(
        session,
        project_id,
        audit.CRITERION_CREATED,
        "criterion",
        criterion.id,
        access.user.id,
        {"code": criterion.code, "type": criterion.type.value},
    )
    session.refresh(criterion)  # the audit commit expired it
    return criterion


@router.patch("/{criterion_id}", response_model=Criterion)
def update_criterion(
    project_id: int,
    criterion_id: int,
    data: CriterionUpdate,
    access: OwnerAccess,
    cs: CriterionServiceDep,
    session: SessionDep,
):
    """Update an existing criterion."""
    criterion = cs.get_criterion_by_id(criterion_id)
    if criterion is None or criterion.project_id != project_id:
        raise HTTPException(status_code=404, detail="Criterion not found")
    changes = data.model_dump(
        exclude_unset=True, exclude_defaults=True, exclude_none=True
    )
    before = {k: getattr(criterion, k) for k in changes}
    criterion = cs.update_criterion(criterion, data)
    audit.record_event(
        session,
        project_id,
        audit.CRITERION_UPDATED,
        "criterion",
        criterion.id,
        access.user.id,
        {
            "code": criterion.code,
            "version": criterion.version,
            "changes": {
                k: {"from": _plain(before[k]), "to": _plain(v)}
                for k, v in changes.items()
                if before[k] != v
            },
        },
    )
    session.refresh(criterion)
    return criterion


@router.delete("/{criterion_id}", status_code=204)
def delete_criterion(
    project_id: int,
    criterion_id: int,
    access: OwnerAccess,
    cs: CriterionServiceDep,
    session: SessionDep,
):
    """Delete a criterion."""
    criterion = cs.get_criterion_by_id(criterion_id)
    if criterion is None or criterion.project_id != project_id:
        raise HTTPException(status_code=404, detail="Criterion not found")
    details = {"code": criterion.code, "type": criterion.type.value}
    cs.delete_criterion(criterion)
    audit.record_event(
        session,
        project_id,
        audit.CRITERION_DELETED,
        "criterion",
        criterion_id,
        access.user.id,
        details,
    )
    return


@router.post("/reorder", response_model=list[Criterion])
def reorder_criteria(
    project_id: int,
    data: CriterionReorder,
    access: OwnerAccess,
    cs: CriterionServiceDep,
):
    """Reorder criteria for a project."""
    return cs.reorder_criteria(project_id, data.criterion_ids)
