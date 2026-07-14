import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.checker import DataIntegrity
from core.collector import DataCollector
from core.evidence_families import EVIDENCE_FAMILIES, family_of


def test_every_layer_function_has_an_explicit_family_mapping():
    """Mapping-completeness gate: every function_id collector.py actually collects must have
    an explicit EVIDENCE_FAMILIES entry, not silently rely on family_of()'s singleton
    fallback. This is a safety net for future indicators (e.g. the two L4 buyback/earnings-
    calendar functions a parallel work stream is adding) so a missing mapping fails a test
    instead of silently degrading DataIntegrity's evidence-diversity accounting.
    """
    collector = DataCollector()
    all_function_ids = {
        function_id
        for functions in collector.LAYER_FUNCTIONS.values()
        for function_id in functions
    }

    missing = sorted(all_function_ids - set(EVIDENCE_FAMILIES.keys()))
    assert not missing, f"LAYER_FUNCTIONS entries missing an explicit EVIDENCE_FAMILIES mapping: {missing}"

    # The two L4 functions a parallel work stream is adding are pre-mapped per the work
    # order; if/when they land in LAYER_FUNCTIONS this assertion keeps them honest.
    if "get_m7_earnings_blackout_calendar" in all_function_ids:
        assert family_of("get_m7_earnings_blackout_calendar") == "corporate_earnings_calendar"
    if "get_m7_buyback_flow" in all_function_ids:
        assert family_of("get_m7_buyback_flow") == "corporate_buyback_flow"


def test_family_of_falls_back_to_singleton_for_unmapped_ids():
    assert family_of("get_totally_unmapped_future_indicator") == "get_totally_unmapped_future_indicator"


def _l5_indicator(function_id):
    return {"layer": 5, "function_id": function_id, "metric_name": function_id, "value": 1}


def test_same_family_dedup_lowers_family_confidence_but_not_function_availability():
    """11 members of the same evidence family (all L5 QQQ-technical functions, which share
    one underlying OHLCV feed) all succeed; 1 singleton-family function fails. Family scoring
    must treat those 11 as a single family worth at most one point, while the legacy
    function-level number keeps counting each of the 12 items as its own vote.
    """
    l5_function_ids = DataCollector().LAYER_FUNCTIONS[5]
    assert len(l5_function_ids) == 11

    data = {
        "indicators": [_l5_indicator(fid) for fid in l5_function_ids]
        + [{"layer": 1, "function_id": "get_totally_unrelated_metric", "error": "Timeout"}]
    }

    report = DataIntegrity().run(data)

    assert report["confidence_percent"] == 50.0
    assert report["function_availability_percent"] == 91.7


def test_future_violation_penalty_bites_harder_under_family_scoring():
    """One future_date_violation on a member of a 4-function family should cost the family
    score proportionally more than the same violation costs the (larger-denominator)
    function-level score, because the -1 penalty is subtracted from a family-count
    denominator instead of a function-count one -- the tightening direction the project's
    edit discipline requires.
    """
    l5_function_ids = list(DataCollector().LAYER_FUNCTIONS[5])[:4]
    tainted_fid = l5_function_ids[0]

    def _indicator_with_future_date(function_id):
        raw_data = {"value": {"level": 1}}
        if function_id == tainted_fid:
            raw_data["value"]["data_date"] = "2099-01-01"
        return {"layer": 5, "function_id": function_id, "metric_name": function_id, "raw_data": raw_data}

    data = {
        "backtest_date": "2025-04-09",
        "indicators": [_indicator_with_future_date(fid) for fid in l5_function_ids]
        + [{"layer": 1, "function_id": "get_singleton_metric", "value": 1}],
    }

    report = DataIntegrity().run(data)

    # 2 families present: qqq_ohlcv_technical (4 members, all otherwise successful) and the
    # singleton. Before the penalty both are fully available (raw family sum == 2.0, 2
    # families -> 100%). The -1 future_date_violation penalty wipes out the entire
    # qqq_ohlcv_technical family's contribution under family scoring (2.0 - 1 = 1.0, / 2
    # families = 50%), while the same -1 only costs one of five function-level votes
    # (5 - 1 = 4, / 5 = 80%).
    assert report["confidence_percent"] == 50.0
    assert report["function_availability_percent"] == 80.0
    assert (100.0 - report["confidence_percent"]) > (100.0 - report["function_availability_percent"])


def test_family_coverage_block_structure():
    l5_function_ids = DataCollector().LAYER_FUNCTIONS[5]
    data = {
        "indicators": [_l5_indicator(fid) for fid in l5_function_ids[:3]]
        + [{"layer": 1, "function_id": "get_fed_funds_rate", "value": 5.25}]
        + [{"layer": 2, "function_id": "get_vix", "error": "Timeout"}]
    }

    report = DataIntegrity().run(data)
    family_coverage = report["family_coverage"]

    assert family_coverage["families_total"] == 3  # qqq_ohlcv_technical, fed_funds_rate_official, volatility_indices
    assert family_coverage["families_available"] == 2
    assert family_coverage["family_coverage_pct"] == round(2 / 3 * 100, 1)

    per_family = family_coverage["per_family"]
    qqq_family = per_family["qqq_ohlcv_technical"]
    assert set(qqq_family["functions"]) == set(l5_function_ids[:3])
    assert qqq_family["succeeded"] == 3
    assert qqq_family["score"] == 1.0

    vix_family = per_family["volatility_indices"]
    assert vix_family["functions"] == ["get_vix"]
    assert vix_family["succeeded"] == 0
    assert vix_family["score"] == 0.0
