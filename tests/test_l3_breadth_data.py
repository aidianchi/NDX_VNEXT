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

    def fake_price_data(effective_date, lookback_days=300, historical_date=None):
        requested["lookback_days"] = lookback_days
        requested["historical_date"] = historical_date
        return ["AAA", "BBB", "CCC"], _price_panel()

    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L2, "_get_ndx100_common_price_data", fake_price_data)

    result = tools_L2.get_new_highs_lows("2025-12-31")

    assert requested["lookback_days"] >= 370
    assert requested["historical_date"] == "2025-12-31"
    assert result["source_tier"] == "component_model"


def test_new_highs_lows_calculates_component_breakout_counts(monkeypatch):
    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(
        tools_L2,
        "_get_ndx100_common_price_data",
        lambda effective_date, **kwargs: (["AAA", "BBB", "CCC"], _price_panel()),
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
        lambda effective_date, **kwargs: (["AAA", "BBB", "CCC"], _short_price_panel()),
    )

    result = tools_L2.get_new_highs_lows("2025-12-31")

    assert result["source_tier"] == "unavailable"
    assert "Insufficient data for 52-week high/low calculation" in result["notes"]


def test_advance_decline_coverage_excludes_empty_components(monkeypatch):
    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(
        tools_L2,
        "_get_ndx100_common_price_data",
        lambda effective_date, **kwargs: (["AAA", "BBB", "CCC", "DDD"], _price_panel_with_empty_component()),
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
        lambda effective_date, **kwargs: (["AAA", "BBB", "CCC"], _price_panel()),
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


def test_realtime_breadth_does_not_request_historical_constituents(monkeypatch):
    tools_L2._NDX100_PRICE_PANEL_RUN_CACHE.clear()
    requested = {}

    def fake_components(end_date=None):
        requested["end_date"] = end_date
        return ["AAA", "BBB", "CCC"]

    monkeypatch.setattr(tools_L2, "get_ndx100_components", fake_components)
    monkeypatch.setattr(tools_L2, "cached_yf_download", lambda *args, **kwargs: _price_panel())

    components, data = tools_L2._get_ndx100_common_price_data(datetime(2026, 5, 10))

    assert components == ["AAA", "BBB", "CCC"]
    assert not data.empty
    assert requested["end_date"] is None


def test_ndx100_common_price_data_uses_local_archive_when_yfinance_fails(tmp_path, monkeypatch):
    tools_L2._NDX100_PRICE_PANEL_RUN_CACHE.clear()
    monkeypatch.setattr(tools_L2.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_L2, "get_ndx100_components", lambda end_date=None: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(tools_L2, "cached_yf_download", lambda *args, **kwargs: _price_panel())

    components, first = tools_L2._get_ndx100_common_price_data(datetime(2025, 12, 31), historical_date="2025-12-31")
    assert components == ["AAA", "BBB", "CCC"]
    assert not first.empty

    tools_L2._NDX100_PRICE_PANEL_RUN_CACHE.clear()

    def empty_download(*args, **kwargs):
        raise AssertionError("archive should avoid a second yfinance fetch")

    monkeypatch.setattr(tools_L2, "cached_yf_download", empty_download)
    components, archived = tools_L2._get_ndx100_common_price_data(datetime(2025, 12, 31), historical_date="2025-12-31")

    assert components == ["AAA", "BBB", "CCC"]
    assert not archived.empty
    assert list(tools_L2._extract_component_close_prices(archived).columns) == ["AAA", "BBB", "CCC"]


def test_ndx100_common_price_data_caches_failed_window_within_run(tmp_path, monkeypatch):
    tools_L2._NDX100_PRICE_PANEL_RUN_CACHE.clear()
    monkeypatch.setattr(tools_L2.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_L2, "get_ndx100_components", lambda end_date=None: ["AAA", "BBB", "CCC"])
    calls = {"count": 0}

    def empty_download(*args, **kwargs):
        calls["count"] += 1
        return None

    monkeypatch.setattr(tools_L2, "_download_ndx100_missing_price_archive", empty_download)

    for _ in range(2):
        _components, data = tools_L2._get_ndx100_common_price_data(datetime(2025, 12, 31), historical_date="2025-12-31")
        assert data.empty

    assert calls["count"] == 1


def test_single_ticker_archive_download_keeps_ticker_column_name():
    dates = pd.date_range("2025-01-01", periods=3, freq="B")
    single = pd.DataFrame({"Close": [10.0, 11.0, 12.0]}, index=dates)

    normalized = tools_L2._ensure_component_ticker_columns(single, ["MSFT"])
    close = tools_L2._extract_component_close_prices(normalized)

    assert list(close.columns) == ["MSFT"]


def test_ndx_ndxe_ratio_yfinance_request_includes_effective_date(monkeypatch):
    calls = []
    dates = pd.date_range("2024-04-10", "2025-04-09", freq="B")

    def fake_download(ticker, **kwargs):
        calls.append((ticker, kwargs.get("end")))
        close = pd.Series(range(100, 100 + len(dates)), index=dates, dtype=float)
        if ticker == "^NDXE":
            close = close * 0.9
        return pd.DataFrame({"Close": close}, index=dates)

    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L2, "cached_yf_download", fake_download)

    result = tools_L2.get_ndx_ndxe_ratio("2025-04-09")

    assert {ticker for ticker, _end in calls} == {"^NDX", "^NDXE"}
    assert {pd.Timestamp(end).date().isoformat() for _ticker, end in calls} == {"2025-04-10"}
    assert result["value"]["date"] == "2025-04-09"
    assert result["name"] == "NDX/NDXE Ratio"
