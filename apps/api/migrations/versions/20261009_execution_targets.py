"""Record requested and selected execution target on worker jobs."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_targets"
down_revision = "20261009_github"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("worker_jobs", sa.Column("requested_target", sa.String(12), server_default="auto", nullable=False))
    op.add_column("worker_jobs", sa.Column("selected_target", sa.String(12), nullable=True))
    op.execute("UPDATE worker_jobs SET selected_target = 'local'")
    op.create_check_constraint("ck_worker_job_requested_target", "worker_jobs", "requested_target IN ('local', 'cloud', 'auto')")
    op.create_check_constraint("ck_worker_job_selected_target", "worker_jobs", "selected_target IS NULL OR selected_target IN ('local', 'cloud')")


def downgrade() -> None:
    op.drop_constraint("ck_worker_job_selected_target", "worker_jobs", type_="check")
    op.drop_constraint("ck_worker_job_requested_target", "worker_jobs", type_="check")
    op.drop_column("worker_jobs", "selected_target")
    op.drop_column("worker_jobs", "requested_target")
