"""Extend the existing activity stream with lifecycle links and safe metadata."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_activity"
down_revision = "20261009_focus_idx"
branch_labels = None
depends_on = None


NEW_TYPES = (
    "command_received", "command_completed", "command_failed", "approval_requested",
    "approval_decided", "worker_job_queued", "worker_job_started",
    "worker_job_completed", "worker_job_failed", "worker_job_cancelled",
    "worker_job_timed_out", "worker_connected", "worker_disconnected", "policy_decision",
    "integration_operation",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in NEW_TYPES:
            op.execute(sa.text(f"ALTER TYPE activity_type ADD VALUE IF NOT EXISTS '{value}'"))
    op.add_column("activity", sa.Column("execution_id", sa.Uuid(), nullable=True))
    op.add_column("activity", sa.Column("approval_id", sa.Uuid(), nullable=True))
    op.add_column("activity", sa.Column("worker_job_id", sa.Uuid(), nullable=True))
    op.add_column("activity", sa.Column("severity", sa.String(16), server_default="info", nullable=False))
    op.add_column("activity", sa.Column("source", sa.String(40), server_default="api", nullable=False))
    op.add_column("activity", sa.Column("correlation_id", sa.String(64), nullable=True))
    op.add_column("activity", sa.Column("idempotency_key", sa.String(160), nullable=True))
    op.add_column("activity", sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False))
    op.create_foreign_key("fk_activity_execution_id_executions", "activity", "executions", ["execution_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_activity_approval_id_approvals", "activity", "approvals", ["approval_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_activity_worker_job_id_worker_jobs", "activity", "worker_jobs", ["worker_job_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_activity_execution_created", "activity", ["execution_id", "created_at"])
    op.create_index("ix_activity_user_type_created", "activity", ["user_id", "activity_type", "created_at"])
    op.create_unique_constraint("uq_activity_user_idempotency", "activity", ["user_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_activity_user_idempotency", "activity", type_="unique")
    op.drop_index("ix_activity_user_type_created", table_name="activity")
    op.drop_index("ix_activity_execution_created", table_name="activity")
    op.drop_constraint("fk_activity_worker_job_id_worker_jobs", "activity", type_="foreignkey")
    op.drop_constraint("fk_activity_approval_id_approvals", "activity", type_="foreignkey")
    op.drop_constraint("fk_activity_execution_id_executions", "activity", type_="foreignkey")
    for name in ("metadata", "idempotency_key", "correlation_id", "source", "severity", "worker_job_id", "approval_id", "execution_id"):
        op.drop_column("activity", name)
