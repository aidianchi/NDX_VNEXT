import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import manual_data


def test_blank_manual_simple_yield_gap_template_is_not_meaningful_override():
    metric = manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_equity_risk_premium"]

    assert manual_data.has_meaningful_manual_override(metric) is False


def test_manual_simple_yield_gap_level_is_meaningful_override():
    metric = json.loads(json.dumps(manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_equity_risk_premium"]))
    metric["value"]["level"] = -0.75
    metric["data_quality"]["data_date"] = "2026-04-30"

    assert manual_data.has_meaningful_manual_override(metric) is True


def test_manual_wind_template_uses_simple_yield_gap_not_wind_erp():
    serialized = json.dumps(manual_data.DEFAULT_MANUAL_DATA, ensure_ascii=False)

    assert "ERP_Wind" not in serialized
    assert "SIMPLE_YIELD_GAP" in serialized
    assert "not Damodaran implied ERP" in serialized
    assert "manual ERP reference" in serialized


def test_manual_l4_templates_include_data_authority_fields():
    required_fields = {
        "source_tier",
        "data_date",
        "collected_at_utc",
        "update_frequency",
        "formula",
        "coverage",
        "anomalies",
        "fallback_chain",
        "source_disagreement",
    }

    for function_id in ["get_ndx_pe_and_earnings_yield", "get_equity_risk_premium", "get_damodaran_us_implied_erp"]:
        data_quality = manual_data.DEFAULT_MANUAL_DATA["metrics"][function_id]["data_quality"]
        assert required_fields <= set(data_quality)
        assert data_quality["source_tier"] == "licensed_manual/Wind"


def test_manual_erp_reference_is_separate_from_simple_yield_gap():
    erp_metric = manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_damodaran_us_implied_erp"]
    simple_gap_metric = manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_equity_risk_premium"]

    assert "manual_erp" in erp_metric["value"]
    assert "manual_erp_percentile_5y" in erp_metric["value"]
    assert "manual_erp_percentile_10y" in erp_metric["value"]
    assert "manual_erp" not in simple_gap_metric["value"]
    assert "not NDX simple yield gap" in erp_metric["notes"]


def test_manual_erp_description_fields_do_not_trigger_override():
    metric = json.loads(json.dumps(manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_damodaran_us_implied_erp"]))
    metric["value"] = {
        "scope": "manual/Wind ERP reference; specify scope when used",
        "not_ndx_valuation_warning": "Manual ERP reference is not NDX PE percentile.",
    }

    assert manual_data.has_meaningful_manual_override(metric) is False


def test_manual_confidence_metadata_does_not_trigger_override():
    metric = json.loads(json.dumps(manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_ndx_pe_and_earnings_yield"]))
    metric["data_quality"]["coverage"]["confidence"] = "high"
    metric["source_name"] = "Wind"

    assert manual_data.has_meaningful_manual_override(metric) is False


# --- Work order #7: primary_fields-based meaningful-override classification ---


def test_primary_fields_declared_on_all_known_manual_slots():
    for function_id, metric in manual_data.DEFAULT_MANUAL_DATA["metrics"].items():
        assert "primary_fields" in metric, function_id
        assert isinstance(metric["primary_fields"], list) and metric["primary_fields"], function_id


def test_ndx_valuation_percentile_only_fill_is_not_meaningful_override():
    """Filling only a percentile/context field (1 of 17 value fields) must not
    flip the whole slot to manual_override_used=True; only the 8 primary
    valuation fields count."""
    metric = json.loads(json.dumps(manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_ndx_pe_and_earnings_yield"]))
    metric["value"]["PE_TTM_percentile_5y"] = 42.0
    metric["value"]["PE_TTM_percentile_10y"] = 55.0

    assert manual_data.has_meaningful_manual_override(metric) is False


def test_ndx_valuation_primary_field_fill_is_meaningful_override():
    metric = json.loads(json.dumps(manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_ndx_pe_and_earnings_yield"]))
    metric["value"]["PE_TTM"] = 35.4

    assert manual_data.has_meaningful_manual_override(metric) is True


def test_damodaran_manual_source_type_alone_is_not_meaningful_override():
    """manual_source_type is provenance metadata, not one of the three ERP
    primary_fields; declaring it without a number must not trigger override."""
    metric = json.loads(json.dumps(manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_damodaran_us_implied_erp"]))
    metric["value"]["manual_source_type"] = "wind_derived"

    assert manual_data.has_meaningful_manual_override(metric) is False


def test_damodaran_template_documents_manual_source_type_field():
    metric = manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_damodaran_us_implied_erp"]

    assert "manual_source_type" in metric["value"]
    assert metric["value"]["manual_source_type"] is None
    assert "damodaran_official" in metric["notes"]
    assert "not NDX simple yield gap" in metric["notes"]
    assert "manual ERP reference" in metric["notes"]


def test_nested_forward_earnings_primary_field_is_meaningful_override():
    """get_ndx_forward_earnings_quality nests its primary field inside
    value.m7.eps_revisions; primary_fields matching must reach that depth."""
    metric = json.loads(json.dumps(manual_data.DEFAULT_MANUAL_DATA["metrics"]["get_ndx_forward_earnings_quality"]))
    metric["value"]["m7"]["eps_revisions"]["revision_direction_30d"] = "up"

    assert manual_data.has_meaningful_manual_override(metric) is False

    metric["value"]["m7"]["eps_revisions"]["weighted_next_year_eps_revision_30d_pct"] = 1.5

    assert manual_data.has_meaningful_manual_override(metric) is True


def test_primary_fields_absent_falls_back_to_legacy_ignored_key_behavior():
    """Custom/ad-hoc manual metrics with no template (no primary_fields
    declared) keep the pre-work-order-7 ignored-key filtering behavior."""
    metric_metadata_only = {"value": {"method": "custom"}}
    assert manual_data.has_meaningful_manual_override(metric_metadata_only) is False

    metric_with_number = {"value": {"method": "custom", "custom_number": 3.2}}
    assert manual_data.has_meaningful_manual_override(metric_with_number) is True
