"""Add encrypted provider connections and GitHub repository context links."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_github"
down_revision = "20261009_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("external_account_id", sa.String(120), nullable=False),
        sa.Column("account_login", sa.String(120), nullable=False),
        sa.Column("credential_ciphertext", sa.Text(), nullable=False),
        sa.Column("granted_scopes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("credential_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_integration_connection_user_provider"),
    )
    op.create_index("ix_integration_connections_provider", "integration_connections", ["provider", "last_successful_sync_at"])
    op.create_table(
        "integration_oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_integration_oauth_state_hash"),
    )
    op.create_index("ix_integration_oauth_states_user_expiry", "integration_oauth_states", ["user_id", "expires_at"])
    op.create_table(
        "project_integration_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_resource_id", sa.String(120), nullable=False),
        sa.Column("resource_owner", sa.String(120), nullable=False),
        sa.Column("resource_name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["integration_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "provider", name="uq_project_integration_source_project_provider"),
    )
    op.create_index("ix_project_integration_sources_user_provider", "project_integration_sources", ["user_id", "provider"])


def downgrade() -> None:
    op.drop_index("ix_project_integration_sources_user_provider", table_name="project_integration_sources")
    op.drop_table("project_integration_sources")
    op.drop_index("ix_integration_oauth_states_user_expiry", table_name="integration_oauth_states")
    op.drop_table("integration_oauth_states")
    op.drop_index("ix_integration_connections_provider", table_name="integration_connections")
    op.drop_table("integration_connections")
