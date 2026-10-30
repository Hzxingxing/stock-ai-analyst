from langchain_core.messages import AnyMessage
from langgraph.checkpoint.mysql.asyncmy import AsyncMySaver
from langgraph.graph import END, START, MessagesState, StateGraph

_UNCOLLATED_CHANNEL_COLUMN = "channel VARCHAR(150) CHARACTER SET utf8mb4 PATH '$'"
_COLLATED_CHANNEL_COLUMN = (
    "channel VARCHAR(150) CHARACTER SET utf8mb4 "
    "COLLATE utf8mb4_unicode_ci PATH '$'"
)


class ResearchAsyncMySaver(AsyncMySaver):
    """Keep LangGraph's generated JSON_TABLE channel compatible with checkpoint columns."""

    @staticmethod
    def _select_sql(where: str) -> str:
        query = AsyncMySaver._select_sql(where)
        if _COLLATED_CHANNEL_COLUMN in query:
            return query

        occurrences = query.count(_UNCOLLATED_CHANNEL_COLUMN)
        if occurrences != 1:
            raise RuntimeError(
                "LangGraph's MySQL checkpoint query changed; review its channel collation"
            )
        return query.replace(
            _UNCOLLATED_CHANNEL_COLUMN,
            _COLLATED_CHANNEL_COLUMN,
            1,
        )


async def append_direct_turn(
    checkpointer: object,
    thread_id: str,
    messages: list[AnyMessage],
) -> None:
    """Persist deterministic replies in the same LangGraph message thread."""
    graph = StateGraph(MessagesState)

    async def preserve_checkpoint(_state: MessagesState) -> dict:
        return {}

    graph.add_node("preserve_direct_turn", preserve_checkpoint)
    graph.add_edge(START, "preserve_direct_turn")
    graph.add_edge("preserve_direct_turn", END)
    app = graph.compile(checkpointer=checkpointer, name="direct_turn_checkpoint")
    await app.ainvoke(
        {"messages": messages},
        config={
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 2,
        },
    )
