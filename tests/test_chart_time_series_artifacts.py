import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chart_time_series_artifacts import DEFAULT_CHART_LOOKBACK_DAYS, build_chart_time_series_artifact, write_chart_time_series_artifact


class _MiniFrame:
    empty = False

    def __init__(self, rows=None):
        self.rows = rows or [
            {
                "date": _Date("2026-05-01"),
                "open": 100,
                "high": 103,
                "low": 99,
                "close": 102,
                "volume": 1000,
            },
            {
                "date": _Date("2026-05-04"),
                "open": 102,
                "high": 106,
                "low": 101,
                "close": 105,
                "volume": 1400,
            },
        ]

    def iterrows(self):
        for index, row in enumerate(self.rows):
            yield index, row


class _Date:
    def __init__(self, text):
        self.text = text

    def strftime(self, _format):
        return self.text


def _ohlcv_frame(count=40):
    rows = []
    for index in range(count):
        close = 100 + index
        rows.append(
            {
                "date": _Date(f"2026-04-{index + 1:02d}"),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": 1000 + index * 10,
            }
        )
    return _MiniFrame(rows)


def _value_frame(values):
    return _MiniFrame(
        [
            {
                "date": _Date(f"2026-05-{index + 1:02d}"),
                "value": value,
            }
            for index, value in enumerate(values)
        ]
    )


def test_write_chart_time_series_artifact_persists_qqq_rows(tmp_path: Path):
    output_path = write_chart_time_series_artifact(
        tmp_path,
        fetcher=lambda lookback_days: _MiniFrame(),
        generated_at="2026-05-05T00:00:00Z",
    )
    payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path == str(tmp_path / "chart_time_series.json")
    assert payload["schema_version"] == "vnext_chart_time_series_v1"
    assert payload["generated_at_utc"] == "2026-05-05T00:00:00Z"
    assert payload["series"]["QQQ_OHLCV"]["source_file"] == "chart_time_series.json"
    assert payload["series"]["QQQ_OHLCV"]["rows"][1]["time"] == "2026-05-04"
    assert payload["series"]["QQQ_OHLCV"]["rows"][1]["ma5"] == 103.5


def test_chart_time_series_artifact_adds_workbench_modules_and_research_series():
    payload = build_chart_time_series_artifact(
        fetcher=lambda lookback_days: _ohlcv_frame(),
        generated_at="2026-05-05T00:00:00Z",
        supplemental_fetchers={
            "VIX": lambda lookback_days: _value_frame([17.1, 18.2]),
            "VXN": lambda lookback_days: _value_frame([22.0, 23.0]),
            "HY_OAS": lambda lookback_days: _value_frame([2.8, 2.7]),
            "IG_OAS": lambda lookback_days: _value_frame([0.81, 0.8]),
            "HY_QUALITY_SPREAD": lambda lookback_days: _value_frame([6.1, 6.2]),
            "US10Y": lambda lookback_days: _value_frame([4.4, 4.35]),
            "US10Y_REAL": lambda lookback_days: _value_frame([2.1, 2.05]),
            "US10Y_BREAKEVEN": lambda lookback_days: _value_frame([2.3, 2.28]),
            "QQQ_QQEW_RATIO": lambda lookback_days: _value_frame([4.7, 4.8]),
            "NET_LIQUIDITY": lambda lookback_days: _value_frame([6100, 6120]),
            "WALCL": lambda lookback_days: _value_frame([7600, 7610]),
            "TGA": lambda lookback_days: _value_frame([600, 590]),
            "RRP": lambda lookback_days: _value_frame([900, 900]),
            "M2_YOY": lambda lookback_days: _value_frame([4.4, 4.5]),
        },
        analysis_packet={
            "raw_data": {
                "L4": {
                    "get_damodaran_us_implied_erp": {
                        "value": {
                            "monthly_series": [
                                {"data_date": "2026-04-01", "erp_t12m_adjusted_payout": 4.1},
                                {"data_date": "2026-05-01", "erp_t12m_adjusted_payout": 4.24},
                            ]
                        }
                    }
                }
            }
        },
    )

    assert payload["workbench_modules"]["price_technical"]["layer_tags"] == ["L5"]
    assert "VIX" in payload["workbench_modules"]["volatility_credit"]["series"]
    assert "HY_QUALITY_SPREAD" in payload["workbench_modules"]["volatility_credit"]["series"]
    assert "DAMODARAN_ERP_MONTHLY" in payload["workbench_modules"]["rates_valuation"]["series"]
    assert payload["series"]["VIX"]["rows"][1] == {"time": "2026-05-02", "value": 18.2}
    assert payload["series"]["HY_QUALITY_SPREAD"]["rows"][1]["value"] == 6.2
    assert payload["series"]["DAMODARAN_ERP_MONTHLY"]["rows"][1]["value"] == 4.24
    latest_qqq = payload["series"]["QQQ_OHLCV"]["rows"][-1]
    assert payload["series"]["QQQ_OHLCV"]["lookback_days"] == DEFAULT_CHART_LOOKBACK_DAYS
    for key in [
        "bb_upper",
        "bb_lower",
        "donchian_upper",
        "donchian_lower",
        "vwap20",
        "obv",
        "macd",
        "macd_signal",
        "macd_histogram",
        "rsi14",
        "atr14",
        "mfi14",
        "cmf20",
    ]:
        assert key in latest_qqq
