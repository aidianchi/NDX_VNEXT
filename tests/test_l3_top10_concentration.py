import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L3
from agent_analysis.packet_builder import AnalysisPacketBuilder


def test_invesco_holdings_fetch_uses_browser_headers(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"holdings": [{"ticker": "MSFT", "percentageOfTotalNetAssets": 8.1}]}

    def fake_get(url, headers=None, timeout=None, proxies=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(tools_L3.requests, "get", fake_get)

    payload, error = tools_L3._fetch_invesco_qqq_holdings()

    assert error is None
    assert payload["holdings"][0]["ticker"] == "MSFT"
    assert captured["url"] == tools_L3.INVESCO_QQQ_HOLDINGS_URL
    assert "Mozilla/5.0" in captured["headers"]["User-Agent"]
    assert captured["headers"]["Accept"] == "application/json, text/plain, */*"
    assert captured["headers"]["Origin"] == "https://www.invesco.com"
    assert captured["headers"]["Referer"] == "https://www.invesco.com/qqq-etf/en/about.html"
    assert captured["timeout"] == 12


def test_qqq_top10_concentration_parses_invesco_holdings(monkeypatch):
    holdings = [
        {"ticker": f"T{i}", "issuerName": f"Company {i}", "percentageOfTotalNetAssets": weight}
        for i, weight in enumerate([9, 8, 7, 6, 5, 4, 3, 2, 1.5, 1, 0.5], start=1)
    ]

    monkeypatch.setattr(
        tools_L3,
        "_fetch_invesco_qqq_holdings",
        lambda: (
            {
                "effectiveDate": "2026-05-07",
                "effectiveBusinessDate": "2026-05-07",
                "totalNumberOfHoldings": 100,
                "holdings": holdings,
            },
            None,
        ),
    )
    monkeypatch.setattr(tools_L3, "_concentration_weight_change_proxy", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tools_L3,
        "_qqq_equal_weight_performance_spread",
        lambda *args, **kwargs: {"availability": "available", "windows": {"1m": {"market_cap_minus_equal_weight_pct": 2.4}}},
    )

    result = tools_L3.get_qqq_top10_concentration()
    value = result["value"]

    assert result["source_tier"] == "official_provider"
    assert value["effective_date"] == "2026-05-07"
    assert value["top10_weight_pct"] == 46.5
    assert value["equal_weight_top10_baseline_pct"] == 10.0
    assert value["top10_excess_vs_equal_weight_pct_points"] == 36.5
    assert len(value["top10_holdings"]) == 10
    assert value["market_cap_vs_equal_weight"]["windows"]["1m"]["market_cap_minus_equal_weight_pct"] == 2.4


def test_l3_state_can_use_top10_concentration_as_structural_warning():
    data = {
        "timestamp_utc": "2026-05-09T00:00:00Z",
        "indicators": [
            {
                "layer": 3,
                "metric_name": "QQQ Top10 Concentration",
                "function_id": "get_qqq_top10_concentration",
                "raw_data": {
                    "name": "QQQ Top10 Concentration",
                    "value": {"top10_weight_pct": 52.0},
                },
                "collection_timestamp_utc": "2026-05-09T00:00:01Z",
            }
        ],
    }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})

    assert packet.facts_by_layer["L3"].state == "deteriorating"
