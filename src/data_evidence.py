from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

try:
    from .data_availability import has_meaningful_observation_value, no_data_reason
except ImportError:
    from data_availability import has_meaningful_observation_value, no_data_reason


DATA_EVIDENCE_CONTRACT_VERSION = "data_evidence_v1"
EVIDENCE_PASSPORT_CONTRACT_VERSION = "evidence_passport_v1"

REQUIRED_DATA_QUALITY_FIELDS = {
    "provider",
    "source_name",
    "source_url",
    "source_tier",
    "as_of_date",
    "effective_date",
    "data_date",
    "vintage_date",
    "collected_at_utc",
    "availability",
    "fallback_reason",
    "fallback_chain",
    "license_note",
    "coverage",
    "methodology",
    "formula",
    "anomalies",
}

CORE_EVIDENCE_FUNCTIONS = {
    "get_10y2y_spread_bp",
    "get_fed_funds_rate",
    "get_fed_funds_rate_path",
    "get_m2_yoy",
    "get_net_liquidity_momentum",
    "get_copper_gold_ratio",
    "get_10y_treasury",
    "get_10y_real_rate",
    "get_10y_breakeven",
    "get_vix",
    "get_vxn",
    "get_hy_oas_bp",
    "get_ig_oas_bp",
    "get_hy_quality_spread_bp",
    "get_hyg_momentum",
    "get_xly_xlp_ratio",
    "get_vxn_vix_ratio",
    "get_vix_term_structure",
    "get_cnn_fear_greed_index",
    "get_advance_decline_line",
    "get_percent_above_ma",
    "get_ndx_ndxe_ratio",
    "get_qqq_qqew_ratio",
    "get_qqq_top10_concentration",
    "get_m7_fundamentals",
    "get_new_highs_lows",
    "get_mcclellan_oscillator_nasdaq_or_nyse",
    "get_ndx_wind_valuation_snapshot",
    "get_ndx_wind_point_in_time_earnings_expectations",
    "get_ndx_pe_and_earnings_yield",
    "get_ndx_forward_earnings_quality",
    "get_equity_risk_premium",
    "get_m7_capex_cycle",
    "get_m7_earnings_blackout_calendar",
    "get_m7_buyback_flow",
    "get_damodaran_us_implied_erp",
    "get_l5_deterministic_snapshot",
    "get_qqq_technical_indicators",
}

LATEST_ONLY_FUNCTIONS = {
    "get_m7_fundamentals",
    "get_qqq_top10_concentration",
    "get_ndx_wind_valuation_snapshot",
    "get_ndx_pe_and_earnings_yield",
    "get_ndx_forward_earnings_quality",
    "get_equity_risk_premium",
}

PROXY_SOURCE_TOKENS = {"proxy", "component_model", "market_data_provider", "third_party_estimate"}
OFFICIAL_SOURCE_TOKENS = {"official", "official_provider", "licensed_manual/wind", "licensed_provider/wind"}


def _supporting_authority(reason: str, *, usage: str = "supporting_only", requires: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "usage": usage,
        "authority": "proxy_or_derived_observation",
        "reason": reason,
        "requires_confirmation": list(requires or []),
    }


_AUTHORITY_USAGE_RANK = {
    "rejected": 0,
    "audit_only": 1,
    "supporting_only": 2,
    "core_allowed": 3,
}


def _merge_authority_rule_min_privilege(policy_rule: Dict[str, Any], producer_rule: Any) -> Dict[str, Any]:
    """Retain producer detail while preventing old payloads from raising evidence authority."""
    existing = producer_rule if isinstance(producer_rule, dict) else {}
    merged = {**existing, **deepcopy(policy_rule)}
    policy_usage = str(policy_rule.get("usage") or "audit_only").strip().lower()
    producer_usage = str(existing.get("usage") or policy_usage).strip().lower()
    if policy_usage not in _AUTHORITY_USAGE_RANK:
        policy_usage = "audit_only"
    if producer_usage not in _AUTHORITY_USAGE_RANK:
        producer_usage = "audit_only"
    merged["usage"] = min(
        (policy_usage, producer_usage),
        key=lambda usage: _AUTHORITY_USAGE_RANK.get(usage, _AUTHORITY_USAGE_RANK["audit_only"]),
    )
    merged["requires_confirmation"] = list(dict.fromkeys(
        _as_list(policy_rule.get("requires_confirmation"))
        + _as_list(existing.get("requires_confirmation"))
    ))
    return merged


