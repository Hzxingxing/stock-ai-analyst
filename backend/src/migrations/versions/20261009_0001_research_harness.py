"""Create user-scoped research and market data tables.

Revision ID: 8b26c610d3a1
Revises: None
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

revision = "8b26c610d3a1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.UniqueConstraint("email", name="uq_app_users_email"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "research_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False, server_default="新研究"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_conversation_owner_updated", "research_conversations", ["owner_id", "updated_at"]
    )

    op.create_table(
        "research_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("research_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_message_conversation_created", "research_messages", ["conversation_id", "created_at"]
    )

    op.create_table(
        "research_tool_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("research_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("research_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("input_summary", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.Text()),
        sa.Column("source", sa.String(200)),
        sa.Column("data_as_of", sa.String(40)),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("cache_status", sa.String(20)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_tool_execution_message", "research_tool_executions", ["message_id"])
    op.create_index(
        "ix_tool_execution_owner_created", "research_tool_executions", ["owner_id", "created_at"]
    )

    op.create_table(
        "research_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("research_conversations.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("attribution", sa.String(30), nullable=False, server_default="user"),
        sa.Column("stance", sa.String(30)),
        sa.Column("supporting_evidence", sa.JSON()),
        sa.Column("counter_evidence", sa.JSON()),
        sa.Column("invalidation_conditions", sa.JSON()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_memory_owner_updated", "research_memories", ["owner_id", "updated_at"])

    op.create_table(
        "market_instruments",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("instrument_type", sa.String(20), nullable=False),
        sa.Column("exchange", sa.String(12), nullable=False),
        sa.Column("provider_symbol", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.UniqueConstraint(
            "instrument_type", "provider_symbol", name="uq_instrument_provider_symbol"
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_instrument_type_active", "market_instruments", ["instrument_type", "is_active"]
    )

    op.create_table(
        "user_watchlist",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "instrument_code", name="uq_watchlist_owner_instrument"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_watchlist_owner", "user_watchlist", ["owner_id"])

    op.create_table(
        "market_daily_bars",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float()),
        sa.Column("high", sa.Float()),
        sa.Column("low", sa.Float()),
        sa.Column("close", sa.Float()),
        sa.Column("volume", sa.Float()),
        sa.Column("amount", sa.Float()),
        sa.Column("change_pct", sa.Float()),
        sa.Column("turnover_rate", sa.Float()),
        sa.Column("adjustment", sa.String(8), nullable=False, server_default="qfq"),
        sa.Column("source", sa.String(100), nullable=False, server_default="AKShare"),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "instrument_code", "trade_date", "adjustment", name="uq_market_daily_bar"
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_market_daily_lookup", "market_daily_bars", ["instrument_code", "trade_date"]
    )

    op.create_table(
        "market_daily_statistics",
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("total_stocks", sa.Integer()),
        sa.Column("advances", sa.Integer()),
        sa.Column("declines", sa.Integer()),
        sa.Column("unchanged", sa.Integer()),
        sa.Column("limit_up", sa.Integer()),
        sa.Column("limit_down", sa.Integer()),
        sa.Column("total_volume", sa.Float()),
        sa.Column("total_amount", sa.Float()),
        sa.Column("source", sa.String(100), nullable=False, server_default="AKShare"),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    instruments = sa.table(
        "market_instruments",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("instrument_type", sa.String),
        sa.column("exchange", sa.String),
        sa.column("provider_symbol", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        instruments,
        [
            {
                "code": "SSE:000001",
                "name": "上证指数",
                "instrument_type": "index",
                "exchange": "SSE",
                "provider_symbol": "sh000001",
                "is_active": True,
            },
            {
                "code": "SZSE:399001",
                "name": "深证成指",
                "instrument_type": "index",
                "exchange": "SZSE",
                "provider_symbol": "sz399001",
                "is_active": True,
            },
            {
                "code": "SZSE:399006",
                "name": "创业板指",
                "instrument_type": "index",
                "exchange": "SZSE",
                "provider_symbol": "sz399006",
                "is_active": True,
            },
            {
                "code": "SSE:000688",
                "name": "科创50",
                "instrument_type": "index",
                "exchange": "SSE",
                "provider_symbol": "sh000688",
                "is_active": True,
            },
            {
                "code": "SSE:000300",
                "name": "沪深300",
                "instrument_type": "index",
                "exchange": "SSE",
                "provider_symbol": "sh000300",
                "is_active": True,
            },
            {
                "code": "SSE:000905",
                "name": "中证500",
                "instrument_type": "index",
                "exchange": "SSE",
                "provider_symbol": "sh000905",
                "is_active": True,
            },
            {
                "code": "SSE:000852",
                "name": "中证1000",
                "instrument_type": "index",
                "exchange": "SSE",
                "provider_symbol": "sh000852",
                "is_active": True,
            },
            {
                "code": "SSE:000016",
                "name": "上证50",
                "instrument_type": "index",
                "exchange": "SSE",
                "provider_symbol": "sh000016",
                "is_active": True,
            },
        ],
    )

    op.create_table(
        "company_notices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("announcement_date", sa.Date()),
        sa.Column("disclosure_time", sa.DateTime()),
        sa.Column("category", sa.String(100)),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("content", sa.Text()),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("instrument_code", "external_id", name="uq_notice_instrument_external"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_notice_instrument_date", "company_notices", ["instrument_code", "announcement_date"]
    )

    op.create_table(
        "company_financial_reports",
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("report_type", sa.String(40), primary_key=True),
        sa.Column("report_date", sa.Date(), primary_key=True),
        sa.Column("available_on", sa.Date()),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_financial_instrument_date",
        "company_financial_reports",
        ["instrument_code", "report_date"],
    )

    op.create_table(
        "company_valuation_snapshots",
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("valuation_date", sa.Date(), primary_key=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("units", sa.JSON(), nullable=False),
        sa.Column("industry", sa.String(200)),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_valuation_instrument_observed",
        "company_valuation_snapshots",
        ["instrument_code", "observed_at"],
    )

    op.create_table(
        "company_chip_snapshots",
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("profit_ratio", sa.Float()),
        sa.Column("average_cost", sa.Float()),
        sa.Column("cost_90_low", sa.Float()),
        sa.Column("cost_90_high", sa.Float()),
        sa.Column("concentration_90", sa.Float()),
        sa.Column("cost_70_low", sa.Float()),
        sa.Column("cost_70_high", sa.Float()),
        sa.Column("concentration_70", sa.Float()),
        sa.Column("price_distribution", sa.JSON()),
        sa.Column("distribution_available", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_chip_instrument_date", "company_chip_snapshots", ["instrument_code", "trade_date"]
    )

    op.create_table(
        "company_fund_flow_bars",
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("units", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_fund_flow_instrument_date", "company_fund_flow_bars", ["instrument_code", "trade_date"]
    )

    op.create_table(
        "company_holder_snapshots",
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("report_date", sa.Date(), primary_key=True),
        sa.Column("available_on", sa.Date()),
        sa.Column("total_holders", sa.Integer()),
        sa.Column("average_hold_number", sa.Float()),
        sa.Column("top10_hold_ratio", sa.Float()),
        sa.Column("first_holder_name", sa.String(500)),
        sa.Column("first_holder_ratio", sa.Float()),
        sa.Column("concentration_trend", sa.String(40)),
        sa.Column("top_holders", sa.JSON()),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("collected_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_holder_instrument_date", "company_holder_snapshots", ["instrument_code", "report_date"]
    )

    op.create_table(
        "company_dataset_states",
        sa.Column(
            "instrument_code",
            sa.String(32),
            sa.ForeignKey("market_instruments.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("dataset", sa.String(40), primary_key=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )



def downgrade() -> None:
    op.drop_table("company_dataset_states")
    op.drop_index("ix_holder_instrument_date", table_name="company_holder_snapshots")
    op.drop_table("company_holder_snapshots")
    op.drop_index("ix_fund_flow_instrument_date", table_name="company_fund_flow_bars")
    op.drop_table("company_fund_flow_bars")
    op.drop_index("ix_chip_instrument_date", table_name="company_chip_snapshots")
    op.drop_table("company_chip_snapshots")
    op.drop_index("ix_valuation_instrument_observed", table_name="company_valuation_snapshots")
    op.drop_table("company_valuation_snapshots")
    op.drop_index("ix_financial_instrument_date", table_name="company_financial_reports")
    op.drop_table("company_financial_reports")
    op.drop_index("ix_notice_instrument_date", table_name="company_notices")
    op.drop_table("company_notices")
    op.drop_table("market_daily_statistics")
    op.drop_index("ix_market_daily_lookup", table_name="market_daily_bars")
    op.drop_table("market_daily_bars")
    op.drop_index("ix_watchlist_owner", table_name="user_watchlist")
    op.drop_table("user_watchlist")
    op.drop_index("ix_instrument_type_active", table_name="market_instruments")
    op.drop_table("market_instruments")
    op.drop_index("ix_memory_owner_updated", table_name="research_memories")
    op.drop_table("research_memories")
    op.drop_index("ix_tool_execution_owner_created", table_name="research_tool_executions")
    op.drop_index("ix_tool_execution_message", table_name="research_tool_executions")
    op.drop_table("research_tool_executions")
    op.drop_index("ix_message_conversation_created", table_name="research_messages")
    op.drop_table("research_messages")
    op.drop_index("ix_conversation_owner_updated", table_name="research_conversations")
    op.drop_table("research_conversations")
    op.drop_table("app_users")
