from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Dict, Optional

NO_DATA_AVAILABLE = "NO_DATA_AVAILABLE"

NO_DATA_STATUSES = {
    "unavailable",
    "backtest_skipped",
    "skipped",
    "failed",
    "no_data",
}

MEANINGFUL_VALUE_META_KEYS = {
    "date",
    "data_date",
    "as_of",
    "asof",
    "timestamp",
    "collection_timestamp_utc",
    "source",
    "source_name",
    "source_tier",
    "metric_name",
    "function_id",
    "name",
    "unit",
    "notes",
    "note",
    "unavailable_reason",
    "skip_reason",
    "availability",
    "availability_sentinel",
    "no_data",
    "no_data_text",
    "sentinel",
    "data_quality",
}


def _is_nan_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return False


def has_meaningful_observation_value(value: Any, *, parent_key: str = "") -> bool:
    """Return True only when a payload contains an actual observed market value."""
    if value is None or _is_nan_number(value):
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        if parent_key.lower() in MEANINGFUL_VALUE_META_KEYS:
            return False
        return text.lower() not in {"none", "null", "nan", "n/a", "unavailable", "failed", NO_DATA_AVAILABLE.lower()}
    if isinstance(value, dict):
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in MEANINGFUL_VALUE_META_KEYS:
                continue
            if has_meaningful_observation_value(item, parent_key=key_l):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(has_meaningful_observation_value(item, parent_key=parent_key) for item in value)
    return True


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def no_data_reason(payload: Dict[str, Any]) -> Optional[str]:
    """Return a machine-readable reason when a payload must not be used as evidence."""
    if not isinstance(payload, dict):
        return "invalid_payload"

    data_quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
    sentinel = _first_text(
        payload.get("availability_sentinel"),
        payload.get("no_data_sentinel"),
        data_quality.get("availability_sentinel"),
        data_quality.get("sentinel"),
    )
    if sentinel == NO_DATA_AVAILABLE:
        return _first_text(
            data_quality.get("no_data_reason"),
            data_quality.get("failure_reason"),
            payload.get("error"),
            payload.get("unavailable_reason"),
            payload.get("skip_reason"),
            NO_DATA_AVAILABLE,
        )

    if payload.get("error"):
        return str(payload.get("error"))
    if payload.get("backtest_skipped") or data_quality.get("availability") == "backtest_skipped":
        return _first_text(payload.get("skip_reason"), data_quality.get("failure_reason"), "backtest_skipped_unsupported_function")

    availability = str(payload.get("availability") or data_quality.get("availability") or "").lower()
    source_tier = str(payload.get("source_tier") or data_quality.get("source_tier") or "").lower()
    if availability in NO_DATA_STATUSES:
        return _first_text(payload.get("unavailable_reason"), data_quality.get("failure_reason"), availability)
    if source_tier in NO_DATA_STATUSES:
        return _first_text(payload.get("unavailable_reason"), data_quality.get("failure_reason"), source_tier)
    if payload.get("value") is None and (payload.get("skip_reason") or payload.get("unavailable_reason")):
        return str(payload.get("skip_reason") or payload.get("unavailable_reason"))

    value_has_observation = has_meaningful_observation_value(payload.get("value"))
    if not value_has_observation:
        reason_text = " ".join(
            str(item or "")
            for item in (
                payload.get("notes"),
                payload.get("note"),
                payload.get("unavailable_reason"),
                payload.get("skip_reason"),
                data_quality.get("failure_reason"),
                " ".join(str(x) for x in data_quality.get("anomalies", []) or []),
            )
        ).lower()
        failed_tokens = (
            "failed",
            "unable",
            "unavailable",
            "insufficient",
            "too many open files",
            "empty frame",
            "no valid",
            "not available",
            "missing",
            "数据不足",
            "无法",
            "失败",
            "不可用",
        )
        if any(token in reason_text for token in failed_tokens):
            return _first_text(payload.get("unavailable_reason"), payload.get("skip_reason"), data_quality.get("failure_reason"), "unavailable_payload")
        if payload.get("value") is not None:
            return "empty_observation_payload"
    return None


def is_no_data_payload(payload: Dict[str, Any]) -> bool:
    return no_data_reason(payload) is not None


def normalize_no_data_payload(
    payload: Dict[str, Any],
    *,
    reason: Optional[str] = None,
    source: Optional[str] = None,
    metric: Optional[str] = None,
    effective_date: Optional[str] = None,
    allowed_use: str = "data_boundary_only",
    forbidden_use: str = "do_not_estimate_or_fabricate",
) -> Dict[str, Any]:
    """Attach the NO_DATA_AVAILABLE sentinel without pretending it is an observation."""
    normalized = payload
    data_quality = normalized.get("data_quality") if isinstance(normalized.get("data_quality"), dict) else {}
    data_quality = deepcopy(data_quality)
    reason_text = reason or no_data_reason(normalized) or "no_data"
    existing_availability = str(data_quality.get("availability") or normalized.get("availability") or "").lower()
    availability = existing_availability if existing_availability in NO_DATA_STATUSES else "unavailable"

    normalized["availability"] = availability
    normalized["availability_sentinel"] = NO_DATA_AVAILABLE
    normalized["no_data_text"] = (
        f"{NO_DATA_AVAILABLE}: source={source or normalized.get('source_name') or 'unknown'}; "
        f"metric={metric or normalized.get('function_id') or normalized.get('name') or 'unknown'}; "
        f"reason={reason_text}; allowed_use={allowed_use}; forbidden_use={forbidden_use}"
    )
    normalized["no_data"] = {
        "schema_version": "no_data_sentinel_v1",
        "sentinel": NO_DATA_AVAILABLE,
        "source": source or normalized.get("source_name"),
        "metric": metric or normalized.get("function_id") or normalized.get("name"),
        "effective_date": effective_date or data_quality.get("effective_date") or normalized.get("date"),
        "reason": reason_text,
        "allowed_use": allowed_use,
        "forbidden_use": forbidden_use,
    }
    data_quality["availability"] = availability
    data_quality["sentinel"] = NO_DATA_AVAILABLE
    data_quality["no_data_reason"] = reason_text
    data_quality["allowed_use"] = allowed_use
    data_quality["forbidden_use"] = forbidden_use
    normalized["data_quality"] = data_quality
    return normalized