# These series are useful observations, but none is an official valuation,
# fundamental, or executable trading conclusion.  Keeping the policy beside
# the evidence normalizer guarantees that success, fallback, and unavailable
# producer branches all receive the same field-level authority contract.
WEAK_METRIC_AUTHORITY_POLICIES: Dict[str, Dict[str, Any]] = {
    "get_vix": {
        "metric_authority": {
            "level": _supporting_authority("Options-implied insurance price; high is not a buy signal and low is not proof of safety.", requires=["get_hy_oas_bp", "get_advance_decline_line"]),
            "historical_stats": _supporting_authority("Third-party historical relativity only; it cannot establish valuation or a trade threshold."),
        },
        "downgrade_rules": ["volatility_level_requires_credit_and_breadth_confirmation", "volatility_cannot_prove_valuation_or_trade_action"],
    },
    "get_vxn": {
        "metric_authority": {
            "level": _supporting_authority("Nasdaq options-implied insurance price; it measures stress pricing, not fundamental value.", requires=["get_hy_oas_bp", "get_percent_above_ma"]),
            "historical_stats": _supporting_authority("Third-party historical relativity only; it cannot establish valuation or a trade threshold."),
        },
        "downgrade_rules": ["volatility_level_requires_credit_and_breadth_confirmation", "volatility_cannot_prove_valuation_or_trade_action"],
    },
    "get_copper_gold_ratio": {
        "metric_authority": {"level": _supporting_authority("Tradable-price macro proxy; it may describe the growth/rate regime but is not official macro evidence.", requires=["get_10y_real_rate", "get_hy_oas_bp"])},
        "downgrade_rules": ["commodity_ratio_is_macro_proxy_only", "proxy_cannot_independently_drive_action"],
    },
    "get_hyg_momentum": {
        "metric_authority": {"level": _supporting_authority("Dividend-adjusted ETF price is a tradable credit proxy; HY OAS remains the primary spread measure.", requires=["get_hy_oas_bp"])},
        "downgrade_rules": ["hyg_price_proxy_requires_hy_oas_confirmation", "proxy_cannot_replace_official_spread_measure"],
    },
    "get_xly_xlp_ratio": {
        "metric_authority": {"level": _supporting_authority("Sector-price ratio is a risk-appetite proxy, not proof of broad economic health or valuation.", requires=["get_advance_decline_line", "get_hy_oas_bp"])},
        "downgrade_rules": ["sector_ratio_is_risk_appetite_proxy_only", "proxy_cannot_independently_drive_action"],
    },
    "get_crowdedness_dashboard": {
        "metric_authority": {
            "skew_index": _supporting_authority("Third-party tail-risk price observation; not a complete positioning measure."),
            "qqq_put_call_ratio_oi": _supporting_authority("Current option-chain open-interest proxy; historical backtests require dated snapshots."),
            "qqq_short_interest_percent": _supporting_authority("Availability-limited third-party positioning observation.", usage="audit_only"),
            "status": _supporting_authority("Composite label derived from partial inputs; unavailable components must remain visible.", usage="audit_only"),
        },
        "downgrade_rules": ["partial_positioning_components_cannot_be_promoted_to_complete_crowding_fact", "composite_cannot_bypass_component_availability"],
    },
    "get_vxn_vix_ratio": {
        "metric_authority": {"level": _supporting_authority("Derived relative options-pressure ratio; it does not measure fundamentals or valuation.", requires=["get_vxn", "get_vix"])},
        "downgrade_rules": ["derived_volatility_ratio_requires_underlying_series", "ratio_cannot_independently_drive_action"],
    },
    "get_cnn_fear_greed_index": {
        "metric_authority": {
            "score": _supporting_authority("Third-party composite sentiment score; extremes require price, volatility, and credit confirmation."),
            "sub_metrics": _supporting_authority("Component display is audit context only and cannot bypass the composite's semantics.", usage="audit_only"),
        },
        "downgrade_rules": ["composite_sentiment_requires_market_confirmation", "composite_or_submetric_cannot_bypass_total_signal_semantics"],
    },
}

