import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Conversation, ConversationMessage, ToolExecution, User, new_id
from app.db.session import SessionFactory, get_session
from app.harness.agent import build_research_agent, safe_tool_input, summarize_tool_output
from app.harness.locks import conversation_lock

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


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
                try:
                    graph = build_research_agent(
                        user.id,
                        SessionFactory,
                        getattr(request.app.state, "redis", None),
                        checkpointer,
                    )
                except Exception:
                    logger.exception("failed to create research agent")
                    message = "研究模型尚未配置完成。请检查服务端模型设置。"
                    await _save_assistant_message(assistant_message_id, message, "error")
                    yield _sse("error", {"message": message})
                    return

                run_config = {"configurable": {"thread_id": conversation_id}}
                async for event in graph.astream_events(
                    {"messages": [HumanMessage(content=content)]},
                    config=run_config,
                    version="v2",
                ):
                    event_name = event.get("event")
                    event_data = event.get("data") or {}
                    if event_name == "on_tool_start":
                        run_id = str(event.get("run_id", new_id()))
                        tool_id = await _start_tool_execution(
                            owner_id=user.id,
                            conversation_id=conversation_id,
                            message_id=assistant_message_id,
                            tool_name=str(event.get("name", "research_tool")),
                            input_summary=safe_tool_input(event_data.get("input", {})),
                        )
                        pending[run_id] = {"id": tool_id, "started": time.monotonic()}
                        yield _sse(
                            "tool",
                            {
                                "id": tool_id,
                                "name": str(event.get("name", "research_tool")),
                                "input": safe_tool_input(event_data.get("input", {})),
                                "status": "running",
                            },
                        )
                    elif event_name == "on_tool_end":
                        run_id = str(event.get("run_id", ""))
                        execution = pending.get(run_id)
                        if execution:
                            output_summary, source, data_as_of, cache_status, error = (
                                summarize_tool_output(event_data.get("output"))
                            )
                            await _finish_tool_execution(
                                execution["id"], output_summary, source, data_as_of,
                                cache_status, error,
                                int((time.monotonic() - execution["started"]) * 1000),
                            )
                            pending.pop(run_id, None)
                            yield _sse(
                                "tool",
                                {
                                    "id": execution["id"],
                                    "name": str(event.get("name", "research_tool")),
                                    "output_summary": output_summary,
                                    "source": source,
                                    "data_as_of": data_as_of,
                                    "cache_status": cache_status,
                                    "status": "error" if error else "complete",
                                },
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
                            await _finish_tool_execution(
                                execution["id"], error, None, None, None, error,
                                int((time.monotonic() - execution["started"]) * 1000),
                            )
                            pending.pop(run_id, None)
                            yield _sse(
                                "tool",
                                {
                                    "id": execution["id"],
                                    "name": str(event.get("name", "research_tool")),
                                    "output_summary": error,
                                    "error_summary": error,
                                    "status": "error",
                                },
                            )
                    elif event_name == "on_chat_model_stream":
                        chunk = event_data.get("chunk")
                        text = _text_content(getattr(chunk, "content", ""))
                        if text:
                            answer.append(text)
                            yield _sse("token", {"text": text})
                    elif event_name == "on_chat_model_end" and not answer:
                        output = event_data.get("output")
                        messages = getattr(output, "generations", None)
                        if messages and messages[0]:
                            fallback = _text_content(getattr(messages[0][0], "text", ""))
                            if fallback:
                                answer.append(fallback)
                                yield _sse("token", {"text": fallback})

                final_answer = "".join(answer).strip()
                if not final_answer:
                    final_answer = "本轮研究没有生成可展示的结论。"
                await _save_assistant_message(assistant_message_id, final_answer, "complete")
                yield _sse(
                    "done",
                    {
                        "conversation_id": conversation_id,
                        "assistant_message_id": assistant_message_id,
                    },
                )
        except asyncio.CancelledError:
            await asyncio.gather(*(
                _finish_tool_execution(
                    execution["id"], "研究请求已中断。", None, None, None,
                    "请求取消，执行结果可能不完整。",
                    int((time.monotonic() - execution["started"]) * 1000),
                )
                for execution in pending.values()
            ), return_exceptions=True)
            await _save_assistant_message(
                assistant_message_id,
                "".join(answer).strip() or "本轮研究已中断。",
                "interrupted",
            )
            raise
        except Exception as exc:
            logger.exception("research run failed (%s)", type(exc).__name__)
            message = "研究请求暂时未能完成，请稍后重试。"
            await asyncio.gather(*(
                _finish_tool_execution(
                    execution["id"], message, None, None, None, message,
                    int((time.monotonic() - execution["started"]) * 1000),
                )
                for execution in pending.values()
            ), return_exceptions=True)
            await _save_assistant_message(
                assistant_message_id, "".join(answer).strip() or message, "error"
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
        record.status = "error" if error_summary else "complete"
        record.duration_ms = duration_ms
        await session.commit()


async def _save_assistant_message(message_id: str, content: str, state: str) -> None:
    async with SessionFactory() as session:
        message = await session.get(ConversationMessage, message_id)
        if message is None:
            return
        message.content = content[:30000]
        message.metadata_json = {"status": state}
        await session.commit()
