"""Project-level authorization shared by all routers.

Roles are ordered ``viewer < reviewer < owner``:

* viewer: read everything that is not blinded
* reviewer: viewer + create their own human decisions + run AI screening
* owner: everything else (edit project, criteria, imports, uploads, members, ...)

Usage in a route::

    def handler(access: OwnerAccess): ...
    access.project, access.user, access.role
"""

from dataclasses import dataclass
from typing import Annotated, Callable, Optional

from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.core.database import SessionDep
from app.features.auth.services import get_current_user
from app.features.users.models import User
from .models import Project, ProjectMember, ProjectRole

ROLE_RANK: dict[ProjectRole, int] = {
    ProjectRole.viewer: 1,
    ProjectRole.reviewer: 2,
    ProjectRole.owner: 3,
}


@dataclass(frozen=True)
class ProjectAccess:
    """A project together with the requesting user and their role in it."""

    project: Project
    user: User
    role: ProjectRole


def get_user_role(
    session: Session, project: Project, user: User
) -> Optional[ProjectRole]:
    """Return the user's role in the project, or None if they are not a member.

    ``Project.owner_id`` is authoritative for ownership, so an owner keeps full
    access even if their membership row is missing.
    """
    if project.owner_id == user.id:
        return ProjectRole.owner
    return session.exec(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
    ).first()


def has_role(role: Optional[ProjectRole], min_role: ProjectRole) -> bool:
    """True if ``role`` is at least ``min_role``."""
    return role is not None and ROLE_RANK[role] >= ROLE_RANK[min_role]


def require_project_role(min_role: ProjectRole) -> Callable[..., ProjectAccess]:
    """Build a dependency that enforces ``min_role`` on the ``project_id`` path param.

    Raises:
        HTTPException: 404 if the project does not exist; 403 if the user is not a
            member (legacy message kept for compatibility) or their role is too low.
    """

    def dependency(
        project_id: int,
        current_user: Annotated[User, Depends(get_current_user)],
        session: SessionDep,
    ) -> ProjectAccess:
        project = session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        role = get_user_role(session, project, current_user)
        if role is None:
            raise HTTPException(
                status_code=403, detail="You are not the owner of the project"
            )
        if not has_role(role, min_role):
            raise HTTPException(
                status_code=403,
                detail=f"This action requires the '{min_role.value}' role",
            )
        return ProjectAccess(project=project, user=current_user, role=role)

    return dependency


ViewerAccess = Annotated[
    ProjectAccess, Depends(require_project_role(ProjectRole.viewer))
]
ReviewerAccess = Annotated[
    ProjectAccess, Depends(require_project_role(ProjectRole.reviewer))
]
OwnerAccess = Annotated[ProjectAccess, Depends(require_project_role(ProjectRole.owner))]
