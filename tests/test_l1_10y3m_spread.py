import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L1
from core.collector import DataCollector
from core.evidence_families import EVIDENCE_FAMILIES
from data_evidence import CORE_EVIDENCE_FUNCTIONS
from recompute_belt import DEVIATION_PCT_FUNCTION_IDS
from tools import TOOLS_REGISTRY


def _fake_spread_series(periods=30):
    dates = pd.date_range("2026-01-01", periods=periods, freq="B")
    # FRED T10Y3M is published in percent; the function converts to basis points.
    return pd.DataFrame({"date": dates, "value": [0.5 + i * 0.01 for i in range(periods)]})


def test_10y3m_spread_calculates_ma_deviation_in_basis_points(monkeypatch):
    series = _fake_spread_series()

    def fake_fred(series_id, end_date=None):
        assert series_id == "T10Y3M"
        assert end_date == "2026-02-15"
        return series

    monkeypatch.setattr(tools_L1, "get_fred_series", fake_fred)

    result = tools_L1.get_10y3m_spread_bp("2026-02-15")

    assert result["series_id"] == "T10Y3M"
    assert result["unit"] == "basis points"
    assert result["source_name"] == "FRED"
    value = result["value"]
    assert value["level"] == round(float(series["value"].iloc[-1]) * 100, 4)
    assert value["ma"] is not None
    assert value["deviation_pct"] is not None
    assert value["position_vs_ma"] == "above"
    assert value["date"] == series["date"].iloc[-1].strftime("%Y-%m-%d")
    assert "relativity" in value
    assert result["recompute_input"]["raw_series"][-1]["date"] <= "2026-02-15"
    assert result["recompute_input"]["point_in_time_cutoff"] <= "2026-02-15"


def test_10y3m_spread_unavailable_when_series_missing(monkeypatch):
    monkeypatch.setattr(tools_L1, "get_fred_series", lambda *_args, **_kwargs: None)

    result = tools_L1.get_10y3m_spread_bp("2026-02-15")

    assert result["series_id"] == "T10Y3M"
    assert result["value"] is None
    assert result["unit"] == "basis points"
    assert result["data_quality"]["availability"] == "unavailable"
    assert result["data_quality"]["minimum_observations_required"] == 20


def test_10y3m_spread_unavailable_when_history_too_short(monkeypatch):
    monkeypatch.setattr(
        tools_L1, "get_fred_series", lambda *_args, **_kwargs: _fake_spread_series(periods=10)
    )

    result = tools_L1.get_10y3m_spread_bp("2026-02-15")

    assert result["value"] is None
    assert result["data_quality"]["availability"] == "unavailable"
    assert result["data_quality"]["observations_available"] == 10


def test_10y3m_spread_is_registered_for_l1():
    assert "get_10y3m_spread_bp" in DataCollector().LAYER_FUNCTIONS[1]
    assert TOOLS_REGISTRY["get_10y3m_spread_bp"] is tools_L1.get_10y3m_spread_bp
    assert EVIDENCE_FAMILIES["get_10y3m_spread_bp"] == "treasury_10y_3m_curve_spread"
    assert "get_10y3m_spread_bp" in CORE_EVIDENCE_FUNCTIONS
    assert "get_10y3m_spread_bp" in DEVIATION_PCT_FUNCTION_IDS
