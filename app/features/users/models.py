from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlmodel import SQLModel, Field, Relationship


class UserBase(SQLModel):
    email: str = Field(index=True, unique=True)
    name: str = Field(index=True)


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    created_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )
    updated_at: Optional[datetime] = Field(
        default=None, sa_column_kwargs={"server_default": func.now()}
    )


class User(UserRead, table=True):
    id: int = Field(primary_key=True)
    hashed_password: str = Field(max_length=1024)

    projects: list["Project"] = Relationship(back_populates="owner")  # noqa: F821
