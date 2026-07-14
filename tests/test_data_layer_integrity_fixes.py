import inspect
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L1
import tools_L2
import tools_L3
from agent_analysis.packet_builder import AnalysisPacketBuilder
from data_manager import calculate_long_term_stats
from tools_common import TICKER_REPLACEMENTS, HistoricalUniverseUnavailable


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


def test_ndx100_components_backtest_raises_and_never_touches_current_universe_strategies(monkeypatch):
    """Backtest mode must only trust the historical ticker-history library. If that
    library fails, get_ndx100_components must raise HistoricalUniverseUnavailable and
    must never fall through to the Nasdaq API / Wikipedia / GitHub-live / static
    fallback strategies, since any of those would silently inject the *current*
    NDX100 roster into a historical calculation (survivorship bias)."""
    import nasdaq_100_ticker_history

    def boom(year, month, day):
        raise RuntimeError("synthetic historical library failure")

    monkeypatch.setattr(nasdaq_100_ticker_history, "tickers_as_of", boom)
    monkeypatch.setattr(
        tools_L3.requests,
        "get",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("current-universe network strategy should not run for a backtest request")
        ),
    )

    try:
        tools_L3.get_ndx100_components_with_provenance(end_date="2025-04-09")
        assert False, "expected HistoricalUniverseUnavailable to be raised"
    except HistoricalUniverseUnavailable as exc:
        assert exc.end_date == "2025-04-09"

    # The thin get_ndx100_components() wrapper must propagate the same exception.
    try:
        tools_L3.get_ndx100_components(end_date="2025-04-09")
        assert False, "expected HistoricalUniverseUnavailable to be raised"
    except HistoricalUniverseUnavailable:
        pass


def test_ndx100_components_historical_success_path_is_unchanged(monkeypatch):
    import nasdaq_100_ticker_history

    def fake_tickers_as_of(year, month, day):
        return ["AAA", "BBB", "CCC"]

    monkeypatch.setattr(nasdaq_100_ticker_history, "tickers_as_of", fake_tickers_as_of)

    tickers, provenance = tools_L3.get_ndx100_components_with_provenance(end_date="2025-04-09")

    assert tickers == ["AAA", "BBB", "CCC"]
    assert provenance["universe_source"] == "historical_library"
    assert provenance["as_of"] == "2025-04-09"
    assert provenance["count"] == 3

    # get_ndx100_components() keeps its original signature/return type (a plain list).
    assert tools_L3.get_ndx100_components(end_date="2025-04-09") == ["AAA", "BBB", "CCC"]


def test_ndx100_components_live_mode_reports_nasdaq_api_provenance(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"data": {"rows": [{"symbol": f"TCK{i}"} for i in range(95)]}}}

    monkeypatch.setattr(tools_L3.requests, "get", lambda *a, **kw: FakeResponse())

    tickers, provenance = tools_L3.get_ndx100_components_with_provenance(end_date=None)

    assert provenance["universe_source"] == "nasdaq_api"
    assert provenance["count"] == len(tickers) == 95


def test_advance_decline_line_reports_honest_unavailable_when_historical_universe_fails(monkeypatch):
    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)

    def raise_unavailable(effective_date, historical_date=None, **kwargs):
        raise HistoricalUniverseUnavailable("synthetic_failure", historical_date)

    monkeypatch.setattr(tools_L2, "_get_ndx100_common_price_data", raise_unavailable)

    result = tools_L2.get_advance_decline_line("2025-04-09")

    assert result["availability"] == "unavailable"
    assert result["unavailable_reason"] == "historical_universe_unavailable"
    assert "historical_universe_unavailable" in result["data_quality"]["anomalies"]
    assert "current_universe_not_used" in result["data_quality"]["anomalies"]


def test_advance_decline_line_surfaces_universe_provenance_in_data_quality(monkeypatch):
    monkeypatch.setattr(tools_L2, "YF_AVAILABLE", True)

    dates = pd.date_range("2025-01-01", periods=260, freq="B")
    close = pd.DataFrame(
        {
            "AAA": range(100, 360),
            "BBB": range(200, 460),
            "CCC": list(range(360, 100, -1)),
        },
        index=dates,
        dtype=float,
    )
    panel = pd.concat({"Close": close}, axis=1)
    panel.attrs["universe_provenance"] = {
        "universe_source": "nasdaq_api",
        "as_of": "2025-12-31",
        "retrieved_at": "2025-12-31T00:00:00Z",
        "count": 3,
    }

    monkeypatch.setattr(
        tools_L2,
        "_get_ndx100_common_price_data",
        lambda effective_date, **kwargs: (["AAA", "BBB", "CCC"], panel),
    )

    result = tools_L2.get_advance_decline_line("2025-12-31")

    assert result["availability"] == "available"
    assert result["data_quality"]["universe_provenance"]["universe_source"] == "nasdaq_api"
