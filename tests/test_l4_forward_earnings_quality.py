import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4


def test_calculate_weighted_metrics_includes_forward_eps_and_margin_quality():
    df = pd.DataFrame(
        [
            {
                "ticker": "A",
                "market_cap": 600.0,
                "trailing_pe": 30.0,
                "forward_pe": 24.0,
                "forward_eps": 5.0,
                "trailing_eps": 4.0,
                "earnings_growth": 0.18,
                "revenue_growth": 0.12,
                "profit_margin": 0.24,
                "gross_margin": 0.55,
                "operating_margin": 0.30,
            },
            {
                "ticker": "B",
                "market_cap": 400.0,
                "trailing_pe": 20.0,
                "forward_pe": 20.0,
                "forward_eps": 2.2,
                "trailing_eps": 2.0,
                "earnings_growth": 0.08,
                "revenue_growth": 0.05,
                "profit_margin": 0.12,
                "gross_margin": 0.35,
                "operating_margin": 0.16,
            },
        ]
    )

    metrics = tools_L4.calculate_weighted_metrics(df)

    assert metrics["weighted_forward_pe"] == 22.22
    assert metrics["weighted_forward_earnings_yield"] == 4.5
    assert metrics["weighted_forward_eps_growth_proxy_pct"] == 19.0
    assert metrics["weighted_profit_margin_pct"] == 19.2
    assert metrics["weighted_operating_margin_pct"] == 24.4
    assert metrics["coverage"]["forward_eps_growth_proxy"]["constituents_used"] == 2


def test_ndx_forward_earnings_quality_uses_component_and_m7_revision_proxies(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "market_cap": 700.0,
                "trailing_pe": 28.0,
                "forward_pe": 23.0,
                "forward_eps": 8.0,
                "trailing_eps": 7.0,
                "profit_margin": 0.25,
                "gross_margin": 0.45,
                "operating_margin": 0.31,
            },
            {
                "ticker": "MSFT",
                "market_cap": 300.0,
                "trailing_pe": 32.0,
                "forward_pe": 25.0,
                "forward_eps": 10.0,
                "trailing_eps": 8.0,
                "profit_margin": 0.35,
                "gross_margin": 0.69,
                "operating_margin": 0.44,
            },
        ]
    )
    monkeypatch.setattr(tools_L4, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L4, "get_ndx_components_data_yf_v5", lambda end_date=None: (df, {"coverage": 1.0, "successful": 2, "total_tickers": 2}))
    monkeypatch.setattr(
        tools_L4,
        "_m7_eps_revision_snapshot",
        lambda market_caps=None: {
            "coverage": {"available_members": 2, "total_members": 7},
            "weighted_next_year_eps_revision_30d_pct": 2.5,
            "revision_direction_30d": "upward",
            "members": {},
        },
    )

    result = tools_L4.get_ndx_forward_earnings_quality(end_date="2026-05-09")
    value = result["value"]

    assert result["source_tier"] == tools_L4.SOURCE_TIER_COMPONENT_MODEL
    assert value["ndx"]["forward_earnings_yield_pct"] is not None
    assert value["ndx"]["weighted_operating_margin_pct"] == 34.9
    assert value["m7"]["eps_revisions"]["revision_direction_30d"] == "upward"
    assert result["data_quality"]["coverage"]["m7_revision_coverage"]["available_members"] == 2


def test_realtime_forward_earnings_does_not_request_historical_constituents(monkeypatch):
    requested = {}

    def fake_components(end_date=None):
        requested["end_date"] = end_date
        return ["AAPL"]

    class FakeTicker:
        info = {
            "marketCap": 100.0,
            "trailingPE": 20.0,
            "forwardPE": 18.0,
            "forwardEps": 10.0,
            "trailingEps": 9.0,
            "profitMargins": 0.2,
            "grossMargins": 0.5,
            "operatingMargins": 0.3,
        }

    monkeypatch.setattr(tools_L4, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L4, "get_ndx100_components", fake_components)
    monkeypatch.setattr(tools_L4.yf, "Ticker", lambda ticker: FakeTicker())

    df, stats = tools_L4.get_ndx_components_data_yf_v5()

    assert requested["end_date"] is None
    assert stats["successful"] == 1
    assert df["ticker"].tolist() == ["AAPL"]


def test_realtime_equity_risk_premium_keeps_valuation_in_realtime_mode(monkeypatch):
    requested = {}

    def fake_valuation(end_date=None):
        requested["valuation_end_date"] = end_date
        return {
            "value": {"EarningsYield": 3.8},
            "source_tier": tools_L4.SOURCE_TIER_COMPONENT_MODEL,
            "data_quality": {"coverage": {}, "anomalies": [], "source_disagreement": {}},
        }

    monkeypatch.setattr(tools_L4, "get_ndx_pe_and_earnings_yield", fake_valuation)
    monkeypatch.setattr(
        tools_L4,
        "get_10y_treasury",
        lambda end_date=None: {"value": {"level": 4.4}},
    )

    result = tools_L4.get_equity_risk_premium()

    assert requested["valuation_end_date"] is None
    assert result["value"]["level"] == -0.6
