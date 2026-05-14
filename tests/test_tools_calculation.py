"""Calculation logic tests for tools_L1 ~ tools_L5 pure functions."""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# tools_L4 — data cleaning / parsing helpers
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_safe_float_numeric(self):
        from tools_L4 import _safe_float
        assert _safe_float(42) == 42.0
        assert _safe_float(3.14) == 3.14
        assert _safe_float("2.5") == 2.5

    def test_safe_float_none_and_nan(self):
        from tools_L4 import _safe_float
        assert _safe_float(None) is None
        assert _safe_float("") is None
        assert _safe_float("  ") is None
        assert _safe_float(float("nan")) is None

    def test_safe_float_percent_and_comma(self):
        from tools_L4 import _safe_float
        assert _safe_float("12.5%") == 12.5
        assert _safe_float("1,234") == 1234.0
        # "1.234,56" → commas stripped → "1.23456" → float 1.23456
        assert _safe_float("1.234,56") == pytest.approx(1.23456, abs=1e-10)

    def test_safe_float_european_decimal(self):
        from tools_L4 import _safe_float
        # "1,23" pattern (comma with 1-2 digits after) → treated as decimal
        assert _safe_float("3,14") == 3.14


class TestRoundOrNone:
    def test_round_or_none_basic(self):
        from tools_L4 import _round_or_none
        assert _round_or_none(3.14159, 2) == 3.14
        assert _round_or_none(100, 0) == 100.0

    def test_round_or_none_edge_cases(self):
        from tools_L4 import _round_or_none
        assert _round_or_none(None) is None
        assert _round_or_none(float("inf")) is None
        assert _round_or_none(float("nan")) is None


class TestPercentOrNone:
    def test_percent_or_none(self):
        from tools_L4 import _percent_or_none
        assert _percent_or_none(0.0525) == 5.25
        assert _percent_or_none(5.25) == 5.25  # already > 1, no change
        assert _percent_or_none(None) is None
        assert _percent_or_none("2.5%") == 2.5


class TestExcelSerialToDate:
    def test_excel_serial_basic(self):
        from tools_L4 import _excel_serial_to_date
        # 2024-01-01 ≈ 45292 in Excel serial (1900 date system)
        result = _excel_serial_to_date(45292)
        assert result == "2024-01-01"

    def test_excel_serial_invalid(self):
        from tools_L4 import _excel_serial_to_date
        assert _excel_serial_to_date(None) is None
        assert _excel_serial_to_date(100) is None  # below 20000 threshold
        assert _excel_serial_to_date("abc") is None

    def test_excel_serial_1904(self):
        from tools_L4 import _excel_serial_to_date
        # 1904 date system: 43861 + 1462 offset = 45323 → 2024-02-01
        result = _excel_serial_to_date(43861, date1904=True)
        assert result == "2024-02-01"


class TestNormalizeLabel:
    def test_normalize_label(self):
        from tools_L4 import _normalize_label
        assert _normalize_label("  Hello   World  ") == "hello world"
        assert _normalize_label(None) == ""
        assert _normalize_label(123) == "123"


class TestXlsxColIndex:
    def test_xlsx_col_index(self):
        from tools_L4 import _xlsx_col_index
        assert _xlsx_col_index("A1") == 0
        assert _xlsx_col_index("B10") == 1
        assert _xlsx_col_index("Z5") == 25
        assert _xlsx_col_index("AA1") == 26
        assert _xlsx_col_index("AB99") == 27

    def test_xlsx_col_index_empty(self):
        from tools_L4 import _xlsx_col_index
        assert _xlsx_col_index("") == 0
        assert _xlsx_col_index(None) == 0


class TestFindColumn:
    def test_find_column_basic(self):
        from tools_L4 import _find_column
        cols = ["Date", "Close Price", "Volume", "PE Ratio"]
        assert _find_column(cols, "close") == "Close Price"
        assert _find_column(cols, "volume") == "Volume"
        assert _find_column(cols, "pe", "ratio") == "PE Ratio"

    def test_find_column_not_found(self):
        from tools_L4 import _find_column
        cols = ["Date", "Close"]
        assert _find_column(cols, "volume") is None

    def test_find_column_any_needles(self):
        from tools_L4 import _find_column
        cols = ["Earnings Per Share", "EPS (ttm)"]
        assert _find_column(cols, any_needles=["eps", "earnings"]) == "Earnings Per Share"


class TestLatestRowByDate:
    def test_latest_row_by_date_datetime_index(self):
        from tools_L4 import _latest_row_by_date
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-02"]),
            "value": [1, 3, 2],
        }).set_index("date")
        row = _latest_row_by_date(df.reset_index(), "date")
        assert row is not None
        assert row["value"] == 3

    def test_latest_row_by_date_max_date_filter(self):
        from tools_L4 import _latest_row_by_date
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-03", "2024-01-05"],
            "value": [1, 3, 5],
        })
        row = _latest_row_by_date(df, "date", max_date="2024-01-03")
        assert row is not None
        assert row["value"] == 3

    def test_latest_row_by_date_empty(self):
        from tools_L4 import _latest_row_by_date
        df = pd.DataFrame({"date": [], "value": []})
        assert _latest_row_by_date(df, "date") is None


