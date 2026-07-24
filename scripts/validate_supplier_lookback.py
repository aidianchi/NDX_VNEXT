#!/usr/bin/env python3
"""Validate Yahoo Finance's eps_trend "NdaysAgo" lookback fields against our
own daily vintage archive.

Purely a read-only analysis over already-collected archive snapshots
(`output/vintage_archive/YYYYMMDD/eps_consensus.json`). No network access,
no writes outside the two output artifacts this script is asked to produce.

For each observation date D where an archive exists at D and at D-7 (calendar
days), and for each ticker x period (0q/+1q/0y/+1y), we compare:

    lookback_side  = archive[D].per_ticker[ticker].yfinance.fields.eps_trend
                      .records[period]["7daysAgo"]
    actual_side    = archive[D-7].per_ticker[ticker].yfinance.fields.eps_trend
                      .records[period]["current"]

    relative_deviation = (lookback_side - actual_side) / actual_side

Pairs where either side is missing (ticker absent, status != "ok", period
absent, value is null, or actual_side == 0) are skipped and counted with a
reason instead of silently dropped.

This script produces no verdict. It only measures. The pass/fail gate
decision belongs to the orchestrating conversation, per E3 in
investigation_reports/20260723_l4_earnings_audit/WORK_ORDERS.md.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = ROOT / "output" / "vintage_archive"
PERIODS = ("0q", "+1q", "0y", "+1y")
TOLERANCE = 0.01  # |relative_deviation| <= 1% suggested tolerance from E3 spec

# Archive coverage starts here (earliest daily snapshot on disk as of this audit).
ARCHIVE_START = date(2026, 7, 12)


def _load_archive(day: date) -> dict[str, Any] | None:
    path = ARCHIVE_DIR / day.strftime("%Y%m%d") / "eps_consensus.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _eps_trend_records(archive: dict[str, Any], ticker: str) -> tuple[str, dict[str, dict[str, Any]] | None]:
    """Return (status_reason, period->record map) for a ticker's yfinance eps_trend.

    status_reason is "ok" when usable, otherwise a short machine reason string
    and the map is None.
    """
    per_ticker = archive.get("per_ticker", {})
    entry = per_ticker.get(ticker)
    if entry is None:
        return "ticker_missing", None
    yfin = entry.get("yfinance")
    if not isinstance(yfin, dict):
        return "yfinance_block_missing", None
    fields = yfin.get("fields", {})
    eps_trend = fields.get("eps_trend")
    if not isinstance(eps_trend, dict):
        return "eps_trend_field_missing", None
    status = eps_trend.get("status")
    if status != "ok":
        return f"source_status_{status}", None
    records = eps_trend.get("records", [])
    by_period = {r.get("period"): r for r in records if isinstance(r, dict) and r.get("period")}
    return "ok", by_period


def build_date_pairs(dates: list[date]) -> list[tuple[date, date]]:
    pairs = []
    for d in dates:
        d_minus_7 = d - timedelta(days=7)
        if _load_archive(d) is not None and _load_archive(d_minus_7) is not None:
            pairs.append((d, d_minus_7))
    return pairs


def validate(dates: list[date]) -> dict[str, Any]:
    date_pairs = build_date_pairs(dates)

    all_pairs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    skip_reason_counts: dict[str, int] = {}

    def _record_skip(day: date, day_minus_7: date, ticker: str, period: str | None, reason: str) -> None:
        skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1
        skipped.append(
            {
                "date": day.isoformat(),
                "date_minus_7": day_minus_7.isoformat(),
                "ticker": ticker,
                "period": period,
                "reason": reason,
            }
        )

    for d, d_minus_7 in date_pairs:
        archive_d = _load_archive(d)
        archive_d7 = _load_archive(d_minus_7)
        assert archive_d is not None and archive_d7 is not None  # guaranteed by build_date_pairs

        tickers = sorted(set(archive_d.get("per_ticker", {}).keys()) | set(archive_d7.get("per_ticker", {}).keys()))

        for ticker in tickers:
            lookback_status, lookback_map = _eps_trend_records(archive_d, ticker)
            actual_status, actual_map = _eps_trend_records(archive_d7, ticker)

            if lookback_status != "ok":
                for period in PERIODS:
                    _record_skip(d, d_minus_7, ticker, period, f"lookback_side_{lookback_status}")
                continue
            if actual_status != "ok":
                for period in PERIODS:
                    _record_skip(d, d_minus_7, ticker, period, f"actual_side_{actual_status}")
                continue

            for period in PERIODS:
                lookback_record = lookback_map.get(period)
                actual_record = actual_map.get(period)
                if lookback_record is None:
                    _record_skip(d, d_minus_7, ticker, period, "period_missing_lookback_side")
                    continue
                if actual_record is None:
                    _record_skip(d, d_minus_7, ticker, period, "period_missing_actual_side")
                    continue

                lookback_value = lookback_record.get("7daysAgo")
                actual_value = actual_record.get("current")

                if lookback_value is None:
                    _record_skip(d, d_minus_7, ticker, period, "lookback_value_null")
                    continue
                if actual_value is None:
                    _record_skip(d, d_minus_7, ticker, period, "actual_value_null")
                    continue
                if actual_value == 0:
                    _record_skip(d, d_minus_7, ticker, period, "actual_value_zero_division")
                    continue

                relative_deviation = (lookback_value - actual_value) / actual_value
                all_pairs.append(
                    {
                        "date": d.isoformat(),
                        "date_minus_7": d_minus_7.isoformat(),
                        "ticker": ticker,
                        "period": period,
                        "lookback_value": lookback_value,
                        "lookback_source": f"archive[{d.isoformat()}].eps_trend.7daysAgo",
                        "actual_value": actual_value,
                        "actual_source": f"archive[{d_minus_7.isoformat()}].eps_trend.current",
                        "relative_deviation": relative_deviation,
                        "abs_relative_deviation": abs(relative_deviation),
                    }
                )

    abs_devs = [p["abs_relative_deviation"] for p in all_pairs]
    outliers = [p for p in all_pairs if p["abs_relative_deviation"] > TOLERANCE]

    outliers_by_ticker: dict[str, int] = {}
    outliers_by_date: dict[str, int] = {}
    for o in outliers:
        outliers_by_ticker[o["ticker"]] = outliers_by_ticker.get(o["ticker"], 0) + 1
        outliers_by_date[o["date"]] = outliers_by_date.get(o["date"], 0) + 1

    def _quantile(data: list[float], q: float) -> float | None:
        if not data:
            return None
        s = sorted(data)
        if len(s) == 1:
            return s[0]
        # statistics.quantiles with n=100 gives 99 cut points; index q*100-1 approximates the qth percentile.
        pts = statistics.quantiles(s, n=100, method="inclusive")
        idx = min(max(int(round(q * 100)) - 1, 0), len(pts) - 1)
        return pts[idx]

    summary = {
        "date_pairs_used": [{"D": d.isoformat(), "D_minus_7": d7.isoformat()} for d, d7 in date_pairs],
        "total_candidate_pairs": len(all_pairs) + len(skipped),
        "total_valid_pairs": len(all_pairs),
        "total_skipped_pairs": len(skipped),
        "skip_reason_counts": skip_reason_counts,
        "abs_relative_deviation_stats": {
            "count": len(abs_devs),
            "min": min(abs_devs) if abs_devs else None,
            "median": statistics.median(abs_devs) if abs_devs else None,
            "p95": _quantile(abs_devs, 0.95),
            "max": max(abs_devs) if abs_devs else None,
            "mean": statistics.fmean(abs_devs) if abs_devs else None,
        },
        "share_within_1pct_tolerance": (
            sum(1 for x in abs_devs if x <= TOLERANCE) / len(abs_devs) if abs_devs else None
        ),
        "tolerance_used": TOLERANCE,
        "outlier_count": len(outliers),
        "outliers_by_ticker": dict(sorted(outliers_by_ticker.items(), key=lambda kv: -kv[1])),
        "outliers_by_date": dict(sorted(outliers_by_date.items())),
    }

    window_notes = _extended_window_notes()

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": (
            "For each D in the requested date list where archive[D] and archive[D-7] both exist, "
            "compare archive[D].per_ticker[ticker].yfinance.fields.eps_trend.records[period]['7daysAgo'] "
            "(the lookback side) against archive[D-7]...records[period]['current'] (the actual side). "
            "relative_deviation = (lookback - actual) / actual. This script issues no pass/fail verdict."
        ),
        "archive_dir": str(ARCHIVE_DIR.relative_to(ROOT)),
        "requested_dates": [d.isoformat() for d in dates],
        "summary": summary,
        "outliers": outliers,
        "pairs": all_pairs,
        "skipped": skipped,
        "extended_window_notes": window_notes,
    }


def _extended_window_notes() -> dict[str, Any]:
    """30/60/90-day lookback windows need archive[D] and archive[D-N] both present.

    Earliest verifiable D for each window = ARCHIVE_START + N days (first date at
    which a D-N archive reaching back to ARCHIVE_START exists).
    """
    notes = {}
    for label, n_days in (("30d", 30), ("60d", 60), ("90d", 90)):
        earliest_d = ARCHIVE_START + timedelta(days=n_days)
        notes[label] = {
            "earliest_verifiable_D": earliest_d.isoformat(),
            "reason": (
                f"archive[D-{n_days}] must exist; archive coverage starts at "
                f"{ARCHIVE_START.isoformat()}, so the earliest D with both sides present is "
                f"{ARCHIVE_START.isoformat()} + {n_days} days = {earliest_d.isoformat()}."
            ),
            "status": "not_yet_verifiable",
        }
    return notes


def _clean_for_json(value: Any) -> Any:
    if isinstance(value, float):
        # keep full precision; json module handles floats natively, this is a no-op
        # placeholder kept for symmetry with other scripts in this repo.
        return value
    if isinstance(value, dict):
        return {k: _clean_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_for_json(v) for v in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Yahoo eps_trend 7daysAgo lookback field against our own vintage archive."
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        default=["20260719", "20260720", "20260721", "20260722", "20260723"],
        help="Observation dates D (YYYYMMDD) to check; each needs archive[D] and archive[D-7] on disk.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=ROOT
        / "investigation_reports"
        / "20260723_l4_earnings_audit"
        / "E3_lookback_validation.json",
        help="Where to write the full pair-level JSON artifact.",
    )
    args = parser.parse_args()

    dates = [datetime.strptime(d, "%Y%m%d").date() for d in args.dates]
    result = validate(dates)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    with args.json_out.open("w", encoding="utf-8") as f:
        json.dump(_clean_for_json(result), f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"\nWrote full detail to {args.json_out}")


if __name__ == "__main__":
    main()
