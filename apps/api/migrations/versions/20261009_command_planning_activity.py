"""Record intent interpretation and validated plan creation in Activity."""
from alembic import op
import sqlalchemy as sa


revision = "20261009_command_planning"
down_revision = "20261009_command_rate_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TYPE activity_type ADD VALUE IF NOT EXISTS 'intent_interpreted'"))
        op.execute(sa.text("ALTER TYPE activity_type ADD VALUE IF NOT EXISTS 'plan_created'"))


def downgrade() -> None:
    # PostgreSQL enum values are intentionally retained; removing them is unsafe in place.
    pass
