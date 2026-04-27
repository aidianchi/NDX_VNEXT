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
                "metric_name": "ERP",
                "function_id": "get_equity_risk_premium",
                "raw_data": {"name": "ERP", "value": {"erp_value": 0.8, "erp_percentile_5y": 12.0}},
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
