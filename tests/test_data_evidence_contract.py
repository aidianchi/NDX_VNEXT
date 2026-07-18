import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import core.collector as collector_module
import manual_data
from agent_analysis.packet_builder import AnalysisPacketBuilder
from agent_analysis.vnext_reporter import VNextReportGenerator
from core.checker import DataIntegrity
from core.collector import DataCollector
from data_evidence import (
    DATA_EVIDENCE_CONTRACT_VERSION,
    data_evidence_issues,
    normalize_data_evidence,
    normalize_source_tier_for_evidence_passport,
)


def _indicator(function_id, raw_data, layer=1):
    return {
        "layer": layer,
        "metric_name": raw_data.get("name", function_id),
        "function_id": function_id,
        "raw_data": raw_data,
        "error": raw_data.get("error"),
        "collection_timestamp_utc": "2026-06-16T00:00:00Z",
    }


def test_normalizer_backfills_legacy_payload_without_inventing_source_url():
    payload = normalize_data_evidence(
        {
            "name": "Unit Metric",
            "value": {"level": 1.23},
            "date": "2026-06-15",
            "source_name": "Unit Source",
        },
        function_id="get_unit_metric",
        layer=1,
        effective_date="2026-06-16",
        collected_at_utc="2026-06-16T00:00:00Z",
    )

    data_quality = payload["data_quality"]
    assert data_quality["contract_version"] == DATA_EVIDENCE_CONTRACT_VERSION
    assert data_quality["source_url"] == "missing"
    assert data_quality["effective_date"] == "2026-06-16"
    assert data_quality["data_date"] == "2026-06-15"
    assert "missing_source_url" in data_quality["anomalies"]


def test_normalizer_marks_explicit_legacy_collection_failure_unavailable():
    payload = normalize_data_evidence(
        {
            "name": "Advance/Decline Line (NDX100)",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "notes": "Failed to calculate: Insufficient data returned from yfinance.",
            "data_quality": {"availability": "available"},
        },
        function_id="get_advance_decline_line",
        layer=3,
        effective_date="2025-04-09",
        collected_at_utc="2025-04-10T00:00:00Z",
    )

    assert payload["data_quality"]["availability"] == "unavailable"
    assert payload["data_quality"]["fallback_reason"] == "legacy_collection_failure"
    assert "legacy_available_failure_normalized_to_unavailable" in payload["data_quality"]["anomalies"]
    issues = data_evidence_issues(payload, function_id="get_advance_decline_line", backtest_date="2025-04-09")
    assert not any(item["code"] == "available_without_meaningful_value" for item in issues["hard_block"])


def test_normalizer_does_not_relax_current_contract_meaningless_available_payload():
    payload = normalize_data_evidence(
        {
            "name": "Current contract bug",
            "value": {"level": None},
            "notes": "Failed to calculate: upstream returned an empty frame.",
            "data_quality": {
                "contract_version": DATA_EVIDENCE_CONTRACT_VERSION,
                "availability": "available",
            },
        },
        function_id="get_advance_decline_line",
        layer=3,
        effective_date="2026-07-17",
    )

    assert payload["data_quality"]["availability"] == "available"
    issues = data_evidence_issues(payload, function_id="get_advance_decline_line")
    assert any(item["code"] == "available_without_meaningful_value" for item in issues["hard_block"])


def test_missing_reference_only_metadata_does_not_degrade_or_block():
    raw = normalize_data_evidence(
        {"name": "Unit Metric", "value": 12.0, "source_name": "Unit Source"},
        function_id="get_unit_metric",
        layer=1,
        effective_date="2026-06-16",
    )

    report = DataIntegrity().run({"indicators": [_indicator("get_unit_metric", raw)]})

    assert report["publish_status"] == "publishable"
    assert report["data_evidence_contract_summary"]["hard_block"] == 0
    assert report["data_evidence_contract_summary"]["degraded"] == 0
    assert report["data_evidence_contract_summary"]["audit_warn"] == 0


def test_unavailable_payload_does_not_repeat_url_coverage_or_vintage_issues():
    raw = normalize_data_evidence(
        {
            "name": "Unavailable breadth",
            "value": None,
            "availability": "unavailable",
            "unavailable_reason": "provider timeout",
            "source_name": "Unit Source",
        },
        function_id="get_percent_above_ma",
        layer=3,
        effective_date="2026-07-10",
    )

    issues = data_evidence_issues(raw, function_id="get_percent_above_ma")
    codes = {item["code"] for group in issues.values() for item in group}

    assert "missing_source_url" not in codes
    assert "missing_license_note" not in codes
    assert "missing_coverage" not in codes
    assert "missing_vintage_date" not in codes
    assert "vintage_date_not_available" not in codes
    assert "metadata_defaulted" not in codes


