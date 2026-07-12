import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4
from data_evidence import data_evidence_issues


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _quarter_native_fact(period_end, value, *, filed=None, form="10-Q", fy=None, fp=None):
    """A single-quarter (~90 day) duration fact, used as-is (not cumulative)."""
    end_dt = date.fromisoformat(period_end)
    start_dt = end_dt - timedelta(days=90)
    filed_date = filed or (end_dt + timedelta(days=25)).isoformat()
    return {
        "start": start_dt.isoformat(),
        "end": period_end,
        "val": value,
        "filed": filed_date,
        "form": form,
        "fy": fy,
        "fp": fp,
        "accn": f"acc-{period_end}",
    }


def _quarter_native_series(quarters, *, form_for_q4="10-K"):
    """quarters: list of (period_end_str, value_usd). Q4 (Oct-Dec end) uses 10-K form."""
    facts = []
    for period_end, value in quarters:
        month = int(period_end[5:7])
        form = form_for_q4 if month == 12 else "10-Q"
        facts.append(_quarter_native_fact(period_end, value, form=form))
    return {"units": {"USD": facts}}


AAPL_QUARTERS_2024 = [
    ("2024-03-31", 10_000_000_000),
    ("2024-06-30", 12_000_000_000),
    ("2024-09-30", 14_000_000_000),
    ("2024-12-31", 16_000_000_000),
]
AAPL_QUARTERS_2025 = [
    ("2025-03-31", 13_000_000_000),  # YoY vs 10B = +30%
    ("2025-06-30", 15_000_000_000),  # YoY vs 12B = +25%
    ("2025-09-30", 17_000_000_000),  # YoY vs 14B = +21.43%
    ("2025-12-31", 18_000_000_000),  # YoY vs 16B = +12.5%
]


def _aapl_payload():
    return _quarter_native_series(AAPL_QUARTERS_2024 + AAPL_QUARTERS_2025)


def _make_fetch_stub(payloads_by_cik_tag, calls=None):
    def fake_fetch(cik, tag):
        if calls is not None:
            calls.append((cik, tag))
        payload = payloads_by_cik_tag.get((cik, tag))
        if payload is None:
            return {}, "tag_not_reported_by_filer"
        return payload, None

    return fake_fetch


# ---------------------------------------------------------------------------
# Helper-level unit tests
# ---------------------------------------------------------------------------

def test_duration_facts_before_filters_by_filed_date_and_dedups_restatements():
    units = {
        "USD": [
            {"start": "2025-01-01", "end": "2025-03-31", "val": 10, "filed": "2025-04-25", "form": "10-Q"},
            # Restatement of the same period filed later: should win over the first.
            {"start": "2025-01-01", "end": "2025-03-31", "val": 11, "filed": "2025-05-01", "form": "10-Q"},
            # Filed after end_date: must be excluded entirely (PIT discipline).
            {"start": "2025-04-01", "end": "2025-06-30", "val": 22, "filed": "2025-07-25", "form": "10-Q"},
            # Wrong form: excluded.
            {"start": "2025-01-01", "end": "2025-03-31", "val": 999, "filed": "2025-04-20", "form": "8-K"},
        ]
    }

    facts = tools_L4._sec_xbrl_duration_facts_before(units, end_date="2025-05-15")

    assert len(facts) == 1
    assert facts[0]["val"] == 11
    assert facts[0]["filed"] == "2025-05-01"


def test_derive_discrete_quarters_from_cumulative_ytd_chain():
    # One fiscal year reported YTD-cumulative (typical 10-Q cash-flow convention):
    # Q1=10 (as-is), H1=22 (cum) -> Q2=12, 9mo=36 (cum) -> Q3=14, FY=52 (cum) -> Q4=16.
    facts = [
        {"start": "2024-01-01", "end": "2024-03-31", "val": 10, "filed": "2024-04-25", "form": "10-Q", "fy": 2024, "fp": "Q1"},
        {"start": "2024-01-01", "end": "2024-06-30", "val": 22, "filed": "2024-07-25", "form": "10-Q", "fy": 2024, "fp": "Q2"},
        {"start": "2024-01-01", "end": "2024-09-30", "val": 36, "filed": "2024-10-25", "form": "10-Q", "fy": 2024, "fp": "Q3"},
        {"start": "2024-01-01", "end": "2024-12-31", "val": 52, "filed": "2025-02-01", "form": "10-K", "fy": 2024, "fp": "FY"},
    ]

    discrete = tools_L4._derive_discrete_quarters_from_cumulative(facts)

    values = [row["value"] for row in discrete]
    assert values == [10, 12, 14, 16]
    # Q1's own duration happens to be ~1 quarter, so it is labeled
    # quarter_native_duration even though it is also the first link of a
    # longer YTD-cumulative chain -- both descriptions are true for Q1.
    assert discrete[0]["derivation"] == "quarter_native_duration"
    assert discrete[1]["derivation"] == "discrete_quarter_from_cumulative_ytd_diff"
    assert discrete[3]["derivation"] == "discrete_quarter_from_cumulative_ytd_diff"
    assert discrete[3]["period_end"] == "2024-12-31"
    assert discrete[3]["filed_date"] == "2025-02-01"


