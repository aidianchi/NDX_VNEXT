#!/usr/bin/env python3
"""vintage_archiver.py — isolated daily archive of raw consensus-EPS snapshots.

WHY THIS EXISTS
----------------
Wind has no usable US-equity consensus-EPS coverage (verified 2026-07-12; see
investigation_reports/20260711_first_principles/WORK_ORDERS.md, queue item 4).
No free source offers deep, multi-year, point-in-time earnings-revision
history (IBES-style vintages are paid). This script is a zero-cost stopgap:
snapshot today's "current consensus" every day from yfinance + FMP, so that in
30-90 days we have a self-produced, genuinely point-in-time vintage series
that cannot be reconstructed retroactively. The earlier this starts, the more
history it will have accumulated by the time it is useful.

BOUNDARY — READ BEFORE WIRING THIS INTO ANYTHING
--------------------------------------------------
This archive is ISOLATED OBSERVATION DATA. Per CLAUDE.md 常驻边界:
    - It is NOT a formal / promoted data source.
    - It MUST NOT be imported from or referenced by any tools_*.py module.
    - It MUST NOT enter the L1-L5 evidence chain.
    - It MUST NOT be used as an `evidence_ref` in any report.
Promotion to a real data source requires a separate, explicit decision.

USAGE
-----
    python -m src.vintage_archiver
    python src/vintage_archiver.py --tickers NVDA,AAPL,MSFT
    python src/vintage_archiver.py --skip-fmp
    python src/vintage_archiver.py --top-n 15

Writes output/vintage_archive/<YYYYMMDD>/eps_consensus.json (UTC date by
default). Idempotent: rerunning on the same UTC day overwrites that day's
file rather than accumulating duplicates.

SCHEMA_VERSION 2 (2026-07-23)
------------------------------
The collection universe was expanded from the top-15 QQQ weights to ALL
valid equity holdings reported by the Invesco QQQ holdings API (108 raw
rows as of 2026-07-22; ~103 are real equities after filtering out
cash/derivative/receivable lines — see `_classify_holding`). `--top-n` is
now an optional cap (default: no cap, archive everything); the per_ticker
record shape is unchanged, so downstream readers keyed by ticker (e.g.
src/expectation_ledger.py) need no changes. New additive fields:
`universe.fallback_used`, `universe.total_holdings_selected`,
`universe.filtered_out` / `filtered_out_count`, `universe.weight_pct_sum`,
and a top-level `collection_summary` block listing failed tickers / missing
fields for the day. yfinance fetches now retry transient whole-ticker
failures (see `_fetch_yfinance_estimates(attempts=...)`); a single bad
ticker no longer aborts the run.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a repo-wide dependency
    pass

try:
    import yfinance as yf

    YF_AVAILABLE = True
except ImportError:  # pragma: no cover
    yf = None
    YF_AVAILABLE = False

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vintage_archiver")

SCHEMA_VERSION = "2"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ARCHIVE_ROOT = os.path.join(BASE_DIR, "output", "vintage_archive")

ISOLATION_NOTICE = (
    "Promoted (2026-07-24, T15) as point-in-time material for NDX "
    "earnings-revision metrics; all other uses remain isolated observation "
    "data, NOT evidence_ref, and MUST NOT enter other L1-L5 evidence chains"
)

try:
    from .qqq_holdings import (
        EQUITY_SECURITY_TYPE_MARKERS,
        INVESCO_QQQ_HOLDINGS_PAGE,
        INVESCO_QQQ_HOLDINGS_URL,
        STATIC_FULL_FALLBACK,
        STATIC_FULL_FALLBACK_DATED,
        _classify_holding,
        _fetch_qqq_top_holdings,
    )
except ImportError:
    from qqq_holdings import (
        EQUITY_SECURITY_TYPE_MARKERS,
        INVESCO_QQQ_HOLDINGS_PAGE,
        INVESCO_QQQ_HOLDINGS_URL,
        STATIC_FULL_FALLBACK,
        STATIC_FULL_FALLBACK_DATED,
        _classify_holding,
        _fetch_qqq_top_holdings,
    )


README_TEXT = """# vintage_archive — isolated EPS-consensus observation store

