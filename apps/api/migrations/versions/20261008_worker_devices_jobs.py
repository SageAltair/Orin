"""Add registered worker devices and approval-gated jobs."""
from alembic import op
import sqlalchemy as sa

revision = "20261008_worker"
down_revision = "20261008_approval_policy"
branch_labels = None
depends_on = None


device_status = sa.Enum("pending", "active", "revoked", "offline", name="device_status")
job_status = sa.Enum("pending_approval", "queued", "starting", "running", "completed", "failed", "cancelled", "expired", name="worker_job_status")


def upgrade() -> None:
    op.create_table("worker_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("platform", sa.String(80), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("status", device_status, server_default="pending", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("credential_hash", name="uq_worker_devices_credential_hash"))
    op.create_index("ix_worker_devices_owner_status", "worker_devices", ["owner_id", "status"])
    op.create_table("worker_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("status", job_status, server_default="pending_approval", nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress", sa.String(240), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("failure", sa.String(240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["worker_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("approval_id", name="uq_worker_jobs_approval_id"),
        sa.UniqueConstraint("nonce", name="uq_worker_job_nonce"))
    op.create_index("ix_worker_jobs_device_status_created", "worker_jobs", ["device_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_jobs_device_status_created", table_name="worker_jobs")
    op.drop_table("worker_jobs")
    op.drop_index("ix_worker_devices_owner_status", table_name="worker_devices")
    op.drop_table("worker_devices")
    job_status.drop(op.get_bind(), checkfirst=True)
    device_status.drop(op.get_bind(), checkfirst=True)
