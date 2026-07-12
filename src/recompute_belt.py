"""Independent recomputation validation belt (the "second book").

Motivation (see investigation_reports/20260711_first_principles/WORK_ORDERS.md
item 3 and U1_RESULTS.md #4): a controlled tampering experiment proved that
`core.checker.DataIntegrity` reacts to zero of the ten runs when snapshot
*values* were altered -- it only checks structural completeness, never
numeric correctness. Historically a net-liquidity value that was wrong by a
full order of magnitude passed every existing gate. This module is a second,
independently implemented set of computations over the same collector
snapshot, built specifically to catch that class of bug.

INDEPENDENCE RULE (non-negotiable): this module must never import the
pipeline's own calculation code (`src/tools*.py`, `src/collector.py`, or
anything that derives percentiles/growth rates/ratios for the main run). If
it shared code with the thing it is meant to audit, a bug in that shared code
would be invisible to both books at once. Only the Python standard library is
used below (no numpy/pandas dependency was needed once formulas were pinned
down against the real snapshot).

Coverage is intentionally honest rather than broad: every field this module
found and inspected is emitted with one of four statuses --
`match` / `deviation` / `unrecomputable_missing_raw` / `uncovered` -- so gaps
in coverage are visible in the report instead of silently absent from it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple

MODULE_VERSION = "recompute_belt_v1"


# ---------------------------------------------------------------------------
# Tolerance constants
# ---------------------------------------------------------------------------
# Each tolerance is named after *why* it is the size it is, not just its
# value, per WORK_ORDERS.md item 3's instruction to document the reasoning.

EPSILON_EXACT = 1e-6
"""A pipeline value that is stored at full float precision (no rounding
step), e.g. a top-level convenience field that should equal a nested field
verbatim. Only float representation slack is allowed."""

TOLERANCE_ROUNDED_2DP = 0.01 + 1e-6
"""Deterministic arithmetic (subtraction/division) compared against a
pipeline value observed to be rounded to 2 decimal places before being
written to the snapshot (e.g. `deviation_pct`, `EarningsYield`,
`equity_risk_premium.level`). Half a cent of rounding slack plus float
epsilon; verified empirically against the live snapshot (max observed
rounding residual ~0.005)."""

TOLERANCE_ROUNDED_4DP = 0.00005 + 1e-6
"""Same idea as TOLERANCE_ROUNDED_2DP but for ratio-style fields observed to
round to 4 decimal places (e.g. `spot_over_ma20_ratio`, `vxn_vix_ratio`)."""

TOLERANCE_PERCENTILE_EXACT = 0.06
"""Rank-based percentile recomputed from a fully available raw series using
the pipeline's own documented method (`count(v<=current)/n*100`, taken
verbatim from the Damodaran ERP payload's `method` field and empirically
reproduced for the NDX forward-PE percentile too). The pipeline rounds to 1
decimal place, so 0.05 is the maximum honest rounding slack; 0.06 adds a hair
of float epsilon."""

TOLERANCE_PERCENTILE_VENDOR_RANK = 0.5
"""Percentile reconstructed only from a vendor-supplied (rank, sample_count)
pair via the standard mid-rank convention `(rank - 0.5) / sample_count * 100`
-- not from an independently observed raw series. This checks the Wind
payload's own internal arithmetic consistency, not truth against
independently observed data (Wind's own tie-handling/rounding is unknown), so
the tolerance is intentionally loose and the finding is informational, never
gate-eligible."""

MAGNITUDE_SENTINEL_NOTE = (
    "order-of-magnitude plausibility band, not a precise value check; a "
    "billion/million unit mixup is a ~1e3 factor, so bands are set wide "
    "enough to span multi-year normal variation while still catching that "
    "class of bug"
)

STATUS_MATCH = "match"
STATUS_DEVIATION = "deviation"
STATUS_MISSING_RAW = "unrecomputable_missing_raw"
STATUS_UNCOVERED = "uncovered"

CRITICALITY_CRITICAL = "critical"
CRITICALITY_STANDARD = "standard"
CRITICALITY_INFO = "informational"


# ---------------------------------------------------------------------------
# Generic snapshot accessors (deliberately trivial -- no pipeline logic)
# ---------------------------------------------------------------------------

def _get_indicator(data_json: Dict[str, Any], function_id: str) -> Optional[Dict[str, Any]]:
    indicators = data_json.get("indicators") if isinstance(data_json, dict) else None
    if not isinstance(indicators, list):
        return None
    for item in indicators:
        if isinstance(item, dict) and item.get("function_id") == function_id:
            return item
    return None


def _indicator_value(item: Optional[Dict[str, Any]]) -> Any:
    if not isinstance(item, dict):
        return None
    raw = item.get("raw_data")
    if not isinstance(raw, dict):
        return None
    return raw.get("value")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Finding construction
# ---------------------------------------------------------------------------

def _finding(
    field: str,
    pipeline_value: Any,
    recomputed_value: Any,
    tolerance: Optional[float],
    status: str,
    category: str,
    criticality: str,
    note: str = "",
) -> Dict[str, Any]:
    deviation = None
    if _is_number(pipeline_value) and _is_number(recomputed_value):
        deviation = recomputed_value - pipeline_value
    return {
        "field": field,
        "category": category,
        "pipeline_value": pipeline_value,
        "recomputed_value": recomputed_value,
        "deviation": deviation,
        "tolerance": tolerance,
        "status": status,
        "criticality": criticality,
        "note": note,
    }


def _compare(
    field: str,
    pipeline_value: Any,
    recomputed_value: Any,
    tolerance: float,
    category: str,
    criticality: str,
    note: str = "",
) -> Dict[str, Any]:
    if not (_is_number(pipeline_value) and _is_number(recomputed_value)):
        return _finding(
            field, pipeline_value, recomputed_value, tolerance, STATUS_MISSING_RAW,
            category, criticality, note or "pipeline or recomputed value missing/non-numeric",
        )
    status = STATUS_MATCH if abs(recomputed_value - pipeline_value) <= tolerance else STATUS_DEVIATION
    return _finding(field, pipeline_value, recomputed_value, tolerance, status, category, criticality, note)


def _missing(field: str, category: str, criticality: str, note: str) -> Dict[str, Any]:
    return _finding(field, None, None, None, STATUS_MISSING_RAW, category, criticality, note)


def _uncovered(field: str, category: str, note: str) -> Dict[str, Any]:
    return _finding(field, None, None, None, STATUS_UNCOVERED, category, CRITICALITY_INFO, note)


# ---------------------------------------------------------------------------
# Recompute primitives
# ---------------------------------------------------------------------------

def _rank_percentile(series: Sequence[Any], current: Any) -> Optional[float]:
    """count(v <= current) / n * 100.

    This is the method documented inline in the Damodaran ERP payload's own
    `method` field ("count(values <= current_value) / sample_count * 100")
    and was independently confirmed (by hand, against the live snapshot) to
    reproduce the NDX forward-PE percentile too. Used only where the raw
    series is actually embedded in the snapshot.
    """
    if not _is_number(current):
        return None
    values = [v for v in series if _is_number(v)]
    n = len(values)
    if n == 0:
        return None
    count = sum(1 for v in values if v <= current)
    return count / n * 100.0


def _mid_rank_percentile(rank: Any, sample_count: Any) -> Optional[float]:
    """(rank - 0.5) / sample_count * 100 -- standard mid-rank convention.

    Used only to reconcile a vendor-supplied (rank, sample_count) pair
    against the vendor's own reported percentile; this is an internal
    consistency check on the Wind payload, not a recomputation from
    independently observed raw data.
    """
    if not _is_number(rank) or not _is_number(sample_count) or not sample_count:
        return None
    return (rank - 0.5) / sample_count * 100.0


def _parse_percent_string(text: Any) -> Optional[float]:
    if _is_number(text):
        return float(text)
    if not isinstance(text, str):
        return None
    try:
        return float(text.strip().rstrip("%").strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Category A: percentile checks
# ---------------------------------------------------------------------------

def check_damodaran_erp_percentiles(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    """Reference cross-validation target: 10y=25.0%, 5y=43.3% (human-verified,
    see WORK_ORDERS.md item 3)."""
    findings: List[Dict[str, Any]] = []
    fid = "get_damodaran_us_implied_erp"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        return findings
    meta = value.get("damodaran_erp_historical_percentiles")
    monthly_series = value.get("monthly_series")
    base_field = f"{fid}.damodaran_erp_historical_percentiles"
    if not isinstance(meta, dict) or not isinstance(monthly_series, list):
        handled.add(base_field)
        findings.append(_missing(base_field, "percentile", CRITICALITY_CRITICAL,
                                  "monthly_series or percentile metadata absent from snapshot"))
        return findings

    primary_field = meta.get("primary_field") or "erp_t12m_adjusted_payout"
    windows = meta.get("windows") if isinstance(meta.get("windows"), dict) else {}
    for window_key, window_meta in windows.items():
        if not isinstance(window_meta, dict):
            continue
        field = f"{base_field}.windows.{window_key}.percentile"
        handled.add(field)
        pipeline_pctl = window_meta.get("percentile")
        current_value = window_meta.get("current_value")
        window_start = window_meta.get("window_start")
        window_end = window_meta.get("window_end")
        windowed = [
            entry.get(primary_field)
            for entry in monthly_series
            if isinstance(entry, dict)
            and _is_number(entry.get(primary_field))
            and (not window_start or str(entry.get("data_date", "")) >= window_start)
            and (not window_end or str(entry.get("data_date", "")) <= window_end)
        ]
        note = (
            f"method=count(v<=current)/n*100; primary_field={primary_field}; "
            f"window={window_start}..{window_end}; n={len(windowed)} "
            f"(pipeline sample_count={window_meta.get('sample_count')})"
        )
        if not windowed or not _is_number(current_value):
            findings.append(_missing(field, "percentile", CRITICALITY_CRITICAL, note + "; empty windowed raw series"))
            continue
        recomputed = _rank_percentile(windowed, current_value)
        findings.append(_compare(field, pipeline_pctl, recomputed, TOLERANCE_PERCENTILE_EXACT,
                                  "percentile", CRITICALITY_CRITICAL, note))

    for dup_key, window_key in (("damodaran_erp_percentile_5y", "5y"), ("damodaran_erp_percentile_10y", "10y")):
        field = f"{fid}.{dup_key}"
        handled.add(field)
        window_meta = windows.get(window_key) if isinstance(windows.get(window_key), dict) else {}
        canonical = window_meta.get("percentile")
        pipeline_val = value.get(dup_key)
        findings.append(_compare(
            field, pipeline_val, canonical, EPSILON_EXACT, "percentile", CRITICALITY_INFO,
            "duplicate top-level convenience field vs nested windows.*.percentile internal consistency",
        ))
    return findings


def check_wind_pe_percentile(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    """NDX forward/trailing PE percentile, recomputed from the embedded
    `HistoryOfMarket.*_percentile_context.raw_series` where present."""
    findings: List[Dict[str, Any]] = []
    fid = "get_ndx_pe_and_earnings_yield"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        return findings
    hom = value.get("HistoryOfMarket")
    if not isinstance(hom, dict):
        return findings

    for direction in ("forward", "trailing"):
        ctx_key = f"{direction}_percentile_context"
        ctx = hom.get(ctx_key)
        field = f"{fid}.HistoryOfMarket.{ctx_key}.percentile"
        handled.add(field)
        if not isinstance(ctx, dict):
            findings.append(_missing(field, "percentile", CRITICALITY_STANDARD, f"{ctx_key} absent"))
            continue
        current_value = hom.get(f"{direction}_pe")
        raw_series = ctx.get("raw_series")
        pipeline_status = ctx.get("status")
        pipeline_pctl = ctx.get("percentile")
        required_min = ctx.get("required_min_observations")
        n_available = len(raw_series) if isinstance(raw_series, list) else 0
        note = (
            f"method=count(v<=current)/n*100; n={n_available}; "
            f"required_min_observations={required_min}; pipeline_status={pipeline_status}"
        )
        if not isinstance(raw_series, list) or not raw_series:
            findings.append(_missing(field, "percentile", CRITICALITY_STANDARD, note + "; raw_series absent/empty"))
            continue
        if _is_number(required_min) and n_available < required_min:
            if pipeline_status == "insufficient_history" and pipeline_pctl is None:
                findings.append(_finding(
                    field, pipeline_pctl, None, None, STATUS_MATCH, "percentile", CRITICALITY_STANDARD,
                    note + "; both sides agree window is insufficient_history (methodology match, no numeric percentile to compare)",
                ))
            else:
                findings.append(_finding(
                    field, pipeline_pctl, None, None, STATUS_DEVIATION, "percentile", CRITICALITY_STANDARD,
                    note + "; recompute says insufficient history but pipeline published a percentile anyway",
                ))
            continue
        series_values = [entry.get("value") for entry in raw_series if isinstance(entry, dict)]
        if not _is_number(current_value):
            findings.append(_missing(field, "percentile", CRITICALITY_STANDARD, note + "; current PE value missing"))
            continue
        recomputed = _rank_percentile(series_values, current_value)
        findings.append(_compare(field, pipeline_pctl, recomputed, TOLERANCE_PERCENTILE_EXACT,
                                  "percentile", CRITICALITY_STANDARD, note))

        # HistoryOfMarket also carries a top-level alias (e.g. `forward_percentile`)
        # that should equal the nested context's percentile verbatim.
        alias_key = f"{direction}_percentile"
        alias_field = f"{fid}.HistoryOfMarket.{alias_key}"
        handled.add(alias_field)
        findings.append(_compare(
            alias_field, hom.get(alias_key), pipeline_pctl, EPSILON_EXACT, "percentile", CRITICALITY_INFO,
            f"top-level alias should equal HistoryOfMarket.{ctx_key}.percentile verbatim",
        ))
    return findings


def check_wind_rank_percentile_consistency(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    """Informational-only: reconcile Wind's own (rank, sample_count) pairs
    against its reported percentile via the standard mid-rank formula. No
    independently observed raw series is available for these fields, so this
    only catches internal payload corruption, not vendor computation errors."""
    findings: List[Dict[str, Any]] = []
    fid = "get_ndx_wind_valuation_snapshot"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        return findings

    for group_key in ("PEPercentileWindows", "RiskPremiumPercentileWindows"):
        windows = value.get(group_key)
        if not isinstance(windows, dict):
            continue
        for window_key, window_meta in windows.items():
            if not isinstance(window_meta, dict):
                continue
            field = f"{fid}.{group_key}.{window_key}.percentile"
            handled.add(field)
            pipeline_pctl = window_meta.get("percentile")
            rank = window_meta.get("rank")
            sample_count = window_meta.get("sample_count")
            note = (
                f"method=(rank-0.5)/sample_count*100 mid-rank convention vs vendor-supplied "
                f"(rank={rank}, sample_count={sample_count}); internal payload consistency only, "
                f"not independent ground truth (no raw daily series embedded)"
            )
            recomputed = _mid_rank_percentile(rank, sample_count)
            if recomputed is None:
                findings.append(_missing(field, "percentile", CRITICALITY_INFO, note + "; rank/sample_count missing"))
                continue
            findings.append(_compare(field, pipeline_pctl, recomputed, TOLERANCE_PERCENTILE_VENDOR_RANK,
                                      "percentile", CRITICALITY_INFO, note))

    issues = value.get("WindPercentileIssues")
    if isinstance(issues, list):
        for idx, issue in enumerate(issues):
            if not isinstance(issue, dict) or "percentile" not in issue:
                continue
            field = f"{fid}.WindPercentileIssues[{idx}].percentile"
            handled.add(field)
            findings.append(_missing(
                field, "percentile", CRITICALITY_INFO,
                f"vendor-flagged: {issue.get('reason')}; sample_count={issue.get('sample_count')} "
                f"< min_sample_count={issue.get('min_sample_count')}; no rank field to reconcile against",
            ))

    alias_field = f"{fid}.PEHistoricalPercentile"
    handled.add(alias_field)
    alias_window = value.get("PEHistoricalPercentileWindow")
    pe_windows = value.get("PEPercentileWindows")
    if alias_window and isinstance(pe_windows, dict):
        target = pe_windows.get(alias_window)
        canonical = target.get("percentile") if isinstance(target, dict) else None
        pipeline_alias = value.get("PEHistoricalPercentile")
        findings.append(_compare(
            alias_field, pipeline_alias, canonical, EPSILON_EXACT, "percentile", CRITICALITY_INFO,
            f"top-level alias should equal PEPercentileWindows.{alias_window}.percentile verbatim "
            f"(window declared via PEHistoricalPercentileWindow)",
        ))
    else:
        findings.append(_missing(alias_field, "percentile", CRITICALITY_INFO, "PEHistoricalPercentileWindow not declared"))
    return findings


# ---------------------------------------------------------------------------
# Category C (+D): net liquidity -- ratio/diff recompute AND unit sentinel
# ---------------------------------------------------------------------------
# This is the field named explicitly in WORK_ORDERS.md item 3 as the
# historical incident: a net-liquidity value wrong by 10x passed every
# existing gate. It gets both a formula recompute (fed_assets - tga - rrp)
# and an order-of-magnitude sentinel.

NET_LIQUIDITY_MAGNITUDE_BANDS_BILLION_USD = {
    # Bands span the 2016-2026 Fed balance sheet cycle (pre-taper ~800B to
    # post-QE peak ~8,900B) with headroom, while still catching a
    # billion/million mixup, which shows up as a ~1e3 factor.
    "fed_assets": (500.0, 12000.0),
    "tga": (0.0, 3000.0),
    "rrp": (0.0, 4000.0),
    "level": (-3000.0, 13000.0),
}


def _unit_label_consistency(fid: str, value: Dict[str, Any], components: Dict[str, Any], handled: Set[str]) -> Dict[str, Any]:
    field = f"{fid}.unit_labels"
    handled.add(field)
    level_unit = value.get("level_unit")
    components_unit = value.get("components_unit")
    component_units = value.get("component_units") if isinstance(value.get("component_units"), dict) else {}
    labels = [str(label) for label in [level_unit, components_unit, *component_units.values()] if label is not None]
    note = f"level_unit={level_unit}, components_unit={components_unit}, component_units={component_units}"
    if not labels:
        return _missing(field, "unit_sentinel", CRITICALITY_CRITICAL, note + "; no unit labels declared")
    consistent = len(set(labels)) == 1
    status = STATUS_MATCH if consistent else STATUS_DEVIATION
    return _finding(
        field, level_unit, components_unit, None, status, "unit_sentinel", CRITICALITY_CRITICAL,
        note + ("; all labels consistent" if consistent else "; MIXED UNIT LABELS across level/components -- billion/million mixup risk"),
    )


def _net_liquidity_magnitude_sentinel(fid: str, value: Dict[str, Any], components: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    candidates = dict(components)
    candidates["level"] = value.get("level")
    for key, (low, high) in NET_LIQUIDITY_MAGNITUDE_BANDS_BILLION_USD.items():
        field = f"{fid}.magnitude_sentinel.{key}"
        handled.add(field)
        magnitude = candidates.get(key)
        note = f"plausible_band_billion_usd=[{low}, {high}]; {MAGNITUDE_SENTINEL_NOTE}"
        if not _is_number(magnitude):
            findings.append(_missing(field, "unit_sentinel", CRITICALITY_CRITICAL, note + "; value missing"))
            continue
        in_band = low <= magnitude <= high
        status = STATUS_MATCH if in_band else STATUS_DEVIATION
        findings.append(_finding(
            field, magnitude, None, None, status, "unit_sentinel", CRITICALITY_CRITICAL,
            note + ("; within band" if in_band else "; OUTSIDE PLAUSIBLE BAND -- possible unit mixup, verify source"),
        ))
    return findings


def check_net_liquidity(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    fid = "get_net_liquidity_momentum"
    value = _indicator_value(_get_indicator(data_json, fid))
    field = f"{fid}.level"
    handled.add(field)
    if not isinstance(value, dict):
        findings.append(_missing(field, "ratio_or_diff", CRITICALITY_CRITICAL, "indicator/value absent"))
        return findings
    components = value.get("components")
    if not isinstance(components, dict):
        findings.append(_missing(field, "ratio_or_diff", CRITICALITY_CRITICAL, "components dict absent"))
        return findings

    fed_assets = components.get("fed_assets")
    tga = components.get("tga")
    rrp = components.get("rrp")
    pipeline_level = value.get("level")
    note = f"formula=fed_assets-tga-rrp; fed_assets={fed_assets}, tga={tga}, rrp={rrp} (billion_usd)"
    if not (_is_number(fed_assets) and _is_number(tga) and _is_number(rrp)):
        findings.append(_missing(field, "ratio_or_diff", CRITICALITY_CRITICAL, note + "; one or more components non-numeric"))
    else:
        recomputed = fed_assets - tga - rrp
        findings.append(_compare(field, pipeline_level, recomputed, TOLERANCE_ROUNDED_2DP,
                                  "ratio_or_diff", CRITICALITY_CRITICAL, note))

    findings.append(_unit_label_consistency(fid, value, components, handled))
    findings.extend(_net_liquidity_magnitude_sentinel(fid, value, components, handled))
    return findings


# ---------------------------------------------------------------------------
# Category C: cross-indicator and intra-payload ratio/diff checks
# ---------------------------------------------------------------------------

def check_cross_indicator_ratios(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    fid = "get_vxn_vix_ratio"
    field = f"{fid}.level"
    handled.add(field)
    vxn_val = _indicator_value(_get_indicator(data_json, "get_vxn"))
    vix_val = _indicator_value(_get_indicator(data_json, "get_vix"))
    ratio_val = _indicator_value(_get_indicator(data_json, fid))
    vxn_level = vxn_val.get("level") if isinstance(vxn_val, dict) else None
    vix_level = vix_val.get("level") if isinstance(vix_val, dict) else None
    pipeline_level = ratio_val.get("level") if isinstance(ratio_val, dict) else None
    note = f"formula=get_vxn.level/get_vix.level; vxn={vxn_level}, vix={vix_level}"
    if _is_number(vxn_level) and _is_number(vix_level) and vix_level:
        findings.append(_compare(field, pipeline_level, vxn_level / vix_level, TOLERANCE_ROUNDED_4DP,
                                  "ratio_or_diff", CRITICALITY_STANDARD, note))
    else:
        findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, note + "; component level(s) missing"))

    fid = "get_equity_risk_premium"
    field = f"{fid}.level"
    handled.add(field)
    erp_val = _indicator_value(_get_indicator(data_json, fid))
    if isinstance(erp_val, dict):
        components = erp_val.get("components") if isinstance(erp_val.get("components"), dict) else {}
        ey_raw = components.get("NDX wind_trailing_earnings_yield")
        tr_raw = components.get("10Y Treasury Yield (Risk-Free)")
        ey = _parse_percent_string(ey_raw)
        tr = _parse_percent_string(tr_raw)
        pipeline_level = erp_val.get("level")
        note = f"formula=trailing_earnings_yield%-10y_treasury%; earnings_yield={ey_raw}, treasury={tr_raw}"
        if ey is not None and tr is not None:
            findings.append(_compare(field, pipeline_level, ey - tr, TOLERANCE_ROUNDED_2DP,
                                      "ratio_or_diff", CRITICALITY_STANDARD, note))
        else:
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, note + "; component percentage string(s) unparsable"))
    else:
        findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, "indicator/value absent"))

    fid = "get_ndx_pe_and_earnings_yield"
    field = f"{fid}.EarningsYield"
    handled.add(field)
    pey_val = _indicator_value(_get_indicator(data_json, fid))
    if isinstance(pey_val, dict):
        trailing_pe = pey_val.get("TrailingPE")
        pipeline_ey = pey_val.get("EarningsYield")
        note = f"formula=100/TrailingPE; TrailingPE={trailing_pe}"
        if _is_number(trailing_pe) and trailing_pe:
            findings.append(_compare(field, pipeline_ey, 100.0 / trailing_pe, TOLERANCE_ROUNDED_2DP,
                                      "ratio_or_diff", CRITICALITY_STANDARD, note))
        else:
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, note + "; TrailingPE missing/zero"))
    else:
        findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, "indicator/value absent"))

    return findings


DEVIATION_PCT_FUNCTION_IDS: Tuple[str, ...] = (
    "get_10y2y_spread_bp",
    "get_10y_treasury",
    "get_10y_real_rate",
    "get_10y_breakeven",
)

SPOT_OVER_MA20_FUNCTION_IDS: Tuple[str, ...] = (
    "get_vix",
    "get_vxn",
)


def check_ma_deviation_family(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for fid in DEVIATION_PCT_FUNCTION_IDS:
        field = f"{fid}.deviation_pct"
        handled.add(field)
        value = _indicator_value(_get_indicator(data_json, fid))
        if not isinstance(value, dict):
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, "indicator/value absent"))
            continue
        level = value.get("level")
        ma = value.get("ma")
        pipeline_dev = value.get("deviation_pct")
        note = f"formula=(level-ma)/ma*100; level={level}, ma={ma}"
        if _is_number(level) and _is_number(ma) and ma:
            findings.append(_compare(field, pipeline_dev, (level - ma) / ma * 100.0, TOLERANCE_ROUNDED_2DP,
                                      "ratio_or_diff", CRITICALITY_STANDARD, note))
        else:
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, note + "; level/ma missing"))

    for fid in SPOT_OVER_MA20_FUNCTION_IDS:
        field = f"{fid}.spot_over_ma20_ratio"
        handled.add(field)
        value = _indicator_value(_get_indicator(data_json, fid))
        if not isinstance(value, dict):
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, "indicator/value absent"))
            continue
        level = value.get("level")
        ma20 = value.get("ma20")
        pipeline_ratio = value.get("spot_over_ma20_ratio")
        note = f"formula=level/ma20; level={level}, ma20={ma20}"
        if _is_number(level) and _is_number(ma20) and ma20:
            findings.append(_compare(field, pipeline_ratio, level / ma20, TOLERANCE_ROUNDED_4DP,
                                      "ratio_or_diff", CRITICALITY_STANDARD, note))
        else:
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, note + "; level/ma20 missing"))
    return findings


# ---------------------------------------------------------------------------
# L5 technical snapshot: moving averages recomputable from recent_closes_30
# ---------------------------------------------------------------------------

L5_UNRECOMPUTABLE_TECHNICAL_KEYS: Tuple[str, ...] = (
    "rsi_14", "macd_line", "macd_signal", "macd_histogram", "atr_14",
    "adx_14", "pdi_14", "mdi_14", "obv", "mfi_14", "cmf_20",
    "donchian_upper", "donchian_middle", "donchian_lower", "vwap_20",
)


def check_l5_moving_averages(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    fid = "get_l5_deterministic_snapshot"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        return findings
    closes_raw = value.get("recent_closes_30")
    exact = value.get("exact_technical_values") if isinstance(value.get("exact_technical_values"), dict) else {}
    closes: List[float] = []
    if isinstance(closes_raw, list):
        closes = [entry.get("close") for entry in closes_raw if isinstance(entry, dict) and _is_number(entry.get("close"))]

    for window, sma_key in ((5, "sma_5"), (20, "sma_20")):
        field = f"{fid}.exact_technical_values.{sma_key}"
        handled.add(field)
        pipeline_value = exact.get(sma_key)
        note = f"formula=mean(last {window} closes in recent_closes_30); n_available={len(closes)}"
        if len(closes) < window:
            findings.append(_missing(field, "moving_average", CRITICALITY_STANDARD, note + "; insufficient closes"))
            continue
        recomputed = sum(closes[-window:]) / window
        findings.append(_compare(field, pipeline_value, recomputed, TOLERANCE_ROUNDED_2DP,
                                  "moving_average", CRITICALITY_STANDARD, note))

    row_count = value.get("row_count")
    for sma_key in ("sma_50", "sma_60", "sma_100", "sma_200"):
        field = f"{fid}.exact_technical_values.{sma_key}"
        handled.add(field)
        findings.append(_missing(
            field, "moving_average", CRITICALITY_STANDARD,
            f"needs a longer close-price window than the embedded recent_closes_30 provides "
            f"(full history row_count={row_count} is not embedded in the snapshot)",
        ))
    for key in L5_UNRECOMPUTABLE_TECHNICAL_KEYS:
        field = f"{fid}.exact_technical_values.{key}"
        handled.add(field)
        findings.append(_missing(
            field, "technical_indicator", CRITICALITY_STANDARD,
            "Wilder-smoothed or multi-window technical indicator; its exact value is path-dependent on "
            f"the full row_count={row_count} OHLCV history, which is not embedded (only the last 30 closes, "
            "no OHLC/volume, are present), so it cannot be exactly reproduced from this snapshot alone",
        ))
    return findings


def check_multi_scale_ma_position(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    fid = "get_multi_scale_ma_position"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        return findings
    current_price = value.get("current_price")
    positions = value.get("ma_positions") if isinstance(value.get("ma_positions"), dict) else {}
    for key, entry in positions.items():
        field = f"{fid}.ma_positions.{key}.deviation_pct"
        handled.add(field)
        if not isinstance(entry, dict):
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, "ma entry missing"))
            continue
        ma_value = entry.get("value")
        pipeline_dev = entry.get("deviation_pct")
        note = f"formula=(current_price-ma_value)/ma_value*100; current_price={current_price}, ma_value={ma_value}"
        if _is_number(current_price) and _is_number(ma_value) and ma_value:
            recomputed = (current_price - ma_value) / ma_value * 100.0
            findings.append(_compare(field, pipeline_dev, recomputed, TOLERANCE_ROUNDED_2DP,
                                      "ratio_or_diff", CRITICALITY_STANDARD, note))
        else:
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, note + "; current_price/ma_value missing"))
    return findings


# ---------------------------------------------------------------------------
# Category B: growth/momentum -- honestly unrecomputable in this snapshot
# ---------------------------------------------------------------------------

MOMENTUM_SUBFIELD_SOURCES: Tuple[Tuple[str, str], ...] = (
    ("get_fed_funds_rate", "momentum"),
    ("get_hyg_momentum", "momentum"),
)


def check_momentum_fields(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for fid, key in MOMENTUM_SUBFIELD_SOURCES:
        value = _indicator_value(_get_indicator(data_json, fid))
        momentum = value.get(key) if isinstance(value, dict) else None
        if not isinstance(momentum, dict):
            continue
        for sub_key, sub_value in momentum.items():
            if not _is_number(sub_value):
                continue
            field = f"{fid}.{key}.{sub_key}"
            handled.add(field)
            findings.append(_missing(
                field, "growth_rate", CRITICALITY_STANDARD,
                "requires multi-day raw price/level history not embedded in this snapshot "
                "(only the current level and moving-average summary stats are present)",
            ))
    return findings


# ---------------------------------------------------------------------------
# Safety net: catch any percentile-named field the specific checks missed
# ---------------------------------------------------------------------------

def _looks_like_raw_series(node: Any) -> Optional[str]:
    """Heuristic: does this dict contain a sibling list that looks like a raw
    date/value time series (length >= 10, elements are plain numbers, or
    dicts carrying a date-ish key)? Used only to distinguish 'uncovered, but
    a raw series is visibly sitting right there' from 'genuinely missing'."""
    if not isinstance(node, dict):
        return None
    for key, val in node.items():
        if not isinstance(val, list) or len(val) < 10:
            continue
        sample = val[:5]
        if all(_is_number(x) for x in sample):
            return f"sibling list '{key}' (len={len(val)}) of plain numbers"
        if all(isinstance(x, dict) for x in sample):
            keys_union: Set[str] = set()
            for x in sample:
                keys_union.update(x.keys())
            if keys_union & {"date", "data_date", "as_of", "timestamp"}:
                return f"sibling list '{key}' (len={len(val)}) of dated observations"
    return None


def _walk_numeric_leaves(node: Any, path: str) -> Iterator[Tuple[str, Any, Any]]:
    if isinstance(node, dict):
        for key, val in node.items():
            child_path = f"{path}.{key}"
            if _is_number(val):
                yield child_path, val, node
            else:
                yield from _walk_numeric_leaves(val, child_path)
    elif isinstance(node, list):
        for idx, val in enumerate(node):
            child_path = f"{path}[{idx}]"
            if _is_number(val):
                yield child_path, val, None
            else:
                yield from _walk_numeric_leaves(val, child_path)


def check_uncatalogued_percentile_fields(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    indicators = data_json.get("indicators") if isinstance(data_json, dict) else None
    if not isinstance(indicators, list):
        return findings
    for item in indicators:
        if not isinstance(item, dict):
            continue
        fid = item.get("function_id") or "unknown_function"
        value = _indicator_value(item)
        if value is None:
            continue
        for field, _leaf, parent in _walk_numeric_leaves(value, str(fid)):
            key_name = field.rsplit(".", 1)[-1].split("[")[0]
            if "percentile" not in key_name.lower():
                continue
            if field in handled:
                continue
            handled.add(field)
            raw_hint = _looks_like_raw_series(parent)
            if raw_hint:
                findings.append(_uncovered(
                    field, "percentile",
                    f"candidate raw series present ({raw_hint}) but no recompute recipe implemented in this pass",
                ))
            else:
                findings.append(_missing(
                    field, "percentile", CRITICALITY_STANDARD,
                    "no raw series or vendor rank/sample_count sibling found in this indicator's payload",
                ))
    return findings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _summarize(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    checked = len(findings)
    matched = sum(1 for f in findings if f["status"] == STATUS_MATCH)
    deviations = sum(1 for f in findings if f["status"] == STATUS_DEVIATION)
    missing_raw = sum(1 for f in findings if f["status"] == STATUS_MISSING_RAW)
    uncovered = sum(1 for f in findings if f["status"] == STATUS_UNCOVERED)
    coverage_ratio = round((matched + deviations) / checked, 4) if checked else 0.0
    critical_deviations = sum(
        1 for f in findings if f["status"] == STATUS_DEVIATION and f["criticality"] == CRITICALITY_CRITICAL
    )
    return {
        "checked": checked,
        "matched": matched,
        "deviations": deviations,
        "unrecomputable_missing_raw": missing_raw,
        "uncovered": uncovered,
        "coverage_ratio": coverage_ratio,
        "critical_deviation_count": critical_deviations,
    }


def run(data_json: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full independent recompute belt over a collector snapshot.

    Returns a report dict: top-level summary counts plus a flat `findings`
    list, each entry shaped {field, category, pipeline_value,
    recomputed_value, deviation, tolerance, status, criticality, note}.
    """
    if not isinstance(data_json, dict):
        data_json = {}
    handled: Set[str] = set()
    findings: List[Dict[str, Any]] = []
    findings.extend(check_damodaran_erp_percentiles(data_json, handled))
    findings.extend(check_wind_pe_percentile(data_json, handled))
    findings.extend(check_wind_rank_percentile_consistency(data_json, handled))
    findings.extend(check_net_liquidity(data_json, handled))
    findings.extend(check_cross_indicator_ratios(data_json, handled))
    findings.extend(check_ma_deviation_family(data_json, handled))
    findings.extend(check_l5_moving_averages(data_json, handled))
    findings.extend(check_multi_scale_ma_position(data_json, handled))
    findings.extend(check_momentum_fields(data_json, handled))
    findings.extend(check_uncatalogued_percentile_fields(data_json, handled))

    return {
        "module": "recompute_belt",
        "module_version": MODULE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **_summarize(findings),
        "findings": findings,
    }


def critical_deviation_findings(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gate-eligible subset: deviations on fields tagged critical. Used by
    core.checker.DataIntegrity to decide whether to hard-block publish."""
    return [
        f for f in (report.get("findings") or [])
        if f.get("status") == STATUS_DEVIATION and f.get("criticality") == CRITICALITY_CRITICAL
    ]
