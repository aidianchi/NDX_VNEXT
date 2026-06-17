from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

try:
    from .data_availability import has_meaningful_observation_value, no_data_reason
except ImportError:
    from data_availability import has_meaningful_observation_value, no_data_reason


DATA_EVIDENCE_CONTRACT_VERSION = "data_evidence_v1"

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
    "get_cnn_fear_greed_index",
    "get_advance_decline_line",
    "get_percent_above_ma",
    "get_qqq_qqew_ratio",
    "get_qqq_top10_concentration",
    "get_m7_fundamentals",
    "get_new_highs_lows",
    "get_mcclellan_oscillator_nasdaq_or_nyse",
    "get_ndx_wind_valuation_snapshot",
    "get_ndx_pe_and_earnings_yield",
    "get_ndx_forward_earnings_quality",
    "get_equity_risk_premium",
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

PROXY_SOURCE_TOKENS = {"proxy", "component_model", "third_party_estimate"}
OFFICIAL_SOURCE_TOKENS = {"official", "official_provider", "licensed_manual/wind", "licensed_provider/wind"}


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

    missing = sorted(field for field in REQUIRED_DATA_QUALITY_FIELDS if field not in quality)
    for field in missing:
        add("degraded", f"missing_{field}", "required data_quality field absent")

    if quality.get("source_url") == "missing":
        add("degraded", "missing_source_url")
    if quality.get("license_note") in (None, "", "missing"):
        add("degraded", "missing_license_note")
    if quality.get("coverage") in (None, "", {}):
        add("degraded", "missing_coverage")
    if quality.get("vintage_date") in (None, "", "missing"):
        add("degraded", "missing_vintage_date")
    elif quality.get("vintage_date") == "not_available":
        add("degraded", "vintage_date_not_available")

    value = payload.get("value")
    availability = str(quality.get("availability") or payload.get("availability") or "").lower()
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

    anomalies = quality.get("anomalies") if isinstance(quality.get("anomalies"), list) else []
    if any(item in anomalies for item in ("missing_source_url", "license_note_defaulted", "coverage_missing_or_unspecified")):
        add("audit_warn", "metadata_defaulted", ", ".join(str(item) for item in anomalies))
    return issues


def flatten_issue_groups(groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for severity in ("hard_block", "degraded", "audit_warn"):
        for issue in groups.get(severity, []):
            rows.append({"severity": severity, **issue})
    return rows