def test_coverage_is_required_only_for_component_or_consensus_aggregates():
    component = normalize_data_evidence(
        {"name": "Breadth", "value": {"level": 60}, "source_name": "component model"},
        function_id="get_percent_above_ma",
        layer=3,
        effective_date="2026-07-10",
    )
    market = normalize_data_evidence(
        {"name": "VIX", "value": {"level": 18}, "source_name": "market data provider"},
        function_id="get_vix",
        layer=2,
        effective_date="2026-07-10",
    )

    component_codes = {item["code"] for item in data_evidence_issues(component, function_id="get_percent_above_ma")["degraded"]}
    market_codes = {item["code"] for item in data_evidence_issues(market, function_id="get_vix")["degraded"]}

    assert "missing_coverage" in component_codes
    assert "missing_coverage" not in market_codes


def test_vintage_is_required_only_for_revisable_data_in_backtests():
    macro = normalize_data_evidence(
        {"name": "M2", "value": {"level": 3.2}, "source_name": "FRED"},
        function_id="get_m2_yoy",
        layer=1,
        effective_date="2025-04-09",
    )
    market = normalize_data_evidence(
        {"name": "VIX", "value": {"level": 18}, "source_name": "market data provider"},
        function_id="get_vix",
        layer=2,
        effective_date="2025-04-09",
    )

    macro_backtest = data_evidence_issues(macro, function_id="get_m2_yoy", backtest_date="2025-04-09")
    macro_live = data_evidence_issues(macro, function_id="get_m2_yoy")
    market_backtest = data_evidence_issues(market, function_id="get_vix", backtest_date="2025-04-09")

    assert any(item["code"] == "vintage_date_not_available" for item in macro_backtest["degraded"])
    assert not any("vintage" in item["code"] for item in macro_live["degraded"])
    assert not any("vintage" in item["code"] for item in market_backtest["degraded"])


def test_market_data_provider_and_component_model_are_proxy_tiers():
    assert normalize_source_tier_for_evidence_passport("market_data_provider") == "proxy"
    assert normalize_source_tier_for_evidence_passport("component_model") == "proxy"


def test_future_date_latest_only_and_proxy_official_are_hard_blocks():
    future = normalize_data_evidence(
        {"name": "Future VIX", "value": 18.0, "date": "2026-06-16", "source_name": "yfinance"},
        function_id="get_vix",
        layer=2,
        effective_date="2025-04-09",
    )
    latest_only = normalize_data_evidence(
        {"name": "M7 Fundamentals", "value": {"AAPL": {"PE": 30}}, "date": "2025-04-09", "source_name": "yfinance"},
        function_id="get_m7_fundamentals",
        layer=3,
        effective_date="2025-04-09",
    )
    proxy_official = normalize_data_evidence(
        {
            "name": "Proxy Official",
            "value": 1.0,
            "date": "2025-04-09",
            "source_name": "Synthetic proxy",
            "data_quality": {"source_tier": "official", "methodology": "proxy estimate"},
        },
        function_id="get_ndx_ndxe_ratio",
        layer=3,
        effective_date="2025-04-09",
    )

    report = DataIntegrity().run(
        {
            "backtest_date": "2025-04-09",
            "indicators": [
                _indicator("get_vix", future, layer=2),
                _indicator("get_m7_fundamentals", latest_only, layer=3),
                _indicator("get_ndx_ndxe_ratio", proxy_official, layer=3),
            ],
        }
    )

    codes = {issue["code"] for issue in report["data_evidence_contract_issues"] if issue["severity"] == "hard_block"}
    assert "data_date_after_effective_date" in codes
    assert "latest_only_source_used_in_backtest" in codes
    assert "proxy_marked_as_official" in codes
    assert report["publish_status"] == "blocked"


def test_fallback_without_reason_blocks_core_but_only_degrades_noncore():
    core_payload = normalize_data_evidence(
        {
            "name": "Core fallback",
            "value": 1.0,
            "source_name": "fallback source",
            "data_quality": {"fallback_chain": ["primary", "fallback"], "fallback_reason": "none"},
        },
        function_id="get_vix",
        layer=2,
    )
    noncore_payload = normalize_data_evidence(
        {
            "name": "Noncore fallback",
            "value": 1.0,
            "source_name": "fallback source",
            "data_quality": {"fallback_chain": ["primary", "fallback"], "fallback_reason": "none"},
        },
        function_id="get_auxiliary_metric",
        layer=2,
    )

    core_issues = data_evidence_issues(core_payload, function_id="get_vix")
    noncore_issues = data_evidence_issues(noncore_payload, function_id="get_auxiliary_metric")

    assert any(issue["code"] == "fallback_without_reason" for issue in core_issues["hard_block"])
    assert any(issue["code"] == "fallback_without_reason" for issue in noncore_issues["degraded"])


