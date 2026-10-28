"""ai usage: tokens and estimated cost of every AI run

Revision ID: c4d8a2f6e1b9
Revises: c4f8a2d6e1b9
Create Date: 2026-10-28 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d8a2f6e1b9"
down_revision: str | Sequence[str] | None = "c4f8a2d6e1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXED = (
    "created_at",
    "activity",
    "stage",
    "model_name",
    "project_id",
    "article_id",
    "user_id",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "aiusage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("decision_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["screeningdecision.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in INDEXED:
        op.create_index(op.f(f"ix_aiusage_{column}"), "aiusage", [column])


def downgrade() -> None:
    """Downgrade schema."""
    for column in reversed(INDEXED):
        op.drop_index(op.f(f"ix_aiusage_{column}"), table_name="aiusage")
    op.drop_table("aiusage")
