from datetime import UTC
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Conversation, ConversationMessage, ResearchMemory, ToolExecution, User
from app.db.session import get_session
from app.harness.locks import conversation_lock

router = APIRouter(tags=["research"])


class ConversationWrite(BaseModel):
    title: str = Field(default="新研究", min_length=1, max_length=200)


class MemoryWrite(BaseModel):
    kind: Literal["preference", "hypothesis", "evidence", "open_question"]
    statement: str = Field(min_length=1, max_length=6000)
    attribution: Literal["user", "agent_inference"] = "user"
    stance: Literal["support", "oppose", "neutral"] | None = None
    supporting_evidence: list[dict] = Field(default_factory=list, max_length=30)
    counter_evidence: list[dict] = Field(default_factory=list, max_length=30)
    invalidation_conditions: list[str] = Field(default_factory=list, max_length=30)
    conversation_id: str | None = None


def _iso(value):
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()


def _conversation_view(conversation: Conversation) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": _iso(conversation.created_at),
        "updated_at": _iso(conversation.updated_at),
    }


@router.get("/conversations")
async def list_conversations(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    conversations = (
        await session.scalars(
            select(Conversation)
            .where(Conversation.owner_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(100)
        )
    ).all()
    return [_conversation_view(item) for item in conversations]


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationWrite,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    conversation = Conversation(owner_id=user.id, title=request.title.strip())
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return _conversation_view(conversation)


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    request: ConversationWrite,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.owner_id == user.id
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="研究会话不存在")
    conversation.title = request.title.strip()
    await session.commit()
    await session.refresh(conversation)
    return _conversation_view(conversation)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.owner_id == user.id
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="研究会话不存在")
    return _conversation_view(conversation)


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    conversation = await session.scalar(
        select(Conversation.id).where(
            Conversation.id == conversation_id, Conversation.owner_id == user.id
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="研究会话不存在")
    messages = (
        await session.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at)
        )
    ).all()
    output = []
    for message in messages:
        tool_calls = (
            (
                await session.scalars(
                    select(ToolExecution)
                    .where(ToolExecution.message_id == message.id)
                    .order_by(ToolExecution.created_at)
                )
            ).all()
            if message.role == "assistant"
            else []
        )
        output.append(
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": _iso(message.created_at),
                "metadata": message.metadata_json or {},
                "tool_calls": [
                    {
                        "id": tool.id,
                        "name": tool.tool_name,
                        "input": tool.input_summary,
                        "output_summary": tool.output_summary,
                        "source": tool.source,
                        "data_as_of": tool.data_as_of,
                        "status": tool.status,
                        "cache_status": tool.cache_status,
                        "duration_ms": tool.duration_ms,
                        "retry_count": tool.retry_count,
                        "error_summary": tool.error_summary,
                        "created_at": _iso(tool.created_at),
                    }
                    for tool in tool_calls
                ],
            }
        )
    return output


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    async with conversation_lock(conversation_id):
        conversation = await session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.owner_id == user.id
            )
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="研究会话不存在")
        checkpointer = getattr(request.app.state, "checkpointer", None)
        if checkpointer is not None and hasattr(checkpointer, "adelete_thread"):
            await checkpointer.adelete_thread(conversation_id)
        await session.delete(conversation)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/memories")
async def list_memories(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (
        await session.scalars(
            select(ResearchMemory)
            .where(ResearchMemory.owner_id == user.id)
            .order_by(ResearchMemory.updated_at.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "statement": row.statement,
            "attribution": row.attribution,
            "stance": row.stance,
            "supporting_evidence": row.supporting_evidence or [],
            "counter_evidence": row.counter_evidence or [],
            "invalidation_conditions": row.invalidation_conditions or [],
            "conversation_id": row.conversation_id,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in rows
    ]


@router.post("/memories", status_code=status.HTTP_201_CREATED)
async def create_memory(
    request: MemoryWrite,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if request.conversation_id:
        owned = await session.scalar(
            select(Conversation.id).where(
                Conversation.id == request.conversation_id, Conversation.owner_id == user.id
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="研究会话不存在")
    memory = ResearchMemory(owner_id=user.id, **request.model_dump())
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    return {"id": memory.id, "statement": memory.statement, "kind": memory.kind}


@router.put("/memories/{memory_id}")
async def update_memory(
    memory_id: str,
    request: MemoryWrite,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if request.conversation_id:
        owned = await session.scalar(
            select(Conversation.id).where(
                Conversation.id == request.conversation_id, Conversation.owner_id == user.id
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="研究会话不存在")
    memory = await session.scalar(
        select(ResearchMemory).where(
            ResearchMemory.id == memory_id, ResearchMemory.owner_id == user.id
        )
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="研究记忆不存在")
    for key, value in request.model_dump().items():
        setattr(memory, key, value)
    await session.commit()
    return {"id": memory.id, "statement": memory.statement, "kind": memory.kind}


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    memory = await session.scalar(
        select(ResearchMemory).where(
            ResearchMemory.id == memory_id, ResearchMemory.owner_id == user.id
        )
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="研究记忆不存在")
    await session.delete(memory)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
