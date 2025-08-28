from typing import Annotated

from fastapi import APIRouter
from fastapi.params import Depends
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from app.features.auth.services import get_current_user
from app.features.users.models import User
from .models import Project
from .services import ProjectService

router = APIRouter(tags=["Projects"], prefix="/projects")


@router.get("", response_model=PaginatedResponse[Project])
def get_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    session: SessionDep,
    fsp: Annotated[FSPManager, Depends()],
):
    projects = ProjectService.get_projects_of_user(current_user)
    return fsp.generate_response(projects, session)
