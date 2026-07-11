import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.checker import DataIntegrity


def test_data_integrity_all_success():
    data = {
        "indicators": [
            {"function_id": "get_fed_funds_rate", "metric_name": "Fed Funds", "value": 5.25},
            {"function_id": "get_vix", "metric_name": "VIX", "value": 18.0},
        ]
    }
    report = DataIntegrity().run(data)
    assert report["confidence_percent"] == 100.0
    assert "所有采集指标均返回有效值" in report["notes"]


def test_data_integrity_some_failures():
    data = {
        "indicators": [
            {"function_id": "get_fed_funds_rate", "metric_name": "Fed Funds", "value": 5.25},
            {"function_id": "get_vix", "metric_name": "VIX", "error": "Timeout"},
            {"function_id": "get_adx", "metric_name": "ADX", "error": "Missing"},
        ]
    }
    report = DataIntegrity().run(data)
    assert report["confidence_percent"] == 33.3
    assert "2 个指标采集失败" in report["notes"]
    assert "示例: VIX, ADX" in report["notes"]
    assert "数据完整性偏低" in report["notes"]


def test_data_integrity_blocks_publish_when_confidence_below_floor():
    data = {
        "indicators": [
            {"layer": 1, "function_id": "get_fed_funds_rate", "metric_name": "Fed Funds", "value": 5.25},
            {"layer": 1, "function_id": "get_10y", "metric_name": "10Y", "value": 4.2},
            {"layer": 2, "function_id": "get_vix", "metric_name": "VIX", "error": "Timeout"},
            {"layer": 3, "function_id": "get_breadth", "metric_name": "Breadth", "error": "Missing"},
            {"layer": 5, "function_id": "get_adx", "metric_name": "ADX", "error": "Missing"},
        ]
    }

    report = DataIntegrity().run(data)

    assert report["publish_status"] == "blocked"
    assert any("low_data_integrity_confidence" in reason for reason in report["blocking_reasons"])


def test_data_integrity_blocks_publish_when_formal_layer_has_no_successes():
    data = {
        "indicators": [
            {"layer": 1, "function_id": "l1_a", "value": 1},
            {"layer": 1, "function_id": "l1_b", "value": 1},
            {"layer": 2, "function_id": "l2_a", "value": 1},
            {"layer": 2, "function_id": "l2_b", "value": 1},
            {"layer": 3, "function_id": "l3_a", "value": 1},
            {"layer": 4, "function_id": "l4_a", "value": 1},
            {"layer": 5, "function_id": "l5_a", "metric_name": "L5 A", "error": "Timeout"},
            {"layer": 5, "function_id": "l5_b", "metric_name": "L5 B", "error": "Timeout"},
            {"layer": 5, "function_id": "l5_c", "metric_name": "L5 C", "error": "Timeout"},
        ]
    }

    report = DataIntegrity().run(data)

    assert report["confidence_percent"] >= DataIntegrity.MIN_PUBLISH_CONFIDENCE_PERCENT
    assert report["publish_status"] == "blocked"
    assert any("critical_layer_no_success" in reason and "L5 success=0/3" in reason for reason in report["blocking_reasons"])


def test_data_integrity_blocks_when_one_formal_layer_is_below_half_even_if_overall_is_high():
    data = {
        "indicators": [
            {"layer": 1, "function_id": "l1_ok", "value": 1},
            {"layer": 1, "function_id": "l1_fail_a", "error": "missing"},
            {"layer": 1, "function_id": "l1_fail_b", "error": "missing"},
            {"layer": 2, "function_id": "l2_a", "value": 1},
            {"layer": 2, "function_id": "l2_b", "value": 1},
            {"layer": 2, "function_id": "l2_c", "value": 1},
            {"layer": 3, "function_id": "l3_a", "value": 1},
            {"layer": 3, "function_id": "l3_b", "value": 1},
            {"layer": 4, "function_id": "l4_a", "value": 1},
            {"layer": 5, "function_id": "l5_a", "value": 1},
        ]
    }

    report = DataIntegrity().run(data)

    assert report["confidence_percent"] == 80.0
    assert report["publish_status"] == "blocked"
    assert any("critical_layer_below_publish_floor" in reason and "L1 success=1/3" in reason for reason in report["blocking_reasons"])


