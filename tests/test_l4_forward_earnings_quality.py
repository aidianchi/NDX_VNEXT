import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4
from data_evidence import data_evidence_issues


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
    assert metrics["weighted_forward_eps_growth_proxy_pct"] == 12.5
    assert metrics["forward_eps_growth_proxy_method"] == "sum(market_cap / forward_pe) / sum(market_cap / trailing_pe) - 1"
    assert metrics["weighted_profit_margin_pct"] == 19.2
    assert metrics["weighted_operating_margin_pct"] == 24.4
    assert metrics["coverage"]["forward_eps_growth_proxy"]["constituents_used"] == 2


def test_calculate_weighted_metrics_aggregates_price_to_book_by_book_equity():
    df = pd.DataFrame(
        [
            {"ticker": "A", "market_cap": 900.0, "trailing_pe": 30.0, "forward_pe": 24.0, "price_to_book": 45.0},
            {"ticker": "B", "market_cap": 100.0, "trailing_pe": 20.0, "forward_pe": 20.0, "price_to_book": 5.0},
        ]
    )

    metrics = tools_L4.calculate_weighted_metrics(df)

    assert metrics["weighted_price_to_book"] == 25.0
    assert metrics["price_to_book_method"] == "covered_market_cap / sum(market_cap / component_price_to_book)"


def test_forward_growth_proxy_uses_aggregate_earnings_not_average_component_growth():
    df = pd.DataFrame(
        [
            {"ticker": "A", "market_cap": 900.0, "trailing_pe": 90.0, "forward_pe": 45.0, "forward_eps": 2.0, "trailing_eps": 1.0},
            {"ticker": "B", "market_cap": 100.0, "trailing_pe": 10.0, "forward_pe": 10.0, "forward_eps": 1.0, "trailing_eps": 1.0},
        ]
    )

    metrics = tools_L4.calculate_weighted_metrics(df)

    assert metrics["weighted_forward_eps_growth_proxy_pct"] == 50.0
    assert metrics["weighted_forward_eps_growth_proxy_pct"] != 90.0


def test_component_valuation_audit_rejects_pb_when_third_party_cross_check_fails():
    audit = tools_L4.audit_component_valuation_metrics(
        {
            "weighted_trailing_pe": 33.3,
            "weighted_forward_pe": 22.7,
            "weighted_price_to_book": 41.18,
        },
        [
            {
                "source_id": "danjuan_ndx_valuation",
                "source_name": "DanjuanFunds",
                "availability": "available",
                "metric": "ndx_trailing_pe",
                "value": 34.16,
                "pb": 10.02,
            },
            {
                "source_id": "trendonify_forward_pe",
                "source_name": "Trendonify",
                "availability": "available",
                "metric": "ndx_forward_pe",
                "value": 23.8,
            },
        ],
    )

    assert audit["metric_authority"]["PE"]["usage"] == "core_allowed"
    assert audit["metric_authority"]["ForwardPE"]["usage"] == "core_allowed"
    assert audit["metric_authority"]["PriceToBook"]["usage"] == "rejected"
    assert audit["rejected_metrics"]["PriceToBook"]["relative_diff_pct"] > 300
    assert audit["source_disagreement_issues"][0]["blocks_publish"] is False


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
                "eps_estimate_current": 9.1,
                "eps_estimate_30d_ago": 8.9,
                "eps_estimate_90d_ago": 8.7,
                "eps_revision_30d_pct": 2.25,
                "eps_estimate_analyst_count": 30,
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
                "eps_estimate_current": 13.0,
                "eps_estimate_30d_ago": 12.9,
                "eps_estimate_90d_ago": 12.5,
                "eps_revision_30d_pct": 0.78,
                "eps_estimate_analyst_count": 35,
            },
        ]
    )
    monkeypatch.setattr(tools_L4, "YF_AVAILABLE", True)
    monkeypatch.setattr(
        tools_L4,
        "get_ndx_components_data_yf_v5",
        lambda end_date=None: (
            df,
            {
                "coverage": 1.0,
                "successful": 2,
                "total_tickers": 2,
                "source_counts": {"yahoo_quote_summary": {"attempted": 2, "available": 2}},
                "primary_source_by_field": tools_L4.L4_COMPONENT_FIELD_SOURCE_POLICY,
                "component_conflict_gate": {"status": "clean"},
            },
        ),
    )
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
    assert value["m7"]["eps_revisions"]["primary_source"] == "yahoo_quote_summary"
    assert value["ndx"]["eps_revision_source"] == "yahoo_quote_summary"
    assert value["ndx"]["eps_revision_usage"] == "earnings_expectation_change_only_not_valuation_cheapness"
    assert result["data_quality"]["coverage"]["m7_revision_coverage"]["available_members"] == 2
    assert result["data_quality"]["metric_authority"]["forward_eps_growth_proxy_pct"]["usage"] == "supporting_only"
    assert result["data_quality"]["metric_authority"]["weighted_profit_margin_pct"]["usage"] == "supporting_only"
    assert result["data_quality"]["metric_authority"]["ndx_weighted_eps_revision_30d_pct"]["usage"] == "supporting_only"


