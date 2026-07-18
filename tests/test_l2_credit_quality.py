import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L2
from agent_analysis.deep_research_canon import INDICATOR_CANONS
from core.collector import DataCollector


def test_hy_quality_spread_calculates_ccc_lower_minus_bb(monkeypatch):
    dates = pd.date_range("2026-01-01", periods=30, freq="B")
    ccc = pd.DataFrame({"date": dates, "value": [8.0 + i * 0.01 for i in range(30)]})
    bb = pd.DataFrame({"date": dates, "value": [2.0 + i * 0.005 for i in range(30)]})

    def fake_fred(series_id, end_date=None):
        if series_id == "BAMLH0A3HYC":
            return ccc
        if series_id == "BAMLH0A1HYBB":
            return bb
        raise AssertionError(series_id)

    monkeypatch.setattr(tools_L2, "get_fred_series", fake_fred)

    result = tools_L2.get_hy_quality_spread_bp("2026-02-15")

    assert result["series_id"] == "BAMLH0A3HYC-BAMLH0A1HYBB"
    assert result["value"]["level"] > 0
    assert result["value"]["ccc_oas"] > result["value"]["bb_oas"]
    assert result["data_quality"]["formula"].startswith("ICE BofA CCC & Lower")
    assert result["recompute_input"]["raw_series"][-1]["date"] <= "2026-02-15"


def test_hy_quality_spread_is_registered_for_l2():
    assert "get_hy_quality_spread_bp" in DataCollector().LAYER_FUNCTIONS[2]
    assert INDICATOR_CANONS["get_hy_quality_spread_bp"].layer.value == "L2"
