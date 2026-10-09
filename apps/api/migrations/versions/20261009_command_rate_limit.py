"""Add shared database-backed command API rate limit windows."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_command_rate_limit"
down_revision = "20261009_worker_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_rate_windows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("route", sa.String(60), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "route", "window_start", name="uq_request_rate_user_route_window"),
    )
    op.create_index("ix_request_rate_window_start", "request_rate_windows", ["window_start"])


def downgrade() -> None:
    op.drop_index("ix_request_rate_window_start", table_name="request_rate_windows")
    op.drop_table("request_rate_windows")