def test_l4_component_model_degraded_outputs_explain_fallback_reason(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "market_cap": 700.0,
                "trailing_pe": 28.0,
                "forward_pe": 23.0,
                "free_cashflow": 30.0,
                "fcf": 30.0,
                "price_to_book": 12.0,
                "profit_margin": 0.25,
                "gross_margin": 0.45,
                "operating_margin": 0.31,
                "eps_estimate_current": 9.1,
                "eps_estimate_30d_ago": 8.9,
                "eps_revision_30d_pct": 2.25,
                "eps_estimate_analyst_count": 30,
            },
            {
                "ticker": "MSFT",
                "market_cap": 300.0,
                "trailing_pe": 32.0,
                "forward_pe": 25.0,
                "free_cashflow": 20.0,
                "fcf": 20.0,
                "price_to_book": 10.0,
                "profit_margin": 0.35,
                "gross_margin": 0.69,
                "operating_margin": 0.44,
                "eps_estimate_current": 13.0,
                "eps_estimate_30d_ago": 12.9,
                "eps_revision_30d_pct": 0.78,
                "eps_estimate_analyst_count": 35,
            },
        ]
    )
    stats = {
        "coverage": 1.0,
        "successful": 2,
        "total_tickers": 2,
        "failed_tickers": [],
        "source_counts": {"yahoo_quote_summary": {"attempted": 2, "available": 2}},
        "source_switches": [],
        "source_disagreement_issues": [{"ticker": "AAPL", "field": "trailing_pe", "severity": "high"}],
        "primary_source_by_field": tools_L4.L4_COMPONENT_FIELD_SOURCE_POLICY,
        "component_conflict_gate": {
            "status": "degraded",
            "high_core_component_disagreements": [{"ticker": "AAPL", "field": "trailing_pe", "severity": "high"}],
        },
        "official_checks": {},
        "sec_official_facts": {},
    }
    monkeypatch.setattr(tools_L4, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L4, "get_ndx_components_data_yf_v5", lambda end_date=None: (df, stats))
    monkeypatch.setattr(tools_L4, "get_ndx_valuation_third_party_checks", lambda: [])
    monkeypatch.setattr(
        tools_L4,
        "audit_component_valuation_metrics",
        lambda metrics, checks: {
            "rejected_metrics": {},
            "source_disagreement_issues": [],
            "metric_authority": {},
            "core_usage_rule": "unit test",
        },
    )
    monkeypatch.setattr(
        tools_L4,
        "_m7_eps_revision_snapshot",
        lambda market_caps=None: {
            "availability": "available",
            "coverage": {"available_members": 2, "total_members": 7},
            "weighted_next_year_eps_revision_30d_pct": 1.8,
            "revision_direction_30d": "upward",
            "members": {},
        },
    )

    valuation = tools_L4.get_ndx_pe_and_earnings_yield(end_date="2026-06-16")
    forward_quality = tools_L4.get_ndx_forward_earnings_quality(end_date="2026-06-16")

    assert valuation["data_quality"]["availability"] == "degraded"
    assert valuation["data_quality"]["fallback_reason"] == tools_L4.NDX_COMPONENT_VALUATION_FALLBACK_REASON
    assert forward_quality["data_quality"]["availability"] == "degraded"
    assert forward_quality["data_quality"]["fallback_reason"] == tools_L4.NDX_FORWARD_QUALITY_FALLBACK_REASON
    valuation_codes = {
        issue["code"]
        for issue in data_evidence_issues(valuation, function_id="get_ndx_pe_and_earnings_yield")["hard_block"]
    }
    forward_codes = {
        issue["code"]
        for issue in data_evidence_issues(forward_quality, function_id="get_ndx_forward_earnings_quality")["hard_block"]
    }
    assert "fallback_without_reason" not in valuation_codes
    assert "fallback_without_reason" not in forward_codes


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
    monkeypatch.setattr(tools_L4, "_fetch_yahoo_quote_summary_direct", lambda ticker: ({}, "skipped"))
    monkeypatch.setattr(
        tools_L4,
        "_enrich_component_rows_with_official_checks",
        lambda df, end_date=None, include_current_web_checks=True: (
            df,
            {"sec_xbrl": {"checked": 0, "available": 0}, "eastmoney": {"checked": 0, "available": 0}},
        ),
    )
    tools_L4.reset_l4_component_snapshot_cache()

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


