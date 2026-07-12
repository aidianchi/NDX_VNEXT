"""Cross-run claim outcome scoring batch runner.

Design context: 施工台账 (`investigation_reports/20260711_first_principles/WORK_ORDERS.md`)
工单队列 #2「校准闭环通电」。

`outcome_review.py` already contains a working claim outcome scorer
(`build_claim_outcome_scores`, T+20/T+60/T+120 verdicts against QQQ price
follow-through). It only ever runs *inside* a live orchestrator pass, and the
orchestrator skips it entirely for non-backtest (live) runs because the
judgement's effective date has not aged enough for any forward window to be
meaningful yet (`source: "not_run_for_live_or_non_backtest_context"`).

This module adds an out-of-band batch path: scan every run under
`output/analysis/vnext/*/final_claim_ledger.json`, work out each run's
effective (judgement) date, and for any run old enough for at least the
T+20 window to exist, call the *existing, unmodified* scoring algorithm and
write a dedicated `claim_outcome_scores.json` into that run's directory. A
one-line-per-run summary is appended to
`output/state_ledger/claim_outcome_ledger.jsonl`.

Boundaries (do not relax without updating WORK_ORDERS.md):
- This module must not import or mutate anything in `orchestrator.py`. It
  runs strictly after the fact, offline, against already-published run
  artifacts.
- It must not touch `outcome_review_report.json` (that file is owned by the
  live orchestrator pass and by the cross-run display-layer deferral in
  `orchestrator.py` around `deferred_until_run_quality_stable`). This module
  only ever writes `claim_outcome_scores.json` plus the ledger line.
- No score-backflow: claim outcome scores must never be injected into
  L1-L5, Bridge, Thesis, Risk, Reviser, or Final prompts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .outcome_review import _fetch_qqq_rows, build_claim_outcome_scores
except ImportError:  # pragma: no cover - exercised when run as a top-level script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from outcome_review import _fetch_qqq_rows, build_claim_outcome_scores


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER_PATH = ROOT / "output" / "state_ledger" / "claim_outcome_ledger.jsonl"

CLAIM_OUTCOME_SCORES_SCHEMA_VERSION = "claim_outcome_scores_v1"
CLAIM_OUTCOME_LEDGER_SCHEMA_VERSION = "claim_outcome_ledger_v1"

MIN_SCORABLE_AGE_DAYS = 20

DATA_QUALITY_CAVEAT = (
    "数据层验收完成前，本分数优先作为数据问题探测器使用（暴露 claim/evidence/价格窗口链路中的结构性缺口），"
    "不代表对判断质量的最终结论；请先核对 verdict 是否合理，再考虑是否用于校准判断质量。"
)

NO_BACKFLOW_RULE = (
    "Claim outcome scores are post-Final review artifacts and must not feed "
    "L1-L5, Bridge, Thesis, Risk, Reviser, or Final prompts."
)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        sha = result.stdout.strip()
        return sha or "unknown"
    except Exception:
        return "unknown"


def resolve_run_effective_date(run_dir: Path) -> Optional[str]:
    """判断生效日期：backtest run 用 backtest_date，live run 用采集当日 data_date。

    两个字段都来自 `analysis_packet.json` 的 `meta`（同一份元数据也是
    orchestrator 自身判定"是否处于回测语境"的依据，见 orchestrator.py
    `_build_outcome_review_report`）；run_summary.json 在 live run 场景下不落
    这两个字段，因此 analysis_packet.json 更可靠。
    """
    packet = _load_json(run_dir / "analysis_packet.json", {})
    meta = packet.get("meta") if isinstance(packet.get("meta"), dict) else {}
    backtest_date = meta.get("backtest_date")
    if isinstance(backtest_date, str) and backtest_date:
        return backtest_date
    data_date = meta.get("data_date")
    if isinstance(data_date, str) and data_date:
        return data_date
    return None


def resolve_run_kind(run_dir: Path) -> str:
    packet = _load_json(run_dir / "analysis_packet.json", {})
    meta = packet.get("meta") if isinstance(packet.get("meta"), dict) else {}
    return "backtest" if meta.get("backtest_date") else "live"


def compute_age_days(effective_date: str, *, as_of: Optional[date] = None) -> Optional[int]:
    try:
        effective = datetime.strptime(effective_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    today = as_of or datetime.now(timezone.utc).date()
    return (today - effective).days


def discover_candidate_run_dirs(vnext_root: Path) -> List[Path]:
    """任何带 final_claim_ledger.json 的 run 目录都是候选；没有该文件的目录天然被跳过（缺 ledger 容忍）。"""
    if not vnext_root.exists():
        return []
    return sorted(
        {path.parent for path in vnext_root.glob("*/final_claim_ledger.json") if path.is_file()},
        key=lambda p: p.name,
    )


def _annotate_pending(window: Dict[str, Any]) -> Dict[str, Any]:
    """如实标注 pending：窗口尚未到期（未来价格数据还不存在）时附加 pending=True，
    不改写 outcome_review.py 原有的 data_status 语义（available/incomplete/missing）。"""
    annotated = dict(window)
    annotated["pending"] = annotated.get("data_status") == "incomplete"
    return annotated


def score_run(
    run_dir: Path,
    *,
    min_age_days: int = MIN_SCORABLE_AGE_DAYS,
    as_of: Optional[date] = None,
    tradable_proxy: str = "QQQ",
) -> Dict[str, Any]:
    """给单个 run 打分（若合格）；返回描述结果的字典，不抛异常给调用方。"""
    run_id = run_dir.name
    effective_date = resolve_run_effective_date(run_dir)
    if not effective_date:
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "status": "skipped_missing_effective_date",
        }

    age_days = compute_age_days(effective_date, as_of=as_of)
    if age_days is None:
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "status": "skipped_invalid_effective_date",
            "effective_date": effective_date,
        }

    run_kind = resolve_run_kind(run_dir)
    if age_days < min_age_days:
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "status": "skipped_too_young",
            "effective_date": effective_date,
            "run_kind": run_kind,
            "age_days": age_days,
            "min_age_days": min_age_days,
        }

    final_claim_ledger = _load_json(run_dir / "final_claim_ledger.json", {})
    entries = final_claim_ledger.get("entries") if isinstance(final_claim_ledger.get("entries"), list) else []
    if not entries:
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "status": "skipped_empty_claim_ledger",
            "effective_date": effective_date,
            "run_kind": run_kind,
            "age_days": age_days,
        }

    evidence_registry = _load_json(run_dir / "evidence_registry.json", {})

    try:
        price_rows, price_source = _fetch_qqq_rows(effective_date, ticker=tradable_proxy)
        claim_scores_payload = build_claim_outcome_scores(
            final_claim_ledger=final_claim_ledger,
            price_rows=price_rows,
            backtest_date=effective_date,
            evidence_registry=evidence_registry,
        )
    except Exception as exc:  # keep one bad run from aborting the whole batch (docstring contract: never raise)
        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "status": "error",
            "effective_date": effective_date,
            "run_kind": run_kind,
            "age_days": age_days,
            "error": f"{type(exc).__name__}: {exc}",
        }

    scoring_date = (as_of or datetime.now(timezone.utc).date()).isoformat()

    windows_out = [_annotate_pending(window) for window in claim_scores_payload.get("windows", [])]

    verdict_totals = {"consistent": 0, "falsifier_triggered": 0, "not_scorable": 0}
    scores_out: List[Dict[str, Any]] = []
    for score in claim_scores_payload.get("scores", []):
        annotated_score = dict(score)
        annotated_score["data_quality_caveat"] = DATA_QUALITY_CAVEAT
        scoring_evidence = dict(annotated_score.get("scoring_evidence") or {})
        scoring_evidence["windows"] = [_annotate_pending(w) for w in scoring_evidence.get("windows", [])]
        annotated_score["scoring_evidence"] = scoring_evidence
        scores_out.append(annotated_score)
        verdict = str(annotated_score.get("verdict") or "not_scorable")
        verdict_totals[verdict] = verdict_totals.get(verdict, 0) + 1

    scorable_claim_count = verdict_totals.get("consistent", 0) + verdict_totals.get("falsifier_triggered", 0)
    not_scorable_claim_count = verdict_totals.get("not_scorable", 0)
    pending_window_labels = sorted({w["window"] for w in windows_out if w.get("pending")})

    claim_outcome_scores_doc: Dict[str, Any] = {
        "schema_version": CLAIM_OUTCOME_SCORES_SCHEMA_VERSION,
        "run_id": run_id,
        "run_kind": run_kind,
        "effective_date": effective_date,
        "scoring_date": scoring_date,
        "scoring_age_days": age_days,
        "min_scorable_age_days": min_age_days,
        "tradable_proxy": tradable_proxy,
        "price_source": price_source,
        "data_quality_caveat": DATA_QUALITY_CAVEAT,
        "windows": windows_out,
        "pending_windows": pending_window_labels,
        "scores": scores_out,
        "summary": claim_scores_payload.get("summary", {}),
        "verdict_totals": verdict_totals,
        "scorable_claim_count": scorable_claim_count,
        "not_scorable_claim_count": not_scorable_claim_count,
        "total_claim_count": len(entries),
        "no_backflow_rule": NO_BACKFLOW_RULE,
    }

    output_path = run_dir / "claim_outcome_scores.json"
    output_path.write_text(
        json.dumps(claim_outcome_scores_doc, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": "scored",
        "effective_date": effective_date,
        "run_kind": run_kind,
        "age_days": age_days,
        "output_path": str(output_path),
        "claim_outcome_scores": claim_outcome_scores_doc,
    }


def build_ledger_entry(result: Dict[str, Any]) -> Dict[str, Any]:
    doc = result["claim_outcome_scores"]
    window_data_status = {w["window"]: w.get("data_status") for w in doc.get("windows", [])}
    return {
        "schema_version": CLAIM_OUTCOME_LEDGER_SCHEMA_VERSION,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_id": result["run_id"],
        "run_kind": doc.get("run_kind"),
        "effective_date": result["effective_date"],
        "scoring_date": doc.get("scoring_date"),
        "scoring_age_days": result.get("age_days"),
        "window_data_status": window_data_status,
        "pending_windows": doc.get("pending_windows", []),
        "verdict_totals": doc.get("verdict_totals", {}),
        "scorable_claim_count": doc.get("scorable_claim_count", 0),
        "not_scorable_claim_count": doc.get("not_scorable_claim_count", 0),
        "total_claim_count": doc.get("total_claim_count", 0),
        "claim_outcome_scores_path": result.get("output_path", ""),
        "git_sha": _git_sha(),
        "data_quality_caveat": DATA_QUALITY_CAVEAT,
        "no_backflow_rule": NO_BACKFLOW_RULE,
    }


def append_claim_outcome_ledger_entry(
    result: Dict[str, Any],
    *,
    ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """按 run_id 幂等追加：同一 run_id 重复打分时覆盖旧记录（保留最新窗口成熟度），不重复堆积。"""
    target = Path(ledger_path) if ledger_path else DEFAULT_LEDGER_PATH
    entry = build_ledger_entry(result)
    run_id = entry["run_id"]

    rows: List[Dict[str, Any]] = []
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("run_id") == run_id:
                continue  # dedupe: drop the stale entry for this run, replaced below
            rows.append(row)
    rows.append(entry)

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return {"status": "appended", "run_id": run_id, "ledger_path": str(target)}


def run_score_outcomes_batch(
    vnext_root: Path,
    *,
    min_age_days: int = MIN_SCORABLE_AGE_DAYS,
    as_of: Optional[date] = None,
    ledger_path: Optional[Path] = None,
    tradable_proxy: str = "QQQ",
) -> Dict[str, Any]:
    """扫描 vnext_root 下所有 run，给合格 run 打分并落盘，返回批次汇总。不造数：无合格对象时如实说明。"""
    candidate_dirs = discover_candidate_run_dirs(vnext_root)
    results = [
        score_run(run_dir, min_age_days=min_age_days, as_of=as_of, tradable_proxy=tradable_proxy)
        for run_dir in candidate_dirs
    ]

    scored_results = [r for r in results if r["status"] == "scored"]
    ledger_appends = [append_claim_outcome_ledger_entry(r, ledger_path=ledger_path) for r in scored_results]

    status_counts: Dict[str, int] = {}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    message = (
        f"{len(scored_results)} 个 run 达到可打分年龄（>= {min_age_days} 自然日）并已打分。"
        if scored_results
        else f"0 个 run 达到可打分年龄（候选 {len(candidate_dirs)} 个，均不满 {min_age_days} 自然日或不合格）。"
    )

    return {
        "mode": "score_outcomes",
        "vnext_root": str(vnext_root),
        "min_scorable_age_days": min_age_days,
        "candidate_run_count": len(candidate_dirs),
        "scored_run_count": len(scored_results),
        "status_counts": status_counts,
        "message": message,
        "results": results,
        "ledger_appends": ledger_appends,
        "ledger_path": str(Path(ledger_path) if ledger_path else DEFAULT_LEDGER_PATH),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline batch: score matured vNext runs' final claims against forward QQQ price windows."
    )
    parser.add_argument("--vnext-root", default=None, help="Root dir containing run subdirectories (default output/analysis/vnext).")
    parser.add_argument("--min-age-days", type=int, default=MIN_SCORABLE_AGE_DAYS)
    parser.add_argument("--ledger-path", default=None)
    args = parser.parse_args()

    if args.vnext_root:
        vnext_root = Path(args.vnext_root)
    else:
        vnext_root = ROOT / "output" / "analysis" / "vnext"

    summary = run_score_outcomes_batch(
        vnext_root,
        min_age_days=args.min_age_days,
        ledger_path=Path(args.ledger_path) if args.ledger_path else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
