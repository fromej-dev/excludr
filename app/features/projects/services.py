from typing import Annotated

from fastapi import Depends
from sqlalchemy import or_
from sqlmodel import Session, delete, select

from .models import (
    ImportBatch,
    Project,
    ProjectCreate,
    ProjectMember,
    ProjectUpdate,
)
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
        """Get select statement for all projects a user is a member of.

        Includes owned projects even if the membership row is missing.

        Args:
            user (User): User whose projects to retrieve

        Returns:
            Select statement for querying user's projects
        """
        member_of = select(ProjectMember.project_id).where(
            ProjectMember.user_id == user.id
        )
        return select(Project).where(
            or_(Project.owner_id == user.id, Project.id.in_(member_of))
        )

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
        # The owner's ProjectMember row is created by an after_insert listener
        # on Project (see models.py) so every creation path gets one.
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def update_project(self, project: Project, data: ProjectUpdate):
        """Update an existing project.

        Args:
            project (Project): Project to update
            data (ProjectUpdate): Project update data

        Returns:
            Project: Updated project object
        """
        project.sqlmodel_update(
            data.model_dump(
                exclude_unset=True, exclude_defaults=True, exclude_none=True
            )
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def delete_project(self, project: Project):
        """Delete an existing project.

        Args:
            project (Project): Project to delete

        Returns:
        """
        # Child rows without an ORM cascade (also covered by DB-level ON DELETE
        # CASCADE; done explicitly so it works on databases without FK enforcement).
        from app.features.audit.models import AuditEvent
        from app.features.billing.models import ProjectPlan

        for model in (ProjectMember, ImportBatch, AuditEvent, ProjectPlan):
            self.session.exec(delete(model).where(model.project_id == project.id))
        self.session.delete(project)
        self.session.commit()
        return


def get_project_service(session: SessionDep) -> ProjectService:
    """Dependency injection function to get ProjectService instance.

    Args:
        session (SessionDep): Database session dependency

    Returns:
        ProjectService: Instantiated ProjectService
    """
    return ProjectService(session=session)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
