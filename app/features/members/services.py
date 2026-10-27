from typing import Annotated, Optional

from fastapi import Depends
from sqlmodel import Session, func, select

from app.core.database import SessionDep
from app.features.projects.models import Project, ProjectMember, ProjectRole
from app.features.users.models import User


class MemberError(Exception):
    """Domain error carrying the HTTP status the router should return."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class MemberService:
    """Manage project memberships."""

    def __init__(self, session: Session):
        self.session = session

    def list_members(self, project_id: int) -> list[tuple[ProjectMember, User]]:
        """Members with their users, owner first then by join order."""
        rows = self.session.exec(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.id)
        ).all()
        return sorted(rows, key=lambda r: r[0].role != ProjectRole.owner)

    def get_member(self, project_id: int, user_id: int) -> Optional[ProjectMember]:
        return self.session.exec(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        ).first()

    def add_member(
        self, project: Project, email: str, role: ProjectRole
    ) -> tuple[ProjectMember, User]:
        """Add the user with ``email`` to the project.

        Raises:
            MemberError: 422 for the owner role, 404 for an unknown user, 409 if
                the user is already a member (or is the owner).
        """
        if role == ProjectRole.owner:
            raise MemberError(422, "A project has exactly one owner")
        user = self.session.exec(
            select(User).where(func.lower(User.email) == email.strip().lower())
        ).first()
        if user is None:
            raise MemberError(404, "User not found")
        if user.id == project.owner_id or self.get_member(project.id, user.id):
            raise MemberError(409, "User is already a member of this project")
        member = ProjectMember(project_id=project.id, user_id=user.id, role=role)
        self.session.add(member)
        self.session.commit()
        self.session.refresh(member)
        return member, user

    def change_role(
        self, project: Project, user_id: int, role: ProjectRole
    ) -> tuple[ProjectMember, User, ProjectRole]:
        """Change a member's role; returns (member, user, previous role)."""
        if role == ProjectRole.owner:
            raise MemberError(422, "A project has exactly one owner")
        member = self._get_non_owner(project, user_id)
        previous = member.role
        member.role = role
        self.session.add(member)
        self.session.commit()
        self.session.refresh(member)
        return member, self.session.get(User, user_id), previous

    def remove_member(self, project: Project, user_id: int) -> ProjectMember:
        """Remove a non-owner member from the project."""
        member = self._get_non_owner(project, user_id)
        self.session.delete(member)
        self.session.commit()
        return member

    def _get_non_owner(self, project: Project, user_id: int) -> ProjectMember:
        if user_id == project.owner_id:
            raise MemberError(400, "The project owner cannot be changed or removed")
        member = self.get_member(project.id, user_id)
        if member is None:
            raise MemberError(404, "Member not found")
        return member


def get_member_service(session: SessionDep) -> MemberService:
    return MemberService(session=session)


MemberServiceDep = Annotated[MemberService, Depends(get_member_service)]
