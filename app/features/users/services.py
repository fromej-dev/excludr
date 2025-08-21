from typing import Annotated

from fastapi import Depends
from passlib.context import CryptContext
from sqlmodel import select

from .models import User, UserCreate
from ...core.database import SessionDep


class UserService:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def get_users():
        return select(User)

    def get_user_by_id(self, user_id: int):
        return self.session.exec(select(User).where(User.id == user_id)).first()

    def get_user_by_email(self, email: str):
        return self.session.exec(select(User).where(User.email == email)).first()

    def create_user(self, data: UserCreate):
        user = User(**data.model_dump())
        user.hashed_password = self.hash_password(data.password)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    @staticmethod
    def hash_password(password: str):
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)


def get_user_service(session: SessionDep):
    return UserService(session=session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
