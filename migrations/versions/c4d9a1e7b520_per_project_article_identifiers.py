"""make article doi/pmid/pmcid unique per project

Revision ID: c4d9a1e7b520
Revises: b7e2f4a6c813
Create Date: 2026-10-27 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d9a1e7b520"
down_revision: str | Sequence[str] | None = "b7e2f4a6c813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDENTIFIER_COLUMNS = ("doi", "pmid", "pmcid")


def upgrade() -> None:
    """Replace global unique indexes with plain indexes + per-project constraints."""
    for column in IDENTIFIER_COLUMNS:
        # The original migration created these as UNIQUE indexes (ix_article_<col>).
        op.drop_index(op.f(f"ix_article_{column}"), table_name="article")
        op.create_index(op.f(f"ix_article_{column}"), "article", [column], unique=False)
    with op.batch_alter_table("article") as batch_op:
        for column in IDENTIFIER_COLUMNS:
            batch_op.create_unique_constraint(
                f"uq_article_project_{column}", ["project_id", column]
            )


def downgrade() -> None:
    """Restore global uniqueness (fails if the same identifier exists in 2 projects)."""
    with op.batch_alter_table("article") as batch_op:
        for column in IDENTIFIER_COLUMNS:
            batch_op.drop_constraint(f"uq_article_project_{column}", type_="unique")
    for column in IDENTIFIER_COLUMNS:
        op.drop_index(op.f(f"ix_article_{column}"), table_name="article")
        op.create_index(op.f(f"ix_article_{column}"), "article", [column], unique=True)
