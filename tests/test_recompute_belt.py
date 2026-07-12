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