# ---------------------------------------------------------------------------
# tools_L5 — technical indicator helpers
# ---------------------------------------------------------------------------

class TestLastValid:
    def test_last_valid_basic(self):
        from tools_L5 import _last_valid
        s = pd.Series([1, 2, 3, np.nan, 5])
        assert _last_valid(s) == 5.0

    def test_last_valid_all_nan(self):
        from tools_L5 import _last_valid
        assert _last_valid(pd.Series([np.nan, np.nan])) is None

    def test_last_valid_empty(self):
        from tools_L5 import _last_valid
        assert _last_valid(pd.Series([], dtype=float)) is None


class TestRoundValue:
    def test_round_value_basic(self):
        from tools_L5 import _round_value
        assert _round_value(3.14159) == 3.14
        assert _round_value(3.14159, 3) == 3.142

    def test_round_value_edge_cases(self):
        from tools_L5 import _round_value
        assert _round_value(None) is None
        assert _round_value(float("nan")) is None
        assert _round_value(float("inf")) is None


class TestManualVwap:
    def test_manual_vwap_basic(self):
        from tools_L5 import _manual_vwap
        n = 25
        high = pd.Series([10.0] * n)
        low = pd.Series([8.0] * n)
        close = pd.Series([9.0] * n)
        volume = pd.Series([1000] * n)
        result = _manual_vwap(high, low, close, volume, window=20)
        # VWAP = typical_price = (high + low + close) / 3 = 9.0
        # First 19 values are NaN due to rolling window
        assert result[:19].isna().all()
        assert result.iloc[19] == pytest.approx(9.0, abs=1e-10)

    def test_manual_vwap_with_volume_weighting(self):
        from tools_L5 import _manual_vwap
        high = pd.Series([12.0, 12.0, 12.0, 12.0, 12.0] * 5)
        low = pd.Series([8.0, 8.0, 8.0, 8.0, 8.0] * 5)
        close = pd.Series([10.0, 10.0, 10.0, 10.0, 10.0] * 5)
        volume = pd.Series([100, 200, 300, 400, 500] * 5)
        result = _manual_vwap(high, low, close, volume, window=5)
        # typical_price = 10.0, volume-weighted average over last 5 = 10.0
        valid = result.dropna()
        assert all(np.isclose(v, 10.0, atol=1e-10) for v in valid)


class TestManualMfi:
    def test_manual_mfi_all_up(self):
        from tools_L5 import _manual_mfi
        # Price rising every day → all positive flow → MFI = 100
        high = pd.Series([10.0 + i for i in range(20)])
        low = pd.Series([8.0 + i for i in range(20)])
        close = pd.Series([9.0 + i for i in range(20)])
        volume = pd.Series([1000.0] * 20)
        result = _manual_mfi(high, low, close, volume, window=14)
        valid = result.dropna()
        assert valid.iloc[-1] == pytest.approx(100.0, abs=1e-10)

    def test_manual_mfi_all_down(self):
        from tools_L5 import _manual_mfi
        # Price falling every day → all negative flow → MFI = 0
        high = pd.Series([20.0 - i for i in range(20)])
        low = pd.Series([18.0 - i for i in range(20)])
        close = pd.Series([19.0 - i for i in range(20)])
        volume = pd.Series([1000.0] * 20)
        result = _manual_mfi(high, low, close, volume, window=14)
        valid = result.dropna()
        assert valid.iloc[-1] == pytest.approx(0.0, abs=1e-10)

    def test_manual_mfi_range(self):
        from tools_L5 import _manual_mfi
        # Oscillating price → MFI between 0 and 100
        close = pd.Series([10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0,
                           10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 11.0])
        high = close + 1.0
        low = close - 1.0
        volume = pd.Series([1000.0] * 20)
        result = _manual_mfi(high, low, close, volume, window=14)
        valid = result.dropna()
        assert 0.0 < valid.iloc[-1] < 100.0


class TestManualCmf:
    def test_manual_cmf_basic(self):
        from tools_L5 import _manual_cmf
        # close in middle of range → multiplier = 0 → CMF = 0
        high = pd.Series([12.0] * 25)
        low = pd.Series([8.0] * 25)
        close = pd.Series([10.0] * 25)
        volume = pd.Series([1000.0] * 25)
        result = _manual_cmf(high, low, close, volume, window=20)
        valid = result.dropna()
        assert valid.iloc[-1] == pytest.approx(0.0, abs=1e-10)

    def test_manual_cmf_closing_at_high(self):
        from tools_L5 import _manual_cmf
        # close at high → multiplier = +1 → CMF = +1
        high = pd.Series([12.0] * 25)
        low = pd.Series([8.0] * 25)
        close = pd.Series([12.0] * 25)
        volume = pd.Series([1000.0] * 25)
        result = _manual_cmf(high, low, close, volume, window=20)
        valid = result.dropna()
        assert valid.iloc[-1] == pytest.approx(1.0, abs=1e-10)

    def test_manual_cmf_closing_at_low(self):
        from tools_L5 import _manual_cmf
        # close at low → multiplier = -1 → CMF = -1
        high = pd.Series([12.0] * 25)
        low = pd.Series([8.0] * 25)
        close = pd.Series([8.0] * 25)
        volume = pd.Series([1000.0] * 25)
        result = _manual_cmf(high, low, close, volume, window=20)
        valid = result.dropna()
        assert valid.iloc[-1] == pytest.approx(-1.0, abs=1e-10)


