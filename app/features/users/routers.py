from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from .services import UserService, UserServiceDep
from .models import User, UserRead
from ..auth.services import get_current_user, get_current_admin_user

router = APIRouter(tags=["Users"], prefix="/users")


@router.get("", response_model=PaginatedResponse[User])
async def get_users(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    session: SessionDep,
    fsp: Annotated[FSPManager, Depends()],
):
    users = UserService.get_users()
    return fsp.generate_response(users, session)


@router.get("/me", response_model=UserRead)
def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.get("/{user_id}", response_model=User)
async def get_user(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    user_id: int,
    us: UserServiceDep,
):
    return us.get_user_by_id(user_id=user_id)
