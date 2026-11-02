"""statistical stopping rule: project settings

Revision ID: e5b2d8f4a7c1
Revises: d7e3a9c1f5b2
Create Date: 2026-11-02 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b2d8f4a7c1"
down_revision: str | Sequence[str] | None = "d7e3a9c1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(
            sa.Column(
                "stopping_rule_type",
                sa.String(length=20),
                server_default="consecutive",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "recall_target", sa.Float(), server_default="0.95", nullable=False
            )
        )
        batch_op.add_column(
            sa.Column(
                "stopping_alpha", sa.Float(), server_default="0.05", nullable=False
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("stopping_alpha")
        batch_op.drop_column("recall_target")
        batch_op.drop_column("stopping_rule_type")
