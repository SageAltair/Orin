"""Add configurable proactive assistance level."""
from alembic import op
import sqlalchemy as sa

revision = "20261029_proactive_mode"
down_revision = "20261028_templates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_preferences", sa.Column("proactive_mode", sa.String(20), nullable=False, server_default="supportive"))
    op.create_check_constraint("ck_user_preferences_proactive_mode", "user_preferences", "proactive_mode IN ('quiet','supportive','proactive','persistent')")


def downgrade():
    op.drop_constraint("ck_user_preferences_proactive_mode", "user_preferences", type_="check")
    op.drop_column("user_preferences", "proactive_mode")