## What this is

A daily raw snapshot of "current consensus" earnings/revenue estimates for
ALL valid equity holdings of NDX/QQQ (not just the top weights), pulled from
yfinance (`Ticker.eps_trend` / `eps_revisions` / `earnings_estimate` /
`revenue_estimate`) and, when available, FMP's `analyst-estimates` endpoint.

Produced by `src/vintage_archiver.py`.

## Why it exists

Wind has no usable US-equity consensus-EPS coverage (verified 2026-07-12).
No free source offers deep, multi-year, point-in-time earnings-revision
history. Snapshotting today's consensus every day is a zero-cost way to
build our own point-in-time vintage series going forward — but only if we
start now, since a snapshot taken today can never be reconstructed later.

## schema_version 2 (2026-07-23) — full-constituent expansion

The collection universe was expanded from the top-15 QQQ weights to ALL
valid equity holdings reported by the Invesco QQQ holdings API (103 equity
rows out of 108 raw holdings as of 2026-07-22; the other 5 rows are
cash/currency/futures/collateral lines, filtered out and recorded in
`universe.filtered_out`). `per_ticker` keeps the same per-ticker shape as
schema_version 1 — there are just more tickers in it — so any reader keyed
by ticker (e.g. `src/expectation_ledger.py`) needs no changes. New fields
added on top of the v1 shape:
  - `universe.fallback_used` (bool), `universe.total_holdings_selected`,
    `universe.filtered_out` / `filtered_out_count`, `universe.weight_pct_sum`
    (sum of archived weight_pct — a coverage check).
  - top-level `collection_summary`: per-day counts of yfinance ok/empty/error
    tickers, the failed-ticker list, and a missing-field list per ticker.
A static fallback (`STATIC_FULL_FALLBACK`, ~103 tickers) is still used if the
live Invesco holdings fetch fails; `universe.fallback_reason` and
`universe.fallback_dated` record why and how stale it is.

## Boundary — isolated observation data, not a data source

This archive is **isolated observation data** with exactly one scoped
promotion (see "Scoped promotion for T15" below). Outside that scope it is
**NOT** a formal data source: it **MUST NOT** be used as a general-purpose
`evidence_ref` and **MUST NOT** enter other L1-L5 evidence chains. Any
further promotion requires a separate, explicit decision (see CLAUDE.md
常驻边界 and investigation_reports/20260723_l4_earnings_audit/WORK_ORDERS.md
E3/E5).

## Layout

    output/vintage_archive/<YYYYMMDD>/eps_consensus.json

One file per UTC calendar day. Reruns on the same day overwrite that day's
file (idempotent — no accumulation of duplicates within a day).

## Suggested schedule

Run once per trading day after US market close, e.g. via crontab:

    30 21 * * 1-5 cd /Users/aidianchi/Desktop/ndx_mac && .venv/bin/python -m src.vintage_archiver >> output/logs/vintage_archiver.log 2>&1

(21:30 local is a placeholder — pick a time after both US close and FMP/Yahoo
data refresh in your timezone. Not installed automatically by this script.)

## Scoped promotion for T15 (2026-07-24)

