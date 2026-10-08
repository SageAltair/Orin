"""Add action approval metadata and immutable execution audit records."""
from alembic import op
import sqlalchemy as sa


revision = "20261008_execution"
down_revision = "20261008_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("action_name", sa.String(length=80), nullable=True))
    op.add_column("approvals", sa.Column("action_payload", sa.JSON(), nullable=True))
    op.add_column("approvals", sa.Column("risk_level", sa.String(length=20), nullable=True))
    op.add_column("approvals", sa.Column("permission", sa.String(length=80), nullable=True))
    op.add_column("approvals", sa.Column("reversible", sa.Boolean(), nullable=True))
    op.create_table(
        "execution_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid(), nullable=False),
        sa.Column("action_name", sa.String(length=80), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("permission", sa.String(length=80), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("execution_status", sa.String(length=30), nullable=False),
        sa.Column("result_status", sa.String(length=30), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=True),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["command_id"], ["commands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_audit_user_created", "execution_audit", ["user_id", "created_at"])
    op.create_index("ix_execution_audit_command", "execution_audit", ["command_id"])


def downgrade() -> None:
    op.drop_index("ix_execution_audit_command", table_name="execution_audit")
    op.drop_index("ix_execution_audit_user_created", table_name="execution_audit")
    op.drop_table("execution_audit")
    op.drop_column("approvals", "reversible")
    op.drop_column("approvals", "permission")
    op.drop_column("approvals", "risk_level")
    op.drop_column("approvals", "action_payload")
    op.drop_column("approvals", "action_name")
