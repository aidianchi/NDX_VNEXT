import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L5
import tools_common


def _ohlcv_frame(periods=260):
    dates = pd.date_range("2025-01-01", periods=periods, freq="B")
    close = pd.Series(range(100, 100 + periods), index=dates, dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": pd.Series(range(1_000_000, 1_000_000 + periods), index=dates, dtype=float),
        },
        index=dates,
    )


def test_l5_formula_layer_keeps_core_fields_and_adds_price_volume_quality():
    indicators = tools_L5.calculate_technical_indicators_yf(_ohlcv_frame())

    assert indicators["current_price"] == 359.0
    assert indicators["formula_engine"] in {"ta", "internal_fallback"}
    assert indicators["sma_50"] is not None
    assert indicators["sma_200"] is not None
    assert indicators["rsi_14"] is not None
    assert indicators["macd_histogram"] is not None
    assert indicators["donchian_position_pct"] is not None
    assert indicators["vwap_20"] is not None
    assert indicators["price_vs_vwap_20"] in {"above", "below"}
    assert indicators["mfi_14"] is not None
    assert indicators["mfi_status"] in {"overbought", "oversold", "neutral"}
    assert indicators["cmf_20"] is not None
    assert indicators["cmf_status"] in {"accumulation", "distribution", "neutral"}
    assert indicators["adx_14"] is not None
    assert indicators["pdi_14"] is not None
    assert indicators["mdi_14"] is not None
    assert indicators["adx_trend_strength"] in {"strong", "weak_or_range"}


def test_l5_formula_layer_calculates_adx_without_ta_library(monkeypatch):
    monkeypatch.setattr(tools_L5, "TA_LIB_AVAILABLE", False)

    indicators = tools_L5.calculate_technical_indicators_yf(_ohlcv_frame())

    assert indicators["formula_engine"] == "internal_fallback"
    assert indicators["adx_14"] is not None
    assert indicators["pdi_14"] is not None
    assert indicators["mdi_14"] is not None
    assert indicators["adx_direction"] in {"up", "down", "neutral"}


def test_l5_price_volume_quality_reuses_technical_indicator_payload(monkeypatch):
    monkeypatch.setattr(
        tools_L5,
        "get_qqq_technical_indicators",
        lambda end_date=None: {
            "date": "2026-05-01",
            "source_name": "unit-test",
            "value": {
                "vwap_20": 350.0,
                "price_vs_vwap_20": "above",
                "vwap_deviation_pct": 1.2,
                "mfi_14": 72.0,
                "mfi_status": "neutral",
                "cmf_20": 0.08,
                "cmf_status": "accumulation",
            },
        },
    )

    result = tools_L5.get_price_volume_quality_qqq()

    assert result["value"]["vwap_20"] == 350.0
    assert result["value"]["cmf_status"] == "accumulation"
    assert result["source_name"] == "unit-test"
    assert "不单独给买卖结论" in result["notes"]


def test_l5_yfinance_requests_include_effective_date_for_daily_history(monkeypatch):
    captured = {}
    frame = _ohlcv_frame()
    frame.index = pd.bdate_range(end="2025-04-09", periods=len(frame))
    frame.attrs["source_name"] = "Twelve Data"
    frame.attrs["market_data_source"] = "twelve_data_priority"

    def fake_download(ticker, **kwargs):
        captured["ticker"] = ticker
        captured["end"] = kwargs.get("end")
        return frame.copy()

    monkeypatch.setattr(tools_L5, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L5, "cached_yf_download", fake_download)

    result = tools_L5.get_qqq_technical_indicators("2025-04-09")

    assert captured["ticker"] == "QQQ"
    assert pd.Timestamp(captured["end"]).date().isoformat() == "2025-04-10"
    assert result["date"] == "2025-04-09"
    assert result["source_name"] == "Twelve Data"


def test_l5_multi_scale_ma_requests_include_effective_date(monkeypatch):
    captured = {}
    frame = _ohlcv_frame()
    frame.index = pd.bdate_range(end="2025-04-09", periods=len(frame))
    frame.attrs["source_name"] = "Twelve Data"

    def fake_download(ticker, **kwargs):
        captured["end"] = kwargs.get("end")
        return frame.copy()

    monkeypatch.setattr(tools_L5, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_L5, "cached_yf_download", fake_download)

    result = tools_L5.get_multi_scale_ma_position("2025-04-09")

    assert pd.Timestamp(captured["end"]).date().isoformat() == "2025-04-10"
    assert result["value"]["date"] == "2025-04-09"
    assert result["source_name"] == "Twelve Data"


