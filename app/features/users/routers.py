from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.database import SessionDep
from .services import UserService, UserServiceDep
from .models import User, UserPublic
from ..auth.services import get_current_user, get_current_admin_user

router = APIRouter(tags=["Users"], prefix="/users")


@router.get("", response_model=PaginatedResponse[UserPublic])
async def get_users(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    session: SessionDep,
    fsp: Annotated[FSPManager, Depends()],
):
    users = UserService.get_users()
    return fsp.generate_response(users, session)


@router.get("/me", response_model=UserPublic)
def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    user_id: int,
    us: UserServiceDep,
):
    user = us.get_user_by_id(user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
