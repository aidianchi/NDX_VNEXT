#!/usr/bin/env python3
"""Probe whether ^NDX/^NDXE can replace QQQ/QQEW as a ratio input.

This script is intentionally small: it fetches close history, aligns dates,
calculates the ratio, and reports whether 5y/10y percentiles are usable.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_manager import calculate_long_term_stats  # noqa: E402
from tools_common import cached_yf_download, clean_yfinance_dataframe  # noqa: E402


def _fetch_close(ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
    raw = cached_yf_download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
    )
    frame = clean_yfinance_dataframe(raw)
    if frame.empty or "close" not in frame.columns:
        return pd.DataFrame(columns=["date", ticker])
    out = frame[["close"]].rename(columns={"close": ticker}).copy()
    out.index = pd.to_datetime(out.index)
    out = out.reset_index().rename(columns={"Date": "date", "index": "date"})
    out["date"] = pd.to_datetime(out["date"])
    out = out[out["date"] <= pd.Timestamp(end)]
    return out[["date", ticker]].dropna()


def _window_counts(ratio: pd.DataFrame, anchor: pd.Timestamp) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, years in [("5y", 5), ("10y", 10)]:
        start = anchor - pd.DateOffset(years=years)
        out[label] = int((ratio["date"] >= start).sum())
    return out


def _clean_number(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        return _clean_number(value.item())
    if isinstance(value, dict):
        return {key: _clean_number(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_clean_number(item) for item in value]
    return value


def probe_ratio(
    numerator: str,
    denominator: str,
    *,
    end_date: str | None,
    lookback_years: int,
) -> dict[str, Any]:
    end = pd.to_datetime(end_date).to_pydatetime() if end_date else datetime.now()
    start = end - timedelta(days=365 * lookback_years + 10)

    numerator_frame = _fetch_close(numerator, start, end)
    denominator_frame = _fetch_close(denominator, start, end)
    aligned = numerator_frame.merge(denominator_frame, on="date", how="inner").dropna()
    aligned = aligned[(aligned[numerator] > 0) & (aligned[denominator] > 0)]

    if aligned.empty:
        return {
            "status": "unavailable",
            "numerator": numerator,
            "denominator": denominator,
            "reason": "no common close history",
            "numerator_rows": len(numerator_frame),
            "denominator_rows": len(denominator_frame),
        }

    aligned["value"] = aligned[numerator] / aligned[denominator]
    ratio = aligned[["date", "value"]].sort_values("date")
    latest = ratio.iloc[-1]
    latest_value = float(latest["value"])
    anchor = pd.to_datetime(latest["date"]).normalize()
    stats = calculate_long_term_stats(ratio, latest_value, as_of_date=anchor)
    counts = _window_counts(ratio, anchor)

    status = "available"
    issues: list[str] = []
    if counts["5y"] < 252:
        issues.append("less_than_one_trading_year_for_5y_window")
    if counts["10y"] < 252 * 5:
        issues.append("less_than_five_trading_years_for_10y_window")
    if stats.get("percentile_10y") is None or pd.isna(stats.get("percentile_10y")):
        issues.append("10y_percentile_unavailable")
    if issues:
        status = "partial"

    if numerator == "^NDX" and denominator == "^NDXE":
        boundary = (
            "This is an index close ratio for NDX vs Nasdaq-100 Equal Weighted Index. "
            "It is not a tradable ETF spread and does not prove valuation is cheap or expensive."
        )
    else:
        boundary = (
            "This is a price ratio for the requested symbols. Confirm each leg's index methodology "
            "before using it as a pure market-cap-weighted vs equal-weight reference."
        )

    return _clean_number(
        {
            "status": status,
            "numerator": numerator,
            "denominator": denominator,
            "formula": f"{numerator} close / {denominator} close",
            "source_name": "yfinance/Yahoo daily close",
            "first_common_date": ratio["date"].iloc[0].strftime("%Y-%m-%d"),
            "latest_common_date": pd.to_datetime(latest["date"]).strftime("%Y-%m-%d"),
            "common_observations": int(len(ratio)),
            "latest_ratio": round(latest_value, 6),
            "percentile_5y": round(float(stats["percentile_5y"]), 4)
            if stats.get("percentile_5y") is not None and not pd.isna(stats.get("percentile_5y"))
            else None,
            "percentile_10y": round(float(stats["percentile_10y"]), 4)
            if stats.get("percentile_10y") is not None and not pd.isna(stats.get("percentile_10y"))
            else None,
            "z_score_10y": round(float(stats["z_score_10y"]), 4)
            if stats.get("z_score_10y") is not None and not pd.isna(stats.get("z_score_10y"))
            else None,
            "window_counts": counts,
            "issues": issues,
            "boundary": boundary,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe ^NDX/^NDXE ratio availability and percentiles.")
    parser.add_argument("--end-date", help="Optional YYYY-MM-DD observation cutoff.")
    parser.add_argument("--lookback-years", type=int, default=11)
    parser.add_argument("--compare-qqq-qqew", action="store_true")
    args = parser.parse_args()

    results = [
        probe_ratio("^NDX", "^NDXE", end_date=args.end_date, lookback_years=args.lookback_years)
    ]
    if args.compare_qqq_qqew:
        results.append(probe_ratio("QQQ", "QQEW", end_date=args.end_date, lookback_years=args.lookback_years))

    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
