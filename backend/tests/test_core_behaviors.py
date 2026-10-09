import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.config import Settings
from app.data.market_service import MarketDataService, _utc_iso, _utc_naive
from app.data.providers.akshare import _market_timestamp
from app.harness import locks
from app.harness.agent import _select_relevant_memories, summarize_tool_output
from app.harness.checkpointer import ResearchAsyncMySaver


def test_research_checkpointer_pins_json_table_channel_collation():
    query = ResearchAsyncMySaver._select_sql("WHERE thread_id = %(thread_id)s")

    assert "COLLATE utf8mb4_unicode_ci PATH '$'" in query
    assert "CHARACTER SET utf8mb4 PATH '$'" not in query


def test_market_snapshot_date_requires_a_real_or_index_date():
    friday = date(2026, 10, 9)
    monday = date(2026, 10, 12)

    assert MarketDataService._snapshot_trade_date([{"date": "2026-10-12 15:00:00"}], friday) == monday
    assert MarketDataService._snapshot_trade_date([{}], friday) == friday
    assert MarketDataService._snapshot_trade_date([{}], None) is None
    assert MarketDataService._snapshot_trade_date(
        [{"date": "2026-10-09T16:30:00+00:00"}], friday
    ) == date(2026, 10, 10)


def test_provider_timestamps_use_the_shanghai_timezone():
    timestamp = _market_timestamp("2026-10-09T16:30:00+00:00")

    assert timestamp is not None
    assert timestamp.isoformat() == "2026-10-10T00:30:00+08:00"


def test_aware_disclosure_timestamps_are_stored_and_serialized_as_utc():
    disclosure_time = datetime.fromisoformat("2026-10-09T16:30:00+08:00")

    expected_naive_utc = datetime.fromisoformat("2026-10-09T08:30:00")
    assert _utc_naive(disclosure_time) == expected_naive_utc
    assert _utc_iso(disclosure_time) == "2026-10-09T08:30:00+00:00"
    assert _utc_iso(expected_naive_utc) == "2026-10-09T08:30:00+00:00"


def test_market_snapshot_number_rejects_non_finite_values():
    assert MarketDataService._snapshot_number({"change": "1,234.5%"}, "change") == 1234.5
    assert MarketDataService._snapshot_number({"change": "NaN"}, "change") is None
    assert MarketDataService._snapshot_number({"change": "invalid"}, "change") is None


def test_legacy_environment_names_do_not_configure_new_system(monkeypatch):
    names = (
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_DATABASE",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "NEWAPI_KEY",
        "NEWAPI_ENDPOINT",
        "RESEARCH_MYSQL_HOST",
        "RESEARCH_MYSQL_PORT",
        "RESEARCH_MYSQL_DATABASE",
        "RESEARCH_MYSQL_USER",
        "RESEARCH_MYSQL_PASSWORD",
        "LLM_API_KEY",
        "LLM_BASE_URL",
    )
    for name in names:
        if name.startswith(("MYSQL_", "NEWAPI_")):
            monkeypatch.setenv(name, "legacy-value")
        else:
            monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)

    assert settings.mysql_host == "127.0.0.1"
    assert settings.mysql_database == "stock_research"
    assert settings.llm_api_key.get_secret_value() == ""
    assert settings.llm_base_url == ""


def test_memory_context_selects_preferences_and_matching_research():
    preference = SimpleNamespace(
        kind="preference",
        statement="偏好使用可核验的最新财报数据",
        supporting_evidence=[],
        counter_evidence=[],
    )
    matching = SimpleNamespace(
        kind="hypothesis",
        statement="600519 的现金流改善可能支持长期假设",
        supporting_evidence=[],
        counter_evidence=[],
    )
    unrelated = SimpleNamespace(
        kind="evidence",
        statement="另一个行业公司的短期风险观察",
        supporting_evidence=[],
        counter_evidence=[],
    )

    selected = _select_relevant_memories(
        [preference, matching, unrelated], "分析 600519 的现金流"
    )

    assert selected == [preference, matching]


@pytest.mark.asyncio
async def test_conversation_lock_serializes_and_releases_unused_entries():
    conversation_id = f"test-{uuid4()}"
    active = 0
    maximum_active = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def run():
        nonlocal active, maximum_active
        async with locks.conversation_lock(conversation_id):
            active += 1
            maximum_active = max(maximum_active, active)
            entered.set()
            await release.wait()
            active -= 1

    first = asyncio.create_task(run())
    await entered.wait()
    second = asyncio.create_task(run())
    await asyncio.sleep(0)
    assert active == 1
    release.set()
    await asyncio.gather(first, second)

    assert maximum_active == 1
    assert conversation_id not in locks._conversation_locks


def test_chip_trace_discloses_missing_price_distribution():
    summary, source, data_as_of, cache_status, error = summarize_tool_output(
        {
            "records": [{"trade_date": "2026-10-09"}],
            "source": "Eastmoney",
            "data_as_of": "2026-10-09",
            "cache_status": "database",
            "distribution_available": False,
        }
    )

    assert "未提供可还原的筹码价位分布" in summary
    assert (source, data_as_of, cache_status, error) == (
        "Eastmoney",
        "2026-10-09",
        "database",
        None,
    )


def test_recent_trade_trace_distinguishes_retrieval_from_trade_time():
    summary, source, data_as_of, cache_status, error = summarize_tool_output(
        {
            "trades": [{"成交时间": "14:59:58"}],
            "retrieved_at": "2026-10-09T07:00:00+00:00",
            "source": "AKShare",
            "cache_status": "hit",
        }
    )

    assert "接口读取时间 2026-10-09T07:00:00+00:00" in summary
    assert "成交发生时间以记录字段为准" in summary
    assert (source, data_as_of, cache_status, error) == ("AKShare", None, "hit", None)
