"""Workspaces: every device gets a session on its first visit, sessions belong to a workspace,
handoff codes attach another device, and runs, uploads, investigations and audit entries record
the workspace that made them and go with it (nullable: rows from before stay valid and simply
belong to no workspace).

Existing sessions each get their own workspace (with the session's ID), keep their lifetime as
the end of their role, and count as last seen when they were created.

Downgrading drops the workspaces and handoff codes, the owner columns and the run names, notes,
archive marks and saved views, deletes visitor sessions (the earlier schema has no such role) and
gives each remaining session the end of its role as its end again.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNED = ("runs", "uploads", "investigations", "audit_entries")


def _owner(table: str) -> None:
    op.add_column(table, sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f(f"fk_{table}_workspace_id_workspaces"),
        table,
        "workspaces",
        ["workspace_id"],
        ["workspace_id"],
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", name=op.f("pk_workspaces")),
    )
    op.create_index(op.f("ix_workspaces_last_seen_at"), "workspaces", ["last_seen_at"])

    op.add_column("sessions", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.add_column("sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "sessions", sa.Column("role_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_sessions_workspace_id_workspaces"),
        "sessions",
        "workspaces",
        ["workspace_id"],
        ["workspace_id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_sessions_workspace_id"), "sessions", ["workspace_id"])
    op.drop_constraint(op.f("ck_sessions_role"), "sessions", type_="check")
    op.create_check_constraint(
        op.f("ck_sessions_role"), "sessions", "role IN ('visitor', 'engineer', 'admin')"
    )
    op.execute(
        "INSERT INTO workspaces (workspace_id, created_at, last_seen_at) "
        "SELECT session_id, created_at, created_at FROM sessions"
    )
    op.execute(
        "UPDATE sessions SET workspace_id = session_id, role_expires_at = expires_at, "
        "last_seen_at = created_at"
    )

    op.create_table(
        "workspace_handoffs",
        sa.Column("code_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["sessions.session_id"],
            name=op.f("fk_workspace_handoffs_created_by_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.workspace_id"],
            name=op.f("fk_workspace_handoffs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("code_hash", name=op.f("pk_workspace_handoffs")),
    )
    op.create_index(op.f("ix_workspace_handoffs_expires_at"), "workspace_handoffs", ["expires_at"])
    op.create_index(
        op.f("ix_workspace_handoffs_workspace_id"), "workspace_handoffs", ["workspace_id"]
    )

    for table in OWNED:
        _owner(table)
    op.create_index("ix_runs_workspace", "runs", ["workspace_id", "created_at", "run_id"])
    op.create_index("ix_uploads_workspace", "uploads", ["workspace_id", "created_at", "upload_id"])
    op.create_index(
        "ix_investigations_workspace",
        "investigations",
        ["workspace_id", "created_at", "investigation_id"],
    )
    op.create_index("ix_audit_entries_workspace", "audit_entries", ["workspace_id", "audit_id"])
    op.add_column("runs", sa.Column("upload_id", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("again_of", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("label", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("view", sa.Text(), nullable=True))
    op.create_index(
        "ix_runs_upload",
        "runs",
        ["upload_id"],
        postgresql_where=sa.text("upload_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runs_upload", table_name="runs", postgresql_where=sa.text("upload_id IS NOT NULL")
    )
    for column in ("view", "archived_at", "note", "label", "again_of", "upload_id"):
        op.drop_column("runs", column)
    op.drop_index("ix_audit_entries_workspace", table_name="audit_entries")
    op.drop_index("ix_investigations_workspace", table_name="investigations")
    op.drop_index("ix_uploads_workspace", table_name="uploads")
    op.drop_index("ix_runs_workspace", table_name="runs")
    for table in OWNED:
        op.drop_constraint(op.f(f"fk_{table}_workspace_id_workspaces"), table, type_="foreignkey")
        op.drop_column(table, "workspace_id")

    op.drop_index(op.f("ix_workspace_handoffs_workspace_id"), table_name="workspace_handoffs")
    op.drop_index(op.f("ix_workspace_handoffs_expires_at"), table_name="workspace_handoffs")
    op.drop_table("workspace_handoffs")

    op.execute("DELETE FROM sessions WHERE role = 'visitor'")
    op.execute("UPDATE sessions SET expires_at = role_expires_at WHERE role_expires_at IS NOT NULL")
    op.drop_constraint(op.f("ck_sessions_role"), "sessions", type_="check")
    op.create_check_constraint(
        op.f("ck_sessions_role"), "sessions", "role IN ('engineer', 'admin')"
    )
    op.drop_index(op.f("ix_sessions_workspace_id"), table_name="sessions")
    op.drop_constraint(op.f("fk_sessions_workspace_id_workspaces"), "sessions", type_="foreignkey")
    op.drop_column("sessions", "role_expires_at")
    op.drop_column("sessions", "last_seen_at")
    op.drop_column("sessions", "workspace_id")

    op.drop_index(op.f("ix_workspaces_last_seen_at"), table_name="workspaces")
    op.drop_table("workspaces")