def test_pandas_datareader_fred_fallback_normalizes_to_date_value(monkeypatch):
    dates = pd.to_datetime(["2025-01-01", "2025-01-02"])

    class FakePDR:
        @staticmethod
        def DataReader(symbol, source, start, end):
            assert symbol == "DGS10"
            assert source == "fred"
            return pd.DataFrame({"DGS10": [4.1, 4.2]}, index=dates)

    monkeypatch.setattr(tools_common, "PANDAS_DATAREADER_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "pdr_data", FakePDR)
    monkeypatch.setattr(tools_common, "get_fred_api_key", lambda: "")

    df = tools_common._fetch_fred_series("DGS10", start_date="2025-01-01")

    assert list(df.columns) == ["date", "value"]
    assert df["date"].dt.strftime("%Y-%m-%d").tolist() == ["2025-01-01", "2025-01-02"]
    assert df["value"].tolist() == [4.1, 4.2]


def test_safe_request_exposes_structured_timeout_reason(monkeypatch):
    def fake_get(*_args, **_kwargs):
        raise tools_common.requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(tools_common.requests, "get", fake_get)
    monkeypatch.setattr(tools_common.time, "sleep", lambda *_args, **_kwargs: None)

    error = {}
    result = tools_common.safe_request("https://example.test", retry_count=1, error_out=error)

    assert result is None
    assert error["reason"] == "timeout"
    assert error["exception_type"] == "Timeout"
    assert tools_common.get_safe_request_last_error()["reason"] == "timeout"


def test_fred_series_primary_api_success_records_quality(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "observations": [
                    {"date": "2025-01-01", "value": "4.1"},
                    {"date": "2025-01-02", "value": "."},
                    {"date": "2025-01-03", "value": "4.2"},
                ]
            }

    monkeypatch.setattr(tools_common, "get_fred_api_key", lambda: "test-key")
    monkeypatch.setattr(tools_common.requests, "get", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(tools_common.time, "sleep", lambda *_args, **_kwargs: None)

    df = tools_common.get_fred_series("DGS10", days=10, end_date="2025-01-10")

    assert df is not None
    assert df["value"].tolist() == [4.1, 4.2]
    assert df.attrs["data_quality"]["source_tier"] == "official_api"
    assert df.attrs["data_quality"]["fallback_chain"] == ["fred_api"]


def test_fred_series_api_failure_uses_keyless_csv_fallback(monkeypatch):
    class FakeCsvResponse:
        text = "observation_date,DGS10\n2025-01-01,4.1\n2025-01-02,.\n2025-01-03,4.2\n"

        def raise_for_status(self):
            return None

    def fake_get(url, *_args, **_kwargs):
        if "fredgraph.csv" in url:
            return FakeCsvResponse()
        raise tools_common.requests.exceptions.ConnectionError("NameResolutionError DNS failure")

    monkeypatch.setattr(tools_common, "get_fred_api_key", lambda: "test-key")
    monkeypatch.setattr(tools_common, "PANDAS_DATAREADER_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "pdr_data", None)
    monkeypatch.setattr(tools_common.requests, "get", fake_get)
    monkeypatch.setattr(tools_common.time, "sleep", lambda *_args, **_kwargs: None)

    df = tools_common.get_fred_series("DGS10", days=10, end_date="2025-01-10")

    assert df is not None
    assert df["date"].dt.strftime("%Y-%m-%d").tolist() == ["2025-01-01", "2025-01-03"]
    assert df["value"].tolist() == [4.1, 4.2]
    quality = df.attrs["data_quality"]
    assert quality["source_tier"] == "official_keyless_csv"
    assert quality["fallback_chain"] == [
        "fred_api_failed",
        "pandas_datareader_unavailable",
        "fredgraph_csv",
    ]
    assert quality["fallback_failures"][0]["reason"] == "dns_error"


def test_fred_series_all_channels_failed_records_diagnostics(monkeypatch):
    def fake_get(url, *_args, **_kwargs):
        if "fredgraph.csv" in url:
            raise tools_common.requests.exceptions.ConnectionError("connection refused")
        raise tools_common.requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(tools_common, "get_fred_api_key", lambda: "test-key")
    monkeypatch.setattr(tools_common, "PANDAS_DATAREADER_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "pdr_data", None)
    monkeypatch.setattr(tools_common.requests, "get", fake_get)
    monkeypatch.setattr(tools_common.time, "sleep", lambda *_args, **_kwargs: None)

    df = tools_common.get_fred_series("FEDFUNDS", days=10, end_date="2025-01-10")
    diagnostics = tools_common.get_fred_series_diagnostics("FEDFUNDS")

    assert df is None
    assert diagnostics["availability"] == "unavailable"
    assert diagnostics["failure_type"] == "connection_error"
    assert diagnostics["fallback_chain"] == [
        "fred_api_failed",
        "pandas_datareader_unavailable",
        "fredgraph_csv_failed",
    ]
    assert diagnostics["fallback_failures"][0]["reason"] == "timeout"
