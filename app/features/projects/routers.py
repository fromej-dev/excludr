import os
import shutil
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, Path
from fastapi.params import Depends
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import SessionDep
from app.features.auth.services import get_current_user
from app.features.users.models import User
from .models import Project, ProjectCreate, ProjectUpdate
from .services import ProjectService, ProjectServiceDep
from .flows import parse_ris_file_flow, parse_pubmed_file_flow

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
def get_project(
    current_user: Annotated[User, Depends(get_current_user)],
    project_id: int,
    ps: ProjectServiceDep,
):
    project = ps.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the owner of the project"
        )
    return project


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
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    project_id: int = Path(
        ..., title="The ID of the project to link the articles to", gt=0
    ),
):
    """
    Accepts a RIS file upload, saves it temporarily, and dispatches a
    Prefect flow to parse it.
    """
    # Verify project ownership
    project = ps.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the owner of the project"
        )

    # Ensure the uploaded file is a RIS file
    if not file.filename.lower().endswith(".ris"):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Please upload a .ris file."
        )

    try:
        # Create a unique filename to avoid collisions
        safe_filename = f"{uuid.uuid4()}_{file.filename}"
        temp_file_path = os.path.join(get_settings().upload_directory, safe_filename)

        # Ensure upload directory exists
        os.makedirs(get_settings().upload_directory, exist_ok=True)

        # Save the uploaded file to the temporary directory
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Run the Prefect flow (can be run async with .submit() if Prefect server is configured)
        # For now, we'll run it synchronously or use run_deployment for async

        # Run the flow - this will execute synchronously
        # For production, use deployments for true async execution
        result = parse_ris_file_flow(temp_file_path, project_id)

        return JSONResponse(
            content={
                "message": "File processing complete.",
                "result": result,
            }
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Error during file upload: {e}")
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
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
    project_id: int = Path(
        ..., title="The ID of the project to link the articles to", gt=0
    ),
):
    """
    Accepts a PubMed export file upload (.txt MEDLINE format or .csv),
    saves it temporarily, and dispatches a Prefect flow to parse it.

    For CSV files, abstracts will be automatically fetched from PubMed.
    """
    # Verify project ownership
    project = ps.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the owner of the project"
        )

    # Ensure the uploaded file is a valid PubMed format
    filename_lower = file.filename.lower() if file.filename else ""
    if not (filename_lower.endswith(".txt") or filename_lower.endswith(".csv")):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a .txt (MEDLINE) or .csv file.",
        )

    try:
        # Create a unique filename to avoid collisions
        safe_filename = f"{uuid.uuid4()}_{file.filename}"
        temp_file_path = os.path.join(get_settings().upload_directory, safe_filename)

        # Ensure upload directory exists
        os.makedirs(get_settings().upload_directory, exist_ok=True)

        # Save the uploaded file to the temporary directory
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Run the Prefect flow
        result = parse_pubmed_file_flow(temp_file_path, project_id)

        return JSONResponse(
            content={
                "message": "File processing complete.",
                "result": result,
            }
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Error during file upload: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during file processing.",
        ) from e
    finally:
        # Close the uploaded file
        await file.close()


@router.patch("/{project_id}", response_model=Project)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
):
    project = ps.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the owner of the project"
        )
    return ps.update_project(project, data)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    ps: ProjectServiceDep,
):
    project = ps.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the owner of the project"
        )
    ps.delete_project(project)
    return
