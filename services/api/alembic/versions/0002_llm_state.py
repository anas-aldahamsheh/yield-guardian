"""Language-model state: call log, response cache, role assignments, chat routes, evaluations;
and the knowledge chunks with their English full-text vector (GIN index).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_routes",
        sa.Column("route_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.CheckConstraint("kind IN ('deterministic', 'model')", name=op.f("ck_chat_routes_kind")),
        sa.PrimaryKeyConstraint("route_id", name=op.f("pk_chat_routes")),
    )
    op.create_index(op.f("ix_chat_routes_at"), "chat_routes", ["at"], unique=False)
    op.create_table(
        "knowledge_chunks",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english'::regconfig, text)", persisted=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("chunk_id", name=op.f("pk_knowledge_chunks")),
    )
    op.create_index(
        "ix_knowledge_chunks_search",
        "knowledge_chunks",
        ["search"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        op.f("ix_knowledge_chunks_source_id"), "knowledge_chunks", ["source_id"], unique=False
    )
    op.create_table(
        "llm_calls",
        sa.Column("call_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("record", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("call_id", name=op.f("pk_llm_calls")),
    )
    op.create_index(
        op.f("ix_llm_calls_correlation_id"), "llm_calls", ["correlation_id"], unique=False
    )
    op.create_index("ix_llm_calls_started", "llm_calls", ["started_at", "call_id"], unique=False)
    op.create_table(
        "llm_evaluations",
        sa.Column("evaluation_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("task_set", sa.Text(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("evaluation_id", name=op.f("pk_llm_evaluations")),
    )
    op.create_index(
        "ix_llm_evaluations_run", "llm_evaluations", ["run_at", "evaluation_id"], unique=False
    )
    op.create_table(
        "llm_response_cache",
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("cache_key", name=op.f("pk_llm_response_cache")),
    )
    op.create_index(
        op.f("ix_llm_response_cache_last_used_at"),
        "llm_response_cache",
        ["last_used_at"],
        unique=False,
    )
    op.create_table(
        "llm_role_assignments",
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("chain", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("role", name=op.f("pk_llm_role_assignments")),
    )


def downgrade() -> None:
    op.drop_table("llm_role_assignments")
    op.drop_index(op.f("ix_llm_response_cache_last_used_at"), table_name="llm_response_cache")
    op.drop_table("llm_response_cache")
    op.drop_index("ix_llm_evaluations_run", table_name="llm_evaluations")
    op.drop_table("llm_evaluations")
    op.drop_index("ix_llm_calls_started", table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_correlation_id"), table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index(op.f("ix_knowledge_chunks_source_id"), table_name="knowledge_chunks")
    op.drop_index(
        "ix_knowledge_chunks_search", table_name="knowledge_chunks", postgresql_using="gin"
    )
    op.drop_table("knowledge_chunks")
    op.drop_index(op.f("ix_chat_routes_at"), table_name="chat_routes")
    op.drop_table("chat_routes")
