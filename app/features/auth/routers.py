from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.features.users.services import UserServiceDep
from .services import create_access_token, verify_password
from .schemas import Token
from ..users.models import UserCreate, UserRead

router = APIRouter(tags=["Auth"], prefix="/auth")


@router.post("/token")
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    us: UserServiceDep,
):
    user = us.get_user_by_email(form_data.username)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    if not verify_password(form_data.password, user):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.email})
    return Token(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=UserRead, status_code=201)
def register(
    data: UserCreate,
    us: UserServiceDep,
):
    if us.get_user_by_email(data.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    return us.create_user(data)
