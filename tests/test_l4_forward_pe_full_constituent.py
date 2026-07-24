"""Offline contract tests for the full-constituent NTM forward-PE source."""

from datetime import datetime as real_datetime, timezone

import pandas as pd
import pytest
import requests

from src import qqq_holdings, tools_L4


TODAY = real_datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


class FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return TODAY if tz is not None else TODAY.replace(tzinfo=None)


def _freeze_today(monkeypatch):
    monkeypatch.setattr(tools_L4, "datetime", FrozenDateTime)


def _holdings(rows, effective_date="2026-07-23", fallback_used=False):
    return {
        "status": "fallback_used" if fallback_used else "ok",
        "fallback_used": fallback_used,
        "fallback_dated": (
            "2026-07-23 (holdings effective 2026-07-22)"
            if fallback_used
            else None
        ),
        "fallback_reason": "mock live failure" if fallback_used else None,
        "effective_date": None if fallback_used else effective_date,
        "constituents": [
            {
                "rank": index + 1,
                "ticker": ticker,
                "issuer_name": f"{ticker} Inc",
                "weight_pct": weight,
            }
            for index, (ticker, weight) in enumerate(rows)
        ],
    }


def _estimate_frame(fy1, fy2):
    return pd.DataFrame(
        {"avg": [fy1, fy2]},
        index=pd.Index(["0y", "+1y"], name="period"),
    )


def _install_yfinance(monkeypatch, payloads):
    class FakeTicker:
        def __init__(self, ticker):
            self.payload = payloads[ticker]
            if self.payload.get("init_error"):
                raise RuntimeError(self.payload["init_error"])

        @property
        def earnings_estimate(self):
            if self.payload.get("estimate_error"):
                raise RuntimeError(self.payload["estimate_error"])
            if self.payload.get("no_estimate"):
                return pd.DataFrame()
            return _estimate_frame(self.payload["fy1"], self.payload["fy2"])

        @property
        def info(self):
            if self.payload.get("info_error"):
                raise RuntimeError(self.payload["info_error"])
            result = {}
            if "price" in self.payload:
                result["currentPrice"] = self.payload["price"]
            if self.payload.get("fiscal_year_end") is not None:
                result["nextFiscalYearEnd"] = self.payload["fiscal_year_end"]
            if self.payload.get("last_fiscal_year_end") is not None:
                result["lastFiscalYearEnd"] = self.payload[
                    "last_fiscal_year_end"
                ]
            return result

        @property
        def fast_info(self):
            if self.payload.get("fast_info_error"):
                raise RuntimeError(self.payload["fast_info_error"])
            return {}

        @property
        def calendar(self):
            return {}

    monkeypatch.setattr(tools_L4.yf, "Ticker", FakeTicker)


@pytest.mark.parametrize(
    ("days_to_fy1_end", "expected_weight"),
    [(0, 0.0), (365, 1.0), (182, 182 / 365)],
)
def test_ntm_interpolation_w_zero_one_and_middle(
    monkeypatch, days_to_fy1_end, expected_weight
):
    _freeze_today(monkeypatch)
    monkeypatch.setattr(
        tools_L4,
        "_fetch_qqq_top_holdings",
        lambda top_n=None: _holdings([("AAA", 100.0)]),
    )
    fiscal_end = TODAY.date() + pd.Timedelta(days=days_to_fy1_end)
    _install_yfinance(
        monkeypatch,
        {
            "AAA": {
                "fy1": 10.0,
                "fy2": 20.0,
                "price": 200.0,
                "fiscal_year_end": fiscal_end,
            }
        },
    )

    result = tools_L4.get_ndx_forward_pe_full_constituent()
    detail = result["components"]["top_10"][0]
    expected_ntm = expected_weight * 10.0 + (1.0 - expected_weight) * 20.0

    assert detail["fy1_weight"] == pytest.approx(expected_weight)
    assert detail["ntm_eps"] == pytest.approx(expected_ntm)
    assert detail["ntm_method"] == "fiscal_calendar"
    assert result["value"] == pytest.approx(200.0 / expected_ntm, rel=1e-4)


def test_aggregate_keeps_negative_ntm_eps_in_weighted_yield(monkeypatch):
    _freeze_today(monkeypatch)
    monkeypatch.setattr(
        tools_L4,
        "_fetch_qqq_top_holdings",
        lambda top_n=None: _holdings([("PROFIT", 60.0), ("LOSS", 40.0)]),
    )
    _install_yfinance(
        monkeypatch,
        {
            "PROFIT": {
                "fy1": 10.0,
                "fy2": 10.0,
                "price": 100.0,
                "fiscal_year_end": TODAY.date(),
            },
            "LOSS": {
                "fy1": -5.0,
                "fy2": -5.0,
                "price": 100.0,
                "fiscal_year_end": TODAY.date(),
            },
        },
    )

    result = tools_L4.get_ndx_forward_pe_full_constituent()

    # 0.6*(10/100) + 0.4*(-5/100) = 0.04; PE = 1/0.04 = 25.
    assert result["forward_earnings_yield"] == pytest.approx(0.04)
    assert result["value"] == pytest.approx(25.0)
    assert result["weight_coverage_pct"] == pytest.approx(100.0)
    assert result["excluded"] == []
    loss = next(row for row in result["components"]["top_10"] if row["ticker"] == "LOSS")
    assert loss["included"] is True
    assert loss["ntm_eps"] == pytest.approx(-5.0)
    assert "Retained 1" in result["notes"]


