from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi_fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

from app.core.config import get_settings
from app.core.database import SessionDep
from app.core.rate_limit import login_rate_limiter
from .schemas import EmailChange, PasswordChange, ProfileUpdate
from .services import UserService, UserServiceDep
from .models import User, UserPublic
from ..auth.schemas import Token
from ..auth.services import (
    get_current_user,
    get_current_admin_user,
    issue_tokens,
    verify_password,
)

router = APIRouter(tags=["Users"], prefix="/users")

CurrentUser = Annotated[User, Depends(get_current_user)]


def _check_current_password(user: User, password: str) -> None:
    """Re-authenticate a sensitive account change, throttled like login."""
    settings = get_settings()
    key = f"account|{user.id}"
    window = settings.login_rate_limit_window_seconds
    if login_rate_limiter.is_limited(key, settings.login_rate_limit_attempts, window):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(login_rate_limiter.retry_after(key, window))},
        )
    if not verify_password(password, user):
        login_rate_limiter.record(key, window)
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    login_rate_limiter.clear(key)


@router.get("", response_model=PaginatedResponse[UserPublic])
async def get_users(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    session: SessionDep,
    fsp: Annotated[FSPManager, Depends()],
):
    users = UserService.get_users()
    return fsp.generate_response(users, session)


@router.get("/me", response_model=UserPublic)
def read_users_me(current_user: CurrentUser):
    return current_user


@router.patch("/me", response_model=UserPublic)
def update_users_me(data: ProfileUpdate, current_user: CurrentUser, us: UserServiceDep):
    """Update the signed-in user's profile."""
    if not data.name.strip():
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    return us.update_name(current_user, data.name)


@router.put("/me/email", response_model=Token)
def change_my_email(data: EmailChange, current_user: CurrentUser, us: UserServiceDep):
    """Change the sign-in email. Tokens name the email, so a new pair is returned
    and tokens issued for the old address stop working."""
    _check_current_password(current_user, data.current_password)
    email = data.email.strip()
    if email != current_user.email:
        if us.get_user_by_email(email):
            raise HTTPException(status_code=409, detail="Email already registered")
        us.update_email(current_user, email)
    return issue_tokens(current_user)


@router.put("/me/password", status_code=204)
def change_my_password(
    data: PasswordChange, current_user: CurrentUser, us: UserServiceDep
):
    """Change the signed-in user's password."""
    _check_current_password(current_user, data.current_password)
    us.update_password(current_user, data.new_password)
    return Response(status_code=204)


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
