"""
状态台账（State Ledger）：跨 run 的确定性状态变量记录层。

设计出处：docs/2026-07-06_STAGE0-4_REVIEW_AND_DIRECTION.md 修正一（state ledger 定案）。

边界：
- 只做记录（append-only JSONL），不做展示；展示层须等三个启用闸门满足后另行实现。
- 状态变量只收确定性数值/枚举（来自 raw_data 与读者出口产物），LLM 派生项必须带 llm_derived 标记。
- 台账是读者出口与结果记分的地基，不得注入 L1-L5、Bridge、Thesis、Critic、Risk、
  Reviser、Final 或竞争裁决的任何 prompt。
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_PATH = ROOT / "output" / "state_ledger" / "state_ledger.jsonl"

STATE_LEDGER_SCHEMA_VERSION = "state_ledger_v1"

# 提取表：稳定状态键 -> (layer, function_id, value 内路径)。
# 路径取不到时记 None 并写入 missing_variables，不视为错误。
STATE_VARIABLE_SPECS: List[Dict[str, Any]] = [
    {"key": "valuation.trailing_pe", "layer": "L4", "function_id": "get_ndx_pe_and_earnings_yield", "path": ["TrailingPE"]},
    {"key": "valuation.forward_pe", "layer": "L4", "function_id": "get_ndx_pe_and_earnings_yield", "path": ["ForwardPE"]},
    {"key": "valuation.forward_earnings_yield_pct", "layer": "L4", "function_id": "get_ndx_pe_and_earnings_yield", "path": ["ForwardEarningsYield"]},
    {"key": "valuation.forward_eps_growth_proxy_pct", "layer": "L4", "function_id": "get_ndx_forward_earnings_quality", "path": ["ndx", "forward_eps_growth_proxy_pct"]},
    {"key": "liquidity.net_liquidity_level_bn", "layer": "L1", "function_id": "get_net_liquidity_momentum", "path": ["level"]},
    {"key": "liquidity.net_liquidity_momentum_4w_bn", "layer": "L1", "function_id": "get_net_liquidity_momentum", "path": ["momentum_4w"]},
    {"key": "risk_appetite.vix_level", "layer": "L2", "function_id": "get_vix", "path": ["level"]},
    {"key": "risk_appetite.vix_percentile_10y", "layer": "L2", "function_id": "get_vix", "path": ["historical_stats", "percentile_10y"]},
    {"key": "credit.hyg_level", "layer": "L2", "function_id": "get_hyg_momentum", "path": ["level"]},
    {"key": "credit.hyg_percentile_1y", "layer": "L2", "function_id": "get_hyg_momentum", "path": ["relativity", "percentile_1y"]},
    {"key": "breadth.adv_decline_level", "layer": "L3", "function_id": "get_advance_decline_line", "path": ["level"]},
    {"key": "breadth.adv_decline_trend", "layer": "L3", "function_id": "get_advance_decline_line", "path": ["trend"]},
    {"key": "concentration.ndx_ndxe_ratio", "layer": "L3", "function_id": "get_ndx_ndxe_ratio", "path": ["level"]},
    {"key": "concentration.ndx_ndxe_percentile_10y", "layer": "L3", "function_id": "get_ndx_ndxe_ratio", "path": ["relativity", "percentile_10y"]},
    {"key": "trend.qqq_price", "layer": "L5", "function_id": "get_multi_scale_ma_position", "path": ["current_price"]},
    {"key": "trend.short_vs_long_divergence_pct", "layer": "L5", "function_id": "get_multi_scale_ma_position", "path": ["cross_scale_divergence", "short_vs_long"]},
    {"key": "trend.donchian_upper", "layer": "L5", "function_id": "get_donchian_channels_qqq", "path": ["upper"]},
    {"key": "trend.donchian_position_pct", "layer": "L5", "function_id": "get_donchian_channels_qqq", "path": ["position_pct"]},
    # Wind 主锚离线时为 None；接上后无需改代码即可入账。
    {"key": "valuation.wind_pe_percentile", "layer": "L4", "function_id": "get_ndx_wind_valuation_snapshot", "path": ["pe_percentile"]},
    {"key": "valuation.equity_risk_premium", "layer": "L4", "function_id": "get_equity_risk_premium", "path": ["level"]},
]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _dig(payload: Any, path: List[str]) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, bool):
        return None
    if isinstance(current, (int, float, str)):
        return current
    return None


def extract_state_variables(analysis_packet: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    raw_data = analysis_packet.get("raw_data") if isinstance(analysis_packet.get("raw_data"), dict) else {}
    variables: Dict[str, Any] = {}
    missing: List[str] = []
    for spec in STATE_VARIABLE_SPECS:
        layer_data = raw_data.get(spec["layer"], {}) if isinstance(raw_data.get(spec["layer"]), dict) else {}
        payload = layer_data.get(spec["function_id"], {}) if isinstance(layer_data.get(spec["function_id"]), dict) else {}
        value = _dig(payload.get("value"), spec["path"]) if isinstance(payload.get("value"), dict) else None
        variables[spec["key"]] = value
        if value is None:
            missing.append(spec["key"])

    upper = variables.get("trend.donchian_upper")
    price = variables.get("trend.qqq_price")
    if isinstance(upper, (int, float)) and isinstance(price, (int, float)) and upper > 0:
        variables["trend.drawdown_from_donchian_upper_pct"] = round((upper - price) / upper * 100, 2)
    else:
        variables["trend.drawdown_from_donchian_upper_pct"] = None
        missing.append("trend.drawdown_from_donchian_upper_pct")
    return variables, missing


def _profile_condition_statuses(golden_pit_checklist: Dict[str, Any]) -> Dict[str, str]:
    entries = golden_pit_checklist.get("entries") if isinstance(golden_pit_checklist.get("entries"), list) else []
    statuses: Dict[str, str] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        condition_id = str(item.get("condition_id") or "")
        # claim 回声条目的 ID 是内容哈希，跨 run 不稳定，永远不入台账。
        if not condition_id or condition_id.startswith("claim:"):
            continue
        statuses[condition_id] = str(item.get("current_status") or "insufficient_evidence")
    return statuses


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


def build_state_ledger_entry(run_dir: str | Path, *, official: bool = False) -> Dict[str, Any]:
    run_path = Path(run_dir)
    analysis_packet = _load_json(run_path / "analysis_packet.json", {})
    golden_pit_checklist = _load_json(run_path / "golden_pit_checklist.json", {})
    final_claim_ledger = _load_json(run_path / "final_claim_ledger.json", {})
    hypothesis_competition = _load_json(run_path / "hypothesis_competition.json", {})
    data_integrity = _load_json(run_path / "data_integrity_report.json", {})

    meta = analysis_packet.get("meta") if isinstance(analysis_packet.get("meta"), dict) else {}
    variables, missing = extract_state_variables(analysis_packet)
    publish_gate = final_claim_ledger.get("publish_gate") if isinstance(final_claim_ledger.get("publish_gate"), dict) else {}
    hypotheses = hypothesis_competition.get("hypotheses") if isinstance(hypothesis_competition.get("hypotheses"), list) else []

    return {
        "schema_version": STATE_LEDGER_SCHEMA_VERSION,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_path.name,
        "data_date": str(meta.get("data_date") or ""),
        "backtest_date": meta.get("backtest_date"),
        "official": bool(official),
        "git_sha": _git_sha(),
        "schema_versions": {
            "analysis_packet": str(meta.get("schema_version") or ""),
            "final_claim_ledger": str(final_claim_ledger.get("schema_version") or ""),
            "golden_pit_checklist": str(golden_pit_checklist.get("schema_version") or ""),
        },
        "state_variables": variables,
        "missing_variables": missing,
        "profile_condition_statuses": _profile_condition_statuses(golden_pit_checklist),
        "gates": {
            "claim_ledger_publish_gate": str(publish_gate.get("status") or "missing"),
            "data_integrity_blocked": bool(data_integrity.get("blocked")),
            "data_integrity_unpublishable": bool(data_integrity.get("unpublishable")),
        },
        "llm_derived": {
            "llm_derived": True,
            "leading_hypothesis_present": bool(hypothesis_competition.get("leading_hypothesis_id")),
            "hypothesis_count": len(hypotheses),
            "note": "LLM 派生项只作背景；跨 run 对比与报警不得基于本组字段。",
        },
        "no_backflow_rule": (
            "State ledger entries are reader-exit / outcome-scoring material only; "
            "they must not be injected into L1-L5, Bridge, Thesis, Critic, Risk, "
            "Reviser, Final, or hypothesis competition prompts."
        ),
    }


def append_state_ledger_entry(
    run_dir: str | Path,
    *,
    official: bool = False,
    ledger_path: str | Path | None = None,
) -> Dict[str, Any]:
    """构建并追加一条台账记录；同 run_id 已存在时跳过，保持 append-only 语义。"""
    target = Path(ledger_path) if ledger_path else DEFAULT_LEDGER_PATH
    entry = build_state_ledger_entry(run_dir, official=official)

    existing_run_ids = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing_run_ids.add(str(json.loads(line).get("run_id") or ""))
            except json.JSONDecodeError:
                continue
    if entry["run_id"] in existing_run_ids:
        return {"status": "skipped_duplicate_run_id", "run_id": entry["run_id"], "ledger_path": str(target)}

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    return {"status": "appended", "run_id": entry["run_id"], "ledger_path": str(target), "official": entry["official"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one deterministic state ledger entry from a run directory.")
    parser.add_argument("--run-dir", required=True, help="vNext run directory")
    parser.add_argument("--official", action="store_true", help="Mark this run as an official daily entry")
    parser.add_argument("--ledger-path", default=None, help="Override ledger JSONL path")
    args = parser.parse_args()
    result = append_state_ledger_entry(args.run_dir, official=args.official, ledger_path=args.ledger_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
