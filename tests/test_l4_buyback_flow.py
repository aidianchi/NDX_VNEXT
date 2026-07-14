import os
import sys
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4
from data_evidence import REQUIRED_DATA_QUALITY_FIELDS, data_evidence_issues


def _fact(period_end, value, filed=None):
    end_dt = date.fromisoformat(period_end)
    return {
        "start": (end_dt - timedelta(days=90)).isoformat(),
        "end": period_end,
        "val": value,
        "filed": filed or (end_dt + timedelta(days=25)).isoformat(),
        "form": "10-K" if end_dt.month == 12 else "10-Q",
        "accn": f"acc-{period_end}",
    }


def _payload(quarters):
    return {"units": {"USD": [_fact(period_end, value) for period_end, value in quarters]}}


def _install_sec(monkeypatch, quarters_by_ticker):
    cik_map = {ticker: f"{idx:010d}" for idx, ticker in enumerate(quarters_by_ticker, start=1)}
    tag = tools_L4.M7_BUYBACK_XBRL_TAG_CANDIDATES[0]
    payloads = {(cik_map[ticker], tag): _payload(quarters) for ticker, quarters in quarters_by_ticker.items()}

    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: cik_map)

    def fake_fetch(cik, requested_tag):
        payload = payloads.get((cik, requested_tag))
        return (payload, None) if payload is not None else ({}, "tag_not_reported")

    monkeypatch.setattr(tools_L4, "_fetch_sec_xbrl_companyconcept", fake_fetch)


def _eight_quarters(base=1_000_000_000):
    return [
        ("2024-03-31", base), ("2024-06-30", base * 2),
        ("2024-09-30", base * 3), ("2024-12-31", base * 4),
        ("2025-03-31", base * 2), ("2025-06-30", base * 3),
        ("2025-09-30", base * 4), ("2025-12-31", base * 5),
    ]


def test_yfinance_buyback_fallback_normalizes_negative_cash_outflow(monkeypatch):
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): [-5_000_000_000.0],
            pd.Timestamp("2025-09-30"): [2_000_000_000.0],
        },
        index=["Repurchase Of Capital Stock"],
    )

    class FakeTicker:
        quarterly_cashflow = frame

    monkeypatch.setattr(tools_L4.yf, "Ticker", lambda _ticker: FakeTicker())
    rows, error = tools_L4._fetch_yfinance_buyback_quarterly("AAPL")

    assert error is None
    assert [row["value"] for row in rows] == [2_000_000_000.0, 5_000_000_000.0]
    assert rows[-1]["raw_value"] == -5_000_000_000.0


def test_buyback_full_contract_ttm_and_comparable_yoy(monkeypatch):
    quarters = {ticker: _eight_quarters((idx + 1) * 1_000_000_000) for idx, ticker in enumerate(tools_L4.M7_TICKERS)}
    _install_sec(monkeypatch, quarters)

    result = tools_L4.get_m7_buyback_flow("2026-07-10")
    value = result["value"]

    assert result["availability"] == "available"
    assert value["per_company"]["AAPL"]["latest_quarter_buyback_usd_bn"] == 5.0
    assert value["per_company"]["AAPL"]["ttm_buyback_usd_bn"] == 14.0
    assert value["m7_quarterly_total"] == 140.0
    assert value["m7_ttm_total"] == 392.0
    assert value["yoy_pct"] == 25.0
    assert value["raw_quarterly_series"]["AAPL"][-1]["value_usd"] == 5_000_000_000


def test_buyback_ttm_withheld_with_fewer_than_four_quarters(monkeypatch):
    _install_sec(monkeypatch, {"AAPL": [("2025-09-30", 2_000_000_000), ("2025-12-31", 3_000_000_000)]})

    result = tools_L4.get_m7_buyback_flow("2026-07-10")

    aapl = result["value"]["per_company"]["AAPL"]
    assert aapl["ttm_buyback_usd_bn"] is None
    assert aapl["ttm_unavailable_reason"] == "fewer_than_4_distinct_consecutive_calendar_quarters"
    assert result["value"]["m7_ttm_total"] is None


def test_buyback_ttm_withheld_when_four_rows_are_not_consecutive(monkeypatch):
    _install_sec(
        monkeypatch,
        {"AAPL": [
            ("2024-12-31", 1_000_000_000),
            ("2025-03-31", 2_000_000_000),
            ("2025-09-30", 3_000_000_000),
            ("2025-12-31", 4_000_000_000),
        ]},
    )

    result = tools_L4.get_m7_buyback_flow("2026-07-10")

    assert result["value"]["per_company"]["AAPL"]["coverage_quarters"] == 4
    assert result["value"]["per_company"]["AAPL"]["ttm_buyback_usd_bn"] is None


