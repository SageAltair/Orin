"""Add creative studio: idea inbox and outline items

Adds the schema needed for the Creative Studio layer:
- idea_inbox: lightweight idea nodes captured from Quick Capture
- creative_outline_items: hierarchical outline / scene structure

Everything is additive and backward-compatible. No existing table is dropped
or modified.
"""
from alembic import op
import sqlalchemy as sa


revision = "20261022_creative_studio_ideas"
down_revision = "20261021_knowledge_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # idea_inbox: lightweight idea nodes captured from Quick Capture.
    op.create_table(
        "idea_inbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="set null"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", name="uq_idea_inbox_id"),
    )
    op.create_index(
        "ix_idea_inbox_user_updated", "idea_inbox", ["user_id", "updated_at"]
    )
    op.create_index(
        "ix_idea_inbox_user_status", "idea_inbox", ["user_id", "status"]
    )

    # creative_outline_items: hierarchical outline / scene structure.
    op.create_table(
        "creative_outline_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "kind",
            sa.String(24),
            nullable=False,
            server_default="section",
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="set null"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["creative_outline_items.id"], ondelete="set null"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="set null"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", name="uq_outline_item_id"),
        sa.CheckConstraint(
            "NOT (parent_id IS NOT NULL AND document_id IS NOT NULL)",
            name="ck_outline_item_at_most_one_target",
        ),
    )
    op.create_index(
        "ix_creative_outline_items_parent",
        "creative_outline_items",
        ["parent_id"],
    )
    op.create_index(
        "ix_creative_outline_items_project_updated",
        "creative_outline_items",
        ["project_id", "updated_at"],
    )

    # Idea-to-document linking from capture for quick conversion.
    op.add_column(
        "idea_inbox",
        sa.Column("linked_document_ids", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_idea_inbox_linked_documents",
        "idea_inbox",
        ["linked_document_ids"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_idea_inbox_linked_documents", table_name="idea_inbox"
    )
    op.drop_column("idea_inbox", "linked_document_ids")
    op.drop_index(
        "ix_creative_outline_items_project_updated",
        table_name="creative_outline_items",
    )
    op.drop_index("ix_creative_outline_items_parent", table_name="creative_outline_items")
    op.drop_table("creative_outline_items")
    op.drop_index("ix_idea_inbox_user_status", table_name="idea_inbox")
    op.drop_index("ix_idea_inbox_user_updated", table_name="idea_inbox")
    op.drop_table("idea_inbox")