def test_simple_yield_gap_uses_earnings_yield_when_fcf_lacks_core_authority(monkeypatch):
    def fake_valuation(end_date=None):
        return {
            "value": {
                "EarningsYield": 3.0,
                "FCFYield": 1.4,
                "MetricAuthority": {
                    "EarningsYield": {"usage": "core_allowed", "authority": "cross_checked"},
                    "FCFYield": {"usage": "supporting_only", "authority": "component_model_uncross_checked"},
                },
            },
            "source_tier": tools_L4.SOURCE_TIER_COMPONENT_MODEL,
            "data_quality": {"coverage": {}, "anomalies": [], "source_disagreement": {}},
        }

    monkeypatch.setattr(tools_L4, "get_ndx_pe_and_earnings_yield", fake_valuation)
    monkeypatch.setattr(
        tools_L4,
        "get_10y_treasury",
        lambda end_date=None: {"value": {"level": 4.47}},
    )

    result = tools_L4.get_equity_risk_premium(end_date="2026-06-07")

    assert result["value"]["level"] == -1.47
    assert result["value"]["method"] == "earnings_yield_minus_10y"
    assert "FCFYield" in result["value"]["rejected_yield_inputs"]


def test_component_snapshot_records_yahoo_fill_and_source_disagreement(monkeypatch):
    calls = {"yf": 0}

    def fake_yf_info(ticker, attempts=2, pause_seconds=0.5):
        calls["yf"] += 1
        if ticker == "AAA":
            return {
                "marketCap": 1000.0,
                "trailingPE": 20.0,
                "forwardPE": 18.0,
                "priceToBook": 10.0,
                "freeCashflow": 50.0,
            }
        return {}

    def fake_yahoo(ticker):
        if ticker == "AAA":
            return (
                {
                    "summaryDetail": {"marketCap": {"raw": 1005.0}, "trailingPE": {"raw": 60.0}},
                    "defaultKeyStatistics": {"forwardPE": {"raw": 18.5}, "priceToBook": {"raw": 10.5}},
                    "financialData": {"freeCashflow": {"raw": 51.0}},
                },
                None,
            )
        return (
            {
                "summaryDetail": {"marketCap": {"raw": 500.0}, "trailingPE": {"raw": 25.0}},
                "defaultKeyStatistics": {"forwardPE": {"raw": 20.0}},
                "financialData": {"freeCashflow": {"raw": 20.0}},
            },
            None,
        )

    monkeypatch.setattr(tools_L4, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L4, "get_ndx100_components", lambda end_date=None: ["AAA", "BBB"])
    monkeypatch.setattr(tools_L4, "get_yf_ticker_info_with_retry", fake_yf_info)
    monkeypatch.setattr(tools_L4, "_fetch_yahoo_quote_summary_direct", fake_yahoo)
    monkeypatch.setattr(
        tools_L4,
        "_enrich_component_rows_with_official_checks",
        lambda df, end_date=None, include_current_web_checks=True: (
            df,
            {"sec_xbrl": {"checked": 0, "available": 0}, "eastmoney": {"checked": 0, "available": 0}},
        ),
    )
    tools_L4.reset_l4_component_snapshot_cache()

    df, stats = tools_L4.get_ndx_component_fundamentals_snapshot()
    cached_df, cached_stats = tools_L4.get_ndx_component_fundamentals_snapshot()

    assert stats["source_counts"]["yfinance"]["available"] == 1
    assert stats["source_counts"]["yahoo_quote_summary"]["available"] == 2
    assert any(item["ticker"] == "BBB" and item["field"] == "market_cap" for item in stats["source_switches"])
    assert any(item["ticker"] == "AAA" and item["field"] == "trailing_pe" for item in stats["source_disagreement_issues"])
    assert pd.isna(df.loc[df["ticker"] == "AAA", "trailing_pe"].iloc[0])
    assert df.loc[df["ticker"] == "BBB", "trailing_pe"].iloc[0] == 25.0
    assert stats["component_conflict_gate"]["status"] == "degraded"
    assert stats["primary_source_by_field"]["eps_revision_30d_pct"] == "yahoo_quote_summary_primary"
    assert cached_stats["cache_hit"] is True
    assert cached_df.equals(df)
    assert calls["yf"] == 2


