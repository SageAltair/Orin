"""Add persistent personal knowledge documents and revision history."""
from alembic import op
import sqlalchemy as sa

revision = "20261019_personal_knowledge"
down_revision = "20261018_task_return_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("document_type", sa.String(24), server_default="quick_note", nullable=False),
        sa.Column("status", sa.String(24), server_default="inbox", nullable=False),
        sa.Column("tags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("exclude_from_ai", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_documents_user_updated", "knowledge_documents", ["user_id", "updated_at"])
    op.create_index("ix_knowledge_documents_user_type_status", "knowledge_documents", ["user_id", "document_type", "status"])
    op.create_table(
        "knowledge_document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_document_versions_document", "knowledge_document_versions", ["document_id", "created_at"])
    op.create_table(
        "knowledge_document_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "target_id", name="uq_knowledge_document_link"),
        sa.CheckConstraint("source_id <> target_id", name="ck_knowledge_document_link_not_self"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_document_links")
    op.drop_index("ix_knowledge_document_versions_document", table_name="knowledge_document_versions")
    op.drop_table("knowledge_document_versions")
    op.drop_index("ix_knowledge_documents_user_type_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_user_updated", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
