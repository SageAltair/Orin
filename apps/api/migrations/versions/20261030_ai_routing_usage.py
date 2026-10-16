"""Add AI routing policy, favorites, usage, and budgets."""
from alembic import op
import sqlalchemy as sa

revision = "20261030_ai_routing_usage"
down_revision = "20261029_proactive_mode"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_model_configurations", sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default="false"))
    op.create_table("ai_user_policies",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("auto_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fallback_model_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("task_model_ids", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("monthly_budget_cents", sa.Integer()),
        sa.Column("warning_threshold_percent", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("ai_usage_records",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_configuration_id", sa.Uuid(), sa.ForeignKey("ai_model_configurations.id", ondelete="SET NULL")),
        sa.Column("provider", sa.String(40), nullable=False), sa.Column("model_id", sa.String(240), nullable=False),
        sa.Column("request_type", sa.String(60), nullable=False), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("input_tokens_estimate", sa.Integer()), sa.Column("output_tokens_estimate", sa.Integer()),
        sa.Column("estimated_cost_microusd", sa.Integer()), sa.Column("error_category", sa.String(60)),
        sa.Column("used_fallback", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ai_usage_user_created", "ai_usage_records", ["user_id", "created_at"])


def downgrade():
    op.drop_table("ai_usage_records"); op.drop_table("ai_user_policies")
    op.drop_column("ai_model_configurations", "is_favorite")
