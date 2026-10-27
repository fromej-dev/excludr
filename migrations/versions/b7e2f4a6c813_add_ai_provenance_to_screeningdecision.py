"""add model_name and prompt_version to screeningdecision

Revision ID: b7e2f4a6c813
Revises: a3c1d5e7f902
Create Date: 2026-10-27 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2f4a6c813"
down_revision: str | Sequence[str] | None = "a3c1d5e7f902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("screeningdecision") as batch_op:
        batch_op.add_column(
            sa.Column("model_name", sa.String(length=200), nullable=True)
        )
        batch_op.add_column(
            sa.Column("prompt_version", sa.String(length=50), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("screeningdecision") as batch_op:
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("model_name")
