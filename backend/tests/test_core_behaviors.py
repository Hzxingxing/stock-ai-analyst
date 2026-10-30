import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from app.api import chat as chat_api
from app.api.chat import _is_standalone_instrument_query, _resolve_standalone_instrument
from app.config import Settings
from app.data.market_service import (
    MarketDataService,
    _market_overview_needs_refresh,
    _utc_iso,
    _utc_naive,
)
from app.data.providers import akshare as market_provider
from app.data.providers.akshare import _market_timestamp
from app.harness import locks
from app.harness.agent import _select_relevant_memories, summarize_tool_output
from app.harness.checkpointer import ResearchAsyncMySaver
from langgraph.checkpoint.memory import MemorySaver


def test_standalone_instrument_query_detection_skips_chat_and_full_questions():
    assert _is_standalone_instrument_query("游族网络")
    assert _is_standalone_instrument_query("002174")
    assert not _is_standalone_instrument_query("继续")
    assert not _is_standalone_instrument_query("___")
    assert not _is_standalone_instrument_query("分析游族网络近期走势")
    assert not _is_standalone_instrument_query("游族网络表现如何")
    assert not _is_standalone_instrument_query("游族网络能涨吗")
    assert not _is_standalone_instrument_query("人工智能")
    assert not _is_standalone_instrument_query("游戏板块")


@pytest.mark.asyncio
async def test_standalone_instrument_resolution_returns_specific_follow_up():
    requested = []

    async def search(query):
        requested.append(query)
        return [{
            "code": "SZSE:002174",
            "name": "游族网络",
            "instrument_type": "equity",
            "provider_symbol": "002174",
        }]

    result = await _resolve_standalone_instrument("游族网络", search)

    assert requested == ["游族网络"]
    assert result is not None
    assert result["matches"][0]["provider_symbol"] == "002174"
    assert "游族网络" in result["reply"]
    assert "SZSE:002174" in result["reply"]
    assert "近期走势、财报公告" in result["reply"]


@pytest.mark.asyncio
async def test_standalone_instrument_resolution_asks_for_code_when_not_found():
    async def search(_query):
        return []

    result = await _resolve_standalone_instrument("未知公司", search)

    assert result is not None
    assert result["matches"] == []
    assert "六位代码" in result["reply"]


@pytest.mark.asyncio
async def test_standalone_sector_term_skips_stock_name_preflight():
    requested = []

    async def search(_query):
        requested.append(_query)
        return [{
            "code": "SZSE:300123",
            "name": "某半导体设备公司",
            "instrument_type": "equity",
            "provider_symbol": "300123",
        }]

    result = await _resolve_standalone_instrument("半导体", search)

    assert result is None
    assert requested == []


@pytest.mark.asyncio
async def test_chat_stream_resolves_bare_stock_name_without_calling_model(monkeypatch):
    conversation = SimpleNamespace(title="新研究", updated_at=None)
    records = {}

    class FakeSession:
        async def scalar(self, _query):
            return conversation

        def add_all(self, items):
            records.update({item.id: item for item in items})

        def add(self, item):
            records[item.id] = item

        async def commit(self):
            return None

        async def get(self, _model, record_id):
            return records.get(record_id)

    class FakeSessionContext:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(chat_api, "SessionFactory", FakeSessionContext)

    async def search_instruments(_service, query):
        assert query == "游族网络"
        return [{
            "code": "SZSE:002174",
            "name": "游族网络",
            "instrument_type": "equity",
            "provider_symbol": "002174",
        }]

    monkeypatch.setattr(MarketDataService, "search_instruments", search_instruments)

    def unexpected_model_call(*_args, **_kwargs):
        raise AssertionError("bare instrument lookup should not call the LLM")

    monkeypatch.setattr(chat_api, "build_research_workflow", unexpected_model_call)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(checkpointer=MemorySaver(), redis=None)
        )
    )
    response = await chat_api.stream_chat(
        chat_api.ChatRequest(conversation_id="conversation-1", content="游族网络"),
        request,
        SimpleNamespace(id="user-1"),
        FakeSession(),
    )
    events = "".join([chunk async for chunk in response.body_iterator])

    assert '"name": "标的检索"' in events
    assert '"status": "complete"' in events
    assert "游族网络" in events
    assert "SZSE:002174" in events
    assert "event: done" in events
    assistant = next(item for item in records.values() if getattr(item, "role", None) == "assistant")
    assert assistant.metadata_json == {"status": "complete"}
    execution = next(item for item in records.values() if hasattr(item, "tool_name"))
    assert execution.tool_name == "标的检索"
    assert execution.status == "complete"


