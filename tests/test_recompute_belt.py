import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import recompute_belt as rb
from core.checker import DataIntegrity


def _damodaran_indicator(percentile_10y, current_value=5.0):
    """Minimal but structurally real get_damodaran_us_implied_erp payload:
    10 monthly observations 1..10, current=5 -> true rank percentile is
    count(v<=5)/10*100 = 50.0. Callers can pass a wrong `percentile_10y` to
    simulate a tampered/buggy pipeline value."""
    monthly_series = [
        {"data_date": f"2025-{month:02d}-01", "erp_t12m_adjusted_payout": float(month)}
        for month in range(1, 11)
    ]
    return {
        "layer": 4,
        "function_id": "get_damodaran_us_implied_erp",
        "metric_name": "Damodaran US Implied ERP Reference",
        "raw_data": {
            "value": {
                "monthly_series": monthly_series,
                "damodaran_erp_historical_percentiles": {
                    "primary_field": "erp_t12m_adjusted_payout",
                    "windows": {
                        "10y": {
                            "current_value": current_value,
                            "percentile": percentile_10y,
                            "sample_count": 10,
                            "window_start": "2025-01-01",
                            "window_end": "2025-10-01",
                        }
                    },
                },
                "damodaran_erp_percentile_10y": percentile_10y,
            }
        },
    }


def _net_liquidity_indicator(fed_assets, tga, rrp, level=None, unit="billion_usd"):
    level_value = level if level is not None else fed_assets - tga - rrp
    return {
        "layer": 1,
        "function_id": "get_net_liquidity_momentum",
        "metric_name": "Net Liquidity (Fed - TGA - RRP)",
        "raw_data": {
            "value": {
                "level": level_value,
                "level_unit": unit,
                "components": {"fed_assets": fed_assets, "tga": tga, "rrp": rrp},
                "components_unit": unit,
                "component_units": {"fed_assets": unit, "tga": unit, "rrp": unit},
            }
        },
    }


def _ma_deviation_indicator(function_id, level, ma, deviation_pct):
    return {
        "layer": 1,
        "function_id": function_id,
        "metric_name": function_id,
        "raw_data": {"value": {"level": level, "ma": ma, "deviation_pct": deviation_pct}},
    }


# ---------------------------------------------------------------------------
# 1. match: raw-series percentile recompute agrees with the pipeline value
# ---------------------------------------------------------------------------

