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
    assert "manual_erp" not in simple_gap_metric["value"]
    assert "not NDX simple yield gap" in erp_metric["notes"]