def test_merge_component_rows_uses_yahoo_as_eps_revision_primary():
    merged = tools_L4._merge_component_source_rows(
        "AAA",
        {"market_cap": 100.0, "eps_revision_30d_pct": -5.0, "eps_estimate_current": 1.0},
        {"market_cap": 101.0, "eps_revision_30d_pct": 2.5, "eps_estimate_current": 1.1},
        {},
    )

    assert merged["eps_revision_30d_pct"] == 2.5
    assert merged["eps_estimate_current"] == 1.1
    assert merged["field_sources"]["eps_revision_30d_pct"] == "yahoo_quote_summary"
    assert any(
        item["field"] == "eps_revision_30d_pct" and item["reason"] == "field_policy_yahoo_primary"
        for item in merged["component_source_switches"]
    )


def test_sec_xbrl_summary_filters_by_filed_date(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "facts": {
                    "us-gaap": {
                        "RevenueFromContractWithCustomerExcludingAssessedTax": {
                            "units": {
                                "USD": [
                                    {
                                        "val": 100,
                                        "form": "10-Q",
                                        "filed": "2025-04-01",
                                        "end": "2025-03-31",
                                        "accn": "0000000001-25-000001",
                                    },
                                    {
                                        "val": 200,
                                        "form": "10-Q",
                                        "filed": "2025-05-01",
                                        "end": "2025-04-30",
                                        "accn": "0000000001-25-000002",
                                    },
                                ]
                            }
                        },
                        "EarningsPerShareDiluted": {
                            "units": {
                                "USD/shares": [
                                    {"val": 1.2, "form": "10-Q", "filed": "2025-04-01", "end": "2025-03-31"}
                                ]
                            }
                        },
                    }
                }
            }

    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {"AAA": "0000000001"})
    monkeypatch.setattr(tools_L4.requests, "get", lambda *args, **kwargs: FakeResponse())

    summary, error = tools_L4._fetch_sec_xbrl_summary("AAA", end_date="2025-04-09")

    assert error is None
    assert summary["revenue"] == 100
    assert summary["revenue_filed_date"] == "2025-04-01"
    assert summary["revenue_source_accession"] == "0000000001-25-000001"
    assert summary["facts"]["revenue"]["source_accession"] == "0000000001-25-000001"
    assert summary["diluted_eps"] == 1.2
    assert summary["facts"]["net_income"]["availability"] == "unavailable"
