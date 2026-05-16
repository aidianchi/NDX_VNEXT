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
                "metric_name": "QQQ/QQEW Ratio",
                "function_id": "get_qqq_qqew_ratio",
                "raw_data": {"name": "QQQ/QQEW Ratio", "value": {"level": 1.15, "relativity": {"percentile_10y": 88.0}}},
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
    assert packet.facts_by_layer["L1"].state == "restrictive"
    assert packet.facts_by_layer["L4"].state == "expensive"
    assert packet.facts_by_layer["L5"].state == "strong_uptrend"

    link_types = {item.link_type for item in packet.candidate_cross_layer_links}
    assert "L1_L4" in link_types
    assert "L3_L5" in link_types


def test_packet_builder_keeps_event_refs_separate_from_layer_data():
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


def test_l4_state_accepts_trendonify_or_manual_real_percentile():
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

    assert valuation_signal["historical_percentile"] == 86.0
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


def test_l4_trendonify_percentile_has_priority_over_danjuan():
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

    assert valuation_signal["historical_percentile"] == 62.0
    assert packet.facts_by_layer["L4"].state == "neutral"


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
