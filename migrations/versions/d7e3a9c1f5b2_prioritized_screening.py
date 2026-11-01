"""prioritized screening: project settings, article relevance, rankingrun

Revision ID: d7e3a9c1f5b2
Revises: c4d8a2f6e1b9
Create Date: 2026-11-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e3a9c1f5b2"
down_revision: str | Sequence[str] | None = "c4d8a2f6e1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(
            sa.Column(
                "prioritized_screening",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "stop_after_consecutive_excludes",
                sa.Integer(),
                server_default="100",
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "ranking_min_random", sa.Integer(), server_default="0", nullable=False
            )
        )
        batch_op.add_column(
            sa.Column(
                "prioritized_screening_enabled_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "stopping_rule_applied_at", sa.DateTime(timezone=True), nullable=True
            )
        )
    with op.batch_alter_table("article") as batch_op:
        batch_op.add_column(sa.Column("relevance_score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "not_screened_stopping_rule",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
    # SQLite cannot index NULLS LAST; there it is plain DESC.
    nulls_last = " NULLS LAST" if op.get_bind().dialect.name == "postgresql" else ""
    op.create_index(
        "ix_article_project_relevance",
        "article",
        ["project_id", sa.text(f"relevance_score DESC{nulls_last}")],
    )
    op.create_table(
        "rankingrun",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("triggered_by", sa.Integer(), nullable=True),
        sa.Column("labelled_includes", sa.Integer(), nullable=False),
        sa.Column("labelled_excludes", sa.Integer(), nullable=False),
        sa.Column("scored", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rankingrun_project_id"), "rankingrun", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_rankingrun_created_at"), "rankingrun", ["created_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_rankingrun_created_at"), table_name="rankingrun")
    op.drop_index(op.f("ix_rankingrun_project_id"), table_name="rankingrun")
    op.drop_table("rankingrun")
    op.drop_index("ix_article_project_relevance", table_name="article")
    with op.batch_alter_table("article") as batch_op:
        batch_op.drop_column("not_screened_stopping_rule")
        batch_op.drop_column("relevance_score")
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("stopping_rule_applied_at")
        batch_op.drop_column("prioritized_screening_enabled_at")
        batch_op.drop_column("ranking_min_random")
        batch_op.drop_column("stop_after_consecutive_excludes")
        batch_op.drop_column("prioritized_screening")
