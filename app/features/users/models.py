from sqlalchemy import func
from sqlmodel import SQLModel, Field


class UserBase(SQLModel):
    email: str = Field(index=True, unique=True)
    name: str = Field(index=True)


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    created_at: str = Field(sa_column_kwargs={"server_default": func.now()})
    updated_at: str = Field(sa_column_kwargs={"server_default": func.now()})


class User(UserRead, table=True):
    id: int = Field(primary_key=True)
    hashed_password: str = Field(max_length=1024)
