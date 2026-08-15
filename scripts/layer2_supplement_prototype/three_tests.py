# -*- coding: utf-8 -*-
"""T49-3 第二层补采原型：三性判定转常驻。

读取 `investigation_reports/20260811_layer2_research/baseline/sources_audit.json`，
对每个注册源按「靠谱 / 必要 / 能死板拿」三性判定，输出：
- `layer2_three_tests_report.json`：每源 {source, reliable, necessary, dead_simple, verdict, reason}
- `sources_to_remove.json`：verdict 非 pass 的源名单（只输出名单，不实际删源）

判定阈值只从 `three_tests_policy.md` 的 JSON 块读取；规则与脚本必须一致。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_AUDIT_PATH = REPO_ROOT / "investigation_reports" / "20260811_layer2_research" / "baseline" / "sources_audit.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
POLICY_FILENAME = "three_tests_policy.md"
ALLOWED_VERDICTS = {"pass", "撤出", "转agentic", "弃用", "挂起"}

REQUIRED_POLICY_KEYS = (
    "reliable_trust_values",
    "necessary_category_keywords",
    "dead_simple_scrapable_values",
    "verdict_decision",
)


def load_policy(policy_path: Optional[Any] = None) -> Dict[str, Any]:
    """从 three_tests_policy.md 的 ```json 围栏块读取阈值常量。"""
    path = Path(policy_path) if policy_path is not None else SCRIPT_DIR / POLICY_FILENAME
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise ValueError(f"政策文件 {path} 里找不到 ```json 围栏块")
    try:
        policy = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"政策文件 {path} 的 JSON 块不合法：{exc}") from exc

    missing = [key for key in REQUIRED_POLICY_KEYS if key not in policy]
    if missing:
        raise ValueError(f"政策 JSON 块缺少键：{missing}")

    for key in REQUIRED_POLICY_KEYS[:3]:
        if not isinstance(policy[key], list):
            raise ValueError(f"政策键 {key} 必须是数组")
    decision = policy["verdict_decision"]
    if not isinstance(decision, dict):
        raise ValueError("政策键 verdict_decision 必须是对象")
    for verdict in decision.values():
        if verdict not in ALLOWED_VERDICTS:
            raise ValueError(f"政策 verdict 非法：{verdict!r}，允许 {sorted(ALLOWED_VERDICTS)}")

    overrides = policy.get("owner_overrides")
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise ValueError("政策键 owner_overrides 必须是对象")
        for source_id, override in overrides.items():
            if isinstance(override, str):
                verdict = override
            elif isinstance(override, dict):
                verdict = override.get("verdict")
            else:
                raise ValueError(f"owner_overrides[{source_id}] 必须是字符串或对象")
            if verdict not in ALLOWED_VERDICTS:
                raise ValueError(
                    f"owner_overrides[{source_id}] 的 verdict 非法：{verdict!r}，允许 {sorted(ALLOWED_VERDICTS)}"
                )

    return policy


def _hit_keyword(necessity_text: str, keywords: List[str]) -> List[str]:
    return [keyword for keyword in keywords if keyword in necessity_text]


