"""Investigations over runs (PLAN_V2 3.4, 7.3): trigger kind ``run_alarm``, and the cause the
fab confirmed when it closed a work order.

Downgrading deletes the ``run_alarm`` investigations (their events, jobs and work orders go with
them), since the earlier schema cannot hold them, and drops the confirmed causes.

Revision ID: 0004
Revises: 0002
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = "'alarm', 'unit', 'wafer', 'lot'"


def _trigger_kinds(kinds: str) -> None:
    name = op.f("ck_investigations_trigger_kind")
    op.drop_constraint(name, "investigations", type_="check")
    op.create_check_constraint(name, "investigations", f"trigger_kind IN ({kinds})")


def upgrade() -> None:
    _trigger_kinds(f"{OLD_KINDS}, 'run_alarm'")
    op.add_column(
        "work_orders",
        sa.Column("confirmed_cause", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_orders", "confirmed_cause")
    op.execute("DELETE FROM investigations WHERE trigger_kind = 'run_alarm'")
    _trigger_kinds(OLD_KINDS)
