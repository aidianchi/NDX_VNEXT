import pandas as pd
import pytest
from datetime import date, timedelta
from pathlib import Path

from src import tools_L2
from src.agent_analysis.packet_builder import LAYER_FUNCTIONS as PACKET_LAYER_FUNCTIONS
from src.agent_analysis.deep_research_canon import get_indicator_canon
from src.core.collector import DataCollector
from src.data_evidence import CORE_EVIDENCE_FUNCTIONS, normalize_data_evidence


_ORIGINAL_RECENCY_GUARD = tools_L2._recent_positioning_date_error


@pytest.fixture(autouse=True)
def _keep_constructed_dates_inside_the_recent_window(monkeypatch):
    monkeypatch.setattr(tools_L2, "_recent_positioning_date_error", lambda _effective: None)


def _cftc_row(report_date="2026-07-14", *, long=120, short=80, open_interest=1000):
    return {
        "report_date_as_yyyy_mm_dd": report_date,
        "cftc_contract_market_code": "20974+",
        "market_and_exchange_names": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        "noncomm_positions_long_all": str(long),
        "noncomm_positions_short_all": str(short),
        "open_interest_all": str(open_interest),
    }


def _finra_frame(*rows):
    return pd.DataFrame(
        rows,
        columns=[
            "Year-Month",
            "Debit Balances in Customers' Securities Margin Accounts",
            "Free Credit Balances in Customers' Cash Accounts",
            "Free Credit Balances in Customers' Securities Margin Accounts",
        ],
    )


def test_cftc_tuesday_snapshot_is_invisible_before_friday(monkeypatch):
    monkeypatch.setattr(tools_L2, "_fetch_cftc_nq_legacy_rows", lambda: [_cftc_row()])

    result = tools_L2.get_cftc_nq_positioning("2026-07-16")

    assert result["availability"] == "unavailable"
    assert result["unavailable_reason"] == "no_cftc_snapshot_visible_by_effective_date"
    assert result["value"] is None


def test_cftc_visible_snapshot_keeps_legacy_classification_and_change(monkeypatch):
    monkeypatch.setattr(
        tools_L2,
        "_fetch_cftc_nq_legacy_rows",
        lambda: [
            _cftc_row("2026-07-14", long=120, short=80),
            _cftc_row("2026-07-07", long=100, short=90),
        ],
    )

    result = tools_L2.get_cftc_nq_positioning("2026-07-17")

    assert result["availability"] == "available"
    assert result["value"]["report_date"] == "2026-07-14"
    assert result["value"]["visible_date"] == "2026-07-17"
    assert result["value"]["noncommercial_net_contracts"] == 40
    assert result["value"]["weekly_change_net_contracts"] == 30
    assert result["value"]["leveraged_funds_net_contracts"] is None
    assert result["value"]["historical_percentile"] is None


def test_cftc_missing_week_does_not_relabel_multiweek_change(monkeypatch):
    monkeypatch.setattr(
        tools_L2,
        "_fetch_cftc_nq_legacy_rows",
        lambda: [
            _cftc_row("2026-07-14", long=120, short=80),
            _cftc_row("2026-06-30", long=100, short=90),
        ],
    )

    result = tools_L2.get_cftc_nq_positioning("2026-07-17")

    assert result["value"]["weekly_change_net_contracts"] is None
    assert result["value"]["weekly_change_status"] == "unavailable_missing_exact_prior_week"
    assert "exact_prior_week_missing_weekly_change_unavailable" in result["data_quality"]["anomalies"]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("long", float("nan")),
        ("short", float("inf")),
        ("open_interest", -1),
    ],
)
def test_cftc_nonfinite_or_negative_positions_fail_closed(monkeypatch, field, bad_value):
    values = {"long": 120, "short": 80, "open_interest": 1000}
    values[field] = bad_value
    monkeypatch.setattr(
        tools_L2,
        "_fetch_cftc_nq_legacy_rows",
        lambda: [_cftc_row("2026-07-14", **values)],
    )

    result = tools_L2.get_cftc_nq_positioning("2026-07-17")

    assert result["availability"] == "unavailable"
    assert result["value"] is None


