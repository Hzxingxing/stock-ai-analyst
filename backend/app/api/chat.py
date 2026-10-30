import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.data.market_service import MarketDataService
from app.db.models import Conversation, ConversationMessage, ToolExecution, User, new_id
from app.db.session import SessionFactory, get_session
from app.harness.agent import (
    safe_tool_input,
    structured_tool_output,
    summarize_tool_output,
    tool_retry_count,
)
from app.harness.checkpointer import append_direct_turn
from app.harness.evidence import normalize_tool_evidence
from app.harness.locks import conversation_lock
from app.harness.workflow import build_research_workflow

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])
MAX_AGENT_RECURSION = 18
MAX_RESEARCH_SECONDS = 180


class ChatRequest(BaseModel):
    conversation_id: str
    content: str = Field(min_length=1, max_length=12000)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


_NON_INSTRUMENT_SHORT_INPUTS = {
    "你好", "您好", "在吗", "谢谢", "好的", "可以", "继续", "明白", "收到",
    "早上好", "晚上好", "辛苦了", "没问题", "ok", "hello", "hi", "help",
    "thanks", "thankyou", "continue", "okay",
}
_RESEARCH_INTENT_TERMS = (
    "分析", "走势", "行情", "公告", "财报", "研究", "近期", "最近", "今天",
    "怎么样", "怎么", "如何", "什么", "表现", "介绍", "查", "看看", "帮", "请",
    "估值", "市值", "营收", "利润", "基本面", "资金", "筹码", "风险", "板块",
    "行业", "概念", "趋势", "涨跌", "成交", "分时", "日线", "周线", "月线",
    "股价", "价格", "现价", "现在", "支撑", "压力", "对比", "比较", "预测",
    "后市", "值得", "能否", "是否", "为什么", "吗", "呢", "么", "涨", "跌", "买", "卖",
)
_STANDALONE_SECTOR_QUERIES = {
    "半导体", "人工智能", "机器人", "新能源", "光伏", "军工", "算力", "云计算",
    "有色金属", "消费电子", "电力设备",
}


def _is_standalone_instrument_query(content: str) -> bool:
    query = content.strip()
    if (
        query.casefold() in _NON_INSTRUMENT_SHORT_INPUTS
        or not 3 <= len(query) <= 16
        or any(term in query for term in _RESEARCH_INTENT_TERMS)
        or query in _STANDALONE_SECTOR_QUERIES
        or query.endswith(("板块", "行业", "概念"))
    ):
        return False
    return (
        re.fullmatch(r"[\u3400-\u9fffA-Za-z0-9.:_-]+", query) is not None
        and re.search(r"[\u3400-\u9fffA-Za-z0-9]", query) is not None
    )


async def _resolve_standalone_instrument(
    content: str,
    search: Callable[[str], Awaitable[list[dict[str, str]]]],
) -> dict[str, object] | None:
    if not _is_standalone_instrument_query(content):
        return None
    matches = await search(content.strip())
    retry_count = getattr(matches, "retry_count", 0)
    provider_error = getattr(matches, "provider_error", False)
    query_key = re.sub(r"[^a-z0-9\u3400-\u9fff]", "", content.casefold())

    def matches_query(instrument: dict[str, str]) -> bool:
        identifiers = (
            instrument.get("name", ""),
            instrument.get("code", ""),
            instrument.get("provider_symbol", ""),
        )
        for identifier in identifiers:
            identifier_key = re.sub(r"[^a-z0-9\u3400-\u9fff]", "", identifier.casefold())
            if identifier_key == query_key or (
                content.strip().isdigit() and identifier_key.endswith(query_key)
            ):
                return True
        return False

    exact_matches = [item for item in matches if matches_query(item)]
    if not exact_matches and matches:
        return {
            "matches": matches, "reply": None, "resolution_type": "candidates",
            "retry_count": retry_count, "provider_error": provider_error,
        }
    if not exact_matches:
        if provider_error:
            reply = "标的目录数据源暂时不可用，当前无法确认这个名称。请提供六位代码或稍后重试。"
        else:
            reply = (
                f"我暂时没能把“{content.strip()}”匹配到明确的股票或指数。"
                "请补充六位代码或更完整的标的名称。"
            )
        return {
            "matches": [], "reply": reply,
            "resolution_type": "unavailable" if provider_error else "not_found",
            "retry_count": retry_count, "provider_error": provider_error,
        }
    if len(exact_matches) == 1:
        instrument = exact_matches[0]
        kind = "指数" if instrument.get("instrument_type") == "index" else "股票"
        name = instrument.get("name") or instrument.get("provider_symbol") or content.strip()
        code = instrument.get("code") or instrument.get("provider_symbol") or "代码未知"
        reply = (
            f"我识别到这是 **{name}**（{code}，{kind}）。\n\n"
            "你想先看近期走势、财报公告，还是讨论某个具体判断？"
        )
    else:
        candidates = exact_matches[:5]
        options = "\n".join(
            f"- {item.get('name', '未知名称')}（"
            f"{item.get('code', item.get('provider_symbol', '代码未知'))}）"
            for item in candidates
        )
        reply = f"我找到多个可能的标的，请确认你指的是哪一个：\n\n{options}"
    return {
        "matches": exact_matches, "reply": reply,
        "resolution_type": "exact" if len(exact_matches) == 1 else "multiple_exact",
        "retry_count": retry_count, "provider_error": provider_error,
    }


