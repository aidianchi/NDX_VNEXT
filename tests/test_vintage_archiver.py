"""Offline tests for src/vintage_archiver.py.

These tests mock every network call (Invesco holdings, yfinance, FMP) so the
suite stays fast and deterministic. They verify:
  1. the on-disk JSON schema (top-level keys + boundary/isolation notice),
  2. idempotent same-day overwrite behavior (no duplicate files, latest wins),
  3. NaN-safe conversion of yfinance-style DataFrames to JSON records.

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

import vintage_archiver as va


def _fake_universe(tickers):
    return {
        "status": "ok",
        "method": "live_invesco_qqq_holdings_api",
        "source_name": "Invesco QQQ official holdings API",
        "source_url": va.INVESCO_QQQ_HOLDINGS_URL,
        "source_authority": "official_provider",
        "effective_date": "2026-07-10",
        "total_holdings": 108,
        "fund_name": "Invesco QQQ Trust",
        "constituents": [
            {"rank": i + 1, "ticker": t, "issuer_name": f"{t} Inc", "weight_pct": 5.0 - i, "security_type": "Common Stock"}
            for i, t in enumerate(tickers)
        ],
    }


def _fake_yfinance_estimates_ok(ticker):
    return {
        "source_name": "yfinance Ticker estimates modules",
        "source_authority": "third_party_unofficial",
        "collected_at_utc": "2026-07-12T00:00:00Z",
        "status": "ok",
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
    for key in ["schema_version", "archive_date", "collected_at_utc", "purpose", "universe", "per_ticker"]:
        assert key in on_disk

    assert on_disk["schema_version"] == va.SCHEMA_VERSION
    assert "evidence_ref" in on_disk["purpose"]
    assert "L1-L5" in on_disk["purpose"]

    assert set(on_disk["per_ticker"].keys()) == {"NVDA", "AAPL"}
    nvda = on_disk["per_ticker"]["NVDA"]
    assert nvda["yfinance"]["status"] == "ok"
    assert nvda["yfinance"]["fields"]["eps_trend"]["records"][0]["current"] == pytest.approx(12.76383)
    assert nvda["fmp"]["status"] == "ok"
    assert nvda["fmp"]["raw_response"][0]["epsAvg"] == pytest.approx(22.1)


def test_same_day_rerun_overwrites_not_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(va, "_fetch_qqq_top_holdings", lambda top_n=15, timeout=15: _fake_universe(["NVDA"]))
    monkeypatch.setattr(va, "_fetch_yfinance_estimates", _fake_yfinance_estimates_ok)
    monkeypatch.setattr(va, "_fetch_fmp_estimates", _fake_fmp_estimates_ok)

    payload1 = va.build_archive(use_fmp=True, fmp_api_key="dummy-key", request_delay_sec=0)
    path1 = va.write_archive(payload1, archive_root=str(tmp_path))
    day_dir = os.path.dirname(path1)
    assert os.listdir(day_dir) == ["eps_consensus.json"]

    # Second run same (mocked) day, different fake data -> must overwrite, not accumulate.
    def _fake_yfinance_estimates_changed(ticker):
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
