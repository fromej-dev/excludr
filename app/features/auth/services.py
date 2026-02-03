from datetime import datetime, timezone, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from passlib.context import CryptContext
from starlette import status

from app.core.config import get_settings
from .schemas import TokenData
from ..users.models import User
from ..users.services import UserServiceDep

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/token")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )
    return encoded_jwt


def verify_password(plain_password, user: User):
    return pwd_context.verify(plain_password, user.hashed_password)


def verify_token_and_get_user(token: str, us: UserServiceDep) -> User | None:
    """
    Verify JWT token and return the user.
    Returns None if token is invalid or user not found.
    This function can be used by both HTTP and WebSocket endpoints.
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        username = payload.get("sub")
        if username is None:
            return None
        token_data = TokenData(username=username)
    except InvalidTokenError:
        return None
    user = us.get_user_by_email(token_data.username)
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
