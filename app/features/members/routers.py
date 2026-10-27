from fastapi import APIRouter, HTTPException

from app.core.database import SessionDep
from app.features.audit import services as audit
from app.features.projects.permissions import OwnerAccess, ViewerAccess
from app.features.users.models import User
from app.features.projects.models import ProjectMember
from .schemas import MemberAdd, MemberRead, MemberRoleUpdate
from .services import MemberError, MemberServiceDep

router = APIRouter(tags=["Members"], prefix="/projects/{project_id}/members")


def _read(member: ProjectMember, user: User) -> MemberRead:
    return MemberRead(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=member.role,
        created_at=member.created_at,
    )


def _raise(exc: MemberError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", response_model=list[MemberRead])
def list_members(access: ViewerAccess, ms: MemberServiceDep):
    """List the project's members (any member)."""
    return [_read(m, u) for m, u in ms.list_members(access.project.id)]


@router.post("", response_model=MemberRead, status_code=201)
def add_member(
    data: MemberAdd, access: OwnerAccess, ms: MemberServiceDep, session: SessionDep
):
    """Add an existing user to the project by email (owner only)."""
    try:
        member, user = ms.add_member(access.project, data.email, data.role)
    except MemberError as exc:
        raise _raise(exc) from exc
    audit.record_event(
        session,
        access.project.id,
        audit.MEMBER_ADDED,
        "member",
        user.id,
        access.user.id,
        {"email": user.email, "role": member.role.value},
    )
    return _read(member, user)


@router.patch("/{user_id}", response_model=MemberRead)
def change_member_role(
    user_id: int,
    data: MemberRoleUpdate,
    access: OwnerAccess,
    ms: MemberServiceDep,
    session: SessionDep,
):
    """Change a member's role (owner only; the owner's role is fixed)."""
    try:
        member, user, previous = ms.change_role(access.project, user_id, data.role)
    except MemberError as exc:
        raise _raise(exc) from exc
    audit.record_event(
        session,
        access.project.id,
        audit.MEMBER_ROLE_CHANGED,
        "member",
        user_id,
        access.user.id,
        {"from": previous.value, "to": member.role.value},
    )
    return _read(member, user)


@router.delete("/{user_id}", status_code=204)
def remove_member(
    user_id: int, access: OwnerAccess, ms: MemberServiceDep, session: SessionDep
):
    """Remove a member from the project (owner only; the owner cannot be removed)."""
    try:
        member = ms.remove_member(access.project, user_id)
    except MemberError as exc:
        raise _raise(exc) from exc
    audit.record_event(
        session,
        access.project.id,
        audit.MEMBER_REMOVED,
        "member",
        user_id,
        access.user.id,
        {"role": member.role.value},
    )