# Coverage is decision-relevant only when a value aggregates constituents or
# analyst consensus. A direct market series does not become weaker merely
# because it has no constituent-coverage object.
COVERAGE_REQUIRED_FUNCTIONS = {
    "get_advance_decline_line",
    "get_percent_above_ma",
    "get_qqq_top10_concentration",
    "get_m7_fundamentals",
    "get_new_highs_lows",
    "get_mcclellan_oscillator_nasdaq_or_nyse",
    "get_ndx_wind_point_in_time_earnings_expectations",
    "get_ndx_pe_and_earnings_yield",
    "get_ndx_forward_earnings_quality",
    "get_m7_capex_cycle",
    "get_m7_earnings_blackout_calendar",
    "get_m7_buyback_flow",
}

# A first-vintage requirement matters in a historical replay only for series
# that can be revised after first publication. Market prices and technical
# indicators are point observations and intentionally stay outside this set.
BACKTEST_VINTAGE_REQUIRED_FUNCTIONS = {
    "get_fed_funds_rate",
    "get_m2_yoy",
    "get_net_liquidity_momentum",
    "get_ndx_wind_point_in_time_earnings_expectations",
    "get_ndx_forward_earnings_quality",
    "get_m7_capex_cycle",
    "get_m7_buyback_flow",
}

CONDITIONAL_OR_REFERENCE_ONLY_METADATA_FIELDS = {
    "source_url",
    "license_note",
    "coverage",
    "vintage_date",
}

