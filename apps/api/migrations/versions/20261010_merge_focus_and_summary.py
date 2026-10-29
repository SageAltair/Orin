"""Merge the focus and summary migration branches."""

revision = "20261010_merge_focus_summary"
down_revision = ("20261009_summary_checkpoint", "20261010_focus_timer_preference")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
