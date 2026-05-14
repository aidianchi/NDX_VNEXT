# tests/test_chart_modules.py
"""Smoke tests for chart_adapter_v6.py and chart_generator.py pure functions."""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# chart_adapter_v6
# ---------------------------------------------------------------------------

def _sample_price_df(n: int = 50) -> pd.DataFrame:
    """Generate a small price DataFrame for testing."""
    dates = pd.date_range(end=datetime.now(), periods=n, freq="D")
    base = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "date": dates,
        "open": base - 0.5,
        "high": base + 1.0,
        "low": base - 1.0,
        "close": base,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    })


def test_calculate_macd_basic():
    from chart_adapter_v6 import calculate_macd

    df = _sample_price_df(60)
    result = calculate_macd(df)

    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert list(result.columns) == ["date", "macd", "signal", "histogram"]
    assert len(result) <= len(df)


def test_calculate_macd_empty_input():
    from chart_adapter_v6 import calculate_macd

    assert calculate_macd(None).empty
    assert calculate_macd(pd.DataFrame()).empty
    assert calculate_macd(pd.DataFrame({"date": [1, 2]})).empty  # no 'close'


def test_calculate_obv_basic():
    from chart_adapter_v6 import calculate_obv

    df = _sample_price_df(30)
    result = calculate_obv(df)

    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert "obv" in result.columns
    assert "value" in result.columns
    # OBV should have same length as input (no dropna)
    assert len(result) == len(df)


def test_calculate_obv_empty_input():
    from chart_adapter_v6 import calculate_obv

    assert calculate_obv(None).empty
    assert calculate_obv(pd.DataFrame()).empty


def test_calculate_volume_analysis_basic():
    from chart_adapter_v6 import calculate_volume_analysis

    df = _sample_price_df(30)
    result = calculate_volume_analysis(df)

    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert list(result.columns) == ["date", "volume", "volume_ma20"]
    # First 19 rows dropped due to rolling window
    assert len(result) == len(df) - 19


def test_calculate_donchian_channels_basic():
    from chart_adapter_v6 import calculate_donchian_channels

    df = _sample_price_df(30)
    result = calculate_donchian_channels(df, period=10)

    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert list(result.columns) == ["date", "close", "upper_band", "lower_band"]
    # First 9 rows dropped
    assert len(result) == len(df) - 9
    # Upper band should always be >= lower band
    assert (result["upper_band"] >= result["lower_band"]).all()


# ---------------------------------------------------------------------------
# chart_generator
# ---------------------------------------------------------------------------

def test_calculate_percentiles_from_data():
    from chart_generator import calculate_percentiles_from_data

    df = pd.DataFrame({"value": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
    result = calculate_percentiles_from_data(df)

    assert isinstance(result, dict)
    assert set(result.keys()) == {"p10", "p25", "p50", "p75", "p90"}
    assert result["p10"] == pytest.approx(1.9, abs=0.1)
    assert result["p50"] == 5.5
    assert result["p90"] == pytest.approx(9.1, abs=0.1)


def test_calculate_percentiles_empty_input():
    from chart_generator import calculate_percentiles_from_data

    assert calculate_percentiles_from_data(None) == {}
    assert calculate_percentiles_from_data(pd.DataFrame()) == {}
    assert calculate_percentiles_from_data(pd.DataFrame({"other": [1, 2]})) == {}


def test_apply_series_transform_zscore():
    from chart_generator import _apply_series_transform

    s = pd.Series([1, 2, 3, 4, 5])
    result = _apply_series_transform(s, "zscore")

    assert len(result) == len(s)
    assert result.mean() == pytest.approx(0, abs=1e-10)
    assert result.std(ddof=0) == pytest.approx(1, abs=1e-10)


def test_apply_series_transform_minmax():
    from chart_generator import _apply_series_transform

    s = pd.Series([10, 20, 30])
    result = _apply_series_transform(s, "minmax")

    assert result.min() == pytest.approx(0, abs=1e-10)
    assert result.max() == pytest.approx(1, abs=1e-10)


def test_apply_series_transform_index_100():
    from chart_generator import _apply_series_transform

    s = pd.Series([50, 100, 150])
    result = _apply_series_transform(s, "index_100")

    assert result.iloc[0] == pytest.approx(100, abs=1e-10)
    assert result.iloc[1] == pytest.approx(200, abs=1e-10)


def test_apply_series_transform_unknown_returns_original():
    from chart_generator import _apply_series_transform

    s = pd.Series([1, 2, 3])
    result = _apply_series_transform(s, "unknown_transform")
    pd.testing.assert_series_equal(result, s)


def test_apply_series_transform_empty():
    from chart_generator import _apply_series_transform

    assert _apply_series_transform(None, "zscore") is None
    assert _apply_series_transform(pd.Series([], dtype=float), "zscore").empty


import pytest  # noqa: E402
