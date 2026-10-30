import asyncio
import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.research import MemoryWrite, create_memory, delete_memory
from app.harness import workflow as workflow_module
from app.harness.budget import TurnToolBudget
from app.harness.checkpointer import append_direct_turn
from app.harness.evidence import audit_final_answer, normalize_tool_evidence
from app.harness.intent import ResearchIntent, classify_intent
from fastapi import HTTPException
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel


class SymbolInput(BaseModel):
    symbol: str


@pytest.mark.asyncio
async def test_tool_budget_coalesces_identical_concurrent_calls():
    calls = 0
    release = asyncio.Event()

    async def fetch(symbol: str) -> dict[str, str]:
        nonlocal calls
        calls += 1
        await release.wait()
        return {"symbol": symbol, "source": "test"}

    tool = StructuredTool.from_function(
        coroutine=fetch,
        name="get_price_history",
        description="test history",
        args_schema=SymbolInput,
    )
    budget = TurnToolBudget(max_cost=4, max_calls=2)
    wrapped = budget.wrap([tool])[0]
    first = asyncio.create_task(wrapped.ainvoke({"symbol": "600519"}))
    await asyncio.sleep(0)
    second = asyncio.create_task(wrapped.ainvoke({"symbol": "600519"}))
    await asyncio.sleep(0)
    release.set()
    result_a, result_b = await asyncio.gather(first, second)

    assert calls == 1
    assert result_a["symbol"] == result_b["symbol"] == "600519"
    assert budget.used_calls == 1
    assert budget.used_cost == 2
    assert result_a.get("_harness", {}).get("deduplicated") or result_b.get(
        "_harness", {}
    ).get("deduplicated")


@pytest.mark.asyncio
async def test_tool_budget_rejects_calls_that_exceed_weighted_limit():
    async def fetch(symbol: str) -> dict[str, str]:
        return {"symbol": symbol}

    tool = StructuredTool.from_function(
        coroutine=fetch,
        name="get_price_history",
        description="test history",
        args_schema=SymbolInput,
    )
    budget = TurnToolBudget(max_cost=1, max_calls=8)
    result = await budget.wrap([tool])[0].ainvoke({"symbol": "600519"})

    assert result["budget_exhausted"] is True
    assert budget.used_cost == 0
    assert budget.used_calls == 0


@pytest.mark.asyncio
async def test_cancelled_tool_waiter_does_not_cancel_shared_provider_call():
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetch(symbol: str) -> dict[str, str]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"symbol": symbol}

    tool = StructuredTool.from_function(
        coroutine=fetch,
        name="get_price_history",
        description="test history",
        args_schema=SymbolInput,
    )
    budget = TurnToolBudget(max_cost=4, max_calls=2)
    wrapped = budget.wrap([tool])[0]
    cancelled_waiter = asyncio.create_task(wrapped.ainvoke({"symbol": "600519"}))
    await started.wait()
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter

    remaining_waiter = asyncio.create_task(wrapped.ainvoke({"symbol": "600519"}))
    release.set()
    result = await remaining_waiter

    assert result["symbol"] == "600519"
    assert calls == 1
    assert budget.used_calls == 1


def test_tool_evidence_normalizes_metadata_and_reports_missing_fields():
    evidence = normalize_tool_evidence("get_current_quote", {
        "source": "Xueqiu",
        "observed_at": "2026-10-13T02:00:00+00:00",
        "units": {"price": "CNY/share"},
        "quote": {"price": 1600, "change_pct": None},
    })

    assert evidence["source"] == "Xueqiu"
    assert evidence["observed_at"] == "2026-10-13T02:00:00+00:00"
    assert evidence["missing_fields"] == ["quote.change_pct"]
    assert evidence["units"]["price"] == "CNY/share"


def test_tool_evidence_remains_bounded_for_oversized_provider_metadata():
    evidence = normalize_tool_evidence(
        "get_company_research_data",
        {"units": {f"field_{index}": "x" * 1000 for index in range(100)}},
    )

    assert len(json.dumps(evidence, ensure_ascii=False).encode("utf-8")) <= 12_000


def test_answer_audit_rejects_unknown_evidence_ids_and_discloses_empty_research():
    answer = audit_final_answer(
        "价格经过核对 [E1]，行业判断见 [E9]。",
        [{"id": "E1", "status": "complete"}],
        research=True,
    )
    empty = audit_final_answer("请继续观察。", [], research=True)

    assert "[E1]" in answer
    assert "[E9]" not in answer
    assert "无法对应" in answer
    assert empty.startswith("本轮未取得可用的研究数据")


class MustNotClassify:
    def with_structured_output(self, _schema):
        raise AssertionError("high-confidence rules should skip classifier calls")


@pytest.mark.asyncio
async def test_intent_router_uses_safe_rule_fast_paths():
    assert await classify_intent("谢谢", [], MustNotClassify()) == ResearchIntent.CONVERSATION
    assert await classify_intent("今天 600519 的行情", [], MustNotClassify()) == ResearchIntent.RESEARCH


