"""Offline tests for src/vintage_archiver.py.

These tests mock every network call (Invesco holdings, yfinance, FMP) so the
suite stays fast and deterministic. They verify:
  1. the on-disk JSON schema (top-level keys + boundary/isolation notice),
  2. idempotent same-day overwrite behavior (no duplicate files, latest wins),
  3. NaN-safe conversion of yfinance-style DataFrames to JSON records,
  4. full-universe expansion (E2, schema_version 2): cash/derivative/
     receivable holdings-row filtering, the static full-holdings fallback,
     per-ticker yfinance retry-on-transient-failure, and the
     `collection_summary` failed/missing-field bookkeeping.

This archiver is deliberately standalone (see module docstring boundary
notes) — it must never be imported by tools_*.py or wired into the L1-L5
pipeline, so this test only exercises the script's own module in isolation.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import pytest
import requests

import vintage_archiver as va


def _fake_universe(tickers):
    return {
        "status": "ok",
        "method": "live_invesco_qqq_holdings_api",
        "source_name": "Invesco QQQ official holdings API",
        "source_url": va.INVESCO_QQQ_HOLDINGS_URL,
        "source_authority": "official_provider",
        "fallback_used": False,
        "effective_date": "2026-07-22",
        "total_holdings_reported": 108,
        "total_holdings_selected": len(tickers),
        "fund_name": "Invesco QQQ Trust",
        "constituents": [
            {"rank": i + 1, "ticker": t, "issuer_name": f"{t} Inc", "weight_pct": 5.0 - i, "security_type": "Common Stock"}
            for i, t in enumerate(tickers)
        ],
        "weight_pct_sum": sum(5.0 - i for i in range(len(tickers))),
        "filtered_out_count": 5,
        "filtered_out": [],
    }


def _fake_yfinance_estimates_ok(ticker, attempts=2, pause_seconds=1.5):
    return {
        "source_name": "yfinance Ticker estimates modules",
        "source_authority": "third_party_unofficial",
        "collected_at_utc": "2026-07-12T00:00:00Z",
        "status": "ok",
        "attempts": 1,
        "fields": {
            "eps_trend": {
                "status": "ok",
                "records": [{"period": "+1y", "current": 12.76383, "90daysAgo": 11.10792, "currency": "USD"}],
            },
            "eps_revisions": {"status": "ok", "records": [{"period": "+1y", "upLast7days": 1}]},
            "earnings_estimate": {"status": "ok", "records": [{"period": "0q", "avg": 2.07925}]},
            "revenue_estimate": {"status": "ok", "records": [{"period": "0q", "avg": 91728642100}]},
        },
    }


def _fake_fmp_estimates_ok(ticker, api_key):
    return {
        "source_name": "FMP analyst-estimates (stable endpoint)",
        "source_authority": "third_party_unofficial",
        "endpoint": "https://financialmodelingprep.com/stable/analyst-estimates",
        "collected_at_utc": "2026-07-12T00:00:00Z",
        "status": "ok",
        "raw_response": [{"symbol": ticker, "date": "2031-01-25", "epsAvg": 22.1}],
    }


def test_build_and_write_archive_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(va, "_fetch_qqq_top_holdings", lambda top_n=15, timeout=15: _fake_universe(["NVDA", "AAPL"]))
    monkeypatch.setattr(va, "_fetch_yfinance_estimates", _fake_yfinance_estimates_ok)
    monkeypatch.setattr(va, "_fetch_fmp_estimates", _fake_fmp_estimates_ok)

    payload = va.build_archive(use_fmp=True, fmp_api_key="dummy-key", request_delay_sec=0)
    out_path = va.write_archive(payload, archive_root=str(tmp_path))

    assert os.path.exists(out_path)
    assert out_path.endswith(os.path.join(payload["archive_date"], "eps_consensus.json"))

    readme_path = os.path.join(str(tmp_path), "README.md")
    assert os.path.exists(readme_path)
    with open(readme_path, encoding="utf-8") as handle:
        readme_text = handle.read()
    assert "evidence_ref" in readme_text
    assert "L1-L5" in readme_text

    with open(out_path, encoding="utf-8") as handle:
        on_disk = json.load(handle)

    # Top-level schema
    for key in ["schema_version", "archive_date", "collected_at_utc", "purpose", "universe", "per_ticker", "collection_summary"]:
        assert key in on_disk

    assert on_disk["schema_version"] == va.SCHEMA_VERSION == "2"
    assert "evidence_ref" in on_disk["purpose"]
    assert "L1-L5" in on_disk["purpose"]

    assert set(on_disk["per_ticker"].keys()) == {"NVDA", "AAPL"}
    nvda = on_disk["per_ticker"]["NVDA"]
    assert nvda["yfinance"]["status"] == "ok"
    assert nvda["yfinance"]["fields"]["eps_trend"]["records"][0]["current"] == pytest.approx(12.76383)
    assert nvda["fmp"]["status"] == "ok"
    assert nvda["fmp"]["raw_response"][0]["epsAvg"] == pytest.approx(22.1)

    summary = on_disk["collection_summary"]
    assert summary["ticker_count"] == 2
    assert summary["yfinance_ok_count"] == 2
    assert summary["yfinance_error_count"] == 0
    assert summary["yfinance_failed_tickers"] == []


def test_same_day_rerun_overwrites_not_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(va, "_fetch_qqq_top_holdings", lambda top_n=15, timeout=15: _fake_universe(["NVDA"]))
    monkeypatch.setattr(va, "_fetch_yfinance_estimates", _fake_yfinance_estimates_ok)
    monkeypatch.setattr(va, "_fetch_fmp_estimates", _fake_fmp_estimates_ok)

    payload1 = va.build_archive(use_fmp=True, fmp_api_key="dummy-key", request_delay_sec=0)
    path1 = va.write_archive(payload1, archive_root=str(tmp_path))
    day_dir = os.path.dirname(path1)
    assert os.listdir(day_dir) == ["eps_consensus.json"]

    # Second run same (mocked) day, different fake data -> must overwrite, not accumulate.
    def _fake_yfinance_estimates_changed(ticker, attempts=2, pause_seconds=1.5):
        data = _fake_yfinance_estimates_ok(ticker)
        data["fields"]["eps_trend"]["records"][0]["current"] = 99.0
        return data

    monkeypatch.setattr(va, "_fetch_yfinance_estimates", _fake_yfinance_estimates_changed)
    payload2 = va.build_archive(use_fmp=True, fmp_api_key="dummy-key", request_delay_sec=0)
    path2 = va.write_archive(payload2, archive_root=str(tmp_path))

    assert path1 == path2
    assert os.listdir(day_dir) == ["eps_consensus.json"]

    with open(path2, encoding="utf-8") as handle:
        on_disk = json.load(handle)
    assert on_disk["per_ticker"]["NVDA"]["yfinance"]["fields"]["eps_trend"]["records"][0]["current"] == 99.0


def test_manual_ticker_override_skips_holdings_fetch(monkeypatch):
    def _boom(**kwargs):
        raise AssertionError("_fetch_qqq_top_holdings should not be called when tickers are overridden")

    monkeypatch.setattr(va, "_fetch_qqq_top_holdings", _boom)
    monkeypatch.setattr(va, "_fetch_yfinance_estimates", _fake_yfinance_estimates_ok)
    monkeypatch.setattr(va, "_fetch_fmp_estimates", _fake_fmp_estimates_ok)

    payload = va.build_archive(tickers=["msft", "avgo"], use_fmp=True, fmp_api_key="dummy-key", request_delay_sec=0)
    assert payload["universe"]["status"] == "manual_override"
    assert set(payload["per_ticker"].keys()) == {"MSFT", "AVGO"}


def test_fmp_missing_key_is_skipped_not_error(monkeypatch):
    monkeypatch.setattr(va, "_fetch_qqq_top_holdings", lambda top_n=15, timeout=15: _fake_universe(["NVDA"]))
    monkeypatch.setattr(va, "_fetch_yfinance_estimates", _fake_yfinance_estimates_ok)
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    payload = va.build_archive(use_fmp=True, fmp_api_key=None, request_delay_sec=0)
    assert payload["per_ticker"]["NVDA"]["fmp"]["status"] == "skipped"
    assert "FMP_API_KEY" in payload["per_ticker"]["NVDA"]["fmp"]["reason"]


def test_df_to_records_handles_nan():
    df = pd.DataFrame(
        {"current": [12.76383, float("nan")], "90daysAgo": [11.10792, 9.0]},
        index=pd.Index(["+1y", "+1q"], name="period"),
    )
    records = va._df_to_records(df)
    assert records[0] == {"period": "+1y", "current": pytest.approx(12.76383), "90daysAgo": pytest.approx(11.10792)}
    assert records[1]["current"] is None


# --- E2: full-universe expansion (schema_version 2) -------------------------


def test_classify_holding_keeps_common_stock_and_adrs():
    assert va._classify_holding("NVDA", 8.0, "Common Stock") is None
    assert va._classify_holding("ASML", 0.7, "American Depository Receipt - NY") is None
    assert va._classify_holding("ARM", 0.5, "American Depository Receipt") is None


def test_classify_holding_filters_cash_derivative_receivable_rows():
    assert va._classify_holding("", 1.0, "Common Stock") == "missing_ticker"
    assert va._classify_holding("USD", None, "Currency") == "missing_or_invalid_weight"
    assert va._classify_holding("XYZ", -0.1, "Common Stock") == "non_positive_weight"
    assert va._classify_holding("NQU6", 0.1, "Index Future") == "non_equity_security_type:Index Future"
    assert va._classify_holding("USD", 0.1, "Currency") == "non_equity_security_type:Currency"
    assert va._classify_holding(None, 0.01, "Currency Collateral") == "missing_ticker"


class _FakeInvescoResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _invesco_payload(rows, effective_date="2026-07-22"):
    return {
        "effectiveBusinessDate": effective_date,
        "effectiveDate": effective_date,
        "totalNumberOfHoldings": len(rows),
        "fundName": "Invesco QQQ Trust",
        "holdings": rows,
    }


def test_fetch_qqq_top_holdings_filters_non_equity_rows_and_counts_them(monkeypatch):
    rows = [
        {"ticker": "NVDA", "issuerName": "NVIDIA Corp", "percentageOfTotalNetAssets": 8.0, "securityTypeName": "Common Stock"},
        {"ticker": "ASML", "issuerName": "ASML Holding NV", "percentageOfTotalNetAssets": 0.7, "securityTypeName": "American Depository Receipt - NY"},
        {"ticker": "USD", "issuerName": "CASH & EQUIVALENTS", "percentageOfTotalNetAssets": 0.1, "securityTypeName": "Currency"},
        {"ticker": "NQU6", "issuerName": "CME E-Mini NASDAQ 100 Index Future", "percentageOfTotalNetAssets": 0.1, "securityTypeName": "Index Future"},
        {"ticker": None, "issuerName": "CASH COLLATERAL", "percentageOfTotalNetAssets": 0.01, "securityTypeName": "Currency Collateral"},
        {"ticker": None, "issuerName": None, "percentageOfTotalNetAssets": -0.1, "securityTypeName": "Synthetic Cash"},
    ]
    monkeypatch.setattr(va.requests, "get", lambda *a, **k: _FakeInvescoResponse(_invesco_payload(rows)))

    universe = va._fetch_qqq_top_holdings()
    assert universe["status"] == "ok"
    assert universe["fallback_used"] is False
    assert universe["effective_date"] == "2026-07-22"
    assert universe["total_holdings_reported"] == 6
    assert universe["total_holdings_selected"] == 2
    assert {c["ticker"] for c in universe["constituents"]} == {"NVDA", "ASML"}
    assert universe["filtered_out_count"] == 4
    assert universe["weight_pct_sum"] == pytest.approx(8.7)
    reasons = {row["reason"] for row in universe["filtered_out"]}
    assert "non_equity_security_type:Currency" in reasons
    assert "non_equity_security_type:Index Future" in reasons
    assert "missing_ticker" in reasons


def test_fetch_qqq_top_holdings_top_n_caps_selection(monkeypatch):
    rows = [
        {"ticker": t, "issuerName": f"{t} Inc", "percentageOfTotalNetAssets": w, "securityTypeName": "Common Stock"}
        for t, w in [("NVDA", 8.0), ("AAPL", 7.0), ("MSFT", 5.0)]
    ]
    monkeypatch.setattr(va.requests, "get", lambda *a, **k: _FakeInvescoResponse(_invesco_payload(rows)))

    universe = va._fetch_qqq_top_holdings(top_n=2)
    assert [c["ticker"] for c in universe["constituents"]] == ["NVDA", "AAPL"]
    assert universe["total_holdings_selected"] == 2


def test_fetch_qqq_top_holdings_falls_back_on_error(monkeypatch):
    def _boom(*a, **k):
        raise requests.exceptions.RequestException("406 Client Error: Not Acceptable")

    monkeypatch.setattr(va.requests, "get", _boom)

    universe = va._fetch_qqq_top_holdings(top_n=3)
    assert universe["status"] == "fallback_used"
    assert universe["fallback_used"] is True
    assert universe["method"] == "static_fallback"
    assert len(universe["constituents"]) == 3
    assert universe["total_holdings_selected"] == 3
    assert universe["filtered_out_count"] == 0
    assert "406" in universe["fallback_reason"]

    universe_full = va._fetch_qqq_top_holdings()
    assert len(universe_full["constituents"]) == len(va.STATIC_FULL_FALLBACK) > 100


def test_yfinance_retry_recovers_from_transient_whole_ticker_failure(monkeypatch):
    calls = {"n": 0}

    class _FlakyTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def _value(self):
            calls["n"] += 1
            if calls["n"] <= 4:  # first attempt: all 4 fields fail
                raise RuntimeError("transient network error")
            return pd.DataFrame({"current": [1.0]}, index=pd.Index(["+1y"], name="period"))

        eps_trend = property(lambda self: self._value())
        eps_revisions = property(lambda self: self._value())
        earnings_estimate = property(lambda self: self._value())
        revenue_estimate = property(lambda self: self._value())

    monkeypatch.setattr(va.yf, "Ticker", _FlakyTicker)
    result = va._fetch_yfinance_estimates("NVDA", attempts=2, pause_seconds=0)
    assert result["status"] == "ok"
    assert result["attempts"] == 2
    assert calls["n"] == 8  # 4 failed fields on attempt 1 + 4 ok fields on attempt 2


def test_yfinance_gives_up_after_exhausting_retry_attempts(monkeypatch):
    class _AlwaysFailTicker:
        def __init__(self, ticker):
            pass

        def _boom(self):
            raise RuntimeError("still failing")

        eps_trend = property(lambda self: self._boom())
        eps_revisions = property(lambda self: self._boom())
        earnings_estimate = property(lambda self: self._boom())
        revenue_estimate = property(lambda self: self._boom())

    monkeypatch.setattr(va.yf, "Ticker", _AlwaysFailTicker)
    result = va._fetch_yfinance_estimates("NVDA", attempts=2, pause_seconds=0)
    assert result["status"] == "error"
    assert result["attempts"] == 2
    assert "still failing" in result["reason"]


def test_collection_summary_lists_failed_tickers_and_missing_fields(monkeypatch):
    monkeypatch.setattr(va, "_fetch_qqq_top_holdings", lambda top_n=None, timeout=15: _fake_universe(["NVDA", "AAPL", "MSFT"]))

    def _yf_side_effect(ticker, attempts=2, pause_seconds=1.5):
        if ticker == "NVDA":
            return _fake_yfinance_estimates_ok(ticker)
        if ticker == "AAPL":
            data = _fake_yfinance_estimates_ok(ticker)
            data["fields"]["revenue_estimate"] = {"status": "empty", "records": []}
            data["status"] = "ok"
            return data
        return {
            "source_name": "yfinance Ticker estimates modules",
            "source_authority": "third_party_unofficial",
            "collected_at_utc": "2026-07-23T00:00:00Z",
            "status": "error",
            "reason": "boom",
            "fields": {},
            "attempts": 2,
        }

    monkeypatch.setattr(va, "_fetch_yfinance_estimates", _yf_side_effect)
    monkeypatch.setattr(va, "_fetch_fmp_estimates", _fake_fmp_estimates_ok)

    payload = va.build_archive(use_fmp=True, fmp_api_key="dummy-key", request_delay_sec=0)
    summary = payload["collection_summary"]
    assert summary["ticker_count"] == 3
    assert summary["yfinance_ok_count"] == 2
    assert summary["yfinance_error_count"] == 1
    assert summary["yfinance_failed_tickers"] == ["MSFT"]
    assert summary["yfinance_missing_fields_by_ticker"] == {"AAPL": ["revenue_estimate"]}


def test_single_ticker_unexpected_exception_does_not_abort_run(monkeypatch):
    monkeypatch.setattr(va, "_fetch_qqq_top_holdings", lambda top_n=None, timeout=15: _fake_universe(["NVDA", "AAPL"]))

    def _yf_side_effect(ticker, attempts=2, pause_seconds=1.5):
        if ticker == "NVDA":
            raise RuntimeError("unexpected bug")
        return _fake_yfinance_estimates_ok(ticker)

    monkeypatch.setattr(va, "_fetch_yfinance_estimates", _yf_side_effect)
    monkeypatch.setattr(va, "_fetch_fmp_estimates", _fake_fmp_estimates_ok)

    payload = va.build_archive(use_fmp=True, fmp_api_key="dummy-key", request_delay_sec=0)
    assert payload["per_ticker"]["NVDA"]["yfinance"]["status"] == "error"
    assert payload["per_ticker"]["AAPL"]["yfinance"]["status"] == "ok"
    assert payload["collection_summary"]["yfinance_failed_tickers"] == ["NVDA"]
