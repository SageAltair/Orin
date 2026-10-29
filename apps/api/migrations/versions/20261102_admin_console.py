"""Add administrator and account-state controls."""

from alembic import op
import sqlalchemy as sa

revision = "20261102_admin_console"
down_revision = "20261101_functional_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("is_disabled", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("users", "is_disabled")
    op.drop_column("users", "is_admin")