def test_memory_selection_respects_scope_expiry_and_superseded_status():
    current = date(2026, 10, 13)
    scoped = SimpleNamespace(
        kind="hypothesis", statement="公司现金流可能改善", supporting_evidence=[],
        counter_evidence=[], instrument_codes=["600519"], valid_until=date(2026, 10, 20),
        status="active",
    )
    expired = SimpleNamespace(
        kind="hypothesis", statement="现金流仍待核实", supporting_evidence=[],
        counter_evidence=[], instrument_codes=["600519"], valid_until=date(2026, 10, 12),
        status="active",
    )
    superseded = SimpleNamespace(
        kind="hypothesis", statement="现金流旧假设", supporting_evidence=[],
        counter_evidence=[], instrument_codes=["600519"], valid_until=None,
        status="superseded",
    )

    from app.harness.agent import _select_relevant_memories

    assert _select_relevant_memories(
        [scoped, expired, superseded],
        "贵州茅台现金流",
        instrument_names={"600519": "贵州茅台"},
        as_of=current,
    ) == [scoped]
    assert _select_relevant_memories(
        [scoped], "宁德时代现金流", instrument_names={"600519": "贵州茅台"}, as_of=current
    ) == []


class FakeStructuredRunnable:
    def __init__(self, result: dict[str, str]):
        self.result = result

    def with_config(self, _config):
        return self

    async def ainvoke(self, _prompt):
        return self.result


class FakeClassifier:
    def __init__(self, result: dict[str, str]):
        self.result = result

    def with_structured_output(self, _schema):
        return FakeStructuredRunnable(self.result)


@pytest.mark.asyncio
async def test_intent_router_uses_structured_fallback_and_fails_open_to_research():
    education = await classify_intent("PE 是什么意思？", [], FakeClassifier({"intent": "education"}))
    assert education == ResearchIntent.EDUCATION

    class BrokenClassifier:
        def with_structured_output(self, _schema):
            raise RuntimeError("classification endpoint unavailable")

    fallback = await classify_intent("帮我看看这个判断", [], BrokenClassifier())
    assert fallback == ResearchIntent.RESEARCH


class FakeResearchGraph:
    async def ainvoke(self, payload: dict[str, Any], config=None):
        messages = payload["messages"]
        return {
            "messages": [
                *messages,
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "get_price_history",
                        "args": {"symbol": "600519"},
                        "id": "call-1",
                        "type": "tool_call",
                    }],
                ),
                ToolMessage(
                    content=json.dumps({
                        "symbol": "600519", "source": "test market data",
                        "data_as_of": "2026-10-12", "bars": [{"close": 100}],
                    }),
                    tool_call_id="call-1",
                    name="get_price_history",
                ),
                AIMessage(content="这是不能发给用户的 ReAct 草稿。"),
            ]
        }


