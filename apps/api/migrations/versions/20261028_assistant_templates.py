"""Contextual and user-authored assistant templates."""
from alembic import op
import sqlalchemy as sa

revision = "20261028_templates"
down_revision = "20261027_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("assistant_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False), sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500), nullable=False), sa.Column("category", sa.String(40), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False), sa.Column("compatible_pages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "slug", name="uq_assistant_template_user_slug"))
    op.create_index("ix_assistant_templates_user_category", "assistant_templates", ["user_id", "category"])


def downgrade():
    op.drop_table("assistant_templates")
