"""add_criteria_screening_and_article_status

Revision ID: f589762b3834
Revises: 60aa2496c42f
Create Date: 2026-01-16 09:53:54.252482

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f589762b3834"
down_revision: Union[str, Sequence[str], None] = "60aa2496c42f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create enum types first using raw SQL (PostgreSQL specific)
    op.execute("CREATE TYPE criteriontype AS ENUM ('inclusion', 'exclusion')")
    op.execute(
        "CREATE TYPE screeningstage AS ENUM ('title_abstract', 'full_text', 'completed')"
    )
    op.execute(
        "CREATE TYPE screeningdecisiontype AS ENUM ('include', 'exclude', 'uncertain')"
    )
    op.execute("CREATE TYPE decisionsource AS ENUM ('ai_agent', 'human')")
    op.execute(
        "CREATE TYPE articlestatus AS ENUM "
        "('imported', 'screening', 'awaiting_full_text', 'full_text_retrieved', 'included', 'excluded')"
    )
    op.execute("CREATE TYPE finaldecision AS ENUM ('pending', 'included', 'excluded')")

    # Create criterion table
    op.create_table(
        "criterion",
        sa.Column(
            "type",
            postgresql.ENUM(name="criteriontype", create_type=False),
            nullable=False,
        ),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False
        ),
        sa.Column(
            "rationale", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_criterion_is_active"), "criterion", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_criterion_project_id"), "criterion", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_criterion_type"), "criterion", ["type"], unique=False)

    # Create screeningdecision table
    op.create_table(
        "screeningdecision",
        sa.Column(
            "stage",
            postgresql.ENUM(name="screeningstage", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "decision",
            postgresql.ENUM(name="screeningdecisiontype", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "source",
            postgresql.ENUM(name="decisionsource", create_type=False),
            nullable=False,
        ),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column(
            "reasoning", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True
        ),
        sa.Column(
            "primary_exclusion_reason",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=True,
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column(
            "criteria_evaluations", postgresql.JSON(astext_type=Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_screeningdecision_article_id"),
        "screeningdecision",
        ["article_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screeningdecision_decision"),
        "screeningdecision",
        ["decision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screeningdecision_reviewer_id"),
        "screeningdecision",
        ["reviewer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screeningdecision_source"),
        "screeningdecision",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screeningdecision_stage"), "screeningdecision", ["stage"], unique=False
    )

    # Add columns to article table
    op.add_column(
        "article",
        sa.Column(
            "status",
            postgresql.ENUM(name="articlestatus", create_type=False),
            nullable=False,
            server_default="imported",
        ),
    )
    op.add_column(
        "article",
        sa.Column(
            "current_stage",
            postgresql.ENUM(name="screeningstage", create_type=False),
            nullable=False,
            server_default="title_abstract",
        ),
    )
    op.add_column(
        "article",
        sa.Column(
            "final_decision",
            postgresql.ENUM(name="finaldecision", create_type=False),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_index(
        op.f("ix_article_current_stage"), "article", ["current_stage"], unique=False
    )
    op.create_index(
        op.f("ix_article_final_decision"), "article", ["final_decision"], unique=False
    )
    op.create_index(op.f("ix_article_status"), "article", ["status"], unique=False)

    # Add column to project table
    op.add_column(
        "project",
        sa.Column(
            "review_question",
            sqlmodel.sql.sqltypes.AutoString(length=1000),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop project column
    op.drop_column("project", "review_question")

    # Drop article columns and indexes
    op.drop_index(op.f("ix_article_status"), table_name="article")
    op.drop_index(op.f("ix_article_final_decision"), table_name="article")
    op.drop_index(op.f("ix_article_current_stage"), table_name="article")
    op.drop_column("article", "final_decision")
    op.drop_column("article", "current_stage")
    op.drop_column("article", "status")

    # Drop screeningdecision table
    op.drop_index(op.f("ix_screeningdecision_stage"), table_name="screeningdecision")
    op.drop_index(op.f("ix_screeningdecision_source"), table_name="screeningdecision")
    op.drop_index(
        op.f("ix_screeningdecision_reviewer_id"), table_name="screeningdecision"
    )
    op.drop_index(op.f("ix_screeningdecision_decision"), table_name="screeningdecision")
    op.drop_index(
        op.f("ix_screeningdecision_article_id"), table_name="screeningdecision"
    )
    op.drop_table("screeningdecision")

    # Drop criterion table
    op.drop_index(op.f("ix_criterion_type"), table_name="criterion")
    op.drop_index(op.f("ix_criterion_project_id"), table_name="criterion")
    op.drop_index(op.f("ix_criterion_is_active"), table_name="criterion")
    op.drop_table("criterion")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS articlestatus")
    op.execute("DROP TYPE IF EXISTS finaldecision")
    op.execute("DROP TYPE IF EXISTS screeningstage")
    op.execute("DROP TYPE IF EXISTS criteriontype")
    op.execute("DROP TYPE IF EXISTS screeningdecisiontype")
    op.execute("DROP TYPE IF EXISTS decisionsource")
