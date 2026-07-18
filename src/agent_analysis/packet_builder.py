from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from .contracts import AnalysisPacket, CandidateCrossLayerLink, LayerFacts
except ImportError:
    from agent_analysis.contracts import AnalysisPacket, CandidateCrossLayerLink, LayerFacts

try:
    from ..config import path_config
except ImportError:
    from config import path_config

try:
    from ..manual_data import has_meaningful_manual_override, load_manual_data
except ImportError:
    from manual_data import has_meaningful_manual_override, load_manual_data

try:
    from ..data_availability import (
        has_meaningful_observation_value as _shared_has_meaningful_observation_value,
        no_data_reason as _shared_no_data_reason,
    )
except ImportError:
    from data_availability import (
        has_meaningful_observation_value as _shared_has_meaningful_observation_value,
        no_data_reason as _shared_no_data_reason,
    )

try:
    from ..data_evidence import data_evidence_issues, flatten_issue_groups
except ImportError:
    from data_evidence import data_evidence_issues, flatten_issue_groups

logger = logging.getLogger(__name__)


def _strip_recompute_audit_inputs(value: Any) -> Any:
    """Enforce the prompt/artifact boundary even for replayed or hand-built payloads."""
    if isinstance(value, dict):
        return {
            key: _strip_recompute_audit_inputs(item)
            for key, item in value.items()
            if key not in {"recompute_input", "recompute_inputs"}
        }
    if isinstance(value, list):
        return [_strip_recompute_audit_inputs(item) for item in value]
    return value

LAYER_NAMES = {
    "L1": "宏观流动性",
    "L2": "风险偏好",
    "L3": "内部健康度",
    "L4": "估值",
    "L5": "趋势与波动",
}

LAYER_FUNCTIONS = {
    "L1": {
        "get_10y2y_spread_bp",
        "get_fed_funds_rate",
        "get_fed_funds_rate_path",
        "get_m2_yoy",
        "get_net_liquidity_momentum",
        "get_copper_gold_ratio",
        "get_10y_treasury",
        "get_10y_real_rate",
        "get_10y_breakeven",
    },
    "L2": {
        "get_vix",
        "get_vxn",
        "get_hy_oas_bp",
        "get_ig_oas_bp",
        "get_hy_quality_spread_bp",
        "get_hyg_momentum",
        "get_xly_xlp_ratio",
        "get_crowdedness_dashboard",
        "get_cftc_nq_positioning",
        "get_finra_margin_debt",
        "get_vxn_vix_ratio",
        "get_vix_term_structure",
        "get_cnn_fear_greed_index",
    },
    "L3": {
        "get_advance_decline_line",
        "get_percent_above_ma",
        "get_ndx_ndxe_ratio",
        "get_qqq_top10_concentration",
        "get_new_highs_lows",
        "get_mcclellan_oscillator_nasdaq_or_nyse",
    },
    "L4": {
        "get_ndx_wind_valuation_snapshot",
        "get_ndx_wind_point_in_time_earnings_expectations",
        "get_ndx_pe_and_earnings_yield",
        "get_ndx_forward_earnings_quality",
        "get_equity_risk_premium",
        "get_m7_capex_cycle",
        "get_m7_earnings_blackout_calendar",
        "get_m7_buyback_flow",
        "get_damodaran_us_implied_erp",
    },
    "L5": {
        "get_l5_deterministic_snapshot",
        "get_qqq_technical_indicators",
        "get_rsi_qqq",
        "get_atr_qqq",
        "get_adx_qqq",
        "get_macd_qqq",
        "get_obv_qqq",
        "get_volume_analysis_qqq",
        "get_price_volume_quality_qqq",
        "get_donchian_channels_qqq",
        "get_multi_scale_ma_position",
    },
}


_MEANINGFUL_VALUE_META_KEYS = {
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
}


def _has_meaningful_observation_value(value: Any, *, parent_key: str = "") -> bool:
    return _shared_has_meaningful_observation_value(value, parent_key=parent_key)


def _payload_unavailable_reason(payload: Dict[str, Any]) -> Optional[str]:
    return _shared_no_data_reason(payload)


