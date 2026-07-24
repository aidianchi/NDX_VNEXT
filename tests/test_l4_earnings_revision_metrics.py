"""Offline contract tests for the NDX earnings-revision metrics family."""

import json
from datetime import datetime as real_datetime, timedelta, timezone

import pandas as pd
import pytest

from src import tools_L4


TODAY = real_datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


class FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return TODAY if tz is not None else TODAY.replace(tzinfo=None)


def _holdings(rows, effective_date="2026-07-24"):
    return {
        "status": "ok",
        "fallback_used": False,
        "effective_date": effective_date,
        "constituents": [
            {
                "rank": index + 1,
                "ticker": ticker,
                "issuer_name": f"{ticker} Inc",
                "weight_pct": weight,
            }
            for index, (ticker, weight) in enumerate(rows)
        ],
    }


def _frame(rows):
    return pd.DataFrame.from_dict(rows, orient="index")


def _payload(
    *,
    current=(110.0, 220.0),
    ago7=(105.0, 210.0),
    ago30=(100.0, 200.0),
    ago90=(90.0, 180.0),
    revisions=((5, 1), (4, 1)),
    estimates=((10.0, 8.0, 12.0, 10), (20.0, 18.0, 24.0, 12)),
    fiscal_year_end=None,
    earnings_dates=(),
):
    return {
        "eps_trend": _frame(
            {
                "0y": {
                    "current": current[0],
                    "7daysAgo": ago7[0],
                    "30daysAgo": ago30[0],
                    "90daysAgo": ago90[0],
                },
                "+1y": {
                    "current": current[1],
                    "7daysAgo": ago7[1],
                    "30daysAgo": ago30[1],
                    "90daysAgo": ago90[1],
                },
            }
        ),
        "eps_revisions": _frame(
            {
                "0y": {
                    "upLast30days": revisions[0][0],
                    "downLast30days": revisions[0][1],
                },
                "+1y": {
                    "upLast30days": revisions[1][0],
                    "downLast30days": revisions[1][1],
                },
            }
        ),
        "earnings_estimate": _frame(
            {
                "0y": {
                    "avg": estimates[0][0],
                    "low": estimates[0][1],
                    "high": estimates[0][2],
                    "numberOfAnalysts": estimates[0][3],
                },
                "+1y": {
                    "avg": estimates[1][0],
                    "low": estimates[1][1],
                    "high": estimates[1][2],
                    "numberOfAnalysts": estimates[1][3],
                },
            }
        ),
        "info": (
            {"nextFiscalYearEnd": fiscal_year_end}
            if fiscal_year_end is not None
            else {}
        ),
        "calendar": (
            {"Earnings Date": list(earnings_dates)}
            if earnings_dates
            else {}
        ),
    }


def _install(monkeypatch, tmp_path, rows, payloads):
    monkeypatch.setattr(tools_L4, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        tools_L4,
        "_fetch_qqq_top_holdings",
        lambda top_n=None: _holdings(rows),
    )
    fake_module = tmp_path / "src" / "tools_L4.py"
    fake_module.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tools_L4, "__file__", str(fake_module))

    class FakeTicker:
        def __init__(self, ticker):
            self.data = payloads[ticker]

        @property
        def eps_trend(self):
            return self.data["eps_trend"]

        @property
        def eps_revisions(self):
            return self.data["eps_revisions"]

        @property
        def earnings_estimate(self):
            return self.data["earnings_estimate"]

        @property
        def info(self):
            return self.data["info"]

        @property
        def calendar(self):
            return self.data["calendar"]

    monkeypatch.setattr(tools_L4.yf, "Ticker", FakeTicker)