The daily snapshots are promoted only as point-in-time material for the NDX
earnings-revision metrics (`NDX_EARNINGS_REVISION_METRICS`). Within that
family, a usable self-archive snapshot within ±2 calendar days of a 30/90-day
target anchor takes priority; supplier-reported lookbacks may only fill
uncovered ticker-windows and must retain their `supplier_lookback` label and
window-level validation status. All other uses remain isolated observation
data: the archive is not a general-purpose `evidence_ref` and must not enter
other L1-L5 evidence chains.
"""


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_scalar(value: Any) -> Any:
    """Make a pandas/numpy scalar JSON-safe (NaN/NaT -> None)."""
    if value is None:
        return None
    if pd is not None:
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _df_to_records(df: Any, index_name: str = "period") -> List[Dict[str, Any]]:
    """Convert a yfinance estimates DataFrame into JSON-safe records."""
    if df is None or pd is None:
        return []
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    reset = df.reset_index()
    reset = reset.rename(columns={reset.columns[0]: index_name})
    records: List[Dict[str, Any]] = []
    for row in reset.to_dict(orient="records"):
        records.append({str(k): _clean_scalar(v) for k, v in row.items()})
    return records


def _fetch_yfinance_estimates(ticker: str, attempts: int = 2, pause_seconds: float = 1.5) -> Dict[str, Any]:
    """Fetch eps_trend / eps_revisions / earnings_estimate / revenue_estimate.

    Retries the whole ticker (up to `attempts` times, with linear backoff)
    only when EVERY field errors out — that pattern indicates a transient
    network/rate-limit failure, not a ticker that legitimately lacks analyst
    coverage (which yfinance reports as empty-but-not-error and is not worth
    retrying). A single ticker's exhausted retries never raises — it is
    recorded as status="error" so the rest of the day's tickers still get
    fetched.
    """
    result: Dict[str, Any] = {
        "source_name": "yfinance Ticker estimates modules",
        "source_authority": "third_party_unofficial",
        "collected_at_utc": _now_utc_iso(),
        "fields": {},
    }
    if not YF_AVAILABLE:
        result["status"] = "skipped"
        result["reason"] = "yfinance not installed"
        return result

    fields = ["eps_trend", "eps_revisions", "earnings_estimate", "revenue_estimate"]
    attempts = max(1, attempts)
    last_error: Optional[str] = None

    for attempt in range(1, attempts + 1):
        try:
            yf_ticker = yf.Ticker(ticker)
        except Exception as exc:
            last_error = f"yf.Ticker init failed: {str(exc)[:200]}"
            if attempt < attempts:
                time.sleep(pause_seconds * attempt)
                continue
            result["status"] = "error"
            result["reason"] = last_error
            result["attempts"] = attempt
            return result

        field_results: Dict[str, Any] = {}
        any_ok = False
        any_error = False
        for field in fields:
            try:
                df = getattr(yf_ticker, field)
                records = _df_to_records(df)
                if records:
                    field_results[field] = {"status": "ok", "records": records}
                    any_ok = True
                else:
                    field_results[field] = {"status": "empty", "records": []}
            except Exception as exc:
                field_results[field] = {"status": "error", "reason": str(exc)[:200], "records": []}
                any_error = True

        if any_ok or not any_error:
            # Either got real data, or every field is a benign "empty" (no
            # coverage) — not a transient failure, so don't retry.
            result["fields"] = field_results
            result["status"] = "ok" if any_ok else "empty"
            result["attempts"] = attempt
            return result

        last_error = "; ".join(
            sorted({v["reason"] for v in field_results.values() if v.get("reason")})
        )[:200]
        if attempt < attempts:
            time.sleep(pause_seconds * attempt)
            continue
        result["fields"] = field_results
        result["status"] = "error"
        result["reason"] = last_error
        result["attempts"] = attempt
        return result

    return result  # pragma: no cover - loop always returns above


def _fetch_fmp_estimates(ticker: str, api_key: Optional[str], timeout: int = 15) -> Dict[str, Any]:
    """Fetch FMP's analyst-estimates endpoint and store the raw response."""
    result: Dict[str, Any] = {
        "source_name": "FMP analyst-estimates (stable endpoint)",
        "source_authority": "third_party_unofficial",
        "endpoint": "https://financialmodelingprep.com/stable/analyst-estimates",
        "collected_at_utc": _now_utc_iso(),
    }
    if not api_key:
        result["status"] = "skipped"
        result["reason"] = "FMP_API_KEY not set in environment/.env"
        return result

    url = (
        "https://financialmodelingprep.com/stable/analyst-estimates"
        f"?symbol={ticker}&period=annual&limit=4&apikey={api_key}"
    )
    try:
        response = requests.get(url, timeout=timeout)
    except Exception as exc:
        result["status"] = "error"
        result["reason"] = f"request failed: {str(exc)[:200]}"
        return result

    if response.status_code == 429:
        result["status"] = "skipped"
        result["reason"] = "rate_limited (HTTP 429)"
        return result
    if response.status_code != 200:
        result["status"] = "error"
        result["reason"] = f"HTTP {response.status_code}: {response.text[:200]}"
        return result

    try:
        payload = response.json()
    except Exception as exc:
        result["status"] = "error"
        result["reason"] = f"non-JSON response: {str(exc)[:200]}"
        return result

    if isinstance(payload, dict) and payload.get("Error Message"):
        result["status"] = "error"
        result["reason"] = str(payload.get("Error Message"))[:200]
        return result

    result["status"] = "ok" if payload else "empty"
    result["raw_response"] = payload
    return result


