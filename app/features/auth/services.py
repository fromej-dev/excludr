from datetime import datetime, timezone, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from app.core.security import verify_password as _verify_password
from starlette import status

from app.core.config import get_settings
from .schemas import Token, TokenData
from ..users.models import User
from ..users.services import UserServiceDep

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/token")


ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _create_token(data: dict, token_type: str, expires_delta: timedelta) -> str:
    """Encode a signed JWT carrying a ``typ`` claim that distinguishes its purpose."""
    to_encode = data.copy()
    to_encode.update(
        {"exp": datetime.now(timezone.utc) + expires_delta, "typ": token_type}
    )
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a short-lived access token."""
    return _create_token(
        data,
        ACCESS_TOKEN_TYPE,
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a long-lived refresh token (only accepted by ``/auth/refresh``)."""
    return _create_token(
        data,
        REFRESH_TOKEN_TYPE,
        expires_delta or timedelta(days=settings.refresh_token_expire_days),
    )


def issue_tokens(user: User) -> Token:
    """A fresh access/refresh token pair for ``user`` (tokens identify it by email)."""
    data = {"sub": user.email}
    return Token(
        access_token=create_access_token(data=data),
        refresh_token=create_refresh_token(data=data),
        token_type="bearer",
    )


def verify_password(plain_password, user: User):
    return _verify_password(plain_password, user.hashed_password)


def verify_token_and_get_user(
    token: str, us: UserServiceDep, token_type: str = ACCESS_TOKEN_TYPE
) -> User | None:
    """
    Verify a JWT of the given type and return the (active) user.
    Returns None if the token is invalid, of the wrong type, expired, or the user
    is missing or inactive.
    This function can be used by both HTTP and WebSocket endpoints.
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        if payload.get("typ") != token_type:
            return None
        username = payload.get("sub")
        if username is None:
            return None
        token_data = TokenData(username=username)
    except InvalidTokenError:
        return None
    user = us.get_user_by_email(token_data.username)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], us: UserServiceDep):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = verify_token_and_get_user(token, us)
    if user is None:
        raise credentials_exception
    return user


def get_current_admin_user(user: Annotated[User, Depends(get_current_user)]):
    admin_exception = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not user.is_superuser:
        raise admin_exception
    return user