def test_fallback_degraded_reason_counts_as_explanation_for_core_metric():
    payload = normalize_data_evidence(
        {
            "name": "Core fallback with degraded explanation",
            "value": 1.0,
            "source_name": "fallback source",
            "data_quality": {
                "availability": "degraded",
                "fallback_chain": ["primary", "fallback"],
                "fallback_reason": "none",
                "degraded_reason": "primary source rejected the latest request; cached prior observation used with boundary disclosed",
            },
        },
        function_id="get_vix",
        layer=2,
    )

    issues = data_evidence_issues(payload, function_id="get_vix")

    assert not any(issue["code"] == "fallback_without_reason" for issue in issues["hard_block"])


def test_collector_attaches_contract_to_every_indicator(monkeypatch, tmp_path):
    monkeypatch.setattr(collector_module.path_config, "data_dir", str(tmp_path))
    monkeypatch.setattr(
        collector_module,
        "TOOLS_REGISTRY",
        {
            "get_unit_metric": lambda end_date=None: {
                "name": "Unit Metric",
                "value": 1.0,
                "date": end_date or "2026-06-16",
                "source_name": "Unit Source",
            }
        },
    )
    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {1: ["get_unit_metric"]}

    data = collector.run(backtest_date=None)

    raw = data["indicators"][0]["raw_data"]
    assert raw["data_quality"]["contract_version"] == DATA_EVIDENCE_CONTRACT_VERSION
    assert raw["data_quality"]["function_id"] == "get_unit_metric"


def test_collector_separates_recompute_inputs_from_layer_raw_data(monkeypatch, tmp_path):
    monkeypatch.setattr(collector_module.path_config, "data_dir", str(tmp_path))
    monkeypatch.setattr(
        collector_module,
        "TOOLS_REGISTRY",
        {
            "get_unit_metric": lambda end_date=None: {
                "name": "Unit Metric",
                "value": {"level": 2.0},
                "date": end_date or "2026-06-16",
                "source_name": "Unit Source",
                "recompute_input": {
                    "schema_version": "dated_value_series_v1",
                    "raw_series": [{"date": "2026-06-15", "value": 1.0}, {"date": "2026-06-16", "value": 2.0}],
                },
            }
        },
    )
    collector = DataCollector()
    collector.LAYER_FUNCTIONS = {1: ["get_unit_metric"]}

    data = collector.run(backtest_date=None)

    assert "recompute_input" not in data["indicators"][0]["raw_data"]
    assert data["recompute_inputs"]["get_unit_metric"]["layer"] == 1
    assert data["recompute_inputs"]["get_unit_metric"]["raw_series"][-1]["value"] == 2.0
    packet = AnalysisPacketBuilder().build(data, manual_overrides={"active": False, "metrics": {}})
    assert "recompute_inputs" not in packet.model_dump_json()


def test_packet_builder_does_not_pass_hard_blocked_value_into_layer_facts():
    raw = normalize_data_evidence(
        {"name": "Future VIX", "value": 18.0, "date": "2026-06-16", "source_name": "yfinance"},
        function_id="get_vix",
        layer=2,
        effective_date="2025-04-09",
    )
    packet = AnalysisPacketBuilder().build(
        {
            "timestamp_utc": "2025-04-09T00:00:00Z",
            "backtest_date": "2025-04-09",
            "indicators": [_indicator("get_vix", raw, layer=2)],
        },
        manual_overrides={"active": False, "metrics": {}},
    )

    payload = packet.raw_data["L2"]["get_vix"]
    assert payload["value"] is None
    assert payload["error"] == "data_evidence_hard_block"
    assert packet.meta["indicator_successful"] == 0


def test_reporter_data_quality_box_displays_contract_source_dates_and_license():
    html = VNextReportGenerator(reports_dir="/tmp")._data_quality_box(
        {
            "contract_version": DATA_EVIDENCE_CONTRACT_VERSION,
            "provider": "Unit Provider",
            "source_name": "Unit Source",
            "source_url": "https://example.test/source",
            "source_tier": "third_party_estimate",
            "data_date": "2026-06-15",
            "as_of_date": "2026-06-15",
            "effective_date": "2026-06-16",
            "vintage_date": "not_available",
            "availability": "degraded",
            "fallback_reason": "none",
            "license_note": "public_endpoint_review_required",
            "coverage": {"scope": "unit"},
            "anomalies": ["missing_vintage"],
        }
    )

    assert DATA_EVIDENCE_CONTRACT_VERSION in html
    assert "Unit Provider" in html
    assert "effective=2026-06-16" in html
    assert "public_endpoint_review_required" in html


def test_manual_templates_include_data_evidence_contract_fields():
    for metric in manual_data.DEFAULT_MANUAL_DATA["metrics"].values():
        data_quality = metric["data_quality"]
        assert data_quality["contract_version"] == DATA_EVIDENCE_CONTRACT_VERSION
        assert data_quality["source_url"] == "missing"
        assert data_quality["license_note"] == "licensed_manual"
        assert "coverage" in data_quality
