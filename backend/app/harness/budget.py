"""Per-turn cost limits and duplicate-call coalescing for research tools."""

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

TOOL_COSTS: dict[str, int] = {
    "search_instruments": 1,
    "get_price_history": 2,
    "get_current_quote": 2,
    "analyze_price_history": 3,
    "compare_instruments": 2,
    "get_market_overview": 2,
    "get_company_research_data": 4,
    "get_intraday_bars": 4,
    "get_recent_trades": 5,
    "propose_research_memory": 1,
}


class TurnToolBudget:
    """Budget unique tool executions and reuse identical in-flight/results per turn."""

    def __init__(self, max_cost: int = 18, max_calls: int = 8):
        self.max_cost = max_cost
        self.max_calls = max_calls
        self.used_cost = 0
        self.used_calls = 0
        self._lock = asyncio.Lock()
        self._results: dict[str, Any] = {}
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    @property
    def remaining_cost(self) -> int:
        return max(0, self.max_cost - self.used_cost)

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self.used_calls)

    def wrap(self, tools: Sequence[BaseTool]) -> list[BaseTool]:
        return [self._wrap_tool(tool) for tool in tools]

    def _wrap_tool(self, target: BaseTool) -> StructuredTool:
        async def invoke(**arguments: Any) -> Any:
            return await self.invoke(target, arguments)

        return StructuredTool.from_function(
            coroutine=invoke,
            name=target.name,
            description=target.description,
            args_schema=target.args_schema,
            return_direct=target.return_direct,
            response_format=target.response_format,
        )

    async def invoke(self, target: BaseTool, arguments: dict[str, Any]) -> Any:
        key = self._fingerprint(target.name, arguments)
        reused = False
        async with self._lock:
            if key in self._results:
                return _mark_reused(self._results[key])
            task = self._inflight.get(key)
            if task is None:
                cost = self._cost(target.name, arguments)
                if self.used_calls >= self.max_calls or self.used_cost + cost > self.max_cost:
                    return {
                        "error": "本轮研究的工具预算已用完，已停止继续取数。",
                        "budget_exhausted": True,
                        "budget": {
                            "used_cost": self.used_cost,
                            "max_cost": self.max_cost,
                            "used_calls": self.used_calls,
                            "max_calls": self.max_calls,
                        },
                    }
                self.used_cost += cost
                self.used_calls += 1
                task = asyncio.create_task(self._execute(key, target, arguments))
                self._inflight[key] = task
                task.add_done_callback(_consume_task_exception)
            else:
                reused = True

        result = await asyncio.shield(task)
        return _mark_reused(result) if reused else result

    async def _execute(
        self, key: str, target: BaseTool, arguments: dict[str, Any]
    ) -> Any:
        try:
            result = await target.ainvoke(arguments)
        except BaseException:
            async with self._lock:
                if self._inflight.get(key) is asyncio.current_task():
                    self._inflight.pop(key, None)
            raise
        async with self._lock:
            self._results[key] = result
            if self._inflight.get(key) is asyncio.current_task():
                self._inflight.pop(key, None)
        return result

    def snapshot(self) -> dict[str, int]:
        return {
            "used_cost": self.used_cost,
            "max_cost": self.max_cost,
            "remaining_cost": self.remaining_cost,
            "used_calls": self.used_calls,
            "max_calls": self.max_calls,
            "remaining_calls": self.remaining_calls,
        }

    @staticmethod
    def _fingerprint(name: str, arguments: dict[str, Any]) -> str:
        return name + ":" + json.dumps(
            arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )

    @staticmethod
    def _cost(name: str, arguments: dict[str, Any]) -> int:
        cost = TOOL_COSTS.get(name, 3)
        if name == "compare_instruments":
            cost += max(0, len(arguments.get("symbols", [])) - 2)
        return cost


def _mark_reused(value: Any) -> Any:
    if isinstance(value, dict):
        result = dict(value)
        result["_harness"] = {"deduplicated": True}
        return result
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            decoded["_harness"] = {"deduplicated": True}
            return decoded
    return {"result": value, "_harness": {"deduplicated": True}}


def _consume_task_exception(task: asyncio.Task[Any]) -> None:
    if not task.cancelled():
        task.exception()