def _write_archive(tmp_path, day, values):
    path = (
        tmp_path
        / "output"
        / "vintage_archive"
        / day.strftime("%Y%m%d")
        / "eps_consensus.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    per_ticker = {}
    for ticker, (fy1, fy2) in values.items():
        per_ticker[ticker] = {
            "yfinance": {
                "fields": {
                    "eps_trend": {
                        "status": "ok",
                        "records": [
                            {"period": "0y", "current": fy1},
                            {"period": "+1y", "current": fy2},
                        ],
                    }
                }
            }
        }
    path.write_text(
        json.dumps({"archive_date": day.strftime("%Y%m%d"), "per_ticker": per_ticker}),
        encoding="utf-8",
    )


def test_slope_formula_archive_priority_and_fiscal_rollover_invalid(
    monkeypatch, tmp_path
):
    fiscal_weight = 182 / 365
    _install(
        monkeypatch,
        tmp_path,
        [("AAA", 70.0), ("ROLL", 30.0)],
        {
            "AAA": _payload(
                current=(110.0, 240.0),
                fiscal_year_end=TODAY.date() + timedelta(days=182),
            ),
            "ROLL": _payload(
                current=(110.0, 220.0),
                # Yahoo has already rolled 0y to the next fiscal year; the
                # immediately preceding same fiscal date is inside the 30d
                # lookback and makes the old/current 0y labels incomparable.
                fiscal_year_end=TODAY.date() - timedelta(days=10) + pd.DateOffset(years=1),
            ),
        },
    )
    anchor = TODAY.date() - timedelta(days=30)
    _write_archive(
        tmp_path,
        anchor,
        {"AAA": (100.0, 200.0), "ROLL": (100.0, 200.0)},
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()
    slope = result["value"]["slope_30d"]
    expected = fiscal_weight * 0.10 + (1 - fiscal_weight) * 0.20

    assert slope["value"] == pytest.approx(expected)
    assert slope["material"] == "self_archive"
    assert slope["verification_status"] == "not_applicable_self_archive"
    assert slope["coverage"]["weight_coverage_pct"] == pytest.approx(70.0)
    assert {
        row["ticker"]: row["reason"] for row in slope["invalid"]
    }["ROLL"] == "fiscal_rollover"
    detail = slope["constituents"][0]
    assert detail["fy1_revision"] == pytest.approx(0.10)
    assert detail["fy2_revision"] == pytest.approx(0.20)


def test_archive_anchor_accepts_plus_two_and_rejects_plus_three(
    monkeypatch, tmp_path
):
    _install(
        monkeypatch,
        tmp_path,
        [("AAA", 100.0)],
        # ago30 stays below the ill-defined-ratio bound (+25%, not a clean
        # doubling) so this test keeps exercising anchor acceptance only.
        {"AAA": _payload(current=(110.0, 220.0), ago30=(88.0, 176.0))},
    )
    target = TODAY.date() - timedelta(days=30)
    _write_archive(tmp_path, target + timedelta(days=2), {"AAA": (100.0, 200.0)})

    accepted = tools_L4.get_ndx_earnings_revision_metrics()
    accepted_detail = accepted["value"]["slope_30d"]["constituents"][0]
    assert accepted_detail["material"] == "self_archive"
    assert accepted_detail["actual_anchor_date"] == (
        target + timedelta(days=2)
    ).isoformat()
    assert accepted_detail["anchor_offset_days"] == 2
    assert accepted["divergence"]["30d"]["status"] == "comparable"

    archive_path = (
        tmp_path
        / "output"
        / "vintage_archive"
        / (target + timedelta(days=2)).strftime("%Y%m%d")
    )
    archive_path.rename(
        archive_path.with_name((target + timedelta(days=3)).strftime("%Y%m%d"))
    )
    rejected = tools_L4.get_ndx_earnings_revision_metrics()
    rejected_detail = rejected["value"]["slope_30d"]["constituents"][0]
    assert rejected_detail["material"] == "supplier_lookback"
    assert rejected["value"]["slope_30d"]["material"] == "supplier_lookback"
    assert (
        rejected["value"]["slope_30d"]["verification_status"]
        == "pending_validation"
    )


def test_supplier_track_labels_and_window_coverage(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        tmp_path,
        [("AAA", 70.0), ("BBB", 30.0)],
        {
            "AAA": _payload(),
            "BBB": _payload(current=(120.0, 210.0), ago30=(100.0, 200.0)),
        },
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()

    for key in ("slope_30d", "slope_90d"):
        block = result["value"][key]
        assert block["material"] == "supplier_lookback"
        assert block["verification_status"] == "pending_validation"
        assert block["coverage"]["weight_coverage_pct"] == pytest.approx(100.0)
        assert block["coverage"]["self_archive_constituents"] == 0
        assert block["coverage"]["supplier_lookback_constituents"] == 2
    assert result["window_effective_coverage_pct"] == {
        "30d": pytest.approx(100.0),
        "90d": pytest.approx(100.0),
    }


def test_seven_day_is_divergence_only_when_both_tracks_are_comparable(
    monkeypatch, tmp_path
):
    _install(
        monkeypatch,
        tmp_path,
        [("AAA", 100.0)],
        {
            "AAA": _payload(
                current=(110.0, 220.0),
                ago7=(100.0, 200.0),
            )
        },
    )
    _write_archive(
        tmp_path,
        TODAY.date() - timedelta(days=7),
        {"AAA": (102.0, 204.0)},
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()

    assert "slope_7d" not in result["value"]
    seven_day = result["divergence"]["7d"]
    assert seven_day["status"] == "comparable"
    assert (
        seven_day["supplier_verification_status"]
        == "verified_with_earnings_week_caveat"
    )
    assert seven_day["self_archive_slope"] == pytest.approx(110 / 102 - 1)
    assert seven_day["supplier_lookback_slope"] == pytest.approx(0.10)
    assert seven_day["weight_coverage_pct"] == pytest.approx(100.0)


def test_earnings_week_and_large_slope_flags_do_not_exclude(
    monkeypatch, tmp_path
):
    _install(
        monkeypatch,
        tmp_path,
        [("EARN", 60.0), ("JUMP", 40.0)],
        {
            "EARN": _payload(
                current=(101.0, 202.0),
                ago30=(100.0, 200.0),
                earnings_dates=(TODAY.date() + timedelta(days=3),),
            ),
            "JUMP": _payload(
                current=(140.0, 280.0),
                ago30=(100.0, 200.0),
            ),
        },
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()
    block = result["value"]["slope_30d"]
    flags = {row["ticker"]: row["reasons"] for row in block["flagged"]}

    assert "earnings_date_in_lookback_or_next_7d" in flags["EARN"]
    assert "absolute_slope_above_20pct" in flags["JUMP"]
    assert block["coverage"]["weight_coverage_pct"] == pytest.approx(100.0)
    assert block["flagged_weight_pct"] == pytest.approx(100.0)
    assert result["flagged_weight_pct"]["30d"] == pytest.approx(100.0)
    assert result["value"]["slope_30d"]["value"] == pytest.approx(
        0.6 * 0.01 + 0.4 * 0.40
    )


def test_breadth_dispersion_and_analyst_coverage_math(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        tmp_path,
        [("AAA", 60.0), ("BBB", 40.0)],
        {
            "AAA": _payload(
                revisions=((5, 1), (2, 0)),
                estimates=((10.0, 8.0, 12.0, 10), (20.0, 18.0, 24.0, 12)),
            ),
            "BBB": _payload(
                revisions=((0, 3), (1, 0)),
                estimates=((20.0, 10.0, 30.0, 5), (40.0, 36.0, 44.0, 8)),
            ),
        },
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()
    breadth = result["value"]["breadth_30d"]
    dispersion = result["value"]["dispersion_ntm"]
    coverage = result["value"]["analyst_coverage"]

    assert breadth["material"] == "supplier"
    assert breadth["verification_status"] == "supplier_reported_counts"
    assert breadth["value"]["0y"] == pytest.approx(20.0)
    assert breadth["value"]["+1y"] == pytest.approx(100.0)
    assert breadth["periods"]["0y"]["raw_up_revision_count"] == 5
    assert breadth["periods"]["0y"]["raw_down_revision_count"] == 4
    # Both use the 0.5 fallback fiscal weight:
    # AAA=(0.4+0.3)/2=0.35; BBB=(1.0+0.2)/2=0.6.
    assert dispersion["value"] == pytest.approx(0.6 * 0.35 + 0.4 * 0.60)
    assert dispersion["coverage"]["weight_coverage_pct"] == pytest.approx(100.0)
    assert coverage["value"]["weighted_mean"] == pytest.approx(8.0)
    assert coverage["value"]["minimum"] == 5
    assert coverage["coverage"]["weight_coverage_pct"] == pytest.approx(100.0)


def test_analyst_coverage_discloses_partial_weight(monkeypatch, tmp_path):
    aaa = _payload()
    bbb = _payload()
    bbb["earnings_estimate"].loc["0y", "numberOfAnalysts"] = None
    _install(
        monkeypatch,
        tmp_path,
        [("AAA", 70.0), ("BBB", 30.0)],
        {"AAA": aaa, "BBB": bbb},
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()
    coverage = result["value"]["analyst_coverage"]

    assert coverage["value"]["weighted_mean"] == pytest.approx(10.0)
    assert coverage["value"]["minimum"] == 10
    assert coverage["coverage"]["weight_coverage_pct"] == pytest.approx(70.0)


def test_historical_end_date_refuses_before_any_live_fetch(monkeypatch):
    monkeypatch.setattr(tools_L4, "datetime", FrozenDateTime)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("historical request must not call live holdings")

    monkeypatch.setattr(tools_L4, "_fetch_qqq_top_holdings", fail_if_called)
    result = tools_L4.get_ndx_earnings_revision_metrics(
        end_date="2026-07-23"
    )

    assert result["availability"] == "unavailable"
    assert result["value"] is None
    assert (
        result["unavailable_reason"]
        == "insufficient_point_in_time_archive_for_backtest"
    )
    assert "latest" not in result["notes"].lower()


def test_submetric_coverage_gate_nulls_each_block_and_slopes_control_top_level(
    monkeypatch, tmp_path
):
    partial = _payload(
        ago30=(None, None),
        ago90=(None, None),
        revisions=((None, None), (None, None)),
        estimates=((10.0, None, None, None), (20.0, None, None, None)),
    )
    _install(
        monkeypatch,
        tmp_path,
        [("GOOD", 60.0), ("MISSING", 40.0)],
        {"GOOD": _payload(), "MISSING": partial},
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()

    for key in (
        "slope_30d",
        "slope_90d",
        "breadth_30d",
        "dispersion_ntm",
        "analyst_coverage",
    ):
        block = result["value"][key]
        assert block["coverage"]["weight_coverage_pct"] == pytest.approx(60.0)
        assert block["availability"] == "unavailable"
        assert block["value"] is None
        assert block["reason"] == "insufficient_constituent_coverage"
    assert result["availability"] == "unavailable"


def test_ill_defined_ratio_base_rows_are_excluded_not_flagged(
    monkeypatch, tmp_path
):
    _install(
        monkeypatch,
        tmp_path,
        [("GOOD", 70.0), ("ZERO", 20.0), ("FLIP", 10.0)],
        {
            "GOOD": _payload(current=(103.0, 206.0), ago30=(100.0, 200.0)),
            # FY1 leg collapses to zero: a -100% "revision" is a data
            # artifact (observed live), not revision information.
            "ZERO": _payload(current=(0.0, 202.0), ago30=(100.0, 200.0)),
            # FY2 leg crosses zero inside the window: the ratio is undefined
            # information-wise even though it is numerically finite.
            "FLIP": _payload(current=(101.0, -1.0), ago30=(100.0, 0.4)),
        },
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()
    block = result["value"]["slope_30d"]

    invalid = {row["ticker"]: row for row in block["invalid"]}
    assert invalid["ZERO"]["reason"] == "ill_defined_ratio_base"
    assert invalid["FLIP"]["reason"] == "ill_defined_ratio_base"
    assert {row["ticker"] for row in block["constituents"]} == {"GOOD"}
    assert block["value"] == pytest.approx(0.03)
    assert block["coverage"]["weight_coverage_pct"] == pytest.approx(70.0)


def test_reliable_base_more_than_doubling_is_retained_winsorized_and_flagged(
    monkeypatch, tmp_path
):
    _install(
        monkeypatch,
        tmp_path,
        [("BASE", 50.0), ("WILD", 50.0)],
        {
            "BASE": _payload(current=(1.02, 2.04), ago30=(1.0, 2.0)),
            # Reliable, same-sign bases more than double. This is a valid large
            # revision, not an ill-defined ratio, so it remains in the sample
            # and is controlled by the existing winsor/flag rules.
            "WILD": _payload(current=(2.2, 4.4), ago30=(1.0, 2.0)),
        },
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()
    block = result["value"]["slope_30d"]
    wild = [row for row in block["constituents"] if row["ticker"] == "WILD"][0]

    assert wild["winsorized"] is True
    assert wild["slope_raw"] == pytest.approx(1.20)
    assert wild["slope"] == pytest.approx(0.50)
    assert "WILD" not in {row["ticker"] for row in block["invalid"]}
    assert block["winsorized_count"] == 1
    assert block["winsorized_weight_pct"] == pytest.approx(50.0)
    assert block["value"] == pytest.approx(0.5 * 0.02 + 0.5 * 0.50)
    assert "absolute_slope_above_20pct" in {
        reason
        for row in block["flagged"]
        for reason in row["reasons"]
    }


def test_winsorized_divergence_uses_raw_archive_slope(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        tmp_path,
        [("WILD", 100.0)],
        {
            "WILD": _payload(
                current=(2.2, 4.4),
                ago30=(2.0, 4.0),
            )
        },
    )
    _write_archive(
        tmp_path,
        TODAY.date() - timedelta(days=30),
        {"WILD": (1.0, 2.0)},
    )

    result = tools_L4.get_ndx_earnings_revision_metrics()
    row = result["divergence"]["30d"]["constituents"][0]

    assert row["archive_slope"] == pytest.approx(1.20)
    assert row["supplier_slope"] == pytest.approx(0.10)
    assert row["difference"] == pytest.approx(
        row["supplier_slope"] - row["archive_slope"]
    )
