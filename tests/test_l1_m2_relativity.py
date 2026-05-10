import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L1


def test_m2_yoy_reports_relativity_on_yoy_history(monkeypatch):
    dates = pd.date_range("2014-01-01", periods=150, freq="MS")
    yoy_history = pd.DataFrame({"date": dates, "value": [float(index % 20) for index in range(150)]})

    monkeypatch.setattr(tools_L1, "calculate_yoy_change", lambda *args, **kwargs: (4.57, "2026-03-01"))
    monkeypatch.setattr(tools_L1, "calculate_yoy_series", lambda *args, **kwargs: yoy_history)

    result = tools_L1.get_m2_yoy()

    relativity = result["value"]["relativity"]
    assert result["value"]["level"] == 4.57
    assert relativity["percentile_1y"] is not None
    assert relativity["percentile_10y"] is not None
    assert relativity["history_years"] >= 9.5
