from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlanSource(str, Enum):
    stripe = "stripe"
    admin = "admin"


class ProjectPlan(SQLModel, table=True):
    """The review pass of a project. Projects without a row are on the free tier.

    An expired pass keeps its row: the project then becomes read-only.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(
        foreign_key="project.id", unique=True, index=True, ondelete="CASCADE"
    )
    tier: str = Field(max_length=20, description="pass_250 | pass_1000 | custom")
    fulltext_limit: int = Field(description="Articles the AI may screen at full text")
    activated_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    expires_at: datetime = Field(sa_type=DateTime(timezone=True), nullable=False)
    source: str = Field(max_length=20, description="stripe | admin (PlanSource)")
    stripe_checkout_session_id: Optional[str] = Field(default=None, max_length=255)
    amount_paid_cents: int = Field(default=0)
    granted_by: Optional[int] = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_type=DateTime(timezone=True), nullable=False
    )


class StripeEvent(SQLModel, table=True):
    """Stripe webhook events already processed (Stripe may deliver one twice)."""

    id: str = Field(primary_key=True, max_length=255)
    type: str = Field(max_length=100)
    received_at: datetime = Field(
        default_factory=_utcnow, sa_type=DateTime(timezone=True), nullable=False
    )


class PaymentStatus(str, Enum):
    paid = "paid"
    partially_refunded = "partially_refunded"
    refunded = "refunded"


class Payment(SQLModel, table=True):
    """One completed Stripe Checkout payment for a review pass.

    ``plan_before`` snapshots the project's plan before this payment was applied
    (null: the project had none), so a full refund can undo exactly this payment.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(
        default=None, foreign_key="project.id", index=True, ondelete="SET NULL"
    )
    project_name: str = Field(max_length=100, description="Kept if the project goes")
    user_id: Optional[int] = Field(
        default=None, foreign_key="user.id", index=True, ondelete="SET NULL"
    )
    stripe_checkout_session_id: str = Field(max_length=255, unique=True)
    stripe_payment_intent: Optional[str] = Field(
        default=None, max_length=255, index=True
    )
    tier: str = Field(max_length=20)
    kind: str = Field(max_length=20, description="new | renewal | upgrade")
    amount_cents: int
    refunded_cents: int = Field(default=0)
    currency: str = Field(max_length=3)
    status: str = Field(
        default=PaymentStatus.paid, max_length=20, description="PaymentStatus"
    )
    plan_before: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=_utcnow, sa_type=DateTime(timezone=True), nullable=False
    )
