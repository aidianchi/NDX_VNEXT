from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


Fetcher = Callable[[int], Any]


def _safe_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    getter = getattr(row, "get", None)
    if callable(getter):
        return getter(key)
    return getattr(row, key, None)


def _date_text(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value or "")


def _default_fetcher(lookback_days: int) -> Any:
    try:
        from chart_adapter_v6 import get_qqq_price_data
    except ImportError:
        from .chart_adapter_v6 import get_qqq_price_data

    return get_qqq_price_data(lookback_days=lookback_days)


def _frame_to_rows(frame: Any) -> List[Dict[str, Any]]:
    if frame is None or getattr(frame, "empty", False):
        return []
    closes: List[float] = []
    rows: List[Dict[str, Any]] = []
    for _, row in frame.iterrows():
        close = _safe_number(_row_get(row, "close"))
        if close is None:
            continue
        closes.append(close)
        prepared = {
            "time": _date_text(_row_get(row, "date")),
            "open": _safe_number(_row_get(row, "open")) or close,
            "high": _safe_number(_row_get(row, "high")) or close,
            "low": _safe_number(_row_get(row, "low")) or close,
            "close": close,
            "volume": _safe_number(_row_get(row, "volume")) or 0.0,
        }
        for window in [5, 20, 60, 200]:
            tail = closes[-window:]
            prepared[f"ma{window}"] = sum(tail) / len(tail)
        rows.append(prepared)
    return rows


def build_chart_time_series_artifact(
    *,
    lookback_days: int = 420,
    fetcher: Optional[Fetcher] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload: Dict[str, Any] = {
        "schema_version": "vnext_chart_time_series_v1",
        "generated_at_utc": generated_at,
        "series": {
            "QQQ_OHLCV": {
                "symbol": "QQQ",
                "provider": "yfinance via chart_adapter_v6",
                "source_file": "chart_time_series.json",
                "frequency": "daily",
                "lookback_days": lookback_days,
                "rows": [],
            }
        },
        "caveats": [
            "This artifact is for native interactive charting and audit alignment. It should not replace L5 indicator interpretation.",
        ],
    }
    try:
        frame = (fetcher or _default_fetcher)(lookback_days)
        payload["series"]["QQQ_OHLCV"]["rows"] = _frame_to_rows(frame)
    except Exception as exc:  # pragma: no cover - defensive artifact fallback
        payload["series"]["QQQ_OHLCV"]["availability"] = "unavailable"
        payload["series"]["QQQ_OHLCV"]["unavailable_reason"] = str(exc)
    return payload


def write_chart_time_series_artifact(
    run_dir: str | Path,
    *,
    lookback_days: int = 420,
    fetcher: Optional[Fetcher] = None,
    generated_at: Optional[str] = None,
) -> str:
    path = Path(run_dir) / "chart_time_series.json"
    payload = build_chart_time_series_artifact(
        lookback_days=lookback_days,
        fetcher=fetcher,
        generated_at=generated_at,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