def test_derive_discrete_quarters_treats_isolated_quarter_length_fact_as_native():
    facts = [
        {"start": "2025-01-01", "end": "2025-03-31", "val": 10, "filed": "2025-04-25", "form": "10-Q"},
        {"start": "2025-04-01", "end": "2025-06-30", "val": 12, "filed": "2025-07-25", "form": "10-Q"},
    ]

    discrete = tools_L4._derive_discrete_quarters_from_cumulative(facts)

    assert [row["value"] for row in discrete] == [10, 12]
    assert all(row["derivation"] == "quarter_native_duration" for row in discrete)


def test_calendar_quarter_label_and_prior_year_lookup():
    assert tools_L4._calendar_quarter_label("2025-06-30") == "2025Q2"
    assert tools_L4._calendar_quarter_label("2025-12-31") == "2025Q4"
    assert tools_L4._calendar_quarter_label(None) is None
    assert tools_L4._prior_year_calendar_quarter_label("2025Q2") == "2024Q2"
    assert tools_L4._prior_year_calendar_quarter_label(None) is None


# ---------------------------------------------------------------------------
# End-to-end get_m7_capex_cycle tests
# ---------------------------------------------------------------------------

def test_capex_cycle_falls_back_across_xbrl_tag_variants(monkeypatch):
    calls = []
    primary_tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[0]
    fallback_tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[1]
    payloads = {("0000320193", fallback_tag): _aapl_payload()}

    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {"AAPL": "0000320193"})
    monkeypatch.setattr(tools_L4, "_fetch_sec_xbrl_companyconcept", _make_fetch_stub(payloads, calls=calls))

    result = tools_L4.get_m7_capex_cycle(end_date="2026-07-10")

    aapl = result["value"]["companies"]["AAPL"]
    assert aapl["xbrl_tag"] == fallback_tag
    assert ("0000320193", primary_tag) in calls
    assert aapl["availability"] == "available"


def test_capex_cycle_full_contract_and_yoy_for_single_company(monkeypatch):
    primary_tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[0]
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {"AAPL": "0000320193"})
    monkeypatch.setattr(
        tools_L4,
        "_fetch_sec_xbrl_companyconcept",
        _make_fetch_stub({("0000320193", primary_tag): _aapl_payload()}),
    )

    result = tools_L4.get_m7_capex_cycle(end_date="2026-07-10")

    assert result["source_tier"] == tools_L4.SOURCE_TIER_OFFICIAL
    assert result["availability"] == "available"
    dq = result["data_quality"]
    assert dq["contract_version"] == "data_evidence_v1"
    assert dq["source_tier"] == tools_L4.SOURCE_TIER_OFFICIAL
    assert dq["vintage_date"] == "2026-01-25"  # latest filed_date among AAPL facts used (2025-12-31 quarter + 25d)
    assert dq["coverage"]["companies_available"] == 1
    assert dq["metric_authority"]["companies_sec_xbrl"]["usage"] == "core_allowed"
    assert "companies_yfinance_fallback" not in dq["metric_authority"]
    assert dq["metric_authority"]["yoy_acceleration"]["usage"] == "supporting_only"
    assert dq["pit_safe_summary"]["yfinance_fallback_companies_not_pit_safe"] == []

    aapl = result["value"]["companies"]["AAPL"]
    assert aapl["primary_source"] == "sec_xbrl"
    assert aapl["pit_safe"] is True
    assert aapl["coverage_quarters"] == 8
    quarters_by_label = {row["calendar_quarter"]: row for row in aapl["quarters"]}
    assert quarters_by_label["2025Q1"]["value_usd_bn"] == 13.0
    assert quarters_by_label["2025Q1"]["yoy_pct"] == 30.0
    assert quarters_by_label["2025Q1"]["source"] == "sec_xbrl"
    assert quarters_by_label["2025Q1"]["pit_safe"] is True
    assert quarters_by_label["2025Q4"]["yoy_pct"] == 12.5
    assert quarters_by_label["2024Q1"]["yoy_pct"] is None  # no prior-year data available

    issues = data_evidence_issues(result, function_id="get_m7_capex_cycle")
    assert issues["hard_block"] == []