def test_buyback_excludes_latest_fiscal_quarter_misalignment_from_ttm(monkeypatch):
    aligned = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    quarters = {ticker: _eight_quarters() for ticker in aligned}
    quarters["NVDA"] = _eight_quarters() + [("2026-01-31", 6_000_000_000)]
    _install_sec(monkeypatch, quarters)

    result = tools_L4.get_m7_buyback_flow("2026-07-10")
    context = result["value"]["aggregate_context"]

    assert context["latest_calendar_quarter"] == "2025Q4"
    assert "NVDA" in context["excluded_for_fiscal_calendar_misalignment"]
    assert "NVDA" not in context["ttm_aligned_companies"]
    assert result["value"]["m7_ttm_total"] == 70.0


def test_buyback_backtest_disables_yfinance_fallback(monkeypatch):
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {})

    def fail_if_called(_ticker):
        raise AssertionError("live-only yfinance fallback must not run in a historical call")

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_buyback_quarterly", fail_if_called)
    result = tools_L4.get_m7_buyback_flow("2020-01-01")

    assert result["availability"] == "unavailable"
    assert result["data_quality"]["pit_safe_summary"]["fallback_allowed_in_this_call"] is False
    assert all("fallback_disabled_not_live_context_pit_unsafe" in row["unavailable_reason"] for row in result["value"]["per_company"].values())
    assert result["data_quality"]["fallback_reason"] == "no_m7_company_buyback_facts_available_from_sec_xbrl_or_yfinance_fallback"


def test_sec_duration_facts_require_valid_filed_date_for_pit():
    units = {
        "USD": [
            {"start": "2025-01-01", "end": "2025-03-31", "val": 1, "form": "10-Q"},
            {"start": "2025-04-01", "end": "2025-06-30", "val": 2, "filed": "invalid", "form": "10-Q"},
            {"start": "2025-07-01", "end": "2025-09-30", "val": 3, "filed": "2025-11-01", "form": "10-Q"},
            {"start": "2025-10-01", "end": "2025-12-31", "val": 4, "filed": "2026-01-20", "form": "10-K"},
        ]
    }

    facts = tools_L4._sec_xbrl_duration_facts_before(units, end_date="2025-12-31")

    assert [row["val"] for row in facts] == [3]


def test_buyback_live_yfinance_fallback_contract(monkeypatch):
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {})

    def fake_yahoo(ticker):
        if ticker != "AAPL":
            return [], "row_missing"
        return [
            {"period_end": "2024-06-30", "raw_value": -1.0e9, "value": 1.0e9},
            {"period_end": "2024-09-30", "raw_value": -2.0e9, "value": 2.0e9},
            {"period_end": "2024-12-31", "raw_value": -3.0e9, "value": 3.0e9},
            {"period_end": "2025-03-31", "raw_value": -4.0e9, "value": 4.0e9},
        ], None

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_buyback_quarterly", fake_yahoo)
    result = tools_L4.get_m7_buyback_flow(end_date=None)

    aapl = result["value"]["per_company"]["AAPL"]
    assert aapl["primary_source"] == "yfinance_fallback"
    assert aapl["pit_safe"] is False
    assert aapl["source_tier"] == tools_L4.SOURCE_TIER_THIRD_PARTY
    assert all(row["filed_date"] is None and row["pit_safe"] is False for row in result["value"]["raw_quarterly_series"]["AAPL"])
    assert "yfinance_fallback_used_pit_unsafe" in result["data_quality"]["anomalies"]


def test_buyback_data_quality_authority_and_full_wiring(monkeypatch):
    _install_sec(monkeypatch, {ticker: _eight_quarters() for ticker in tools_L4.M7_TICKERS})
    result = tools_L4.get_m7_buyback_flow("2026-07-10")

    assert REQUIRED_DATA_QUALITY_FIELDS <= set(result["data_quality"])
    assert result["data_quality"]["metric_authority"]["actual_buyback_spending"]["usage"] == "supporting_only"
    assert "abs(reported_cash_flow_value)" in result["data_quality"]["formula"]
    assert data_evidence_issues(result, function_id="get_m7_buyback_flow")["hard_block"] == []

    from agent_analysis.deep_research_canon import INDICATOR_CANONS
    from agent_analysis.packet_builder import LAYER_FUNCTIONS as PACKET_LAYER_FUNCTIONS
    from core.collector import DataCollector
    from data_evidence import BACKTEST_VINTAGE_REQUIRED_FUNCTIONS, CORE_EVIDENCE_FUNCTIONS
    from data_evidence import normalize_source_tier_for_evidence_passport
    from tools import TOOLS_REGISTRY

    assert "get_m7_buyback_flow" in CORE_EVIDENCE_FUNCTIONS
    assert "get_m7_buyback_flow" in BACKTEST_VINTAGE_REQUIRED_FUNCTIONS
    assert "get_m7_buyback_flow" in DataCollector().LAYER_FUNCTIONS[4]
    assert "get_m7_buyback_flow" in PACKET_LAYER_FUNCTIONS["L4"]
    assert TOOLS_REGISTRY["get_m7_buyback_flow"] is tools_L4.get_m7_buyback_flow
    assert INDICATOR_CANONS["get_m7_buyback_flow"].layer.value == "L4"
    assert normalize_source_tier_for_evidence_passport("mixed_official_and_third_party") == "proxy"
