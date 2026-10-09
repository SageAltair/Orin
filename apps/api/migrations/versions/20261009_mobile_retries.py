"""Add command idempotency and cached response fields for safe client retries."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_mobile_retries"
down_revision = "20261009_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commands", sa.Column("idempotency_key", sa.String(160), nullable=True))
    op.add_column("commands", sa.Column("response_intent", sa.String(40), nullable=True))
    op.add_column("commands", sa.Column("response_json", sa.JSON(), nullable=True))
    op.add_column("commands", sa.Column("response_message", sa.Text(), nullable=True))
    op.add_column("commands", sa.Column("response_execution_json", sa.JSON(), nullable=True))
    op.create_unique_constraint("uq_command_user_idempotency", "commands", ["user_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_command_user_idempotency", "commands", type_="unique")
    op.drop_column("commands", "response_execution_json")
    op.drop_column("commands", "response_message")
    op.drop_column("commands", "response_json")
    op.drop_column("commands", "response_intent")
    op.drop_column("commands", "idempotency_key")
