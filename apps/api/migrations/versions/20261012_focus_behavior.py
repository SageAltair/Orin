"""Persist the preferences and visit state used by Focus behavior."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261012_focus_behavior"
down_revision = "20261011_nav_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM("low", "medium", "high", name="default_energy_level").create(bind, checkfirst=True)
        energy_type = postgresql.ENUM("low", "medium", "high", name="default_energy_level", create_type=False)
    else:
        energy_type = sa.Enum("low", "medium", "high", name="default_energy_level", native_enum=False)
    op.add_column("user_settings", sa.Column("default_energy", energy_type, nullable=True))
    op.add_column("user_settings", sa.Column("weekly_rest_day", sa.Integer(), nullable=True))
    op.add_column("user_settings", sa.Column("check_in_interval", sa.Integer(), nullable=True))
    op.add_column("user_settings", sa.Column("routines", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("user_settings", sa.Column("last_seen_day_key", sa.String(10), nullable=True))
    op.add_column("user_settings", sa.Column("active_absence_key", sa.String(10), nullable=True))
    op.add_column("user_settings", sa.Column("dismissed_absence_key", sa.String(10), nullable=True))
    op.add_column("user_settings", sa.Column("prompt_state", sa.JSON(), server_default="{}", nullable=False))
    op.create_check_constraint("ck_user_settings_rest_day_range", "user_settings", "weekly_rest_day IS NULL OR weekly_rest_day BETWEEN 0 AND 6")
    op.create_check_constraint("ck_user_settings_check_in_interval", "user_settings", "check_in_interval IS NULL OR check_in_interval BETWEEN 5 AND 120")
    op.create_index("ix_tasks_owner_decay_review", "tasks", ["owner_id", "decay_review_at"])


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_tasks_owner_decay_review", table_name="tasks")
    op.drop_constraint("ck_user_settings_check_in_interval", "user_settings", type_="check")
    op.drop_constraint("ck_user_settings_rest_day_range", "user_settings", type_="check")
    for name in ("prompt_state", "dismissed_absence_key", "active_absence_key", "last_seen_day_key", "routines", "check_in_interval", "weekly_rest_day", "default_energy"):
        op.drop_column("user_settings", name)
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(name="default_energy_level").drop(bind, checkfirst=True)
