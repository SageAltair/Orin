"""Add the worker progress event type to the unified timeline."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_worker_progress"
down_revision = "20261009_mobile_retries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TYPE activity_type ADD VALUE IF NOT EXISTS 'worker_job_progress'"))


def downgrade() -> None:
    # PostgreSQL enum values are intentionally retained; removing them is unsafe in place.
    pass