def test_capex_cycle_respects_point_in_time_effective_date(monkeypatch):
    """A 10-K filed 2026-02-01 covering FY2025 must not appear when end_date
    is set before that filing date, even though the fiscal period itself
    (2025-12-31) has already ended."""
    primary_tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[0]
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {"AAPL": "0000320193"})
    monkeypatch.setattr(
        tools_L4,
        "_fetch_sec_xbrl_companyconcept",
        _make_fetch_stub({("0000320193", primary_tag): _aapl_payload()}),
    )

    result = tools_L4.get_m7_capex_cycle(end_date="2026-01-15")

    aapl = result["value"]["companies"]["AAPL"]
    labels = {row["calendar_quarter"] for row in aapl["quarters"]}
    assert "2025Q4" not in labels
    assert "2025Q3" in labels
    assert result["data_quality"]["vintage_date"] <= "2026-01-15"


def test_capex_cycle_m7_aggregate_sums_by_calendar_quarter_with_coverage_threshold(monkeypatch):
    tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[0]
    tickers_ciks = {
        "AAPL": "0000000001",
        "MSFT": "0000000002",
        "GOOGL": "0000000003",
        "AMZN": "0000000004",
        "NVDA": "0000000005",
        # META, TSLA intentionally left without a CIK to exercise partial coverage.
    }
    # 2025Q4 values differ per company; total should be an exact sum.
    per_ticker_q4 = {"AAPL": 18_000_000_000, "MSFT": 20_000_000_000, "GOOGL": 14_000_000_000,
                      "AMZN": 16_000_000_000, "NVDA": 12_000_000_000}
    per_ticker_q4_prior = {"AAPL": 16_000_000_000, "MSFT": 17_000_000_000, "GOOGL": 12_000_000_000,
                            "AMZN": 13_000_000_000, "NVDA": 8_000_000_000}

    payloads = {}
    for ticker, cik in tickers_ciks.items():
        quarters_2024 = [
            ("2024-03-31", 5_000_000_000), ("2024-06-30", 5_500_000_000),
            ("2024-09-30", 6_000_000_000), ("2024-12-31", per_ticker_q4_prior[ticker]),
        ]
        quarters_2025 = [
            ("2025-03-31", 6_500_000_000), ("2025-06-30", 7_000_000_000),
            ("2025-09-30", 7_500_000_000), ("2025-12-31", per_ticker_q4[ticker]),
        ]
        payloads[(cik, tag)] = _quarter_native_series(quarters_2024 + quarters_2025)

    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: tickers_ciks)
    monkeypatch.setattr(tools_L4, "_fetch_sec_xbrl_companyconcept", _make_fetch_stub(payloads))

    result = tools_L4.get_m7_capex_cycle(end_date="2026-07-10")

    coverage = result["data_quality"]["coverage"]
    assert coverage["companies_available"] == 5
    assert set(coverage["companies_missing"]) == {"META", "TSLA"}

    by_quarter = {row["calendar_quarter"]: row for row in result["value"]["m7_aggregate"]["by_calendar_quarter"]}
    q4_2025 = by_quarter["2025Q4"]
    assert q4_2025["companies_covered_count"] == 5
    expected_sum_bn = sum(per_ticker_q4.values()) / 1e9
    assert q4_2025["sum_usd_bn"] == round(expected_sum_bn, 3)
    expected_yoy = (sum(per_ticker_q4.values()) / sum(per_ticker_q4_prior.values()) - 1.0) * 100.0
    assert q4_2025["yoy_pct"] == round(expected_yoy, 2)

    latest_covered = result["value"]["m7_aggregate"]["latest_covered_quarter"]
    assert latest_covered["calendar_quarter"] == "2025Q4"
    acceleration = result["value"]["m7_aggregate"]["yoy_acceleration"]
    assert acceleration is not None
    assert acceleration["direction"] in {"accelerating", "decelerating", "stable"}


