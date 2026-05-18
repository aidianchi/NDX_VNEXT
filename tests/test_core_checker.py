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
