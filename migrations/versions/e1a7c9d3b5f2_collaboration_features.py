"""project members, dual screening, import batches and audit trail

Revision ID: e1a7c9d3b5f2
Revises: d8f3b6c2a914
Create Date: 2026-10-27 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e1a7c9d3b5f2"
down_revision: str | Sequence[str] | None = "d8f3b6c2a914"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE TYPE projectrole AS ENUM ('owner', 'reviewer', 'viewer')")

    with op.batch_alter_table("project") as batch_op:
        batch_op.add_column(
            sa.Column(
                "required_reviewers",
                sa.Integer(),
                server_default="1",
                nullable=False,
            )
        )
    with op.batch_alter_table("screeningdecision") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_resolution",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )

    op.create_table(
        "projectmember",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="projectrole", create_type=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "user_id", name="uq_projectmember_project_user"
        ),
    )
    op.create_index(
        op.f("ix_projectmember_project_id"), "projectmember", ["project_id"]
    )
    op.create_index(op.f("ix_projectmember_user_id"), "projectmember", ["user_id"])
    op.create_index(op.f("ix_projectmember_role"), "projectmember", ["role"])

    # Backfill: every existing project gets an owner membership for its owner.
    projectmember = sa.table(
        "projectmember",
        sa.column("project_id", sa.Integer),
        sa.column("user_id", sa.Integer),
        sa.column("role", postgresql.ENUM(name="projectrole", create_type=False)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    project = sa.table(
        "project", sa.column("id", sa.Integer), sa.column("owner_id", sa.Integer)
    )
    op.execute(
        projectmember.insert().from_select(
            ["project_id", "user_id", "role", "created_at"],
            sa.select(
                project.c.id,
                project.c.owner_id,
                sa.cast(sa.literal("owner"), projectmember.c.role.type),
                sa.func.now(),
            ),
        )
    )

    op.create_table(
        "importbatch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("records_found", sa.Integer(), nullable=False),
        sa.Column("imported", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_importbatch_project_id"), "importbatch", ["project_id"])

    op.create_table(
        "auditevent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auditevent_project_id"), "auditevent", ["project_id"])
    op.create_index(op.f("ix_auditevent_user_id"), "auditevent", ["user_id"])
    op.create_index(op.f("ix_auditevent_action"), "auditevent", ["action"])
    op.create_index(op.f("ix_auditevent_entity_type"), "auditevent", ["entity_type"])
    op.create_index(op.f("ix_auditevent_created_at"), "auditevent", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_auditevent_created_at"), table_name="auditevent")
    op.drop_index(op.f("ix_auditevent_entity_type"), table_name="auditevent")
    op.drop_index(op.f("ix_auditevent_action"), table_name="auditevent")
    op.drop_index(op.f("ix_auditevent_user_id"), table_name="auditevent")
    op.drop_index(op.f("ix_auditevent_project_id"), table_name="auditevent")
    op.drop_table("auditevent")

    op.drop_index(op.f("ix_importbatch_project_id"), table_name="importbatch")
    op.drop_table("importbatch")

    op.drop_index(op.f("ix_projectmember_role"), table_name="projectmember")
    op.drop_index(op.f("ix_projectmember_user_id"), table_name="projectmember")
    op.drop_index(op.f("ix_projectmember_project_id"), table_name="projectmember")
    op.drop_table("projectmember")

    with op.batch_alter_table("screeningdecision") as batch_op:
        batch_op.drop_column("is_resolution")
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_column("required_reviewers")

    op.execute("DROP TYPE IF EXISTS projectrole")
