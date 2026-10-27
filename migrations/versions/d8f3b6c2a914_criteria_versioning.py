"""add criterion.version and screeningdecision.criteria_snapshot

Revision ID: d8f3b6c2a914
Revises: c4d9a1e7b520
Create Date: 2026-10-27 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f3b6c2a914"
down_revision: str | Sequence[str] | None = "c4d9a1e7b520"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("criterion") as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), server_default="1", nullable=False)
        )
    with op.batch_alter_table("screeningdecision") as batch_op:
        batch_op.add_column(sa.Column("criteria_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("screeningdecision") as batch_op:
        batch_op.drop_column("criteria_snapshot")
    with op.batch_alter_table("criterion") as batch_op:
        batch_op.drop_column("version")