def test_finra_month_is_invisible_before_conservative_three_week_gate(monkeypatch):
    frame = _finra_frame(("2026-04", 1000, 100, 120))
    monkeypatch.setattr(tools_L2, "_fetch_finra_margin_frame", lambda: frame)

    result = tools_L2.get_finra_margin_debt("2026-05-20")

    assert result["availability"] == "unavailable"
    assert result["unavailable_reason"] == "no_finra_month_visible_by_conservative_release_gate"
    assert result["value"] is None


def test_finra_visible_month_calculates_changes_from_visible_rows(monkeypatch):
    frame = _finra_frame(
        ("2026-04", 1100, 100, 120),
        ("2026-03", 1000, 90, 110),
        ("2025-04", 880, 80, 100),
    )
    monkeypatch.setattr(tools_L2, "_fetch_finra_margin_frame", lambda: frame)

    result = tools_L2.get_finra_margin_debt("2026-05-21")

    assert result["availability"] == "available"
    assert result["value"]["reference_month"] == "2026-04"
    assert result["value"]["estimated_visible_date"] == "2026-05-21"
    assert result["value"]["margin_debt_millions"] == 1100
    assert result["value"]["month_over_month_pct"] == 10.0
    assert result["value"]["year_over_year_pct"] == 25.0


def test_finra_column_reordering_does_not_change_field_meaning(monkeypatch):
    frame = _finra_frame(("2026-04", 1100, 100, 120))
    frame = frame[
        [
            tools_L2.FINRA_MARGIN_COLUMNS["cash_credit"],
            tools_L2.FINRA_MARGIN_COLUMNS["reference_month"],
            tools_L2.FINRA_MARGIN_COLUMNS["margin_credit"],
            tools_L2.FINRA_MARGIN_COLUMNS["margin_debt"],
        ]
    ]
    monkeypatch.setattr(tools_L2, "_fetch_finra_margin_frame", lambda: frame)

    result = tools_L2.get_finra_margin_debt("2026-05-21")

    assert result["value"]["margin_debt_millions"] == 1100
    assert result["value"]["cash_account_free_credit_millions"] == 100
    assert result["value"]["margin_account_free_credit_millions"] == 120


@pytest.mark.parametrize("bad_frame", [
    pd.DataFrame({"Year-Month": ["2026-04"]}),
    pd.DataFrame(
        [["2026-04", 1100, 9999, 100, 120]],
        columns=[
            "Year-Month",
            "Debit Balances in Customers' Securities Margin Accounts",
            "Debit Balances in Customers' Securities Margin Accounts",
            "Free Credit Balances in Customers' Cash Accounts",
            "Free Credit Balances in Customers' Securities Margin Accounts",
        ],
    ),
    _finra_frame(("2026-04", float("nan"), 100, 120)),
])
def test_finra_missing_duplicate_or_nonfinite_fields_fail_closed(monkeypatch, bad_frame):
    monkeypatch.setattr(tools_L2, "_fetch_finra_margin_frame", lambda: bad_frame)

    result = tools_L2.get_finra_margin_debt("2026-05-21")

    assert result["availability"] == "unavailable"
    assert result["value"] is None


@pytest.mark.parametrize("field_index", [1, 2, 3])
def test_finra_negative_balance_fields_fail_closed(monkeypatch, field_index):
    row = ["2026-04", 1100, 100, 120]
    row[field_index] = -1
    frame = _finra_frame(tuple(row))
    monkeypatch.setattr(tools_L2, "_fetch_finra_margin_frame", lambda: frame)

    result = tools_L2.get_finra_margin_debt("2026-05-21")

    assert result["availability"] == "unavailable"
    assert result["value"] is None


@pytest.mark.parametrize("bad_reference_month", ["Jun-26", "0001-06", "2026-13", "2026-08"])
def test_finra_invalid_or_future_reference_months_fail_closed(monkeypatch, bad_reference_month):
    frame = _finra_frame((bad_reference_month, 1100, 100, 120))
    monkeypatch.setattr(tools_L2, "_fetch_finra_margin_frame", lambda: frame)

    result = tools_L2.get_finra_margin_debt("2026-07-19")

    assert result["availability"] == "unavailable"
    assert result["value"] is None