def test_data_integrity_reports_yfinance_runtime_diagnostics():
    data = {
        "indicators": [
            {"function_id": "get_vix", "metric_name": "VIX", "value": 18.0},
        ],
        "runtime_diagnostics": {
            "yfinance": {
                "by_status": {"retry_scheduled": 2, "cache_fallback": 1, "failed": 1},
                "by_failure_type": {"rate_limited": 2, "sqlite_cache_error": 1},
                "total_backoff_seconds": 70,
            }
        },
    }
    report = DataIntegrity().run(data)
    assert "yfinance 运行诊断" in report["notes"]
    assert "retry=2" in report["notes"]
    assert report["runtime_diagnostics"]["yfinance"]["by_failure_type"]["sqlite_cache_error"] == 1


def test_data_integrity_empty_indicators():
    report = DataIntegrity().run({"indicators": []})
    assert report["confidence_percent"] == 0.0
    assert "所有采集指标均返回有效值" in report["notes"]


def test_data_integrity_missing_indicators_key():
    report = DataIntegrity().run({})
    assert report["confidence_percent"] == 0.0


def test_data_integrity_layer_breakdown():
    data = {
        "indicators": [
            {"layer": 1, "function_id": "get_fed_funds_rate", "value": 5.25},
            {"layer": 1, "function_id": "get_vix", "error": "Timeout"},
            {"layer": 2, "function_id": "get_adx", "value": 25.0},
        ]
    }
    report = DataIntegrity().run(data)
    breakdown = report["layer_breakdown"]
    assert "1" in breakdown
    assert "2" in breakdown
    assert breakdown["1"]["total"] == 2
    assert breakdown["1"]["success"] == 1
    assert breakdown["1"]["confidence"] == 50.0
    assert breakdown["2"]["confidence"] == 100.0


def test_data_integrity_third_party_checks():
    data = {
        "indicators": [
            {
                "layer": 4,
                "function_id": "get_ndx_pe",
                "raw_data": {
                    "value": {
                        "ThirdPartyChecks": [
                            {"source_name": "A", "availability": "available"},
                            {"source_name": "B", "availability": "unavailable"},
                        ]
                    }
                },
            },
            {
                "layer": 1,
                "function_id": "get_fed_funds_rate",
                "value": 5.25,
            },
        ]
    }
    report = DataIntegrity().run(data)
    tp = report["third_party_checks"]
    assert tp["total"] == 2
    assert tp["available"] == 1
    assert tp["confidence"] == 50.0


def test_data_integrity_reports_nonblocking_valuation_source_disagreement():
    data = {
        "indicators": [
            {
                "layer": 4,
                "function_id": "get_ndx_pe_and_earnings_yield",
                "metric_name": "NDX P/E and Earnings Yield",
                "raw_data": {
                    "value": {"PE": 33.3},
                    "data_quality": {
                        "source_disagreement_issues": [
                            {
                                "issue_type": "valuation_source_disagreement",
                                "metric": "PriceToBook",
                                "severity": "high",
                                "component_value": 41.18,
                                "reference_median": 10.02,
                                "relative_diff_pct": 311.0,
                                "blocks_publish": False,
                                "action": "reject_metric_from_core_evidence",
                            }
                        ]
                    },
                },
            }
        ]
    }

    report = DataIntegrity().run(data)

    assert report["publish_status"] == "publishable"
    assert report["quality_issues"][0]["metric"] == "PriceToBook"
    assert "估值源严重冲突" in report["notes"]


