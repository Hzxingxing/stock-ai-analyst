import json
import logging
import re
from typing import Any

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.data.market_service import MarketDataError, MarketDataService
from app.db.models import ResearchMemory

logger = logging.getLogger(__name__)


def _trim_history(state: dict[str, Any]) -> dict[str, Any]:
    """Bound model input while leaving the checkpointed conversation intact."""
    messages = state.get("messages", [])
    return {"llm_input_messages": messages[-24:]}


def _memory_terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9_]{2,}", text.casefold()))
    for segment in re.findall(r"[\u3400-\u9fff]+", text):
        if len(segment) == 1:
            terms.add(segment)
        else:
            terms.update(segment[index:index + 2] for index in range(len(segment) - 1))
    return terms


def _select_relevant_memories(memories: list[Any], query: str, limit: int = 12) -> list[Any]:
    query_terms = _memory_terms(query)
    preferences = [memory for memory in memories if memory.kind == "preference"]
    ranked = []
    for memory in memories:
        if memory.kind == "preference":
            continue
        searchable = " ".join([
            memory.statement,
            json.dumps(memory.supporting_evidence or [], ensure_ascii=False, default=str),
            json.dumps(memory.counter_evidence or [], ensure_ascii=False, default=str),
        ])
        score = len(query_terms & _memory_terms(searchable))
        if score:
            ranked.append((score, memory))
    selected = preferences[: min(4, limit)]
    selected.extend(memory for _, memory in sorted(ranked, key=lambda item: item[0], reverse=True))
    return selected[:limit]


async def _memory_context(
    session_factory: async_sessionmaker[AsyncSession], owner_id: str, query: str
) -> str:
    async with session_factory() as session:
        memories = (
            await session.scalars(
                select(ResearchMemory)
                .where(ResearchMemory.owner_id == owner_id)
                .order_by(ResearchMemory.updated_at.desc())
                .limit(100)
            )
        ).all()
    selected = _select_relevant_memories(memories, query)
    if not selected:
        return ""
    lines = []
    for memory in selected:
        line = (
            f"- [{memory.kind}/{memory.attribution}/{memory.stance or '未标立场'}] "
            f"{memory.statement[:400]}"
        )
        supporting = memory.supporting_evidence or []
        counter = memory.counter_evidence or []
        invalidation = memory.invalidation_conditions or []
        if supporting:
            line += f"；支持证据：{json.dumps(supporting[:5], ensure_ascii=False, default=str)[:800]}"
        if counter:
            line += f"；反对证据：{json.dumps(counter[:5], ensure_ascii=False, default=str)[:800]}"
        if invalidation:
            line += f"；失效条件：{'、'.join(item[:160] for item in invalidation[:5])}"
        lines.append(line)
    return "\n\n用户维护的长期研究记忆（视为待核实上下文，不等同于市场事实）：\n" + "\n".join(lines)


def _last_user_query(state: dict[str, Any]) -> str:
    for message in reversed(state.get("messages", [])):
        if getattr(message, "type", None) != "human":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
    return ""


