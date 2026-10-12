"""Add creative studio activity_type enum values

Registers the activity types emitted by the Creative Studio routes on the
shared activity_type Postgres enum. Guarded with IF NOT EXISTS so it is safe
to re-run. The values are also present on the ActivityType Python enum so
validate_strings accepts them in application code. Downgrade is intentionally a
no-op because Postgres cannot drop individual enum labels.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261023_creative_activity_types"
down_revision = "20261022_creative_studio_cards_links"
branch_labels = None
depends_on = None

_VALUES = (
    "idea_created",
    "idea_linked",
    "idea_unlinked",
    "outline_item_created",
    "outline_item_updated",
    "document_card_created",
    "document_card_updated",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in _VALUES:
            op.execute(sa.text(f"ALTER TYPE activity_type ADD VALUE IF NOT EXISTS '{value}'"))


def downgrade() -> None:
    # Postgres cannot remove values from an existing enum, and rebuilding the
    # type would cascade into every table that uses it. Leftover labels are
    # inert: nothing writes them once the creative routes are gone.
    pass