def test_data_integrity_blocks_publish_for_core_valuation_source_disagreement():
    data = {
        "indicators": [
            {
                "layer": 4,
                "function_id": "get_ndx_pe_and_earnings_yield",
                "metric_name": "NDX P/E and Earnings Yield",
                "raw_data": {
                    "value": {"PE": 70.0},
                    "data_quality": {
                        "source_disagreement_issues": [
                            {
                                "issue_type": "valuation_source_disagreement",
                                "metric": "PE",
                                "severity": "high",
                                "component_value": 70.0,
                                "reference_median": 34.0,
                                "relative_diff_pct": 105.9,
                                "blocks_publish": True,
                                "action": "block_publish_until_manual_or_official_override",
                            }
                        ]
                    },
                },
            }
        ]
    }

    report = DataIntegrity().run(data)

    assert report["blocked"] is True
    assert report["unpublishable"] is True
    assert report["publish_status"] == "blocked"
    assert any("valuation_source_disagreement" in reason for reason in report["blocking_reasons"])


def test_data_integrity_penalizes_skips_partial_coverage_and_future_dates():
    data = {
        "backtest_date": "2025-04-09",
        "indicators": [
            {
                "layer": 3,
                "function_id": "get_percent_above_ma",
                "metric_name": "Percent Above MA",
                "raw_data": {
                    "value": {"level": 40},
                    "data_quality": {"coverage": {"constituent_coverage_pct": 55.0}},
                },
            },
            {
                "layer": 2,
                "function_id": "get_cnn_fear_greed_index",
                "metric_name": "CNN FGI",
                "raw_data": {"value": {"score": 62.9, "data_date": "2026-05-15"}},
            },
            {
                "layer": 4,
                "function_id": "get_ndx_forward_earnings_quality",
                "metric_name": "Forward Earnings",
                "raw_data": {"value": None, "backtest_skipped": True},
                "error": "backtest_skipped_unsupported_function",
            },
        ],
    }

    report = DataIntegrity().run(data)

    assert report["confidence_percent"] < 100.0
    assert "覆盖率不足" in report["notes"]
    assert "晚于回测日" in report["notes"]
    assert "前瞻风险被跳过" in report["notes"]


def test_data_integrity_recursively_blocks_future_observation_dates_and_note_dates():
    data = {
        "backtest_date": "2025-04-09",
        "indicators": [
            {
                "layer": 4,
                "function_id": "get_damodaran_us_implied_erp",
                "metric_name": "Damodaran ERP",
                "raw_data": {
                    "value": {
                        "data_date": "2025-04-01",
                        "monthly_series": [
                            {"data_date": "2025-04-01", "level": 4.43},
                            {"data_date": "2026-05-01", "level": 4.24},
                        ],
                    }
                },
            },
            {
                "layer": 2,
                "function_id": "get_crowdedness_dashboard",
                "metric_name": "Crowdedness",
                "raw_data": {
                    "value": {"skew_index": {"date": "2025-04-09", "value": 120.0}},
                    "notes": "基于到期日: 2026-05-18 的期权持仓量",
                },
            },
        ],
    }

    report = DataIntegrity().run(data)

    assert report["blocked"] is True
    assert report["unpublishable"] is True
    assert report["publish_status"] == "blocked"
    assert "value.monthly_series[1].data_date=2026-05-01" in report["future_date_violations"]["Damodaran ERP"]
    assert "notes[text_date]=2026-05-18" in report["future_date_violations"]["Crowdedness"]


def test_data_integrity_carries_strict_backtest_invariants_without_blocking():
    data = {
        "backtest_date": "2025-04-09",
        "strict_backtest_invariants": {
            "schema_version": "strict_backtest_invariants_v1",
            "declared_limitations": [
                {"invariant_id": "alfred_first_vintage_not_enforced", "status": "declared_limitation"},
                {"invariant_id": "financials_first_reported_not_enforced", "status": "declared_limitation"},
            ],
        },
        "indicators": [
            {"function_id": "get_fed_funds_rate", "metric_name": "Fed Funds", "value": 5.25},
        ],
    }

    report = DataIntegrity().run(data)

    assert report["publish_status"] == "publishable"
    assert report["strict_backtest_invariants"]["schema_version"] == "strict_backtest_invariants_v1"
    assert "严格回测限制已明示" in report["notes"]
    assert "alfred_first_vintage_not_enforced" in report["notes"]
