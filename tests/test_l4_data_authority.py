import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4


def test_weighted_metrics_use_aggregate_earnings_and_fcf_with_coverage():
    df = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "market_cap": 100.0,
                "trailing_pe": 10.0,
                "forward_pe": 20.0,
                "fcf": 8.0,
                "weight": 0.2,
            },
            {
                "ticker": "BBB",
                "market_cap": 300.0,
                "trailing_pe": 30.0,
                "forward_pe": 15.0,
                "fcf": 12.0,
                "weight": 0.6,
            },
            {
                "ticker": "CCC",
                "market_cap": 100.0,
                "trailing_pe": -5.0,
                "forward_pe": None,
                "fcf": None,
                "weight": 0.2,
            },
        ]
    )

    metrics = tools_L4.calculate_weighted_metrics(df)

    assert metrics["weighted_trailing_pe"] == 20.0
    assert metrics["weighted_forward_pe"] == 16.0
    assert metrics["weighted_earnings_yield"] == 5.0
    assert metrics["weighted_forward_earnings_yield"] == 6.25
    assert metrics["weighted_fcf_yield"] == 5.0
    assert metrics["coverage"]["trailing_pe"]["market_cap_coverage_pct"] == 80.0
    assert metrics["coverage"]["forward_pe"]["constituent_coverage_pct"] == 66.67
    assert any(item["ticker"] == "CCC" for item in metrics["anomalies"])


def test_simple_yield_gap_is_not_labeled_as_implied_erp(monkeypatch):
    monkeypatch.setattr(
        tools_L4,
        "get_ndx_pe_and_earnings_yield",
        lambda end_date=None: {
            "name": "NDX Valuation",
            "value": {"EarningsYield": 4.0, "FCFYield": 3.5},
            "data_quality": {"source_tier": "component_model"},
        },
    )
    monkeypatch.setattr(
        tools_L4,
        "get_10y_treasury",
        lambda end_date=None: {"value": {"level": 4.25}},
    )

    result = tools_L4.get_equity_risk_premium("2026-04-30")

    assert result["name"] == "NDX Simple Yield Gap"
    assert result["series_id"] == "SIMPLE_YIELD_GAP"
    assert result["value"]["level"] == -0.75
    assert result["value"]["method"] == "fcf_yield_minus_10y"
    assert result["data_quality"]["formula"] == "NDX FCF yield - 10Y Treasury yield"
    assert "Damodaran" in result["value"]["not_implied_erp_warning"]


def test_damodaran_reference_parser_extracts_latest_fcfe_premium():
    html = """
    <table>
      <tr><th>Year</th><th>Implied Premium (FCFE)</th><th>T.Bond Rate</th></tr>
      <tr><td>2024</td><td>4.60%</td><td>4.00%</td></tr>
      <tr><td>2025</td><td>4.33%</td><td>4.58%</td></tr>
    </table>
    """

    parsed = tools_L4._parse_damodaran_implied_erp_html(html)

    assert parsed["year"] == 2025
    assert parsed["implied_premium_fcfe"] == 4.33
    assert parsed["t_bond_rate"] == 4.58


def test_damodaran_excel_parser_extracts_latest_row_from_official_dataset():
    excel_like_bytes = b"""
    <table>
      <tr><th>Year</th><th>Implied Premium (FCFE)</th><th>Implied Premium (DDM)</th><th>T.Bond Rate</th></tr>
      <tr><td>2024</td><td>4.60%</td><td>4.40%</td><td>4.00%</td></tr>
      <tr><td>2025</td><td>4.33%</td><td>4.20%</td><td>4.58%</td></tr>
    </table>
    """

    parsed = tools_L4._parse_damodaran_implied_erp_excel(excel_like_bytes)

    assert parsed["year"] == 2025
    assert parsed["implied_erp_fcfe"] == 4.33
    assert parsed["implied_erp_ddm"] == 4.2
    assert parsed["tbond_rate"] == 4.58


def test_damodaran_getter_prefers_excel_and_marks_it_official(monkeypatch):
    excel_like_bytes = b"""
    <table>
      <tr><th>Year</th><th>Implied Premium (FCFE)</th><th>T.Bond Rate</th></tr>
      <tr><td>2026</td><td>4.10%</td><td>4.55%</td></tr>
    </table>
    """
    html_called = {"value": False}

    monkeypatch.setattr(tools_L4, "_fetch_bytes", lambda url, timeout=12: (excel_like_bytes, None))

    def fake_fetch_text(url, timeout=8):
        html_called["value"] = True
        return None, "html should not be needed"

    monkeypatch.setattr(tools_L4, "_fetch_text", fake_fetch_text)

    result = tools_L4.get_damodaran_us_implied_erp("2026-05-01")

    assert result["source_tier"] == "official"
    assert result["value"]["implied_erp_fcfe"] == 4.1
    assert result["value"]["tbond_rate"] == 4.55
    assert result["value"]["scope"] == "US equity market reference, not NDX-specific"
    assert result["value"]["download_url"].endswith("histimpl.xls")
    assert html_called["value"] is False


def test_damodaran_getter_falls_back_to_html_when_excel_fails(monkeypatch):
    html = """
    <table>
      <tr><th>Year</th><th>Implied Premium (FCFE)</th><th>T.Bond Rate</th></tr>
      <tr><td>2025</td><td>4.33%</td><td>4.58%</td></tr>
    </table>
    """

    monkeypatch.setattr(tools_L4, "_fetch_bytes", lambda url, timeout=12: (None, "excel failed"))
    monkeypatch.setattr(tools_L4, "_fetch_text", lambda url, timeout=8: (html, None))

    result = tools_L4.get_damodaran_us_implied_erp("2026-05-01")

    assert result["source_tier"] == "official"
    assert result["value"]["implied_erp_fcfe"] == 4.33
    assert result["value"]["tbond_rate"] == 4.58
    assert result["value"]["retrieval_method"] == "html_fallback"


def test_damodaran_getter_returns_unavailable_when_excel_and_html_fail(monkeypatch):
    monkeypatch.setattr(tools_L4, "_fetch_bytes", lambda url, timeout=12: (None, "excel failed"))
    monkeypatch.setattr(tools_L4, "_fetch_text", lambda url, timeout=8: (None, "html failed"))

    result = tools_L4.get_damodaran_us_implied_erp("2026-05-01")

    assert result["source_tier"] == "unavailable"
    assert result["value"] is None
    assert "excel failed" in result["unavailable_reason"]
    assert "html failed" in result["unavailable_reason"]
