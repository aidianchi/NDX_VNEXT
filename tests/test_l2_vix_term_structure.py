import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd

import tools_L1
from data_evidence import data_evidence_issues


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _series(dates, values):
    return pd.DataFrame({"date": [pd.to_datetime(d) for d in dates], "value": list(values)})


def _daily_dates(start, n):
    start_dt = date.fromisoformat(start)
    return [(start_dt + timedelta(days=i)).isoformat() for i in range(n)]


def _fake_get_series_for_effective_date(vix_df, vix3m_df, vix6m_df):
    frames = {"VIX": vix_df, "VIX3M": vix3m_df, "VIX6M": vix6m_df}

    def fake(series_id, update_func, end_date):
        return frames[series_id].copy()

    return fake


SMALL_WINDOWS = {
    "5y": {"years": 5, "min_observations": 20, "min_span_days": 10},
    "10y": {"years": 10, "min_observations": 20, "min_span_days": 10},
}


# ---------------------------------------------------------------------------
# 1. state classification band, including the documented flat buffer
# ---------------------------------------------------------------------------

def test_term_structure_state_classification_bands():
    assert tools_L1._vix_term_structure_state(1.10) == "contango"
    assert tools_L1._vix_term_structure_state(1.005) == "contango"
    assert tools_L1._vix_term_structure_state(1.004) == "flat"
    assert tools_L1._vix_term_structure_state(1.0) == "flat"
    assert tools_L1._vix_term_structure_state(0.996) == "flat"
    assert tools_L1._vix_term_structure_state(0.995) == "backwardation"
    assert tools_L1._vix_term_structure_state(0.80) == "backwardation"
    assert tools_L1._vix_term_structure_state(None) == "unavailable"


# ---------------------------------------------------------------------------
# 2. percentile window helper: hand-verified rank percentile + honest
#    insufficient_history degrade (no extrapolation past the raw sample)
# ---------------------------------------------------------------------------

def test_percentile_window_available_matches_hand_computed_rank():
    dates = _daily_dates("2020-01-01", 100)
    ratios = [round((i + 1) / 100.0, 4) for i in range(100)]  # 0.01 .. 1.00 ascending
    merged = pd.DataFrame({"date": [pd.to_datetime(d) for d in dates], "ratio_vix3m_over_vix": ratios})
    anchor = merged["date"].iloc[-1]

    result_max = tools_L1._vix_term_structure_percentile_window(
        merged, anchor=anchor, years=5, current_value=ratios[-1], min_observations=50, min_span_days=30,
    )
    assert result_max["status"] == "available"
    assert result_max["percentile"] == 100.0
    assert result_max["sample_count"] == 100

    median_value = ratios[49]  # 0.50 -> exactly 50 of 100 values are <= 0.50
    result_median = tools_L1._vix_term_structure_percentile_window(
        merged, anchor=anchor, years=5, current_value=median_value, min_observations=50, min_span_days=30,
    )
    assert result_median["percentile"] == 50.0


def test_percentile_window_insufficient_history_is_honest_not_extrapolated():
    dates = _daily_dates("2026-01-01", 10)
    merged = pd.DataFrame({"date": [pd.to_datetime(d) for d in dates], "ratio_vix3m_over_vix": [1.0] * 10})
    anchor = merged["date"].iloc[-1]

    result = tools_L1._vix_term_structure_percentile_window(
        merged, anchor=anchor, years=5, current_value=1.0, min_observations=750, min_span_days=1460,
    )
    assert result["status"] == "insufficient_history"
    assert result["percentile"] is None
    assert "requires >=" in result["reason"]


# ---------------------------------------------------------------------------
# 3. end-to-end contract: contango case, full data_quality/metric_authority
# ---------------------------------------------------------------------------

def test_get_vix_term_structure_full_contract_and_contango_state(monkeypatch):
    n = 40
    dates = _daily_dates("2024-01-01", n)
    vix_values = [20.0] * n
    vix3m_values = [20.0 + i * 0.05 for i in range(n)]  # strictly increasing -> last value is the running max
    vix_df = _series(dates, vix_values)
    vix3m_df = _series(dates, vix3m_values)
    vix6m_df = _series(dates, [22.0 + i * 0.05 for i in range(n)])

    monkeypatch.setattr(
        tools_L1, "_get_series_for_effective_date",
        _fake_get_series_for_effective_date(vix_df, vix3m_df, vix6m_df),
    )
    monkeypatch.setattr(tools_L1, "VIX_TERM_STRUCTURE_PERCENTILE_WINDOWS", SMALL_WINDOWS)

    result = tools_L1.get_vix_term_structure(end_date=None)

    assert result["availability"] == "available"
    v = result["value"]
    assert v["term_structure_state"] == "contango"
    assert v["level"] == round(vix3m_values[-1] / vix_values[-1], 4)
    assert v["percentile_5y"] == 100.0  # current is the running max of a monotonic ramp
    assert v["percentile_10y"] == 100.0
    assert v["vix6m"]["availability"] == "available"
    assert v["state_usage_boundary"]["contango"]["usage"] == "not_bullish_evidence"

    dq = result["data_quality"]
    assert dq["contract_version"] == "data_evidence_v1"
    assert dq["source_tier"] == "third_party_estimate"
    assert dq["metric_authority"]["term_structure_state"]["usage"] == "supporting_only"
    assert dq["metric_authority"]["term_structure_state"]["authority"] == "asymmetric_risk_signal_only"

    issues = data_evidence_issues(result, function_id="get_vix_term_structure")
    assert issues["hard_block"] == []


