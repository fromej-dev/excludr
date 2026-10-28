"""skip title/abstract: importbatch.title_abstract_screened, article flag

Revision ID: c4f8a2d6e1b9
Revises: b3e7f1a9c2d4
Create Date: 2026-10-28 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f8a2d6e1b9"
down_revision: str | Sequence[str] | None = "b3e7f1a9c2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("importbatch") as batch_op:
        batch_op.add_column(
            sa.Column(
                "title_abstract_screened",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
    with op.batch_alter_table("article") as batch_op:
        batch_op.add_column(
            sa.Column(
                "title_abstract_skipped",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("article") as batch_op:
        batch_op.drop_column("title_abstract_skipped")
    with op.batch_alter_table("importbatch") as batch_op:
        batch_op.drop_column("title_abstract_screened")