@pytest.mark.asyncio
async def test_conversation_intent_bypasses_research_tools(monkeypatch):
    class TrackingResearchGraph:
        calls = 0

        async def ainvoke(self, payload: dict[str, Any], config=None):
            self.calls += 1
            return {"messages": payload["messages"]}

    research_graph = TrackingResearchGraph()
    monkeypatch.setattr(
        workflow_module,
        "create_research_model",
        lambda: FakeListChatModel(responses=["不客气，有需要可以继续聊。"]),
    )
    monkeypatch.setattr(
        workflow_module,
        "build_research_agent",
        lambda *_args, **_kwargs: research_graph,
    )

    async def no_memory(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(workflow_module, "_memory_context", no_memory)
    app = workflow_module.build_research_workflow(
        "user-1", object(), None, MemorySaver()
    )
    config = {"configurable": {"thread_id": "conversation-test"}}
    await app.ainvoke(
        {"messages": [HumanMessage(content="谢谢")]}, config=config
    )
    state = await app.aget_state(config)

    assert research_graph.calls == 0
    assert state.values["intent"] == ResearchIntent.CONVERSATION.value
    assert state.values["messages"][-1].content == "不客气，有需要可以继续聊。"


@pytest.mark.asyncio
async def test_research_workflow_streams_only_final_answer_and_drops_worker_draft(monkeypatch):
    monkeypatch.setattr(
        workflow_module,
        "create_research_model",
        lambda: FakeListChatModel(responses=["最终结论引用 [E1]。"]),
    )
    monkeypatch.setattr(
        workflow_module,
        "build_research_agent",
        lambda *_args, **_kwargs: FakeResearchGraph(),
    )

    async def no_memory(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(workflow_module, "_memory_context", no_memory)
    app = workflow_module.build_research_workflow(
        "user-1", object(), None, MemorySaver()
    )
    config = {
        "configurable": {"thread_id": "workflow-test"},
        "recursion_limit": 24,
    }
    events = [
        event async for event in app.astream_events(
            {"messages": [HumanMessage(content="查 600519 今天行情")]},
            config=config,
            version="v2",
        )
    ]

    final_nodes = [
        event for event in events
        if event["event"] == "on_chain_end"
        and event.get("metadata", {}).get("langgraph_node") == "final_answer"
    ]
    assert final_nodes
    assert "intent_router" in {
        event.get("metadata", {}).get("langgraph_node")
        for event in events if event["event"] == "on_chain_start"
    }
    state = await app.aget_state(config)
    messages = state.values["messages"]
    assert messages[-1].content == "最终结论引用 [E1]。"
    assert all("ReAct 草稿" not in getattr(message, "content", "") for message in messages)
    final_output = final_nodes[-1]["data"]["output"]
    assert final_output["messages"][-1].content == "最终结论引用 [E1]。"


@pytest.mark.asyncio
async def test_direct_reply_advances_langgraph_message_checkpoint():
    saver = MemorySaver()
    await append_direct_turn(
        saver,
        "direct-turn-test",
        [
            HumanMessage(content="贵州茅台", id="user-1"),
            AIMessage(content="识别到贵州茅台。", id="assistant-1"),
        ],
    )
    checkpoint = await saver.aget_tuple({"configurable": {"thread_id": "direct-turn-test"}})

    assert checkpoint is not None
    messages = checkpoint.checkpoint["channel_values"]["messages"]
    assert [message.content for message in messages] == ["贵州茅台", "识别到贵州茅台。"]


@pytest.mark.asyncio
async def test_memory_revision_keeps_history_and_marks_previous_as_superseded():
    previous = SimpleNamespace(id="old-memory", owner_id="user-1", status="active")

    class Session:
        added = None

        async def scalar(self, _query):
            return previous

        def add(self, value):
            self.added = value

        async def commit(self):
            return None

        async def refresh(self, _value):
            return None

    session = Session()
    request = MemoryWrite(
        kind="hypothesis",
        statement="贵州茅台现金流趋势出现变化",
        attribution="user",
        instrument_codes=["600519"],
        valid_until=date(2026, 12, 31),
        supersedes_id="old-memory",
    )

    created = await create_memory(request, SimpleNamespace(id="user-1"), session)

    assert previous.status == "superseded"
    assert session.added.instrument_codes == ["600519"]
    assert session.added.supersedes_id == "old-memory"
    assert created["statement"] == request.statement


@pytest.mark.asyncio
async def test_memory_revision_cannot_supersede_another_users_memory():
    class Session:
        added = None

        async def scalar(self, _query):
            return None

        def add(self, value):
            self.added = value

    session = Session()
    request = MemoryWrite(
        kind="hypothesis", statement="跨用户记录", supersedes_id="private-memory"
    )

    with pytest.raises(HTTPException) as error:
        await create_memory(request, SimpleNamespace(id="user-2"), session)

    assert error.value.status_code == 404
    assert session.added is None


@pytest.mark.asyncio
async def test_deleting_active_revision_restores_previous_memory():
    previous = SimpleNamespace(id="old-memory", owner_id="user-1", status="superseded")
    current = SimpleNamespace(
        id="new-memory", owner_id="user-1", status="active", supersedes_id="old-memory"
    )

    class Session:
        calls = 0
        deleted = None

        async def scalar(self, _query):
            self.calls += 1
            return current if self.calls == 1 else previous

        async def scalars(self, _query):
            return SimpleNamespace(all=list)

        async def delete(self, value):
            self.deleted = value

        async def commit(self):
            return None

    session = Session()
    await delete_memory("new-memory", SimpleNamespace(id="user-1"), session)

    assert previous.status == "active"
    assert session.deleted is current


@pytest.mark.asyncio
async def test_deleting_superseded_memory_preserves_chain_for_later_restore():
    ancestor = SimpleNamespace(id="base-memory", owner_id="user-1", status="superseded")
    middle = SimpleNamespace(
        id="middle-memory", owner_id="user-1", status="superseded", supersedes_id="base-memory"
    )
    current = SimpleNamespace(
        id="current-memory", owner_id="user-1", status="active", supersedes_id="middle-memory"
    )

    class Session:
        def __init__(self):
            self.scalar_results = [middle, current, ancestor]
            self.successor_results = [[current], []]
            self.deleted = []

        async def scalar(self, _query):
            return self.scalar_results.pop(0)

        async def scalars(self, _query):
            values = self.successor_results.pop(0)
            return SimpleNamespace(all=lambda: values)

        async def delete(self, value):
            self.deleted.append(value)

        async def commit(self):
            return None

    session = Session()

    await delete_memory("middle-memory", SimpleNamespace(id="user-1"), session)
    assert current.supersedes_id == "base-memory"

    await delete_memory("current-memory", SimpleNamespace(id="user-1"), session)

    assert ancestor.status == "active"
    assert session.deleted == [middle, current]
