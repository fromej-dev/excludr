"""Admin area API (superusers only)."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.database import SessionDep
from app.features.ai_usage import services as ai_usage
from app.features.ai_usage.models import AIActivity
from app.features.auth.services import get_current_admin_user
from app.features.billing import services as billing
from app.features.billing.models import ProjectPlan
from app.features.projects.models import Project
from app.features.screening.models import ScreeningStage
from app.features.users.models import User
from . import services as admin
from .schemas import (
    AdminPayment,
    AdminProject,
    AdminUser,
    AdminUserDetail,
    AIUsageReport,
    GrantRequest,
    Overview,
    Page,
    PlanUpdate,
    UserUpdate,
)

router = APIRouter(tags=["Admin"], prefix="/admin")

AdminDep = Annotated[User, Depends(get_current_admin_user)]
PageQuery = Annotated[int, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]


def _project(session: SessionDep, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/overview", response_model=Overview)
def get_overview(_: AdminDep, session: SessionDep):
    return admin.overview(session)


@router.get("/users", response_model=Page[AdminUser])
def get_users(
    _: AdminDep,
    session: SessionDep,
    search: Optional[str] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
):
    return admin.list_users(session, search, page, page_size)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user(user_id: int, _: AdminDep, session: SessionDep):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return admin.get_user_detail(session, user)


@router.patch("/users/{user_id}", response_model=AdminUserDetail)
def update_user(user_id: int, data: UserUpdate, current: AdminDep, session: SessionDep):
    """Deactivate/reactivate an account (blocks login and existing tokens) or
    change its admin rights."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        admin.update_user(session, current, user, data.is_active, data.is_superuser)
    except admin.SelfChangeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return admin.get_user_detail(session, user)


@router.get("/projects", response_model=Page[AdminProject])
def get_projects(
    _: AdminDep,
    session: SessionDep,
    search: Optional[str] = None,
    state: Optional[Literal["free", "active", "expiring", "expired"]] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
):
    return admin.list_projects(session, search, state, page, page_size)


@router.post("/projects/{project_id}/plan", response_model=ProjectPlan)
def grant_pass(
    project_id: int, data: GrantRequest, current: AdminDep, session: SessionDep
):
    """Give a project a new pass starting today, without Stripe (replaces any
    current pass): invoice or PO payments, pilots, discounts."""
    project = _project(session, project_id)
    try:
        return billing.grant_pass(
            session, project, current, data.tier, data.fulltext_limit, data.days
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch("/projects/{project_id}/plan", response_model=ProjectPlan)
def update_pass(
    project_id: int, data: PlanUpdate, current: AdminDep, session: SessionDep
):
    """Change a pass's limit or end date (extend it, or end it early)."""
    project = _project(session, project_id)
    try:
        return billing.update_pass(
            session, project, current, data.fulltext_limit, data.expires_at
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/payments", response_model=Page[AdminPayment])
def get_payments(
    _: AdminDep,
    session: SessionDep,
    status: Optional[Literal["paid", "partially_refunded", "refunded"]] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
):
    return admin.list_payments(session, status, page, page_size)


def _usage_filters(
    start: Annotated[Optional[date], Query(description="First day (UTC)")] = None,
    end: Annotated[
        Optional[date], Query(description="Last day (UTC), inclusive")
    ] = None,
    project_id: Optional[int] = None,
    user_id: Annotated[Optional[int], Query(description="Who started the runs")] = None,
    activity: Optional[AIActivity] = None,
    stage: Optional[ScreeningStage] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    def midnight(day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=timezone.utc)

    return {
        "start": midnight(start) if start else None,
        "end": midnight(end + timedelta(days=1)) if end else None,
        "project_id": project_id,
        "user_id": user_id,
        "activity": activity.value if activity else None,
        "stage": stage.value if stage else None,
        "model": model,
    }


UsageFilters = Annotated[dict[str, Any], Depends(_usage_filters)]
GroupByQuery = Annotated[ai_usage.GroupBy, Query()]


@router.get("/ai-usage", response_model=AIUsageReport)
def get_ai_usage(
    _: AdminDep,
    session: SessionDep,
    filters: UsageFilters,
    group_by: GroupByQuery = "project",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    """AI token usage and estimated cost (USD), in total and per group.

    Every AI run counts, failed ones included. Groups are ordered by tokens used
    (by date for ``day`` and ``month``); ``group_count`` is the number before
    ``limit``.
    """
    return ai_usage.report(session, group_by, limit, **filters)


@router.get("/ai-usage/export")
def export_ai_usage(
    _: AdminDep,
    session: SessionDep,
    filters: UsageFilters,
    group_by: Annotated[
        Optional[ai_usage.GroupBy], Query(description="Omit for one line per AI run")
    ] = None,
):
    """Download AI usage as CSV: every run, or the totals per group."""
    if group_by:
        body = ai_usage.iter_groups_csv(session, group_by, **filters)
        name = f"ai-usage-by-{group_by}.csv"
    else:
        body = ai_usage.iter_runs_csv(session, **filters)
        name = "ai-usage-runs.csv"
    return StreamingResponse(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
