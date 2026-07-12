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

SCHEMA_VERSION = "1"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ARCHIVE_ROOT = os.path.join(BASE_DIR, "output", "vintage_archive")

ISOLATION_NOTICE = (
    "isolated observation data; NOT promoted to a formal data source; "
    "MUST NOT be used as evidence_ref; MUST NOT enter the L1-L5 evidence chain"
)

# Official Invesco QQQ holdings API — same public endpoint already used by
# src/tools_L3.py's get_qqq_top10_concentration(). Re-implemented standalone
# here on purpose so this archiver has zero import dependency on the vNext
# pipeline (see BOUNDARY above).
INVESCO_QQQ_HOLDINGS_URL = (
    "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/"
    "holdings/fund?idType=ticker&interval=monthly&productType=ETF"
)
INVESCO_QQQ_HOLDINGS_PAGE = "https://www.invesco.com/qqq-etf/en/about.html#top-10-holdings"

# Static fallback used only if the live Invesco holdings fetch fails. Sourced
# from a live pull of INVESCO_QQQ_HOLDINGS_URL on 2026-07-12 (holdings
# effective date reported as 2026-07-10). Update this list if the script has
# been failing over to it for a while — it will go stale.
STATIC_TOP15_FALLBACK = [
    {"rank": 1, "ticker": "NVDA", "issuer_name": "NVIDIA Corp", "weight_pct": 8.015779},
    {"rank": 2, "ticker": "AAPL", "issuer_name": "Apple Inc", "weight_pct": 7.271526},
    {"rank": 3, "ticker": "MU", "issuer_name": "Micron Technology Inc", "weight_pct": 4.787834},
    {"rank": 4, "ticker": "MSFT", "issuer_name": "Microsoft Corp", "weight_pct": 4.491608},
    {"rank": 5, "ticker": "AMZN", "issuer_name": "Amazon.com Inc", "weight_pct": 4.143754},
    {"rank": 6, "ticker": "AMD", "issuer_name": "Advanced Micro Devices Inc", "weight_pct": 3.943158},
    {"rank": 7, "ticker": "GOOGL", "issuer_name": "Alphabet Inc Class A", "weight_pct": 3.266173},
    {"rank": 8, "ticker": "TSLA", "issuer_name": "Tesla Inc", "weight_pct": 3.198246},
    {"rank": 9, "ticker": "META", "issuer_name": "Meta Platforms Inc", "weight_pct": 3.111561},
    {"rank": 10, "ticker": "GOOG", "issuer_name": "Alphabet Inc Class C", "weight_pct": 3.041380},
    {"rank": 11, "ticker": "AVGO", "issuer_name": "Broadcom Inc", "weight_pct": 2.977513},
    {"rank": 12, "ticker": "WMT", "issuer_name": "Walmart Inc", "weight_pct": 2.408404},
    {"rank": 13, "ticker": "INTC", "issuer_name": "Intel Corp", "weight_pct": 2.392936},
    {"rank": 14, "ticker": "CSCO", "issuer_name": "Cisco Systems Inc", "weight_pct": 2.079934},
    {"rank": 15, "ticker": "AMAT", "issuer_name": "Applied Materials Inc", "weight_pct": 2.073488},
]
STATIC_TOP15_FALLBACK_DATED = "2026-07-12 (holdings effective 2026-07-10)"

