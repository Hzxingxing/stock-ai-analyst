"""Bounded, structured evidence records for tool outputs and final-answer checks."""

import json
import re
from datetime import UTC, datetime
from typing import Any

MAX_EVIDENCE_BYTES = 12_000
MAX_MISSING_FIELDS = 40
MAX_EVIDENCE_NODES = 1_000
_ARRAY_LIMITS = {"bars": 12, "records": 10, "trades": 10, "points": 12, "comparisons": 8}


def result_mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "content"):
        value = value.content
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {"result": value[:3000]}
    return value if isinstance(value, dict) else {"result": value}


def normalize_tool_evidence(tool_name: str, value: Any) -> dict[str, Any]:
    result = result_mapping(value)
    metadata_fields = {
        "_harness", "source", "data_as_of", "trade_date", "report_date", "valuation_date",
        "trade_date_source", "observed_at", "market_time", "retrieved_at", "collected_at", "units",
        "cache_status", "warning", "error",
    }
    data = {key: val for key, val in result.items() if key not in metadata_fields}
    status = "error" if result.get("error") else "complete"
    if result.get("warning"):
        status = "partial"
    if _is_empty_result(result):
        status = "empty"

    evidence = {
        "schema_version": 1,
        "tool": tool_name,
        "status": status,
        "source": _source(result.get("source")),
        "data_as_of": _compact(_first(
            result, "data_as_of", "trade_date", "report_date", "valuation_date"
        )),
        "date_source": _safe_text(result.get("trade_date_source"), 200),
        "observed_at": _compact(_first(
            result, "observed_at", "market_time", "retrieved_at", "collected_at"
        )),
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "units": _bounded_units(result.get("units"))
        if isinstance(result.get("units"), (dict, list, str)) else None,
        "cache_status": result.get("cache_status"),
        "deduplicated": bool(
            isinstance(result.get("_harness"), dict)
            and result["_harness"].get("deduplicated")
        ),
        "missing_fields": [item[:240] for item in _missing_fields(data)],
        "warning": _safe_text(result.get("warning"), 800),
        "error": _safe_text(result.get("error"), 800),
        "data": _bounded_data(data),
    }
    return _fit_evidence(evidence)


def audit_final_answer(answer: str, evidence: list[dict[str, Any]], research: bool) -> str:
    """Remove ungrounded evidence labels and ensure missing research data is disclosed."""
    allowed = {item.get("id") for item in evidence if isinstance(item.get("id"), str)}
    invalid: set[str] = set()

    def replace_citation(match: re.Match[str]) -> str:
        label = match.group(1)
        if label not in allowed:
            invalid.add(label)
            return ""
        return f"[{label}]"

    cleaned = re.sub(r"\[(E\d+)\]", replace_citation, answer).strip()
    if invalid:
        cleaned += "\n\n（有证据编号无法对应本轮工具记录，相关内容未作为已核实引用。）"

    if research and not any(_has_usable_evidence(item) for item in evidence):
        if not any(term in cleaned for term in ("未核实", "未取得", "没有可用", "无法确认")):
            cleaned = "本轮未取得可用的研究数据，具体市场事实尚未核实。\n\n" + cleaned
    elif research and evidence and not re.search(r"\[E\d+\]", cleaned):
        references = []
        for item in evidence:
            source = item.get("source") or "来源未记录"
            if isinstance(source, list):
                source = "、".join(source)
            date_label = f"，数据截至 {item['data_as_of']}" if item.get("data_as_of") else ""
            references.append(f"[{item['id']}] {item.get('tool', '研究工具')}，{source}{date_label}")
        cleaned += "\n\n证据索引：" + "；".join(references[:8])

    limitations = []
    for item in evidence:
        detail = item.get("error") or item.get("warning")
        if detail and detail not in limitations:
            limitations.append(detail)
        if item.get("status") == "empty":
            limitations.append(f"{item.get('tool', '研究工具')}未返回可用记录。")
        missing = item.get("missing_fields") or []
        if missing:
            limitations.append(f"{item.get('tool', '研究工具')}缺少字段：{', '.join(missing[:8])}")
    if limitations and not any(term in cleaned for term in ("数据限制", "字段缺失", "暂时不可用")):
        summary = "；".join(limitations[:5])[:1200]
        cleaned = f"{cleaned}\n\n数据限制：{summary}"
    return cleaned


