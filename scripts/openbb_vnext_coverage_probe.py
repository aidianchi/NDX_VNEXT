#!/usr/bin/env python3
"""
OpenBB coverage probe for the vNext L1-L5 data stack.

This is a research artifact only. It does not feed production evidence, does
not alter the L1-L5 collector, and does not promote OpenBB output into
evidence_refs. It maps each existing function_id to candidate OpenBB commands,
runs small probes where safe, and writes JSON/CSV/Markdown results.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "output" / "openbb_coverage"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency exists in project env
    load_dotenv = None


CredentialMap = Dict[str, bool]
ProbeCallable = Callable[[Any, str, str], Any]

OPENBB_CREDENTIAL_FIELDS = {
    "alpha_vantage_api_key",
    "benzinga_api_key",
    "biztoc_api_key",
    "bls_api_key",
    "cftc_app_token",
    "congress_gov_api_key",
    "econdb_api_key",
    "eia_api_key",
    "finnhub_api_key",
    "fmp_api_key",
    "fred_api_key",
    "intrinio_api_key",
    "nasdaq_api_key",
    "polygon_api_key",
    "simfin_api_key",
    "tiingo_token",
    "tradier_api_key",
    "tradingeconomics_api_key",
}


@dataclass(frozen=True)
class Candidate:
    layer: int
    function_id: str
    current_source: str
    data_question: str
    current_backtest_boundary: str
    openbb_command: str
    provider: str
    replacement_rating: str
    backtest_fit: str
    notes: str
    probe: Optional[ProbeCallable] = None


def _load_dotenv() -> None:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
    env_aliases = {
        "FMP_API_KEY": "OPENBB_API_FMP_KEY",
        "FRED_API_KEY": "OPENBB_API_FRED_KEY",
        "ALPHA_VANTAGE_API_KEY": "OPENBB_API_ALPHA_VANTAGE_KEY",
        "POLYGON_API_KEY": "OPENBB_API_POLYGON_KEY",
    }
    for src, dst in env_aliases.items():
        value = os.getenv(src)
        if value and not os.getenv(dst):
            os.environ[dst] = value


def _safe_version(package: str) -> Optional[str]:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _to_df(result: Any):
    if result is None:
        return None
    if hasattr(result, "to_df"):
        return result.to_df()
    return result


def _frame_summary(result: Any) -> Dict[str, Any]:
    df = _to_df(result)
    if df is None:
        return {"row_count": 0, "columns": [], "date_fields": [], "latest_date": None}

    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        pd = None

    if hasattr(df, "empty"):
        columns = [str(col) for col in list(df.columns)]
        row_count = int(len(df))
        date_fields: List[str] = []
        latest_date = None
        for col in columns:
            low = col.lower()
            if low in {"date", "datetime", "timestamp", "reported_date", "period_ending", "expiration"} or "date" in low:
                date_fields.append(col)
                if low == "expiration":
                    continue
                if pd is not None and row_count:
                    parsed = pd.to_datetime(df[col], errors="coerce").dropna()
                    if not parsed.empty:
                        candidate = parsed.max()
                        try:
                            latest_date = candidate.strftime("%Y-%m-%d")
                        except AttributeError:
                            latest_date = str(candidate)
        if latest_date is None and row_count:
            try:
                idx = df.index
                if pd is not None and isinstance(idx, pd.DatetimeIndex):
                    parsed = pd.to_datetime(idx, errors="coerce")
                    parsed = parsed.dropna()
                    if len(parsed):
                        latest_date = parsed.max().strftime("%Y-%m-%d")
            except Exception:
                pass
        return {
            "row_count": row_count,
            "columns": columns[:40],
            "date_fields": date_fields[:10],
            "latest_date": latest_date,
        }

    if isinstance(df, dict):
        return {
            "row_count": 1,
            "columns": list(df.keys())[:40],
            "date_fields": [k for k in df if "date" in str(k).lower()][:10],
            "latest_date": None,
        }

    return {"row_count": 1, "columns": [], "date_fields": [], "latest_date": None}


def _run_probe(obb: Any, candidate: Candidate, start_date: str, end_date: str) -> Dict[str, Any]:
    base = {
        "layer": f"L{candidate.layer}",
        "function_id": candidate.function_id,
        "current_source": candidate.current_source,
        "data_question": candidate.data_question,
        "current_backtest_boundary": candidate.current_backtest_boundary,
        "openbb_command": candidate.openbb_command,
        "provider": candidate.provider,
        "replacement_rating": candidate.replacement_rating,
        "backtest_fit": candidate.backtest_fit,
        "notes": candidate.notes,
    }
    if candidate.probe is None:
        return {
            **base,
            "status": "not_probed",
            "row_count": 0,
            "columns": [],
            "date_fields": [],
            "latest_date": None,
            "duration_ms": 0,
            "error": None,
        }

    started = time.monotonic()
    try:
        result = candidate.probe(obb, start_date, end_date)
        summary = _frame_summary(result)
        status = "ok" if summary.get("row_count", 0) > 0 else "empty"
        return {
            **base,
            "status": status,
            **summary,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "error": None,
        }
    except Exception as exc:
        return {
            **base,
            "status": "error",
            "row_count": 0,
            "columns": [],
            "date_fields": [],
            "latest_date": None,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }


def _fred(symbol: str, min_lookback_days: int = 0) -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        query_start = start_date
        if min_lookback_days:
            query_start = (
                datetime.fromisoformat(end_date).date() - timedelta(days=min_lookback_days)
            ).isoformat()
        return obb.economy.fred_series(symbol, start_date=query_start, end_date=end_date, provider="fred")

    return run


def _fred_many(symbols: Iterable[str]) -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        import pandas as pd

        frames = []
        for symbol in symbols:
            frames.append(
                obb.economy.fred_series(symbol, start_date=start_date, end_date=end_date, provider="fred").to_df()
            )
        return pd.concat(frames, axis=1).sort_index() if frames else None

    return run


def _treasury_rates() -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        return obb.fixedincome.government.treasury_rates(
            start_date=start_date,
            end_date=end_date,
            provider="federal_reserve",
        )

    return run


def _index_price(symbol: str, provider: str = "cboe") -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        return obb.index.price.historical(symbol, start_date=start_date, end_date=end_date, provider=provider)

    return run


def _equity_price(symbol: str, provider: str) -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        return obb.equity.price.historical(symbol, start_date=start_date, end_date=end_date, provider=provider)

    return run


def _options_chains(symbol: str, provider: str = "cboe") -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        return obb.derivatives.options.chains(symbol, provider=provider)

    return run


def _etf_holdings(symbol: str, provider: str) -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        return obb.etf.holdings(symbol, provider=provider)

    return run


def _equity_metrics(symbol: str, provider: str) -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        return obb.equity.fundamental.metrics(symbol, provider=provider)

    return run


def _sec_company_fact(symbol: str, fact: str) -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        return obb.equity.compare.company_facts(symbol, fact=fact, provider="sec")

    return run


def _analyst_consensus(symbol: str) -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        return obb.equity.estimates.consensus(symbol, provider="fmp")

    return run


def _qqq_technical(indicator: str) -> ProbeCallable:
    def run(obb: Any, start_date: str, end_date: str) -> Any:
        prices = obb.equity.price.historical(
            "QQQ",
            start_date=(datetime.fromisoformat(start_date) - timedelta(days=180)).date().isoformat(),
            end_date=end_date,
            provider="yfinance",
        ).to_df()
        func = getattr(obb.technical, indicator)
        return func(data=prices, target="close")

    return run


def _coverage_candidates() -> List[Candidate]:
    return [
        Candidate(1, "get_10y2y_spread_bp", "FRED direct", "10Y minus 2Y Treasury spread", "Observation-date only; ALFRED first vintage not enforced.", "obb.economy.fred_series('T10Y2Y')", "fred", "candidate_direct", "good_with_vintage_caveat", "Official FRED series maps cleanly.", _fred("T10Y2Y")),
        Candidate(1, "get_fed_funds_rate", "FRED direct", "Effective fed funds / policy rate background", "Observation-date only; ALFRED first vintage not enforced.", "obb.economy.fred_series('DFF')", "fred", "candidate_direct", "good_with_vintage_caveat", "Direct official series.", _fred("DFF")),
        Candidate(1, "get_m2_yoy", "FRED direct plus local YoY formula", "M2 money stock YoY", "Observation-date only; revisions not first-vintage safe.", "obb.economy.fred_series('M2SL')", "fred", "candidate_partial", "good_with_vintage_caveat", "OpenBB supplies raw series; vNext still computes YoY semantics.", _fred("M2SL", min_lookback_days=800)),
        Candidate(1, "get_net_liquidity_momentum", "FRED direct plus local formula", "WALCL minus TGA minus reverse repo liquidity proxy", "Observation-date only; composite semantics stay local.", "obb.economy.fred_series(['WALCL','WTREGEN','RRPONTSYD'])", "fred", "candidate_partial", "good_with_vintage_caveat", "OpenBB can fetch pieces; vNext should keep formula and naming contract.", _fred_many(["WALCL", "WTREGEN", "RRPONTSYD"])),
        Candidate(1, "get_copper_gold_ratio", "yfinance futures/ETFs", "Copper/gold growth-risk proxy", "Price history can be date-filtered; exact instrument mapping matters.", "obb.equity.price.historical('CPER','GLD')", "yfinance", "candidate_partial", "proxy_only", "OpenBB can fetch ETF proxies; futures mapping needs separate validation.", _equity_price("GLD", "yfinance")),
        Candidate(1, "get_10y_treasury", "FRED direct", "10Y Treasury yield", "Observation-date only; ALFRED first vintage not enforced.", "obb.economy.fred_series('DGS10')", "fred", "candidate_direct", "good_with_vintage_caveat", "Direct official series.", _fred("DGS10")),
        Candidate(1, "get_10y_treasury", "Federal Reserve curve", "Full Treasury curve context", "Observation-date only; published table timing should be disclosed.", "obb.fixedincome.government.treasury_rates()", "federal_reserve", "candidate_direct", "good_with_publication_caveat", "Adds full curve fields for cross-check.", _treasury_rates()),
        Candidate(1, "get_10y_real_rate", "FRED direct", "10Y TIPS real yield", "Observation-date only; ALFRED first vintage not enforced.", "obb.economy.fred_series('DFII10')", "fred", "candidate_direct", "good_with_vintage_caveat", "Direct official series.", _fred("DFII10")),
        Candidate(1, "get_10y_breakeven", "FRED direct", "10Y breakeven inflation", "Observation-date only; ALFRED first vintage not enforced.", "obb.economy.fred_series('T10YIE')", "fred", "candidate_direct", "good_with_vintage_caveat", "Direct official series.", _fred("T10YIE")),
        Candidate(2, "get_vix", "yfinance/cache plus Alpha Vantage fallback", "VIX level and trend", "Daily price can be date-filtered.", "obb.index.price.historical('VIX')", "cboe", "candidate_direct", "good_for_observation_date", "CBOE is a cleaner primary provider than yfinance for VIX.", _index_price("VIX")),
        Candidate(2, "get_vxn", "yfinance", "Nasdaq volatility index", "Daily price can be date-filtered if symbol maps correctly.", "obb.index.price.historical('VXN')", "cboe", "candidate_direct", "needs_symbol_validation", "Needs symbol validation with CBOE naming.", _index_price("VXN")),
        Candidate(2, "get_vxn_vix_ratio", "yfinance pair formula", "Nasdaq vol premium vs broad vol", "Date-filtered price series; formula local.", "obb.index.price.historical('VXN'/'VIX')", "cboe", "candidate_partial", "needs_symbol_validation", "OpenBB can supply legs; vNext keeps ratio semantics.", _index_price("VIX")),
        Candidate(2, "get_hy_oas_bp", "FRED / ICE BofA", "High-yield OAS", "Observation-date only; FRED vintage caveat.", "obb.economy.fred_series('BAMLH0A0HYM2')", "fred", "candidate_direct", "good_with_vintage_caveat", "Direct official/provider series via FRED.", _fred("BAMLH0A0HYM2")),
        Candidate(2, "get_ig_oas_bp", "FRED / ICE BofA", "Investment-grade OAS", "Observation-date only; FRED vintage caveat.", "obb.economy.fred_series('BAMLC0A0CM')", "fred", "candidate_direct", "good_with_vintage_caveat", "Direct official/provider series via FRED.", _fred("BAMLC0A0CM")),
        Candidate(2, "get_hy_quality_spread_bp", "FRED / ICE BofA composite", "CCC and lower minus BB OAS", "Observation-date only; composite formula local.", "obb.economy.fred_series('BAMLH0A3HYC','BAMLH0A1HYBB')", "fred", "candidate_partial", "good_with_vintage_caveat", "OpenBB supplies raw legs; vNext keeps quality-spread formula.", _fred_many(["BAMLH0A3HYC", "BAMLH0A1HYBB"])),
        Candidate(2, "get_hyg_momentum", "yfinance HYG price", "HYG credit ETF momentum", "Daily price can be date-filtered.", "obb.equity.price.historical('HYG')", "yfinance", "candidate_direct", "good_for_observation_date", "Polygon can be added when entitlement is present.", _equity_price("HYG", "yfinance")),
        Candidate(2, "get_xly_xlp_ratio", "yfinance pair formula", "Cyclical vs defensive sector ratio", "Daily price can be date-filtered; formula local.", "obb.equity.price.historical('XLY'/'XLP')", "yfinance", "candidate_partial", "good_for_observation_date", "OpenBB supplies legs; vNext keeps ratio semantics.", _equity_price("XLY", "yfinance")),
        Candidate(2, "get_crowdedness_dashboard", "yfinance SKEW plus current options proxy", "Crowding, skew and options positioning", "Options chain is current-only unless provider has historical chain entitlement.", "obb.derivatives.options.chains('QQQ')", "cboe", "cross_check_only", "not_backtest_safe_current_chain", "Useful live cross-check; not historical evidence by default.", _options_chains("QQQ")),
        Candidate(2, "get_cnn_fear_greed_index", "CNN endpoint", "Retail sentiment dashboard", "Historical endpoint availability is inconsistent.", "No obvious OpenBB command", "none", "not_covered", "external_only", "Keep current isolated source or replace with different sentiment series.", None),
        Candidate(3, "get_advance_decline_line", "yfinance NDX components", "Breadth: advancers minus decliners", "Needs point-in-time universe; current components cannot masquerade as history.", "obb.equity.price.historical(component basket)", "polygon/yfinance", "candidate_partial", "requires_pit_universe", "OpenBB helps prices, not historical NDX membership.", _equity_price("AAPL", "yfinance")),
        Candidate(3, "get_percent_above_ma", "yfinance NDX components", "Share of members above moving averages", "Needs point-in-time universe.", "obb.equity.price.historical(component basket)", "polygon/yfinance", "candidate_partial", "requires_pit_universe", "OpenBB can be a price engine under vNext universe rules.", _equity_price("MSFT", "yfinance")),
        Candidate(3, "get_ndx_ndxe_ratio", "yfinance ^NDX/^NDXE", "Cap-weight vs equal-weight leadership", "Daily index close can be date-filtered; formula local.", "obb.index.price.historical('^NDX','^NDXE')", "yfinance", "candidate_partial", "good_for_observation_date", "OpenBB may supply index legs when provider support exists; vNext keeps ratio semantics.", _equity_price("^NDXE", "yfinance")),
        Candidate(3, "get_qqq_top10_concentration", "Invesco latest holdings", "Top-10 concentration in QQQ", "Current holdings are not backtest-safe.", "obb.etf.holdings('QQQ')", "fmp", "cross_check_only", "not_backtest_safe_without_history", "May need subscription and historical holdings entitlement.", _etf_holdings("QQQ", "fmp")),
        Candidate(3, "get_qqq_top10_concentration", "Invesco latest holdings", "Top-10 concentration in QQQ", "Current holdings are not backtest-safe.", "obb.etf.holdings('QQQ')", "tmx", "cross_check_only", "not_backtest_safe_without_history", "Can test free endpoint; prior probes may return empty for US ETF.", _etf_holdings("QQQ", "tmx")),
        Candidate(3, "get_m7_fundamentals", "yfinance info plus Alpha Vantage fallback", "M7 quality/fundamental proxy", "Latest-only fundamentals are skipped in backtests.", "obb.equity.fundamental.metrics('AAPL')", "finviz", "cross_check_only", "latest_only", "Good live sanity check; not first-reported safe.", _equity_metrics("AAPL", "finviz")),
        Candidate(3, "get_new_highs_lows", "yfinance NDX components", "Internal new highs/new lows", "Needs point-in-time universe.", "obb.equity.price.historical(component basket)", "polygon/yfinance", "candidate_partial", "requires_pit_universe", "OpenBB helps price collection only.", _equity_price("NVDA", "yfinance")),
        Candidate(3, "get_mcclellan_oscillator_nasdaq_or_nyse", "yfinance component breadth proxy", "Breadth momentum oscillator", "Needs point-in-time universe and exchange breadth definition.", "obb.equity.price.historical(component basket)", "polygon/yfinance", "candidate_partial", "requires_pit_universe", "OpenBB does not solve exchange-wide breadth semantics by itself.", _equity_price("QQQ", "yfinance")),
        Candidate(4, "get_ndx_pe_and_earnings_yield", "yfinance component model plus manual/web checks", "NDX valuation and earnings yield", "Latest component fundamentals skipped in strict backtests.", "obb.equity.fundamental.metrics('AAPL')", "fmp", "cross_check_only", "latest_or_subscription_dependent", "Provider can standardize fields, but aggregate NDX semantics remain local.", _equity_metrics("AAPL", "fmp")),
        Candidate(4, "get_ndx_pe_and_earnings_yield", "component model", "First-reported fundamentals for valuation audit", "Needs filing/report availability date.", "obb.equity.compare.company_facts('AAPL','Revenues')", "sec", "candidate_partial", "better_for_first_reported_audit", "SEC facts include reported dates and can harden future L4 history.", _sec_company_fact("AAPL", "Revenues")),
        Candidate(4, "get_ndx_forward_earnings_quality", "yfinance EPS trend", "Forward earnings estimates and revisions", "Latest-only estimates skipped in strict backtests.", "obb.equity.estimates.consensus('AAPL')", "fmp", "cross_check_only", "latest_or_subscription_dependent", "Useful live source; historical estimate vintages still need proof.", _analyst_consensus("AAPL")),
        Candidate(4, "get_equity_risk_premium", "NDX earnings yield minus Treasury plus Damodaran context", "Simplified equity risk premium", "Depends on valuation path; skipped when component valuation not safe.", "OpenBB FRED rates plus SEC/FMP fundamentals", "mixed", "candidate_partial", "depends_on_l4_visibility", "OpenBB can supply ingredients, not the audit-safe ERP claim.", _fred("DGS10")),
        Candidate(4, "get_damodaran_us_implied_erp", "Damodaran spreadsheet/web cache", "US implied ERP anchor", "Monthly publication and target-date filtering local.", "No OpenBB provider found", "none", "not_covered", "external_only", "Keep Damodaran path; OpenBB does not replace it.", None),
        Candidate(5, "get_qqq_technical_indicators", "yfinance OHLCV plus ta/internal formulas", "Composite QQQ technical state", "Daily price can be date-filtered; formula parity must be tested.", "obb.equity.price.historical('QQQ') + obb.technical.*", "yfinance", "candidate_direct", "good_for_observation_date", "Strong candidate for formula-engine comparison.", _qqq_technical("rsi")),
        Candidate(5, "get_rsi_qqq", "ta/internal formula", "RSI(14)", "Formula parity required.", "obb.technical.rsi", "openbb_technical", "candidate_direct", "good_for_observation_date", "Direct formula candidate.", _qqq_technical("rsi")),
        Candidate(5, "get_atr_qqq", "ta/internal formula", "ATR(14)", "Formula parity required.", "obb.technical.atr", "openbb_technical", "candidate_direct", "good_for_observation_date", "Direct formula candidate.", _qqq_technical("atr")),
        Candidate(5, "get_adx_qqq", "ta/internal formula", "ADX(14)", "Formula parity required.", "obb.technical.adx", "openbb_technical", "candidate_direct", "good_for_observation_date", "Direct formula candidate.", _qqq_technical("adx")),
        Candidate(5, "get_macd_qqq", "ta/internal formula", "MACD", "Formula parity required.", "obb.technical.macd", "openbb_technical", "candidate_direct", "good_for_observation_date", "Direct formula candidate.", _qqq_technical("macd")),
        Candidate(5, "get_obv_qqq", "ta/internal formula", "On-balance volume", "Formula parity required.", "obb.technical.obv", "openbb_technical", "candidate_direct", "good_for_observation_date", "Direct formula candidate.", _qqq_technical("obv")),
        Candidate(5, "get_volume_analysis_qqq", "yfinance volume formulas", "Volume trend and confirmation", "Formula semantics local.", "obb.equity.price.historical('QQQ')", "yfinance", "candidate_partial", "good_for_observation_date", "OpenBB supplies OHLCV; vNext keeps interpretation.", _equity_price("QQQ", "yfinance")),
        Candidate(5, "get_price_volume_quality_qqq", "VWAP/MFI/CMF formulas", "Price-volume quality", "Formula parity required.", "obb.technical.vwap", "openbb_technical", "candidate_direct", "good_for_observation_date", "Direct formula candidate for VWAP; MFI/CMF need separate mapping.", _qqq_technical("vwap")),
        Candidate(5, "get_donchian_channels_qqq", "ta/internal formula", "Donchian breakout channel", "Formula parity required.", "obb.technical.donchian", "openbb_technical", "candidate_direct", "good_for_observation_date", "Direct formula candidate.", _qqq_technical("donchian")),
        Candidate(5, "get_multi_scale_ma_position", "yfinance SMA formulas", "Multi-scale moving-average position", "Formula parity required.", "obb.technical.sma", "openbb_technical", "candidate_direct", "good_for_observation_date", "Direct formula candidate for SMA legs.", _qqq_technical("sma")),
    ]


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def _status_counts(rows: List[Dict[str, Any]], field: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _write_markdown(path: Path, payload: Dict[str, Any]) -> None:
    rows = payload["rows"]
    meta = payload["meta"]
    lines = [
        "# OpenBB vNext Coverage Probe",
        "",
        f"- Generated at: `{meta['generated_at']}`",
        f"- Effective date: `{meta['effective_date']}`",
        f"- Probe window: `{meta['start_date']}` to `{meta['end_date']}`",
        f"- OpenBB version: `{meta.get('openbb_version')}`",
        f"- Providers installed: `{meta.get('provider_count')}`",
        "",
        "## Summary",
        "",
        f"- Probe status: `{_status_counts(rows, 'status')}`",
        f"- Replacement rating: `{_status_counts(rows, 'replacement_rating')}`",
        f"- Backtest fit: `{_status_counts(rows, 'backtest_fit')}`",
        "",
        "## Coverage Matrix",
        "",
        "| Layer | function_id | Provider | Status | Rating | Backtest fit | Rows | Latest | Notes |",
        "| --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        notes = str(row.get("notes") or "").replace("|", "\\|")
        error = row.get("error")
        if error:
            notes = (notes + " Error: " + str(error)).replace("|", "\\|")
        lines.append(
            "| {layer} | `{function_id}` | {provider} | {status} | {rating} | {backtest_fit} | {rows} | {latest} | {notes} |".format(
                layer=row.get("layer"),
                function_id=row.get("function_id"),
                provider=row.get("provider"),
                status=row.get("status"),
                rating=row.get("replacement_rating"),
                backtest_fit=row.get("backtest_fit"),
                rows=row.get("row_count"),
                latest=row.get("latest_date") or "",
                notes=notes[:260],
            )
        )
    lines.extend(
        [
            "",
            "## Reading Rule",
            "",
            "A row marked `candidate_direct` still means only that OpenBB can supply the data or formula candidate. It does not mean the source is promoted into L1-L5 evidence. Promotion still requires vNext date visibility, unit semantics, quality notes, and DataIntegrity checks.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _credentials(obb: Any) -> CredentialMap:
    out: CredentialMap = {}
    creds = getattr(getattr(obb, "user", None), "credentials", None)
    if not creds:
        return out
    for name in dir(creds):
        if name.startswith("_"):
            continue
        if name in OPENBB_CREDENTIAL_FIELDS:
            try:
                out[name] = bool(getattr(creds, name))
            except Exception:
                out[name] = False
    return dict(sorted(out.items()))


def run(args: argparse.Namespace) -> Dict[str, Any]:
    _load_dotenv()
    from openbb import obb

    effective = date.fromisoformat(args.effective_date)
    start = effective - timedelta(days=args.lookback_days)
    candidates = _coverage_candidates()
    rows = [_run_probe(obb, candidate, start.isoformat(), effective.isoformat()) for candidate in candidates]

    providers = sorted(list(obb.coverage.providers))
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "effective_date": effective.isoformat(),
            "start_date": start.isoformat(),
            "end_date": effective.isoformat(),
            "lookback_days": args.lookback_days,
            "openbb_version": _safe_version("openbb"),
            "openbb_core_version": _safe_version("openbb-core"),
            "provider_count": len(providers),
            "providers": providers,
            "credentials_present": _credentials(obb),
            "production_integration": "none",
        },
        "rows": rows,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "openbb_vnext_coverage_matrix.json", payload)
    _write_csv(output_dir / "openbb_vnext_coverage_matrix.csv", rows)
    _write_markdown(output_dir / "openbb_vnext_coverage_report.md", payload)
    return payload


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe OpenBB coverage for vNext L1-L5 data functions.")
    parser.add_argument("--effective-date", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    payload = run(args)
    rows = payload["rows"]
    print(
        "OpenBB coverage probe complete: "
        f"{len(rows)} rows, status={_status_counts(rows, 'status')}, "
        f"rating={_status_counts(rows, 'replacement_rating')}"
    )
    print(f"Artifacts: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
