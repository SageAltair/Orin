"""Add creative studio: document cards and bidirectional idea-document links

Extends the Creative Studio layer with:
- creative_document_cards: alternate visual representation of documents
- idea_document_links: bidirectional links between ideas and documents for
  the visual idea canvas
"""
from alembic import op
import sqlalchemy as sa


revision = "20261022_creative_studio_cards_links"
down_revision = "20261022_creative_studio_ideas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # creative_document_cards: alternate visual representation of documents.
    op.create_table(
        "creative_document_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("central_question", sa.Text(), nullable=True),
        sa.Column("point_of_view", sa.String(240), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="todo"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="cascade"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="set null"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", name="uq_card_id"),
    )
    op.create_index(
        "ix_creative_document_cards_project_updated",
        "creative_document_cards",
        ["project_id", "updated_at"],
    )

    # Bidirectional idea-document links for the visual canvas.
    op.create_table(
        "idea_document_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("idea_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("link_type", sa.String(24), nullable=False, server_default="inspires"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="cascade"
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"], ["idea_inbox.id"], ondelete="cascade"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idea_id", "document_id", "link_type", name="uq_idea_document_link"
        ),
    )


def downgrade() -> None:
    op.drop_table("idea_document_links")
    op.drop_index(
        "ix_creative_document_cards_project_updated",
        table_name="creative_document_cards",
    )
    op.drop_table("creative_document_cards")
