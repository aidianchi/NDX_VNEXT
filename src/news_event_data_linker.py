from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


LINKABLE_SERIES = [
    "QQQ_OHLCV",
    "VIX",
    "VXN",
    "US10Y",
    "US10Y_REAL",
    "HY_OAS",
    "HYG",
    "DAMODARAN_ERP_MONTHLY",
]

DEFAULT_WINDOWS_DAYS = [1, 3, 5, 20]

SERIES_THRESHOLDS = {
    "QQQ_OHLCV": {"pct": 2.0},
    "HYG": {"pct": 1.0},
    "VIX": {"abs": 2.0, "pct": 10.0},
    "VXN": {"abs": 2.0, "pct": 10.0},
    "US10Y": {"abs": 0.10},
    "US10Y_REAL": {"abs": 0.10},
    "HY_OAS": {"abs": 0.20},
    "DAMODARAN_ERP_MONTHLY": {"abs": 0.20},
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: str | Path, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    with file_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        for candidate in (text, f"{text}T00:00:00+00:00"):
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                break
            except ValueError:
                parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_number(value: Any) -> Optional[float]:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_value(row: Dict[str, Any]) -> Optional[float]:
    for key in ("close", "value", "Close", "adj_close", "erp_t12m_adjusted_payout"):
        value = _safe_number(row.get(key))
        if value is not None:
            return value
    return None


def _normalized_rows(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_time = _parse_datetime(row.get("time") or row.get("date"))
        value = _row_value(row)
        if row_time is None or value is None:
            continue
        normalized.append({"time": row_time, "value": value})
    return sorted(normalized, key=lambda item: item["time"])


def _window_points(rows: List[Dict[str, Any]], event_time: datetime, days: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], int]:
    start = event_time - timedelta(days=days)
    end = event_time + timedelta(days=days)
    candidates = [row for row in rows if start <= row["time"] <= end]
    if len(candidates) < 2:
        return None, None, len(candidates)
    return candidates[0], candidates[-1], len(candidates)


def _direction(change_abs: float) -> str:
    if change_abs > 0:
        return "up"
    if change_abs < 0:
        return "down"
    return "flat"


def _needs_review(series_key: str, change_abs: float, change_pct: Optional[float], points: int, window_days: int) -> Tuple[bool, str]:
    threshold = SERIES_THRESHOLDS.get(series_key, {"pct": 3.0})
    abs_hit = "abs" in threshold and abs(change_abs) >= float(threshold["abs"])
    pct_hit = change_pct is not None and "pct" in threshold and abs(change_pct) >= float(threshold["pct"])
    enough_points = points >= 2 and window_days <= 5
    if enough_points and (abs_hit or pct_hit):
        return True, "短窗口内该序列变化幅度达到连接器阈值，建议 Bridge 只作为背景观察复核。"
    if window_days == 20 and (abs_hit or pct_hit):
        return True, "20日窗口内该序列变化较明显，适合作为跨层复核线索，不构成因果证明。"
    return False, "变化未达到自动复核阈值；保留为时间邻近观察。"


def _label_for_series(series_key: str, meta: Dict[str, Any]) -> str:
    if series_key == "QQQ_OHLCV":
        return "QQQ"
    return str(meta.get("label") or meta.get("symbol") or series_key)


def _observation_text(label: str, window_days: int, start: Dict[str, Any], end: Dict[str, Any], change_abs: float, change_pct: Optional[float]) -> str:
    pct_text = f", {change_pct:.2f}%" if change_pct is not None else ""
    return (
        f"{label} 在事件日前后 +/-{window_days} 天窗口内从 "
        f"{start['value']:.4g} 变为 {end['value']:.4g}，变化 {change_abs:.4g}{pct_text}。"
    )


class NewsEventDataLinker:
    """Create a sidecar that links official events to nearby market data moves.

    The output is deliberately observational: it never upgrades events into
    evidence refs and never injects event data into L1-L5 runtime context.
    """

    def __init__(self, windows_days: Optional[List[int]] = None, max_events: int = 30, max_observations_per_event: int = 16) -> None:
        self.windows_days = windows_days or list(DEFAULT_WINDOWS_DAYS)
        self.max_events = max_events
        self.max_observations_per_event = max_observations_per_event

    def build(
        self,
        *,
        event_ledger: Dict[str, Any],
        chart_time_series: Dict[str, Any],
        analysis_packet: Optional[Dict[str, Any]] = None,
        output_path: Optional[str | Path] = None,
        source_paths: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        series = chart_time_series.get("series") if isinstance(chart_time_series, dict) else {}
        series = series if isinstance(series, dict) else {}
        events = [event for event in event_ledger.get("events", []) if isinstance(event, dict)]
        prepared = self._prepare_series(series)
        links = []
        for event in events[: self.max_events]:
            link = self._link_event(event, prepared)
            if link:
                links.append(link)
        payload = {
            "schema_version": "news_event_data_links_v1",
            "generated_at_utc": _utc_now_iso(),
            "policy": {
                "runtime_context_rule": "This sidecar is not injected into L1-L5 layer-local prompts.",
                "causality_rule": "Only temporal_association, co_movement_observation, and needs_bridge_review are emitted; no causal proof is asserted.",
                "evidence_rule": "Events and event-data links are never evidence_ref.",
                "allowed_observation_types": ["temporal_association", "co_movement_observation", "needs_bridge_review"],
            },
            "source_artifacts": source_paths or {},
            "windows_days": self.windows_days,
            "linked_series": sorted(prepared.keys()),
            "analysis_packet_context": self._analysis_packet_context(analysis_packet or {}),
            "links": links,
        }
        if output_path:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def _prepare_series(self, series: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        prepared: Dict[str, Dict[str, Any]] = {}
        for series_key in LINKABLE_SERIES:
            meta = series.get(series_key)
            if not isinstance(meta, dict):
                continue
            rows = _normalized_rows(meta.get("rows", []))
            if not rows:
                continue
            prepared[series_key] = {
                "label": _label_for_series(series_key, meta),
                "frequency": meta.get("frequency", ""),
                "source_file": meta.get("source_file", ""),
                "rows": rows,
            }
        return prepared

    def _link_event(self, event: Dict[str, Any], prepared: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        event_time = _parse_datetime(event.get("published_at"))
        if event_time is None:
            return None
        observations: List[Dict[str, Any]] = []
        for series_key, meta in prepared.items():
            rows = meta["rows"]
            for window_days in self.windows_days:
                start, end, points = _window_points(rows, event_time, window_days)
                if start is None or end is None:
                    continue
                change_abs = round(end["value"] - start["value"], 6)
                change_pct = None if start["value"] == 0 else round((change_abs / start["value"]) * 100, 4)
                review, rationale = _needs_review(series_key, change_abs, change_pct, points, window_days)
                observation_type = "needs_bridge_review" if review else "co_movement_observation"
                observations.append(
                    {
                        "observation_type": observation_type,
                        "association_type": "temporal_association",
                        "series_key": series_key,
                        "series_label": meta["label"],
                        "frequency": meta.get("frequency", ""),
                        "window_days": window_days,
                        "start_time": start["time"].date().isoformat(),
                        "end_time": end["time"].date().isoformat(),
                        "points": points,
                        "start_value": round(start["value"], 6),
                        "end_value": round(end["value"], 6),
                        "change_abs": change_abs,
                        "change_pct": change_pct,
                        "direction": _direction(change_abs),
                        "needs_bridge_review": review,
                        "bridge_review_rationale": rationale,
                        "statement": _observation_text(meta["label"], window_days, start, end, change_abs, change_pct),
                    }
                )
        observations = sorted(
            observations,
            key=lambda item: (not item["needs_bridge_review"], item["window_days"], item["series_key"]),
        )[: self.max_observations_per_event]
        if not observations:
            return None
        return {
            "event_ref": event.get("event_id"),
            "event_id": event.get("event_id"),
            "dedupe_id": event.get("dedupe_id"),
            "title": event.get("title"),
            "published_at": event.get("published_at"),
            "source_tier": event.get("source_tier"),
            "event_type": event.get("event_type"),
            "symbols": event.get("symbols", []),
            "layers": event.get("layers", []),
            "link_boundary": "temporal_association only; no causal proof and no evidence_ref.",
            "observations": observations,
        }

    def _analysis_packet_context(self, analysis_packet: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(analysis_packet, "model_dump"):
            analysis_packet = analysis_packet.model_dump()
        elif not isinstance(analysis_packet, dict):
            analysis_packet = {}
        meta = analysis_packet.get("meta", {}) if isinstance(analysis_packet, dict) else {}
        event_refs = analysis_packet.get("event_refs", {}) if isinstance(analysis_packet, dict) else {}
        return {
            "data_date": meta.get("data_date"),
            "event_refs_available": len(event_refs) if isinstance(event_refs, dict) else 0,
            "note": "analysis_packet is used only for metadata/source alignment; event links are not added to layer raw_data.",
        }


def write_news_event_data_links(
    run_dir: str | Path,
    *,
    event_ledger: Optional[Dict[str, Any]] = None,
    chart_time_series: Optional[Dict[str, Any]] = None,
    analysis_packet: Optional[Dict[str, Any]] = None,
    event_ledger_path: Optional[str | Path] = None,
    chart_time_series_path: Optional[str | Path] = None,
    analysis_packet_path: Optional[str | Path] = None,
) -> str:
    run_path = Path(run_dir)
    event_path = Path(event_ledger_path) if event_ledger_path else run_path / "news_event_ledger.json"
    chart_path = Path(chart_time_series_path) if chart_time_series_path else run_path / "chart_time_series.json"
    packet_path = Path(analysis_packet_path) if analysis_packet_path else run_path / "analysis_packet.json"
    ledger_payload = event_ledger if event_ledger is not None else _load_json(event_path, {})
    chart_payload = chart_time_series if chart_time_series is not None else _load_json(chart_path, {})
    packet_payload = analysis_packet if analysis_packet is not None else _load_json(packet_path, {})
    output_path = run_path / "news_event_data_links.json"
    NewsEventDataLinker().build(
        event_ledger=ledger_payload,
        chart_time_series=chart_payload,
        analysis_packet=packet_payload,
        output_path=output_path,
        source_paths={
            "news_event_ledger": str(event_path),
            "chart_time_series": str(chart_path),
            "analysis_packet": str(packet_path),
        },
    )
    return str(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build event-to-market-data observational links.")
    parser.add_argument("--run-dir", required=True, help="vNext run directory containing news_event_ledger.json and chart_time_series.json.")
    args = parser.parse_args()
    output = write_news_event_data_links(args.run_dir)
    print(json.dumps({"news_event_data_links": output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