def test_coverage_disclosure_and_all_exclusion_reasons(monkeypatch):
    _freeze_today(monkeypatch)
    monkeypatch.setattr(
        tools_L4,
        "_fetch_qqq_top_holdings",
        lambda top_n=None: _holdings(
            [("APPROX", 50.0), ("NOEST", 20.0), ("NOPRICE", 20.0), ("FAILED", 10.0)],
            effective_date="2026-07-01",
        ),
    )
    _install_yfinance(
        monkeypatch,
        {
            "APPROX": {
                "fy1": 8.0,
                "fy2": 12.0,
                "price": 200.0,
                "last_fiscal_year_end": "2025-12-31",
            },
            "NOEST": {"no_estimate": True},
            "NOPRICE": {
                "fy1": 4.0,
                "fy2": 4.0,
                "fast_info_error": "no quote",
            },
            "FAILED": {"estimate_error": "HTTP 429"},
        },
    )

    result = tools_L4.get_ndx_forward_pe_full_constituent()

    assert result["weight_coverage_pct"] == pytest.approx(50.0)
    assert result["availability"] == "unavailable"
    assert result["unavailable_reason"] == "insufficient_constituent_coverage"
    assert result["value"] is None
    assert result["forward_earnings_yield"] is None
    assert result["holdings_freshness_days"] == 22
    assert result["approx_equal_weight_pct"] == pytest.approx(100.0)
    assert result["components"]["top_10"][0]["ntm_method"] == "approx_equal_weight"
    assert result["components"]["remaining"]["component_count"] == 0
    assert {item["ticker"]: item["reason"] for item in result["excluded"]} == {
        "NOEST": "no_estimate",
        "NOPRICE": "no_price",
        "FAILED": "fetch_failed",
    }


def test_historical_end_date_is_unavailable_without_fetching(monkeypatch):
    _freeze_today(monkeypatch)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("live sources must not be called for a historical date")

    monkeypatch.setattr(tools_L4, "_fetch_qqq_top_holdings", fail_if_called)
    result = tools_L4.get_ndx_forward_pe_full_constituent(
        end_date="2026-07-22"
    )

    assert result["availability"] == "unavailable"
    assert result["value"] is None
    assert (
        result["unavailable_reason"]
        == "no_point_in_time_consensus_for_backtest"
    )


def test_holdings_older_than_ten_calendar_days_are_stale(monkeypatch):
    _freeze_today(monkeypatch)
    monkeypatch.setattr(
        tools_L4,
        "_fetch_qqq_top_holdings",
        lambda top_n=None: _holdings(
            [("AAA", 100.0)], effective_date="2026-07-12"
        ),
    )
    _install_yfinance(
        monkeypatch,
        {
            "AAA": {
                "fy1": 10.0,
                "fy2": 10.0,
                "price": 200.0,
                "fiscal_year_end": TODAY.date(),
            }
        },
    )

    result = tools_L4.get_ndx_forward_pe_full_constituent()

    assert result["value"] == pytest.approx(20.0)
    assert result["availability"] == "stale"
    assert result["holdings_freshness_days"] == 11


def test_live_holdings_failure_uses_dated_static_fallback(monkeypatch):
    _freeze_today(monkeypatch)

    def fail_live(*args, **kwargs):
        raise requests.RequestException("406 Client Error")

    monkeypatch.setattr(qqq_holdings.requests, "get", fail_live)
    payloads = {
        row["ticker"]: {
            "fy1": 10.0,
            "fy2": 10.0,
            "price": 200.0,
            "fiscal_year_end": TODAY.date(),
        }
        for row in qqq_holdings.STATIC_FULL_FALLBACK
    }
    _install_yfinance(monkeypatch, payloads)

    result = tools_L4.get_ndx_forward_pe_full_constituent()

    assert result["fallback_used"] is True
    assert "406" in result["fallback_reason"]
    assert result["effective_date"] == "2026-07-22"
    assert result["holdings_freshness_days"] == 1
    assert result["availability"] == "available"
    assert result["weight_coverage_pct"] == pytest.approx(100.0)
    assert len(result["components"]["top_10"]) == 10
    assert result["components"]["remaining"]["component_count"] > 90