def _bounded_data(data: dict[str, Any]) -> Any:
    compact = _compact(data)
    encoded = json.dumps(compact, ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) <= MAX_EVIDENCE_BYTES // 2:
        return compact
    preview = json.dumps(compact, ensure_ascii=False, default=str)
    return {"truncated": True, "preview": preview[: MAX_EVIDENCE_BYTES // 2]}


def _compact(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        bounded = {}
        for index, (item_key, item) in enumerate(value.items()):
            if index == 80:
                bounded["_truncated"] = True
                break
            bounded[str(item_key)[:100]] = _compact(item, str(item_key))
        return bounded
    if isinstance(value, list):
        limit = _ARRAY_LIMITS.get(key, 20)
        selected = value[:limit]
        return [_compact(item) for item in selected]
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def _bounded_units(value: Any) -> Any:
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, dict):
        bounded = {}
        for index, (key, unit) in enumerate(value.items()):
            if index == 32:
                bounded["_truncated"] = True
                break
            bounded[str(key)[:100]] = (
                _compact(unit) if not isinstance(unit, str) else unit[:300]
            )
        return bounded
    return _compact(value)


def _fit_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    for _ in range(16):
        size = len(json.dumps(evidence, ensure_ascii=False, default=str).encode("utf-8"))
        if size <= MAX_EVIDENCE_BYTES:
            break
        evidence["truncated"] = True
        data = evidence.get("data")
        if isinstance(data, dict) and data.get("preview"):
            data["preview"] = data["preview"][: len(data["preview"]) // 2]
        elif isinstance(data, dict) and data != {"truncated": True}:
            evidence["data"] = {"truncated": True}
        elif "data" in evidence:
            evidence.pop("data")
        elif evidence.get("units") is not None:
            evidence["units"] = None
        elif evidence.get("missing_fields"):
            evidence["missing_fields"] = evidence["missing_fields"][:8]
        elif evidence.get("warning") or evidence.get("error"):
            evidence["warning"] = (evidence.get("warning") or "")[:200] or None
            evidence["error"] = (evidence.get("error") or "")[:200] or None
        else:
            break
    return evidence


def _missing_fields(value: Any) -> list[str]:
    missing: list[str] = []
    visited = 0

    def walk(item: Any, path: str) -> None:
        nonlocal visited
        visited += 1
        if visited > MAX_EVIDENCE_NODES:
            return
        if len(missing) >= MAX_MISSING_FIELDS:
            return
        if isinstance(item, dict):
            for key, nested in item.items():
                walk(nested, f"{path}.{key}" if path else str(key))
        elif isinstance(item, list):
            for index, nested in enumerate(item[:8]):
                walk(nested, f"{path}[{index}]")
        elif item is None and path:
            missing.append(path)

    walk(value, "")
    return missing


def _is_empty_result(value: dict[str, Any]) -> bool:
    collections = [item for item in value.values() if isinstance(item, list)]
    return bool(collections) and all(not item for item in collections) and not value.get("error")


def _has_usable_evidence(item: dict[str, Any]) -> bool:
    if item.get("status") not in {"complete", "partial"} or item.get("error"):
        return False
    data = item.get("data")
    if not isinstance(data, dict):
        return data not in (None, "", [], {})
    return bool(
        item.get("truncated")
        or data.get("truncated")
        or data.get("_truncated")
        or any(
            key not in {"symbol", "name", "dataset"}
            and value not in (None, "", [], {})
            for key, value in data.items()
        )
    )


def _source(value: Any) -> str | list[str] | None:
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, (list, tuple)):
        return [str(item)[:150] for item in value[:8]]
    return None


def _first(value: dict[str, Any], *keys: str) -> Any:
    return next((value.get(key) for key in keys if value.get(key) is not None), None)


def _safe_text(value: Any, limit: int) -> str | None:
    return str(value)[:limit] if value else None
