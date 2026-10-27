import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, Path
from fastapi.params import Depends
from fastapi_fsp import FSPManager
from sqlmodel import select
from fastapi_fsp.models import PaginatedResponse
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import SessionDep
from app.core.uploads import display_filename, remove_file, save_upload
from app.features.audit import services as audit
from app.features.auth.services import get_current_user
from app.features.users.models import User
from .models import ImportBatch, Project, ProjectCreate, ProjectUpdate
from .permissions import OwnerAccess, ViewerAccess
from .services import ProjectService, ProjectServiceDep
from app.features.screening.services import ScreeningService
from .flows import parse_ris_file_flow, parse_pubmed_file_flow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Projects"], prefix="/projects")


@router.get("", response_model=PaginatedResponse[Project])
def get_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    fsp: Annotated[FSPManager, Depends()],
):
    projects = ProjectService.get_projects_of_user(current_user)
    return fsp.generate_response(projects, session)


@router.get("/{project_id}", response_model=Project)
def get_project(access: ViewerAccess):
    return access.project


@router.get("/{project_id}/me")
def get_my_role(access: ViewerAccess):
    """The caller's role in the project (viewer, reviewer or owner)."""
    return {
        "project_id": access.project.id,
        "user_id": access.user.id,
        "role": access.role,
    }


@router.post("", response_model=Project, status_code=201)
def create_project(
    data: ProjectCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
):
    return ps.create_project(data, current_user)


@router.post("/{project_id}/upload/ris", status_code=200)
async def upload_ris_file(
    file: UploadFile,
    access: OwnerAccess,
    project_id: int = Path(
        ..., title="The ID of the project to link the articles to", gt=0
    ),
):
    """
    Accepts a RIS file upload, saves it temporarily, and dispatches a
    Prefect flow to parse it.
    """
    temp_file_path: str | None = None
    try:
        # Validates extension and size; stored under a server-generated name
        temp_file_path = await save_upload(
            file,
            get_settings().upload_directory,
            {".ris"},
            invalid_type_detail="Invalid file type. Please upload a .ris file.",
        )

        # The flow removes the temporary file when it finishes
        result = parse_ris_file_flow(
            temp_file_path, project_id, display_filename(file), access.user.id
        )

        return JSONResponse(
            content={
                "message": "File processing complete.",
                "result": result,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error during file upload")
        if temp_file_path:
            remove_file(temp_file_path)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during file processing.",
        ) from e
    finally:
        # Close the uploaded file
        await file.close()


@router.post("/{project_id}/upload/pubmed", status_code=200)
async def upload_pubmed_file(
    file: UploadFile,
    access: OwnerAccess,
    project_id: int = Path(
        ..., title="The ID of the project to link the articles to", gt=0
    ),
):
    """
    Accepts a PubMed export file upload (.txt MEDLINE format or .csv),
    saves it temporarily, and dispatches a Prefect flow to parse it.

    For CSV files, abstracts will be automatically fetched from PubMed.
    """
    temp_file_path: str | None = None
    try:
        temp_file_path = await save_upload(
            file,
            get_settings().upload_directory,
            {".txt", ".csv"},
            invalid_type_detail=(
                "Invalid file type. Please upload a .txt (MEDLINE) or .csv file."
            ),
        )

        # The flow removes the temporary file when it finishes
        result = parse_pubmed_file_flow(
            temp_file_path, project_id, display_filename(file), access.user.id
        )

        return JSONResponse(
            content={
                "message": "File processing complete.",
                "result": result,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error during file upload")
        if temp_file_path:
            remove_file(temp_file_path)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during file processing.",
        ) from e
    finally:
        # Close the uploaded file
        await file.close()


@router.get("/{project_id}/imports", response_model=list[ImportBatch])
def get_imports(access: ViewerAccess, session: SessionDep):
    """List the project's import batches, newest first."""
    return session.exec(
        select(ImportBatch)
        .where(ImportBatch.project_id == access.project.id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    ).all()


@router.patch("/{project_id}", response_model=Project)
def update_project(
    data: ProjectUpdate,
    access: OwnerAccess,
    ps: ProjectServiceDep,
    session: SessionDep,
):
    """Update project fields and settings (owner only)."""
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    reviewers_before = access.project.required_reviewers
    project = ps.update_project(access.project, data)
    if project.required_reviewers != reviewers_before:
        # Articles may now be settled (or in conflict) under the new rule.
        ScreeningService(session).reevaluate_project(project)
    if changes:
        audit.record_event(
            session,
            project.id,
            audit.PROJECT_SETTINGS_UPDATED,
            "project",
            project.id,
            access.user.id,
            changes,
        )
        session.refresh(project)  # the audit commit expired it
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(access: OwnerAccess, ps: ProjectServiceDep):
    ps.delete_project(access.project)
    return
