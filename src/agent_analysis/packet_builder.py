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

logger = logging.getLogger(__name__)

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
        "get_hyg_momentum",
        "get_xly_xlp_ratio",
        "get_crowdedness_dashboard",
        "get_vxn_vix_ratio",
        "get_cnn_fear_greed_index",
    },
    "L3": {
        "get_advance_decline_line",
        "get_percent_above_ma",
        "get_qqq_qqew_ratio",
        "get_m7_fundamentals",
        "get_new_highs_lows",
        "get_mcclellan_oscillator_nasdaq_or_nyse",
    },
    "L4": {
        "get_ndx_pe_and_earnings_yield",
        "get_equity_risk_premium",
        "get_damodaran_us_implied_erp",
    },
    "L5": {
        "get_qqq_technical_indicators",
        "get_rsi_qqq",
        "get_atr_qqq",
        "get_adx_qqq",
        "get_macd_qqq",
        "get_obv_qqq",
        "get_volume_analysis_qqq",
        "get_donchian_channels_qqq",
        "get_multi_scale_ma_position",
    },
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


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
        output_path: Optional[str] = None,
    ) -> AnalysisPacket:
        manual_overrides = deepcopy(manual_overrides if manual_overrides is not None else load_manual_data())
        grouped_raw_data = self._group_raw_data(data_json, manual_overrides)
        facts_by_layer = {
            layer: self._build_layer_facts(layer, grouped_raw_data.get(layer, {}))
            for layer in LAYER_NAMES
        }
        candidate_links = self._build_candidate_links(facts_by_layer)
        packet = AnalysisPacket(
            meta=self._build_meta(data_json, manual_overrides, grouped_raw_data),
            raw_data=grouped_raw_data,
            facts_by_layer=facts_by_layer,
            candidate_cross_layer_links=candidate_links,
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
        successful_indicators = sum(1 for item in indicators if not item.get("error"))
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
            "collector_timestamp_utc": data_json.get("timestamp_utc"),
            "backtest_date": backtest_date,
            "indicator_total": total_indicators,
            "indicator_successful": successful_indicators,
            "manual_override_count": manual_count,
            "manual_override_active": bool(manual_overrides.get("active")),
        }

    def _build_context(
        self,
        data_json: Dict[str, Any],
        facts_by_layer: Dict[str, LayerFacts],
        extra_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        context = {
            "source_timestamp_utc": data_json.get("timestamp_utc"),
            "backtest_date": data_json.get("backtest_date"),
            "layer_states": {layer: facts.state for layer, facts in facts_by_layer.items()},
            "layer_summaries": {layer: facts.summary for layer, facts in facts_by_layer.items()},
        }
        if isinstance(extra_context, dict):
            context.update(extra_context)
        return context

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

            raw_payload = deepcopy(indicator.get("raw_data") if isinstance(indicator.get("raw_data"), dict) else {})
            raw_payload.setdefault("name", indicator.get("metric_name") or function_id)
            raw_payload["function_id"] = function_id
            raw_payload["metric_name"] = indicator.get("metric_name") or raw_payload.get("name") or function_id
            raw_payload["error"] = indicator.get("error")
            raw_payload["collection_timestamp_utc"] = indicator.get("collection_timestamp_utc")

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
        key_metrics = [signal["metric"] for signal in core_signals if not signal.get("error")][:5]
        summary_parts = [signal["summary"] for signal in core_signals if signal.get("summary") and not signal.get("error")][:3]
        if not summary_parts:
            summary_parts = ["关键指标不完整"]
        summary = f"{LAYER_NAMES[layer]}状态: {state}。关键事实: {'；'.join(summary_parts)}。"
        return LayerFacts(
            core_signals=core_signals[:8],
            state=state,
            key_metrics=key_metrics,
            summary=summary,
        )

    def _build_signal(self, function_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        value = payload.get("value")
        percentile = self._extract_percentile(value)
        trend = self._extract_trend(value)
        status = self._extract_status(value)
        compact_value = self._extract_signal_value(value)
        summary_bits = [payload.get("metric_name") or function_id]
        if compact_value is not None:
            summary_bits.append(f"值={compact_value}")
        if percentile is not None:
            summary_bits.append(f"分位={percentile}")
        if trend:
            summary_bits.append(f"趋势={trend}")
        if status:
            summary_bits.append(f"状态={status}")
        if payload.get("manual_override_used"):
            summary_bits.append("人工覆盖")
        if function_id == "get_ndx_pe_and_earnings_yield" and percentile is None and compact_value is not None:
            summary_bits.append("历史分位缺失")
        if payload.get("error"):
            summary_bits.append(f"异常={payload['error']}")
        return {
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

    def _extract_signal_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float)):
            return _round_if_float(value)
        if isinstance(value, dict):
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
        return _find_first_number(value, ("percentile_10y", "percentile_5y", "percentile_1y", "percentile"))

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
            fear_greed = self._metric_level(metrics, "get_cnn_fear_greed_index", "score")
            if (vix is not None and vix >= 25) or (hy_oas is not None and hy_oas >= 500) or (fear_greed is not None and fear_greed <= 30):
                return "risk_off"
            if (vix is not None and vix <= 15) or (fear_greed is not None and fear_greed >= 70):
                return "risk_on"
            return "neutral"

        if layer == "L3":
            breadth_ratio_pct = self._metric_level(metrics, "get_qqq_qqew_ratio", "percentile_10y", "percentile_1y", "percentile")
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
            if ad_line_trend in {"falling", "declining", "deteriorating"} or (breadth_ratio_pct is not None and breadth_ratio_pct >= 80):
                return "deteriorating"
            if pct_above is not None and pct_above >= 60:
                return "healthy"
            return "neutral"

        if layer == "L4":
            pe = self._metric_level(metrics, "get_ndx_pe_and_earnings_yield", "pe_ttm", "weighted_forward_pe", "forward_pe")
            pe_pct = self._metric_level(metrics, "get_ndx_pe_and_earnings_yield", "pe_ttm_percentile_5y", "percentile_5y", "percentile_10y")
            simple_gap = self._metric_level(metrics, "get_equity_risk_premium", "simple_yield_gap", "erp_value", "level")
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
                ["L3.get_advance_decline_line", "L3.get_qqq_qqew_ratio", "L5.get_qqq_technical_indicators", "L5.get_adx_qqq"],
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
                ["L3.get_qqq_qqew_ratio", "L5.get_qqq_technical_indicators"],
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
