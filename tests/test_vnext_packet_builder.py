import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.packet_builder import AnalysisPacketBuilder


def _mock_data_json():
    return {
        "timestamp_utc": "2026-04-24T00:00:00Z",
        "backtest_date": None,
        "indicators": [
            {
                "layer": 1,
                "metric_name": "Fed Funds Rate",
                "function_id": "get_fed_funds_rate",
                "raw_data": {"name": "Fed Funds Rate", "value": {"level": 5.25, "trend": "rising"}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:01Z",
            },
            {
                "layer": 1,
                "metric_name": "10Y Real Rate",
                "function_id": "get_10y_real_rate",
                "raw_data": {"name": "10Y Real Rate", "value": {"level": 1.8, "relativity": {"percentile_10y": 82.0}}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:02Z",
            },
            {
                "layer": 1,
                "metric_name": "Net Liquidity",
                "function_id": "get_net_liquidity_momentum",
                "raw_data": {"name": "Net Liquidity", "value": {"level": 5200.0, "momentum_4w": -120.5}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:03Z",
            },
            {
                "layer": 3,
                "metric_name": "NDX/NDXE Ratio",
                "function_id": "get_ndx_ndxe_ratio",
                "raw_data": {"name": "NDX/NDXE Ratio", "value": {"level": 2.9, "relativity": {"percentile_10y": 88.0}}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:04Z",
            },
            {
                "layer": 3,
                "metric_name": "Advance Decline Line",
                "function_id": "get_advance_decline_line",
                "raw_data": {"name": "Advance Decline Line", "value": {"trend": "falling"}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:05Z",
            },
            {
                "layer": 4,
                "metric_name": "NDX Valuation",
                "function_id": "get_ndx_pe_and_earnings_yield",
                "raw_data": {"name": "NDX Valuation", "value": {"PE_TTM": 32.5, "PE_TTM_percentile_5y": 78.0}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:06Z",
            },
            {
                "layer": 4,
                "metric_name": "Simple Yield Gap",
                "function_id": "get_equity_risk_premium",
                "raw_data": {"name": "NDX Simple Yield Gap", "value": {"level": 0.8, "percentile_5y": 12.0}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:07Z",
            },
            {
                "layer": 5,
                "metric_name": "QQQ Technical",
                "function_id": "get_qqq_technical_indicators",
                "raw_data": {"name": "QQQ Technical", "value": {"sma_position": "above_200", "macd_status": "bullish"}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:08Z",
            },
            {
                "layer": 5,
                "metric_name": "ADX",
                "function_id": "get_adx_qqq",
                "raw_data": {"name": "ADX", "value": {"level": {"adx": 33.0, "pdi": 40.0, "mdi": 20.0}}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:09Z",
            },
        ],
    }


def test_packet_builder_groups_data_and_generates_candidate_links():
    builder = AnalysisPacketBuilder()
    packet = builder.build(_mock_data_json(), manual_overrides={"active": False, "metrics": {}})

    assert packet.meta["indicator_total"] == 9
    assert packet.meta["object_run_gate"]["primary_object"] == "NDX"
    assert packet.meta["object_run_gate"]["tradable_proxy"] == "QQQ"
    assert packet.meta["object_run_gate"]["date_boundary"] == "2026-04-24"
    assert "NDXE" in packet.meta["object_run_gate"]["equal_weight_references"]
    assert "evidence_ref" in packet.meta["object_run_gate"]["evidence_boundary"]
    assert packet.context["object_run_gate"]["methodology_boundary"] == packet.meta["object_run_gate"]["methodology_boundary"]
    assert packet.facts_by_layer["L1"].state == "restrictive"
    assert packet.facts_by_layer["L4"].state == "expensive"
    assert packet.facts_by_layer["L5"].state == "strong_uptrend"

    link_types = {item.link_type for item in packet.candidate_cross_layer_links}
    assert "L1_L4" in link_types
    assert "L3_L5" in link_types


def test_packet_builder_labels_damodaran_erp_percentile_without_ndx_valuation_mixup():
    data = {
        "timestamp_utc": "2026-05-01T00:00:00Z",
        "indicators": [
            {
                "layer": 4,
                "metric_name": "Damodaran US Implied ERP Reference",
                "function_id": "get_damodaran_us_implied_erp",
                "raw_data": {
                    "name": "Damodaran US Implied ERP Reference",
                    "value": {
                        "erp_t12m_adjusted_payout": 4.24,
                        "damodaran_erp_percentile_5y": 42.7,
                        "damodaran_erp_percentile_10y": 37.5,
                        "damodaran_erp_historical_percentiles": {
                            "windows": {
                                "5y": {"percentile": 42.7, "status": "available", "sample_count": 60},
                                "10y": {"percentile": 37.5, "status": "available", "sample_count": 120},
                            }
                        },
                    },
                },
            }
        ],
    }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    signal = next(
        item
        for item in packet.facts_by_layer["L4"].core_signals
        if item["metric"] == "get_damodaran_us_implied_erp"
    )

    assert signal["historical_percentile"] == 37.5
    assert "Damodaran ERP 10Y分位=37.5" in signal["summary"]
    assert "分位=42.7" not in signal["summary"]


def test_packet_builder_hides_inactive_manual_metric_values_and_carries_backtest_boundaries():
    data = _mock_data_json()
    data["backtest_date"] = "2025-04-09"
    data["backtest_data_boundaries"] = [
        {
            "function_id": "get_ndx_pe_and_earnings_yield",
            "reason": "latest-only source",
            "future_upgrade": "historical source",
        }
    ]
    data["strict_backtest_invariants"] = {
        "schema_version": "strict_backtest_invariants_v1",
        "declared_limitations": [
            {"invariant_id": "alfred_first_vintage_not_enforced", "status": "declared_limitation"}
        ],
    }
    packet = AnalysisPacketBuilder().build(
        data,
        manual_overrides={
            "active": False,
            "date": "2025-04-09",
            "metrics": {
                "get_ndx_pe_and_earnings_yield": {"value": {"PE_TTM": 36.6, "PE_TTM_percentile_10y": 90}}
            },
        },
    )

    assert packet.manual_overrides["metrics"] == {}
    assert packet.manual_overrides["inactive_metric_count"] == 1
    assert packet.meta["backtest_data_boundaries"][0]["function_id"] == "get_ndx_pe_and_earnings_yield"
    assert packet.context["backtest_data_boundaries"][0]["future_upgrade"] == "historical source"
    assert packet.meta["strict_backtest_invariants"]["schema_version"] == "strict_backtest_invariants_v1"
    assert packet.context["strict_backtest_invariants"]["declared_limitations"][0]["invariant_id"] == "alfred_first_vintage_not_enforced"


def test_packet_builder_defaults_to_data_only_even_when_event_ledger_is_provided():
    builder = AnalysisPacketBuilder()
    event_ledger = {
        "events": [
            {
                "event_id": "event:abc123",
                "dedupe_id": "abc123",
                "source_id": "federal_reserve_press_all",
                "source_name": "Federal Reserve Press Releases",
                "source_tier": "official_macro",
                "event_type": "policy_or_financial_conditions",
                "title": "Federal Reserve issues FOMC statement",
                "url": "https://www.federalreserve.gov/example.htm",
                "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                "layers": ["L1", "L2", "L4"],
                "symbols": [],
                "confidence": "high",
            }
        ]
    }

    packet = builder.build(_mock_data_json(), manual_overrides={"active": False, "metrics": {}}, event_ledger=event_ledger)

    assert packet.event_refs == {}
    assert "event:abc123" not in packet.raw_data["L1"]


def test_packet_builder_can_keep_event_refs_for_legacy_compatibility():
    builder = AnalysisPacketBuilder()
    event_ledger = {
        "events": [
            {
                "event_id": "event:abc123",
                "dedupe_id": "abc123",
                "source_id": "federal_reserve_press_all",
                "source_name": "Federal Reserve Press Releases",
                "source_tier": "official_macro",
                "event_type": "policy_or_financial_conditions",
                "title": "Federal Reserve issues FOMC statement",
                "url": "https://www.federalreserve.gov/example.htm",
                "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                "layers": ["L1", "L2", "L4"],
                "symbols": [],
                "confidence": "high",
            }
        ]
    }

    packet = builder.build(
        _mock_data_json(),
        manual_overrides={"active": False, "metrics": {}},
        event_ledger=event_ledger,
        allow_event_refs=True,
    )

    assert "event:abc123" in packet.event_refs
    assert packet.event_refs["event:abc123"]["usage_boundary"].startswith("event_ref only")
    assert "event:abc123" not in packet.raw_data["L1"]


def test_l4_state_uses_real_percentile_not_yfinance_current_pe_alone():
    data = _mock_data_json()
    for indicator in data["indicators"]:
        if indicator["function_id"] == "get_ndx_pe_and_earnings_yield":
            indicator["raw_data"] = {
                "name": "NDX Valuation",
                "value": {
                    "PE": 34.0,
                    "TrailingPE": 34.0,
                    "ThirdPartyChecks": [
                        {
                            "source_name": "WorldPERatio",
                            "metric": "ndx_trailing_pe",
                            "value": 32.27,
                            "historical_percentile": None,
                            "methodology": "rolling average / outlier notes",
                        }
                    ],
                },
                "source_tier": "component_model",
            }
        if indicator["function_id"] == "get_equity_risk_premium":
            indicator["raw_data"] = {
                "name": "NDX Simple Yield Gap",
                "value": {"level": 2.2},
            }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    valuation_signal = next(
        signal for signal in packet.facts_by_layer["L4"].core_signals if signal["metric"] == "get_ndx_pe_and_earnings_yield"
    )

    assert valuation_signal["historical_percentile"] is None
    assert "历史分位缺失" in valuation_signal["summary"]
    assert packet.facts_by_layer["L4"].state == "neutral"


def test_l4_state_suppresses_stale_hom_percentile_leaking_through_history_of_market():
    """Regression for the 20260719_130534 run: HoM's own gated top-level fields
    (TrailingPEHistoricalPercentile/ForwardPEHistoricalPercentile) already
    correctly return None when the source is stale or insufficient_history,
    but a generic deep scan of the payload could still reach past that gate
    into the raw, ungated `HistoryOfMarket.trailing_percentile` sub-field and
    surface it in the core summary as a bare "分位=68.5" number. E1 P0 fix:
    the summary must never show that bare number; it must say the historical
    percentile is unavailable instead, while the raw value stays in the
    payload/audit area untouched.
    """
    data = _mock_data_json()
    for indicator in data["indicators"]:
        if indicator["function_id"] == "get_ndx_pe_and_earnings_yield":
            indicator["raw_data"] = {
                "name": "NDX Valuation",
                "source_tier": "third_party_estimate",
                "source_name": "History of Market",
                "value": {
                    "PE": 34.39,
                    "TrailingPE": 34.39,
                    "ForwardPE": None,
                    "TrailingPEHistoricalPercentile": None,
                    "ForwardPEHistoricalPercentile": None,
                    "ThirdPartyChecks": [
                        {"source_id": "worldperatio_pe", "availability": "unavailable"},
                        {"source_id": "danjuan_ndx_valuation", "availability": "unavailable"},
                    ],
                    "HistoryOfMarket": {
                        "trailing_percentile": 68.5,
                        "forward_percentile": None,
                        "trailing_percentile_status": "insufficient_history",
                        "forward_percentile_status": "unavailable",
                        "trailing_decision_eligible": True,
                        "forward_decision_eligible": False,
                    },
                    "StaleReferences": {},
                },
            }
        if indicator["function_id"] == "get_equity_risk_premium":
            indicator["raw_data"] = {"name": "NDX Simple Yield Gap", "value": {"level": 2.2}}

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    valuation_signal = next(
        signal for signal in packet.facts_by_layer["L4"].core_signals if signal["metric"] == "get_ndx_pe_and_earnings_yield"
    )

    assert valuation_signal["historical_percentile"] is None
    assert "68.5" not in valuation_signal["summary"]
    assert "历史分位缺失" in valuation_signal["summary"]
    # The raw stale value must still be reachable in the untouched payload/audit
    # area (packet.raw_data), not silently deleted.
    raw_hom = packet.raw_data["L4"]["get_ndx_pe_and_earnings_yield"]["value"]["HistoryOfMarket"]
    assert raw_hom["trailing_percentile"] == 68.5
    assert raw_hom["trailing_percentile_status"] == "insufficient_history"


def test_l4_signal_carries_worldperatio_relative_position_without_percentile():
    data = _mock_data_json()
    for indicator in data["indicators"]:
        if indicator["function_id"] == "get_ndx_pe_and_earnings_yield":
            indicator["raw_data"] = {
                "name": "NDX Valuation",
                "value": {
                    "PE": 32.8,
                    "ThirdPartyChecks": [
                            {
                                "source_name": "WorldPERatio",
                                "source_id": "worldperatio_pe",
                                "availability": "available",
                                "usage": "validation_only",
                                "metric": "ndx_trailing_pe",
                            "value": 32.27,
                            "historical_percentile": None,
                            "relative_position": {
                                "position_type": "std_dev_context_not_percentile",
                                "valuation_windows": {
                                    "10y": {
                                        "average_pe": 26.8,
                                        "std_dev": 3.2,
                                        "deviation_vs_mean_sigma": 1.71,
                                        "valuation_label": "Overvalued",
                                    }
                                },
                            },
                        }
                    ],
                },
            }
        if indicator["function_id"] == "get_equity_risk_premium":
            indicator["raw_data"] = {"name": "NDX Simple Yield Gap", "value": {"level": 2.2}}

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    valuation_signal = next(
        signal for signal in packet.facts_by_layer["L4"].core_signals if signal["metric"] == "get_ndx_pe_and_earnings_yield"
    )

    assert valuation_signal["historical_percentile"] is None
    assert valuation_signal["relative_position_context"]["WorldPERatio"]["position_type"] == "std_dev_context_not_percentile"
    assert valuation_signal["relative_position_context"]["WorldPERatio"]["valuation_windows"]["10y"]["valuation_label"] == "Overvalued"
    assert packet.facts_by_layer["L4"].state == "neutral"


def test_l4_state_rejects_trendonify_percentile_without_current_validation_status():
    data = _mock_data_json()
    for indicator in data["indicators"]:
        if indicator["function_id"] == "get_ndx_pe_and_earnings_yield":
            indicator["raw_data"] = {
                "name": "NDX Valuation",
                "value": {
                    "PE": 34.0,
                    "ThirdPartyChecks": [
                        {
                            "source_name": "Trendonify",
                            "metric": "ndx_trailing_pe",
                            "value": 34.1,
                            "percentile_10y": 86.0,
                            "historical_percentile": 86.0,
                        }
                    ],
                },
                "source_tier": "component_model",
            }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    valuation_signal = next(
        signal for signal in packet.facts_by_layer["L4"].core_signals if signal["metric"] == "get_ndx_pe_and_earnings_yield"
    )

    assert valuation_signal["historical_percentile"] is None
    # The untouched mock simple-yield-gap percentile remains restrictive; the
    # assertion here is only that Trendonify did not supply the percentile.
    assert packet.facts_by_layer["L4"].state == "expensive"


def test_l4_state_prefers_wind_ndx_snapshot_when_available():
    data = _mock_data_json()
    data["indicators"].append(
        {
            "layer": 4,
            "metric_name": "Wind NDX Valuation and Risk Premium Snapshot",
            "function_id": "get_ndx_wind_valuation_snapshot",
            "raw_data": {
                "name": "Wind NDX Valuation and Risk Premium Snapshot",
                "value": {
                    "PE": 35.2454,
                    "PB": 10.3394,
                    "PS": 7.4105,
                    "RiskPremium": 1.0926,
                    "PEHistoricalPercentile": 84.64,
                    "PBHistoricalPercentile": 99.27,
                    "PSHistoricalPercentile": 97.67,
                    "RiskPremiumHistoricalPercentile": 55.54,
                },
                "source_tier": "licensed_provider/Wind",
                "source_name": "Wind index_data.get_index_fundamentals",
            },
            "error": None,
            "collection_timestamp_utc": "2026-06-16T00:00:00Z",
        }
    )
    for indicator in data["indicators"]:
        if indicator["function_id"] == "get_ndx_pe_and_earnings_yield":
            indicator["raw_data"] = {
                "name": "NDX Valuation",
                "value": {"PE": 34.0, "ThirdPartyChecks": []},
                "source_tier": "component_model",
            }
        if indicator["function_id"] == "get_equity_risk_premium":
            indicator["raw_data"] = {"name": "NDX Simple Yield Gap", "value": {"level": 2.2}}

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    wind_signal = next(
        signal for signal in packet.facts_by_layer["L4"].core_signals if signal["metric"] == "get_ndx_wind_valuation_snapshot"
    )

    assert wind_signal["historical_percentile"] == 84.64
    assert "Wind PE分位=84.64" in wind_signal["summary"]
    assert "Wind风险溢价分位=55.54" in wind_signal["summary"]
    assert packet.facts_by_layer["L4"].state == "expensive"


def test_l4_wind_risk_premium_low_percentile_marks_compensation_thin():
    data = {
        "timestamp_utc": "2026-06-16T00:00:00Z",
        "indicators": [
            {
                "layer": 4,
                "metric_name": "Wind NDX Valuation and Risk Premium Snapshot",
                "function_id": "get_ndx_wind_valuation_snapshot",
                "raw_data": {
                    "name": "Wind NDX Valuation and Risk Premium Snapshot",
                    "value": {
                        "PE": 24.0,
                        "PEHistoricalPercentile": 45.0,
                        "RiskPremium": 0.5,
                        "RiskPremiumHistoricalPercentile": 18.0,
                    },
                    "source_tier": "licensed_provider/Wind",
                },
                "error": None,
                "collection_timestamp_utc": "2026-06-16T00:00:00Z",
            }
        ],
    }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})

    assert packet.facts_by_layer["L4"].state == "expensive"


def test_l4_state_accepts_danjuan_real_percentile_after_trendonify():
    data = _mock_data_json()
    for indicator in data["indicators"]:
        if indicator["function_id"] == "get_ndx_pe_and_earnings_yield":
            indicator["raw_data"] = {
                "name": "NDX Valuation",
                "value": {
                    "PE": 34.0,
                    "TrailingPE": 34.0,
                    "ThirdPartyChecks": [
                            {
                                "source_name": "WorldPERatio",
                                "source_id": "worldperatio_pe",
                                "availability": "available",
                                "usage": "validation_only",
                                "metric": "ndx_trailing_pe",
                            "value": 32.27,
                            "historical_percentile": None,
                            "relative_position": {
                                "position_type": "std_dev_context_not_percentile",
                                "valuation_windows": {"10y": {"valuation_label": "Overvalued"}},
                            },
                        },
                        {
                            "source_name": "DanjuanFunds",
                            "source_id": "danjuan_ndx_valuation",
                            "metric": "ndx_trailing_pe",
                            "value": 36.5,
                            "historical_percentile": 87.0,
                            "pe_percentile_raw": 0.87,
                            "availability": "available",
                        },
                    ],
                },
                "source_tier": "component_model",
                "source_name": "yfinance (NDX100 Components)",
            }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    valuation_signal = next(
        signal for signal in packet.facts_by_layer["L4"].core_signals if signal["metric"] == "get_ndx_pe_and_earnings_yield"
    )

    assert valuation_signal["historical_percentile"] == 87.0
    assert valuation_signal["relative_position_context"]["WorldPERatio"]["position_type"] == "std_dev_context_not_percentile"
    assert packet.facts_by_layer["L4"].state == "expensive"


def test_l4_trendonify_percentile_does_not_override_current_danjuan_validation():
    data = _mock_data_json()
    for indicator in data["indicators"]:
        if indicator["function_id"] == "get_ndx_pe_and_earnings_yield":
            indicator["raw_data"] = {
                "name": "NDX Valuation",
                "value": {
                    "PE": 34.0,
                    "ThirdPartyChecks": [
                        {
                            "source_name": "DanjuanFunds",
                            "source_id": "danjuan_ndx_valuation",
                            "historical_percentile": 87.0,
                            "availability": "available",
                        },
                        {
                            "source_name": "Trendonify",
                            "source_id": "trendonify_pe",
                            "historical_percentile": 62.0,
                            "availability": "available",
                        },
                    ],
                },
                "source_tier": "component_model",
                "source_name": "yfinance (NDX100 Components)",
            }
        if indicator["function_id"] == "get_equity_risk_premium":
            indicator["raw_data"] = {"name": "NDX Simple Yield Gap", "value": {"level": 2.2}}

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    valuation_signal = next(
        signal for signal in packet.facts_by_layer["L4"].core_signals if signal["metric"] == "get_ndx_pe_and_earnings_yield"
    )

    assert valuation_signal["historical_percentile"] == 87.0
    assert packet.facts_by_layer["L4"].state == "expensive"


def test_l3_state_treats_declining_ad_line_as_deteriorating():
    data = {
        "timestamp_utc": "2026-05-02T00:00:00Z",
        "backtest_date": None,
        "indicators": [
            {
                "layer": 3,
                "metric_name": "Advance Decline Line",
                "function_id": "get_advance_decline_line",
                "raw_data": {"name": "Advance Decline Line", "value": {"trend": "declining"}},
                "error": None,
                "collection_timestamp_utc": "2026-05-02T00:00:01Z",
            }
        ],
    }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})

    assert packet.facts_by_layer["L3"].state == "deteriorating"


def test_packet_builder_normalizes_ratio_scale_percentiles_before_signals_and_state():
    data = {
        "timestamp_utc": "2026-07-10T00:00:00Z",
        "backtest_date": None,
        "indicators": [
            {
                "layer": 1,
                "metric_name": "10Y Real Rate",
                "function_id": "get_10y_real_rate",
                "raw_data": {"value": {"level": 1.0, "relativity": {"percentile_10y": 0.82}}},
                "error": None,
            },
            {
                "layer": 2,
                "metric_name": "VIX",
                "function_id": "get_vix",
                "raw_data": {"value": {"level": 18.0, "relativity": {"percentile_10y": 82.0}}},
                "error": None,
            },
            {
                "layer": 3,
                "metric_name": "NDX/NDXE Ratio",
                "function_id": "get_ndx_ndxe_ratio",
                "raw_data": {
                    "value": {
                        "level": 2.9,
                        # Deliberately put 1Y first: window priority must not
                        # depend on dictionary insertion order.
                        "relativity": {"percentile_1y": 0.10, "percentile_10y": 0.96538},
                    }
                },
                "error": None,
            },
        ],
    }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})

    l1_signal = next(item for item in packet.facts_by_layer["L1"].core_signals if item["metric"] == "get_10y_real_rate")
    l2_signal = next(item for item in packet.facts_by_layer["L2"].core_signals if item["metric"] == "get_vix")
    l3_signal = next(item for item in packet.facts_by_layer["L3"].core_signals if item["metric"] == "get_ndx_ndxe_ratio")
    assert l1_signal["historical_percentile"] == 82.0
    assert l2_signal["historical_percentile"] == 82.0
    assert l3_signal["historical_percentile"] == 96.538
    assert packet.facts_by_layer["L3"].state == "deteriorating"


def test_l3_state_reads_current_percent_above_ma_fields():
    data = {
        "timestamp_utc": "2026-05-02T00:00:00Z",
        "backtest_date": None,
        "indicators": [
            {
                "layer": 3,
                "metric_name": "% Stocks Above MA",
                "function_id": "get_percent_above_ma",
                "raw_data": {
                    "name": "% Stocks Above MA",
                    "value": {
                        "level": {
                            "percent_above_50d": 66.0,
                            "percent_above_200d": 57.0,
                        }
                    },
                },
                "error": None,
                "collection_timestamp_utc": "2026-05-02T00:00:01Z",
            }
        ],
    }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})

    assert packet.facts_by_layer["L3"].state == "healthy"


def test_l3_unavailable_nested_none_payload_is_not_promoted_to_core_fact():
    data = {
        "timestamp_utc": "2026-05-02T00:00:00Z",
        "backtest_date": "2025-04-09",
        "indicators": [
            {
                "layer": 3,
                "metric_name": "Advance Decline Line",
                "function_id": "get_advance_decline_line",
                "raw_data": {
                    "name": "Advance Decline Line",
                    "value": {"level": None, "date": None, "momentum": None},
                    "notes": "Failed to calculate advance decline line",
                },
                "error": None,
                "collection_timestamp_utc": "2026-05-02T00:00:01Z",
            },
            {
                "layer": 3,
                "metric_name": "% Stocks Above MA",
                "function_id": "get_percent_above_ma",
                "raw_data": {
                    "name": "% Stocks Above MA",
                    "value": {"level": {"percent_above_50d": None, "percent_above_200d": None}},
                    "source_tier": "unavailable",
                },
                "error": None,
                "collection_timestamp_utc": "2026-05-02T00:00:02Z",
            },
        ],
    }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    l3 = packet.facts_by_layer["L3"]

    assert "get_advance_decline_line" not in l3.key_metrics
    assert "get_percent_above_ma" not in l3.key_metrics
    assert l3.state == "insufficient_data"
    assert "值={'level': None" not in l3.summary
    failed = next(signal for signal in l3.core_signals if signal["metric"] == "get_advance_decline_line")
    assert failed["error"] == "unavailable_payload"


def test_l5_price_volume_quality_is_native_packet_metric():
    data = {
        "timestamp_utc": "2026-05-04T00:00:00Z",
        "indicators": [
            {
                "layer": 5,
                "function_id": "get_price_volume_quality_qqq",
                "metric_name": "QQQ Price-Volume Quality",
                "raw_data": {
                    "name": "QQQ Price-Volume Quality",
                    "value": {
                        "vwap_20": 350.0,
                        "price_vs_vwap_20": "above",
                        "mfi_14": 72.0,
                        "mfi_status": "neutral",
                        "cmf_20": 0.08,
                        "cmf_status": "accumulation",
                    },
                },
                "collection_timestamp_utc": "2026-05-04T00:00:01Z",
            }
        ],
    }

    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})

    assert "get_price_volume_quality_qqq" in packet.raw_data["L5"]
    assert "get_price_volume_quality_qqq" in packet.facts_by_layer["L5"].key_metrics
    signal = next(
        item
        for item in packet.facts_by_layer["L5"].core_signals
        if item["metric"] == "get_price_volume_quality_qqq"
    )
    assert signal["value"]["vwap_20"] == 350.0
    assert signal["value"]["mfi_14"] == 72.0
    assert signal["value"]["cmf_20"] == 0.08
