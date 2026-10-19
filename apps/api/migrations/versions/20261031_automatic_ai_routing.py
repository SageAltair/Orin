"""Enable automatic AI routing for existing and future users."""

from alembic import op
import sqlalchemy as sa

revision = "20261031_automatic_ai_routing"
down_revision = "20261030_ai_routing_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("ai_user_policies", "auto_enabled", server_default=sa.true())
    op.execute(sa.text("UPDATE ai_user_policies SET auto_enabled = true WHERE auto_enabled = false"))


def downgrade() -> None:
    op.alter_column("ai_user_policies", "auto_enabled", server_default=sa.false())
