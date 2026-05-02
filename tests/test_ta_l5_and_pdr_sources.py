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
