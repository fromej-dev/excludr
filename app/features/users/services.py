from typing import Annotated

from fastapi import Depends
from passlib.context import CryptContext
from sqlmodel import select, Session

from .models import User, UserCreate
from ...core.database import SessionDep


class UserService:
    """Service class for managing User-related operations."""

    def __init__(self, session: Session):
        """Initialize UserService with database session.

        Args:
            session (Session): SQLModel database session
        """
        self.session = session

    @staticmethod
    def get_users():
        """Get select statement for all users.

        Returns:
            Select statement for querying all users
        """
        return select(User)

    def get_user_by_id(self, user_id: int):
        """Get user by their ID.

        Args:
            user_id (int): ID of the user to retrieve

        Returns:
            User: User object if found, None otherwise
        """
        return self.session.exec(select(User).where(User.id == user_id)).first()

    def get_user_by_email(self, email: str):
        """Get user by their email address.

        Args:
            email (str): Email address of the user to retrieve

        Returns:
            User: User object if found, None otherwise
        """
        return self.session.exec(select(User).where(User.email == email)).first()

    def create_user(self, data: UserCreate):
        """Create a new user.

        Args:
            data (UserCreate): User creation data including password

        Returns:
            User: Created user object
        """
        user = User(**data.model_dump())
        user.hashed_password = self.hash_password(data.password)
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    @staticmethod
    def hash_password(password: str):
        """Hash a password string.

        Args:
            password (str): Plain text password to hash

        Returns:
            str: Hashed password
        """
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)


def get_user_service(session: SessionDep):
    """Dependency injection function to get UserService instance.

    Args:
        session (SessionDep): Database session dependency

    Returns:
        UserService: Instantiated UserService
    """
    return UserService(session=session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
