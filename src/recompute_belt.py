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

FED_FUNDS_PATH_NEGLIGIBLE_VOLUME = 5.0
FED_FUNDS_PATH_THIN_VOLUME = 100.0
"""Frozen canon thresholds repeated deliberately in the independent book.
They must not be imported from pipeline code or trusted from the payload,
otherwise a coordinated threshold/path mutation could fool both books."""

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


def _recompute_input(data_json: Dict[str, Any], function_id: str) -> Dict[str, Any]:
    inputs = data_json.get("recompute_inputs") if isinstance(data_json, dict) else None
    value = inputs.get(function_id) if isinstance(inputs, dict) else None
    return value if isinstance(value, dict) else {}


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


def check_vix_term_structure_percentile(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    """VIX3M/VIX term-structure ratio's own 5y/10y percentile, recomputed from
    the embedded `percentile_context.raw_series` -- added for
    investigation_reports/20260711_first_principles/WORK_ORDERS.md item 4,
    task A (see get_vix_term_structure in tools_L1.py). Shares the same
    windows-over-one-raw-series shape as check_damodaran_erp_percentiles
    above, just with a daily instead of monthly primary field."""
    findings: List[Dict[str, Any]] = []
    fid = "get_vix_term_structure"
    value = _indicator_value(_get_indicator(data_json, fid))
    base_field = f"{fid}.percentile_context"
    if not isinstance(value, dict):
        handled.add(base_field)
        findings.append(_missing(base_field, "percentile", CRITICALITY_STANDARD, "indicator/value absent"))
        return findings

    ctx = value.get("percentile_context")
    raw_series = ctx.get("raw_series") if isinstance(ctx, dict) else None
    if not isinstance(ctx, dict) or not isinstance(raw_series, list):
        handled.add(base_field)
        findings.append(_missing(base_field, "percentile", CRITICALITY_STANDARD,
                                  "percentile_context or raw_series absent from snapshot"))
        return findings

    primary_field = ctx.get("primary_field") or "ratio_vix3m_over_vix"
    windows = ctx.get("windows") if isinstance(ctx.get("windows"), dict) else {}
    for window_key, window_meta in windows.items():
        if not isinstance(window_meta, dict):
            continue
        field = f"{base_field}.windows.{window_key}.percentile"
        handled.add(field)
        pipeline_pctl = window_meta.get("percentile")
        current_value = window_meta.get("current_value")
        window_start = window_meta.get("window_start")
        window_end = window_meta.get("window_end")
        pipeline_status = window_meta.get("status")
        eligible_entries = [
            entry
            for entry in raw_series
            if isinstance(entry, dict)
            and _is_number(entry.get(primary_field))
            and (not window_start or str(entry.get("data_date", "")) >= window_start)
            and (not window_end or str(entry.get("data_date", "")) <= window_end)
        ]
        # Prefer rebuilding VIX3M/VIX from the two legs.  The producer computes
        # its percentile before rounding the displayed ratio to four decimals;
        # ranking the rounded convenience field can move one or more ties.
        if primary_field == "ratio_vix3m_over_vix" and all(
            _is_number(entry.get("vix")) and _is_number(entry.get("vix3m")) and float(entry["vix"]) != 0
            for entry in eligible_entries
        ):
            windowed = [float(entry["vix3m"]) / float(entry["vix"]) for entry in eligible_entries]
            current_vix = value.get("vix") if isinstance(value.get("vix"), dict) else {}
            current_vix3m = value.get("vix3m") if isinstance(value.get("vix3m"), dict) else {}
            if (
                _is_number(current_vix.get("level"))
                and float(current_vix["level"]) != 0
                and _is_number(current_vix3m.get("level"))
            ):
                current_value = float(current_vix3m["level"]) / float(current_vix["level"])
        else:
            windowed = [entry.get(primary_field) for entry in eligible_entries]
        note = (
            f"method=count(v<=current)/n*100; primary_field={primary_field}; "
            f"window={window_start}..{window_end}; n={len(windowed)} "
            f"(pipeline sample_count={window_meta.get('sample_count')}, pipeline_status={pipeline_status})"
        )
        if pipeline_status == "insufficient_history" and pipeline_pctl is None:
            findings.append(_finding(
                field, pipeline_pctl, None, None, STATUS_MATCH, "percentile", CRITICALITY_STANDARD,
                note + "; both sides agree window is insufficient_history (methodology match, no numeric percentile to compare)",
            ))
            continue
        if not windowed or not _is_number(current_value):
            findings.append(_missing(field, "percentile", CRITICALITY_STANDARD, note + "; empty windowed raw series or current_value missing"))
            continue
        recomputed = _rank_percentile(windowed, current_value)
        findings.append(_compare(field, pipeline_pctl, recomputed, TOLERANCE_PERCENTILE_EXACT,
                                  "percentile", CRITICALITY_STANDARD, note))

    for dup_key, window_key in (("percentile_5y", "5y"), ("percentile_10y", "10y")):
        field = f"{fid}.{dup_key}"
        handled.add(field)
        window_meta = windows.get(window_key) if isinstance(windows.get(window_key), dict) else {}
        canonical = window_meta.get("percentile")
        pipeline_val = value.get(dup_key)
        findings.append(_compare(
            field, pipeline_val, canonical, EPSILON_EXACT, "percentile", CRITICALITY_INFO,
            "duplicate top-level convenience field vs nested percentile_context.windows.*.percentile internal consistency",
        ))
    return findings


def check_fed_funds_rate_path(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    """Independently rebuild the reduced ZQ curve from embedded raw rows.

    Standard-library only by design: the audit book selects the last close
    on/before effective_date, recomputes 10-row average volume and liquidity
    exclusion, then derives implied rates, slope and priced cuts without
    importing any pipeline helper.
    """
    findings: List[Dict[str, Any]] = []
    fid = "get_fed_funds_rate_path"
    value = _indicator_value(_get_indicator(data_json, fid))
    base_field = f"{fid}.raw_series"
    if not isinstance(value, dict):
        handled.add(base_field)
        findings.append(_missing(base_field, "rate_path", CRITICALITY_STANDARD, "indicator/value absent"))
        return findings

    raw_series = value.get("raw_series")
    effective_date = str(value.get("effective_date") or "")
    thresholds = value.get("liquidity_thresholds") if isinstance(value.get("liquidity_thresholds"), dict) else {}
    if not isinstance(raw_series, list):
        handled.add(base_field)
        findings.append(_missing(
            base_field,
            "rate_path",
            CRITICALITY_STANDARD,
            "raw_series absent from snapshot",
        ))
        return findings

    for key, frozen_value in (
        ("negligible_below_avg_volume_10d", FED_FUNDS_PATH_NEGLIGIBLE_VOLUME),
        ("thin_below_avg_volume_10d", FED_FUNDS_PATH_THIN_VOLUME),
    ):
        field = f"{fid}.liquidity_thresholds.{key}"
        handled.add(field)
        findings.append(_compare(
            field,
            thresholds.get(key),
            frozen_value,
            EPSILON_EXACT,
            "rate_path",
            CRITICALITY_STANDARD,
            "payload declaration checked against the frozen independent-book threshold",
        ))

    rebuilt: List[Dict[str, Any]] = []
    for contract_entry in raw_series:
        if not isinstance(contract_entry, dict):
            continue
        contract = contract_entry.get("contract")
        months_ahead = contract_entry.get("months_ahead")
        observations = contract_entry.get("observations")
        if not contract or not _is_number(months_ahead) or not isinstance(observations, list):
            continue
        eligible_observations = [
            item for item in observations
            if isinstance(item, dict)
            and _is_number(item.get("close"))
            and (not effective_date or str(item.get("data_date") or "") <= effective_date)
        ]
        eligible_observations.sort(key=lambda item: str(item.get("data_date") or ""))
        eligible_observations = eligible_observations[-10:]
        if not eligible_observations:
            continue
        volumes = [item.get("volume") for item in eligible_observations if _is_number(item.get("volume"))]
        avg_volume = sum(volumes) / len(volumes) if volumes else None
        if avg_volume is None or avg_volume < FED_FUNDS_PATH_NEGLIGIBLE_VOLUME:
            continue
        latest = eligible_observations[-1]
        rebuilt.append({
            "contract": contract,
            "months_ahead": int(months_ahead),
            "implied_rate": 100.0 - float(latest["close"]),
            "avg_volume_10d": avg_volume,
            "liquidity_tier": "thin" if avg_volume < FED_FUNDS_PATH_THIN_VOLUME else "adequate",
        })
    rebuilt.sort(key=lambda item: item["months_ahead"])

    pipeline_path = value.get("path") if isinstance(value.get("path"), list) else []
    pipeline_by_contract = {
        item.get("contract"): item for item in pipeline_path
        if isinstance(item, dict) and item.get("contract")
    }
    rebuilt_contracts = [item["contract"] for item in rebuilt]
    pipeline_contracts = [
        item.get("contract") for item in pipeline_path
        if isinstance(item, dict) and item.get("contract")
    ]
    membership_field = f"{fid}.path_membership"
    handled.add(membership_field)
    findings.append(_finding(
        membership_field,
        pipeline_contracts,
        rebuilt_contracts,
        None,
        STATUS_MATCH if pipeline_contracts == rebuilt_contracts else STATUS_DEVIATION,
        "rate_path",
        CRITICALITY_STANDARD,
        "formal path must contain exactly the independently rebuilt non-negligible contracts in months_ahead order",
    ))

    for rebuilt_item in rebuilt:
        contract = rebuilt_item["contract"]
        field = f"{fid}.path.{contract}.implied_rate"
        handled.add(field)
        pipeline_item = pipeline_by_contract.get(contract) if isinstance(pipeline_by_contract.get(contract), dict) else {}
        findings.append(_compare(
            field,
            pipeline_item.get("implied_rate"),
            rebuilt_item["implied_rate"],
            TOLERANCE_ROUNDED_4DP,
            "rate_path",
            CRITICALITY_STANDARD,
            "formula=100-latest raw close on/before effective_date after independent liquidity filtering",
        ))

    recomputed_status = "available" if len(rebuilt) >= 4 else "insufficient_curve"
    status_field = f"{fid}.status"
    handled.add(status_field)
    pipeline_status = value.get("status")
    findings.append(_finding(
        status_field,
        pipeline_status,
        recomputed_status,
        None,
        STATUS_MATCH if pipeline_status == recomputed_status else STATUS_DEVIATION,
        "rate_path",
        CRITICALITY_STANDARD,
        f"qualified_contracts={len(rebuilt)}; minimum_required=4",
    ))

    if recomputed_status == "insufficient_curve":
        for field_name in ("slope_12m", "cuts_priced_bps"):
            field = f"{fid}.{field_name}"
            handled.add(field)
            pipeline_value = value.get(field_name)
            findings.append(_finding(
                field,
                pipeline_value,
                None,
                None,
                STATUS_MATCH if pipeline_value is None else STATUS_DEVIATION,
                "rate_path",
                CRITICALITY_STANDARD,
                "both books must withhold the numeric curve conclusion when fewer than four contracts qualify",
            ))
        return findings

    front = rebuilt[0]
    far = rebuilt[-1]
    recomputed_slope = far["implied_rate"] - front["implied_rate"]
    recomputed_cuts = round(-recomputed_slope * 100)
    for field_name, recomputed_value, tolerance in (
        ("slope_12m", recomputed_slope, TOLERANCE_ROUNDED_4DP),
        ("cuts_priced_bps", recomputed_cuts, EPSILON_EXACT),
    ):
        field = f"{fid}.{field_name}"
        handled.add(field)
        findings.append(_compare(
            field,
            value.get(field_name),
            recomputed_value,
            tolerance,
            "rate_path",
            CRITICALITY_STANDARD,
            f"front={front['contract']}({front['implied_rate']}); far={far['contract']}({far['implied_rate']})",
        ))

    horizon = value.get("horizon_used") if isinstance(value.get("horizon_used"), dict) else {}
    horizon_field = f"{fid}.horizon_used.actual_months_ahead"
    handled.add(horizon_field)
    findings.append(_compare(
        horizon_field,
        horizon.get("actual_months_ahead"),
        far["months_ahead"] - front["months_ahead"],
        EPSILON_EXACT,
        "rate_path",
        CRITICALITY_STANDARD,
        "actual horizon must equal farthest qualified months_ahead minus front qualified months_ahead",
    ))
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
# Category E: M7 capex cycle -- order-of-magnitude sentinel
# ---------------------------------------------------------------------------
# Added for investigation_reports/20260711_first_principles/WORK_ORDERS.md
# item 4 (evidence menu rebalancing). The M7 capex cycle metric
# (get_m7_capex_cycle) is a new quarterly-dollar-figure indicator built from
# SEC XBRL facts; a billion/million unit mixup in that pipeline is exactly
# the class of bug this module exists to catch (see module docstring). This
# is a plausibility band, not a value recompute -- the year-to-date-to-
# discrete-quarter derivation math itself lives only in tools_L4.py, which
# this module must not import (independence rule above). Bands are NOT
# empirically validated against a live snapshot (SEC network access was
# blocked in the build sandbox that added this check), so criticality is
# deliberately "standard" (record, do not hard-block) until a real run
# confirms the ranges; see WORK_LOG for the residual-risk note.

M7_CAPEX_SINGLE_QUARTER_BAND_USD_BN = (0.05, 60.0)
"""Per-company single-quarter capex band. Smaller M7 members' historical
quarters sit near the low end; the largest hyperscalers' AI-buildout
quarters are well under the high end. Wide enough to span the capex
super-cycle while still catching a ~1e3 unit mixup."""

M7_CAPEX_AGGREGATE_QUARTER_BAND_USD_BN = (5.0, 250.0)
"""M7 combined single-quarter capex band, spanning pre-AI-cycle norms
through an elevated buildout scenario with headroom."""


def check_m7_capex_cycle_magnitude(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    fid = "get_m7_capex_cycle"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        field = f"{fid}.companies"
        handled.add(field)
        findings.append(_missing(field, "unit_sentinel", CRITICALITY_STANDARD, "indicator/value absent"))
        return findings

    companies = value.get("companies") if isinstance(value.get("companies"), dict) else {}
    low, high = M7_CAPEX_SINGLE_QUARTER_BAND_USD_BN
    for ticker, company in companies.items():
        quarters = company.get("quarters") if isinstance(company, dict) else None
        field = f"{fid}.magnitude_sentinel.{ticker}.latest_quarter"
        handled.add(field)
        if not isinstance(quarters, list) or not quarters:
            continue
        latest = quarters[-1]
        magnitude = latest.get("value_usd_bn") if isinstance(latest, dict) else None
        note = (
            f"plausible_band_usd_bn=[{low}, {high}]; ticker={ticker}; "
            f"period_end={latest.get('period_end') if isinstance(latest, dict) else None}; {MAGNITUDE_SENTINEL_NOTE}"
        )
        if not _is_number(magnitude):
            findings.append(_missing(field, "unit_sentinel", CRITICALITY_STANDARD, note + "; value missing"))
            continue
        in_band = low <= magnitude <= high
        status = STATUS_MATCH if in_band else STATUS_DEVIATION
        findings.append(_finding(
            field, magnitude, None, None, status, "unit_sentinel", CRITICALITY_STANDARD,
            note + ("; within band" if in_band else "; OUTSIDE PLAUSIBLE BAND -- possible unit mixup, verify source"),
        ))

    aggregate = value.get("m7_aggregate") if isinstance(value.get("m7_aggregate"), dict) else {}
    latest_covered = aggregate.get("latest_covered_quarter") if isinstance(aggregate.get("latest_covered_quarter"), dict) else None
    field = f"{fid}.magnitude_sentinel.m7_aggregate.latest_covered_quarter"
    handled.add(field)
    low_agg, high_agg = M7_CAPEX_AGGREGATE_QUARTER_BAND_USD_BN
    note = f"plausible_band_usd_bn=[{low_agg}, {high_agg}]; {MAGNITUDE_SENTINEL_NOTE}"
    magnitude = latest_covered.get("sum_usd_bn") if isinstance(latest_covered, dict) else None
    if not _is_number(magnitude):
        findings.append(_missing(field, "unit_sentinel", CRITICALITY_STANDARD, note + "; value missing"))
    else:
        in_band = low_agg <= magnitude <= high_agg
        status = STATUS_MATCH if in_band else STATUS_DEVIATION
        findings.append(_finding(
            field, magnitude, None, None, status, "unit_sentinel", CRITICALITY_STANDARD,
            note + ("; within band" if in_band else "; OUTSIDE PLAUSIBLE BAND -- possible unit mixup, verify source"),
        ))
    return findings


# ---------------------------------------------------------------------------
# Category E: M7 earnings-blackout calendar and actual buyback flow
# ---------------------------------------------------------------------------

def _exact_equality(
    field: str,
    pipeline_value: Any,
    recomputed_value: Any,
    category: str,
    criticality: str,
    note: str,
) -> Dict[str, Any]:
    status = STATUS_MATCH if pipeline_value == recomputed_value else STATUS_DEVIATION
    return _finding(field, pipeline_value, recomputed_value, 0.0, status, category, criticality, note)


def _compare_when_recomputed(
    field: str,
    pipeline_value: Any,
    recomputed_value: float,
    tolerance: float,
    category: str,
    criticality: str,
    note: str,
) -> Dict[str, Any]:
    """A missing/non-numeric pipeline value is a deviation when raw recompute succeeded."""
    if not _is_number(pipeline_value):
        return _finding(
            field, pipeline_value, recomputed_value, tolerance, STATUS_DEVIATION,
            category, criticality, note + "; raw recompute succeeded but pipeline value is missing/non-numeric",
        )
    return _compare(field, pipeline_value, recomputed_value, tolerance, category, criticality, note)


def _raw_earnings_date_texts(rows: Any) -> List[str]:
    result: List[str] = []
    if not isinstance(rows, list):
        return result
    for row in rows:
        raw = row.get("date") if isinstance(row, dict) else row
        try:
            text = str(raw)[:10]
            datetime.strptime(text, "%Y-%m-%d")
            result.append(text)
        except Exception:
            continue
    return sorted(set(result))


def check_m7_earnings_blackout_calendar(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    fid = "get_m7_earnings_blackout_calendar"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        field = f"{fid}.raw_earnings_dates"
        handled.add(field)
        return [_missing(field, "date_rule_recompute", CRITICALITY_CRITICAL, "indicator/value absent")]
    raw_by_ticker = value.get("raw_earnings_dates")
    rule = value.get("blackout_rule")
    rows = value.get("per_ticker")
    as_of_text = value.get("as_of_date")
    if not isinstance(raw_by_ticker, dict) or not isinstance(rule, dict) or not isinstance(rows, list):
        field = f"{fid}.raw_earnings_dates"
        handled.add(field)
        return [_missing(field, "date_rule_recompute", CRITICALITY_CRITICAL, "raw dates/rule/per_ticker missing")]
    try:
        as_of = datetime.strptime(str(as_of_text)[:10], "%Y-%m-%d").date()
        before = int(rule["days_before_earnings"])
        after = int(rule["days_after_earnings"])
        lookahead = int(rule["lookahead_days"])
    except Exception:
        field = f"{fid}.blackout_rule"
        handled.add(field)
        return [_missing(field, "date_rule_recompute", CRITICALITY_CRITICAL, "invalid as_of date or rule parameters")]

    recomputed_bools: Dict[str, bool] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("ticker"):
            continue
        ticker = str(row["ticker"])
        parsed = [datetime.strptime(text, "%Y-%m-%d").date() for text in _raw_earnings_date_texts(raw_by_ticker.get(ticker))]
        recent = sorted((item for item in parsed if 0 <= (as_of - item).days <= after), reverse=True)
        upcoming = sorted(item for item in parsed if 0 <= (item - as_of).days <= lookahead)
        selected = recent[0] if recent else (upcoming[0] if upcoming else None)
        if selected is None:
            continue
        recomputed = selected.toordinal() - before <= as_of.toordinal() <= selected.toordinal() + after
        recomputed_bools[ticker] = recomputed
        field = f"{fid}.per_ticker.{ticker}.in_estimated_blackout"
        handled.add(field)
        findings.append(_exact_equality(
            field, row.get("in_estimated_blackout"), recomputed,
            "date_rule_recompute", CRITICALITY_CRITICAL,
            f"raw selected earnings_date={selected.isoformat()}; inclusive days_before={before}, days_after={after}",
        ))

    recomputed_count = sum(1 for state in recomputed_bools.values() if state)
    count_field = f"{fid}.m7_in_blackout_count"
    handled.add(count_field)
    findings.append(_compare_when_recomputed(
        count_field, value.get("m7_in_blackout_count"), recomputed_count, EPSILON_EXACT,
        "date_rule_recompute", CRITICALITY_CRITICAL, "count of independently recomputed true ticker states",
    ))
    share_field = f"{fid}.m7_in_blackout_share_equal_weight"
    handled.add(share_field)
    recomputed_share = round(recomputed_count / 7, 4) if len(recomputed_bools) == 7 else None
    if recomputed_share is None:
        findings.append(_missing(share_field, "date_rule_recompute", CRITICALITY_CRITICAL, "fewer than 7 recomputable M7 dates"))
    else:
        findings.append(_compare_when_recomputed(
            share_field, value.get("m7_in_blackout_share_equal_weight"), recomputed_share, TOLERANCE_ROUNDED_4DP,
            "date_rule_recompute", CRITICALITY_CRITICAL, "equal-weight share=count/7; requires full M7 coverage",
        ))
    return findings


M7_BUYBACK_SINGLE_QUARTER_MAX_USD_BN = 100.0
M7_BUYBACK_AGGREGATE_TTM_MAX_USD_BN = 1000.0


def _belt_calendar_quarter_ordinal(label: Any) -> Optional[int]:
    try:
        year_text, quarter_text = str(label).split("Q", 1)
        quarter = int(quarter_text)
        if quarter not in {1, 2, 3, 4}:
            return None
        return int(year_text) * 4 + quarter - 1
    except (TypeError, ValueError):
        return None


def _belt_calendar_quarter_from_period_end(period_end: Any) -> Optional[str]:
    try:
        parsed = datetime.strptime(str(period_end)[:10], "%Y-%m-%d")
        return f"{parsed.year}Q{(parsed.month - 1) // 3 + 1}"
    except Exception:
        return None


def _belt_last_four_consecutive(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_label: Dict[str, Dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: str(item.get("period_end") or "")):
        label = row.get("calendar_quarter")
        if label and _belt_calendar_quarter_ordinal(label) is not None:
            by_label[str(label)] = row
    ordered = sorted(by_label.values(), key=lambda item: _belt_calendar_quarter_ordinal(item.get("calendar_quarter")) or -1)
    latest_four = ordered[-4:]
    ordinals = [_belt_calendar_quarter_ordinal(row.get("calendar_quarter")) for row in latest_four]
    if len(latest_four) != 4 or any(item is None for item in ordinals):
        return []
    return latest_four if all(ordinals[idx] - ordinals[idx - 1] == 1 for idx in range(1, 4)) else []


def check_m7_buyback_flow(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    fid = "get_m7_buyback_flow"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        field = f"{fid}.raw_quarterly_series"
        handled.add(field)
        return [_missing(field, "quarterly_sum_growth", CRITICALITY_CRITICAL, "indicator/value absent")]
    raw = value.get("raw_quarterly_series")
    per_company = value.get("per_company")
    context = value.get("aggregate_context")
    if not isinstance(raw, dict) or not isinstance(per_company, dict) or not isinstance(context, dict):
        field = f"{fid}.raw_quarterly_series"
        handled.add(field)
        return [_missing(field, "quarterly_sum_growth", CRITICALITY_CRITICAL, "raw series/per_company/context missing")]

    normalized: Dict[str, List[Dict[str, Any]]] = {}
    company_ttm_bn: Dict[str, float] = {}
    for ticker, rows in raw.items():
        clean = [
            dict(row) for row in rows if isinstance(row, dict)
            and _is_number(row.get("value_usd")) and row.get("period_end")
        ] if isinstance(rows, list) else []
        for row in clean:
            pipeline_label = row.get("calendar_quarter")
            recomputed_label = _belt_calendar_quarter_from_period_end(row.get("period_end"))
            field = f"{fid}.raw_quarterly_series.{ticker}.{row.get('period_end')}.calendar_quarter"
            handled.add(field)
            findings.append(_exact_equality(
                field, pipeline_label, recomputed_label,
                "date_rule_recompute", CRITICALITY_CRITICAL, "calendar quarter derived independently from period_end",
            ))
            row["calendar_quarter"] = recomputed_label
        clean = sorted(clean, key=lambda row: str(row["period_end"]))
        normalized[str(ticker)] = clean
        company = per_company.get(ticker) if isinstance(per_company.get(ticker), dict) else {}
        ttm_rows = _belt_last_four_consecutive(clean)
        if len(ttm_rows) == 4:
            recomputed_ttm = round(sum(float(row["value_usd"]) for row in ttm_rows) / 1e9, 3)
            company_ttm_bn[str(ticker)] = recomputed_ttm
            field = f"{fid}.per_company.{ticker}.ttm_buyback_usd_bn"
            handled.add(field)
            findings.append(_compare_when_recomputed(
                field, company.get("ttm_buyback_usd_bn"), recomputed_ttm, 0.001 + EPSILON_EXACT,
                "quarterly_sum_growth", CRITICALITY_CRITICAL, "sum of last four raw normalized quarterly values",
            ))
        elif company.get("availability") == "available":
            field = f"{fid}.per_company.{ticker}.ttm_buyback_usd_bn"
            handled.add(field)
            findings.append(_exact_equality(
                field, company.get("ttm_buyback_usd_bn"), None,
                "quarterly_sum_growth", CRITICALITY_CRITICAL,
                "fewer than four distinct consecutive raw calendar quarters; TTM must be withheld",
            ))
        if clean:
            latest_bn = float(clean[-1]["value_usd"]) / 1e9
            field = f"{fid}.magnitude_sentinel.{ticker}.latest_quarter"
            handled.add(field)
            in_band = 0.0 <= latest_bn <= M7_BUYBACK_SINGLE_QUARTER_MAX_USD_BN
            findings.append(_finding(
                field, latest_bn, None, None, STATUS_MATCH if in_band else STATUS_DEVIATION,
                "unit_sentinel", CRITICALITY_STANDARD,
                f"normalized buyback must be non-negative and <= {M7_BUYBACK_SINGLE_QUARTER_MAX_USD_BN} USD bn; {MAGNITUDE_SENTINEL_NOTE}",
            ))

    by_label: Dict[str, Dict[str, float]] = {}
    for ticker, rows in normalized.items():
        for row in rows:
            label = row.get("calendar_quarter")
            if label and _belt_calendar_quarter_ordinal(label) is not None:
                by_label.setdefault(str(label), {})[ticker] = float(row["value_usd"])
    eligible_labels = sorted(
        (label for label, members in by_label.items() if len(members) >= 5),
        key=lambda label: _belt_calendar_quarter_ordinal(label) or -1,
    )
    latest_label = eligible_labels[-1] if eligible_labels else None
    latest_members = by_label.get(latest_label, {}) if latest_label else {}
    latest_companies = sorted(latest_members)
    if latest_label:
        try:
            year_text, quarter_text = latest_label.split("Q", 1)
            prior_label = f"{int(year_text) - 1}Q{quarter_text}"
        except (TypeError, ValueError):
            prior_label = None
    else:
        prior_label = None
    prior_members = by_label.get(prior_label, {}) if prior_label else {}
    comparable = sorted(set(latest_members) & set(prior_members))
    aligned = sorted(
        ticker for ticker, ttm in company_ttm_bn.items()
        if normalized.get(ticker) and normalized[ticker][-1].get("calendar_quarter") == latest_label
    )
    excluded = sorted(
        ticker for ticker, rows in normalized.items()
        if rows and rows[-1].get("calendar_quarter") != latest_label
    )

    context_checks = {
        "latest_calendar_quarter": latest_label,
        "prior_year_calendar_quarter": prior_label,
        "latest_quarter_companies": latest_companies,
        "yoy_comparable_companies": comparable,
        "ttm_aligned_companies": aligned,
        "excluded_for_fiscal_calendar_misalignment": excluded,
    }
    for key, recomputed_context_value in context_checks.items():
        field = f"{fid}.aggregate_context.{key}"
        handled.add(field)
        pipeline_context_value = context.get(key)
        if isinstance(recomputed_context_value, list) and isinstance(pipeline_context_value, list):
            pipeline_context_value = sorted(str(item) for item in pipeline_context_value)
        findings.append(_exact_equality(
            field, pipeline_context_value, recomputed_context_value,
            "quarterly_sum_growth", CRITICALITY_CRITICAL, "aggregate context independently derived from raw quarterly series",
        ))

    latest_values = list(latest_members.values())
    quarterly_total = round(sum(latest_values) / 1e9, 3) if latest_values else None
    quarterly_field = f"{fid}.m7_quarterly_total"
    handled.add(quarterly_field)
    if quarterly_total is None:
        findings.append(_missing(quarterly_field, "quarterly_sum_growth", CRITICALITY_CRITICAL, "latest aggregate rows missing"))
    else:
        findings.append(_compare_when_recomputed(
            quarterly_field, value.get("m7_quarterly_total"), quarterly_total, 0.001 + EPSILON_EXACT,
            "quarterly_sum_growth", CRITICALITY_CRITICAL, "sum raw values for latest eligible calendar-quarter members",
        ))

    ttm_values = [company_ttm_bn[str(ticker)] for ticker in aligned if str(ticker) in company_ttm_bn]
    ttm_total = round(sum(ttm_values), 3) if len(ttm_values) >= 5 else None
    ttm_field = f"{fid}.m7_ttm_total"
    handled.add(ttm_field)
    if ttm_total is None:
        findings.append(_exact_equality(
            ttm_field, value.get("m7_ttm_total"), None,
            "quarterly_sum_growth", CRITICALITY_CRITICAL, "fewer than five aligned company TTM values; aggregate withheld",
        ))
    else:
        findings.append(_compare_when_recomputed(
            ttm_field, value.get("m7_ttm_total"), ttm_total, 0.001 + EPSILON_EXACT,
            "quarterly_sum_growth", CRITICALITY_CRITICAL, "sum independently recomputed aligned company TTM values",
        ))
        field = f"{fid}.magnitude_sentinel.m7_ttm_total"
        handled.add(field)
        in_band = 0.0 <= ttm_total <= M7_BUYBACK_AGGREGATE_TTM_MAX_USD_BN
        findings.append(_finding(
            field, ttm_total, None, None, STATUS_MATCH if in_band else STATUS_DEVIATION,
            "unit_sentinel", CRITICALITY_STANDARD,
            f"aggregate TTM must be non-negative and <= {M7_BUYBACK_AGGREGATE_TTM_MAX_USD_BN} USD bn; {MAGNITUDE_SENTINEL_NOTE}",
        ))

    current_sum = 0.0
    prior_sum = 0.0
    comparable_found = 0
    for ticker in comparable:
        by_label = {row.get("calendar_quarter"): float(row["value_usd"]) for row in normalized.get(str(ticker), [])}
        if latest_label in by_label and prior_label in by_label:
            current_sum += by_label[latest_label]
            prior_sum += by_label[prior_label]
            comparable_found += 1
    recomputed_yoy = round((current_sum / prior_sum - 1.0) * 100.0, 2) if comparable_found >= 5 and prior_sum else None
    yoy_field = f"{fid}.yoy_pct"
    handled.add(yoy_field)
    if recomputed_yoy is None:
        findings.append(_exact_equality(
            yoy_field, value.get("yoy_pct"), None,
            "quarterly_sum_growth", CRITICALITY_CRITICAL, "fewer than five raw comparable companies or zero prior sum",
        ))
    else:
        findings.append(_compare_when_recomputed(
            yoy_field, value.get("yoy_pct"), recomputed_yoy, TOLERANCE_ROUNDED_2DP,
            "quarterly_sum_growth", CRITICALITY_CRITICAL, "latest/prior-year same-calendar-quarter comparable subset",
        ))
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

    fid = "get_vix_term_structure"
    field = f"{fid}.level"
    handled.add(field)
    term_structure_val = _indicator_value(_get_indicator(data_json, fid))
    if isinstance(term_structure_val, dict):
        vix_leg = term_structure_val.get("vix") if isinstance(term_structure_val.get("vix"), dict) else {}
        vix3m_leg = term_structure_val.get("vix3m") if isinstance(term_structure_val.get("vix3m"), dict) else {}
        vix_level = vix_leg.get("level")
        vix3m_level = vix3m_leg.get("level")
        pipeline_level = term_structure_val.get("level")
        note = f"formula=vix3m.level/vix.level (intra-payload legs); vix3m={vix3m_level}, vix={vix_level}"
        if _is_number(vix3m_level) and _is_number(vix_level) and vix_level:
            findings.append(_compare(field, pipeline_level, vix3m_level / vix_level, TOLERANCE_ROUNDED_4DP,
                                      "ratio_or_diff", CRITICALITY_STANDARD, note))
        else:
            findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, note + "; component level(s) missing"))
    else:
        findings.append(_missing(field, "ratio_or_diff", CRITICALITY_STANDARD, "indicator/value absent"))

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
# L5 technical snapshot: independently recomputable from audit-only raw OHLCV
# ---------------------------------------------------------------------------

L5_UNRECOMPUTABLE_TECHNICAL_KEYS: Tuple[str, ...] = (
    "rsi_14", "macd_line", "macd_signal", "macd_histogram", "atr_14",
    "adx_14", "pdi_14", "mdi_14", "obv", "mfi_14", "cmf_20",
    "donchian_upper", "donchian_middle", "donchian_lower", "vwap_20",
)


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _ema(values: Sequence[float], span: int) -> List[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * float(value) + (1.0 - alpha) * result[-1])
    return result


def _wilder_ewm(values: Sequence[float], window: int, *, seed_from_first: bool = False) -> List[Optional[float]]:
    if not values:
        return []
    if seed_from_first:
        result: List[Optional[float]] = [float(values[0])]
        alpha = 1.0 / window
        for value in values[1:]:
            previous = result[-1]
            result.append(alpha * float(value) + (1.0 - alpha) * float(previous))
        return result
    result = [None] * len(values)
    if len(values) < window:
        return result
    result[window - 1] = sum(float(value) for value in values[:window]) / window
    for index in range(window, len(values)):
        previous = float(result[index - 1])
        result[index] = (previous * (window - 1) + float(values[index])) / window
    return result


def _l5_recompute_values(rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    cleaned = [
        row for row in rows
        if isinstance(row, dict)
        and all(_is_number(row.get(key)) for key in ("high", "low", "close", "volume"))
    ]
    if not cleaned:
        return {}
    high = [float(row["high"]) for row in cleaned]
    low = [float(row["low"]) for row in cleaned]
    close = [float(row["close"]) for row in cleaned]
    volume = [float(row["volume"]) for row in cleaned]
    result: Dict[str, Optional[float]] = {}
    for window in (5, 20, 50, 60, 100, 200):
        result[f"sma_{window}"] = _mean(close[-window:]) if len(close) >= window else None

    deltas = [0.0] + [close[index] - close[index - 1] for index in range(1, len(close))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    avg_gains = _wilder_ewm(gains, 14, seed_from_first=True)
    avg_losses = _wilder_ewm(losses, 14, seed_from_first=True)
    if len(close) >= 14 and avg_gains and avg_losses:
        gain = float(avg_gains[-1])
        loss = float(avg_losses[-1])
        result["rsi_14"] = 100.0 if loss == 0 else 100.0 - (100.0 / (1.0 + gain / loss))

    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd = [fast - slow for fast, slow in zip(ema12, ema26)]
    signal = _ema(macd, 9)
    if macd:
        result["macd_line"] = macd[-1]
        result["macd_signal"] = signal[-1]
        result["macd_histogram"] = macd[-1] - signal[-1]

    true_ranges = []
    for index in range(len(close)):
        previous_close = close[index - 1] if index else close[index]
        true_ranges.append(max(high[index] - low[index], abs(high[index] - previous_close), abs(low[index] - previous_close)))
    atr = _wilder_ewm(true_ranges, 14)
    if atr and atr[-1] is not None:
        result["atr_14"] = float(atr[-1])

    plus_dm = [0.0]
    minus_dm = [0.0]
    for index in range(1, len(close)):
        up_move = high[index] - high[index - 1]
        down_move = low[index - 1] - low[index]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
    smooth_plus = _wilder_ewm(plus_dm, 14)
    smooth_minus = _wilder_ewm(minus_dm, 14)
    dx: List[Optional[float]] = [None] * len(close)
    pdi: List[Optional[float]] = [None] * len(close)
    mdi: List[Optional[float]] = [None] * len(close)
    for index in range(len(close)):
        if atr[index] in (None, 0) or smooth_plus[index] is None or smooth_minus[index] is None:
            continue
        pdi[index] = 100.0 * float(smooth_plus[index]) / float(atr[index])
        mdi[index] = 100.0 * float(smooth_minus[index]) / float(atr[index])
        denominator = float(pdi[index]) + float(mdi[index])
        dx[index] = 0.0 if denominator == 0 else 100.0 * abs(float(pdi[index]) - float(mdi[index])) / denominator
    valid_dx = [float(value) for value in dx if value is not None]
    adx_values = _wilder_ewm(valid_dx, 14)
    if adx_values and adx_values[-1] is not None:
        result["adx_14"] = float(adx_values[-1])
    result["pdi_14"] = next((float(value) for value in reversed(pdi) if value is not None), None)
    result["mdi_14"] = next((float(value) for value in reversed(mdi) if value is not None), None)

    obv = volume[0]
    for index in range(1, len(close)):
        if close[index] < close[index - 1]:
            obv -= volume[index]
        else:
            obv += volume[index]
    result["obv"] = obv

    if len(close) >= 20:
        result["donchian_upper"] = max(high[-20:])
        result["donchian_lower"] = min(low[-20:])
        result["donchian_middle"] = (float(result["donchian_upper"]) + float(result["donchian_lower"])) / 2.0
        typical = [(h + l + c) / 3.0 for h, l, c in zip(high, low, close)]
        pv = [price * vol for price, vol in zip(typical, volume)]
        result["vwap_20"] = sum(pv[-20:]) / sum(volume[-20:]) if sum(volume[-20:]) else None
        money_flow_multiplier = [
            0.0 if h == l else ((c - l) - (h - c)) / (h - l)
            for h, l, c in zip(high, low, close)
        ]
        money_flow_volume = [multiplier * vol for multiplier, vol in zip(money_flow_multiplier, volume)]
        result["cmf_20"] = sum(money_flow_volume[-20:]) / sum(volume[-20:]) if sum(volume[-20:]) else None
    if len(close) >= 14:
        typical = [(h + l + c) / 3.0 for h, l, c in zip(high, low, close)]
        raw_flow = [price * vol for price, vol in zip(typical, volume)]
        positive = []
        negative = []
        for index, flow in enumerate(raw_flow):
            direction = 0 if index == 0 else (1 if typical[index] > typical[index - 1] else -1 if typical[index] < typical[index - 1] else 0)
            positive.append(flow if direction == 1 else 0.0)
            negative.append(flow if direction == -1 else 0.0)
        pos_sum = sum(positive[-14:])
        neg_sum = sum(negative[-14:])
        result["mfi_14"] = 100.0 if neg_sum == 0 and pos_sum > 0 else (0.0 if pos_sum == 0 else 100.0 - 100.0 / (1.0 + pos_sum / neg_sum))
    return result


def check_l5_moving_averages(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    fid = "get_l5_deterministic_snapshot"
    value = _indicator_value(_get_indicator(data_json, fid))
    if not isinstance(value, dict):
        return findings
    exact = value.get("exact_technical_values") if isinstance(value.get("exact_technical_values"), dict) else {}
    audit_input = _recompute_input(data_json, fid)
    raw_ohlcv = audit_input.get("raw_ohlcv") if isinstance(audit_input, dict) else None
    recomputed = _l5_recompute_values(raw_ohlcv) if isinstance(raw_ohlcv, list) else {}

    keys = ("sma_5", "sma_20", "sma_50", "sma_60", "sma_100", "sma_200") + L5_UNRECOMPUTABLE_TECHNICAL_KEYS
    for key in keys:
        category = "moving_average" if key.startswith("sma_") else "technical_indicator"
        field = f"{fid}.exact_technical_values.{key}"
        handled.add(field)
        note = f"independent stdlib recompute from audit-only raw_ohlcv; n={len(raw_ohlcv or [])}"
        if key not in recomputed or recomputed.get(key) is None:
            findings.append(_missing(field, category, CRITICALITY_STANDARD, note + "; input or recipe unavailable"))
            continue
        tolerance = 0.2 if key in {"adx_14", "pdi_14", "mdi_14"} else TOLERANCE_ROUNDED_2DP
        if key == "obv":
            tolerance = EPSILON_EXACT
        findings.append(_compare(field, exact.get(key), recomputed.get(key), tolerance,
                                  category, CRITICALITY_STANDARD, note))
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
            audit_input = _recompute_input(data_json, fid)
            rows = audit_input.get("raw_series") if isinstance(audit_input, dict) else None
            values = [
                float(row.get("value")) for row in (rows or [])
                if isinstance(row, dict) and _is_number(row.get("value"))
            ]
            note = f"independent difference from audit-only raw_series; n={len(values)}"
            if len(values) < 3:
                findings.append(_missing(field, "growth_rate", CRITICALITY_STANDARD, note + "; fewer than 3 values"))
                continue
            velocity = values[-1] - values[-2]
            acceleration = velocity - (values[-2] - values[-3])
            recomputed = velocity if sub_key == "velocity_1d" else acceleration if sub_key == "acceleration_1d" else None
            if recomputed is None:
                findings.append(_uncovered(field, "growth_rate", note + "; unsupported momentum subfield"))
                continue
            findings.append(_compare(field, sub_value, recomputed, TOLERANCE_ROUNDED_4DP,
                                     "growth_rate", CRITICALITY_STANDARD, note))
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


def _years_before(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _parse_observation_date(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def check_audit_value_series_percentiles(data_json: Dict[str, Any], handled: Set[str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    indicators = data_json.get("indicators") if isinstance(data_json, dict) else None
    if not isinstance(indicators, list):
        return findings
    for item in indicators:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("function_id") or "unknown_function")
        value = _indicator_value(item)
        audit_input = _recompute_input(data_json, fid)
        rows = audit_input.get("raw_series") if isinstance(audit_input, dict) else None
        if value is None or not isinstance(rows, list):
            continue
        observations: List[Tuple[datetime, float]] = []
        for row in rows:
            if not isinstance(row, dict) or not _is_number(row.get("value")):
                continue
            parsed = _parse_observation_date(row.get("date") or row.get("data_date"))
            if parsed is not None:
                observations.append((parsed, float(row["value"])))
        observations.sort(key=lambda pair: pair[0])
        if not observations:
            continue
        anchor = observations[-1][0]
        current = observations[-1][1]
        history_years = max((anchor - observations[0][0]).days / 365.25, 0.0)
        percentile_contract = audit_input.get("percentile_contract") if isinstance(audit_input.get("percentile_contract"), dict) else {}
        for field, pipeline_value, _parent in _walk_numeric_leaves(value, fid):
            key = field.rsplit(".", 1)[-1].lower()
            if "percentile" not in key or field in handled:
                continue
            window = 1 if "1y" in key else 5 if "5y" in key else 10 if "10y" in key else None
            if window is None:
                continue
            handled.add(field)
            declared_scale = str(percentile_contract.get("scale") or "")
            scale_100 = declared_scale == "0_100" or (not declared_scale and abs(float(pipeline_value)) > 1.0)
            if scale_100 and window == 10:
                if history_years < 9.5:
                    findings.append(_missing(field, "percentile", CRITICALITY_STANDARD,
                                             f"raw history {history_years:.1f}y is below pipeline 9.5y minimum"))
                    continue
                selected = observations
            else:
                cutoff = _years_before(anchor, window)
                selected = [pair for pair in observations if pair[0] >= cutoff]
                if scale_100 and window == 1 and len(selected) < 3:
                    selected = observations
            values = [pair[1] for pair in selected]
            if not values:
                findings.append(_missing(field, "percentile", CRITICALITY_STANDARD, "no dated values inside requested window"))
                continue
            strict_less = str(percentile_contract.get("comparison") or "") == "strict_less" or (not percentile_contract and scale_100)
            count = sum(1 for candidate in values if candidate < current) if strict_less else sum(1 for candidate in values if candidate <= current)
            recomputed = count / len(values) * (100.0 if scale_100 else 1.0)
            tolerance = 0.06 if scale_100 else 0.0006
            findings.append(_compare(
                field,
                pipeline_value,
                recomputed,
                tolerance,
                "percentile",
                CRITICALITY_STANDARD,
                f"audit raw_series window={window}y n={len(values)} comparison={'<' if strict_less else '<='}",
            ))
    return findings


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
    findings.extend(check_vix_term_structure_percentile(data_json, handled))
    findings.extend(check_fed_funds_rate_path(data_json, handled))
    findings.extend(check_net_liquidity(data_json, handled))
    findings.extend(check_m7_capex_cycle_magnitude(data_json, handled))
    findings.extend(check_m7_earnings_blackout_calendar(data_json, handled))
    findings.extend(check_m7_buyback_flow(data_json, handled))
    findings.extend(check_cross_indicator_ratios(data_json, handled))
    findings.extend(check_ma_deviation_family(data_json, handled))
    findings.extend(check_l5_moving_averages(data_json, handled))
    findings.extend(check_multi_scale_ma_position(data_json, handled))
    findings.extend(check_momentum_fields(data_json, handled))
    findings.extend(check_audit_value_series_percentiles(data_json, handled))
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