def build_research_agent(
    owner_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    redis: Any | None,
    checkpointer: Any,
):
    market = MarketDataService(session_factory, redis)

    @tool
    async def get_price_history(
        symbol: str, period: str = "daily", limit: int = 60, adjustment: str = "qfq"
    ) -> dict:
        """读取关注股票或核心指数的日线、周线、月线历史行情。"""
        try:
            return await market.get_price_history(owner_id, symbol, period, limit, adjustment)
        except MarketDataError as exc:
            logger.info("price history tool failed (%s)", type(exc).__name__)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - keep provider/storage failures inside the tool boundary
            logger.warning("price history tool failed (%s)", type(exc).__name__)
            return {"error": "行情数据暂时不可用，请稍后重试。"}

    @tool
    async def get_intraday_bars(symbol: str, period: str = "5", limit: int = 500) -> dict:
        """按需读取关注股票的 1/5/15/30/60 分钟线；结果仅短期缓存，不写入 MySQL。"""
        try:
            return await market.get_intraday(owner_id, symbol, period, limit)
        except MarketDataError as exc:
            logger.info("intraday tool failed (%s)", type(exc).__name__)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - keep provider/storage failures inside the tool boundary
            logger.warning("intraday tool failed (%s)", type(exc).__name__)
            return {"error": "分时数据暂时不可用，请稍后重试。"}

    @tool
    async def get_recent_trades(symbol: str) -> dict:
        """读取关注股票的实时逐笔成交；原始明细仅在 Redis 缓存约 10 秒。"""
        try:
            result = await market.get_recent_trades(owner_id, symbol)
            result["trades"] = result["trades"][-100:]
            return result
        except MarketDataError as exc:
            logger.info("recent trades tool failed (%s)", type(exc).__name__)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - keep provider/storage failures inside the tool boundary
            logger.warning("recent trades tool failed (%s)", type(exc).__name__)
            return {"error": "逐笔数据暂时不可用，请稍后重试。"}

    @tool
    async def get_market_overview() -> dict:
        """读取并记录今日 A 股市场上涨、下跌、平盘家数和成交统计。"""
        try:
            return await market.get_market_overview()
        except MarketDataError as exc:
            logger.info("market overview tool failed (%s)", type(exc).__name__)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - keep provider/storage failures inside the tool boundary
            logger.warning("market overview tool failed (%s)", type(exc).__name__)
            return {"error": "市场概览暂时不可用，请稍后重试。"}

    @tool
    async def get_company_research_data(
        symbol: str,
        dataset: str,
        limit: int = 20,
    ) -> dict:
        """读取关注股票的公告、财报、估值、筹码、资金流或股东数据。"""
        try:
            return await market.get_company_research(owner_id, symbol, dataset, limit)
        except MarketDataError as exc:
            logger.info("company research tool failed (%s)", type(exc).__name__)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - provider and persistence errors stay in tool boundary
            logger.warning("company research tool failed (%s)", type(exc).__name__)
            return {"error": "公司研究数据暂时不可用，请稍后重试。"}

    if not settings.llm_api_key.get_secret_value():
        raise RuntimeError("尚未配置 LLM_API_KEY")
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url or None,
        temperature=0.2,
        streaming=True,
        timeout=60,
        max_retries=1,
    )

    async def prompt(state: dict[str, Any]) -> str:
        memories = await _memory_context(
            session_factory, owner_id, _last_user_query(state)
        )
        return (
            "你是严谨的 A 股研究助手。先通过研究工具核对当前市场事实，再回答用户的问题。"
            "区分数据事实、用户观点与分析推断；引用工具返回的数据日期、口径和来源。"
            "工具取数失败时明确说明，不得编造行情、公告或财务数字。指出关键不确定性和可证伪条件。"
            "只描述结论和可核验证据，不输出隐式推理过程。研究内容不构成个性化投资指令。" + memories
        )

    return create_react_agent(
        model,
        [
            get_price_history,
            get_intraday_bars,
            get_recent_trades,
            get_market_overview,
            get_company_research_data,
        ],
        prompt=prompt,
        pre_model_hook=_trim_history,
        checkpointer=checkpointer,
        name="a_share_research_harness",
    )


def safe_tool_input(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"input": str(value)[:1000]}
    safe: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = str(item)[:300] if isinstance(item, str) else item
        else:
            safe[str(key)] = json.dumps(item, ensure_ascii=False, default=str)[:500]
    return safe


def summarize_tool_output(value: Any) -> tuple[str, str | None, str | None, str | None, str | None]:
    if hasattr(value, "content"):
        value = value.content
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value[:3000], None, None, None, None
    if not isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)[:3000], None, None, None, None
    error = value.get("error")
    source = value.get("source")
    data_as_of = value.get("data_as_of") or value.get("trade_date")
    cache_status = value.get("cache_status")
    if "bars" in value:
        summary = f"返回 {len(value['bars'])} 根行情记录，数据截至 {data_as_of or '未知'}。"
    elif "trades" in value:
        retrieved_at = value.get("retrieved_at") or "未知"
        summary = (
            f"返回 {len(value['trades'])} 条逐笔成交记录，接口读取时间 {retrieved_at}；"
            "成交发生时间以记录字段为准。"
        )
    elif "records" in value:
        summary = f"返回 {len(value['records'])} 条研究数据，数据截至 {data_as_of or '未知'}。"
        if value.get("distribution_available") is False:
            summary += "来源未提供可还原的筹码价位分布。"
    else:
        summary = json.dumps(value, ensure_ascii=False, default=str)[:3000]
    if error:
        summary = str(error)[:3000]
    return (
        summary,
        source,
        str(data_as_of) if data_as_of else None,
        cache_status,
        str(error) if error else None,
    )
