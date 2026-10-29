"""Add persistent system administration controls."""

from alembic import op
import sqlalchemy as sa

revision = "20261103_admin_controls"
down_revision = "20261102_admin_console"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.execute(sa.text("INSERT INTO system_settings (key, value) VALUES ('access', '{\"registration_enabled\": true}')"))


def downgrade() -> None:
    op.drop_table("system_settings")
