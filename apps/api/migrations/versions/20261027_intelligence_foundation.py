"""User-owned AI providers and model preferences."""
from alembic import op
import sqlalchemy as sa

revision = "20261027_intelligence"
down_revision = "20261026_notifications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ai_provider_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False), sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("credential_ciphertext", sa.Text(), nullable=False), sa.Column("credential_hint", sa.String(16), nullable=False),
        sa.Column("account_id", sa.String(160)), sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("verified_at", sa.DateTime(timezone=True)), sa.Column("last_test_status", sa.String(24)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_ai_provider_connection_user_provider"))
    op.create_index("ix_ai_provider_connections_user_enabled", "ai_provider_connections", ["user_id", "enabled"])
    op.create_table("ai_model_configurations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("ai_provider_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_id", sa.String(240), nullable=False), sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "model_id", name="uq_ai_model_connection_model"))
    op.create_index("ix_ai_model_configurations_user_default", "ai_model_configurations", ["user_id", "is_default"])


def downgrade():
    op.drop_table("ai_model_configurations")
    op.drop_table("ai_provider_connections")
