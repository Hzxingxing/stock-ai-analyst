from langgraph.checkpoint.mysql.asyncmy import AsyncMySaver

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
