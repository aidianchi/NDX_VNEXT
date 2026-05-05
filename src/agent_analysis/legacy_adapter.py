# -*- coding: utf-8 -*-
"""
NDX Agent vNext - Legacy Adapter

将 vNext 的结构化产物重新拼装成 legacy ReportGenerator 期望的 __LOGIC__ 结构。
这层兼容器不只是“把字段名对上”，还负责把 Layer / Bridge / Governance 的解释信息
重新组织成旧报告能消费的 indicator_narratives、layer_conclusions 和 regime 分析。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

LAYER_NAMES = {
    1: "第一层：宏观经济状况",
    2: "第二层：市场风险偏好",
    3: "第三层：指数内部健康度",
    4: "第四层：基本面估值",
    5: "第五层：价格趋势",
}

LAYER_TOPICS = {
    1: "宏观流动性、利率与增长定价",
    2: "情绪、信用与风险偏好",
    3: "广度、集中度与内部健康",
    4: "估值、盈利预期与风险补偿",
    5: "趋势强弱、超买超卖与技术触发",
}

FUNCTION_ALIASES = {
    "get_10y2y_spread_bp": ["treasury_spread_10y2y", "10y 2y treasury spread", "10y2y spread"],
    "get_fed_funds_rate": ["fed_funds_rate", "fed_rate", "fed funds rate", "federal funds"],
    "get_m2_yoy": ["m2_yoy", "m2 yoy", "m2"],
    "get_net_liquidity_momentum": ["net_liquidity", "net liquidity", "net liquidity momentum"],
    "get_copper_gold_ratio": ["copper_gold_ratio", "copper gold ratio"],
    "get_10y_treasury": ["10y_treasury", "10y treasury", "treasury yield"],
    "get_10y_real_rate": ["real_rate", "10y real rate"],
    "get_10y_breakeven": ["10y_breakeven", "10y breakeven", "breakeven inflation"],
    "get_vix": ["vix"],
    "get_vxn": ["vxn"],
    "get_hy_oas_bp": ["hy_oas", "high yield oas", "hy oas"],
    "get_ig_oas_bp": ["ig_oas", "investment grade oas", "ig oas"],
    "get_hyg_momentum": ["hyg", "high yield corp bond", "high yield corp"],
    "get_xly_xlp_ratio": ["xly_xlp_ratio", "xly xlp ratio"],
    "get_crowdedness_dashboard": ["crowdedness_skew", "crowdedness dashboard", "skew"],
    "get_vxn_vix_ratio": ["vxn_vix_ratio", "vxn vix ratio"],
    "get_cnn_fear_greed_index": ["cnn_fear_greed", "cnn fear greed", "fear greed"],
    "get_advance_decline_line": ["advance_decline_line", "advance decline line", "ad line"],
    "get_percent_above_ma": ["percent_above_ma", "stocks above ma", "above ma"],
    "get_qqq_qqew_ratio": ["qqq qqew ratio", "qqq_qqew_ratio"],
    "get_m7_fundamentals": ["m7 fundamentals", "m7"],
    "get_new_highs_lows": ["new highs lows", "new highs", "new lows"],
    "get_mcclellan_oscillator_nasdaq_or_nyse": ["mcclellan oscillator", "mcclellan"],
    "get_ndx_pe_and_earnings_yield": ["pe_ratio", "ndx valuation", "pe ttm", "earnings yield"],
    "get_equity_risk_premium": ["simple yield gap", "简式收益差距", "erp", "equity risk premium"],
    "get_qqq_technical_indicators": ["price_vs_sma_200", "qqq technical indicators", "technical indicators"],
    "get_rsi_qqq": ["rsi", "qqq rsi"],
    "get_atr_qqq": ["atr", "qqq atr"],
    "get_adx_qqq": ["adx", "qqq adx"],
    "get_macd_qqq": ["macd", "qqq macd"],
    "get_obv_qqq": ["obv", "on balance volume"],
    "get_volume_analysis_qqq": ["obv", "volume analysis", "qqq volume analysis"],
    "get_price_volume_quality_qqq": ["vwap", "mfi", "cmf", "price volume quality", "量价质量"],
    "get_donchian_channels_qqq": ["donchian_channel", "donchian channels"],
    "get_multi_scale_ma_position": ["price_vs_sma_200", "multi scale ma position", "moving average position"],
}

TREND_LABELS = {
    "rising": "上行",
    "falling": "下行",
    "stable": "平稳",
    "volatile": "波动较大",
    "above": "位于均线上方",
    "below": "位于均线下方",
    "above_200": "位于 200 日均线上方",
    "below_200": "位于 200 日均线下方",
    "greed": "偏贪婪",
    "fear": "偏恐慌",
    "bullish": "偏多",
    "bearish": "偏空",
    "near_upper": "靠近上轨",
    "near_lower": "靠近下轨",
    "short_above_long": "短周期强于长周期",
    "short_below_long": "短周期弱于长周期",
}

STATUS_LABELS = {
    "greed": "贪婪",
    "fear": "恐慌",
    "bullish": "看多",
    "bearish": "看空",
    "overbought": "超买",
    "oversold": "超卖",
    "near_upper": "接近上轨",
    "near_lower": "接近下轨",
    "high": "偏高",
    "low": "偏低",
}

LAYER_RISK_KEYWORDS = {
    1: ("利率", "流动性", "估值", "降息", "增长", "通胀"),
    2: ("情绪", "恐贪", "信用", "风险偏好", "拥挤", "波动"),
    3: ("集中度", "广度", "背离", "内部健康", "七巨头"),
    4: ("估值", "erp", "风险补偿", "盈利", "压缩"),
    5: ("趋势", "回调", "超买", "闪崩", "技术"),
}


def _to_dict(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    return default


def _normalize(text: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", str(text or "").lower()).strip()


def _tokens(text: Any) -> List[str]:
    return [token for token in _normalize(text).split() if token]


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _layer_number(layer_value: Any) -> int:
    value = _enum_value(layer_value)
    if isinstance(value, str) and value.upper().startswith("L"):
        return int(value[1:])
    return int(value)


def _coerce_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw.startswith("{") and not raw.startswith("["):
        return value
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return value


def _round(value: float) -> float:
    return round(value, 2)


def _format_number(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.2f}".rstrip("0").rstrip(".")
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _compact_value(value: Any, *, max_items: int = 4) -> str:
    value = _coerce_jsonish(value)
    if value is None:
        return "N/A"
    if isinstance(value, (str, int, float, bool)):
        return _format_number(value)
    if isinstance(value, dict):
        parts: List[str] = []
        for key, item in value.items():
            if len(parts) >= max_items:
                break
            item = _coerce_jsonish(item)
            if isinstance(item, dict):
                nested = _compact_value(item, max_items=2)
                if nested and nested != "N/A":
                    parts.append(f"{key}={nested}")
            elif isinstance(item, list):
                if item:
                    parts.append(f"{key}={_compact_value(item[:2], max_items=2)}")
            elif item is not None:
                parts.append(f"{key}={_format_number(item)}")
        return ", ".join(parts) if parts else str(value)
    if isinstance(value, list):
        rendered = [_compact_value(item, max_items=2) for item in value[:max_items]]
        return "; ".join(item for item in rendered if item and item != "N/A") or "N/A"
    return str(value)


def _find_first_number(data: Any, keywords: Iterable[str] = ()) -> Optional[float]:
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    if isinstance(data, (int, float)) and not isinstance(data, bool):
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


def _raw_indicator_value(indicator: Dict[str, Any]) -> Any:
    raw = indicator.get("raw_data") or {}
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value")
    return raw


def _extract_percentile(indicator: Dict[str, Any], fact: Optional[Dict[str, Any]]) -> Optional[float]:
    if fact and fact.get("historical_percentile") is not None:
        return float(fact["historical_percentile"])
    raw = _raw_indicator_value(indicator)
    percentile = _find_first_number(
        raw,
        (
            "percentile_10y",
            "percentile_5y",
            "percentile_1y",
            "erp_percentile_5y",
            "pe_ttm_percentile_5y",
            "percentile",
        ),
    )
    if percentile is None:
        return None
    if 0 <= percentile <= 1:
        return percentile * 100
    return percentile


def _extract_trend(indicator: Dict[str, Any], fact: Optional[Dict[str, Any]]) -> str:
    raw = _raw_indicator_value(indicator)
    trend = ""
    if fact and fact.get("trend"):
        trend = str(fact["trend"])
    if not trend:
        trend = _find_first_string(
            raw,
            (
                "trend",
                "direction",
                "sma_position",
                "position_vs_ma",
                "ratio_trend_vs_ma20",
                "obv_trend",
                "volume_price_relationship",
                "donchian_signal",
                "macd_status",
            ),
        ) or ""
    return TREND_LABELS.get(trend.lower(), trend)


def _extract_status(indicator: Dict[str, Any], fact: Optional[Dict[str, Any]]) -> str:
    raw = _raw_indicator_value(indicator)
    status = _find_first_string(
        raw,
        (
            "status",
            "rating",
            "signal",
            "cross_signal",
            "rsi_status",
            "volume_status",
            "bb_compression_status",
        ),
    ) or ""
    if not status and fact and fact.get("magnitude"):
        status = str(fact["magnitude"])
    return STATUS_LABELS.get(status.lower(), status)


def _extract_value_text(indicator: Dict[str, Any], fact: Optional[Dict[str, Any]]) -> str:
    if fact and fact.get("value") is not None:
        return _compact_value(fact["value"])
    return _compact_value(_raw_indicator_value(indicator))


def _score_alias_match(text: str, aliases: Sequence[str]) -> int:
    normalized_text = _normalize(text)
    text_tokens = set(_tokens(text))
    best = 0
    for alias in aliases:
        normalized_alias = _normalize(alias)
        if not normalized_alias:
            continue
        score = 0
        if normalized_text == normalized_alias:
            score += 20
        if normalized_alias and normalized_alias in normalized_text:
            score += 10
        alias_tokens = set(_tokens(alias))
        if alias_tokens and text_tokens:
            score += len(alias_tokens & text_tokens) * 3
        best = max(best, score)
    return best


def _match_core_fact(indicator: Dict[str, Any], facts: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    function_id = str(indicator.get("function_id") or "")
    metric_name = str(indicator.get("metric_name") or "")
    aliases = [metric_name, function_id, *(FUNCTION_ALIASES.get(function_id, []))]
    best_fact: Optional[Dict[str, Any]] = None
    best_score = 0
    for fact in facts:
        candidates = [str(fact.get("metric") or "")]
        raw_data = fact.get("raw_data") or {}
        if isinstance(raw_data, dict):
            candidates.extend(
                [
                    str(raw_data.get("metric_name") or ""),
                    str(raw_data.get("name") or ""),
                    str(raw_data.get("function_id") or ""),
                ]
            )
        score = max(_score_alias_match(candidate, aliases) for candidate in candidates if candidate)
        if score > best_score:
            best_score = score
            best_fact = fact
    return best_fact if best_score > 0 else None


def _select_bridge_context(
    layer_label: str,
    indicator: Dict[str, Any],
    bridge_memos: Sequence[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    function_id = str(indicator.get("function_id") or "")
    aliases = [_normalize(indicator.get("metric_name") or ""), _normalize(function_id)]
    aliases.extend(_normalize(alias) for alias in FUNCTION_ALIASES.get(function_id, []))

    best_memo: Optional[Dict[str, Any]] = None
    best_claim: Optional[Dict[str, Any]] = None
    best_conflict: Optional[Dict[str, Any]] = None

    for memo in bridge_memos:
        connected_layers = {_normalize(layer) for layer in memo.get("layers_connected") or []}
        if _normalize(layer_label) not in connected_layers:
            continue
        if best_memo is None:
            best_memo = memo

        for claim in memo.get("cross_layer_claims") or []:
            refs = " ".join(str(item) for item in claim.get("supporting_facts") or [])
            refs_normalized = _normalize(refs)
            if any(alias and alias in refs_normalized for alias in aliases):
                best_claim = claim
                break
        if best_claim is None and memo.get("cross_layer_claims"):
            best_claim = memo["cross_layer_claims"][0]

        for conflict in memo.get("conflicts") or []:
            involved_layers = {_normalize(layer) for layer in conflict.get("involved_layers") or []}
            haystack = _normalize(conflict.get("conflict_type")) + " " + _normalize(conflict.get("description"))
            if _normalize(layer_label) in involved_layers or any(alias and alias in haystack for alias in aliases):
                best_conflict = conflict
                break
        if best_conflict is None and memo.get("conflicts"):
            best_conflict = memo["conflicts"][0]
    return best_memo, best_claim, best_conflict


def _select_layer_assessment(layer_num: int, thesis: Dict[str, Any]) -> str:
    if not thesis:
        return ""
    if layer_num in {1, 2, 3}:
        return str(thesis.get("environment_assessment") or "")
    if layer_num == 4:
        return str(thesis.get("valuation_assessment") or "")
    return str(thesis.get("timing_assessment") or "")


def _select_related_risk(layer_num: int, indicator: Dict[str, Any], risk_texts: Sequence[str]) -> str:
    if not risk_texts:
        return ""
    metric_tokens = set(_tokens(indicator.get("metric_name") or ""))
    metric_tokens.update(_tokens(indicator.get("function_id") or ""))
    metric_tokens.update(_tokens(" ".join(LAYER_RISK_KEYWORDS.get(layer_num, ()))))
    best_text = ""
    best_score = -1
    for text in risk_texts:
        score = len(metric_tokens & set(_tokens(text)))
        if score > best_score:
            best_score = score
            best_text = text
    return best_text


def _select_primary_conflict_id(
    bridge_memos: Sequence[Dict[str, Any]],
    risk_report: Dict[str, Any],
    revised: Dict[str, Any],
) -> str:
    matrix = risk_report.get("conflict_matrix_check") or {}
    for key, active in matrix.items():
        if active:
            return str(key).split("_", 1)[0]
    conflicts = revised.get("remaining_conflicts") or []
    if conflicts:
        return str(conflicts[0].get("conflict_type") or "N/A")
    for memo in bridge_memos:
        memo_conflicts = memo.get("conflicts") or []
        if memo_conflicts:
            return str(memo_conflicts[0].get("conflict_type") or "N/A")
    return "N/A"


def _build_key_drivers(
    layer_num: int,
    indicators_by_layer: Dict[int, List[Dict[str, Any]]],
    facts_by_layer: Dict[int, List[Dict[str, Any]]],
) -> List[str]:
    drivers: List[str] = []
    for indicator in indicators_by_layer.get(layer_num, []):
        fact = _match_core_fact(indicator, facts_by_layer.get(layer_num, []))
        display_name = str(indicator.get("metric_name") or indicator.get("function_id") or "Unknown")
        value_text = _extract_value_text(indicator, fact)
        percentile = _extract_percentile(indicator, fact)
        trend = _extract_trend(indicator, fact)
        parts = [f"{display_name}: {value_text}"]
        if percentile is not None:
            parts.append(f"{_round(percentile)}% 分位")
        if trend:
            parts.append(trend)
        drivers.append(" | ".join(parts))
        if len(drivers) >= 4:
            break

    if drivers:
        return drivers

    for fact in facts_by_layer.get(layer_num, [])[:4]:
        drivers.append(f"{fact.get('metric')}: {fact.get('value')}")
    return drivers


def _build_indicator_narrative(
    *,
    layer_num: int,
    indicator: Dict[str, Any],
    fact: Optional[Dict[str, Any]],
    card: Dict[str, Any],
    claim: Optional[Dict[str, Any]],
    conflict: Optional[Dict[str, Any]],
    thesis: Dict[str, Any],
) -> str:
    display_name = str(indicator.get("metric_name") or indicator.get("function_id") or "Unknown")
    value_text = _extract_value_text(indicator, fact)
    percentile = _extract_percentile(indicator, fact)
    trend = _extract_trend(indicator, fact)
    status = _extract_status(indicator, fact)
    interpretation_bits = [str(card.get("local_conclusion") or "").strip()]
    layer_assessment = _select_layer_assessment(layer_num, thesis)
    if layer_assessment:
        interpretation_bits.append(layer_assessment.strip())
    if claim and claim.get("mechanism"):
        interpretation_bits.append(str(claim["mechanism"]).strip())
    if conflict and conflict.get("description"):
        interpretation_bits.append(str(conflict["description"]).strip())

    parts = [f"水平：{display_name}当前为 {value_text}。"]
    if trend or status:
        trend_status = "；".join(item for item in [trend, status] if item)
        parts.append(f"趋势/状态：{trend_status}。")
    if percentile is not None:
        parts.append(f"相对性：处于历史 {_round(percentile)}% 分位。")
    interpretation_text = " ".join(bit for bit in interpretation_bits if bit)
    if interpretation_text:
        parts.append(f"典范化解读：{interpretation_text}")
    return " ".join(parts)


def _build_reasoning_process(
    *,
    layer_num: int,
    layer_label: str,
    indicator: Dict[str, Any],
    fact: Optional[Dict[str, Any]],
    card: Dict[str, Any],
    claim: Optional[Dict[str, Any]],
    conflict: Optional[Dict[str, Any]],
    thesis: Dict[str, Any],
    risk_text: str,
) -> str:
    display_name = str(indicator.get("metric_name") or indicator.get("function_id") or "Unknown")
    value_text = _extract_value_text(indicator, fact)
    percentile = _extract_percentile(indicator, fact)
    trend = _extract_trend(indicator, fact)
    status = _extract_status(indicator, fact)
    notes = str(card.get("notes") or "").strip()
    hooks = card.get("cross_layer_hooks") or []
    hook_question = ""
    if hooks:
        hook_question = str(hooks[0].get("question") or "").strip()
    layer_assessment = _select_layer_assessment(layer_num, thesis)

    sentences = [f"我先看 {display_name}，当前读数为 {value_text}。"]
    if percentile is not None or trend or status:
        qualifiers = []
        if percentile is not None:
            qualifiers.append(f"它位于历史 {_round(percentile)}% 分位")
        if trend:
            qualifiers.append(f"当前呈现 {trend}")
        if status:
            qualifiers.append(f"并处于 {status}")
        sentences.append("、".join(qualifiers) + "。")
    sentences.append(
        f"放在 {layer_label} 里，这条指标主要用来判断 {LAYER_TOPICS[layer_num]}；"
        f"结合本层结论，{str(card.get('local_conclusion') or '').strip()}"
    )
    if layer_assessment:
        sentences.append(f"继续往总论点上推，它对应的上层判断是：{layer_assessment}")
    if notes:
        sentences.append(notes)
    if hook_question:
        sentences.append(f"它还引出了一个必须跨层验证的问题：{hook_question}")
    if conflict and conflict.get("description"):
        implication = str(conflict.get("implication") or "").strip()
        conflict_text = str(conflict["description"]).strip()
        if implication:
            conflict_text = f"{conflict_text}；其含义是 {implication}"
        sentences.append(f"桥接层把这条线索延伸成了核心冲突：{conflict_text}")
    elif claim and claim.get("claim"):
        mechanism = str(claim.get("mechanism") or "").strip()
        claim_text = str(claim["claim"]).strip()
        if mechanism:
            claim_text = f"{claim_text}；传导机制是 {mechanism}"
        sentences.append(f"桥接层给出的跨层支撑关系是：{claim_text}")
    if risk_text:
        sentences.append(f"最终在治理层，这条指标落到的风险边界是：{risk_text}")
    return " ".join(sentence.strip() for sentence in sentences if sentence).strip()


def _fallback_indicator_items(
    layer_num: int,
    facts: Sequence[Dict[str, Any]],
    card: Dict[str, Any],
    thesis: Dict[str, Any],
    bridge_memos: Sequence[Dict[str, Any]],
    risk_texts: Sequence[str],
) -> List[Dict[str, str]]:
    layer_label = f"L{layer_num}"
    items: List[Dict[str, str]] = []
    for fact in facts:
        indicator = {
            "metric_name": fact.get("metric"),
            "function_id": fact.get("metric"),
            "raw_data": {"value": fact.get("raw_data") or fact.get("value")},
        }
        _, claim, conflict = _select_bridge_context(layer_label, indicator, bridge_memos)
        risk_text = _select_related_risk(layer_num, indicator, risk_texts)
        items.append(
            {
                "metric": str(fact.get("metric") or "Unknown"),
                "narrative": _build_indicator_narrative(
                    layer_num=layer_num,
                    indicator=indicator,
                    fact=fact,
                    card=card,
                    claim=claim,
                    conflict=conflict,
                    thesis=thesis,
                ),
                "reasoning_process": _build_reasoning_process(
                    layer_num=layer_num,
                    layer_label=layer_label,
                    indicator=indicator,
                    fact=fact,
                    card=card,
                    claim=claim,
                    conflict=conflict,
                    thesis=thesis,
                    risk_text=risk_text,
                ),
            }
        )
    return items


def _match_native_indicator_analysis(
    indicator: Dict[str, Any],
    native_analyses: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    function_id = str(indicator.get("function_id") or "")
    metric_name = str(indicator.get("metric_name") or "")
    aliases = [
        _normalize(function_id),
        _normalize(metric_name),
        *(_normalize(alias) for alias in FUNCTION_ALIASES.get(function_id, [])),
    ]
    aliases = [alias for alias in aliases if alias]

    best_analysis: Optional[Dict[str, Any]] = None
    best_score = 0
    for analysis in native_analyses:
        candidates = [
            str(analysis.get("function_id") or ""),
            str(analysis.get("metric") or ""),
            str(analysis.get("metric_name") or ""),
        ]
        score = max((_score_alias_match(candidate, aliases) for candidate in candidates if candidate), default=0)
        if score > best_score:
            best_score = score
            best_analysis = analysis
    return best_analysis if best_score > 0 else None


def _native_indicator_item(
    analysis: Dict[str, Any],
    *,
    indicator: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    metric = str(
        (indicator or {}).get("metric_name")
        or analysis.get("metric")
        or analysis.get("function_id")
        or "Unknown"
    )
    narrative = str(
        analysis.get("narrative")
        or analysis.get("output_narrative")
        or analysis.get("current_reading")
        or ""
    ).strip()
    reasoning = str(
        analysis.get("reasoning_process")
        or analysis.get("reasoning")
        or analysis.get("rationale")
        or ""
    ).strip()
    first_principles = analysis.get("first_principles_chain") or []
    cross_layer_implications = analysis.get("cross_layer_implications") or []
    if first_principles and isinstance(first_principles, list):
        reasoning = (reasoning + " " if reasoning else "") + "因果链：" + " -> ".join(str(item) for item in first_principles)
    if cross_layer_implications and isinstance(cross_layer_implications, list):
        reasoning = (reasoning + " " if reasoning else "") + "跨层含义：" + "；".join(str(item) for item in cross_layer_implications)
    return {
        "metric": metric,
        "narrative": narrative,
        "reasoning_process": reasoning or narrative,
    }


def adapt_vnext_to_legacy(
    final_adj: Any,
    revised: Any,
    layer_cards: Sequence[Any],
    bridge_memos: Sequence[Any],
    data_integrity_report: Dict[str, Any],
    *,
    data_json: Optional[Dict[str, Any]] = None,
    analysis_packet: Optional[Any] = None,
    context_brief: Optional[Any] = None,
    thesis_draft: Optional[Any] = None,
    critique: Optional[Any] = None,
    risk_boundary_report: Optional[Any] = None,
) -> Dict[str, Any]:
    """Translate vNext artifacts into legacy __LOGIC__ format.

    Optional inputs let the adapter rebuild a richer legacy contract:
    - `data_json` allows narrative coverage to match the full report indicator set.
    - `analysis_packet` / `context_brief` / `thesis_draft` / `critique` / `risk_boundary_report`
      provide additional explanation density for regime and revision sections.
    """

    final_data = _to_dict(final_adj) or {}
    revised_data = _to_dict(revised) or {}
    thesis_data = _to_dict(thesis_draft) or (_to_dict(_get(revised, "revised_thesis")) or {})
    critique_data = _to_dict(critique) or {}
    risk_report = _to_dict(risk_boundary_report) or {}
    packet_data = _to_dict(analysis_packet) or {}
    context_data = _to_dict(context_brief) or {}
    bridge_data = [_to_dict(memo) or {} for memo in bridge_memos]
    card_data = [_to_dict(card) or {} for card in layer_cards]

    cards_by_layer: Dict[int, Dict[str, Any]] = {}
    facts_by_layer: Dict[int, List[Dict[str, Any]]] = {}
    for card in card_data:
        layer_num = _layer_number(card.get("layer"))
        cards_by_layer[layer_num] = card
        facts_by_layer[layer_num] = list(card.get("core_facts") or [])

    indicators_by_layer: Dict[int, List[Dict[str, Any]]] = {index: [] for index in range(1, 6)}
    if isinstance(data_json, dict):
        for indicator in data_json.get("indicators", []):
            layer_raw = indicator.get("layer")
            if isinstance(layer_raw, str) and layer_raw.upper().startswith("L"):
                layer_num = int(layer_raw[1:])
            else:
                layer_num = int(layer_raw or 0)
            if layer_num in indicators_by_layer:
                indicators_by_layer[layer_num].append(indicator)

    risk_texts: List[str] = []
    risk_texts.extend(list(final_data.get("must_preserve_risks") or []))
    risk_texts.extend(list(risk_report.get("must_preserve_risks") or []))

    indicator_narratives: Dict[str, List[Dict[str, str]]] = {}
    layer_conclusions: List[Dict[str, Any]] = []

    for layer_num in range(1, 6):
        card = cards_by_layer.get(layer_num, {})
        layer_label = f"L{layer_num}"
        layer_items: List[Dict[str, str]] = []
        native_analyses = list(card.get("indicator_analyses") or [])

        if indicators_by_layer.get(layer_num):
            for indicator in indicators_by_layer[layer_num]:
                native_analysis = _match_native_indicator_analysis(indicator, native_analyses)
                if native_analysis:
                    layer_items.append(_native_indicator_item(native_analysis, indicator=indicator))
                else:
                    fact = _match_core_fact(indicator, facts_by_layer.get(layer_num, []))
                    _, claim, conflict = _select_bridge_context(layer_label, indicator, bridge_data)
                    risk_text = _select_related_risk(layer_num, indicator, risk_texts)
                    layer_items.append(
                        {
                            "metric": str(indicator.get("metric_name") or indicator.get("function_id") or "Unknown"),
                            "narrative": _build_indicator_narrative(
                                layer_num=layer_num,
                                indicator=indicator,
                                fact=fact,
                                card=card,
                                claim=claim,
                                conflict=conflict,
                                thesis=thesis_data,
                            ),
                            "reasoning_process": _build_reasoning_process(
                                layer_num=layer_num,
                                layer_label=layer_label,
                                indicator=indicator,
                                fact=fact,
                                card=card,
                                claim=claim,
                                conflict=conflict,
                                thesis=thesis_data,
                                risk_text=risk_text,
                            ),
                        }
                    )
        elif native_analyses:
            layer_items = [_native_indicator_item(analysis) for analysis in native_analyses]
        else:
            layer_items = _fallback_indicator_items(
                layer_num,
                facts_by_layer.get(layer_num, []),
                card,
                thesis_data,
                bridge_data,
                risk_texts,
            )

        indicator_narratives[f"layer_{layer_num}"] = layer_items

        related_conflicts = []
        related_claims = []
        for memo in bridge_data:
            connected = {_normalize(layer) for layer in memo.get("layers_connected") or []}
            if _normalize(layer_label) in connected:
                related_conflicts.extend(memo.get("conflicts") or [])
                related_claims.extend(memo.get("cross_layer_claims") or [])

        conflict_parts: List[str] = []
        if card.get("risk_flags"):
            conflict_parts.append("风险标记：" + "、".join(str(item) for item in card.get("risk_flags") or []))
        if related_conflicts:
            conflict_parts.append(
                "跨层冲突：" + "；".join(str(item.get("description") or "") for item in related_conflicts[:2] if item.get("description"))
            )
        if card.get("cross_layer_hooks"):
            hook_text = "；".join(
                str(hook.get("question") or "") for hook in (card.get("cross_layer_hooks") or [])[:2] if hook.get("question")
            )
            if hook_text:
                conflict_parts.append("待验证问题：" + hook_text)
        if card.get("notes"):
            conflict_parts.append(str(card.get("notes")))
        if card.get("internal_conflict_analysis"):
            conflict_parts.append(str(card.get("internal_conflict_analysis")))

        layer_conclusions.append(
            {
                "layer": LAYER_NAMES[layer_num],
                "judgement": str(
                    card.get("layer_synthesis")
                    or card.get("local_conclusion")
                    or _select_layer_assessment(layer_num, thesis_data)
                    or "无"
                ),
                "internal_conflict_analysis": "；".join(part for part in conflict_parts if part) or "无明显内部冲突。",
                "key_drivers": _build_key_drivers(layer_num, indicators_by_layer, facts_by_layer),
            }
        )

    remaining_conflicts = revised_data.get("remaining_conflicts") or []
    if not remaining_conflicts:
        remaining_conflicts = [conflict for memo in bridge_data for conflict in (memo.get("conflicts") or [])]

    conflict_rationale_parts: List[str] = []
    for conflict in remaining_conflicts[:3]:
        description = str(conflict.get("description") or "").strip()
        implication = str(conflict.get("implication") or "").strip()
        if description and implication:
            conflict_rationale_parts.append(f"{description} 含义是：{implication}")
        elif description:
            conflict_rationale_parts.append(description)

    main_thesis = str(thesis_data.get("main_thesis") or final_data.get("final_stance") or "")
    environment = str(thesis_data.get("environment_assessment") or "")
    valuation = str(thesis_data.get("valuation_assessment") or "")
    timing = str(thesis_data.get("timing_assessment") or "")
    bridge_implication = "；".join(
        str(memo.get("implication_for_ndx") or "").strip() for memo in bridge_data[:2] if memo.get("implication_for_ndx")
    )
    uncertainties = [str(item) for memo in bridge_data for item in (memo.get("key_uncertainties") or [])]
    dependencies = [str(item) for item in thesis_data.get("dependencies") or []]

    masters_sections = []
    if final_data.get("adjudicator_notes"):
        masters_sections.append(f"最终裁决：{final_data['adjudicator_notes']}")
    if main_thesis:
        masters_sections.append(f"主论点：{main_thesis}")
    if critique_data.get("overall_assessment"):
        masters_sections.append(f"治理层审查：{critique_data['overall_assessment']}")
    if dependencies:
        masters_sections.append("成立前提：" + "；".join(dependencies[:4]))
    if remaining_conflicts:
        masters_sections.append(
            "保留冲突：" + "；".join(str(item.get("description") or "") for item in remaining_conflicts[:3] if item.get("description"))
        )

    market_regime_analysis = {
        "identified_regime": main_thesis or str(final_data.get("final_stance") or ""),
        "regime_rationale": " ".join(
            item for item in [environment, valuation, timing, bridge_implication] if item
        ) or str(final_data.get("adjudicator_notes") or ""),
        "identified_conflict_scenario_ID": _select_primary_conflict_id(bridge_data, risk_report, revised_data),
        "conflict_rationale": "；".join(conflict_rationale_parts) or "暂无显式冲突说明。",
        "risk_flags": risk_texts or list(card_data[0].get("risk_flags") or []) if card_data else [],
        "masters_perspective": "\n".join(section for section in masters_sections if section),
        "institutional_dynamics": "；".join(
            item for item in [bridge_implication, "关键不确定性：" + "；".join(uncertainties[:3]) if uncertainties else ""] if item
        ),
    }

    revision_summary: Dict[str, Any] = {}
    if revised_data.get("revision_summary"):
        revision_summary["overall_revision"] = revised_data["revision_summary"]
    for index, critique_item in enumerate(revised_data.get("accepted_critiques") or [], 1):
        revision_summary[f"response_to_critique_{index}"] = f"【采纳】{critique_item}"
    for index, item in enumerate(revised_data.get("rejected_critiques") or [], 1):
        reason = item.get("reason", "") if isinstance(item, dict) else ""
        criticism = item.get("criticism", "") if isinstance(item, dict) else ""
        revision_summary[f"response_to_critique_rejected_{index}"] = f"【驳回】{criticism} {reason}".strip()
    if main_thesis:
        revision_summary["revised_main_thesis"] = main_thesis
    if final_data.get("approval_status"):
        revision_summary["final_adjudication"] = (
            f"{_enum_value(final_data['approval_status'])}: {final_data.get('adjudicator_notes', '')}".strip()
        )
    if context_data.get("special_attention"):
        revision_summary["special_attention"] = "；".join(str(item) for item in context_data["special_attention"][:3])

    logic_json = {
        "__LOGIC__": {
            "market_regime_analysis": market_regime_analysis,
            "layer_conclusions": layer_conclusions,
            "indicator_narratives": indicator_narratives,
            "data_integrity_report": data_integrity_report,
            "revision_summary": revision_summary,
            "vnext_native_artifacts": {
                "adapter_policy": {
                    "legacy_adapter_role": "compatibility_mapping_only",
                    "primary_reasoning_source": "vnext_artifacts",
                    "native_ui_is_quality_baseline": True,
                },
                "typed_conflicts": [
                    conflict
                    for memo in bridge_data
                    for conflict in (memo.get("typed_conflicts") or [])
                ],
                "resonance_chains": [
                    chain
                    for memo in bridge_data
                    for chain in (memo.get("resonance_chains") or [])
                ],
                "transmission_paths": [
                    path
                    for memo in bridge_data
                    for path in (memo.get("transmission_paths") or [])
                ],
            },
        }
    }
    return logic_json
