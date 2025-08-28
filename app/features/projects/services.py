from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, select

from .models import Project, ProjectCreate
from ..users.models import User
from ...core.database import SessionDep


class ProjectService:
    """Service class for managing Project-related operations."""

    def __init__(self, session: Session):
        """Initialize ProjectService with database session.

        Args:
            session (Session): SQLModel database session
        """
        self.session = session

    @staticmethod
    def get_projects():
        """Get select statement for all projects.

        Returns:
            Select statement for querying all projects
        """
        return select(Project)

    def get_project_by_id(self, project_id: int):
        """Get project by its ID.

        Args:
            project_id (int): ID of the project to retrieve

        Returns:
            Project: Project object if found, None otherwise
        """
        return self.session.exec(
            select(Project).where(Project.id == project_id)
        ).first()

    @staticmethod
    def get_projects_of_user(user: User):
        """Get select statement for all projects owned by a user.

        Args:
            user (User): User whose projects to retrieve

        Returns:
            Select statement for querying user's projects
        """
        return select(Project).where(Project.owner_id == user.id)

    def create_project(self, data: ProjectCreate, user: User):
        """Create a new project.

        Args:
            data (ProjectCreate): Project creation data
            user (User): Owner of the project

        Returns:
            Project: Created project object
        """
        project = Project(**data.model_dump())
        project.owner_id = user.id
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project


def get_project_service(session: SessionDep):
    """Dependency injection function to get ProjectService instance.

    Args:
        session (SessionDep): Database session dependency

    Returns:
        ProjectService: Instantiated ProjectService
    """
    return ProjectService(session=session)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
