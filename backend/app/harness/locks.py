"""Process-local serialization for operations that mutate a conversation thread."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


_conversation_locks: dict[str, _LockEntry] = {}


@asynccontextmanager
async def conversation_lock(conversation_id: str) -> AsyncIterator[None]:
    """Serialize operations for one conversation and discard unused locks."""
    entry = _conversation_locks.get(conversation_id)
    if entry is None:
        entry = _LockEntry(asyncio.Lock())
        _conversation_locks[conversation_id] = entry
    entry.users += 1
    try:
        async with entry.lock:
            yield
    finally:
        entry.users -= 1
        if entry.users == 0 and _conversation_locks.get(conversation_id) is entry:
            del _conversation_locks[conversation_id]