async def _history_messages_for_uncheckpointed_thread(
    conversation_id: str,
    current_message_ids: set[str],
) -> list[HumanMessage | AIMessage]:
    async with SessionFactory() as session:
        rows = (
            await session.scalars(
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.id.notin_(current_message_ids),
                )
                .order_by(ConversationMessage.created_at.desc())
                .limit(40)
            )
        ).all()
    messages: list[HumanMessage | AIMessage] = []
    for row in reversed(rows):
        if not row.content.strip():
            continue
        content = row.content
        if row.role == "assistant" and (row.metadata_json or {}).get("status") in {
            "error", "interrupted",
        }:
            content += "\n[上一轮研究未完整结束，以上内容可能不完整]"
        if row.role == "user":
            messages.append(HumanMessage(content=content))
        elif row.role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


async def _bounded_events(stream, timeout_seconds: int):
    async with asyncio.timeout(timeout_seconds):
        async for event in stream:
            yield event


async def _finalize_pending_tools(pending: dict[str, dict], message: str) -> list[dict]:
    closed = []
    for run_id, execution in list(pending.items()):
        elapsed = int((time.monotonic() - execution["started"]) * 1000)
        try:
            await _finish_tool_execution(
                execution["id"], message, None, None, None, message, elapsed,
                evidence=normalize_tool_evidence(execution["name"], {"error": message}),
            )
        except Exception:
            logger.exception("failed to finalize tool execution %s", execution["id"])
        closed.append({
            "id": execution["id"], "name": execution["name"],
            "output_summary": message, "error_summary": message, "status": "error",
            "evidence": normalize_tool_evidence(execution["name"], {"error": message}),
        })
        pending.pop(run_id, None)
    return closed