def test_capex_cycle_aggregate_yoy_withheld_below_min_company_overlap(monkeypatch):
    tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[0]
    # Only 3 companies (below MIN_M7_CAPEX_COMPANIES_FOR_AGGREGATE=5) have data
    # for both the current and prior-year quarter.
    tickers_ciks = {"AAPL": "0000000001", "MSFT": "0000000002", "GOOGL": "0000000003"}
    payloads = {}
    for ticker, cik in tickers_ciks.items():
        payloads[(cik, tag)] = _quarter_native_series(
            [("2024-12-31", 5_000_000_000), ("2025-12-31", 6_000_000_000)]
        )
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: tickers_ciks)
    monkeypatch.setattr(tools_L4, "_fetch_sec_xbrl_companyconcept", _make_fetch_stub(payloads))

    result = tools_L4.get_m7_capex_cycle(end_date="2026-07-10")

    by_quarter = {row["calendar_quarter"]: row for row in result["value"]["m7_aggregate"]["by_calendar_quarter"]}
    q4_2025 = by_quarter["2025Q4"]
    assert q4_2025["companies_covered_count"] == 3
    assert q4_2025["yoy_pct"] is None
    assert result["value"]["m7_aggregate"]["latest_covered_quarter"] is None


def test_capex_cycle_unavailable_when_no_company_has_data_and_fallback_disabled(monkeypatch):
    """Explicit past end_date -> backtest context -> fallback must not even be
    attempted (network call would be a bug), so with no CIKs available at all
    the result must honestly degrade to unavailable via the SEC-only reason."""
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {})

    def fail_if_called(_ticker):
        raise AssertionError("yfinance fallback must not be attempted in a past-date/backtest context")

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_capex_quarterly", fail_if_called)

    result = tools_L4.get_m7_capex_cycle(end_date="2020-01-01")

    assert result["availability"] == "unavailable"
    assert result["unavailable_reason"] == "no_m7_company_capex_facts_available_from_sec_xbrl_or_yfinance_fallback"
    assert result["data_quality"]["availability"] == "unavailable"
    for ticker in tools_L4.M7_TICKERS:
        reason = result["value"]["companies"][ticker]["unavailable_reason"]
        assert "sec_xbrl:missing_cik" in reason
        assert "yfinance_fallback:yfinance_fallback_disabled_not_live_context_pit_unsafe" in reason
    issues = data_evidence_issues(result, function_id="get_m7_capex_cycle")
    assert issues["hard_block"] == []


def test_capex_cycle_falls_back_to_yfinance_when_sec_unavailable_in_live_context(monkeypatch):
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {})  # SEC unavailable for every company

    def fake_yfinance(ticker):
        if ticker != "AAPL":
            return [], "yfinance_quarterly_cashflow_empty"
        quarters = [
            {"period_end": "2024-03-31", "value": 10_000_000_000.0},
            {"period_end": "2024-06-30", "value": 12_000_000_000.0},
            {"period_end": "2025-03-31", "value": 13_000_000_000.0},
            {"period_end": "2025-06-30", "value": 15_000_000_000.0},
        ]
        return quarters, None

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_capex_quarterly", fake_yfinance)

    result = tools_L4.get_m7_capex_cycle(end_date=None)  # end_date=None is unconditionally live

    aapl = result["value"]["companies"]["AAPL"]
    assert aapl["availability"] == "available"
    assert aapl["primary_source"] == "yfinance_fallback"
    assert aapl["source_tier"] == tools_L4.SOURCE_TIER_THIRD_PARTY
    assert aapl["pit_safe"] is False
    assert "sec_xbrl_unavailable: missing_cik" in aapl["fallback_reason"]

    quarters_by_label = {row["calendar_quarter"]: row for row in aapl["quarters"]}
    assert quarters_by_label["2025Q1"]["source"] == "yfinance_fallback"
    assert quarters_by_label["2025Q1"]["pit_safe"] is False
    assert quarters_by_label["2025Q1"]["filed_date"] is None
    assert quarters_by_label["2025Q1"]["conservative_visible_after_date"] is not None
    assert quarters_by_label["2025Q1"]["yoy_pct"] == 30.0

    for other_ticker in ("MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"):
        assert result["value"]["companies"][other_ticker]["availability"] == "unavailable"


