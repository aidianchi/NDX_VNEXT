import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L2


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_cnn_fgi_backtest_uses_historical_series_not_live_field(monkeypatch):
    payload = {
        "fear_and_greed": {"score": 62.91, "rating": "greed", "timestamp": 1778803200000},
        "fear_and_greed_historical": {
            "data": [
                {"x": 1744070400000, "y": 12.0, "rating": "extreme fear"},
                {"x": 1744156800000, "y": 9.5, "rating": "extreme fear"},
                {"x": 1744243200000, "y": 18.0, "rating": "fear"},
            ]
        },
    }
    monkeypatch.setattr(tools_L2.requests, "get", lambda *args, **kwargs: _Response(payload))

    result = tools_L2.get_cnn_fear_greed_index(end_date="2025-04-09")

    assert result["value"]["score"] == 9.5
    assert result["value"]["trend"] == "extreme_fear"
    assert result["value"]["data_date"] == "2025-04-09"
    assert result["data_quality"]["source_path"] == "fear_and_greed_historical.data"


def test_cnn_fgi_backtest_does_not_fallback_to_live_when_history_missing(monkeypatch):
    payload = {
        "fear_and_greed": {"score": 62.91, "rating": "greed", "timestamp": 1778803200000},
        "fear_and_greed_historical": {"data": []},
    }
    monkeypatch.setattr(tools_L2.requests, "get", lambda *args, **kwargs: _Response(payload))

    result = tools_L2.get_cnn_fear_greed_index(end_date="2025-04-09")

    assert result["value"] is None
    assert "live field was not used" in result["notes"]
