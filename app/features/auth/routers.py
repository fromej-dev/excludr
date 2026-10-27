from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import get_settings
from app.core.rate_limit import login_rate_limiter
from app.features.users.services import UserServiceDep
from .services import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    verify_password,
    verify_token_and_get_user,
)
from .schemas import RefreshRequest, Token
from ..users.models import User, UserCreate, UserPublic

router = APIRouter(tags=["Auth"], prefix="/auth")


def _issue_tokens(user: User) -> Token:
    data = {"sub": user.email}
    return Token(
        access_token=create_access_token(data=data),
        refresh_token=create_refresh_token(data=data),
        token_type="bearer",
    )


def _rate_limit_key(request: Request, email: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}|{email.strip().lower()}"


@router.post("/token", response_model=Token)
def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    us: UserServiceDep,
):
    settings = get_settings()
    key = _rate_limit_key(request, form_data.username)
    window = settings.login_rate_limit_window_seconds
    if login_rate_limiter.is_limited(key, settings.login_rate_limit_attempts, window):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(login_rate_limiter.retry_after(key, window))},
        )

    user = us.get_user_by_email(form_data.username)
    if not user or not verify_password(form_data.password, user):
        login_rate_limiter.record(key, window)
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    login_rate_limiter.clear(key)
    return _issue_tokens(user)


@router.post("/refresh", response_model=Token)
def refresh(body: RefreshRequest, us: UserServiceDep):
    """Exchange a valid refresh token for a new access/refresh token pair."""
    user = verify_token_and_get_user(
        body.refresh_token, us, token_type=REFRESH_TOKEN_TYPE
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return _issue_tokens(user)


@router.post("/register", response_model=UserPublic, status_code=201)
def register(
    data: UserCreate,
    us: UserServiceDep,
):
    if us.get_user_by_email(data.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    return us.create_user(data)
