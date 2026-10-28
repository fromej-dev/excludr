"""payments: one row per Stripe Checkout payment

Revision ID: b3e7f1a9c2d4
Revises: a9d4c2e8f1b6
Create Date: 2026-10-28 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3e7f1a9c2d4"
down_revision: str | Sequence[str] | None = "a9d4c2e8f1b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "payment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("project_name", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_payment_intent", sa.String(length=255), nullable=True),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("refunded_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("plan_before", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_checkout_session_id"),
    )
    op.create_index(op.f("ix_payment_project_id"), "payment", ["project_id"])
    op.create_index(op.f("ix_payment_user_id"), "payment", ["user_id"])
    op.create_index(
        op.f("ix_payment_stripe_payment_intent"), "payment", ["stripe_payment_intent"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_payment_stripe_payment_intent"), table_name="payment")
    op.drop_index(op.f("ix_payment_user_id"), table_name="payment")
    op.drop_index(op.f("ix_payment_project_id"), table_name="payment")
    op.drop_table("payment")
