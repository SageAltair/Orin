"""Show core workspace sections by default for existing users."""

from alembic import op
import sqlalchemy as sa


revision = "20261011_nav_defaults"
down_revision = "20261010_merge_focus_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE user_capabilities SET visible = true, pinned = false "
        "WHERE granted = true AND capability_id IN ("
        "SELECT id FROM capabilities WHERE is_enabled = true AND code IN ('projects', 'activity'))"
    ))


def downgrade() -> None:
    # This is a user preference data backfill. Reverting it could erase changes
    # users make after upgrade, so visibility settings are retained on downgrade.
    pass
