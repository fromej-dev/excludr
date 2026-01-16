from typing import Annotated

from fastapi import APIRouter, HTTPException, Depends
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.features.auth.services import get_current_user
from app.features.users.models import User
from app.features.projects.services import ProjectServiceDep
from .models import Criterion, CriterionCreate, CriterionUpdate, CriterionReorder
from .services import CriterionServiceDep

router = APIRouter(tags=["Criteria"], prefix="/projects/{project_id}/criteria")


def verify_project_ownership(
    project_id: int, current_user: User, ps: ProjectServiceDep
):
    """Helper to verify project exists and user owns it."""
    project = ps.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the owner of the project"
        )
    return project


@router.get("", response_model=PaginatedResponse[Criterion])
def get_criteria(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    ps: ProjectServiceDep,
    cs: CriterionServiceDep,
    fsp: Annotated[FSPManager, Depends()],
    active_only: bool = False,
):
    """Get all criteria for a project."""
    verify_project_ownership(project_id, current_user, ps)
    if active_only:
        query = cs.get_active_criteria_for_project(project_id)
    else:
        query = cs.get_criteria_for_project(project_id)
    return fsp.generate_response(query, session)


@router.get("/{criterion_id}", response_model=Criterion)
def get_criterion(
    project_id: int,
    criterion_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    cs: CriterionServiceDep,
):
    """Get a single criterion by ID."""
    verify_project_ownership(project_id, current_user, ps)
    criterion = cs.get_criterion_by_id(criterion_id)
    if criterion is None or criterion.project_id != project_id:
        raise HTTPException(status_code=404, detail="Criterion not found")
    return criterion


@router.post("", response_model=Criterion, status_code=201)
def create_criterion(
    project_id: int,
    data: CriterionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    cs: CriterionServiceDep,
):
    """Create a new criterion for a project."""
    verify_project_ownership(project_id, current_user, ps)
    return cs.create_criterion(project_id, data)


@router.patch("/{criterion_id}", response_model=Criterion)
def update_criterion(
    project_id: int,
    criterion_id: int,
    data: CriterionUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    cs: CriterionServiceDep,
):
    """Update an existing criterion."""
    verify_project_ownership(project_id, current_user, ps)
    criterion = cs.get_criterion_by_id(criterion_id)
    if criterion is None or criterion.project_id != project_id:
        raise HTTPException(status_code=404, detail="Criterion not found")
    return cs.update_criterion(criterion, data)


@router.delete("/{criterion_id}", status_code=204)
def delete_criterion(
    project_id: int,
    criterion_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    cs: CriterionServiceDep,
):
    """Delete a criterion."""
    verify_project_ownership(project_id, current_user, ps)
    criterion = cs.get_criterion_by_id(criterion_id)
    if criterion is None or criterion.project_id != project_id:
        raise HTTPException(status_code=404, detail="Criterion not found")
    cs.delete_criterion(criterion)
    return


@router.post("/reorder", response_model=list[Criterion])
def reorder_criteria(
    project_id: int,
    data: CriterionReorder,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    cs: CriterionServiceDep,
):
    """Reorder criteria for a project."""
    verify_project_ownership(project_id, current_user, ps)
    return cs.reorder_criteria(project_id, data.criterion_ids)