def test_damodaran_percentile_match_against_hand_verified_reference():
    data = {"indicators": [_damodaran_indicator(percentile_10y=50.0)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    key = "get_damodaran_us_implied_erp.damodaran_erp_historical_percentiles.windows.10y.percentile"
    assert findings[key]["status"] == "match"
    assert findings[key]["recomputed_value"] == 50.0
    assert findings[key]["pipeline_value"] == 50.0
    assert findings[key]["criticality"] == "critical"


# ---------------------------------------------------------------------------
# 2. deviation: a wrong percentile is caught with both books' numbers surfaced
# ---------------------------------------------------------------------------

def test_damodaran_percentile_deviation_is_flagged_with_both_values():
    data = {"indicators": [_damodaran_indicator(percentile_10y=99.9)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    key = "get_damodaran_us_implied_erp.damodaran_erp_historical_percentiles.windows.10y.percentile"
    finding = findings[key]
    assert finding["status"] == "deviation"
    assert finding["pipeline_value"] == 99.9
    assert finding["recomputed_value"] == 50.0
    assert finding["criticality"] == "critical"
    assert report["deviations"] >= 1
    assert report["critical_deviation_count"] >= 1


# ---------------------------------------------------------------------------
# 3. unrecomputable_missing_raw: percentile field with no embedded raw series
# ---------------------------------------------------------------------------

def test_percentile_without_raw_series_is_honestly_missing_raw():
    data = {
        "indicators": [
            {
                "layer": 1,
                "function_id": "get_fed_funds_rate",
                "metric_name": "Fed Funds Rate",
                "raw_data": {
                    "value": {
                        "level": 3.63,
                        "relativity": {"percentile_1y": 75.6, "percentile_10y": 75.6},
                    }
                },
            }
        ]
    }
    report = rb.run(data)
    findings = [f for f in report["findings"] if f["field"].startswith("get_fed_funds_rate.relativity.percentile")]
    assert len(findings) == 2
    for finding in findings:
        assert finding["status"] == "unrecomputable_missing_raw"
        assert finding["pipeline_value"] is None
        assert finding["recomputed_value"] is None
    # never silently dropped -- coverage math accounts for the gap honestly
    assert report["unrecomputable_missing_raw"] >= 2
    assert report["coverage_ratio"] < 1.0


# ---------------------------------------------------------------------------
# 4. unit/magnitude sentinel: billion vs million mixup caught even when the
#    subtraction formula itself stays internally consistent
# ---------------------------------------------------------------------------

def test_net_liquidity_magnitude_sentinel_catches_unit_mixup():
    # fed_assets reported in millions (6,735,610) but labeled billion_usd --
    # mirrors the historical incident cited in WORK_ORDERS.md item 3. The
    # subtraction formula is self-consistent (level derived from the same
    # tampered fed_assets), so the ratio/diff check alone would not catch it.
    data = {"indicators": [_net_liquidity_indicator(fed_assets=6735610.0, tga=774.06, rrp=5.77)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}

    formula_finding = findings["get_net_liquidity_momentum.level"]
    assert formula_finding["status"] == "match"  # internally consistent, formula alone is blind to the bug

    sentinel_finding = findings["get_net_liquidity_momentum.magnitude_sentinel.fed_assets"]
    assert sentinel_finding["status"] == "deviation"
    assert sentinel_finding["criticality"] == "critical"
    assert "OUTSIDE PLAUSIBLE BAND" in sentinel_finding["note"]


def test_net_liquidity_magnitude_sentinel_passes_for_plausible_values():
    data = {"indicators": [_net_liquidity_indicator(fed_assets=6735.61, tga=774.06, rrp=5.77)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    assert findings["get_net_liquidity_momentum.magnitude_sentinel.fed_assets"]["status"] == "match"
    assert findings["get_net_liquidity_momentum.level"]["status"] == "match"
    assert findings["get_net_liquidity_momentum.unit_labels"]["status"] == "match"


def test_net_liquidity_unit_label_mismatch_is_flagged():
    indicator = _net_liquidity_indicator(fed_assets=6735.61, tga=774.06, rrp=5.77)
    indicator["raw_data"]["value"]["component_units"]["fed_assets"] = "million_usd"
    report = rb.run({"indicators": [indicator]})
    findings = {f["field"]: f for f in report["findings"]}
    assert findings["get_net_liquidity_momentum.unit_labels"]["status"] == "deviation"


def _m7_capex_indicator(latest_quarter_value_bn, aggregate_sum_bn):
    return {
        "layer": 4,
        "function_id": "get_m7_capex_cycle",
        "metric_name": "M7 / Hyperscaler Capex Cycle",
        "raw_data": {
            "value": {
                "companies": {
                    "AAPL": {
                        "quarters": [
                            {"calendar_quarter": "2025Q4", "period_end": "2025-12-31", "value_usd_bn": latest_quarter_value_bn}
                        ]
                    }
                },
                "m7_aggregate": {
                    "latest_covered_quarter": {"calendar_quarter": "2025Q4", "sum_usd_bn": aggregate_sum_bn}
                },
            }
        },
    }


def test_m7_capex_magnitude_sentinel_passes_for_plausible_values():
    data = {"indicators": [_m7_capex_indicator(latest_quarter_value_bn=18.0, aggregate_sum_bn=80.0)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    assert findings["get_m7_capex_cycle.magnitude_sentinel.AAPL.latest_quarter"]["status"] == "match"
    assert findings["get_m7_capex_cycle.magnitude_sentinel.m7_aggregate.latest_covered_quarter"]["status"] == "match"


def test_m7_capex_magnitude_sentinel_catches_unit_mixup():
    # 18000.0 "billion" would actually be a thousand-fold unit mixup (e.g. a
    # million-USD value mislabeled as billions); combined M7 quarterly capex
    # has never been anywhere near $18,000bn.
    data = {"indicators": [_m7_capex_indicator(latest_quarter_value_bn=18000.0, aggregate_sum_bn=80.0)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    sentinel = findings["get_m7_capex_cycle.magnitude_sentinel.AAPL.latest_quarter"]
    assert sentinel["status"] == "deviation"
    assert sentinel["criticality"] == "standard"
    assert "OUTSIDE PLAUSIBLE BAND" in sentinel["note"]


def test_m7_capex_magnitude_sentinel_missing_indicator_is_honestly_missing():
    report = rb.run({"indicators": []})
    findings = {f["field"]: f for f in report["findings"]}
    assert findings["get_m7_capex_cycle.companies"]["status"] == "unrecomputable_missing_raw"


# ---------------------------------------------------------------------------
# 4b. VIX term structure (get_vix_term_structure): percentile recompute from
# the embedded raw ratio series, plus an intra-payload ratio consistency
# check (vix3m.level / vix.level == level). Added for
# investigation_reports/20260711_first_principles/WORK_ORDERS.md item 4, task A.
# ---------------------------------------------------------------------------

def _vix_term_structure_indicator(pipeline_percentile_10y, current_value=0.5, window_status="available"):
    """Minimal but structurally real get_vix_term_structure payload: 10 monthly
    ratio observations 0.1..1.0, current=0.5 -> true rank percentile is
    count(v<=0.5)/10*100 = 50.0 (mirrors _damodaran_indicator's construction
    so the expected numbers are easy to hand-verify)."""
    raw_series = [
        {
            "data_date": f"2025-{month:02d}-01",
            "vix": 20.0,
            "vix3m": round(20.0 * (month / 10.0), 4),
            "ratio_vix3m_over_vix": round(month / 10.0, 4),
        }
        for month in range(1, 11)
    ]
    vix3m_level = round(20.0 * current_value, 4)
    return {
        "layer": 2,
        "function_id": "get_vix_term_structure",
        "metric_name": "VIX Term Structure (VIX3M/VIX)",
        "raw_data": {
            "value": {
                "level": current_value,
                "vix": {"level": 20.0, "date": "2025-10-01"},
                "vix3m": {"level": vix3m_level, "date": "2025-10-01"},
                "percentile_context": {
                    "primary_field": "ratio_vix3m_over_vix",
                    "windows": {
                        "10y": {
                            "current_value": current_value,
                            "percentile": pipeline_percentile_10y,
                            "sample_count": 10,
                            "window_start": "2025-01-01",
                            "window_end": "2025-10-01",
                            "status": window_status,
                        }
                    },
                    "raw_series": raw_series,
                },
                "percentile_10y": pipeline_percentile_10y,
            }
        },
    }


def test_vix_term_structure_percentile_match_against_hand_verified_reference():
    data = {"indicators": [_vix_term_structure_indicator(pipeline_percentile_10y=50.0)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    key = "get_vix_term_structure.percentile_context.windows.10y.percentile"
    assert findings[key]["status"] == "match"
    assert findings[key]["recomputed_value"] == 50.0
    assert findings[key]["pipeline_value"] == 50.0
    assert findings[key]["criticality"] == "standard"


def test_vix_term_structure_percentile_deviation_is_flagged_with_both_values():
    data = {"indicators": [_vix_term_structure_indicator(pipeline_percentile_10y=99.9)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    key = "get_vix_term_structure.percentile_context.windows.10y.percentile"
    finding = findings[key]
    assert finding["status"] == "deviation"
    assert finding["pipeline_value"] == 99.9
    assert finding["recomputed_value"] == 50.0
    assert report["deviations"] >= 1


def test_vix_term_structure_percentile_insufficient_history_agreement_is_match():
    data = {"indicators": [_vix_term_structure_indicator(
        pipeline_percentile_10y=None, window_status="insufficient_history",
    )]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    key = "get_vix_term_structure.percentile_context.windows.10y.percentile"
    assert findings[key]["status"] == "match"
    assert findings[key]["recomputed_value"] is None


def test_vix_term_structure_ratio_cross_check_matches_intra_payload_legs():
    data = {"indicators": [_vix_term_structure_indicator(pipeline_percentile_10y=50.0, current_value=0.5)]}
    report = rb.run(data)
    findings = {f["field"]: f for f in report["findings"]}
    key = "get_vix_term_structure.level"
    assert findings[key]["status"] == "match"
    assert findings[key]["recomputed_value"] == 0.5


def test_vix_term_structure_ratio_cross_check_catches_tampered_level():
    fixture = _vix_term_structure_indicator(pipeline_percentile_10y=50.0, current_value=0.5)
    fixture["raw_data"]["value"]["level"] = 9.99  # tampered, no longer matches vix3m.level/vix.level
    report = rb.run({"indicators": [fixture]})
    findings = {f["field"]: f for f in report["findings"]}
    key = "get_vix_term_structure.level"
    assert findings[key]["status"] == "deviation"
    assert findings[key]["pipeline_value"] == 9.99
    assert findings[key]["recomputed_value"] == 0.5


# ---------------------------------------------------------------------------
# 4c. Fed funds futures reduced path: implied rates, slope and priced cuts
# independently rebuilt from embedded per-contract close/volume observations.
# ---------------------------------------------------------------------------

def _fed_funds_rate_path_indicator(qualified_months=5):
    raw_series = []
    path = []
    for months_ahead in range(qualified_months):
        contract = f"ZQ_TEST_{months_ahead}"
        close = round(96.0 + months_ahead * 0.1, 4)
        raw_series.append({
            "months_ahead": months_ahead,
            "contract": contract,
            "observations": [
                {"data_date": "2026-07-09", "close": close - 0.01, "volume": 200.0},
                {"data_date": "2026-07-10", "close": close, "volume": 200.0},
            ],
        })
        path.append({
            "months_ahead": months_ahead,
            "contract": contract,
            "implied_rate": round(100.0 - close, 4),
        })
    status = "available" if qualified_months >= 4 else "insufficient_curve"
    slope = round(path[-1]["implied_rate"] - path[0]["implied_rate"], 4) if status == "available" else None
    cuts = round(-slope * 100) if slope is not None else None
    return {
        "layer": 1,
        "function_id": "get_fed_funds_rate_path",
        "metric_name": "Fed Funds Futures Implied Rate Path",
        "raw_data": {
            "value": {
                "effective_date": "2026-07-10",
                "status": status,
                "path": path,
                "slope_12m": slope,
                "cuts_priced_bps": cuts,
                "horizon_used": {
                    "actual_months_ahead": path[-1]["months_ahead"],
                },
                "liquidity_thresholds": {
                    "negligible_below_avg_volume_10d": 5.0,
                    "thin_below_avg_volume_10d": 100.0,
                },
                "raw_series": raw_series,
            }
        },
    }


def test_fed_funds_rate_path_recompute_matches_implied_slope_and_cuts():
    report = rb.run({"indicators": [_fed_funds_rate_path_indicator()]})
    findings = {finding["field"]: finding for finding in report["findings"]}

    assert findings["get_fed_funds_rate_path.path.ZQ_TEST_2.implied_rate"]["status"] == "match"
    assert round(findings["get_fed_funds_rate_path.path.ZQ_TEST_2.implied_rate"]["recomputed_value"], 4) == 3.8
    assert findings["get_fed_funds_rate_path.slope_12m"]["status"] == "match"
    assert round(findings["get_fed_funds_rate_path.slope_12m"]["recomputed_value"], 4) == -0.4
    assert findings["get_fed_funds_rate_path.cuts_priced_bps"]["status"] == "match"
    assert findings["get_fed_funds_rate_path.cuts_priced_bps"]["recomputed_value"] == 40


def test_fed_funds_rate_path_recompute_catches_tampered_slope():
    fixture = _fed_funds_rate_path_indicator()
    fixture["raw_data"]["value"]["slope_12m"] = 9.99
    report = rb.run({"indicators": [fixture]})
    finding = {item["field"]: item for item in report["findings"]}["get_fed_funds_rate_path.slope_12m"]

    assert finding["status"] == "deviation"
    assert finding["pipeline_value"] == 9.99
    assert round(finding["recomputed_value"], 4) == -0.4


def test_fed_funds_rate_path_recompute_catches_tampered_month_implied_rate():
    fixture = _fed_funds_rate_path_indicator()
    fixture["raw_data"]["value"]["path"][2]["implied_rate"] = 8.88
    report = rb.run({"indicators": [fixture]})
    finding = {item["field"]: item for item in report["findings"]}[
        "get_fed_funds_rate_path.path.ZQ_TEST_2.implied_rate"
    ]

    assert finding["status"] == "deviation"
    assert finding["pipeline_value"] == 8.88
    assert round(finding["recomputed_value"], 4) == 3.8


def test_fed_funds_rate_path_recompute_catches_tampered_liquidity_threshold():
    fixture = _fed_funds_rate_path_indicator()
    fixture["raw_data"]["value"]["liquidity_thresholds"]["negligible_below_avg_volume_10d"] = 999.0
    report = rb.run({"indicators": [fixture]})
    finding = {item["field"]: item for item in report["findings"]}[
        "get_fed_funds_rate_path.liquidity_thresholds.negligible_below_avg_volume_10d"
    ]

    assert finding["status"] == "deviation"
    assert finding["pipeline_value"] == 999.0
    assert finding["recomputed_value"] == 5.0


def test_fed_funds_rate_path_insufficient_curve_agreement_is_match():
    report = rb.run({"indicators": [_fed_funds_rate_path_indicator(qualified_months=3)]})
    findings = {finding["field"]: finding for finding in report["findings"]}

    assert findings["get_fed_funds_rate_path.status"]["status"] == "match"
    assert findings["get_fed_funds_rate_path.status"]["recomputed_value"] == "insufficient_curve"
    assert findings["get_fed_funds_rate_path.slope_12m"]["status"] == "match"
    assert findings["get_fed_funds_rate_path.cuts_priced_bps"]["status"] == "match"


# ---------------------------------------------------------------------------
# 5. checker.py hard-gate integration: critical deviations block publish,
#    non-critical ones do not (criticality tiering avoids over-blocking)
# ---------------------------------------------------------------------------

def test_checker_hard_blocks_on_critical_recompute_deviation():
    data = {
        "backtest_date": None,
        "indicators": [_damodaran_indicator(percentile_10y=99.9)],
    }
    report = DataIntegrity().run(data)
    assert report["publish_status"] == "blocked"
    assert any(reason.startswith("recompute_belt_critical_deviation") for reason in report["blocking_reasons"])
    assert report["recompute_belt"]["critical_deviation_count"] >= 1


def test_checker_does_not_block_on_standard_criticality_deviation():
    # deviation_pct is a "standard" criticality ratio check -- a small
    # deliberate mismatch here must not trip the recompute hard gate, per
    # WORK_ORDERS.md item 3's "按字段关键性分级，避免非关键小偏差误伤发布".
    data = {
        "backtest_date": None,
        "indicators": [_ma_deviation_indicator("get_10y_treasury", level=4.56, ma=4.472, deviation_pct=999.0)],
    }
    report = DataIntegrity().run(data)
    recompute_findings = {f["field"]: f for f in report["recompute_belt"]["findings"]}
    assert recompute_findings["get_10y_treasury.deviation_pct"]["status"] == "deviation"
    assert recompute_findings["get_10y_treasury.deviation_pct"]["criticality"] == "standard"
    assert not any(reason.startswith("recompute_belt_critical_deviation") for reason in report["blocking_reasons"])


def test_checker_recompute_belt_toggle_disables_hard_gate():
    data = {
        "backtest_date": None,
        "indicators": [_damodaran_indicator(percentile_10y=99.9)],
    }

    class _ToggledOff(DataIntegrity):
        RECOMPUTE_BELT_ENABLED = False

    report = _ToggledOff().run(data)
    # report still computed and surfaced for audit, but does not gate publish
    assert report["recompute_belt"]["critical_deviation_count"] >= 1
    assert not any(reason.startswith("recompute_belt_critical_deviation") for reason in report["blocking_reasons"])


def test_checker_survives_recompute_belt_crash_without_blocking(monkeypatch):
    # 校验带自身崩溃是带的 bug，不是数据被污染的证据：闸门必须存活、
    # 不因此拦截发布，但要在 notes 里留下修带信号。
    import core.checker as checker_module

    def _boom(_data_json):
        raise RuntimeError("synthetic belt crash")

    monkeypatch.setattr(checker_module, "run_recompute_belt", _boom)
    data = {
        "backtest_date": None,
        "indicators": [_net_liquidity_indicator(fed_assets=6735.61, tga=774.06, rrp=5.77)],
    }
    report = DataIntegrity().run(data)
    assert report["recompute_belt"]["status"] == "error"
    assert not any(reason.startswith("recompute_belt_critical_deviation") for reason in report["blocking_reasons"])
    assert "独立重算校验带运行失败" in report.get("notes", "")


def test_checker_clean_snapshot_has_no_recompute_blocking_reason():
    data = {
        "backtest_date": None,
        "indicators": [
            _damodaran_indicator(percentile_10y=50.0),
            _net_liquidity_indicator(fed_assets=6735.61, tga=774.06, rrp=5.77),
        ],
    }
    report = DataIntegrity().run(data)
    assert not any(reason.startswith("recompute_belt_critical_deviation") for reason in report["blocking_reasons"])
    assert report["recompute_belt"]["critical_deviation_count"] == 0