def build_archive(
    tickers: Optional[List[str]] = None,
    top_n: Optional[int] = None,
    use_fmp: bool = True,
    fmp_api_key: Optional[str] = None,
    request_delay_sec: float = 0.4,
    yf_retry_attempts: int = 2,
    yf_retry_pause_sec: float = 1.5,
) -> Dict[str, Any]:
    """Build the full archive payload for the given (or auto-discovered) tickers.

    Default universe (top_n=None) is ALL valid equity holdings reported by
    the Invesco QQQ holdings API — see _fetch_qqq_top_holdings. `top_n` is an
    optional cap kept for quick manual/test runs.
    """
    now = datetime.now(timezone.utc)
    holdings = None
    if tickers:
        constituents = [{"rank": i + 1, "ticker": t.upper(), "issuer_name": None, "weight_pct": None} for i, t in enumerate(tickers)]
        universe = {
            "status": "manual_override",
            "method": "cli_override",
            "source_name": "manual --tickers override",
            "source_url": None,
            "source_authority": "n/a",
            "effective_date": None,
            "total_holdings": None,
            "fund_name": None,
            "constituents": constituents,
        }
    else:
        universe = _fetch_qqq_top_holdings(top_n=top_n)

    ticker_list = [item["ticker"] for item in universe["constituents"]]

    if use_fmp and fmp_api_key is None:
        fmp_api_key = os.environ.get("FMP_API_KEY") or None

    per_ticker: Dict[str, Any] = {}
    failed_tickers: List[str] = []
    missing_fields_by_ticker: Dict[str, List[str]] = {}
    for idx, ticker in enumerate(ticker_list):
        entry: Dict[str, Any] = {}
        try:
            entry["yfinance"] = _fetch_yfinance_estimates(
                ticker, attempts=yf_retry_attempts, pause_seconds=yf_retry_pause_sec
            )
        except Exception as exc:  # belt-and-suspenders: one ticker must never abort the run
            entry["yfinance"] = {
                "source_name": "yfinance Ticker estimates modules",
                "source_authority": "third_party_unofficial",
                "collected_at_utc": _now_utc_iso(),
                "status": "error",
                "reason": f"unexpected exception: {str(exc)[:200]}",
                "fields": {},
            }
        if use_fmp:
            try:
                entry["fmp"] = _fetch_fmp_estimates(ticker, fmp_api_key)
            except Exception as exc:
                entry["fmp"] = {"status": "error", "reason": f"unexpected exception: {str(exc)[:200]}"}
        else:
            entry["fmp"] = {"status": "skipped", "reason": "use_fmp=False"}
        per_ticker[ticker] = entry

        yf_status = entry["yfinance"].get("status")
        if yf_status == "error":
            failed_tickers.append(ticker)
        missing = [
            field
            for field, payload in entry["yfinance"].get("fields", {}).items()
            if not isinstance(payload, dict) or payload.get("status") != "ok"
        ]
        if missing:
            missing_fields_by_ticker[ticker] = missing

        if idx < len(ticker_list) - 1 and request_delay_sec > 0:
            time.sleep(request_delay_sec)

    collection_summary = {
        "ticker_count": len(ticker_list),
        "yfinance_ok_count": sum(1 for e in per_ticker.values() if e["yfinance"].get("status") == "ok"),
        "yfinance_empty_count": sum(1 for e in per_ticker.values() if e["yfinance"].get("status") == "empty"),
        "yfinance_error_count": len(failed_tickers),
        "yfinance_failed_tickers": failed_tickers,
        "yfinance_missing_fields_by_ticker": missing_fields_by_ticker,
    }

    archive_date = now.strftime("%Y%m%d")
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "archive_date": archive_date,
        "collected_at_utc": _now_utc_iso(),
        "purpose": ISOLATION_NOTICE,
        "generator": "src/vintage_archiver.py",
        "universe": universe,
        "per_ticker": per_ticker,
        "collection_summary": collection_summary,
    }
    return payload