SOURCE_TIER_AUTHORITY_MODEL = {
    "official": {
        "can_support": "正式事实或一手公开数据；仍需尊重口径和 effective_date。",
        "cannot_support": "不能自动证明跨层因果或投资动作。",
    },
    "licensed_provider": {
        "can_support": "授权数据源读数，可作为正式数据证据。",
        "cannot_support": "不能绕过授权口径、覆盖率和回测可见日期。",
    },
    "licensed_manual": {
        "can_support": "人工录入授权数据，可作为正式数据证据但需保留录入来源。",
        "cannot_support": "不能伪装成自动实时源或官方直接接口。",
    },
    "proxy": {
        "can_support": "代理观察某个不可直接观测状态。",
        "cannot_support": "不能说成官方事实或单独支撑强结论。",
    },
    "candidate_external_material": {
        "can_support": "事件背景、解释线索或待验证问题。",
        "cannot_support": "不能成为 L1-L5 evidence_ref，不能单独证明指数级结论。",
    },
    "derived_inference": {
        "can_support": "记录推理、假说或最终 claim 的来源关系。",
        "cannot_support": "不能替代底层证据。",
    },
    "unknown": {
        "can_support": "只可作为审计占位。",
        "cannot_support": "不能支撑可发布结论。",
    },
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_data_quality(
    *,
    provider: str = "",
    source_name: str = "",
    source_url: str = "",
    source_tier: str = "",
    as_of_date: str = "",
    effective_date: str = "",
    data_date: str = "",
    vintage_date: str = "",
    collected_at_utc: str = "",
    availability: str = "available",
    fallback_reason: str = "none",
    fallback_chain: Optional[List[str]] = None,
    license_note: str = "public_endpoint_review_required",
    coverage: Any = None,
    methodology: str = "",
    formula: str = "",
    anomalies: Optional[List[Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    quality = {
        "contract_version": DATA_EVIDENCE_CONTRACT_VERSION,
        "provider": provider or source_name or "missing",
        "source_name": source_name or provider or "missing",
        "source_url": source_url or "missing",
        "source_tier": source_tier or "proxy",
        "as_of_date": as_of_date or data_date or effective_date or "not_available",
        "effective_date": effective_date or "not_available",
        "data_date": data_date or as_of_date or effective_date or "not_available",
        "vintage_date": vintage_date or "not_available",
        "collected_at_utc": collected_at_utc or utc_timestamp(),
        "availability": availability or "available",
        "fallback_reason": fallback_reason or "none",
        "fallback_chain": fallback_chain if isinstance(fallback_chain, list) else [],
        "license_note": license_note or "public_endpoint_review_required",
        "coverage": coverage if coverage is not None else {},
        "methodology": methodology or formula or "",
        "formula": formula or methodology or "",
        "anomalies": anomalies if isinstance(anomalies, list) else [],
    }
    quality.update(extra)
    return quality


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if value in (None, "", {}):
        return []
    return [value]


def _append_unique(items: List[Any], value: Any) -> None:
    if value and value not in items:
        items.append(value)


def _meaningful_fallback_explanation(payload: Dict[str, Any], quality: Dict[str, Any]) -> str:
    for value in (
        quality.get("fallback_reason"),
        quality.get("degraded_reason"),
        quality.get("unavailable_reason"),
        quality.get("no_data_reason"),
        payload.get("fallback_reason"),
        payload.get("degraded_reason"),
        payload.get("unavailable_reason"),
        payload.get("notes"),
    ):
        text = str(value or "").strip()
        if text and text.lower() not in {"none", "missing", "not_available", "not_applicable"}:
            return text
    return ""


def _parse_date(value: Any) -> Optional[datetime]:
    if value in (None, "", "missing", "not_available", "not_applicable"):
        return None
    try:
        return datetime.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _date_text(value: Any) -> str:
    parsed = _parse_date(value)
    return parsed.date().isoformat() if parsed else ""


def _source_tier_from_name(text: str) -> str:
    lowered = text.lower()
    if "fred" in lowered or "invesco" in lowered or "nasdaq" in lowered or "sec" in lowered or "damodaran" in lowered:
        return "official"
    if "wind" in lowered and "manual" not in lowered:
        return "licensed_provider/Wind"
    if "manual" in lowered or "wind" in lowered:
        return "licensed_manual/Wind"
    if "alpha vantage" in lowered or "yfinance" in lowered or "yahoo" in lowered:
        return "third_party_estimate"
    if "calculated" in lowered or "proxy" in lowered:
        return "proxy"
    return "proxy"


def normalize_source_tier_for_evidence_passport(value: Any) -> str:
    """Normalize legacy data_quality source_tier values to the Stage 4 authority model."""
    text = str(value or "").lower()
    if "mixed" in text and any(token in text for token in ("third_party", "proxy", "estimate")):
        return "proxy"
    if "licensed_provider" in text or ("wind" in text and "manual" not in text):
        return "licensed_provider"
    if "licensed_manual" in text or "manual" in text:
        return "licensed_manual"
    if "official" in text:
        return "official"
    if "formal_data_source" in text:
        return "formal_data_source"
    if "trusted_sidecar" in text:
        return "trusted_sidecar"
    if "candidate" in text or "external" in text or "headline" in text or "media" in text or "rumor" in text:
        return "candidate_external_material"
    if (
        "proxy" in text
        or "third_party" in text
        or "estimate" in text
        or "market_data_provider" in text
        or "component_model" in text
    ):
        return "proxy"
    if "derived" in text or "hypothesis" in text or "claim" in text:
        return "derived_inference"
    return "unknown"


def source_authority_model_for_tier(source_tier: Any) -> Dict[str, str]:
    tier = normalize_source_tier_for_evidence_passport(source_tier)
    return dict(SOURCE_TIER_AUTHORITY_MODEL.get(tier, SOURCE_TIER_AUTHORITY_MODEL["unknown"]))


def _license_note(source_tier: str, source_name: str) -> str:
    lowered = f"{source_tier} {source_name}".lower()
    if "manual" in lowered:
        return "licensed_manual"
    if "wind" in lowered:
        return "licensed_provider"
    if "fred" in lowered or "sec" in lowered or "nasdaq" in lowered or "invesco" in lowered or "damodaran" in lowered:
        return "official_public"
    if "openbb" in lowered:
        return "open_source_allowed_personal_research"
    return "public_endpoint_review_required"


def _infer_data_date(payload: Dict[str, Any], quality: Dict[str, Any], effective_date: Optional[str]) -> str:
    value = payload.get("value") if isinstance(payload.get("value"), dict) else {}
    return _first_text(
        quality.get("data_date"),
        payload.get("data_date"),
        payload.get("date"),
        value.get("data_date") if isinstance(value, dict) else None,
        value.get("date") if isinstance(value, dict) else None,
        value.get("observation_date") if isinstance(value, dict) else None,
        value.get("effective_date") if isinstance(value, dict) else None,
        effective_date,
    )


def normalize_data_evidence(
    payload: Dict[str, Any],
    *,
    function_id: str,
    layer: Optional[int] = None,
    effective_date: Optional[str] = None,
    collected_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    normalized = payload if isinstance(payload, dict) else {"value": payload}
    quality = deepcopy(normalized.get("data_quality") if isinstance(normalized.get("data_quality"), dict) else {})
    legacy_contract_missing = not str(quality.get("contract_version") or "").strip()
    legacy_failure_text = " ".join(
        str(value or "").strip().lower()
        for value in (
            normalized.get("notes"),
            normalized.get("error"),
            normalized.get("failure_type"),
            quality.get("failure_type"),
            quality.get("failure_reason"),
        )
    )
    legacy_explicit_failure = (
        legacy_contract_missing
        and not has_meaningful_observation_value(normalized.get("value"))
        and any(
            marker in legacy_failure_text
            for marker in (
                "failed to calculate",
                "failed to get",
                "insufficient data",
                "no data returned",
                "upstream_error",
                "collection_error",
            )
        )
    )
    source_name = _first_text(quality.get("source_name"), normalized.get("source_name"), normalized.get("source"), normalized.get("provider"))
    source_tier = _first_text(quality.get("source_tier"), normalized.get("source_tier"), _source_tier_from_name(source_name))
    data_date = _infer_data_date(normalized, quality, effective_date)
    effective = _first_text(quality.get("effective_date"), effective_date, normalized.get("effective_date"), normalized.get("date"), data_date)
    as_of_date = _first_text(quality.get("as_of_date"), normalized.get("as_of_date"), normalized.get("as_of"), data_date, effective)
    source_url = _first_text(quality.get("source_url"), normalized.get("source_url"))
    formula = _first_text(quality.get("formula"), normalized.get("formula"), normalized.get("methodology"))
    methodology = _first_text(quality.get("methodology"), normalized.get("methodology"), formula, normalized.get("notes"))
    fallback_chain = _as_list(quality.get("fallback_chain") or normalized.get("fallback_chain"))
    fallback_reason = _first_text(quality.get("fallback_reason"), normalized.get("fallback_reason"))
    anomalies = _as_list(quality.get("anomalies"))
    coverage = quality.get("coverage") if "coverage" in quality else normalized.get("coverage", {})
    availability = _first_text(quality.get("availability"), normalized.get("availability"))
    reason = no_data_reason(normalized)
    if legacy_explicit_failure:
        availability = "unavailable"
        fallback_reason = "legacy_collection_failure"
        _append_unique(anomalies, "legacy_available_failure_normalized_to_unavailable")
    if not availability:
        availability = "unavailable" if reason else "available"
    if fallback_chain and not fallback_reason:
        fallback_reason = "fallback_chain_declared"
    if not fallback_reason:
        fallback_reason = "none"

    if not source_url:
        source_url = "missing"
        _append_unique(anomalies, "missing_source_url")
    if not quality.get("license_note"):
        _append_unique(anomalies, "license_note_defaulted")
    vintage = _first_text(quality.get("vintage_date"), normalized.get("vintage_date"))
    if not vintage:
        vintage = "not_available"
        _append_unique(anomalies, "vintage_date_not_available")
    if coverage in (None, ""):
        coverage = {}
    if coverage == {}:
        _append_unique(anomalies, "coverage_missing_or_unspecified")

    normalized_quality = build_data_quality(
        provider=_first_text(quality.get("provider"), normalized.get("provider"), source_name),
        source_name=source_name,
        source_url=source_url,
        source_tier=source_tier,
        as_of_date=_date_text(as_of_date) or as_of_date or "not_available",
        effective_date=_date_text(effective) or effective or "not_available",
        data_date=_date_text(data_date) or data_date or "not_available",
        vintage_date=_date_text(vintage) or vintage,
        collected_at_utc=collected_at_utc or quality.get("collected_at_utc") or normalized.get("collection_timestamp_utc") or "",
        availability=availability,
        fallback_reason=fallback_reason,
        fallback_chain=fallback_chain,
        license_note=quality.get("license_note") or _license_note(source_tier, source_name),
        coverage=coverage,
        methodology=methodology,
        formula=formula,
        anomalies=anomalies,
    )
    for key, value in quality.items():
        if key not in normalized_quality:
            normalized_quality[key] = value
    weak_policy = WEAK_METRIC_AUTHORITY_POLICIES.get(function_id)
    if weak_policy:
        existing_authority = normalized_quality.get("metric_authority")
        producer_authority = existing_authority if isinstance(existing_authority, dict) else {}
        policy_authority = {
            field: _merge_authority_rule_min_privilege(rule, producer_authority.get(field))
            for field, rule in weak_policy["metric_authority"].items()
        }
        undeclared_policy = _supporting_authority(
            "Field is not declared in the weak-metric authority policy; retain for audit only until explicitly reviewed.",
            usage="audit_only",
        )
        undeclared_authority = {
            field: _merge_authority_rule_min_privilege(undeclared_policy, rule)
            for field, rule in producer_authority.items()
            if field not in policy_authority
        }
        normalized_quality["metric_authority"] = {**undeclared_authority, **policy_authority}
        normalized_quality["downgrade_rules"] = list(
            dict.fromkeys(
                _as_list(normalized_quality.get("downgrade_rules"))
                + list(weak_policy["downgrade_rules"])
            )
        )
    normalized_quality["function_id"] = function_id
    if layer is not None:
        normalized_quality["layer"] = layer
    normalized["data_quality"] = normalized_quality
    return normalized


def data_evidence_issues(payload: Dict[str, Any], *, function_id: str, backtest_date: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
    issues: Dict[str, List[Dict[str, Any]]] = {"hard_block": [], "degraded": [], "audit_warn": []}

    def add(level: str, code: str, detail: str = "") -> None:
        issues[level].append({"function_id": function_id, "code": code, "detail": detail})

    if quality.get("contract_version") != DATA_EVIDENCE_CONTRACT_VERSION:
        add("degraded", "missing_data_evidence_contract", "contract_version is not data_evidence_v1")

    missing = sorted(
        field
        for field in REQUIRED_DATA_QUALITY_FIELDS
        if field not in quality and field not in CONDITIONAL_OR_REFERENCE_ONLY_METADATA_FIELDS
    )
    for field in missing:
        add("degraded", f"missing_{field}", "required data_quality field absent")

    value = payload.get("value")
    availability = str(quality.get("availability") or payload.get("availability") or "").lower()
    unavailable = availability == "unavailable" or bool(no_data_reason(payload))

    if (
        not unavailable
        and function_id in COVERAGE_REQUIRED_FUNCTIONS
        and quality.get("coverage") in (None, "", {})
    ):
        add("degraded", "missing_coverage")
    if not unavailable and backtest_date and function_id in BACKTEST_VINTAGE_REQUIRED_FUNCTIONS:
        if quality.get("vintage_date") in (None, "", "missing"):
            add("degraded", "missing_vintage_date")
        elif quality.get("vintage_date") == "not_available":
            add("degraded", "vintage_date_not_available")

    if availability == "available" and not has_meaningful_observation_value(value):
        add("hard_block", "available_without_meaningful_value")

    if backtest_date:
        effective = _parse_date(backtest_date)
        for key in ("data_date", "as_of_date", "effective_date", "vintage_date"):
            parsed = _parse_date(quality.get(key))
            if effective is not None and parsed is not None and parsed > effective:
                add("hard_block", "data_date_after_effective_date", f"{key}={quality.get(key)} > {backtest_date}")
        if function_id in LATEST_ONLY_FUNCTIONS and not payload.get("backtest_skipped") and availability == "available":
            add("hard_block", "latest_only_source_used_in_backtest")

    source_tier = str(quality.get("source_tier") or "").lower()
    source_text = " ".join(str(item).lower() for item in [quality.get("provider"), quality.get("source_name"), quality.get("methodology"), quality.get("formula")])
    looks_proxy = any(token in source_tier for token in PROXY_SOURCE_TOKENS) or "proxy" in source_text
    looks_official = any(token in source_tier for token in OFFICIAL_SOURCE_TOKENS)
    if looks_proxy and looks_official and "licensed_manual" not in source_tier:
        add("hard_block", "proxy_marked_as_official")

    fallback_context = " ".join(
        str(item).lower()
        for item in [
            quality.get("source_tier"),
            quality.get("source_name"),
            quality.get("provider"),
            quality.get("availability"),
            quality.get("fallback_reason"),
            *list(quality.get("anomalies") if isinstance(quality.get("anomalies"), list) else []),
        ]
    )
    actual_fallback = "fallback" in fallback_context or "degraded" in fallback_context
    fallback_explanation = _meaningful_fallback_explanation(payload, quality)
    if quality.get("fallback_chain") and not fallback_explanation and actual_fallback:
        level = "hard_block" if function_id in CORE_EVIDENCE_FUNCTIONS else "degraded"
        add(level, "fallback_without_reason")

    return issues


def flatten_issue_groups(groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for severity in ("hard_block", "degraded", "audit_warn"):
        for issue in groups.get(severity, []):
            rows.append({"severity": severity, **issue})
    return rows
