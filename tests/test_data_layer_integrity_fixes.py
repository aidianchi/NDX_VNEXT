import inspect
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L1
import tools_L3
from agent_analysis.packet_builder import AnalysisPacketBuilder
from data_manager import calculate_long_term_stats
from tools_common import TICKER_REPLACEMENTS


def test_long_term_stats_anchors_to_as_of_date_and_drops_future_rows():
    frame = pd.DataFrame(
        {
            "date": [
                "2019-12-31",
                "2020-12-31",
                "2021-12-31",
                "2022-12-31",
                "2023-12-31",
                "2024-12-31",
                "2025-04-09",
                "2026-06-09",
            ],
            "value": [1, 2, 3, 4, 5, 6, 7, 100],
        }
    )

    stats = calculate_long_term_stats(frame, 50, as_of_date="2025-04-09")

    assert stats["window_anchor_date"] == "2025-04-09"
    assert stats["percentile_5y"] == 1.0
    assert stats["percentile_10y"] == 1.0
    assert math.isfinite(stats["z_score_10y"])


def test_googl_is_not_silently_replaced_with_goog():
    assert "GOOGL" not in TICKER_REPLACEMENTS


def test_qqq_top10_concentration_does_not_use_current_holdings_for_backtest(monkeypatch):
    monkeypatch.setattr(
        tools_L3,
        "_fetch_invesco_qqq_holdings",
        lambda: (_ for _ in ()).throw(AssertionError("current holdings fetch should not run")),
    )

    result = tools_L3.get_qqq_top10_concentration(end_date="2025-04-09")

    assert result["source_tier"] == "unavailable"
    assert result["value"] is None
    assert "live_current_holdings_not_used" in result["data_quality"]["anomalies"]


def test_m7_alpha_vantage_fallback_normalizes_percent_units(monkeypatch):
    monkeypatch.setattr(tools_L3, "YF_AVAILABLE", False)
    monkeypatch.setattr(tools_L3, "M7_TICKERS", ["DECIMAL", "WHOLE", "PCTTEXT"])
    monkeypatch.setattr(tools_L3, "get_alphavantage_api_key", lambda: "demo")
    monkeypatch.setattr(tools_L3.time, "sleep", lambda *_args, **_kwargs: None)

    overview_by_symbol = {
        "DECIMAL": {"ReturnOnEquity": "0.25", "GrossMargin": "0.60", "OperatingMargin": "0.20", "ProfitMargin": "0.18"},
        "WHOLE": {"ReturnOnEquity": "25", "GrossMargin": "60", "OperatingMargin": "20", "ProfitMargin": "18"},
        "PCTTEXT": {"ReturnOnEquity": "25%", "GrossMargin": "60%", "OperatingMargin": "20%", "ProfitMargin": "18%"},
    }

    def fake_safe_request(_url, params):
        if params["function"] == "OVERVIEW":
            return {
                "Symbol": params["symbol"],
                "PERatio": "20",
                "ForwardPE": "18",
                "PEGRatio": "1.5",
                "EPS": "5",
                "MarketCapitalization": "1000000000",
                "52WeekHigh": "120",
                "52WeekLow": "80",
                **overview_by_symbol[params["symbol"]],
            }
        return {"Time Series (Daily)": {"2026-05-01": {"4. close": "100"}}}

    monkeypatch.setattr(tools_L3, "safe_request", fake_safe_request)

    result = tools_L3.get_m7_fundamentals()

    for symbol in ["DECIMAL", "WHOLE", "PCTTEXT"]:
        row = result["value"][symbol]
        assert row["ROE"] == 25.0
        assert row["GrossMargin"] == 60.0
        assert row["OperatingMargin"] == 20.0
        assert row["ProfitMargin"] == 18.0


def test_sofr_text_does_not_describe_unsecured_interbank_lending():
    source = inspect.getsource(tools_L1.get_sofr_rate)
    assert "无担保" not in source
    assert "以美国国债为抵押" in source


def test_l2_fear_greed_cannot_set_layer_state_without_hard_confirmation():
    def build_l2(metrics):
        data = {
            "timestamp_utc": "2026-05-01T00:00:00Z",
            "indicators": [
                {
                    "layer": 2,
                    "metric_name": name,
                    "function_id": function_id,
                    "raw_data": {"name": name, "value": value},
                    "collection_timestamp_utc": "2026-05-01T00:00:01Z",
                }
                for function_id, name, value in metrics
            ],
        }
        return AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})

    greedy = build_l2([("get_cnn_fear_greed_index", "CNN Fear & Greed Index", {"score": 85})])
    fearful = build_l2([("get_cnn_fear_greed_index", "CNN Fear & Greed Index", {"score": 15})])
    confirmed_stress = build_l2(
        [
            ("get_cnn_fear_greed_index", "CNN Fear & Greed Index", {"score": 15}),
            ("get_vix", "VIX", {"level": 21}),
        ]
    )
    calm_confirmed = build_l2(
        [
            ("get_vix", "VIX", {"level": 14}),
            ("get_hy_oas_bp", "HY OAS", {"level": 300}),
        ]
    )

    assert greedy.facts_by_layer["L2"].state == "neutral"
    assert fearful.facts_by_layer["L2"].state == "neutral"
    assert confirmed_stress.facts_by_layer["L2"].state == "risk_off"
    assert calm_confirmed.facts_by_layer["L2"].state == "risk_on"