@router.post("/chat/stream")
async def stream_chat(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    conversation_id = payload.conversation_id
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="研究问题不能为空")
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.owner_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="研究会话不存在")
    await session.commit()
    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is None:
        raise HTTPException(status_code=503, detail="研究工作流尚未就绪")

    async def events() -> AsyncIterator[str]:
        user_message_id = new_id()
        assistant_message_id = new_id()
        pending: dict[str, dict] = {}
        answer: list[str] = []
        try:
            async with conversation_lock(conversation_id):
                async with SessionFactory() as write_session:
                    active_conversation = await write_session.scalar(
                        select(Conversation).where(
                            Conversation.id == conversation_id,
                            Conversation.owner_id == user.id,
                        )
                    )
                    if active_conversation is None:
                        yield _sse("error", {"message": "研究会话不存在"})
                        return
                    active_conversation.updated_at = time_to_datetime()
                    if active_conversation.title == "新研究":
                        active_conversation.title = content.splitlines()[0][:80] or "新研究"
                    write_session.add_all([
                        ConversationMessage(
                            id=user_message_id,
                            conversation_id=conversation_id,
                            role="user",
                            content=content,
                        ),
                        ConversationMessage(
                            id=assistant_message_id,
                            conversation_id=conversation_id,
                            role="assistant",
                            content="",
                        ),
                    ])
                    await write_session.commit()

                yield _sse(
                    "conversation",
                    {
                        "conversation_id": conversation_id,
                        "user_message_id": user_message_id,
                        "assistant_message_id": assistant_message_id,
                    },
                )
                yield _sse("status", {"phase": "researching", "label": "正在整理问题并核对数据"})
                if _is_standalone_instrument_query(content):
                    lookup_id = await _start_tool_execution(
                        owner_id=user.id,
                        conversation_id=conversation_id,
                        message_id=assistant_message_id,
                        tool_name="标的检索",
                        input_summary={"query": content},
                    )
                    lookup_key = f"instrument-search:{lookup_id}"
                    lookup_started = time.monotonic()
                    pending[lookup_key] = {
                        "id": lookup_id,
                        "name": "标的检索",
                        "started": lookup_started,
                    }
                    yield _sse(
                        "tool",
                        {
                            "id": lookup_id,
                            "name": "标的检索",
                            "input": {"query": content},
                            "status": "running",
                        },
                    )
                    lookup_error = None
                    lookup_warning = None
                    lookup_retry_count = 0
                    resolution = None
                    try:
                        market = MarketDataService(
                            SessionFactory, getattr(request.app.state, "redis", None)
                        )
                        resolution = await _resolve_standalone_instrument(
                            content, market.search_instruments
                        )
                        if resolution is None:
                            raise RuntimeError("standalone instrument query was not resolved")
                        matches = resolution["matches"]
                        lookup_retry_count = int(resolution.get("retry_count", 0))
                        if resolution.get("provider_error"):
                            lookup_warning = "标的目录数据源暂时不可用，候选结果可能不完整。"
                        candidate_labels = [
                            {
                                "name": re.sub(
                                    r"\s+", " ", str(item.get("name", "未知名称"))
                                ).strip()[:80],
                                "code": re.sub(
                                    r"\s+", " ", str(item.get(
                                        "code", item.get("provider_symbol", "代码未知")
                                    ))
                                ).strip()[:40],
                            }
                            for item in matches[:5]
                        ]
                        candidate_summary = "；".join(
                            f"{item['name']}（{item['code']}）"
                            for item in candidate_labels
                        )
                        resolution_type = resolution["resolution_type"]
                        if resolution_type == "unavailable":
                            output_summary = "标的目录数据源暂时不可用，当前无法确认标的。"
                        elif matches:
                            output_summary = (
                                f"标的检索返回 {len(matches)} 个候选：{candidate_summary}"
                            )
                        else:
                            output_summary = "标的检索未找到明确匹配结果。"
                    except Exception as exc:  # noqa: BLE001 - keep lookup failures visible in the trace
                        logger.warning("standalone instrument lookup failed (%s)", type(exc).__name__)
                        lookup_error = "标的目录暂时无法查询，请提供股票代码或稍后重试。"
                        output_summary = lookup_error

                    if lookup_warning and not (
                        resolution and resolution.get("resolution_type") == "unavailable"
                    ):
                        output_summary += f" 警告：{lookup_warning}"
                    evidence = normalize_tool_evidence(
                        "标的检索",
                        {
                            "matches": candidate_labels if resolution else [],
                            "source": "MySQL instruments + AKShare directory",
                            "warning": lookup_warning,
                            "error": lookup_error,
                        },
                    )
                    elapsed_ms = int((time.monotonic() - lookup_started) * 1000)
                    await _finish_tool_execution(
                        lookup_id,
                        output_summary,
                        "MySQL instruments + AKShare directory",
                        None,
                        None,
                        lookup_error,
                        elapsed_ms,
                        retry_count=lookup_retry_count,
                        evidence=evidence,
                    )
                    pending.pop(lookup_key, None)
                    yield _sse(
                        "tool",
                        {
                            "id": lookup_id,
                            "name": "标的检索",
                            "output_summary": output_summary,
                            "source": "MySQL instruments + AKShare directory",
                            "status": (
                                "error" if lookup_error else
                                "partial" if evidence.get("status") in {"partial", "empty"}
                                else "complete"
                            ),
                            "error_summary": lookup_error,
                            "retry_count": lookup_retry_count,
                            "evidence": evidence,
                        },
                    )
                    if lookup_error:
                        answer.append(lookup_error)
                        await _save_assistant_message(assistant_message_id, lookup_error, "error")
                        yield _sse("token", {"text": lookup_error})
                        yield _sse("error", {"message": lookup_error})
                        return

                    resolution_type = resolution["resolution_type"]
                    if resolution_type == "candidates":
                        candidate_lines = "\n".join(
                            f"- {item['name']}（{item['code']}）" for item in candidate_labels
                        )
                        direct_reply = (
                            f"我找到几个可能的标的，请确认你指的是哪一个：\n\n{candidate_lines}"
                        )
                    else:
                        direct_reply = str(resolution.get("reply") or "")
                    if lookup_warning and resolution_type != "unavailable":
                        direct_reply = f"{lookup_warning}\n\n{direct_reply}"
                    if not direct_reply:
                        direct_reply = (
                            "我暂时无法确认这个标的，请提供六位股票代码或更完整的名称。"
                        )

                    try:
                        await append_direct_turn(
                            checkpointer,
                            conversation_id,
                            [
                                HumanMessage(content=content, id=user_message_id),
                                AIMessage(content=direct_reply, id=assistant_message_id),
                            ],
                        )
                    except Exception:
                        logger.exception("failed to persist direct instrument turn in checkpoint")
                        failure = "本轮标的检索已完成，但会话状态未能保存，请稍后重试。"
                        await _save_assistant_message(
                            assistant_message_id, failure, "error", error_summary=failure
                        )
                        yield _sse("error", {"message": failure})
                        return
                    answer.append(direct_reply)
                    await _save_assistant_message(assistant_message_id, direct_reply, "complete")
                    yield _sse("token", {"text": direct_reply})
                    yield _sse(
                        "done",
                        {
                            "conversation_id": conversation_id,
                            "assistant_message_id": assistant_message_id,
                        },
                    )
                    return

                try:
                    graph = build_research_workflow(
                        user.id,
                        SessionFactory,
                        getattr(request.app.state, "redis", None),
                        checkpointer,
                        assistant_message_id=assistant_message_id,
                    )
                except Exception:
                    logger.exception("failed to create research agent")
                    message = "研究模型尚未配置完成。请检查服务端模型设置。"
                    await _save_assistant_message(assistant_message_id, message, "error")
                    yield _sse("error", {"message": message})
                    return

                run_config = {
                    "configurable": {"thread_id": conversation_id},
                    "recursion_limit": MAX_AGENT_RECURSION + 4,
                }
                deadline = asyncio.get_running_loop().time() + MAX_RESEARCH_SECONDS
                checkpoint = await asyncio.wait_for(
                    graph.aget_state(run_config),
                    timeout=max(0.001, deadline - asyncio.get_running_loop().time()),
                )
                checkpoint_messages = checkpoint.values.get("messages", [])
                initial_messages = [HumanMessage(content=content, id=user_message_id)]
                if not checkpoint_messages:
                    history = await asyncio.wait_for(
                        _history_messages_for_uncheckpointed_thread(
                            conversation_id, {user_message_id, assistant_message_id}
                        ),
                        timeout=max(0.001, deadline - asyncio.get_running_loop().time()),
                    )
                    initial_messages = [*history, *initial_messages]
                async for event in _bounded_events(graph.astream_events(
                    {"messages": initial_messages},
                    config=run_config,
                    version="v2",
                ), max(0.001, deadline - asyncio.get_running_loop().time())):
                    event_name = event.get("event")
                    event_data = event.get("data") or {}
                    event_metadata = event.get("metadata") or {}
                    if event_name == "on_chain_start":
                        node_name = event_metadata.get("langgraph_node")
                        phase_labels = {
                            "intent_router": "正在判断问题类型",
                            "research": "正在核对相关数据",
                            "final_answer": "正在整理证据和结论",
                        }
                        if node_name in phase_labels:
                            yield _sse("status", {
                                "phase": node_name,
                                "label": phase_labels[node_name],
                            })
                    if event_name == "on_tool_start":
                        run_id = str(event.get("run_id", new_id()))
                        tool_name = str(event.get("name", "research_tool"))
                        tool_id = await _start_tool_execution(
                            owner_id=user.id,
                            conversation_id=conversation_id,
                            message_id=assistant_message_id,
                            tool_name=tool_name,
                            input_summary=safe_tool_input(event_data.get("input", {})),
                        )
                        pending[run_id] = {
                            "id": tool_id,
                            "name": tool_name,
                            "started": time.monotonic(),
                        }
                        yield _sse(
                            "tool",
                            {
                                "id": tool_id,
                                "name": tool_name,
                                "input": safe_tool_input(event_data.get("input", {})),
                                "status": "running",
                            },
                        )
                    elif event_name == "on_tool_end":
                        run_id = str(event.get("run_id", ""))
                        execution = pending.get(run_id)
                        if execution:
                            tool_output = event_data.get("output")
                            output_summary, source, data_as_of, cache_status, error = (
                                summarize_tool_output(tool_output)
                            )
                            evidence = normalize_tool_evidence(
                                execution["name"], tool_output
                            )
                            retry_count = tool_retry_count(tool_output)
                            await _finish_tool_execution(
                                execution["id"], output_summary, source, data_as_of,
                                cache_status, error,
                                int((time.monotonic() - execution["started"]) * 1000),
                                retry_count=retry_count,
                                evidence=evidence,
                            )
                            pending.pop(run_id, None)
                            payload = {
                                "id": execution["id"],
                                "name": execution["name"],
                                "output_summary": output_summary,
                                "source": source,
                                "data_as_of": data_as_of,
                                "cache_status": cache_status,
                                "retry_count": retry_count,
                                "status": (
                                    "error" if error else
                                    "partial" if evidence.get("status") in {"partial", "empty"}
                                    else "complete"
                                ),
                                "evidence": evidence,
                            }
                            output_data = structured_tool_output(tool_output)
                            if output_data and isinstance(output_data.get("memory_proposal"), dict):
                                payload["memory_proposal"] = output_data["memory_proposal"]
                            yield _sse(
                                "tool",
                                payload,
                            )
                    elif event_name == "on_tool_error":
                        run_id = str(event.get("run_id", ""))
                        execution = pending.get(run_id)
                        if execution:
                            error_value = event_data.get("error")
                            error_type = (
                                type(error_value).__name__
                                if isinstance(error_value, BaseException)
                                else "未知异常"
                            )
                            error = f"工具执行失败（{error_type}）。"
                            evidence = normalize_tool_evidence(
                                execution["name"], {"error": error}
                            )
                            await _finish_tool_execution(
                                execution["id"], error, None, None, None, error,
                                int((time.monotonic() - execution["started"]) * 1000),
                                evidence=evidence,
                            )
                            pending.pop(run_id, None)
                            yield _sse(
                                "tool",
                                {
                                    "id": execution["id"],
                                    "name": execution["name"],
                                    "output_summary": error,
                                    "error_summary": error,
                                    "evidence": evidence,
                                    "status": "error",
                                },
                            )
                    elif (
                        event_name == "on_chain_end"
                        and event_metadata.get("langgraph_node") == "final_answer"
                    ):
                        output = event_data.get("output") or {}
                        final_messages = output.get("messages", []) if isinstance(output, dict) else []
                        if final_messages:
                            final_text = _text_content(getattr(final_messages[-1], "content", ""))
                            for offset in range(0, len(final_text), 48):
                                text = final_text[offset:offset + 48]
                                answer.append(text)
                                yield _sse("token", {"text": text})

                final_answer = "".join(answer).strip()
                if not final_answer:
                    message = "模型未返回可展示的正文，本轮研究未完成。请稍后重试。"
                    await _save_assistant_message(
                        assistant_message_id,
                        message,
                        "error",
                        error_summary=message,
                    )
                    yield _sse("error", {"message": message})
                    return
                await _save_assistant_message(assistant_message_id, final_answer, "complete")
                yield _sse(
                    "done",
                    {
                        "conversation_id": conversation_id,
                        "assistant_message_id": assistant_message_id,
                    },
                )
        except asyncio.CancelledError:
            await _finalize_pending_tools(pending, "请求取消，工具结果可能不完整。")
            interrupted = "".join(answer).strip() or "本轮研究已中断。"
            await _append_checkpoint_answer(
                checkpointer, conversation_id, assistant_message_id, interrupted
            )
            await _save_assistant_message(
                assistant_message_id,
                interrupted,
                "interrupted",
                error_summary="本轮研究已中断，已展示内容可能不完整。",
            )
            raise
        except GraphRecursionError:
            message = "本轮研究触及工具调用上限，已停止继续取数；请基于当前证据继续提问。"
            for tool_event in await _finalize_pending_tools(pending, message):
                yield _sse("tool", tool_event)
            await _append_checkpoint_answer(
                checkpointer,
                conversation_id,
                assistant_message_id,
                "".join(answer).strip() or message,
            )
            await _save_assistant_message(
                assistant_message_id,
                "".join(answer).strip() or message,
                "error",
                error_summary=message,
            )
            yield _sse("error", {"message": message})
        except TimeoutError:
            message = "本轮研究超过时间上限，已停止；当前回答可能不完整。"
            for tool_event in await _finalize_pending_tools(pending, message):
                yield _sse("tool", tool_event)
            await _append_checkpoint_answer(
                checkpointer,
                conversation_id,
                assistant_message_id,
                "".join(answer).strip() or message,
            )
            await _save_assistant_message(
                assistant_message_id,
                "".join(answer).strip() or message,
                "error",
                error_summary=message,
            )
            yield _sse("error", {"message": message})
        except Exception as exc:
            logger.exception("research run failed (%s)", type(exc).__name__)
            message = "研究请求暂时未能完成，请稍后重试。"
            for tool_event in await _finalize_pending_tools(pending, message):
                yield _sse("tool", tool_event)
            await _append_checkpoint_answer(
                checkpointer,
                conversation_id,
                assistant_message_id,
                "".join(answer).strip() or message,
            )
            await _save_assistant_message(
                assistant_message_id,
                "".join(answer).strip() or message,
                "error",
                error_summary=message,
            )
            yield _sse("error", {"message": message})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def time_to_datetime():
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(tzinfo=None)


