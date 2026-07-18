"""Supporting-only expectation-versus-realized ledger (W4).

This module is audit/comprehensive-layer material.  It never writes L1-L5
evidence refs and only uses observations visible on or before effective_date.
"""
from __future__ import annotations

import calendar
import json
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VINTAGE_ROOT = REPO_ROOT / "output" / "vintage_archive"
DEFAULT_ANALYSIS_ROOT = REPO_ROOT / "output" / "analysis" / "vnext"
DOWNGRADE_RULES = [
    "supporting_only_not_core_evidence",
    "must_not_enter_l1_l5_raw_prompt_or_evidence_ref",
    "historical_comparisons_require_observation_date_lte_effective_date",
    "coverage_shortfalls_must_remain_explicit",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def _parse_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _forward_eps(snapshot: Dict[str, Any]) -> Dict[str, float]:
    values: Dict[str, float] = {}
    per_ticker = snapshot.get("per_ticker") if isinstance(snapshot.get("per_ticker"), dict) else {}
    for ticker, payload in per_ticker.items():
        yf_payload = payload.get("yfinance") if isinstance(payload, dict) and isinstance(payload.get("yfinance"), dict) else {}
        fields = yf_payload.get("fields") if isinstance(yf_payload.get("fields"), dict) else {}
        eps_trend = fields.get("eps_trend") if isinstance(fields.get("eps_trend"), dict) else {}
        for row in eps_trend.get("records") if isinstance(eps_trend.get("records"), list) else []:
            if not isinstance(row, dict) or str(row.get("period")) != "+1y":
                continue
            current = _safe_float(row.get("current"))
            if current is not None and current > 0:
                values[str(ticker).upper()] = current
            break
    return values


def _vintage_snapshots(vintage_root: Path, effective_date: date) -> List[tuple[date, Dict[str, Any]]]:
    snapshots = []
    if not vintage_root.is_dir():
        return snapshots
    for path in sorted(vintage_root.glob("*/eps_consensus.json")):
        payload = _read_json(path)
        snapshot_date = _parse_date(payload.get("archive_date") or path.parent.name)
        if snapshot_date and snapshot_date <= effective_date:
            snapshots.append((snapshot_date, payload))
    return snapshots


def _earnings_book(vintage_root: Path, effective_date: date) -> Dict[str, Any]:
    snapshots = _vintage_snapshots(vintage_root, effective_date)
    if not snapshots:
        return {
            "status": "insufficient_coverage",
            "current_snapshot_date": None,
            "windows": [],
            "note": "没有 effective_date 及以前的自建 EPS vintage 快照。",
        }
    current_date, current_snapshot = snapshots[-1]
    current_values = _forward_eps(current_snapshot)
    windows = []
    for days in (30, 90):
        target = current_date - timedelta(days=days)
        eligible = [(d, payload) for d, payload in snapshots if d <= target]
        if not eligible:
            available_days = (current_date - snapshots[0][0]).days
            windows.append({
                "window_days": days,
                "status": "insufficient_coverage",
                "target_date": target.isoformat(),
                "prior_snapshot_date": None,
                "available_days": available_days,
                "shortfall_days": max(0, days - available_days),
                "ticker_changes": [],
                "note": "自建跨日 vintage 尚未积累到目标窗口；未使用供应商回看字段替代。",
            })
            continue
        prior_date, prior_snapshot = eligible[-1]
        prior_values = _forward_eps(prior_snapshot)
        common = sorted(set(current_values) & set(prior_values))
        rows = []
        elapsed_days = max(1, (current_date - prior_date).days)
        for ticker in common:
            previous, current = prior_values[ticker], current_values[ticker]
            if previous <= 0:
                continue
            change_pct = (current / previous - 1.0) * 100.0
            rows.append({
                "ticker": ticker,
                "prior_forward_eps": round(previous, 6),
                "current_forward_eps": round(current, 6),
                "change_pct": round(change_pct, 6),
                "slope_pct_per_30d": round(change_pct * 30.0 / elapsed_days, 6),
                "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
            })
        windows.append({
            "window_days": days,
            "status": "available" if rows else "insufficient_coverage",
            "target_date": target.isoformat(),
            "prior_snapshot_date": prior_date.isoformat(),
            "actual_elapsed_days": elapsed_days,
            "intersection_ticker_count": len(rows),
            "ticker_changes": rows,
            "average_change_pct": round(statistics.fmean(row["change_pct"] for row in rows), 6) if rows else None,
            "note": "仅比较两个 PIT 快照的 +1y current；不使用 eps_trend.30daysAgo/90daysAgo。",
        })
    return {
        "status": "available" if any(item["status"] == "available" for item in windows) else "insufficient_coverage",
        "current_snapshot_date": current_date.isoformat(),
        "current_ticker_count": len(current_values),
        "windows": windows,
        "source_boundary": "isolated vintage observation; third_party_unofficial; supporting_only",
    }


def _fed_path(packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = packet.get("raw_data") if isinstance(packet.get("raw_data"), dict) else {}
    l1 = raw.get("L1") if isinstance(raw.get("L1"), dict) else {}
    indicator = l1.get("get_fed_funds_rate_path") if isinstance(l1.get("get_fed_funds_rate_path"), dict) else {}
    value = indicator.get("value") if isinstance(indicator.get("value"), dict) else None
    if not value:
        return None
    return {
        "effective_date": value.get("effective_date"),
        "status": value.get("status"),
        "path": [dict(item) for item in value.get("path", []) if isinstance(item, dict)],
        "state": value.get("state"),
        "effr_anchor": value.get("effr_anchor"),
    }


def _historical_rate_inputs(
    analysis_root: Path,
    effective_date: date,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    paths: List[Dict[str, Any]] = []
    actuals: List[Dict[str, Any]] = []
    audit: Dict[str, Any] = {
        "runs_scanned": 0,
        "qualified_runs": 0,
        "rejected_runs": 0,
        "no_candidate_runs": 0,
        "rejection_counts": {},
        "path_candidates_accepted": 0,
        "actual_observations_accepted": 0,
    }
    if not analysis_root.is_dir():
        return paths, actuals, audit

    def reject(reason: str) -> None:
        counts = audit["rejection_counts"]
        counts[reason] = counts.get(reason, 0) + 1

    for run_dir in sorted(path for path in analysis_root.iterdir() if path.is_dir()):
        audit["runs_scanned"] += 1
        integrity = _read_json(run_dir / "data_integrity_report.json")
        if not integrity:
            audit["rejected_runs"] += 1
            reject("missing_data_integrity_report")
            continue
        if (
            integrity.get("blocked")
            or integrity.get("unpublishable")
            or str(integrity.get("publish_status") or "") != "publishable"
        ):
            audit["rejected_runs"] += 1
            reject("data_integrity_not_publishable")
            continue

        packet = _read_json(run_dir / "analysis_packet.json")
        packet_meta = packet.get("meta") if isinstance(packet.get("meta"), dict) else {}
        packet_date = _parse_date(
            packet_meta.get("data_date")
            or packet_meta.get("backtest_date")
            or packet_meta.get("effective_date")
        )
        if not packet or packet_date is None or packet_date > effective_date:
            audit["rejected_runs"] += 1
            reject("packet_date_missing_or_future")
            continue

        accepted_from_run = False
        candidate_seen = False
        stored = _read_json(run_dir / "expectation_vs_realized.json")
        stored_current = (stored.get("rate_path") or {}).get("current_path") if isinstance(stored.get("rate_path"), dict) else None
        if isinstance(stored_current, dict):
            candidate_seen = True
            stored_date = _parse_date(stored.get("effective_date"))
            stored_path_date = _parse_date(stored_current.get("effective_date"))
            if stored_date == packet_date == stored_path_date:
                paths.append(stored_current)
                audit["path_candidates_accepted"] += 1
                accepted_from_run = True
            else:
                reject("stored_ledger_packet_path_date_mismatch")

        path = _fed_path(packet)
        if path:
            candidate_seen = True
            path_date = _parse_date(path.get("effective_date"))
            if path_date == packet_date:
                paths.append(path)
                audit["path_candidates_accepted"] += 1
                accepted_from_run = True
                anchor = path.get("effr_anchor") if isinstance(path.get("effr_anchor"), dict) else {}
                anchor_date = _parse_date(anchor.get("data_date"))
                anchor_rate = _safe_float(anchor.get("rate"))
                anchor_series = str(anchor.get("series_id") or "")
                if (
                    anchor_series in {"EFFR", "DFF"}
                    and anchor_date
                    and anchor_date <= packet_date
                    and anchor_rate is not None
                ):
                    actuals.append({
                        "date": anchor_date.isoformat(),
                        "available_date": packet_date.isoformat(),
                        "rate": anchor_rate,
                        "series_id": anchor_series,
                        "source": "qualified_run_effr_anchor",
                    })
                    audit["actual_observations_accepted"] += 1
            else:
                reject("packet_path_date_mismatch")
        if accepted_from_run:
            audit["qualified_runs"] += 1
        elif candidate_seen:
            audit["rejected_runs"] += 1
        else:
            audit["no_candidate_runs"] += 1
    unique_paths = {str(item.get("effective_date")): item for item in paths if _parse_date(item.get("effective_date"))}
    unique_actuals = {(str(item.get("series_id")), str(item.get("date"))): item for item in actuals}
    return list(unique_paths.values()), list(unique_actuals.values()), audit


def _next_business_day(value: date) -> date:
    try:
        import pandas as pd
        from pandas.tseries.holiday import USFederalHolidayCalendar
        from pandas.tseries.offsets import CustomBusinessDay

        return (pd.Timestamp(value) + CustomBusinessDay(calendar=USFederalHolidayCalendar())).date()
    except Exception:
        # If the holiday calendar is unavailable, prefer a conservative delay
        # to treating an unreleased same-day observation as historical fact.
        return value + timedelta(days=4)


def _expected_rate_observation_dates(year: int, month: int, series_id: str) -> List[date]:
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    if series_id == "DFF":
        return [date(year, month, day) for day in range(1, month_end.day + 1)]
    try:
        import pandas as pd
        from pandas.tseries.holiday import USFederalHolidayCalendar
        from pandas.tseries.offsets import CustomBusinessDay

        values = pd.date_range(
            start=date(year, month, 1),
            end=month_end,
            freq=CustomBusinessDay(calendar=USFederalHolidayCalendar()),
        )
        return [item.date() for item in values]
    except Exception:
        return [date(year, month, day) for day in range(1, month_end.day + 1) if date(year, month, day).weekday() < 5]


def _fetch_fred_actual_rate_series(effective_date: date) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    audit: Dict[str, Any] = {
        "source": "FRED EFFR/DFF",
        "status": "unavailable",
        "series_id": None,
        "observation_count": 0,
        "attempt_errors": [],
    }
    try:
        try:
            from .tools_common import get_fred_series
        except ImportError:
            from tools_common import get_fred_series
        for series_id in ("EFFR", "DFF"):
            try:
                frame = get_fred_series(series_id, days=5475, end_date=effective_date.isoformat())
            except Exception as exc:
                audit["attempt_errors"].append(f"{series_id}:{type(exc).__name__}:{str(exc)[:120]}")
                continue
            if frame is None or frame.empty or not {"date", "value"}.issubset(frame.columns):
                continue
            rows = []
            for _, row in frame.iterrows():
                observation_date = _parse_date(row.get("date"))
                rate = _safe_float(row.get("value"))
                if observation_date is None or rate is None:
                    continue
                available_date = _next_business_day(observation_date)
                if available_date > effective_date:
                    continue
                rows.append({
                    "date": observation_date.isoformat(),
                    "available_date": available_date.isoformat(),
                    "rate": rate,
                    "series_id": series_id,
                    "source": "FRED",
                })
            if rows:
                audit.update({"status": "available", "series_id": series_id, "observation_count": len(rows)})
                return rows, audit
    except Exception as exc:
        audit["attempt_errors"].append(f"loader:{type(exc).__name__}:{str(exc)[:200]}")
    return [], audit


def _rate_book(
    current_packet: Dict[str, Any],
    effective_date: date,
    historical_paths: Iterable[Dict[str, Any]],
    actual_rate_series: Iterable[Dict[str, Any]],
    historical_input_audit: Optional[Dict[str, Any]] = None,
    fred_actuals_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    current_path = _fed_path(current_packet)
    current_path_date = _parse_date(current_path.get("effective_date")) if current_path else None
    if current_path is None:
        current_path_status = "missing"
    elif current_path_date is None:
        current_path = None
        current_path_status = "rejected_missing_effective_date"
    elif current_path_date > effective_date:
        current_path = None
        current_path_status = "rejected_future_effective_date"
    else:
        current_path_status = "available" if current_path_date == effective_date else "available_stale"
    cutoff = effective_date - timedelta(days=30)
    eligible = [item for item in historical_paths if (_parse_date(item.get("effective_date")) or date.max) <= cutoff]
    actuals = []
    for item in actual_rate_series:
        obs_date = _parse_date(item.get("date"))
        available_date = _parse_date(item.get("available_date")) or obs_date
        rate = _safe_float(item.get("rate") if "rate" in item else item.get("value"))
        if obs_date and available_date and available_date <= effective_date and obs_date <= effective_date and rate is not None:
            actuals.append((obs_date, rate, str(item.get("series_id") or "EFFR/DFF")))
    comparisons = []
    incomplete_months = []
    for historical in sorted(eligible, key=lambda item: str(item.get("effective_date"))):
        historical_date = _parse_date(historical.get("effective_date"))
        if not historical_date:
            continue
        for point in historical.get("path") if isinstance(historical.get("path"), list) else []:
            if not isinstance(point, dict):
                continue
            months_ahead = int(point.get("months_ahead") or 0)
            month_index = historical_date.year * 12 + historical_date.month - 1 + months_ahead
            year, month0 = divmod(month_index, 12)
            month = month0 + 1
            month_end = date(year, month, calendar.monthrange(year, month)[1])
            if month_end > effective_date:
                continue
            priced = _safe_float(point.get("implied_rate"))
            if priced is None:
                continue
            selected_series = None
            selected_values: List[float] = []
            missing_by_series: Dict[str, Any] = {}
            for series_id in ("EFFR", "DFF"):
                observed = {
                    obs_date: rate
                    for obs_date, rate, actual_series in actuals
                    if actual_series == series_id and obs_date.year == year and obs_date.month == month
                }
                expected_dates = _expected_rate_observation_dates(year, month, series_id)
                final_visible_date = _next_business_day(expected_dates[-1]) if expected_dates else month_end
                missing_dates = [item for item in expected_dates if item not in observed]
                if effective_date < final_visible_date:
                    missing_by_series[series_id] = {
                        "reason": "final_observation_not_yet_visible",
                        "final_visible_date": final_visible_date.isoformat(),
                    }
                    continue
                if missing_dates:
                    missing_by_series[series_id] = {
                        "reason": "incomplete_month_observations",
                        "expected_count": len(expected_dates),
                        "observed_count": len(expected_dates) - len(missing_dates),
                        "missing_dates_sample": [item.isoformat() for item in missing_dates[:5]],
                    }
                    continue
                selected_series = series_id
                selected_values = [observed[item] for item in expected_dates]
                break
            if selected_series is None:
                incomplete_months.append({
                    "historical_effective_date": historical_date.isoformat(),
                    "contract_month": f"{year:04d}-{month:02d}",
                    "status": "not_realized_yet_or_incomplete",
                    "series_checks": missing_by_series,
                })
                continue
            realized = statistics.fmean(selected_values)
            comparisons.append({
                "historical_effective_date": historical_date.isoformat(),
                "contract_month": f"{year:04d}-{month:02d}",
                "months_ahead_at_pricing": months_ahead,
                "priced_rate": round(priced, 6),
                "realized_rate": round(realized, 6),
                "priced_minus_realized_pp": round(priced - realized, 6),
                "actual_observation_count": len(selected_values),
                "actual_series_ids": [selected_series],
            })
    return {
        "status": "available" if comparisons else "accumulating",
        "current_path": current_path,
        "current_path_status": current_path_status,
        "historical_path_count_eligible": len(eligible),
        "comparisons": comparisons,
        "incomplete_months": incomplete_months,
        "note": "已形成历史定价与实际兑现对照。" if comparisons else "对照样本积累中",
        "source_boundary": "Fed funds futures pricing is supporting_only; realized rates require dated FRED EFFR/DFF observations.",
        "historical_input_audit": historical_input_audit or {},
        "fred_actuals_audit": fred_actuals_audit or {},
    }


def _empirical_percentile(values: List[float], current: float) -> float:
    below = sum(1 for value in values if value < current)
    equal = sum(1 for value in values if value == current)
    return round(100.0 * (below + 0.5 * equal) / len(values), 2)


def _volatility_book(chart: Dict[str, Any], effective_date: date) -> Dict[str, Any]:
    series = chart.get("series") if isinstance(chart.get("series"), dict) else {}
    qqq = series.get("QQQ_OHLCV") if isinstance(series.get("QQQ_OHLCV"), dict) else {}
    vix = series.get("VIX") if isinstance(series.get("VIX"), dict) else {}
    closes = []
    for row in qqq.get("rows") if isinstance(qqq.get("rows"), list) else []:
        row_date, close = _parse_date(row.get("time") if isinstance(row, dict) else None), _safe_float(row.get("close") if isinstance(row, dict) else None)
        if row_date and row_date <= effective_date and close and close > 0:
            closes.append((row_date, close))
    vix_by_date = {}
    for row in vix.get("rows") if isinstance(vix.get("rows"), list) else []:
        row_date, value = _parse_date(row.get("time") if isinstance(row, dict) else None), _safe_float(row.get("value") if isinstance(row, dict) else None)
        if row_date and row_date <= effective_date and value is not None:
            vix_by_date[row_date] = value
    closes.sort()
    premiums = []
    for start_index in range(0, max(0, len(closes) - 21)):
        window = closes[start_index:start_index + 22]
        start_date = window[0][0]
        if len(window) < 22 or start_date not in vix_by_date:
            continue
        returns = [math.log(window[index][1] / window[index - 1][1]) for index in range(1, len(window))]
        if len(returns) < 2:
            continue
        realized_pct = statistics.stdev(returns) * math.sqrt(252.0) * 100.0
        implied_pct = vix_by_date[start_date]
        premiums.append({
            "start_date": start_date.isoformat(),
            "end_date": window[-1][0].isoformat(),
            "vix_implied_vol_pct": round(implied_pct, 6),
            "realized_vol_pct": round(realized_pct, 6),
            "premium_pct_points": round(implied_pct - realized_pct, 6),
        })
    values = [item["premium_pct_points"] for item in premiums]
    enough = len(values) >= 20
    return {
        "status": "available" if enough else "insufficient_coverage",
        "window_trading_days": 21,
        "sample_count": len(values),
        "premium_series": premiums,
        "recent_premium_pct_points": values[-1] if values else None,
        "recent_percentile": _empirical_percentile(values, values[-1]) if enough else None,
        "note": "VIX at window start minus following 21-trading-day realized QQQ volatility."
        if enough else "有效窗口少于 20 个，不输出近期分位。",
    }


def build_expectation_ledger(
    *,
    effective_date: str,
    vintage_root: str | Path = DEFAULT_VINTAGE_ROOT,
    analysis_root: str | Path = DEFAULT_ANALYSIS_ROOT,
    current_analysis_packet: Optional[Dict[str, Any]] = None,
    chart_time_series: Optional[Dict[str, Any]] = None,
    historical_paths: Optional[List[Dict[str, Any]]] = None,
    actual_rate_series: Optional[List[Dict[str, Any]]] = None,
    historical_input_audit: Optional[Dict[str, Any]] = None,
    fred_actuals_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    as_of = _parse_date(effective_date)
    if not as_of:
        raise ValueError(f"invalid effective_date: {effective_date}")
    packet = current_analysis_packet or {}
    chart = chart_time_series or {}
    if historical_paths is None or actual_rate_series is None:
        discovered_paths, discovered_actuals, discovered_audit = _historical_rate_inputs(Path(analysis_root), as_of)
        historical_paths = discovered_paths if historical_paths is None else historical_paths
        actual_rate_series = discovered_actuals if actual_rate_series is None else actual_rate_series
        historical_input_audit = discovered_audit if historical_input_audit is None else historical_input_audit
    return {
        "schema_version": "expectation_vs_realized_v1",
        "generated_at_utc": _utc_now_iso(),
        "effective_date": as_of.isoformat(),
        "metric_authority": "supporting_only",
        "downgrade_rules": list(DOWNGRADE_RULES),
        "earnings_expectations": _earnings_book(Path(vintage_root), as_of),
        "rate_path": _rate_book(
            packet,
            as_of,
            historical_paths or [],
            actual_rate_series or [],
            historical_input_audit=historical_input_audit,
            fred_actuals_audit=fred_actuals_audit,
        ),
        "volatility_premium": _volatility_book(chart, as_of),
        "evidence_boundary": "Audit/comprehensive-layer artifact only; never an L1-L5 evidence_ref.",
    }


def write_expectation_ledger(
    run_dir: str | Path,
    *,
    effective_date: str,
    vintage_root: str | Path = DEFAULT_VINTAGE_ROOT,
    analysis_root: str | Path = DEFAULT_ANALYSIS_ROOT,
) -> str:
    run_path = Path(run_dir)
    as_of = _parse_date(effective_date)
    if as_of is None:
        raise ValueError(f"invalid effective_date: {effective_date}")
    historical_paths, discovered_actuals, historical_audit = _historical_rate_inputs(Path(analysis_root), as_of)
    fred_actuals, fred_audit = _fetch_fred_actual_rate_series(as_of)
    payload = build_expectation_ledger(
        effective_date=effective_date,
        vintage_root=vintage_root,
        analysis_root=analysis_root,
        current_analysis_packet=_read_json(run_path / "analysis_packet.json"),
        chart_time_series=_read_json(run_path / "chart_time_series.json"),
        historical_paths=historical_paths,
        actual_rate_series=fred_actuals or discovered_actuals,
        historical_input_audit=historical_audit,
        fred_actuals_audit=fred_audit,
    )
    return _write_json(run_path / "expectation_vs_realized.json", payload)


def write_expectation_ledger_failure(run_dir: str | Path, *, effective_date: str, error: Exception) -> str:
    payload = {
        "schema_version": "expectation_vs_realized_v1",
        "generated_at_utc": _utc_now_iso(),
        "effective_date": effective_date,
        "metric_authority": "supporting_only",
        "downgrade_rules": list(DOWNGRADE_RULES),
        "status": "generation_failed_non_blocking",
        "notes": [f"expectation_ledger_generation_failed:{type(error).__name__}:{str(error)[:300]}"],
        "earnings_expectations": {"status": "unavailable"},
        "rate_path": {"status": "unavailable"},
        "volatility_premium": {"status": "unavailable"},
        "evidence_boundary": "Audit/comprehensive-layer artifact only; never an L1-L5 evidence_ref.",
    }
    return _write_json(Path(run_dir) / "expectation_vs_realized.json", payload)