# ---------------------------------------------------------------------------
# 4. backwardation case + missing VIX6M must not block the primary ratio
# ---------------------------------------------------------------------------

def test_get_vix_term_structure_detects_backwardation_and_handles_missing_vix6m(monkeypatch):
    n = 30
    dates = _daily_dates("2024-01-01", n)
    vix_values = [30.0 + i * 0.2 for i in range(n)]   # panic leg rising fast
    vix3m_values = [25.0 + i * 0.1 for i in range(n)]  # rising slower -> ratio ends < 1
    vix_df = _series(dates, vix_values)
    vix3m_df = _series(dates, vix3m_values)
    empty_vix6m = pd.DataFrame(columns=["date", "value"])

    monkeypatch.setattr(
        tools_L1, "_get_series_for_effective_date",
        _fake_get_series_for_effective_date(vix_df, vix3m_df, empty_vix6m),
    )
    monkeypatch.setattr(tools_L1, "VIX_TERM_STRUCTURE_PERCENTILE_WINDOWS", SMALL_WINDOWS)

    result = tools_L1.get_vix_term_structure(end_date=None)

    v = result["value"]
    last_ratio = vix3m_values[-1] / vix_values[-1]
    assert last_ratio < 1.0
    assert v["term_structure_state"] == "backwardation"
    assert v["vix6m"]["availability"] == "unavailable"
    assert v["state_usage_boundary"]["backwardation"]["usage"] == "supporting_only"
    assert result["availability"] == "available"

    issues = data_evidence_issues(result, function_id="get_vix_term_structure")
    assert issues["hard_block"] == []


# ---------------------------------------------------------------------------
# 5. point-in-time backtest truncation: future rows leaking from the fetch
#    layer must not reach the payload, even if the fetch stub over-supplies.
# ---------------------------------------------------------------------------

def test_get_vix_term_structure_respects_point_in_time_effective_date(monkeypatch):
    n = 30
    dates = _daily_dates("2024-01-01", n)  # runs through 2024-01-30
    vix_values = [20.0] * n
    vix3m_values = [20.0 + i * 0.1 for i in range(n)]
    vix_df = _series(dates, vix_values)
    vix3m_df = _series(dates, vix3m_values)
    vix6m_df = pd.DataFrame(columns=["date", "value"])

    monkeypatch.setattr(
        tools_L1, "_get_series_for_effective_date",
        _fake_get_series_for_effective_date(vix_df, vix3m_df, vix6m_df),
    )
    monkeypatch.setattr(tools_L1, "VIX_TERM_STRUCTURE_PERCENTILE_WINDOWS", {
        "5y": {"years": 5, "min_observations": 5, "min_span_days": 5},
        "10y": {"years": 10, "min_observations": 5, "min_span_days": 5},
    })

    cutoff = "2024-01-15"
    result = tools_L1.get_vix_term_structure(end_date=cutoff)

    v = result["value"]
    assert v["date"] <= cutoff
    for row in v["percentile_context"]["raw_series"]:
        assert row["data_date"] <= cutoff

    expected_index = 14  # 2024-01-01 + 14 days = 2024-01-15
    expected_ratio = round(vix3m_values[expected_index] / vix_values[expected_index], 4)
    assert v["level"] == expected_ratio


# ---------------------------------------------------------------------------
# 6. missing primary legs degrade honestly to unavailable, not a crash/guess
# ---------------------------------------------------------------------------

def test_get_vix_term_structure_unavailable_when_no_overlapping_dates(monkeypatch):
    vix_df = _series(_daily_dates("2024-01-01", 10), [20.0] * 10)
    vix3m_df = _series(_daily_dates("2025-01-01", 10), [21.0] * 10)  # no overlapping trading dates
    vix6m_df = pd.DataFrame(columns=["date", "value"])

    monkeypatch.setattr(
        tools_L1, "_get_series_for_effective_date",
        _fake_get_series_for_effective_date(vix_df, vix3m_df, vix6m_df),
    )

    result = tools_L1.get_vix_term_structure(end_date=None)
    assert result["availability"] == "unavailable"
    assert result["value"] is None
    assert "unavailable_reason" in result
