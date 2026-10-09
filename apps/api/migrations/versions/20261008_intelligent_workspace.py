"""Add project objectives, structured memory, personalization and focus sessions."""
from alembic import op
import sqlalchemy as sa

revision = "20261008_workspace"
down_revision = "20261008_worker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE project_status ADD VALUE IF NOT EXISTS 'planning'")
    op.execute("ALTER TYPE project_status ADD VALUE IF NOT EXISTS 'blocked'")
    op.execute("ALTER TYPE activity_type ADD VALUE IF NOT EXISTS 'memory_changed'")
    op.execute("ALTER TYPE activity_type ADD VALUE IF NOT EXISTS 'focus_updated'")
    op.add_column("projects", sa.Column("objective", sa.Text(), nullable=True))
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("memory_type", sa.String(24), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(240), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_user_project_type", "memories", ["user_id", "project_id", "memory_type", "archived"])
    op.create_table(
        "environment_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("surface", sa.String(60), nullable=False),
        sa.Column("item", sa.String(80), nullable=False),
        sa.Column("visibility", sa.String(16), server_default="visible", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.String(24), server_default="explicit", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "surface", "item", name="uq_environment_preference_item"),
    )
    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("objective", sa.String(500), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("context_snapshot", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_focus_sessions_user_status", "focus_sessions", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_focus_sessions_user_status", table_name="focus_sessions")
    op.drop_table("focus_sessions")
    op.drop_table("environment_preferences")
    op.drop_index("ix_memories_user_project_type", table_name="memories")
    op.drop_table("memories")
    op.drop_column("projects", "objective")
