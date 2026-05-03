import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L2
import tools_L3


def _price_panel():
    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    close = pd.DataFrame(
        {
            "AAA": range(100, 360),
            "BBB": range(200, 460),
            "CCC": list(range(360, 100, -1)),
        },
        index=dates,
        dtype=float,
    )
    return pd.concat({"Close": close}, axis=1)


def _short_price_panel():
    dates = pd.date_range("2025-01-01", periods=208, freq="B")
    close = pd.DataFrame(
        {
            "AAA": range(100, 308),
            "BBB": range(200, 408),
            "CCC": list(range(308, 100, -1)),
        },
        index=dates,
        dtype=float,
    )
    return pd.concat({"Close": close}, axis=1)


def _price_panel_with_empty_component():
    panel = _price_panel()
    panel[("Close", "DDD")] = float("nan")
    return panel


def test_l2_breadth_module_has_component_provider_imported():
    assert hasattr(tools_L2, "get_ndx100_components")


def test_new_highs_lows_requests_enough_history_for_52w_window(monkeypatch):
    requested = {}

    def fake_price_data(effective_date, lookback_days=300):
        requested["lookback_days"] = lookback_days
        return ["AAA", "BBB", "CCC"], _price_panel()

    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L2, "_get_ndx100_common_price_data", fake_price_data)

    result = tools_L2.get_new_highs_lows("2025-12-31")

    assert requested["lookback_days"] >= 370
    assert result["source_tier"] == "component_model"


def test_new_highs_lows_calculates_component_breakout_counts(monkeypatch):
    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(
        tools_L2,
        "_get_ndx100_common_price_data",
        lambda effective_date: (["AAA", "BBB", "CCC"], _price_panel()),
    )

    result = tools_L2.get_new_highs_lows("2025-12-31")

    assert result["value"]["level"]["new_highs_52w"] == 2
    assert result["value"]["level"]["new_lows_52w"] == 1
    assert result["value"]["coverage"]["constituents_used"] == 3
    assert result["source_tier"] == "component_model"


def test_new_highs_lows_reports_unavailable_when_52w_window_is_missing(monkeypatch):
    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(
        tools_L2,
        "_get_ndx100_common_price_data",
        lambda effective_date: (["AAA", "BBB", "CCC"], _short_price_panel()),
    )

    result = tools_L2.get_new_highs_lows("2025-12-31")

    assert result["source_tier"] == "unavailable"
    assert "Insufficient data for 52-week high/low calculation" in result["notes"]


def test_advance_decline_coverage_excludes_empty_components(monkeypatch):
    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(
        tools_L2,
        "_get_ndx100_common_price_data",
        lambda effective_date: (["AAA", "BBB", "CCC", "DDD"], _price_panel_with_empty_component()),
    )

    result = tools_L2.get_advance_decline_line("2025-12-31")

    assert result["data_quality"]["coverage"]["constituents_used"] == 3
    assert result["data_quality"]["coverage"]["total_constituents"] == 4
    assert result["data_quality"]["coverage"]["constituent_coverage_pct"] == 75.0
    assert any("DDD" in item for item in result["data_quality"]["anomalies"])


def test_mcclellan_oscillator_uses_ad_series_when_available(monkeypatch):
    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(
        tools_L2,
        "_get_ndx100_common_price_data",
        lambda effective_date: (["AAA", "BBB", "CCC"], _price_panel()),
    )

    result = tools_L2.get_mcclellan_oscillator_nasdaq_or_nyse("2025-12-31")

    assert isinstance(result["value"]["level"], float)
    assert result["value"]["coverage"]["constituents_used"] == 3
    assert result["source_tier"] == "component_model"


def test_m7_summary_uses_weighted_contribution_not_simple_average():
    summary = tools_L3._summarize_m7_fundamentals(
        {
            "AAA": {"PE": 10.0, "ROE": 20.0, "MarketCap": 100.0, "quantitative_moat_score": 5.0},
            "BBB": {"PE": 30.0, "ROE": 40.0, "MarketCap": 300.0, "quantitative_moat_score": 9.0},
        }
    )

    assert "avg_PE" not in summary
    assert summary["market_cap_weighted_PE"] == 20.0
    assert summary["market_cap_weighted_ROE"] == 35.0
    assert summary["top_weight_ticker"] == "BBB"


def test_l3_prompt_documents_breadth_priority_and_missing_data_boundary():
    prompt_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "src",
        "agent_analysis",
        "prompts",
        "l3_analyst.md",
    )
    prompt = open(prompt_path, encoding="utf-8").read()

    assert "A/D Line" in prompt
    assert "% Above MA" in prompt
    assert "New Highs/Lows" in prompt
    assert "McClellan" in prompt
    assert "不能把缺失写成恶化" in prompt
