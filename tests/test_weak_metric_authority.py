import pytest

from src.data_evidence import normalize_data_evidence


WEAK_FUNCTIONS = [
    "get_vix",
    "get_vxn",
    "get_copper_gold_ratio",
    "get_hyg_momentum",
    "get_xly_xlp_ratio",
    "get_crowdedness_dashboard",
    "get_vxn_vix_ratio",
    "get_cnn_fear_greed_index",
]


@pytest.mark.parametrize("function_id", WEAK_FUNCTIONS)
def test_weak_indicator_contract_carries_field_authority_and_downgrade_rules(function_id):
    normalized = normalize_data_evidence(
        {
            "name": function_id,
            "value": {"level": 20.0},
            "source_name": "yfinance proxy",
            "source_tier": "proxy",
        },
        function_id=function_id,
        layer=2,
        effective_date="2026-07-17",
    )

    quality = normalized["data_quality"]
    assert quality["metric_authority"]
    assert quality["downgrade_rules"]
    assert all(rule.get("usage") != "core_allowed" for rule in quality["metric_authority"].values())


def test_cnn_composite_and_submetrics_cannot_bypass_each_other():
    quality = normalize_data_evidence(
        {"value": {"score": 80, "sub_metrics": {}}, "source_name": "CNN Business"},
        function_id="get_cnn_fear_greed_index",
        layer=2,
        effective_date="2026-07-17",
    )["data_quality"]

    assert quality["metric_authority"]["score"]["usage"] == "supporting_only"
    assert quality["metric_authority"]["sub_metrics"]["usage"] == "audit_only"
    assert "composite_or_submetric_cannot_bypass_total_signal_semantics" in quality["downgrade_rules"]


def test_weak_policy_cannot_be_promoted_by_an_old_payload():
    quality = normalize_data_evidence(
        {
            "value": {"level": 17.0},
            "data_quality": {
                "metric_authority": {
                    "level": {"usage": "core_allowed", "authority": "official_fact"},
                },
            },
        },
        function_id="get_vix",
        layer=2,
        effective_date="2026-07-17",
    )["data_quality"]

    assert quality["metric_authority"]["level"]["usage"] == "supporting_only"
    assert quality["metric_authority"]["level"]["authority"] == "proxy_or_derived_observation"


def test_crowdedness_authority_keys_match_the_runtime_payload():
    quality = normalize_data_evidence(
        {"value": {"skew_index": {}, "qqq_put_call_ratio_oi": {}, "qqq_short_interest_percent": {}}},
        function_id="get_crowdedness_dashboard",
        layer=2,
        effective_date="2026-07-17",
    )["data_quality"]

    assert quality["metric_authority"]["qqq_put_call_ratio_oi"]["usage"] == "supporting_only"
    assert quality["metric_authority"]["qqq_short_interest_percent"]["usage"] == "audit_only"
    assert "put_call_ratio" not in quality["metric_authority"]


def test_unknown_weak_metric_fields_default_to_audit_only_even_if_producer_claims_core():
    quality = normalize_data_evidence(
        {
            "value": {"level": 17.0, "mystery_signal": 99},
            "data_quality": {
                "metric_authority": {
                    "mystery_signal": {"usage": "core_allowed", "authority": "official_fact"},
                },
            },
        },
        function_id="get_vix",
        layer=2,
        effective_date="2026-07-17",
    )["data_quality"]

    assert quality["metric_authority"]["mystery_signal"]["usage"] == "audit_only"
    assert quality["metric_authority"]["mystery_signal"]["authority"] == "proxy_or_derived_observation"


def test_malformed_authority_usage_fails_closed_to_audit_only():
    quality = normalize_data_evidence(
        {
            "value": {"level": 17.0},
            "data_quality": {"metric_authority": {"level": {"usage": "super_core"}}},
        },
        function_id="get_vix",
        layer=2,
        effective_date="2026-07-17",
    )["data_quality"]

    assert quality["metric_authority"]["level"]["usage"] == "audit_only"