def _normalize_historical_percentile(value: Any) -> Optional[float]:
    """Normalize supported percentile scales to 0-100 and reject invalid values."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    percentile = float(value)
    if not 0.0 <= percentile <= 100.0:
        return None
    if percentile <= 1.0:
        percentile *= 100.0
    return percentile


_HISTORICAL_PERCENTILE_KEY_PRIORITY = (
    "percentile_10y",
    "percentile_5y",
    "percentile_1y",
    "percentile",
)


def indicator_payload_unavailable_reason(payload: Dict[str, Any]) -> Optional[str]:
    """Public helper for prompt orchestration to share packet availability rules."""
    return _payload_unavailable_reason(payload)


def _indicator_error(indicator: Dict[str, Any], raw_payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
    error = indicator.get("error")
    if error:
        return str(error)
    payload = raw_payload if isinstance(raw_payload, dict) else indicator.get("raw_data")
    if isinstance(payload, dict):
        reason = _payload_unavailable_reason(payload)
        if reason:
            return reason
    if indicator.get("backtest_skipped"):
        return "backtest_skipped_unsupported_function"
    return None


def _indicator_successful(indicator: Dict[str, Any]) -> bool:
    if _indicator_error(indicator):
        return False
    raw = indicator.get("raw_data") if isinstance(indicator.get("raw_data"), dict) else {}
    if _payload_unavailable_reason(raw):
        return False
    if "value" in raw:
        return _has_meaningful_observation_value(raw.get("value"))
    return indicator.get("value") is not None or bool(raw)


def _data_evidence_issue_rows(indicator: Dict[str, Any], backtest_date: Optional[str]) -> List[Dict[str, Any]]:
    raw = indicator.get("raw_data") if isinstance(indicator.get("raw_data"), dict) else {}
    function_id = str(indicator.get("function_id") or raw.get("function_id") or indicator.get("metric_name") or "unknown_metric")
    rows = flatten_issue_groups(data_evidence_issues(raw, function_id=function_id, backtest_date=backtest_date))
    for row in rows:
        row["metric_name"] = indicator.get("metric_name")
        row["layer"] = indicator.get("layer")
    return rows


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _sanitize_manual_overrides(manual_overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Keep inactive manual config auditable without exposing metric values to agents."""
    overrides = deepcopy(manual_overrides if isinstance(manual_overrides, dict) else {})
    metrics = overrides.get("metrics") if isinstance(overrides.get("metrics"), dict) else {}
    if overrides.get("active"):
        return _strip_recompute_audit_inputs(overrides)
    return {
        "active": False,
        "date": overrides.get("date", ""),
        "metrics": {},
        "inactive_metric_count": len(metrics),
        "inactive_metrics_hidden": bool(metrics),
    }


def _round_if_float(value: Any) -> Any:
    return round(value, 4) if isinstance(value, float) else value


def _find_first_number(data: Any, keywords: Iterable[str] = ()) -> Optional[float]:
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if lowered_keywords:
            return None
        return float(data)
    if isinstance(data, dict):
        if lowered_keywords:
            for key, value in data.items():
                key_l = str(key).lower()
                if key_l in lowered_keywords and isinstance(value, (int, float)) and not isinstance(value, bool):
                    return float(value)
            for key, value in data.items():
                key_l = str(key).lower()
                if any(keyword in key_l for keyword in lowered_keywords):
                    found = _find_first_number(value)
                    if found is not None:
                        return found
        for value in data.values():
            found = _find_first_number(value, keywords)
            if found is not None:
                return found
    if isinstance(data, (list, tuple)):
        for item in data:
            found = _find_first_number(item, keywords)
            if found is not None:
                return found
    return None


def _find_first_string(data: Any, keywords: Iterable[str]) -> Optional[str]:
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    if isinstance(data, dict):
        for key, value in data.items():
            key_l = str(key).lower()
            if key_l in lowered_keywords and isinstance(value, str) and value.strip():
                return value.strip()
        for key, value in data.items():
            key_l = str(key).lower()
            if any(keyword in key_l for keyword in lowered_keywords):
                found = _find_first_string(value, keywords)
                if found:
                    return found
        for value in data.values():
            found = _find_first_string(value, keywords)
            if found:
                return found
    if isinstance(data, (list, tuple)):
        for item in data:
            found = _find_first_string(item, keywords)
            if found:
                return found
    return None


def _compact_value(value: Any, *, max_items: int = 3) -> Any:
    if isinstance(value, (str, int, float)) or value is None:
        return _round_if_float(value)
    if isinstance(value, dict):
        compact: Dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, (str, int, float)) or item is None:
                compact[str(key)] = _round_if_float(item)
            elif isinstance(item, dict):
                nested = _compact_value(item, max_items=max_items)
                if nested:
                    compact[str(key)] = nested
            if len(compact) >= max_items:
                break
        return compact
    if isinstance(value, list):
        return [_compact_value(item, max_items=max_items) for item in value[:max_items]]
    return str(value)[:200]


def _build_object_run_gate(data_date: str, data_json: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "object_run_gate_v1",
        "primary_object": "NDX",
        "tradable_proxy": "QQQ",
        "equal_weight_references": ["NDXE", "QEW"],
        "object_scope": (
            "NDX is the Nasdaq-100 index; QQQ is a tradable proxy; "
            "NDXE/QEW are equal-weight references for breadth and concentration checks."
        ),
        "date_boundary": data_date,
        "methodology_boundary": (
            "Treat Nasdaq-100 as a rules-based modified market-cap weighted index. "
            "Methodology, quarterly rebalancing, annual reconstitution, and the "
            "2026-05-01 methodology update are object-level boundaries."
        ),
        "data_boundary": (
            "Use the collector snapshot for this run and preserve backtest_data_boundaries "
            "or strict_backtest_invariants when present."
        ),
        "evidence_boundary": (
            "Object definition is static context and cannot be used as an L1-L5 evidence_ref "
            "for market, valuation, breadth, or trend claims."
        ),
        "backtest_date": data_json.get("backtest_date"),
    }


