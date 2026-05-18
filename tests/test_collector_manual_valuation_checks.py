import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import manual_data
import core.collector as collector_module
from core.collector import DataCollector


def test_manual_ndx_valuation_keeps_live_third_party_checks(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {
            "active": True,
            "metrics": {
                "get_ndx_pe_and_earnings_yield": {
                    "name": "NDX Valuation (Manual)",
                    "value": {"PE_TTM": 36.6},
                    "data_quality": {"source_disagreement": {}},
                }
            },
        },
    )
    monkeypatch.setattr(manual_data, "has_meaningful_manual_override", lambda metric: True)
    monkeypatch.setattr(
        "tools_L4.get_ndx_valuation_third_party_checks",
        lambda: [
            {
                "source_id": "worldperatio_pe",
                "metric": "ndx_trailing_pe",
                "value": 32.66,
                "availability": "available",
            },
            {
                "source_id": "trendonify_forward_pe",
                "metric": "ndx_forward_pe",
                "value": 23.8,
                "availability": "available",
                "browser_sidecar": {"user_trusted": True},
            },
        ],
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_ndx_pe_and_earnings_yield"]}

    data = collector.run()
    raw = data["indicators"][0]["raw_data"]

    assert raw["value"]["PE_TTM"] == 36.6
    assert raw["value"]["ThirdPartyChecks"][0]["source_id"] == "worldperatio_pe"
    assert raw["data_quality"]["source_disagreement"]["trendonify_forward_pe"]["browser_sidecar"]["user_trusted"] is True
    assert "Manual valuation values remain primary" in raw["manual_override_note"]


def test_manual_confidence_only_falls_back_to_live_source(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {
            "active": True,
            "metrics": {
                "get_ndx_pe_and_earnings_yield": {
                    "name": "NDX Valuation (Manual)",
                    "value": {},
                    "source_name": "Wind",
                    "data_quality": {"coverage": {"confidence": "high"}},
                }
            },
        },
    )
    monkeypatch.setitem(
        collector_module.TOOLS_REGISTRY,
        "get_ndx_pe_and_earnings_yield",
        lambda end_date=None: {"name": "NDX Valuation (Live)", "value": {"PE_TTM": 35.0}, "source_name": "live"},
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_ndx_pe_and_earnings_yield"]}

    data = collector.run()
    raw = data["indicators"][0]["raw_data"]

    assert raw["source_name"] == "live"
    assert raw["value"]["PE_TTM"] == 35.0


def test_backtest_skips_yfinance_component_valuation_without_manual_override(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {"active": False, "metrics": {}},
    )
    monkeypatch.setitem(
        collector_module.TOOLS_REGISTRY,
        "get_ndx_pe_and_earnings_yield",
        lambda end_date=None: (_ for _ in ()).throw(AssertionError("should not call yfinance valuation in backtest")),
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_ndx_pe_and_earnings_yield", "get_equity_risk_premium"]}

    data = collector.run(backtest_date="2025-04-09")

    skipped = {item["function_id"]: item["raw_data"] for item in data["indicators"]}
    assert skipped["get_ndx_pe_and_earnings_yield"]["backtest_skipped"] is True
    assert skipped["get_ndx_pe_and_earnings_yield"]["data_quality"]["availability"] == "backtest_skipped"
    assert skipped["get_equity_risk_premium"]["backtest_skipped"] is True
    assert {item["function_id"] for item in data["backtest_data_boundaries"]} == {
        "get_ndx_pe_and_earnings_yield",
        "get_equity_risk_premium",
    }


def test_backtest_manual_ndx_valuation_still_overrides_skip(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {
            "active": True,
            "metrics": {
                "get_ndx_pe_and_earnings_yield": {
                    "name": "NDX Valuation (Manual)",
                    "value": {"PE_TTM": 31.2},
                    "source_name": "Wind",
                    "data_quality": {"source_disagreement": {}},
                }
            },
        },
    )
    monkeypatch.setattr(manual_data, "has_meaningful_manual_override", lambda metric: True)
    monkeypatch.setattr("tools_L4.get_ndx_valuation_third_party_checks", lambda: [])

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_ndx_pe_and_earnings_yield"]}

    data = collector.run(backtest_date="2025-04-09")
    raw = data["indicators"][0]["raw_data"]

    assert raw["source_name"] == "Wind"
    assert raw["value"]["PE_TTM"] == 31.2
    assert not data["backtest_data_boundaries"]