def test_research_checkpointer_pins_json_table_channel_collation():
    query = ResearchAsyncMySaver._select_sql("WHERE thread_id = %(thread_id)s")

    assert "COLLATE utf8mb4_unicode_ci PATH '$'" in query
    assert "CHARACTER SET utf8mb4 PATH '$'" not in query


def test_market_snapshot_date_requires_a_real_or_index_date():
    friday = date(2026, 10, 9)
    monday = date(2026, 10, 12)

    assert MarketDataService._snapshot_trade_date([{"date": "2026-10-12 15:00:00"}], friday) == monday
    assert MarketDataService._snapshot_has_trade_date([{"date": "2026-10-12 15:00:00"}])
    assert not MarketDataService._snapshot_has_trade_date([{}])
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


def test_market_snapshot_statistics_accept_canonical_tencent_fields():
    statistics = MarketDataService._market_snapshot_statistics([
        {"change_pct": 1.25, "volume": 10, "amount": 100000},
        {"change_pct": -0.5, "volume": 20, "amount": 200000},
        {"change_pct": 0, "volume": 30, "amount": 300000},
    ])

    assert statistics == {
        "total_stocks": 3,
        "advances": 1,
        "declines": 1,
        "unchanged": 1,
        "total_volume": 60,
        "total_amount": 600000,
    }


def test_market_snapshot_statistics_do_not_report_partial_turnover_totals():
    statistics = MarketDataService._market_snapshot_statistics([
        {"change_pct": 1, "volume": 10, "amount": 100000},
        {"change_pct": -1, "volume": None, "amount": None},
    ])

    assert statistics["total_stocks"] == 2
    assert statistics["total_volume"] is None
    assert statistics["total_amount"] is None


def test_sina_index_normalization_derives_change_and_keeps_missing_amount():
    frame = pd.DataFrame([
        {"date": "2026-10-08", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 500},
        {"date": "2026-10-09", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 600},
    ])

    records = market_provider.normalize_daily_frame(frame, derive_change_pct=True)

    assert records[0]["change_pct"] is None
    assert records[1]["change_pct"] == pytest.approx(2)
    assert records[1]["amount"] is None


def test_sina_equity_daily_normalizes_volume_and_turnover(monkeypatch):
    import akshare

    requested = {}

    def fake_daily(**kwargs):
        requested.update(kwargs)
        return pd.DataFrame([
            {
                "date": "2026-10-08", "open": 9.5, "high": 9.7, "low": 9.4,
                "close": 9.6, "volume": 10000, "amount": 96000, "turnover": 0.001,
            },
            {
                "date": "2026-10-09", "open": 9.7, "high": 9.8, "low": 9.5,
                "close": 9.7, "volume": 20000, "amount": 194000, "turnover": 0.002,
            },
        ])

    monkeypatch.setattr(akshare, "stock_zh_a_daily", fake_daily)
    payload = market_provider.fetch_daily_bars(
        "600000", "equity", date(2026, 10, 9), date(2026, 10, 9), "qfq"
    )

    assert requested["symbol"] == "sh600000"
    assert requested["adjust"] == "qfq"
    assert payload["source"] == market_provider.SINA_EQUITY_DAILY_SOURCE
    assert payload["records"] == [{
        "trade_date": date(2026, 10, 9), "open": 9.7, "high": 9.8, "low": 9.5,
        "close": 9.7, "volume": 200, "amount": 194000, "change_pct": pytest.approx(1.0416667),
        "turnover_rate": 0.2,
    }]


def test_sina_index_provider_filters_range_after_deriving_change(monkeypatch):
    import akshare

    frame = pd.DataFrame([
        {"date": "2026-10-08", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 500},
        {"date": "2026-10-09", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 600},
    ])
    monkeypatch.setattr(akshare, "stock_zh_index_daily", lambda symbol: frame)

    payload = market_provider.fetch_index_bars(
        "sh000001", date(2026, 10, 9), date(2026, 10, 9)
    )

    assert payload["source"] == market_provider.SINA_INDEX_DAILY_SOURCE
    assert len(payload["records"]) == 1
    assert payload["records"][0]["change_pct"] == pytest.approx(2)
    assert payload["records"][0]["volume"] == 6
    assert payload["records"][0]["amount"] is None
    assert "100 shares per lot" in payload["units"]["volume"]