def test_capex_cycle_authority_and_source_tier_downgraded_for_fallback(monkeypatch):
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {})

    def fake_yfinance(ticker):
        if ticker != "MSFT":
            return [], "yfinance_quarterly_cashflow_empty"
        return [
            {"period_end": "2024-12-31", "value": 16_000_000_000.0},
            {"period_end": "2025-12-31", "value": 20_000_000_000.0},
        ], None

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_capex_quarterly", fake_yfinance)

    result = tools_L4.get_m7_capex_cycle(end_date=None)

    assert result["source_tier"] == tools_L4.SOURCE_TIER_THIRD_PARTY  # every available company came via fallback
    dq = result["data_quality"]
    assert "companies_sec_xbrl" not in dq["metric_authority"]
    fallback_authority = dq["metric_authority"]["companies_yfinance_fallback"]
    assert fallback_authority["usage"] == "supporting_only"
    assert fallback_authority["authority"] == "yahoo_normalized_cashflow_third_party_unofficial"
    assert dq["metric_authority"]["m7_aggregate"]["usage"] == "supporting_only"
    assert dq["vintage_date"] == "not_available"
    assert "vintage_date_not_available_fallback_lacks_filed_date" in dq["anomalies"]
    assert dq["pit_safe_summary"]["is_live_context"] is True
    assert dq["coverage"]["companies_via_yfinance_fallback"] == ["MSFT"]
    issues = data_evidence_issues(result, function_id="get_m7_capex_cycle")
    assert issues["hard_block"] == []


def test_capex_cycle_mixed_sources_produce_mixed_top_level_tier_and_aggregate_flags(monkeypatch):
    tag = tools_L4.M7_CAPEX_XBRL_TAG_CANDIDATES[0]
    monkeypatch.setattr(tools_L4, "_sec_cik_map", lambda: {"AAPL": "0000320193"})
    monkeypatch.setattr(
        tools_L4,
        "_fetch_sec_xbrl_companyconcept",
        _make_fetch_stub({("0000320193", tag): _aapl_payload()}),
    )

    def fake_yfinance(ticker):
        if ticker != "MSFT":
            return [], "yfinance_quarterly_cashflow_empty"
        # Same calendar quarters as AAPL's SEC series so 2025Q4 has mixed sources.
        return [
            {"period_end": "2024-12-31", "value": 16_000_000_000.0},
            {"period_end": "2025-12-31", "value": 20_000_000_000.0},
        ], None

    monkeypatch.setattr(tools_L4, "_fetch_yfinance_capex_quarterly", fake_yfinance)

    result = tools_L4.get_m7_capex_cycle(end_date=None)

    assert result["source_tier"] == tools_L4.SOURCE_TIER_MIXED_OFFICIAL_AND_THIRD_PARTY
    by_quarter = {row["calendar_quarter"]: row for row in result["value"]["m7_aggregate"]["by_calendar_quarter"]}
    q4_2025 = by_quarter["2025Q4"]
    assert set(q4_2025["sources_used"]) == {"sec_xbrl", "yfinance_fallback"}
    assert q4_2025["pit_safe"] is False
    assert q4_2025["sum_usd_bn"] == round(18.0 + 20.0, 3)


def test_capex_cycle_registered_in_evidence_contract_sets():
    from data_evidence import BACKTEST_VINTAGE_REQUIRED_FUNCTIONS, CORE_EVIDENCE_FUNCTIONS, COVERAGE_REQUIRED_FUNCTIONS, LATEST_ONLY_FUNCTIONS

    assert "get_m7_capex_cycle" in CORE_EVIDENCE_FUNCTIONS
    assert "get_m7_capex_cycle" in COVERAGE_REQUIRED_FUNCTIONS
    assert "get_m7_capex_cycle" in BACKTEST_VINTAGE_REQUIRED_FUNCTIONS
    # Deliberately PIT-safe (filters facts by filed_date <= end_date internally),
    # unlike the yfinance-latest-only functions in this set.
    assert "get_m7_capex_cycle" not in LATEST_ONLY_FUNCTIONS


def test_capex_cycle_wired_into_collector_and_packet_builder_and_registry():
    from core.collector import DataCollector
    from agent_analysis.packet_builder import LAYER_FUNCTIONS as PACKET_LAYER_FUNCTIONS
    from tools import TOOLS_REGISTRY

    assert "get_m7_capex_cycle" in DataCollector().LAYER_FUNCTIONS[4]
    assert "get_m7_capex_cycle" not in DataCollector.BACKTEST_UNSUPPORTED_FUNCTIONS
    assert "get_m7_capex_cycle" in PACKET_LAYER_FUNCTIONS["L4"]
    assert TOOLS_REGISTRY["get_m7_capex_cycle"] is tools_L4.get_m7_capex_cycle


def test_capex_cycle_indicator_canon_registered():
    from agent_analysis.deep_research_canon import INDICATOR_CANONS

    canon = INDICATOR_CANONS["get_m7_capex_cycle"]
    assert canon.layer.value == "L4"
    assert canon.permission_type.value == "fact"
    assert canon.b_prompt