def _ensure_readme(archive_root: str) -> None:
    os.makedirs(archive_root, exist_ok=True)
    readme_path = os.path.join(archive_root, "README.md")
    # Always (re)write so README stays in sync with the script; cheap and idempotent.
    with open(readme_path, "w", encoding="utf-8") as handle:
        handle.write(README_TEXT)


def write_archive(payload: Dict[str, Any], archive_root: str = DEFAULT_ARCHIVE_ROOT) -> str:
    """Write payload to output/vintage_archive/<archive_date>/eps_consensus.json.

    Idempotent: overwrites the same-day file rather than accumulating copies.
    """
    _ensure_readme(archive_root)
    day_dir = os.path.join(archive_root, payload["archive_date"])
    os.makedirs(day_dir, exist_ok=True)
    out_path = os.path.join(day_dir, "eps_consensus.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot today's EPS/revenue consensus for all valid QQQ holdings.")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated ticker override, e.g. NVDA,AAPL,MSFT")
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Optional cap on how many top-weight constituents to archive (default: no cap, archive all valid equity holdings)",
    )
    parser.add_argument("--skip-fmp", action="store_true", help="Skip FMP calls entirely (yfinance only)")
    parser.add_argument("--out-dir", type=str, default=DEFAULT_ARCHIVE_ROOT, help="Override archive root directory (mainly for tests)")
    parser.add_argument("--request-delay", type=float, default=0.4, help="Seconds to sleep between tickers")
    parser.add_argument("--yf-retry-attempts", type=int, default=2, help="Max attempts per ticker for yfinance when every field fails")
    parser.add_argument("--yf-retry-pause", type=float, default=1.5, help="Base seconds to back off between yfinance retry attempts")
    args = parser.parse_args(argv)

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None

    logger.info("Building vintage archive (top_n=%s, use_fmp=%s)...", args.top_n, not args.skip_fmp)
    payload = build_archive(
        tickers=tickers,
        top_n=args.top_n,
        use_fmp=not args.skip_fmp,
        request_delay_sec=args.request_delay,
        yf_retry_attempts=args.yf_retry_attempts,
        yf_retry_pause_sec=args.yf_retry_pause,
    )
    out_path = write_archive(payload, archive_root=args.out_dir)
    logger.info("Wrote %s", out_path)

    summary = payload["collection_summary"]
    logger.info(
        "yfinance ok for %d/%d tickers (empty=%d, error=%d); universe status=%s",
        summary["yfinance_ok_count"],
        summary["ticker_count"],
        summary["yfinance_empty_count"],
        summary["yfinance_error_count"],
        payload["universe"]["status"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
