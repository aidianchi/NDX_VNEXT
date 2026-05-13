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
