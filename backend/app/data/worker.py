import json
import sys
from datetime import date

from app.data.providers import akshare


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    args = sys.argv[2:]
    if action == "ticks" and len(args) == 1:
        result = akshare.fetch_recent_trades(args[0])
    elif action == "daily" and len(args) == 5:
        result = akshare.fetch_daily_bars(
            args[0], args[1], date.fromisoformat(args[2]), date.fromisoformat(args[3]), args[4]
        )
    elif action == "minute" and len(args) == 2:
        result = akshare.fetch_intraday_bars(args[0], args[1])
    elif action == "search" and len(args) == 1:
        result = akshare.search_equities(args[0])
    elif action == "snapshot" and not args:
        result = akshare.fetch_market_snapshot()
    elif action == "company-research" and len(args) == 2:
        result = akshare.fetch_company_research(args[0], args[1])
    elif action == "index-daily" and len(args) == 3:
        result = akshare.fetch_index_bars(
            args[0], date.fromisoformat(args[1]), date.fromisoformat(args[2])
        )
    else:
        raise SystemExit("unsupported provider action")
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
