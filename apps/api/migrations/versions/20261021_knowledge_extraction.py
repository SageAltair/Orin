"""Persist extraction jobs, derived document data and user feedback."""
from alembic import op
import sqlalchemy as sa

revision = "20261021_knowledge_extraction"
down_revision = "20261020_knowledge_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("extraction_status", sa.String(16), server_default="not_requested", nullable=False))
    op.add_column("knowledge_documents", sa.Column("extracted_data", sa.JSON(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("extraction_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("knowledge_documents", sa.Column("extraction_error", sa.String(240), nullable=True))
    op.create_table(
        "knowledge_extraction_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(240), nullable=True),
        sa.Column("model_name", sa.String(160), nullable=True),
        sa.Column("prompt_version", sa.String(32), server_default="knowledge-extraction-v1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "document_version", name="uq_knowledge_extraction_version"),
    )
    op.create_index("ix_knowledge_extraction_jobs_status_retry", "knowledge_extraction_jobs", ["status", "next_retry_at"])
    op.create_table(
        "knowledge_feedback",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("insight_id", sa.Uuid(), nullable=True), sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("feedback_type", sa.String(24), nullable=False), sa.Column("correction", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["insight_id"], ["knowledge_insights.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_feedback_user_created", "knowledge_feedback", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_feedback_user_created", table_name="knowledge_feedback")
    op.drop_table("knowledge_feedback")
    op.drop_index("ix_knowledge_extraction_jobs_status_retry", table_name="knowledge_extraction_jobs")
    op.drop_table("knowledge_extraction_jobs")
    op.drop_column("knowledge_documents", "extraction_error")
    op.drop_column("knowledge_documents", "extraction_version")
    op.drop_column("knowledge_documents", "extracted_data")
    op.drop_column("knowledge_documents", "extraction_status")
