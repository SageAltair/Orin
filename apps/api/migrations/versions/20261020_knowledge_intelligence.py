"""Add persisted evidence insights and document review state."""
from alembic import op
import sqlalchemy as sa

revision = "20261020_knowledge_intelligence"
down_revision = "20261019_personal_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("review_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "knowledge_insights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("insight_type", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(160), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("frequency", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("suggested_next_step", sa.Text(), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "insight_type", "fingerprint", name="uq_knowledge_insight_identity"),
    )
    op.create_index("ix_knowledge_insights_user_status", "knowledge_insights", ["user_id", "status", "evaluated_at"])
    op.create_table(
        "knowledge_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_surfaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_knowledge_review_document"),
    )
    op.create_index("ix_knowledge_reviews_user_status_due", "knowledge_reviews", ["user_id", "status", "due_at"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_reviews_user_status_due", table_name="knowledge_reviews")
    op.drop_table("knowledge_reviews")
    op.drop_index("ix_knowledge_insights_user_status", table_name="knowledge_insights")
    op.drop_table("knowledge_insights")
    op.drop_column("knowledge_documents", "review_at")
