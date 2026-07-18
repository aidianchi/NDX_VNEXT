#!/usr/bin/env python3
"""Audit candidate analog-variable histories without building an analog engine.

This module is intentionally standalone.  It measures history coverage, lineage
breaks, and a mechanical upper bound on independent directional clusters.  It
must not calculate forward returns, win rates, conditional distributions, or
emit a trading/analogy signal.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "investigation_reports" / "20260718_first_principles_debate"
MIN_INDEPENDENT_GAP_TRADING_DAYS = 63


SOURCE_POLICIES: Dict[str, Dict[str, Any]] = {
    "dfii10": {
        "label": "10Y real rate (DFII10)",
        "source_id": "FRED_DFII10",
        "source_name": "Federal Reserve Bank of St. Louis (FRED)",
        "source_tier": "official_relay",
        "frequency": "daily_business_day",
        "known_revision_risks": [
            "No ALFRED vintage was collected, so historical publication vintages are not proven point-in-time.",
            "Source corrections, holiday gaps, and metadata changes may alter the downloaded history.",
        ],
    },
    "hy_oas": {
        "label": "ICE BofA US High Yield OAS (BAMLH0A0HYM2)",
        "source_id": "FRED_BAMLH0A0HYM2",
        "source_name": "ICE BofA via FRED",
        "source_tier": "official_relay",
        "frequency": "daily_business_day",
        "known_revision_risks": [
            "No ALFRED vintage was collected, so historical publication vintages are not proven point-in-time.",
            "Provider methodology, bond-universe composition, corrections, or backfills can change history.",
            "Starting in April 2026, FRED only exposes three years of this copyrighted ICE series; the accessible start is not the original series inception.",
        ],
        "coverage_limit": (
            "Current FRED relay coverage is limited to three years starting in April 2026. "
            "The measured rows are the currently accessible window, not the complete history; older data requires the licensed source and a retained PIT archive."
        ),
        "coverage_limit_source": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
    },
    "vix": {
        "label": "CBOE Volatility Index (^VIX)",
        "source_id": "YFINANCE_VIX",
        "source_name": "Yahoo Finance relay for Cboe VIX",
        "source_tier": "third_party_relay",
        "frequency": "trading_day",
        "known_revision_risks": [
            "Market closes are normally final, but the third-party relay can correct, omit, or remap observations.",
            "This audit does not use an official Cboe historical archive and does not retain vendor vintages.",
        ],
    },
    "ndx_valuation_percentile": {
        "label": "NDX valuation percentile lineage (Wind / History of Market)",
        "source_id": "NDX_VALUATION_MIXED_LINEAGE",
        "source_name": "Wind snapshots and History of Market histories",
        "source_tier": "mixed_non_stitchable",
        "frequency": "mixed",
        "known_revision_risks": [
            "Wind is archived by this project as current/recent snapshots, not as a complete historical point-in-time series.",
            "History of Market is a third-party API with no retained publication vintages; its Bloomberg BEst attribution is not independently verified.",
            "Trailing PE is daily while forward PE is monthly, and neither History of Market series is the same field or methodology as Wind's percentile snapshot.",
            "Index composition and valuation methodology can change through time.",
        ],
    },
}


def _iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return parsed.date().isoformat()


def normalize_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    default_source_id: str,
) -> List[Dict[str, Any]]:
    """Return sorted, finite, dated rows; duplicate dates retain the last row."""
    by_date: Dict[str, Dict[str, Any]] = {}
    for raw in rows:
        observed_date = _iso_date(raw.get("date"))
        try:
            observed_value = float(raw.get("value"))
        except (TypeError, ValueError):
            continue
        if not observed_date or not math.isfinite(observed_value):
            continue
        row = {
            "date": observed_date,
            "value": observed_value,
            "source_id": str(raw.get("source_id") or default_source_id),
        }
        if raw.get("state") in {"up", "down"}:
            row["state"] = raw["state"]
        if raw.get("methodology"):
            row["methodology"] = str(raw["methodology"])
        if raw.get("break_before"):
            row["break_before"] = True
        by_date[observed_date] = row
    return [by_date[key] for key in sorted(by_date)]


def detect_source_breaks(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Report explicit, source-id, or methodology transitions without joining them."""
    breaks: List[Dict[str, Any]] = []
    previous: Optional[Mapping[str, Any]] = None
    for row in rows:
        if previous is not None:
            reasons: List[str] = []
            if row.get("break_before"):
                reasons.append("explicit_break")
            if row.get("source_id") != previous.get("source_id"):
                reasons.append("source_id_changed")
            if row.get("methodology") != previous.get("methodology"):
                reasons.append("methodology_changed")
            if reasons:
                breaks.append(
                    {
                        "date": row.get("date"),
                        "from_source_id": previous.get("source_id"),
                        "to_source_id": row.get("source_id"),
                        "reasons": reasons,
                    }
                )
        previous = row
    return breaks


