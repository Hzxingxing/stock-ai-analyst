from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "app_users"
    __table_args__ = (UniqueConstraint("email", name="uq_app_users_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="owner")


class Conversation(Base):
    __tablename__ = "research_conversations"
    __table_args__ = (Index("ix_conversation_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="新研究", server_default="新研究"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    owner: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(Base):
    __tablename__ = "research_messages"
    __table_args__ = (Index("ix_message_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("research_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ToolExecution(Base):
    __tablename__ = "research_tool_executions"
    __table_args__ = (
        Index("ix_tool_execution_message", "message_id"),
        Index("ix_tool_execution_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("research_conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("research_messages.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_summary: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200))
    data_as_of: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running", server_default="running"
    )
    cache_status: Mapped[str | None] = mapped_column(String(20))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ResearchMemory(Base):
    __tablename__ = "research_memories"
    __table_args__ = (Index("ix_memory_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_conversations.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    attribution: Mapped[str] = mapped_column(
        String(30), nullable=False, default="user", server_default="user"
    )
    stance: Mapped[str | None] = mapped_column(String(30))
    supporting_evidence: Mapped[list | None] = mapped_column(JSON)
    counter_evidence: Mapped[list | None] = mapped_column(JSON)
    invalidation_conditions: Mapped[list | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class Instrument(Base):
    __tablename__ = "market_instruments"
    __table_args__ = (
        UniqueConstraint(
            "instrument_type", "provider_symbol", name="uq_instrument_provider_symbol"
        ),
        Index("ix_instrument_type_active", "instrument_type", "is_active"),
    )

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str] = mapped_column(String(12), nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    bars: Mapped[list["MarketDailyBar"]] = relationship(back_populates="instrument")


class UserWatchlist(Base):
    __tablename__ = "user_watchlist"
    __table_args__ = (
        UniqueConstraint("owner_id", "instrument_code", name="uq_watchlist_owner_instrument"),
        Index("ix_watchlist_owner", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False
    )
    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class MarketDailyBar(Base):
    __tablename__ = "market_daily_bars"
    __table_args__ = (
        UniqueConstraint("instrument_code", "trade_date", "adjustment", name="uq_market_daily_bar"),
        Index("ix_market_daily_lookup", "instrument_code", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    change_pct: Mapped[float | None] = mapped_column(Float)
    turnover_rate: Mapped[float | None] = mapped_column(Float)
    adjustment: Mapped[str] = mapped_column(
        String(8), nullable=False, default="qfq", server_default="qfq"
    )
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, default="AKShare", server_default="AKShare"
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    instrument: Mapped[Instrument] = relationship(back_populates="bars")


class MarketStatistic(Base):
    __tablename__ = "market_daily_statistics"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    total_stocks: Mapped[int | None] = mapped_column(Integer)
    advances: Mapped[int | None] = mapped_column(Integer)
    declines: Mapped[int | None] = mapped_column(Integer)
    unchanged: Mapped[int | None] = mapped_column(Integer)
    limit_up: Mapped[int | None] = mapped_column(Integer)
    limit_down: Mapped[int | None] = mapped_column(Integer)
    total_volume: Mapped[float | None] = mapped_column(Float)
    total_amount: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, default="AKShare", server_default="AKShare"
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class CompanyNotice(Base):
    __tablename__ = "company_notices"
    __table_args__ = (
        UniqueConstraint("instrument_code", "external_id", name="uq_notice_instrument_external"),
        Index("ix_notice_instrument_date", "instrument_code", "announcement_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    announcement_date: Mapped[date | None] = mapped_column(Date)
    disclosure_time: Mapped[datetime | None] = mapped_column(DateTime)
    category: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class CompanyFinancialReport(Base):
    __tablename__ = "company_financial_reports"
    __table_args__ = (
        Index("ix_financial_instrument_date", "instrument_code", "report_date"),
    )

    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), primary_key=True
    )
    report_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, primary_key=True)
    available_on: Mapped[date | None] = mapped_column(Date)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ValuationSnapshot(Base):
    __tablename__ = "company_valuation_snapshots"
    __table_args__ = (
        Index("ix_valuation_instrument_observed", "instrument_code", "observed_at"),
    )

    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), primary_key=True
    )
    valuation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    units: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    industry: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ChipDistributionSnapshot(Base):
    __tablename__ = "company_chip_snapshots"
    __table_args__ = (
        Index("ix_chip_instrument_date", "instrument_code", "trade_date"),
    )

    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    profit_ratio: Mapped[float | None] = mapped_column(Float)
    average_cost: Mapped[float | None] = mapped_column(Float)
    cost_90_low: Mapped[float | None] = mapped_column(Float)
    cost_90_high: Mapped[float | None] = mapped_column(Float)
    concentration_90: Mapped[float | None] = mapped_column(Float)
    cost_70_low: Mapped[float | None] = mapped_column(Float)
    cost_70_high: Mapped[float | None] = mapped_column(Float)
    concentration_70: Mapped[float | None] = mapped_column(Float)
    price_distribution: Mapped[list | None] = mapped_column(JSON)
    distribution_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class FundFlowBar(Base):
    __tablename__ = "company_fund_flow_bars"
    __table_args__ = (Index("ix_fund_flow_instrument_date", "instrument_code", "trade_date"),)

    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), primary_key=True
    )
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    units: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class HolderSnapshot(Base):
    __tablename__ = "company_holder_snapshots"
    __table_args__ = (Index("ix_holder_instrument_date", "instrument_code", "report_date"),)

    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), primary_key=True
    )
    report_date: Mapped[date] = mapped_column(Date, primary_key=True)
    available_on: Mapped[date | None] = mapped_column(Date)
    total_holders: Mapped[int | None] = mapped_column(Integer)
    average_hold_number: Mapped[float | None] = mapped_column(Float)
    top10_hold_ratio: Mapped[float | None] = mapped_column(Float)
    first_holder_name: Mapped[str | None] = mapped_column(String(500))
    first_holder_ratio: Mapped[float | None] = mapped_column(Float)
    concentration_trend: Mapped[str | None] = mapped_column(String(40))
    top_holders: Mapped[list | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class CompanyDatasetState(Base):
    __tablename__ = "company_dataset_states"

    instrument_code: Mapped[str] = mapped_column(
        ForeignKey("market_instruments.code", ondelete="CASCADE"), primary_key=True
    )
    dataset: Mapped[str] = mapped_column(String(40), primary_key=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    record_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
