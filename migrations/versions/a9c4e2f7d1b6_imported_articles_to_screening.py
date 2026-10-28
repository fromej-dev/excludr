"""move articles stuck in 'imported' to title/abstract screening

Imports used to leave new articles in status ``imported`` until an explicit
``POST .../articles/start-screening`` call, which the UI never made. Imports now
create articles directly in ``screening``; this data migration releases the
articles created before that change.

Revision ID: a9c4e2f7d1b6
Revises: f2b8d4e6a1c3
Create Date: 2026-10-28 09:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c4e2f7d1b6"
down_revision: str | Sequence[str] | None = "f2b8d4e6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Move every ``imported`` article to ``screening`` at title/abstract."""
    op.execute(
        "UPDATE article SET status = 'screening', current_stage = 'title_abstract' "
        "WHERE status = 'imported'"
    )


def downgrade() -> None:
    """No-op: the moved articles cannot be told apart from ones already screening.

    Putting them back in ``imported`` would also hide them from the screening
    queue again, so the data change is intentionally kept.
    """