# ---------------------------------------------------------------------------
# tools_common — series analysis
# ---------------------------------------------------------------------------

class TestAnalyzeSeriesMomentumRelativity:
    def test_momentum_rising(self):
        from tools_common import analyze_series_momentum_relativity
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        }, index=dates)
        result = analyze_series_momentum_relativity(df)
        assert result["level"] == 10.0
        assert result["momentum"]["direction"] == "rising"
        assert result["momentum"]["velocity_1d"] == 1.0
        assert result["momentum"]["acceleration_1d"] == 0.0
        # percentile uses strict <, so max value gets 90.0 (9 out of 10 are smaller)
        assert result["relativity"]["percentile_1y"] == 90.0

    def test_momentum_falling(self):
        from tools_common import analyze_series_momentum_relativity
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({
            "value": [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
        }, index=dates)
        result = analyze_series_momentum_relativity(df)
        assert result["level"] == 1.0
        assert result["momentum"]["direction"] == "falling"
        assert result["momentum"]["velocity_1d"] == -1.0
        assert result["relativity"]["percentile_1y"] == 0.0  # lowest value

    def test_momentum_flat(self):
        from tools_common import analyze_series_momentum_relativity
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({
            "value": [5.0] * 10,
        }, index=dates)
        result = analyze_series_momentum_relativity(df)
        assert result["momentum"]["direction"] == "flat"
        assert result["momentum"]["velocity_1d"] == 0.0

    def test_short_history_no_10y_percentile(self):
        from tools_common import analyze_series_momentum_relativity
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        df = pd.DataFrame({
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        }, index=dates)
        result = analyze_series_momentum_relativity(df)
        assert result["relativity"]["percentile_10y"] is None
        assert "不足10年" in result["relativity"]["notes"]

    def test_empty_input(self):
        from tools_common import analyze_series_momentum_relativity
        assert analyze_series_momentum_relativity(None) == {
            "level": None, "momentum": None, "relativity": None
        }
        assert analyze_series_momentum_relativity(pd.DataFrame()) == {
            "level": None, "momentum": None, "relativity": None
        }


class TestAnalyzeSeriesMaDeviation:
    def test_ma_deviation_basic(self):
        from tools_common import analyze_series_ma_deviation
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        values = list(range(30))  # 0, 1, 2, ..., 29
        df = pd.DataFrame({"value": values}, index=dates)
        result = analyze_series_ma_deviation(df, ma_period=20)
        assert result["level"] == 29.0
        assert result["ma"] is not None
        assert "deviation_pct" in result
        assert result["position_vs_ma"] == "above"  # latest > MA

    def test_ma_deviation_short_series(self):
        from tools_common import analyze_series_ma_deviation
        df = pd.DataFrame({"value": [1.0, 2.0]}, index=pd.date_range("2024-01-01", periods=2, freq="D"))
        result = analyze_series_ma_deviation(df, ma_period=20)
        # Series too short for 20-period MA
        assert result.get("latest_ma") is None or pd.isna(result.get("latest_ma"))


class TestAnalyzeSeriesMaTrend:
    def test_ma_trend_rising(self):
        from tools_common import analyze_series_ma_trend
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        values = list(range(30))
        df = pd.DataFrame({"value": values}, index=dates)
        result = analyze_series_ma_trend(df, short_period=5, long_period=20)
        assert result["trend"] == "short_above_long"
        assert result["short_ma"] is not None
        assert result["long_ma"] is not None

    def test_ma_trend_falling(self):
        from tools_common import analyze_series_ma_trend
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        values = list(range(29, -1, -1))  # 29, 28, ..., 0
        df = pd.DataFrame({"value": values}, index=dates)
        result = analyze_series_ma_trend(df, short_period=5, long_period=20)
        assert result["trend"] == "short_below_long"


class TestAnalyzeSeriesRatioVsMa:
    def test_ratio_vs_ma_basic(self):
        from tools_common import analyze_series_ratio_vs_ma
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        values = [10.0] * 30
        df = pd.DataFrame({"value": values}, index=dates)
        result = analyze_series_ratio_vs_ma(df, ma_period=20)
        # Price equals MA → position_vs_ma = "on"
        assert result["level"] == 10.0
        assert result["ma"] == pytest.approx(10.0, abs=1e-10)
        assert result["position_vs_ma"] == "on"

    def test_ratio_vs_ma_above(self):
        from tools_common import analyze_series_ratio_vs_ma
        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        values = list(range(30))  # rising, latest above MA
        df = pd.DataFrame({"value": values}, index=dates)
        result = analyze_series_ratio_vs_ma(df, ma_period=20)
        assert result["level"] == 29.0
        assert result["position_vs_ma"] == "above"
