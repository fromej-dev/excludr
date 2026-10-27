import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import SessionDep
from app.features.auth.services import get_current_admin_user
from app.features.projects.models import Project
from app.features.projects.permissions import OwnerAccessAnyState, ViewerAccess
from app.features.users.models import User
from . import services as billing
from . import stripe_client
from .models import ProjectPlan
from .schemas import (
    BillingStatus,
    CheckoutRequest,
    CheckoutResponse,
    GrantRequest,
    PublicPlans,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Billing"])


def _require_billing() -> None:
    if not billing.billing_enabled():
        raise HTTPException(status_code=404, detail="Billing is not enabled")


@router.get("/billing/plans", response_model=PublicPlans)
def get_plans():
    """Public plan limits and prices (used by the pricing page)."""
    return billing.public_plans()


@router.get("/projects/{project_id}/billing", response_model=BillingStatus)
def get_billing_status(access: ViewerAccess, session: SessionDep):
    """The project's plan, AI screening usage and the passes it can buy."""
    return billing.get_status(session, access.project)


@router.post("/projects/{project_id}/billing/checkout", response_model=CheckoutResponse)
async def start_checkout(
    data: CheckoutRequest, access: OwnerAccessAnyState, session: SessionDep
):
    """Start a Stripe Checkout payment for a review pass (owner only)."""
    _require_billing()
    if not get_settings().stripe_secret_key:
        raise HTTPException(status_code=503, detail="Payments are not configured")
    try:
        url = await billing.create_checkout(
            session, access.project, access.user, data.tier
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except stripe_client.StripeError as e:
        logger.error("Stripe checkout failed for project %s: %s", access.project.id, e)
        raise HTTPException(
            status_code=502, detail="Could not start the payment. Please try again."
        ) from e
    return {"url": url}


@router.post("/billing/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, session: SessionDep):
    """Receive Stripe events; only signed events are applied, each at most once."""
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Webhooks are not configured")
    payload = await request.body()
    try:
        event = stripe_client.verify_webhook(
            payload, request.headers.get("stripe-signature"), secret
        )
    except stripe_client.InvalidSignatureError as e:
        raise HTTPException(status_code=400, detail="Invalid signature") from e
    try:
        outcome = billing.handle_event(session, event)
    except IntegrityError:
        session.rollback()  # the same event arrived concurrently
        outcome = "duplicate"
    return {"received": True, "outcome": outcome}


@router.post("/billing/admin/projects/{project_id}/grant", response_model=ProjectPlan)
def grant_pass(
    project_id: int,
    data: GrantRequest,
    admin: Annotated[User, Depends(get_current_admin_user)],
    session: SessionDep,
):
    """Give a project a pass without Stripe (superusers only)."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return billing.grant_pass(
            session, project, admin, data.tier, data.fulltext_limit, data.days
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
