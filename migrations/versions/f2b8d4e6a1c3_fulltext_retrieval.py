"""full-text retrieval provenance on articles

Revision ID: f2b8d4e6a1c3
Revises: e1a7c9d3b5f2
Create Date: 2026-10-27 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2b8d4e6a1c3"
down_revision: str | Sequence[str] | None = "e1a7c9d3b5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("article") as batch_op:
        batch_op.add_column(sa.Column("full_text_source", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("full_text_retrieval_error", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "full_text_attempted_at", sa.DateTime(timezone=True), nullable=True
            )
        )
    # Existing full texts were all uploaded by hand.
    op.execute(
        "UPDATE article SET full_text_source = 'manual' WHERE full_text_retrieved"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("article") as batch_op:
        batch_op.drop_column("full_text_attempted_at")
        batch_op.drop_column("full_text_retrieval_error")
        batch_op.drop_column("full_text_source")