@pytest.mark.parametrize(
    ("adjustment", "data_key", "adjustment_param"),
    [
        ("qfq", "qfqday", "qfq"),
        ("hfq", "hfqday", "hfq"),
        ("none", "day", ""),
    ],
)
def test_tencent_beijing_daily_normalizes_and_filters_data(
    monkeypatch, adjustment, data_key, adjustment_param
):
    import json
    from io import BytesIO
    from urllib.parse import parse_qs, urlparse

    import akshare  # noqa: F401 - provider imports this before dispatching by exchange

    requested = {}
    rows = [
        ["2026-10-08", "9.50", "9.80", "9.85", "9.45", "7061", "0", "0.45", "992.37"],
        ["2026-10-09", "9.80", "10.00", "10.10", "9.70", "8000", "0", "0.50", "1200.00"],
    ]

    def fake_urlopen(request, timeout):
        requested["timeout"] = timeout
        query = parse_qs(urlparse(request.full_url).query)
        requested.update(query)
        callback = query["_var"][0]
        payload = {"code": 0, "data": {"bj920000": {data_key: rows}}}
        return BytesIO(f"{callback}={json.dumps(payload)};".encode())

    monkeypatch.setattr(market_provider, "urlopen", fake_urlopen)
    payload = market_provider.fetch_daily_bars(
        "920000", "equity", date(2026, 10, 9), date(2026, 10, 9), adjustment
    )

    assert requested["timeout"] == 10
    assert requested["_var"] == [f"kline_day{adjustment_param}2026"]
    assert requested["param"] == [
        f"bj920000,day,2026-09-25,2026-10-09,640,{adjustment_param}"
    ]
    assert payload["source"] == market_provider.TENCENT_BEIJING_EQUITY_DAILY_SOURCE
    assert payload["records"] == [{
        "trade_date": date(2026, 10, 9), "open": 9.8, "close": 10.0,
        "high": 10.1, "low": 9.7, "volume": 8000,
        "amount": 12_000_000, "change_pct": pytest.approx(2.0408163),
        "turnover_rate": 0.5,
    }]


def test_tencent_beijing_daily_partitions_cross_year_ranges_without_overlap(monkeypatch):
    import json
    from io import BytesIO
    from urllib.parse import parse_qs, urlparse

    import akshare  # noqa: F401 - provider imports this before dispatching by exchange

    requested = []

    def fake_urlopen(request, timeout):
        query = parse_qs(urlparse(request.full_url).query)
        requested.append(query["param"][0])
        year = "2025" if "2025" in query["_var"][0] else "2026"
        payload = {"code": 0, "data": {"bj920000": {"qfqday": []}}}
        if year == "2025":
            payload["data"]["bj920000"]["qfqday"] = [
                ["2025-12-31", "10", "10", "10", "10", "500", "0", "0.2", "50"]
            ]
        else:
            payload["data"]["bj920000"]["qfqday"] = [
                ["2026-01-02", "10", "11", "11", "10", "600", "0", "0.3", "60"]
            ]
        callback = query["_var"][0]
        return BytesIO(f"{callback}={json.dumps(payload)};".encode())

    monkeypatch.setattr(market_provider, "urlopen", fake_urlopen)
    payload = market_provider.fetch_daily_bars(
        "920000", "equity", date(2026, 1, 1), date(2026, 1, 3), "qfq"
    )

    assert requested == [
        "bj920000,day,2025-12-18,2025-12-31,640,qfq",
        "bj920000,day,2026-01-01,2026-01-03,640,qfq",
    ]
    assert [row["trade_date"] for row in payload["records"]] == [date(2026, 1, 2)]
    assert payload["records"][0]["change_pct"] == pytest.approx(10)


