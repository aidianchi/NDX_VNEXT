import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4
from data_evidence import REQUIRED_DATA_QUALITY_FIELDS, data_evidence_issues


def _mock_dates(monkeypatch, dates_by_ticker, *, endpoint="get_earnings_dates"):
    def fake_fetch(ticker):
        dates = dates_by_ticker.get(ticker, [])
        return (
            [{"date": item, "endpoint": endpoint} for item in dates],
            {"attempted_endpoints": ["mock"]},
            None,
        )

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_earnings_dates", fake_fetch)


@pytest.mark.parametrize(
    ("offset_days", "expected"),
    [(-22, False), (-21, True), (2, True)],
)
def test_blackout_window_inclusive_boundaries(monkeypatch, offset_days, expected):
    earnings = date(2026, 6, 30)
    as_of = earnings + timedelta(days=offset_days)
    _mock_dates(monkeypatch, {ticker: [earnings.isoformat()] for ticker in tools_L4.M7_TICKERS})

    result = tools_L4.get_m7_earnings_blackout_calendar(as_of.isoformat())

    states = {row["ticker"]: row["in_estimated_blackout"] for row in result["value"]["per_ticker"]}
    assert set(states.values()) == {expected}
    assert result["value"]["m7_in_blackout_count"] == (7 if expected else 0)


def test_blackout_window_day_after_inclusive_end_is_outside():
    window_start, window_end = tools_L4._estimated_blackout_window("2026-06-30")
    assert window_start == "2026-06-09"
    assert window_end == "2026-07-02"
    assert not (window_start <= "2026-07-03" <= window_end)


def test_blackout_equal_weight_share_and_upcoming_calendar(monkeypatch):
    as_of = date(2026, 5, 1)
    dates = {}
    for ticker in tools_L4.M7_TICKERS[:3]:
        dates[ticker] = [(as_of + timedelta(days=10)).isoformat()]
    for ticker in tools_L4.M7_TICKERS[3:]:
        dates[ticker] = [(as_of + timedelta(days=40)).isoformat()]
    _mock_dates(monkeypatch, dates)

    result = tools_L4.get_m7_earnings_blackout_calendar(as_of.isoformat())
    value = result["value"]

    assert value["m7_in_blackout_count"] == 3
    assert value["m7_in_blackout_share_equal_weight"] == round(3 / 7, 4)
    assert {row["ticker"] for row in value["upcoming_28d_calendar"]} == set(tools_L4.M7_TICKERS[:3])
    assert value["blackout_rule"]["days_before_earnings"] == 21
    assert value["blackout_rule"]["days_after_earnings"] == 2


def test_blackout_historical_pit_approximation_and_90d_unavailable(monkeypatch):
    as_of = "2026-01-01"
    _mock_dates(
        monkeypatch,
        {
            "AAPL": ["2026-01-29"],
            "MSFT": ["2026-05-01"],  # outside the explicit 90-day selection window
        },
    )

    result = tools_L4.get_m7_earnings_blackout_calendar(as_of)

    rows = {row["ticker"]: row for row in result["value"]["per_ticker"]}
    assert rows["AAPL"]["availability"] == "available"
    assert rows["MSFT"]["availability"] == "unavailable"
    assert result["availability"] == "degraded"
    assert result["value"]["m7_in_blackout_share_equal_weight"] is None
    assert result["data_quality"]["pit_approximation"] == "realized_earnings_date_used_as_scheduled_proxy"


def test_blackout_historical_call_rejects_current_calendar_only_rows(monkeypatch):
    _mock_dates(
        monkeypatch,
        {ticker: ["2026-02-01"] for ticker in tools_L4.M7_TICKERS},
        endpoint="calendar",
    )

    result = tools_L4.get_m7_earnings_blackout_calendar("2026-01-15")

    assert result["availability"] == "unavailable"
    assert all(row["availability"] == "unavailable" for row in result["value"]["per_ticker"])


def test_blackout_historical_call_rejects_not_yet_realized_future_scrape_rows(monkeypatch):
    runtime_today = date.today()
    as_of = runtime_today - timedelta(days=10)
    not_yet_realized = runtime_today + timedelta(days=10)
    _mock_dates(
        monkeypatch,
        {ticker: [not_yet_realized.isoformat()] for ticker in tools_L4.M7_TICKERS},
        endpoint="get_earnings_dates",
    )

    result = tools_L4.get_m7_earnings_blackout_calendar(as_of.isoformat())

    assert result["availability"] == "unavailable"
    assert all(row["availability"] == "unavailable" for row in result["value"]["per_ticker"])


def test_blackout_data_quality_authority_and_full_wiring(monkeypatch):
    _mock_dates(monkeypatch, {ticker: ["2026-07-14"] for ticker in tools_L4.M7_TICKERS})
    result = tools_L4.get_m7_earnings_blackout_calendar("2026-06-23")

    assert REQUIRED_DATA_QUALITY_FIELDS <= set(result["data_quality"])
    authority = result["data_quality"]["metric_authority"]["estimated_blackout_state"]
    assert authority["usage"] == "supporting_only"
    assert "not_company_disclosure" in authority["authority"]
    assert data_evidence_issues(result, function_id="get_m7_earnings_blackout_calendar")["hard_block"] == []

    from agent_analysis.deep_research_canon import INDICATOR_CANONS
    from agent_analysis.packet_builder import LAYER_FUNCTIONS as PACKET_LAYER_FUNCTIONS
    from core.collector import DataCollector
    from data_evidence import CORE_EVIDENCE_FUNCTIONS
    from tools import TOOLS_REGISTRY

    assert "get_m7_earnings_blackout_calendar" in CORE_EVIDENCE_FUNCTIONS
    assert "get_m7_earnings_blackout_calendar" in DataCollector().LAYER_FUNCTIONS[4]
    assert "get_m7_earnings_blackout_calendar" in PACKET_LAYER_FUNCTIONS["L4"]
    assert TOOLS_REGISTRY["get_m7_earnings_blackout_calendar"] is tools_L4.get_m7_earnings_blackout_calendar
    assert INDICATOR_CANONS["get_m7_earnings_blackout_calendar"].layer.value == "L4"
