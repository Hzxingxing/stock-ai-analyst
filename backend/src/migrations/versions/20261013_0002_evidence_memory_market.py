"""Add structured tool evidence, scoped memory lifecycle, and market-limit sources.

Revision ID: 20261013_0002
Revises: 8b26c610d3a1
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from alembic import op

revision = "20261013_0002"
down_revision = "8b26c610d3a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_tool_executions", sa.Column("evidence", sa.JSON(), nullable=True))

    op.add_column("research_memories", sa.Column("instrument_codes", sa.JSON(), nullable=True))
    op.add_column("research_memories", sa.Column("valid_until", sa.Date(), nullable=True))
    op.add_column(
        "research_memories",
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )
    op.add_column("research_memories", sa.Column("supersedes_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_research_memories_supersedes_id",
        "research_memories",
        "research_memories",
        ["supersedes_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_memory_owner_status_validity",
        "research_memories",
        ["owner_id", "status", "valid_until"],
    )

    op.add_column("market_daily_statistics", sa.Column("limit_up_source", sa.String(100)))
    op.add_column("market_daily_statistics", sa.Column("limit_down_source", sa.String(100)))
    op.add_column("market_daily_statistics", sa.Column("trade_date_source", sa.String(100)))


def downgrade() -> None:
    op.drop_column("market_daily_statistics", "trade_date_source")
    op.drop_column("market_daily_statistics", "limit_down_source")
    op.drop_column("market_daily_statistics", "limit_up_source")

    op.drop_index("ix_memory_owner_status_validity", table_name="research_memories")
    op.drop_constraint(
        "fk_research_memories_supersedes_id", "research_memories", type_="foreignkey"
    )
    op.drop_column("research_memories", "supersedes_id")
    op.drop_column("research_memories", "status")
    op.drop_column("research_memories", "valid_until")
    op.drop_column("research_memories", "instrument_codes")

    op.drop_column("research_tool_executions", "evidence")