def _judge_source(source: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    source_id = str(source.get("source_id") or "")
    trust = str(source.get("trust") or "").strip()
    necessity_text = str(source.get("necessity") or "").strip()
    scrapable = str(source.get("scrapable") or "").strip()

    reliable_values = list(policy["reliable_trust_values"])
    necessary_keywords = list(policy["necessary_category_keywords"])
    dead_simple_values = list(policy["dead_simple_scrapable_values"])
    decision = policy["verdict_decision"]

    reliable = trust in reliable_values
    necessity_hits = _hit_keyword(necessity_text, necessary_keywords)
    necessary = bool(necessity_hits)
    dead_simple = scrapable in dead_simple_values

    if not necessary:
        machine_verdict = decision["not_necessary"]
    elif reliable and dead_simple:
        machine_verdict = decision["reliable_and_dead_simple"]
    elif reliable and not dead_simple:
        machine_verdict = decision["reliable_not_dead_simple"]
    elif not reliable and dead_simple:
        machine_verdict = decision["not_reliable_dead_simple"]
    else:
        machine_verdict = decision["not_reliable_not_dead_simple"]

    reason_parts: List[str] = []
    if reliable:
        reason_parts.append(f"trust={trust}∈可靠档{reliable_values}")
    else:
        reason_parts.append(f"trust={trust}∉可靠档{reliable_values}")
    if necessary:
        reason_parts.append(f"necessity 命中{necessity_hits}")
    else:
        reason_parts.append(f"necessity 未命中{necessary_keywords}")
    if dead_simple:
        reason_parts.append(f"scrapable={scrapable}∈死板可拿档{dead_simple_values}")
    else:
        reason_parts.append(f"scrapable={scrapable}∉死板可拿档{dead_simple_values}")
    reason_parts.append(f"判定顺序→{machine_verdict}")
    machine_reason = "；".join(reason_parts)

    verdict = machine_verdict
    reason = machine_reason
    overrides = policy.get("owner_overrides") if isinstance(policy.get("owner_overrides"), dict) else {}
    override = overrides.get(source_id)
    if override is not None:
        if isinstance(override, str):
            verdict = override
            override_note = ""
        else:
            verdict = str(override.get("verdict") or machine_verdict)
            override_note = str(override.get("reason") or "")
        reason = (
            f"owner_overrides → {verdict}（机器初判 {machine_verdict}）：{override_note}；"
            f"机器理由：{machine_reason}"
        )

    return {
        "source": source_id,
        "reliable": reliable,
        "necessary": necessary,
        "dead_simple": dead_simple,
        "verdict": verdict,
        "machine_verdict": machine_verdict,
        "reason": reason,
    }


def run_three_tests(audit: Any, output_dir: Any = None, policy_path: Any = None) -> Dict[str, Any]:
    """执行三性判定。

    audit: sources_audit.json 的 dict 或文件路径。
    output_dir: 输出目录；默认 scripts/layer2_supplement_prototype/output/。
    policy_path: 政策 md 路径；默认同目录 three_tests_policy.md。
    """
    if isinstance(audit, (str, Path)):
        audit = json.loads(Path(audit).read_text(encoding="utf-8"))

    policy = load_policy(policy_path)
    output_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    sources_raw = audit.get("sources")
    if not isinstance(sources_raw, list):
        raise ValueError("sources_audit 缺少 sources 数组")

    judged_sources = [_judge_source(source, policy) for source in sources_raw if isinstance(source, dict)]

    verdict_counts: Dict[str, int] = {verdict: 0 for verdict in sorted(ALLOWED_VERDICTS)}
    for item in judged_sources:
        verdict_counts[item["verdict"]] = verdict_counts.get(item["verdict"], 0) + 1

    report = {
        "schema_version": "layer2_three_tests_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy_file": str(Path(policy_path) if policy_path is not None else SCRIPT_DIR / POLICY_FILENAME),
        "audited_source_count": len(judged_sources),
        "verdict_counts": verdict_counts,
        "sources": judged_sources,
    }
    (output_dir / "layer2_three_tests_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 挂起 = 所有者已裁"暂时不管"，不进撤出名单，也不当 pass。
    removed_sources = [item for item in judged_sources if item["verdict"] in {"撤出", "转agentic", "弃用"}]
    removal_list = {
        "schema_version": "layer2_sources_to_remove_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy_file": str(Path(policy_path) if policy_path is not None else SCRIPT_DIR / POLICY_FILENAME),
        "removal_count": len(removed_sources),
        "note": "只输出名单，不实际删源；名单与 baseline 差异需人工复核后再施工。",
        "sources": removed_sources,
    }
    (output_dir / "sources_to_remove.json").write_text(
        json.dumps(removal_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="T49-3 第二层补采原型：三性判定转常驻（只输出名单，不实际删源）")
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT_PATH), help="sources_audit.json 路径")
    parser.add_argument("--policy", default=str(SCRIPT_DIR / POLICY_FILENAME), help="three_tests_policy.md 路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录（默认 scripts/layer2_supplement_prototype/output/）")
    args = parser.parse_args(argv)

    audit_path = Path(args.audit)
    if not audit_path.is_file():
        print(f"audit 文件不存在：{audit_path}", file=sys.stderr)
        return 2

    report = run_three_tests(audit_path, output_dir=args.output_dir, policy_path=args.policy)
    counts = report["verdict_counts"]
    print(
        f"三性判定完成：共 {report['audited_source_count']} 源；"
        f"pass {counts.get('pass', 0)} / 撤出 {counts.get('撤出', 0)} / "
        f"转agentic {counts.get('转agentic', 0)} / 弃用 {counts.get('弃用', 0)} / "
        f"挂起 {counts.get('挂起', 0)}"
    )
    print(f"报告：{Path(args.output_dir) / 'layer2_three_tests_report.json'}")
    print(f"撤出/转agentic/弃用名单：{Path(args.output_dir) / 'sources_to_remove.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