class AnalysisPacketBuilder:
    """Build an L1-L5 aligned analysis packet from collector output."""

    def __init__(self, version: str = "vNext-1.0"):
        self.version = version

    def build(
        self,
        data_json: Dict[str, Any],
        *,
        manual_overrides: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        event_ledger: Optional[Dict[str, Any]] = None,
        event_ledger_path: Optional[str] = None,
        allow_event_refs: bool = False,
        output_path: Optional[str] = None,
    ) -> AnalysisPacket:
        manual_overrides = _sanitize_manual_overrides(
            manual_overrides if manual_overrides is not None else load_manual_data()
        )
        grouped_raw_data = self._group_raw_data(data_json, manual_overrides)
        facts_by_layer = {
            layer: self._build_layer_facts(layer, grouped_raw_data.get(layer, {}))
            for layer in LAYER_NAMES
        }
        candidate_links = self._build_candidate_links(facts_by_layer)
        event_refs = (
            self._build_event_refs(event_ledger=event_ledger, event_ledger_path=event_ledger_path)
            if allow_event_refs
            else {}
        )
        packet = AnalysisPacket(
            meta=self._build_meta(data_json, manual_overrides, grouped_raw_data),
            raw_data=grouped_raw_data,
            facts_by_layer=facts_by_layer,
            candidate_cross_layer_links=candidate_links,
            event_refs=event_refs,
            manual_overrides=manual_overrides,
            context=self._build_context(data_json, facts_by_layer, context),
        )
        if output_path:
            self.save(packet, output_path)
        return packet

    def save(self, packet: AnalysisPacket, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(_model_dump(packet), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        logger.info("Analysis packet saved to %s", path)
        return str(path)

    def _build_event_refs(
        self,
        *,
        event_ledger: Optional[Dict[str, Any]] = None,
        event_ledger_path: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        payload = event_ledger
        if payload is None and event_ledger_path:
            path = Path(event_ledger_path)
            if path.exists():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    logger.warning("Failed to parse event ledger: %s", path)
                    payload = None
        if not isinstance(payload, dict):
            return {}
        refs: Dict[str, Dict[str, Any]] = {}
        for event in payload.get("events", []):
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("event_id") or "").strip()
            if not event_id:
                continue
            refs[event_id] = {
                "event_id": event_id,
                "dedupe_id": event.get("dedupe_id"),
                "source_id": event.get("source_id"),
                "source_name": event.get("source_name"),
                "source_tier": event.get("source_tier") or event.get("authority_tier"),
                "event_type": event.get("event_type"),
                "title": event.get("title"),
                "url": event.get("url"),
                "published_at": event.get("published_at"),
                "layers": event.get("layers") or event.get("relevance_tags") or [],
                "symbols": event.get("symbols") or [],
                "confidence": event.get("confidence"),
                "usage_boundary": "event_ref only: catalyst/background/observation, not numeric proof",
            }
        return refs

    def default_output_path(self, data_date: str) -> str:
        return str(Path(path_config.analysis_dir) / f"analysis_packet_{data_date}.json")

    def _build_meta(
        self,
        data_json: Dict[str, Any],
        manual_overrides: Dict[str, Any],
        grouped_raw_data: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        indicators = data_json.get("indicators", [])
        total_indicators = len(indicators)
        evidence_issues = [
            issue
            for indicator in indicators
            for issue in _data_evidence_issue_rows(indicator, data_json.get("backtest_date"))
        ]
        evidence_summary = {
            severity: sum(1 for issue in evidence_issues if issue.get("severity") == severity)
            for severity in ("hard_block", "degraded", "audit_warn")
        }
        hard_block_ids = {
            str(issue.get("function_id"))
            for issue in evidence_issues
            if issue.get("severity") == "hard_block"
        }
        successful_indicators = sum(
            1
            for item in indicators
            if _indicator_successful(item) and str(item.get("function_id")) not in hard_block_ids
        )
        manual_count = 0
        for metrics in grouped_raw_data.values():
            manual_count += sum(1 for item in metrics.values() if item.get("manual_override_used"))

        backtest_date = data_json.get("backtest_date")
        timestamp = data_json.get("timestamp_utc") or _utc_now().isoformat()
        data_date = backtest_date or str(timestamp)[:10]
        return {
            "version": self.version,
            "schema_version": "1.0",
            "generated_at": _utc_now().isoformat(),
            "data_date": data_date,
            "object_run_gate": _build_object_run_gate(data_date, data_json),
            "collector_timestamp_utc": data_json.get("timestamp_utc"),
            "backtest_date": backtest_date,
            "indicator_total": total_indicators,
            "indicator_successful": successful_indicators,
            "manual_override_count": manual_count,
            "manual_override_active": bool(manual_overrides.get("active")),
            "backtest_data_boundaries": data_json.get("backtest_data_boundaries", []),
            "strict_backtest_invariants": data_json.get("strict_backtest_invariants", {}),
            "data_evidence_contract_summary": evidence_summary,
            "data_evidence_hard_blocks": [
                issue for issue in evidence_issues if issue.get("severity") == "hard_block"
            ],
        }

    def _build_context(
        self,
        data_json: Dict[str, Any],
        facts_by_layer: Dict[str, LayerFacts],
        extra_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        evidence_issues = [
            issue
            for indicator in data_json.get("indicators", [])
            for issue in _data_evidence_issue_rows(indicator, data_json.get("backtest_date"))
        ]
        context = {
            "source_timestamp_utc": data_json.get("timestamp_utc"),
            "backtest_date": data_json.get("backtest_date"),
            "object_run_gate": _build_object_run_gate(
                data_json.get("backtest_date") or str(data_json.get("timestamp_utc") or "")[:10],
                data_json,
            ),
            "backtest_data_boundaries": data_json.get("backtest_data_boundaries", []),
            "strict_backtest_invariants": data_json.get("strict_backtest_invariants", {}),
            "data_evidence_contract_summary": {
                severity: sum(1 for issue in evidence_issues if issue.get("severity") == severity)
                for severity in ("hard_block", "degraded", "audit_warn")
            },
            "data_evidence_hard_blocks": [
                issue for issue in evidence_issues if issue.get("severity") == "hard_block"
            ],
            "layer_states": {layer: facts.state for layer, facts in facts_by_layer.items()},
            "layer_summaries": {layer: facts.summary for layer, facts in facts_by_layer.items()},
        }
        if isinstance(extra_context, dict):
            context.update(_strip_recompute_audit_inputs(extra_context))
        return _strip_recompute_audit_inputs(context)

    def _group_raw_data(
        self,
        data_json: Dict[str, Any],
        manual_overrides: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        grouped = {layer: {} for layer in LAYER_NAMES}
        manual_metrics = manual_overrides.get("metrics", {}) if isinstance(manual_overrides, dict) else {}

        for indicator in data_json.get("indicators", []):
            layer_value = indicator.get("layer")
            layer = f"L{layer_value}" if isinstance(layer_value, int) else str(layer_value or "").upper()
            if layer not in grouped:
                continue

            function_id = str(indicator.get("function_id") or indicator.get("metric_name") or "").strip()
            if not function_id:
                continue

            raw_payload = _strip_recompute_audit_inputs(
                deepcopy(indicator.get("raw_data") if isinstance(indicator.get("raw_data"), dict) else {})
            )
            raw_payload.setdefault("name", indicator.get("metric_name") or function_id)
            raw_payload["function_id"] = function_id
            raw_payload["metric_name"] = indicator.get("metric_name") or raw_payload.get("name") or function_id
            raw_payload["error"] = _indicator_error(indicator, raw_payload)
            raw_payload["collection_timestamp_utc"] = indicator.get("collection_timestamp_utc")
            issue_rows = _data_evidence_issue_rows(indicator, data_json.get("backtest_date"))
            hard_blocks = [issue for issue in issue_rows if issue.get("severity") == "hard_block"]
            if hard_blocks:
                grouped[layer][function_id] = {
                    "function_id": function_id,
                    "metric_name": raw_payload.get("metric_name"),
                    "name": raw_payload.get("name"),
                    "value": None,
                    "error": "data_evidence_hard_block",
                    "data_quality": raw_payload.get("data_quality", {}),
                    "data_evidence_hard_block_issues": hard_blocks,
                    "collection_timestamp_utc": indicator.get("collection_timestamp_utc"),
                }
                continue

            manual_metric = manual_metrics.get(function_id) if isinstance(manual_metrics, dict) else None
            raw_payload["manual_override_used"] = bool(
                manual_overrides.get("active") and has_meaningful_manual_override(manual_metric)
            )
            grouped[layer][function_id] = raw_payload

        for layer, expected_functions in LAYER_FUNCTIONS.items():
            for function_id in expected_functions:
                grouped[layer].setdefault(
                    function_id,
                    {
                        "function_id": function_id,
                        "metric_name": function_id,
                        "value": None,
                        "error": "missing_from_collector_output",
                    },
                )
        return grouped

    def _build_layer_facts(self, layer: str, metrics: Dict[str, Dict[str, Any]]) -> LayerFacts:
        core_signals = [self._build_signal(function_id, payload) for function_id, payload in metrics.items()]
        core_signals = sorted(
            core_signals,
            key=lambda item: (
                item.get("error") is not None,
                item.get("historical_percentile") is None,
                item.get("metric"),
            ),
        )
        state = self._infer_layer_state(layer, metrics)
        usable_signals = [signal for signal in core_signals if not signal.get("error")]
        unavailable_signals = [signal for signal in core_signals if signal.get("error")]
        key_metrics = [signal["metric"] for signal in usable_signals][:5]
        summary_parts = [signal["summary"] for signal in usable_signals if signal.get("summary")][:3]
        if not summary_parts:
            summary_parts = ["关键指标不完整"]
        if unavailable_signals:
            summary_parts.append(
                "缺口="
                + ",".join(signal["metric"] for signal in unavailable_signals[:3])
            )
        summary = f"{LAYER_NAMES[layer]}状态: {state}。关键事实: {'；'.join(summary_parts)}。"
        return LayerFacts(
            core_signals=(usable_signals + unavailable_signals)[:8],
            state=state,
            key_metrics=key_metrics,
            summary=summary,
        )

    def _build_signal(self, function_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        value = payload.get("value")
        percentile = (
            self._extract_wind_ndx_valuation_percentile(value)
            if function_id == "get_ndx_wind_valuation_snapshot"
            else
            self._extract_l4_valuation_percentile(value, payload=payload)
            if function_id == "get_ndx_pe_and_earnings_yield"
            else self._extract_damodaran_erp_percentile(value)
            if function_id == "get_damodaran_us_implied_erp"
            else self._extract_percentile(value)
        )
        trend = self._extract_trend(value)
        status = self._extract_status(value)
        compact_value = self._extract_signal_value(value, function_id=function_id)
        relative_position_context = self._extract_relative_position_context(value, function_id=function_id)
        summary_bits = [payload.get("metric_name") or function_id]
        if compact_value is not None:
            summary_bits.append(f"值={compact_value}")
        if percentile is not None and function_id == "get_damodaran_us_implied_erp":
            summary_bits.append(f"Damodaran ERP 10Y分位={percentile}")
        elif percentile is not None and function_id == "get_ndx_wind_valuation_snapshot":
            summary_bits.append(f"Wind PE分位={percentile}")
        elif percentile is not None:
            summary_bits.append(f"分位={percentile}")
        if function_id == "get_ndx_wind_valuation_snapshot" and isinstance(value, dict):
            risk_pct = _normalize_historical_percentile(
                _find_first_number(
                    value,
                    (
                        "riskpremiumhistoricalpercentile",
                        "risk_premium_historical_percentile",
                        "RiskPremiumHistoricalPercentile",
                    ),
                )
            )
            risk_level = _find_first_number(value, ("riskpremium", "risk_premium", "RiskPremium"))
            if risk_level is not None:
                summary_bits.append(f"Wind风险溢价={_round_if_float(risk_level)}")
            if risk_pct is not None:
                summary_bits.append(f"Wind风险溢价分位={_round_if_float(risk_pct)}")
        if trend:
            summary_bits.append(f"趋势={trend}")
        if status:
            summary_bits.append(f"状态={status}")
        if payload.get("manual_override_used"):
            summary_bits.append("人工覆盖")
        if function_id == "get_ndx_pe_and_earnings_yield" and percentile is None and compact_value is not None:
            summary_bits.append("历史分位缺失")
        if relative_position_context:
            summary_bits.append("含非分位相对位置")
        if payload.get("error"):
            summary_bits.append(f"异常={payload['error']}")
        signal = {
            "metric": function_id,
            "metric_name": payload.get("metric_name") or function_id,
            "value": compact_value,
            "historical_percentile": percentile,
            "trend": trend,
            "status": status,
            "source_name": payload.get("source_name"),
            "error": payload.get("error"),
            "summary": " | ".join(str(bit) for bit in summary_bits if bit),
        }
        if relative_position_context:
            signal["relative_position_context"] = relative_position_context
        return signal

    def _extract_signal_value(self, value: Any, *, function_id: str = "") -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float)):
            return _round_if_float(value)
        if isinstance(value, dict):
            if function_id == "get_ndx_wind_valuation_snapshot":
                return {
                    key: _round_if_float(value[key])
                    for key in ("PE", "PB", "PS", "RiskPremium")
                    if key in value and value.get(key) is not None
                }
            if function_id == "get_price_volume_quality_qqq":
                return {
                    key: _round_if_float(value[key])
                    for key in ("vwap_20", "mfi_14", "cmf_20")
                    if key in value
                }
            level = value.get("level")
            if isinstance(level, (str, int, float)):
                return _round_if_float(level)
            if isinstance(level, dict):
                return _compact_value(level)
            score = value.get("score")
            if isinstance(score, (int, float)):
                return _round_if_float(score)
            if len(value) <= 4:
                return _compact_value(value)
        return _compact_value(value)

    def _extract_percentile(self, value: Any) -> Optional[float]:
        # Search one window at a time so dictionary insertion order cannot make
        # a shorter window override an available 10Y/5Y percentile.
        for key in _HISTORICAL_PERCENTILE_KEY_PRIORITY:
            percentile = _normalize_historical_percentile(_find_first_number(value, (key,)))
            if percentile is not None:
                return percentile
        return None

    def _extract_damodaran_erp_percentile(self, value: Any) -> Optional[float]:
        if not isinstance(value, dict):
            return None
        percentile = value.get("damodaran_erp_percentile_10y")
        if isinstance(percentile, (int, float)) and not isinstance(percentile, bool):
            return _normalize_historical_percentile(percentile)
        windows = value.get("damodaran_erp_historical_percentiles", {}).get("windows", {})
        if isinstance(windows, dict):
            window_10y = windows.get("10y")
            if isinstance(window_10y, dict):
                percentile = window_10y.get("percentile")
                if isinstance(percentile, (int, float)) and not isinstance(percentile, bool):
                    return _normalize_historical_percentile(percentile)
        return None

    def _extract_wind_ndx_valuation_percentile(self, value: Any) -> Optional[float]:
        if not isinstance(value, dict):
            return None
        for key in ("PEHistoricalPercentile", "pe_historical_percentile", "pe_percentile"):
            percentile = value.get(key)
            if isinstance(percentile, (int, float)) and not isinstance(percentile, bool):
                return _normalize_historical_percentile(percentile)
        return None

    def _extract_l4_valuation_percentile(self, value: Any, *, payload: Optional[Dict[str, Any]] = None) -> Optional[float]:
        if not isinstance(value, dict):
            return self._extract_percentile(value)

        checks = value.get("ThirdPartyChecks")
        root_value = {key: item for key, item in value.items() if key != "ThirdPartyChecks"}
        payload = payload or {}
        source_tier = str(payload.get("source_tier") or payload.get("data_quality", {}).get("source_tier") or "").lower()
        source_name = str(payload.get("source_name") or "").lower()

        # Root-level percentiles are accepted for Manual/Wind or legacy explicit inputs,
        # but not for yfinance component-model current valuation proxies.
        if "component_model" not in source_tier and "yfinance" not in source_name:
            root_percentile = self._extract_percentile(root_value)
            if root_percentile is not None:
                return root_percentile

        if not isinstance(checks, list):
            return None

        def source_percentile(*source_tokens: str) -> Optional[float]:
            for item in checks:
                if not isinstance(item, dict):
                    continue
                if str(item.get("availability") or "").lower() != "available":
                    continue
                if str(item.get("usage") or "validation_only").lower() not in {"validation_only", "core_allowed"}:
                    continue
                source_label = " ".join(
                    str(item.get(key) or "")
                    for key in ("source_id", "source", "source_name")
                ).lower()
                if not any(token in source_label for token in source_tokens):
                    continue
                for key in ("historical_percentile", *_HISTORICAL_PERCENTILE_KEY_PRIORITY):
                    percentile = _normalize_historical_percentile(_find_first_number(item, (key,)))
                    if percentile is not None:
                        return percentile
            return None

        for percentile in (
            source_percentile("danjuan"),
            source_percentile("worldperatio"),
            source_percentile("history_of_market"),
        ):
            if percentile is not None:
                return percentile
        return None

    def _extract_relative_position_context(self, value: Any, *, function_id: str = "") -> Dict[str, Any]:
        if function_id != "get_ndx_pe_and_earnings_yield" or not isinstance(value, dict):
            return {}
        checks = value.get("ThirdPartyChecks")
        if not isinstance(checks, list):
            return {}
        context: Dict[str, Any] = {}
        for item in checks:
            if not isinstance(item, dict) or not isinstance(item.get("relative_position"), dict):
                continue
            if str(item.get("availability") or "").lower() != "available":
                continue
            if str(item.get("usage") or "validation_only").lower() not in {"validation_only", "core_allowed"}:
                continue
            source_name = str(item.get("source_name") or item.get("source_id") or item.get("source") or "unknown")
            context[source_name] = item["relative_position"]
        return context

    def _extract_trend(self, value: Any) -> Optional[str]:
        return _find_first_string(
            value,
            (
                "trend",
                "direction",
                "sma_position",
                "position_vs_ma",
                "ratio_trend_vs_ma20",
                "obv_trend",
                "volume_price_relationship",
                "donchian_signal",
            ),
        )

    def _extract_status(self, value: Any) -> Optional[str]:
        return _find_first_string(
            value,
            (
                "status",
                "rating",
                "signal",
                "cross_signal",
                "rsi_status",
                "volume_status",
                "bb_compression_status",
            ),
        )

    def _metric_level(self, metrics: Dict[str, Dict[str, Any]], function_id: str, *keywords: str) -> Optional[float]:
        payload = metrics.get(function_id, {})
        value = payload.get("value")
        if keywords:
            return _find_first_number(value, keywords)
        return _find_first_number(value, ("level", "score", "value", "current_price"))

    def _metric_text(self, metrics: Dict[str, Dict[str, Any]], function_id: str, *keywords: str) -> Optional[str]:
        payload = metrics.get(function_id, {})
        value = payload.get("value")
        if keywords:
            return _find_first_string(value, keywords)
        return _find_first_string(value, ("trend", "status", "rating", "sma_position"))

    def _infer_layer_state(self, layer: str, metrics: Dict[str, Dict[str, Any]]) -> str:
        if layer == "L1":
            fed_rate = self._metric_level(metrics, "get_fed_funds_rate", "level")
            real_rate = self._metric_level(metrics, "get_10y_real_rate", "level")
            liquidity_momentum = self._metric_level(metrics, "get_net_liquidity_momentum", "momentum_4w")
            if (fed_rate is not None and fed_rate >= 4.0) or (real_rate is not None and real_rate >= 1.5):
                return "restrictive"
            if liquidity_momentum is not None and liquidity_momentum < 0:
                return "restrictive"
            if (fed_rate is not None and fed_rate <= 2.0) and (real_rate is None or real_rate <= 0.5):
                return "expansionary"
            return "neutral"

        if layer == "L2":
            vix = self._metric_level(metrics, "get_vix", "level")
            hy_oas = self._metric_level(metrics, "get_hy_oas_bp", "level")
            hy_quality_spread = self._metric_level(metrics, "get_hy_quality_spread_bp", "level")
            fear_greed = self._metric_level(metrics, "get_cnn_fear_greed_index", "score")
            vol_stress = vix is not None and vix >= 25
            credit_stress = (
                (hy_oas is not None and hy_oas >= 500)
                or (hy_quality_spread is not None and hy_quality_spread >= 700)
            )
            sentiment_stress_confirmed = (
                fear_greed is not None
                and fear_greed <= 30
                and ((vix is not None and vix >= 20) or credit_stress)
            )
            if vol_stress or credit_stress or sentiment_stress_confirmed:
                return "risk_off"
            credit_calm = (
                hy_oas is not None
                and hy_oas < 350
                and (hy_quality_spread is None or hy_quality_spread < 500)
            )
            if vix is not None and vix <= 15 and credit_calm:
                return "risk_on"
            return "neutral"

        if layer == "L3":
            usable_count = sum(1 for payload in metrics.values() if not _payload_unavailable_reason(payload))
            ratio_payload = metrics.get("get_ndx_ndxe_ratio", {})
            breadth_ratio_pct = self._extract_percentile(ratio_payload.get("value"))
            top10_weight = self._metric_level(metrics, "get_qqq_top10_concentration", "top10_weight_pct")
            ad_line_trend = self._metric_text(metrics, "get_advance_decline_line", "trend", "direction")
            pct_above = self._metric_level(
                metrics,
                "get_percent_above_ma",
                "percent_50ma",
                "percent_above_50ma",
                "percent_above_50d",
                "percent_above_200ma",
                "percent_above_200d",
                "percent_200ma",
            )
            if (
                ad_line_trend in {"falling", "declining", "deteriorating"}
                or (breadth_ratio_pct is not None and breadth_ratio_pct >= 80)
                or (top10_weight is not None and top10_weight >= 50)
            ):
                return "deteriorating"
            if pct_above is not None and pct_above >= 60:
                return "healthy"
            if usable_count < 2:
                return "insufficient_data"
            return "neutral"

        if layer == "L4":
            pe = self._metric_level(metrics, "get_ndx_pe_and_earnings_yield", "pe_ttm", "weighted_forward_pe", "forward_pe")
            wind_payload = metrics.get("get_ndx_wind_valuation_snapshot", {})
            wind_value = wind_payload.get("value") if isinstance(wind_payload.get("value"), dict) else {}
            wind_pe_pct = self._extract_wind_ndx_valuation_percentile(wind_value)
            wind_pb_pct = _normalize_historical_percentile(
                _find_first_number(wind_value, ("PBHistoricalPercentile", "pb_historical_percentile"))
            )
            wind_ps_pct = _normalize_historical_percentile(
                _find_first_number(wind_value, ("PSHistoricalPercentile", "ps_historical_percentile"))
            )
            wind_risk_premium_pct = _normalize_historical_percentile(
                _find_first_number(
                    wind_value,
                    ("RiskPremiumHistoricalPercentile", "risk_premium_historical_percentile"),
                )
            )
            valuation_payload = metrics.get("get_ndx_pe_and_earnings_yield", {})
            pe_pct = self._extract_l4_valuation_percentile(
                valuation_payload.get("value"),
                payload=valuation_payload,
            )
            simple_gap = self._metric_level(metrics, "get_equity_risk_premium", "simple_yield_gap", "erp_value", "level")
            if wind_value:
                valuation_pressure = any(
                    pct is not None and pct >= 70
                    for pct in (wind_pe_pct, wind_pb_pct, wind_ps_pct)
                )
                compensation_thin = wind_risk_premium_pct is not None and wind_risk_premium_pct <= 30
                valuation_support = (
                    wind_pe_pct is not None
                    and wind_pe_pct <= 30
                    and (wind_risk_premium_pct is None or wind_risk_premium_pct >= 70)
                )
                if valuation_pressure or compensation_thin:
                    return "expensive"
                if valuation_support:
                    return "cheap"
            if (pe_pct is not None and pe_pct >= 70) or (simple_gap is not None and simple_gap <= 1.5):
                return "expensive"
            if (pe_pct is not None and pe_pct <= 30) or (simple_gap is not None and simple_gap >= 3.5):
                return "cheap"
            return "neutral"

        if layer == "L5":
            sma_position = self._metric_text(metrics, "get_qqq_technical_indicators", "sma_position")
            macd_status = self._metric_text(metrics, "get_macd_qqq", "status") or self._metric_text(
                metrics,
                "get_qqq_technical_indicators",
                "macd_status",
                "status",
            )
            adx = self._metric_level(metrics, "get_adx_qqq", "adx")
            if sma_position == "above_200":
                return "uptrend" if adx is None or adx < 25 or macd_status != "bullish" else "strong_uptrend"
            if sma_position == "below_200":
                return "downtrend"
            return "sideways"

        return "unknown"

    def _build_candidate_links(self, facts_by_layer: Dict[str, LayerFacts]) -> List[CandidateCrossLayerLink]:
        states = {layer: facts.state for layer, facts in facts_by_layer.items()}
        links: List[CandidateCrossLayerLink] = []

        def add(link_type: str, description: str, trigger_condition: str, relevant_metrics: List[str]) -> None:
            links.append(
                CandidateCrossLayerLink(
                    link_type=link_type,
                    description=description,
                    trigger_condition=trigger_condition,
                    relevant_metrics=relevant_metrics,
                )
            )

        if states.get("L1") == "restrictive" and states.get("L4") == "expensive":
            add(
                "L1_L4",
                "流动性收紧与高估值并存，估值压缩风险需要在桥接阶段被显式检验。",
                "l1_restrictive_and_l4_expensive",
                ["L1.get_fed_funds_rate", "L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield", "L4.get_equity_risk_premium"],
            )
        if states.get("L3") == "deteriorating" and states.get("L5") in {"uptrend", "strong_uptrend"}:
            add(
                "L3_L5",
                "广度走弱但价格趋势仍强，趋势质量与集中度风险需要被单独讨论。",
                "l3_deteriorating_but_l5_still_uptrend",
                ["L3.get_advance_decline_line", "L3.get_ndx_ndxe_ratio", "L5.get_qqq_technical_indicators", "L5.get_adx_qqq"],
            )
        if states.get("L2") == "risk_on" and states.get("L4") == "expensive":
            add(
                "L2_L4",
                "高风险偏好可能在推升高估值，需要检查情绪驱动而非基本面驱动的扩张。",
                "risk_appetite_supporting_multiple_expansion",
                ["L2.get_vix", "L2.get_cnn_fear_greed_index", "L4.get_ndx_pe_and_earnings_yield"],
            )
        if states.get("L1") == "restrictive" and states.get("L5") in {"uptrend", "strong_uptrend"}:
            add(
                "L1_L5",
                "环境偏紧但趋势仍强，需确认价格是否只是延迟反应。",
                "macro_constraint_vs_price_strength",
                ["L1.get_fed_funds_rate", "L1.get_net_liquidity_momentum", "L5.get_qqq_technical_indicators"],
            )
        if not links:
            add(
                "L1_L4",
                "默认检查流动性与估值之间的适配关系。",
                "default_macro_valuation_check",
                ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
            )
            add(
                "L3_L5",
                "默认检查广度对趋势的支撑质量。",
                "default_breadth_trend_check",
                ["L3.get_ndx_ndxe_ratio", "L5.get_qqq_technical_indicators"],
            )
        return links


def build_analysis_packet(
    data_json: Dict[str, Any],
    *,
    manual_overrides: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
) -> AnalysisPacket:
    builder = AnalysisPacketBuilder()
    packet = builder.build(
        data_json,
        manual_overrides=manual_overrides,
        context=context,
        output_path=output_path,
    )
    return packet
