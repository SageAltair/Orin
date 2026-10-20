"""Persist workspaces and scope projects, tasks, and routines."""

from alembic import op
import sqlalchemy as sa

revision = "20261101_functional_workspaces"
down_revision = "20261031_automatic_ai_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = sa.Uuid()
    op.create_table(
        "workspaces",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("owner_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("color", sa.String(7), server_default="#6b73ff", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_workspaces_name_nonempty"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_workspace_owner_name"),
    )
    op.create_index("ix_workspaces_owner_id", "workspaces", ["owner_id"])
    for table in ("projects", "tasks", "routines"):
        op.add_column(table, sa.Column("workspace_id", uuid_type, nullable=True))
        op.create_foreign_key(f"fk_{table}_workspace_id", table, "workspaces", ["workspace_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])

    uuid_expression = "lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-a' || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))" if op.get_bind().dialect.name == "sqlite" else "gen_random_uuid()"
    op.execute(sa.text(f"INSERT INTO workspaces (id, owner_id, name, color) SELECT {uuid_expression}, id, 'Personal', '#6b73ff' FROM users"))
    op.execute(sa.text("UPDATE projects SET workspace_id = (SELECT id FROM workspaces WHERE workspaces.owner_id = projects.owner_id AND workspaces.name = 'Personal')"))
    op.execute(sa.text("UPDATE tasks SET workspace_id = (SELECT id FROM workspaces WHERE workspaces.owner_id = tasks.owner_id AND workspaces.name = 'Personal')"))
    op.execute(sa.text("UPDATE routines SET workspace_id = (SELECT id FROM workspaces WHERE workspaces.owner_id = routines.user_id AND workspaces.name = 'Personal')"))


def downgrade() -> None:
    for table in ("routines", "tasks", "projects"):
        op.drop_index(f"ix_{table}_workspace_id", table_name=table)
        op.drop_constraint(f"fk_{table}_workspace_id", table, type_="foreignkey")
        op.drop_column(table, "workspace_id")
    op.drop_index("ix_workspaces_owner_id", table_name="workspaces")
    op.drop_table("workspaces")