async def _append_checkpoint_answer(
    checkpointer: Any, conversation_id: str, message_id: str, content: str
) -> None:
    try:
        await append_direct_turn(
            checkpointer,
            conversation_id,
            [AIMessage(content=content, id=message_id)],
        )
    except Exception:
        logger.exception("failed to close interrupted LangGraph turn %s", conversation_id)


async def _start_tool_execution(
    owner_id: str,
    conversation_id: str,
    message_id: str,
    tool_name: str,
    input_summary: dict,
) -> str:
    record = ToolExecution(
        owner_id=owner_id,
        conversation_id=conversation_id,
        message_id=message_id,
        tool_name=tool_name,
        input_summary=input_summary,
        status="running",
    )
    async with SessionFactory() as session:
        session.add(record)
        await session.commit()
        return record.id


async def _finish_tool_execution(
    execution_id: str,
    output_summary: str,
    source: str | None,
    data_as_of: str | None,
    cache_status: str | None,
    error_summary: str | None,
    duration_ms: int,
    retry_count: int = 0,
    evidence: dict[str, Any] | None = None,
) -> None:
    async with SessionFactory() as session:
        record = await session.get(ToolExecution, execution_id)
        if record is None:
            return
        record.output_summary = output_summary[:6000]
        record.source = source
        record.data_as_of = data_as_of
        record.cache_status = cache_status
        record.error_summary = error_summary[:2000] if error_summary else None
        record.status = (
            "error" if error_summary else
            "partial" if evidence and evidence.get("status") in {"partial", "empty"}
            else "complete"
        )
        record.duration_ms = duration_ms
        record.retry_count = retry_count
        record.evidence_json = evidence
        await session.commit()


async def _save_assistant_message(
    message_id: str, content: str, state: str, error_summary: str | None = None
) -> None:
    async with SessionFactory() as session:
        message = await session.get(ConversationMessage, message_id)
        if message is None:
            return
        message.content = content[:30000]
        message.metadata_json = {"status": state, "error": error_summary} if error_summary else {
            "status": state
        }
        await session.commit()
