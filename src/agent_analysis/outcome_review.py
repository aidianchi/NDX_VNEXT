from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .contracts import OutcomeReviewReport, OutcomeWindowPerformance, RunReviewFinding
except ImportError:
    from contracts import OutcomeReviewReport, OutcomeWindowPerformance, RunReviewFinding


OUTCOME_WINDOWS = [
    ("+1w", 5),
    ("+1m", 21),
    ("+3m", 63),
    ("+6m", 126),
    ("+12m", 252),
]

PROMPT_ARTIFACTS = [
    "analysis_packet.json",
    "context_brief.json",
    "synthesis_packet.json",
    "thesis_draft.json",
    "risk_boundary_report.json",
    "analysis_revised.json",
    "final_adjudication.json",
]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _date_key(row: Dict[str, Any]) -> str:
    return str(row.get("date") or row.get("time") or row.get("Date") or "")


def _close_value(row: Dict[str, Any]) -> Optional[float]:
    for key in ("close", "Close", "adj_close", "Adj Close"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _normalize_price_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_text = _date_key(row)[:10]
        close = _close_value(row)
        if not date_text or close is None:
            continue
        normalized.append({"date": date_text, "close": close})
    return sorted(normalized, key=lambda item: item["date"])


def _fetch_qqq_rows(backtest_date: str, *, ticker: str = "QQQ") -> tuple[List[Dict[str, Any]], str]:
    start = datetime.strptime(backtest_date, "%Y-%m-%d").date()
    end = start + timedelta(days=390)
    try:
        from tools_common import cached_yf_download, clean_yfinance_dataframe
    except Exception:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        try:
            from tools_common import cached_yf_download, clean_yfinance_dataframe
        except Exception:
            return [], "unavailable: tools_common/yfinance path not importable"

    frame = cached_yf_download(ticker, start=str(start), end=str(end), auto_adjust=True)
    if frame is None or getattr(frame, "empty", True):
        return [], "unavailable: yfinance returned no QQQ outcome rows"
    try:
        frame = clean_yfinance_dataframe(frame)
    except Exception:
        pass
    rows: List[Dict[str, Any]] = []
    for record in frame.reset_index().to_dict(orient="records"):
        date_value = record.get("date") or record.get("Date") or record.get("index")
        close = record.get("close") if "close" in record else record.get("Close")
        rows.append({"date": str(date_value)[:10], "close": close})
    return _normalize_price_rows(rows), "Yahoo Finance via cached_yf_download"


def _window_performance(rows: List[Dict[str, Any]], backtest_date: str) -> List[OutcomeWindowPerformance]:
    if not rows:
        return [
            OutcomeWindowPerformance(window=label, target_trading_days=days, data_status="missing")
            for label, days in OUTCOME_WINDOWS
        ]
    start_idx = next((index for index, row in enumerate(rows) if row["date"] >= backtest_date), None)
    if start_idx is None:
        return [
            OutcomeWindowPerformance(window=label, target_trading_days=days, data_status="missing")
            for label, days in OUTCOME_WINDOWS
        ]
    start = rows[start_idx]
    start_close = float(start["close"])
    outputs: List[OutcomeWindowPerformance] = []
    for label, days in OUTCOME_WINDOWS:
        end_idx = start_idx + days
        if end_idx >= len(rows):
            outputs.append(
                OutcomeWindowPerformance(
                    window=label,
                    target_trading_days=days,
                    start_date=start["date"],
                    start_close=round(start_close, 4),
                    data_status="incomplete",
                )
            )
            continue
        end = rows[end_idx]
        segment = rows[start_idx : end_idx + 1]
        min_close = min(float(row["close"]) for row in segment)
        outputs.append(
            OutcomeWindowPerformance(
                window=label,
                target_trading_days=days,
                start_date=start["date"],
                end_date=end["date"],
                start_close=round(start_close, 4),
                end_close=round(float(end["close"]), 4),
                return_pct=round((float(end["close"]) / start_close - 1.0) * 100.0, 2),
                max_drawdown_pct=round((min_close / start_close - 1.0) * 100.0, 2),
                data_status="available",
            )
        )
    return outputs


def _market_outcome_label(windows: List[OutcomeWindowPerformance]) -> str:
    returns = {item.window: item.return_pct for item in windows if item.return_pct is not None}
    drawdowns = [item.max_drawdown_pct for item in windows if item.max_drawdown_pct is not None]
    if returns.get("+3m", 0) >= 10 or returns.get("+6m", 0) >= 15 or returns.get("+12m", 0) >= 20:
        return "strong_follow_through_rally"
    if returns.get("+1m", 0) <= -10 or returns.get("+3m", 0) <= -15 or (drawdowns and min(drawdowns) <= -15):
        return "material_follow_through_selloff"
    return "mixed_or_range_bound"


def _has_cautious_language(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("谨慎", "防守", "等待", "中性", "cautious", "defensive", "wait"))


def _has_aggressive_language(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("进攻", "满仓", "高赔率", "加大", "aggressive", "risk-on"))


def _leakage_checks(run_path: Path) -> List[str]:
    checks: List[str] = []
    banned_tokens = ("outcome_review", "post_hoc_outcome", "return_pct", "+12m")
    for name in PROMPT_ARTIFACTS:
        path = run_path / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        leaked = [token for token in banned_tokens if token in text]
        if leaked:
            checks.append(f"{name}: possible leakage tokens found: {', '.join(leaked)}")
        else:
            checks.append(f"{name}: no Outcome Review tokens found")
    if not checks:
        checks.append("No prompt artifacts found to inspect; Outcome Review still runs as a post-Final artifact.")
    return checks


def build_outcome_review_report(
    *,
    run_dir: str = "",
    backtest_date: Optional[str] = None,
    final_adjudication: Optional[Dict[str, Any]] = None,
    price_rows: Optional[List[Dict[str, Any]]] = None,
    source: str = "",
    tradable_proxy: str = "QQQ",
) -> OutcomeReviewReport:
    run_path = Path(run_dir) if run_dir else Path()
    final_adjudication = final_adjudication or {}
    if not backtest_date and run_dir:
        packet = _load_json(run_path / "analysis_packet.json", {})
        meta = packet.get("meta", {}) if isinstance(packet.get("meta"), dict) else {}
        backtest_date = meta.get("backtest_date") or meta.get("data_date")
    if not backtest_date:
        raise ValueError("backtest_date is required for Outcome Review.")

    if price_rows is None:
        price_rows, fetched_source = _fetch_qqq_rows(backtest_date, ticker=tradable_proxy)
        source = source or fetched_source
    else:
        price_rows = _normalize_price_rows(price_rows)
        source = source or "provided_price_rows"

    windows = _window_performance(price_rows, backtest_date)
    label = _market_outcome_label(windows)
    final_text = " ".join(
        str(part)
        for part in [
            final_adjudication.get("final_stance", ""),
            final_adjudication.get("state_diagnosis", ""),
            final_adjudication.get("payoff_assessment", ""),
            (final_adjudication.get("reader_final") or {}).get("one_liner", "")
            if isinstance(final_adjudication.get("reader_final"), dict)
            else "",
        ]
        if part
    )

    findings: List[RunReviewFinding] = []
    learning_updates: List[str] = []
    if label == "strong_follow_through_rally":
        if _has_cautious_language(final_text):
            caution_review = "后续 QQQ 大涨；原判断含谨慎/等待语言，需要检查 Final 是否低估确认成本和踏空成本。"
            findings.append(
                RunReviewFinding(
                    category="final",
                    severity="observe",
                    finding=caution_review,
                    artifact_refs=["final_adjudication.json", "outcome_review_report.json"],
                    recommended_rule_update="后续大涨样本中，Review 必须检查 Final 是否把风险未解除误写成动作过度防守。",
                )
            )
            learning_updates.append("强反弹后验只能用于 Review；下一轮应让 Risk/Final 更稳定地表达踏空成本。")
        else:
            caution_review = "后续 QQQ 大涨；原判断未明显过度谨慎，但仍需检查是否清楚表达了分批进攻和失效条件。"
    else:
        caution_review = "后续市场未呈现强反弹；本轮不把过度谨慎作为主要复盘问题。"

    if label == "material_follow_through_selloff":
        if _has_aggressive_language(final_text):
            aggression_review = "后续 QQQ 明显下跌；原判断含进攻/高赔率语言，需要检查是否过度冒进。"
            findings.append(
                RunReviewFinding(
                    category="final",
                    severity="observe",
                    finding=aggression_review,
                    artifact_refs=["final_adjudication.json", "outcome_review_report.json"],
                    recommended_rule_update="后续下跌样本中，Review 必须检查 Final 是否把便宜/恐慌误写成无纪律进攻。",
                )
            )
            learning_updates.append("下跌后验只能用于 Review；下一轮应检查便宜与基本面恶化是否被混淆。")
        else:
            aggression_review = "后续 QQQ 明显下跌；原判断未明显冒进，但需检查失效条件是否足够早、足够可执行。"
    else:
        aggression_review = "后续市场未呈现显著下跌；本轮不把过度冒进作为主要复盘问题。"

    return OutcomeReviewReport(
        run_dir=run_dir,
        backtest_date=backtest_date,
        tradable_proxy=tradable_proxy,
        source=source,
        windows=windows,
        market_outcome_label=label,
        caution_review=caution_review,
        aggression_review=aggression_review,
        attribution_findings=findings,
        learning_updates=list(dict.fromkeys(learning_updates)),
        prompt_leakage_checks=_leakage_checks(run_path) if run_dir else [],
    )


def build_outcome_review_from_dir(run_dir: str | Path) -> OutcomeReviewReport:
    run_path = Path(run_dir)
    packet = _load_json(run_path / "analysis_packet.json", {})
    meta = packet.get("meta", {}) if isinstance(packet.get("meta"), dict) else {}
    return build_outcome_review_report(
        run_dir=str(run_path),
        backtest_date=meta.get("backtest_date") or meta.get("data_date"),
        final_adjudication=_load_json(run_path / "final_adjudication.json", {}),
    )


def write_outcome_review_report(run_dir: str | Path, output_path: str | Path | None = None) -> Path:
    report = build_outcome_review_from_dir(run_dir)
    target = Path(output_path) if output_path else Path(run_dir) / "outcome_review_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a post-hoc vNext Outcome Review artifact.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    print(write_outcome_review_report(args.run_dir, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
