#!/usr/bin/env python3
"""Validate Yahoo Finance's eps_trend "NdaysAgo" lookback fields against our
own daily vintage archive.

Purely a read-only analysis over already-collected archive snapshots
(`output/vintage_archive/YYYYMMDD/eps_consensus.json`). No network access,
no writes outside the two output artifacts this script is asked to produce.

For each observation date D where an archive exists at D and at D-N (calendar
days, N = --window), and for each ticker x period (0q/+1q/0y/+1y), we compare:

    lookback_side  = archive[D].per_ticker[ticker].yfinance.fields.eps_trend
                      .records[period]["{N}daysAgo"]
    actual_side    = archive[D-N].per_ticker[ticker].yfinance.fields.eps_trend
                      .records[period]["current"]

    relative_deviation = (lookback_side - actual_side) / actual_side

Pairs where either side is missing (ticker absent, status != "ok", period
absent, value is null, or actual_side == 0) are skipped and counted with a
reason instead of silently dropped.

Universe honesty: the archive started 2026-07-12 with a 15-ticker early
universe and only expanded to the full NDX constituent list later, so for
longer windows the verifiable ticker set is genuinely smaller than today's
universe. The summary therefore reports exactly which tickers were verifiable,
which current-universe tickers lack N-day history, and the earliest date a
full-universe validation becomes possible. No extrapolation.

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

WINDOWS = (7, 30, 60, 90)

# Historic defaults preserving the original E3 7-day gate behaviour.
DEFAULT_7D_DATES = ["20260719", "20260720", "20260721", "20260722", "20260723"]
DEFAULT_7D_JSON_OUT = (
    ROOT
    / "investigation_reports"
    / "20260723_l4_earnings_audit"
    / "E3_lookback_validation.json"
)


def _load_archive(day: date) -> dict[str, Any] | None:
    path = ARCHIVE_DIR / day.strftime("%Y%m%d") / "eps_consensus.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _archive_dates_on_disk() -> list[date]:
    dates = []
    for child in sorted(ARCHIVE_DIR.iterdir()):
        if not child.is_dir():
            continue
        try:
            day = datetime.strptime(child.name, "%Y%m%d").date()
        except ValueError:
            continue
        if (child / "eps_consensus.json").exists():
            dates.append(day)
    return dates


def _discover_verifiable_dates(window: int) -> list[date]:
    """All on-disk D where both archive[D] and archive[D-N] exist."""
    on_disk = set(_archive_dates_on_disk())
    return sorted(d for d in on_disk if d - timedelta(days=window) in on_disk)


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


def build_date_pairs(dates: list[date], window: int) -> list[tuple[date, date]]:
    pairs = []
    for d in dates:
        d_minus_n = d - timedelta(days=window)
        if _load_archive(d) is not None and _load_archive(d_minus_n) is not None:
            pairs.append((d, d_minus_n))
    return pairs


def _universe_facts() -> dict[str, Any]:
    """On-disk universe facts, derived only from the archives themselves.

    The archive began with a small early universe and later expanded to the
    full constituent list; both the expansion date and today's universe are
    measured from disk, never assumed.
    """
    counts: dict[str, int] = {}
    ticker_sets: dict[str, list[str]] = {}
    for day in _archive_dates_on_disk():
        archive = _load_archive(day)
        tickers = sorted((archive or {}).get("per_ticker", {}).keys())
        counts[day.isoformat()] = len(tickers)
        ticker_sets[day.isoformat()] = tickers
    if not counts:
        return {
            "ticker_count_by_date": {},
            "earliest_archive_date": None,
            "latest_archive_date": None,
            "latest_universe_tickers": [],
            "universe_expansion_date": None,
        }
    ordered = sorted(counts)
    earliest, latest = ordered[0], ordered[-1]
    initial_size = counts[earliest]
    expansion = next((d for d in ordered if counts[d] > initial_size), None)
    return {
        "ticker_count_by_date": counts,
        "earliest_archive_date": earliest,
        "latest_archive_date": latest,
        "latest_universe_tickers": ticker_sets[latest],
        "universe_expansion_date": expansion,
    }


def validate(dates: list[date], window: int = 7) -> dict[str, Any]:
    lookback_field = f"{window}daysAgo"
    date_pairs = build_date_pairs(dates, window)

    all_pairs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    skip_reason_counts: dict[str, int] = {}
    verifiable_tickers: set[str] = set()

    def _record_skip(day: date, day_minus_n: date, ticker: str, period: str | None, reason: str) -> None:
        skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1
        skipped.append(
            {
                "date": day.isoformat(),
                f"date_minus_{window}": day_minus_n.isoformat(),
                "ticker": ticker,
                "period": period,
                "reason": reason,
            }
        )

    for d, d_minus_n in date_pairs:
        archive_d = _load_archive(d)
        archive_dn = _load_archive(d_minus_n)
        assert archive_d is not None and archive_dn is not None  # guaranteed by build_date_pairs

        tickers = sorted(set(archive_d.get("per_ticker", {}).keys()) | set(archive_dn.get("per_ticker", {}).keys()))

        for ticker in tickers:
            lookback_status, lookback_map = _eps_trend_records(archive_d, ticker)
            actual_status, actual_map = _eps_trend_records(archive_dn, ticker)

            if actual_status == "ok":
                verifiable_tickers.add(ticker)

            if lookback_status != "ok":
                for period in PERIODS:
                    _record_skip(d, d_minus_n, ticker, period, f"lookback_side_{lookback_status}")
                continue
            if actual_status != "ok":
                for period in PERIODS:
                    _record_skip(d, d_minus_n, ticker, period, f"actual_side_{actual_status}")
                continue

            for period in PERIODS:
                lookback_record = lookback_map.get(period)
                actual_record = actual_map.get(period)
                if lookback_record is None:
                    _record_skip(d, d_minus_n, ticker, period, "period_missing_lookback_side")
                    continue
                if actual_record is None:
                    _record_skip(d, d_minus_n, ticker, period, "period_missing_actual_side")
                    continue

                lookback_value = lookback_record.get(lookback_field)
                actual_value = actual_record.get("current")

                if lookback_value is None:
                    _record_skip(d, d_minus_n, ticker, period, "lookback_value_null")
                    continue
                if actual_value is None:
                    _record_skip(d, d_minus_n, ticker, period, "actual_value_null")
                    continue
                if actual_value == 0:
                    _record_skip(d, d_minus_n, ticker, period, "actual_value_zero_division")
                    continue

                relative_deviation = (lookback_value - actual_value) / actual_value
                all_pairs.append(
                    {
                        "date": d.isoformat(),
                        f"date_minus_{window}": d_minus_n.isoformat(),
                        "ticker": ticker,
                        "period": period,
                        "lookback_value": lookback_value,
                        "lookback_source": f"archive[{d.isoformat()}].eps_trend.{lookback_field}",
                        "actual_value": actual_value,
                        "actual_source": f"archive[{d_minus_n.isoformat()}].eps_trend.current",
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

    universe = _universe_facts()
    latest_universe = set(universe["latest_universe_tickers"])
    without_history = sorted(latest_universe - verifiable_tickers)

    summary = {
        "window_days": window,
        "lookback_field": lookback_field,
        "date_pairs_used": [
            {
                "D": d.isoformat(),
                f"D_minus_{window}": dn.isoformat(),
                "ticker_count_D": len(_load_archive(d).get("per_ticker", {})),
                f"ticker_count_D_minus_{window}": len(_load_archive(dn).get("per_ticker", {})),
            }
            for d, dn in date_pairs
        ],
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
        "universe": {
            "verifiable_tickers": sorted(verifiable_tickers),
            "verifiable_ticker_count": len(verifiable_tickers),
            "latest_archive_date": universe["latest_archive_date"],
            "latest_universe_ticker_count": len(latest_universe),
            "tickers_without_lookback_history_count": len(without_history),
            "tickers_without_lookback_history": without_history,
            "universe_expansion_date": universe["universe_expansion_date"],
            "note": (
                "verifiable_tickers = tickers whose D-N archive side was usable in at least one "
                "date pair; tickers_without_lookback_history = current-universe tickers with no "
                f"usable archive {window} days before any tested D (universe expanded "
                "after the early archive window). Their absence is a history-length fact, "
                "not a data-quality verdict."
            ),
        },
    }

    window_notes = _extended_window_notes(universe)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": (
            f"For each D in the requested date list where archive[D] and archive[D-{window}] both exist, "
            f"compare archive[D].per_ticker[ticker].yfinance.fields.eps_trend.records[period]['{lookback_field}'] "
            f"(the lookback side) against archive[D-{window}]...records[period]['current'] (the actual side). "
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


def _extended_window_notes(universe: dict[str, Any] | None = None) -> dict[str, Any]:
    """30/60/90-day lookback windows need archive[D] and archive[D-N] both present.

    Earliest verifiable D for each window = ARCHIVE_START + N days (first date at
    which a D-N archive reaching back to ARCHIVE_START exists). Status is judged
    against the latest archive actually on disk, not the wall clock. The full
    constituent universe only entered the archive at the measured expansion
    date, so full-universe validation has its own later earliest-D.
    """
    if universe is None:
        universe = _universe_facts()
    latest_s = universe.get("latest_archive_date")
    latest = date.fromisoformat(latest_s) if latest_s else None
    expansion_s = universe.get("universe_expansion_date")
    expansion = date.fromisoformat(expansion_s) if expansion_s else None

    notes = {}
    for label, n_days in (("30d", 30), ("60d", 60), ("90d", 90)):
        earliest_d = ARCHIVE_START + timedelta(days=n_days)
        verifiable_now = latest is not None and latest >= earliest_d
        note: dict[str, Any] = {
            "earliest_verifiable_D": earliest_d.isoformat(),
            "reason": (
                f"archive[D-{n_days}] must exist; archive coverage starts at "
                f"{ARCHIVE_START.isoformat()}, so the earliest D with both sides present is "
                f"{ARCHIVE_START.isoformat()} + {n_days} days = {earliest_d.isoformat()}."
            ),
            "status": "verifiable_now" if verifiable_now else "not_yet_verifiable",
            "status_as_of_archive_date": latest_s,
        }
        if expansion is not None:
            full_earliest = expansion + timedelta(days=n_days)
            note["full_universe"] = {
                "universe_expansion_date": expansion_s,
                "earliest_verifiable_D": full_earliest.isoformat(),
                "status": (
                    "verifiable_now" if latest is not None and latest >= full_earliest else "not_yet_verifiable"
                ),
                "reason": (
                    f"the archive only holds the full constituent universe from {expansion_s} onward "
                    f"(measured on disk), so a full-universe {n_days}-day validation first becomes possible at "
                    f"{expansion_s} + {n_days} days = {full_earliest.isoformat()}; earlier D values validate "
                    "only the early smaller universe."
                ),
            }
        notes[label] = note
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
        description="Validate Yahoo eps_trend NdaysAgo lookback fields against our own vintage archive."
    )
    parser.add_argument(
        "--window",
        type=int,
        choices=WINDOWS,
        default=7,
        help="Lookback window in calendar days; compares archive[D]['{N}daysAgo'] vs archive[D-N]['current'].",
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        default=None,
        help=(
            "Observation dates D (YYYYMMDD) to check; each needs archive[D] and archive[D-N] on disk. "
            "Default: the historic E3 dates for --window 7; auto-discovered from on-disk archives "
            "for other windows."
        ),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Where to write the full pair-level JSON artifact (default keeps the historic E3 path for --window 7).",
    )
    args = parser.parse_args()

    if args.dates is not None:
        dates = [datetime.strptime(d, "%Y%m%d").date() for d in args.dates]
    elif args.window == 7:
        dates = [datetime.strptime(d, "%Y%m%d").date() for d in DEFAULT_7D_DATES]
    else:
        dates = _discover_verifiable_dates(args.window)

    if args.json_out is not None:
        json_out = args.json_out
    elif args.window == 7:
        json_out = DEFAULT_7D_JSON_OUT
    else:
        json_out = (
            ROOT
            / "investigation_reports"
            / "20260816_O12_supplier_lookback_专审"
            / f"E3_lookback_validation_{args.window}d.json"
        )

    result = validate(dates, window=args.window)

    json_out.parent.mkdir(parents=True, exist_ok=True)
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(_clean_for_json(result), f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"\nWrote full detail to {json_out}")


if __name__ == "__main__":
    main()