def _directional_observations(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Use provided up/down states, otherwise the sign of the one-step change.

    The fallback is deliberately mechanical.  It is a data-density diagnostic,
    not an economic regime definition and not a preregistered analog state.
    """
    observations: List[Dict[str, Any]] = []
    previous_value: Optional[float] = None
    provided_state_mode = any("state" in row for row in rows)
    for index, row in enumerate(rows):
        state = row.get("state")
        value = float(row["value"])
        if not provided_state_mode and previous_value is not None:
            if value > previous_value:
                state = "up"
            elif value < previous_value:
                state = "down"
        if state in {"up", "down"}:
            observations.append({"index": index, "date": row["date"], "state": state})
        previous_value = value
    return observations


def count_independent_directional_clusters(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_gap_trading_days: int = MIN_INDEPENDENT_GAP_TRADING_DAYS,
) -> Dict[str, Any]:
    """Count same-direction observations only when separated by the gap.

    Distance is measured in positions in the cleaned trading-day series, not
    calendar days.  Up and down have separate last-accepted positions.
    """
    if min_gap_trading_days < 1:
        raise ValueError("min_gap_trading_days must be positive")
    accepted: List[Dict[str, Any]] = []
    last_by_state: Dict[str, int] = {}
    for observation in _directional_observations(rows):
        last = last_by_state.get(observation["state"])
        if last is None or observation["index"] - last >= min_gap_trading_days:
            accepted.append(observation)
            last_by_state[observation["state"]] = observation["index"]
    counts = defaultdict(int)
    for observation in accepted:
        counts[observation["state"]] += 1
    return {
        "method": "same_direction_observations_separated_by_cleaned_trading_day_positions",
        "minimum_gap_trading_days": min_gap_trading_days,
        "classification": "provided up/down state; otherwise sign of one-step value change",
        "interpretation_limit": "mechanical data-density upper bound only; not an economic regime definition",
        "count_total": len(accepted),
        "count_by_direction": {"up": counts["up"], "down": counts["down"]},
        "accepted_observations": accepted,
    }


def _history_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "availability": "unavailable",
            "usable_start": None,
            "usable_end": None,
            "observation_count": 0,
            "calendar_span_days": 0,
        }
    start = date.fromisoformat(str(rows[0]["date"]))
    end = date.fromisoformat(str(rows[-1]["date"]))
    return {
        "availability": "available",
        "usable_start": start.isoformat(),
        "usable_end": end.isoformat(),
        "observation_count": len(rows),
        "calendar_span_days": (end - start).days,
    }


def audit_series(
    key: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    as_of: str,
    loader_note: Optional[str] = None,
    forced_breaks: Optional[Sequence[Mapping[str, Any]]] = None,
    lineages: Optional[Sequence[Mapping[str, Any]]] = None,
    history_semantics: Optional[str] = None,
) -> Dict[str, Any]:
    policy = SOURCE_POLICIES[key]
    normalized_all = normalize_rows(rows, default_source_id=policy["source_id"])
    normalized = [row for row in normalized_all if row["date"] <= as_of]
    excluded_after_as_of_count = len(normalized_all) - len(normalized)
    source_breaks = detect_source_breaks(normalized)
    source_breaks.extend(dict(item) for item in (forced_breaks or []))
    return {
        "candidate": key,
        "label": policy["label"],
        "source_name": policy["source_name"],
        "source_tier": policy["source_tier"],
        "frequency": policy["frequency"],
        "history": _history_summary(normalized),
        "as_of_filter": {
            "cutoff": as_of,
            "rule": "date <= as_of",
            "excluded_after_as_of_count": excluded_after_as_of_count,
        },
        "history_semantics": history_semantics or "candidate level observations",
        "coverage_limit": policy.get("coverage_limit"),
        "coverage_limit_source": policy.get("coverage_limit_source"),
        "known_revision_risks": list(policy["known_revision_risks"]),
        "source_migration_breaks": source_breaks,
        "lineages": list(lineages or []),
        "independent_directional_cluster_audit": count_independent_directional_clusters(normalized),
        "loader_note": loader_note,
    }


def _frame_rows(frame: Any, source_id: str) -> List[Dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    return [
        {"date": row["date"], "value": row["value"], "source_id": source_id}
        for _, row in frame.iterrows()
        if "date" in row and "value" in row
    ]


def _load_fred(series_id: str, as_of: str) -> Dict[str, Any]:
    try:
        try:
            from .tools_common import get_fred_series
        except ImportError:
            from tools_common import get_fred_series
        frame = get_fred_series(series_id, days=50000, end_date=as_of)
        quality = dict(getattr(frame, "attrs", {}).get("data_quality") or {})
        return {
            "rows": _frame_rows(frame, f"FRED_{series_id}"),
            "note": json.dumps(quality, ensure_ascii=False, sort_keys=True) if quality else None,
        }
    except Exception as exc:  # standalone audit must fail closed per candidate
        return {"rows": [], "note": f"loader_failed:{type(exc).__name__}:{str(exc)[:160]}"}


def _load_vix(as_of: str) -> Dict[str, Any]:
    try:
        try:
            from .tools_L1 import _fetch_vix_history
        except ImportError:
            from tools_L1 import _fetch_vix_history
        frame = _fetch_vix_history(start_date="1990-01-01", end_date=as_of)
        return {"rows": _frame_rows(frame, "YFINANCE_VIX"), "note": "project yfinance relay/cache"}
    except Exception as exc:
        return {"rows": [], "note": f"loader_failed:{type(exc).__name__}:{str(exc)[:160]}"}


def _load_valuation(as_of: str) -> Dict[str, Any]:
    history_by_name: Dict[str, List[Dict[str, Any]]] = {"trailing_pe": [], "forward_pe": []}
    notes: List[str] = []
    try:
        try:
            from .tools_L4 import get_ndx_valuation_history_of_market
        except ImportError:
            from tools_L4 import get_ndx_valuation_history_of_market
        payload = get_ndx_valuation_history_of_market(end_date=as_of)
        value = payload.get("value") if isinstance(payload, dict) else None
        if isinstance(value, dict):
            for series_name, context_key in (
                ("trailing_pe", "trailing_percentile_context"),
                ("forward_pe", "forward_percentile_context"),
            ):
                context = value.get(context_key)
                raw = context.get("raw_series") if isinstance(context, dict) else []
                for item in raw or []:
                    if isinstance(item, dict):
                        history_by_name[series_name].append(
                            {
                                "date": item.get("date"),
                                "value": item.get("value"),
                                "source_id": f"HOM_{series_name.upper()}",
                                "methodology": series_name,
                            }
                        )
        if not any(history_by_name.values()):
            notes.append(f"History of Market unavailable: {payload.get('unavailable_reason') or payload.get('availability')}")
    except Exception as exc:
        notes.append(f"History of Market loader failed:{type(exc).__name__}:{str(exc)[:140]}")

    # Wind does not expose a complete PIT history in this project.  Archive
    # observations are deliberately not stitched onto History of Market.
    wind_points = 0
    for packet_path in sorted((ROOT / "output" / "analysis" / "vnext").glob("*/analysis_packet.json")):
        try:
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        layers = packet.get("layers")
        l4 = layers.get("L4") if isinstance(layers, dict) else None
        item = l4.get("get_ndx_wind_valuation_snapshot") if isinstance(l4, dict) else None
        value = item.get("value") if isinstance(item, dict) else None
        if isinstance(value, dict):
            observed_date = value.get("data_date") or item.get("date")
            percentile = value.get("PEHistoricalPercentile")
            normalized_date = _iso_date(observed_date)
            if normalized_date and normalized_date <= as_of and isinstance(percentile, (int, float)):
                wind_points += 1
    notes.append(
        f"Wind archive scan found {wind_points} percentile snapshot(s); they are counted as lineage evidence only and are not stitched into the History of Market value series."
    )
    lineages: List[Dict[str, Any]] = []
    for series_name in ("trailing_pe", "forward_pe"):
        normalized = normalize_rows(
            history_by_name[series_name],
            default_source_id=f"HOM_{series_name.upper()}",
        )
        normalized = [row for row in normalized if row["date"] <= as_of]
        history_by_name[series_name] = normalized
        lineages.append(
            {
                "source_id": f"HOM_{series_name.upper()}",
                "methodology": series_name,
                **_history_summary(normalized),
                "pit_vintages_retained": False,
            }
        )
    lineages.append(
        {
            "source_id": "WIND_NDX_VALUATION_SNAPSHOT",
            "methodology": "Wind PEHistoricalPercentile point snapshots",
            "availability": "limited_snapshots" if wind_points else "unavailable",
            "observation_count": wind_points,
            "usable_start": None,
            "usable_end": None,
            "calendar_span_days": None,
            "pit_vintages_retained": True if wind_points else False,
            "note": "Archive scan counts only; dates and values are not joined to the third-party series.",
        }
    )
    # Use the longer HoM component only as a representative density series.
    # The lineage table above remains authoritative for coverage; no splice is made.
    representative = max(history_by_name.values(), key=len, default=[])
    notes.append(
        "The longer History of Market component is used only for the mechanical density count; trailing and forward series remain separate in lineages."
    )
    return {
        "rows": representative,
        "note": " ".join(notes),
        "wind_snapshot_count": wind_points,
        "lineages": lineages,
        "history_semantics": (
            "Representative underlying History of Market PE observations used to assess the raw history available for percentile calculation; "
            "this is not a time series of historical percentile readings, and it is not joined to Wind snapshots."
        ),
    }


def load_candidate_histories(as_of: str) -> Dict[str, Dict[str, Any]]:
    return {
        "dfii10": _load_fred("DFII10", as_of),
        "hy_oas": _load_fred("BAMLH0A0HYM2", as_of),
        "vix": _load_vix(as_of),
        "ndx_valuation_percentile": _load_valuation(as_of),
    }


def build_audit(
    *,
    as_of: Optional[str] = None,
    candidate_histories: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    audit_date = _iso_date(as_of or date.today().isoformat())
    if audit_date is None:
        raise ValueError("as_of must be YYYY-MM-DD")
    loaded = dict(candidate_histories or load_candidate_histories(audit_date))
    candidates: List[Dict[str, Any]] = []
    for key in ("dfii10", "hy_oas", "ndx_valuation_percentile", "vix"):
        entry = dict(loaded.get(key) or {})
        forced_breaks: List[Mapping[str, Any]] = list(entry.get("forced_breaks") or [])
        if key == "ndx_valuation_percentile":
            forced_breaks.append(
                {
                    "date": None,
                    "from_source_id": "WIND_NDX_VALUATION_SNAPSHOT",
                    "to_source_id": "HOM_TRAILING_PE/HOM_FORWARD_PE",
                    "reasons": ["non_stitchable_source_and_methodology_lineage"],
                    "note": "Wind percentile snapshots and History of Market PE histories are separate lineages; no splice is permitted.",
                }
            )
        if key == "hy_oas" and audit_date >= "2026-04-01":
            forced_breaks.append(
                {
                    "date": "2026-04-01",
                    "from_source_id": "FRED_BAMLH0A0HYM2_fuller_access",
                    "to_source_id": "FRED_BAMLH0A0HYM2_three_year_window",
                    "reasons": ["source_access_window_changed_to_three_years"],
                    "note": (
                        "FRED states that starting in April 2026 this copyrighted ICE series only includes three years of observations; "
                        "the measured start is an access-window boundary, not series inception."
                    ),
                    "source_url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
                }
            )
        candidates.append(
            audit_series(
                key,
                entry.get("rows") or [],
                as_of=audit_date,
                loader_note=entry.get("note"),
                forced_breaks=forced_breaks,
                lineages=entry.get("lineages"),
                history_semantics=entry.get("history_semantics"),
            )
        )

    unavailable = [item["candidate"] for item in candidates if item["history"]["availability"] != "available"]
    pit_unproven = [item["candidate"] for item in candidates if item["known_revision_risks"]]
    return {
        "schema_version": "analog_history_audit_v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "as_of": audit_date,
        "purpose": "data_history_audit_only",
        "metric_authority": "audit_only",
        "policy": {
            "forbidden_outputs": [
                "state_to_forward_return_distribution",
                "conditional_return",
                "win_rate",
                "return_estimate",
                "analogy_signal",
            ],
            "point_in_time_rule": "An observation history without retained publication vintages is not treated as proven PIT history.",
            "cluster_rule": "Same-direction accepted observations must be at least 63 cleaned trading-day positions apart.",
            "cluster_limit": "Counts are mechanical coverage diagnostics, not evidence of comparable economic regimes.",
        },
        "candidates": candidates,
        "admission": {
            "analogy_engine": "rejected_insufficient_clean_pit_history",
            "reasons": [
                "No candidate has a retained full publication-vintage history proving point-in-time availability.",
                "NDX valuation history has non-stitchable Wind and History of Market lineages.",
                *([f"Unavailable candidate histories: {', '.join(unavailable)}."] if unavailable else []),
                f"Revision/PIT caveats remain for: {', '.join(pit_unproven)}.",
            ],
            "next_step": "Do not build or admit an analogy engine from this audit; first establish clean PIT archives and revise the frozen preregistration draft in a separate work order.",
        },
    }


def render_markdown(audit: Mapping[str, Any]) -> str:
    lines = [
        "# 历史状态类比：数据史审计",
        "",
        f"- 审计截止日：`{audit['as_of']}`",
        "- 权限：`audit_only`（只审计，不进入 L1-L5 或综合结论）",
        "- 禁止项：未计算状态后的收益分布、条件收益、胜率、收益估计或类比信号。",
        "",
        "## 结论",
        "",
        f"类比引擎准入：`{audit['admission']['analogy_engine']}`。",
    ]
    lines.extend(f"- {reason}" for reason in audit["admission"]["reasons"])
    lines.extend(["", "## 各候选变量", ""])
    for item in audit["candidates"]:
        history = item["history"]
        clusters = item["independent_directional_cluster_audit"]
        lines.extend(
            [
                f"### {item['label']}",
                "",
                f"- 来源：{item['source_name']}（`{item['source_tier']}`）",
                f"- 可用历史：{history['usable_start'] or '无'} 至 {history['usable_end'] or '无'}；{history['observation_count']} 条；跨 {history['calendar_span_days']} 个日历日。",
                f"- 截止日硬过滤：剔除 {item['as_of_filter']['excluded_after_as_of_count']} 条晚于 `{item['as_of_filter']['cutoff']}` 的观察。",
                f"- 历史口径：{item['history_semantics']}。",
                f"- 机械独立簇上界：{clusters['count_total']}（上行 {clusters['count_by_direction']['up']} / 下行 {clusters['count_by_direction']['down']}）；同向至少间隔 {clusters['minimum_gap_trading_days']} 个清洗后交易日位置。",
                f"- 解释边界：{clusters['interpretation_limit']}。",
                f"- 数据源断点：{len(item['source_migration_breaks'])} 个。",
            ]
        )
        if item.get("loader_note"):
            lines.append(f"- 装载说明：{item['loader_note']}")
        if item.get("coverage_limit"):
            lines.append(f"- 覆盖限制：{item['coverage_limit']}")
            lines.append(f"- 覆盖限制来源：{item['coverage_limit_source']}")
        lines.append("- 已知风险：")
        lines.extend(f"  - {risk}" for risk in item["known_revision_risks"])
        if item["source_migration_breaks"]:
            lines.append("- 断点明细：")
            for source_break in item["source_migration_breaks"]:
                lines.append(
                    "  - "
                    + f"{source_break.get('date') or '无单一日期'}："
                    + ", ".join(source_break.get("reasons") or [])
                    + (f"；{source_break.get('note')}" if source_break.get("note") else "")
                )
        if item.get("lineages"):
            lines.append("- 谱系覆盖（彼此不拼接）：")
            for lineage in item["lineages"]:
                lines.append(
                    "  - "
                    + f"`{lineage.get('source_id')}` / {lineage.get('methodology')}："
                    + f"{lineage.get('usable_start') or '无'} 至 {lineage.get('usable_end') or '无'}，"
                    + f"{lineage.get('observation_count', 0)} 条；PIT vintages retained={lineage.get('pit_vintages_retained')}."
                )
        lines.append("")
    lines.extend(
        [
            "## 准入边界",
            "",
            audit["admission"]["next_step"],
            "",
            "本文件只回答数据史是否足够干净，不回答历史状态之后市场会涨还是跌。",
            "",
        ]
    )
    return "\n".join(lines)


def write_audit(audit: Mapping[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "analog_history_audit.json"
    md_path = output_dir / "analog_history_audit.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(audit), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    audit = build_audit(as_of=args.as_of)
    paths = write_audit(audit, args.output_dir)
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