README_TEXT = """# vintage_archive — isolated EPS-consensus observation store

## What this is

A daily raw snapshot of "current consensus" earnings/revenue estimates for
the top-weight NDX/QQQ constituents, pulled from yfinance
(`Ticker.eps_trend` / `eps_revisions` / `earnings_estimate` /
`revenue_estimate`) and, when available, FMP's `analyst-estimates` endpoint.

Produced by `src/vintage_archiver.py`.

## Why it exists

Wind has no usable US-equity consensus-EPS coverage (verified 2026-07-12).
No free source offers deep, multi-year, point-in-time earnings-revision
history. Snapshotting today's consensus every day is a zero-cost way to
build our own point-in-time vintage series going forward — but only if we
start now, since a snapshot taken today can never be reconstructed later.

## Boundary — isolated observation data, not a data source

This archive is **isolated observation data**. It is **NOT** promoted to a
formal data source. It **MUST NOT** be used as an `evidence_ref`, and it
**MUST NOT** enter the L1-L5 evidence chain. No `tools_*.py` module may
import or reference it. Promotion to a real data source requires a separate,
explicit decision (see CLAUDE.md 常驻边界 and
investigation_reports/20260711_first_principles/WORK_ORDERS.md, queue item 4).

## Layout

    output/vintage_archive/<YYYYMMDD>/eps_consensus.json

One file per UTC calendar day. Reruns on the same day overwrite that day's
file (idempotent — no accumulation of duplicates within a day).

## Suggested schedule

Run once per trading day after US market close, e.g. via crontab:

    30 21 * * 1-5 cd /Users/aidianchi/Desktop/ndx_mac && .venv/bin/python -m src.vintage_archiver >> output/logs/vintage_archiver.log 2>&1

(21:30 local is a placeholder — pick a time after both US close and FMP/Yahoo
data refresh in your timezone. Not installed automatically by this script.)
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


def _fetch_qqq_top_holdings(top_n: int = 15, timeout: int = 15) -> Dict[str, Any]:
    """Fetch official Invesco QQQ holdings and return the top-N by weight.

    Falls back to STATIC_TOP15_FALLBACK (truncated/padded to top_n) if the
    live fetch fails for any reason. Always returns a dict describing which
    path was taken.
    """
    try:
        response = requests.get(
            INVESCO_QQQ_HOLDINGS_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.invesco.com",
                "Referer": "https://www.invesco.com/qqq-etf/en/about.html",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        holdings_raw = data.get("holdings") if isinstance(data, dict) else None
        if not isinstance(holdings_raw, list) or not holdings_raw:
            raise ValueError("Invesco response missing holdings list")

        normalized = []
        for row in holdings_raw:
            ticker = str(row.get("ticker") or "").strip().upper()
            try:
                weight_pct = float(row.get("percentageOfTotalNetAssets"))
            except (TypeError, ValueError):
                continue
            if not ticker or weight_pct <= 0:
                continue
            normalized.append(
                {
                    "ticker": ticker,
                    "issuer_name": row.get("issuerName"),
                    "weight_pct": round(weight_pct, 6),
                    "security_type": row.get("securityTypeName"),
                }
            )
        normalized.sort(key=lambda item: item["weight_pct"], reverse=True)
        top = normalized[:top_n]
        for rank, item in enumerate(top, start=1):
            item["rank"] = rank

        effective_date = data.get("effectiveBusinessDate") or data.get("effectiveDate")
        return {
            "status": "ok",
            "method": "live_invesco_qqq_holdings_api",
            "source_name": "Invesco QQQ official holdings API",
            "source_url": INVESCO_QQQ_HOLDINGS_URL,
            "source_authority": "official_provider",
            "effective_date": str(effective_date)[:10] if effective_date else None,
            "total_holdings": data.get("totalNumberOfHoldings"),
            "fund_name": data.get("fundName") or data.get("shareClassName"),
            "constituents": top,
        }
    except Exception as exc:
        logger.warning("Live QQQ holdings fetch failed, using static fallback: %s", exc)
        fallback = [dict(item) for item in STATIC_TOP15_FALLBACK[:top_n]]
        return {
            "status": "fallback_used",
            "method": "static_fallback",
            "source_name": "Invesco QQQ official holdings API (static fallback, not live)",
            "source_url": INVESCO_QQQ_HOLDINGS_PAGE,
            "source_authority": "official_provider",
            "effective_date": None,
            "fallback_dated": STATIC_TOP15_FALLBACK_DATED,
            "fallback_reason": str(exc)[:200],
            "total_holdings": None,
            "fund_name": None,
            "constituents": fallback,
        }


def _fetch_yfinance_estimates(ticker: str) -> Dict[str, Any]:
    """Fetch eps_trend / eps_revisions / earnings_estimate / revenue_estimate."""
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
    try:
        yf_ticker = yf.Ticker(ticker)
    except Exception as exc:
        result["status"] = "error"
        result["reason"] = f"yf.Ticker init failed: {str(exc)[:200]}"
        return result

    any_ok = False
    for field in fields:
        try:
            df = getattr(yf_ticker, field)
            records = _df_to_records(df)
            if records:
                result["fields"][field] = {"status": "ok", "records": records}
                any_ok = True
            else:
                result["fields"][field] = {"status": "empty", "records": []}
        except Exception as exc:
            result["fields"][field] = {"status": "error", "reason": str(exc)[:200], "records": []}

    result["status"] = "ok" if any_ok else "empty"
    return result


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
    top_n: int = 15,
    use_fmp: bool = True,
    fmp_api_key: Optional[str] = None,
    request_delay_sec: float = 0.4,
) -> Dict[str, Any]:
    """Build the full archive payload for the given (or auto-discovered) tickers."""
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
    for idx, ticker in enumerate(ticker_list):
        entry: Dict[str, Any] = {}
        entry["yfinance"] = _fetch_yfinance_estimates(ticker)
        if use_fmp:
            entry["fmp"] = _fetch_fmp_estimates(ticker, fmp_api_key)
        else:
            entry["fmp"] = {"status": "skipped", "reason": "use_fmp=False"}
        per_ticker[ticker] = entry
        if idx < len(ticker_list) - 1 and request_delay_sec > 0:
            time.sleep(request_delay_sec)

    archive_date = now.strftime("%Y%m%d")
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "archive_date": archive_date,
        "collected_at_utc": _now_utc_iso(),
        "purpose": ISOLATION_NOTICE,
        "generator": "src/vintage_archiver.py",
        "universe": universe,
        "per_ticker": per_ticker,
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
    parser = argparse.ArgumentParser(description="Snapshot today's EPS/revenue consensus for top NDX/QQQ weights.")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated ticker override, e.g. NVDA,AAPL,MSFT")
    parser.add_argument("--top-n", type=int, default=15, help="How many top-weight constituents to archive (default 15)")
    parser.add_argument("--skip-fmp", action="store_true", help="Skip FMP calls entirely (yfinance only)")
    parser.add_argument("--out-dir", type=str, default=DEFAULT_ARCHIVE_ROOT, help="Override archive root directory (mainly for tests)")
    parser.add_argument("--request-delay", type=float, default=0.4, help="Seconds to sleep between tickers")
    args = parser.parse_args(argv)

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None

    logger.info("Building vintage archive (top_n=%s, use_fmp=%s)...", args.top_n, not args.skip_fmp)
    payload = build_archive(
        tickers=tickers,
        top_n=args.top_n,
        use_fmp=not args.skip_fmp,
        request_delay_sec=args.request_delay,
    )
    out_path = write_archive(payload, archive_root=args.out_dir)
    logger.info("Wrote %s", out_path)

    ok_count = sum(1 for v in payload["per_ticker"].values() if v["yfinance"].get("status") == "ok")
    logger.info("yfinance ok for %d/%d tickers; universe status=%s", ok_count, len(payload["per_ticker"]), payload["universe"]["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