@pytest.mark.parametrize(
    ("adjustment", "available_key"),
    [("qfq", "day"), ("hfq", "qfqday"), ("none", "hfqday")],
)
def test_tencent_beijing_daily_does_not_fall_back_to_another_adjustment(
    monkeypatch, adjustment, available_key
):
    import json
    from io import BytesIO

    import akshare  # noqa: F401 - provider imports this before dispatching by exchange

    def fake_urlopen(request, timeout):
        payload = {"code": 0, "data": {"bj920000": {available_key: []}}}
        return BytesIO(f"callback={json.dumps(payload)};".encode())

    monkeypatch.setattr(market_provider, "urlopen", fake_urlopen)

    with pytest.raises(ValueError, match=f"缺少 {adjustment} 数据"):
        market_provider.fetch_daily_bars(
            "bj920000", "equity", date(2026, 10, 9), date(2026, 10, 9), adjustment
        )


def test_tencent_snapshot_normalizes_turnover_to_cny_and_volume_to_lots(monkeypatch):
    import akshare

    frame = pd.DataFrame([{
        "code": "sh600000", "name": "浦发银行", "zdf": "-1.65",
        "volume": "947958.00", "turnover": "91531",
    }])
    monkeypatch.setattr(akshare, "stock_zh_a_spot_tx", lambda: frame)

    payload = market_provider.fetch_market_snapshot()

    assert payload["source"] == market_provider.TENCENT_MARKET_SNAPSHOT_SOURCE
    assert payload["records"] == [{
        "code": "sh600000", "name": "浦发银行", "change_pct": -1.65,
        "volume": 947958, "amount": 915310000,
    }]


def test_weekly_aggregation_keeps_unavailable_metrics_null_and_tracks_source():
    result = MarketDataService._aggregate([
        {
            "date": "2026-10-08", "open": 100, "high": 101, "low": 99,
            "close": 100, "volume": 500, "amount": None, "change_pct": None,
            "turnover_rate": None, "source": market_provider.SINA_INDEX_DAILY_SOURCE,
        },
        {
            "date": "2026-10-09", "open": 101, "high": 103, "low": 100,
            "close": 102, "volume": 600, "amount": None, "change_pct": 2,
            "turnover_rate": None, "source": market_provider.SINA_INDEX_DAILY_SOURCE,
        },
    ], "weekly")

    assert result[0]["volume"] == 1100
    assert result[0]["amount"] is None
    assert result[0]["turnover_rate"] is None
    assert result[0]["source"] == market_provider.SINA_INDEX_DAILY_SOURCE


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


def test_limit_pool_counts_empty_success_as_zero_and_keeps_failed_field_missing(monkeypatch):
    import akshare as ak

    monkeypatch.setattr(ak, "stock_zt_pool_em", lambda date: pd.DataFrame({"代码": ["600519"]}))

    def fail_limit_down(date):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(ak, "stock_zt_pool_dtgc_em", fail_limit_down)
    partial = market_provider.fetch_market_limit_statistics(date(2026, 10, 12))
    monkeypatch.setattr(ak, "stock_zt_pool_dtgc_em", lambda date: pd.DataFrame())
    complete = market_provider.fetch_market_limit_statistics(date(2026, 10, 12))

    assert partial["limit_up"] == 1
    assert partial["limit_down"] is None
    assert "limit_down" in partial["errors"]
    assert complete["limit_down"] == 0


def test_market_overview_retries_missing_limit_counts_without_hot_looping():
    now = datetime(2026, 10, 13, 4, 0, tzinfo=UTC).replace(tzinfo=None)
    just_checked = SimpleNamespace(
        collected_at=now - timedelta(minutes=10), limit_up=None, limit_down=2,
        trade_date_source="SSE:000001 stored daily bars",
    )
    retry_due = SimpleNamespace(
        collected_at=now - timedelta(minutes=16), limit_up=None, limit_down=2,
        trade_date_source="SSE:000001 stored daily bars",
    )
    recent_complete = SimpleNamespace(
        collected_at=now - timedelta(hours=1), limit_up=45, limit_down=2,
        trade_date_source="Tencent snapshot date field",
    )
    missing_date_source = SimpleNamespace(
        collected_at=now - timedelta(minutes=1), limit_up=45, limit_down=2,
        trade_date_source=None,
    )

    assert not _market_overview_needs_refresh(just_checked, now)
    assert _market_overview_needs_refresh(retry_due, now)
    assert not _market_overview_needs_refresh(recent_complete, now)
    assert _market_overview_needs_refresh(missing_date_source, now)


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
