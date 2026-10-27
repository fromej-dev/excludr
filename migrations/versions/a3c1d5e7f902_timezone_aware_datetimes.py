"""make datetime columns timezone-aware

Revision ID: a3c1d5e7f902
Revises: 9bc80ee934e2
Create Date: 2026-10-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c1d5e7f902"
down_revision: str | Sequence[str] | None = "9bc80ee934e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, nullable)
DATETIME_COLUMNS: list[tuple[str, str, bool]] = [
    ("user", "created_at", True),
    ("user", "updated_at", True),
    ("project", "created_at", True),
    ("project", "updated_at", True),
    ("criterion", "created_at", True),
    ("criterion", "updated_at", True),
    ("screeningdecision", "created_at", True),
    ("article", "last_ai_check", True),
    ("article", "created_at", False),
    ("article", "updated_at", False),
]


def _alter(to_timezone: bool) -> None:
    """Convert datetime columns between ``timestamp`` and ``timestamptz``.

    Existing naive values are interpreted as UTC. SQLite has no timezone-aware
    column type (DateTime(timezone=True) is rendered identically), so it is a no-op.
    """
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    for table, column, nullable in DATETIME_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=not to_timezone),
            type_=sa.DateTime(timezone=to_timezone),
            existing_nullable=nullable,
            postgresql_using=f"\"{column}\" AT TIME ZONE 'UTC'",
        )


def upgrade() -> None:
    """Upgrade schema."""
    _alter(to_timezone=True)


def downgrade() -> None:
    """Downgrade schema."""
    _alter(to_timezone=False)