def test_finra_excel_date_cell_is_accepted_as_reference_month(monkeypatch):
    frame = _finra_frame((pd.Timestamp("2026-04-01"), 1100, 100, 120))
    monkeypatch.setattr(tools_L2, "_fetch_finra_margin_frame", lambda: frame)

    result = tools_L2.get_finra_margin_debt("2026-05-21")

    assert result["availability"] == "available"
    assert result["value"]["reference_month"] == "2026-04"


def test_official_source_failure_is_honestly_unavailable(monkeypatch):
    def fail():
        raise RuntimeError("source down")

    monkeypatch.setattr(tools_L2, "_fetch_cftc_nq_legacy_rows", fail)
    monkeypatch.setattr(tools_L2, "_fetch_finra_margin_frame", fail)

    cftc = tools_L2.get_cftc_nq_positioning("2026-07-17")
    finra = tools_L2.get_finra_margin_debt("2026-07-17")

    assert cftc["availability"] == "unavailable"
    assert finra["availability"] == "unavailable"
    assert cftc["value"] is None and finra["value"] is None
    assert "official_source_unavailable" in cftc["unavailable_reason"]
    assert "official_source_unavailable" in finra["unavailable_reason"]


def test_official_positioning_permissions_and_runtime_registration():
    for function_id, value in (
        ("get_cftc_nq_positioning", {"noncommercial_net_contracts": 10}),
        ("get_finra_margin_debt", {"margin_debt_millions": 1000}),
    ):
        quality = normalize_data_evidence(
            {"value": value, "source_name": "official", "source_tier": "official"},
            function_id=function_id,
            layer=2,
            effective_date="2026-07-17",
        )["data_quality"]
        assert quality["metric_authority"]
        assert quality["downgrade_rules"]
        assert all(rule["usage"] == "supporting_only" for rule in quality["metric_authority"].values())
        assert all(rule["authority"] == "official_positioning_fact" for rule in quality["metric_authority"].values())
        assert function_id in CORE_EVIDENCE_FUNCTIONS
        assert function_id in DataCollector().LAYER_FUNCTIONS[2]
        assert function_id in PACKET_LAYER_FUNCTIONS["L2"]


def test_every_numeric_positioning_output_field_has_explicit_supporting_authority(monkeypatch):
    monkeypatch.setattr(
        tools_L2,
        "_fetch_cftc_nq_legacy_rows",
        lambda: [_cftc_row("2026-07-14"), _cftc_row("2026-07-07")],
    )
    monkeypatch.setattr(
        tools_L2,
        "_fetch_finra_margin_frame",
        lambda: _finra_frame(
            ("2026-04", 1100, 100, 120),
            ("2026-03", 1000, 90, 110),
            ("2025-04", 880, 80, 100),
        ),
    )
    payloads = [
        tools_L2.get_cftc_nq_positioning("2026-07-17"),
        tools_L2.get_finra_margin_debt("2026-05-21"),
    ]

    for payload in payloads:
        authority = payload["data_quality"]["metric_authority"]
        numeric_fields = {
            key
            for key, value in payload["value"].items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        assert numeric_fields <= set(authority)
        assert all(authority[field]["usage"] == "supporting_only" for field in numeric_fields)


def test_historical_dates_are_rejected_until_pit_archives_are_connected():
    old_date = date.today() - timedelta(days=tools_L2.OFFICIAL_POSITIONING_RECENT_WINDOW_DAYS + 1)

    assert _ORIGINAL_RECENCY_GUARD(old_date) == "historical_pit_archive_not_connected"


def test_fable_canon_text_is_present_in_runtime_and_research_canon():
    cftc = get_indicator_canon("get_cftc_nq_positioning")
    finra = get_indicator_canon("get_finra_margin_debt")
    canon_text = (Path(__file__).parents[1] / "RESEARCH_CANON.md").read_text(encoding="utf-8")

    assert cftc.b_prompt == 'COT 告诉你"船的一侧站了多少人"，不告诉你船什么时候翻。'
    assert finra.b_prompt == "看同比方向，别看创没创新高；它是月度后视镜，不是雷达。"
    assert cftc.b_prompt in canon_text
    assert finra.b_prompt in canon_text
