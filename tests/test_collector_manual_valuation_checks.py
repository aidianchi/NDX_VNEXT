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
    invariants = data["strict_backtest_invariants"]
    assert invariants["effective_date"] == "2025-04-09"
    assert any(item["invariant_id"] == "observation_dates_lte_effective_date" for item in invariants["hard_enforced"])
    assert any(item["invariant_id"] == "alfred_first_vintage_not_enforced" for item in invariants["declared_limitations"])
    assert invariants["research_candidate_policy"]["status"] == "manual_review_required"


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
    monkeypatch.setattr(
        "tools_L4.get_ndx_valuation_third_party_checks",
        lambda: (_ for _ in ()).throw(AssertionError("should not fetch live valuation checks in backtest")),
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_ndx_pe_and_earnings_yield"]}

    data = collector.run(backtest_date="2025-04-09")
    raw = data["indicators"][0]["raw_data"]

    assert raw["source_name"] == "Wind"
    assert raw["value"]["PE_TTM"] == 31.2
    assert raw["value"]["ThirdPartyChecks"] == []
    assert raw["data_quality"]["source_disagreement"] == {}
    assert "live third-party checks are skipped in backtest" in raw["manual_override_note"]
    assert not data["backtest_data_boundaries"]


# --- Work order #7: Damodaran manual ERP provenance (three branches) ---


def test_damodaran_manual_official_source_has_no_provenance_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {
            "active": True,
            "metrics": {
                "get_damodaran_us_implied_erp": {
                    "name": "Manual/Wind ERP Reference",
                    "primary_fields": ["manual_erp", "implied_erp_fcfe", "implied_erp_ddm"],
                    "value": {"manual_erp": 4.5, "manual_source_type": "damodaran_official"},
                    "data_quality": {"data_date": "2025-12-20"},
                }
            },
        },
    )
    monkeypatch.setitem(
        collector_module.TOOLS_REGISTRY,
        "get_damodaran_us_implied_erp",
        lambda end_date=None: {"name": "Damodaran", "value": {}, "data_quality": {}},
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_damodaran_us_implied_erp"]}

    data = collector.run(backtest_date="2026-01-01")
    raw = data["indicators"][0]["raw_data"]

    assert raw["value"]["manual_erp"] == 4.5
    anomalies = raw["data_quality"]["anomalies"]
    assert "manual_erp_provenance_undeclared" not in anomalies
    assert "erp_independence_compromised_manual_source_not_damodaran" not in anomalies
    assert "manual_data_stale" not in anomalies


def test_damodaran_manual_wind_derived_source_flags_independence_compromised(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {
            "active": True,
            "metrics": {
                "get_damodaran_us_implied_erp": {
                    "name": "Manual/Wind ERP Reference",
                    "primary_fields": ["manual_erp", "implied_erp_fcfe", "implied_erp_ddm"],
                    "value": {"manual_erp": 4.5, "manual_source_type": "wind_derived"},
                    "data_quality": {"data_date": "2025-12-20"},
                }
            },
        },
    )
    monkeypatch.setitem(
        collector_module.TOOLS_REGISTRY,
        "get_damodaran_us_implied_erp",
        lambda end_date=None: {"name": "Damodaran", "value": {}, "data_quality": {}},
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_damodaran_us_implied_erp"]}

    data = collector.run(backtest_date="2026-01-01")
    raw = data["indicators"][0]["raw_data"]

    anomalies = raw["data_quality"]["anomalies"]
    assert "erp_independence_compromised_manual_source_not_damodaran" in anomalies
    assert "manual_erp_provenance_undeclared" not in anomalies
    assert "该值未声明为 Damodaran 官方口径" in raw["manual_override_note"]


def test_damodaran_manual_undeclared_source_flags_provenance_undeclared(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {
            "active": True,
            "metrics": {
                "get_damodaran_us_implied_erp": {
                    "name": "Manual/Wind ERP Reference",
                    "primary_fields": ["manual_erp", "implied_erp_fcfe", "implied_erp_ddm"],
                    # manual_source_type deliberately absent (undeclared provenance).
                    "value": {"manual_erp": 4.5},
                    "data_quality": {"data_date": "2025-12-20"},
                }
            },
        },
    )
    monkeypatch.setitem(
        collector_module.TOOLS_REGISTRY,
        "get_damodaran_us_implied_erp",
        lambda end_date=None: {"name": "Damodaran", "value": {}, "data_quality": {}},
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_damodaran_us_implied_erp"]}

    data = collector.run(backtest_date="2026-01-01")
    raw = data["indicators"][0]["raw_data"]

    anomalies = raw["data_quality"]["anomalies"]
    assert "manual_erp_provenance_undeclared" in anomalies
    assert "erp_independence_compromised_manual_source_not_damodaran" not in anomalies
    assert "该值未声明为 Damodaran 官方口径" in raw["manual_override_note"]


# --- Work order #7: manual data staleness annotation (two branches) ---


def test_damodaran_manual_stale_date_flags_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {
            "active": True,
            "metrics": {
                "get_damodaran_us_implied_erp": {
                    "name": "Manual/Wind ERP Reference",
                    "primary_fields": ["manual_erp", "implied_erp_fcfe", "implied_erp_ddm"],
                    "value": {"manual_erp": 4.5, "manual_source_type": "damodaran_official"},
                    "data_quality": {"data_date": "2020-01-01"},
                }
            },
        },
    )
    monkeypatch.setitem(
        collector_module.TOOLS_REGISTRY,
        "get_damodaran_us_implied_erp",
        lambda end_date=None: {"name": "Damodaran", "value": {}, "data_quality": {}},
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {4: ["get_damodaran_us_implied_erp"]}

    data = collector.run(backtest_date="2026-01-01")
    raw = data["indicators"][0]["raw_data"]

    anomalies = raw["data_quality"]["anomalies"]
    assert "manual_data_stale" in anomalies
    assert "manual_data_date_missing" not in anomalies
    assert "2020-01-01" in raw["manual_override_note"]
    assert "超过" in raw["manual_override_note"]


def test_manual_value_missing_date_flags_date_missing_anomaly(tmp_path, monkeypatch):
    monkeypatch.setattr("core.collector.path_config.data_dir", str(tmp_path))
    monkeypatch.setattr(
        manual_data,
        "load_manual_data",
        lambda: {
            "active": True,
            "metrics": {
                "get_qqq_top10_concentration": {
                    "name": "QQQ Top10 Concentration (Manual)",
                    "primary_fields": ["top10_weight_pct", "top5_weight_pct", "m7_weight_pct"],
                    "value": {"top10_weight_pct": 50.1},
                    "data_quality": {},
                }
            },
        },
    )

    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {3: ["get_qqq_top10_concentration"]}

    data = collector.run(backtest_date="2026-01-01")
    raw = data["indicators"][0]["raw_data"]

    assert "manual_data_date_missing" in raw["data_quality"]["anomalies"]
    assert "manual_data_stale" not in raw["data_quality"]["anomalies"]
    # Classification metadata must not leak into the evidence payload.
    assert "primary_fields" not in raw
