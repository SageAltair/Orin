"""Persist task-focused conversations and link command history."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_conversations"
down_revision = "20261009_command_planning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("pending_question", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_user_updated", "conversations", ["user_id", "updated_at"])
    op.add_column("commands", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_commands_conversation_id_conversations", "commands", "conversations", ["conversation_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_commands_conversation_created", "commands", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_commands_conversation_created", table_name="commands")
    op.drop_constraint("fk_commands_conversation_id_conversations", "commands", type_="foreignkey")
    op.drop_column("commands", "conversation_id")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")
