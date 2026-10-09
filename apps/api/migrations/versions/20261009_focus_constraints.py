"""Keep focus mode to one active session per user."""
from alembic import op

revision = "20261009_focus_idx"
down_revision = "20261008_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_focus_sessions_one_active_per_user ON focus_sessions (user_id) WHERE status = 'active'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_focus_sessions_one_active_per_user")
