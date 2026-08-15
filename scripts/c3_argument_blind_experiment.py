#!/usr/bin/env python
"""C3 论证盲对照实验执行器（2026-08-15，方案见 T50-3_论证盲对照实验_方案.md）。

用同一份真实 run 的上游产物，对 risk 站跑两组、各一次：
  A 组 blind：consumer="risk"（无任何 thesis_*，论证盲）——生产新口径。
  B 组 seen ：consumer="critic" 包（含 thesis_*），提示词同 A 组、只把
              "拿不到论点"改为"拿得到论点、仍产出完整风险报告"（不设输出禁令）。
两组共用同一个模型（默认 deepseek-v4-flash，与最近真实跑 risk 站一致）。

用法：
  .venv/bin/python scripts/c3_argument_blind_experiment.py \
      --run-dir output/analysis/vnext/20260731_002156 \
      --out-dir output/experiments/c3_argument_blind_20260815
"""

import argparse
import json
import shutil
from pathlib import Path

from agent_analysis.contracts import (
    LayerCard,
    RiskBoundaryReport,
    SynthesisPacket,
    ThesisDraft,
)
from agent_analysis.orchestrator import VNextOrchestrator
from agent_analysis.packet_builder import _model_dump

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_model(path: Path, model_cls):
    return model_cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_layer_cards(run_dir: Path):
    cards = []
    cards_dir = run_dir / "layer_cards"
    if cards_dir.exists():
        for path in sorted(cards_dir.glob("*.json")):
            cards.append(_load_model(path, LayerCard))
    return cards or None


def _build_seen_prompt_dir(exp_dir: Path) -> Path:
    """B 组提示词：同 A 组，只把论证盲两句话换成"看得到论点、仍交完整报告"。"""
    src = REPO_ROOT / "src" / "agent_analysis" / "prompts" / "risk_sentinel.md"
    prompt_dir = exp_dir / "prompts_seen"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    text = text.replace(
        "你的任务：不看论点论证，从输入的风险面（冲突清单 + 五层摘要 + 主要矛盾候选 + 证据读数）判断是否触发了五层框架的冲突矩阵、哪些风险边界必须保留，以及是否遗漏了过度谨慎、等待确认和假安全带来的风险。",
        "你的任务：你可以参考论点论证，但必须独立产出完整风险报告——判断是否触发了五层框架的冲突矩阵、哪些风险边界必须保留，以及是否遗漏了过度谨慎、等待确认和假安全带来的风险。",
    )
    text = text.replace(
        "**你拿不到论点论证（thesis 的任何段落与结构），这是刻意设计（论证盲），不得脑补一个论点出来攻击。**",
        "**你拿得到论点论证（governance_input 含 thesis_* 字段）；你的任务不变：产出完整风险报告，不设输出数量限制。**",
    )
    (prompt_dir / "risk_sentinel.md").write_text(text, encoding="utf-8")
    return prompt_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "output" / "experiments" / "c3_argument_blind_20260815"))
    parser.add_argument("--model", default="deepseek-v4-flash")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    synthesis = _load_model(run_dir / "synthesis_packet.json", SynthesisPacket)
    thesis = _load_model(run_dir / "thesis_draft.json", ThesisDraft)
    layer_cards = _load_layer_cards(run_dir)

    manifest = {
        "experiment": "c3_argument_blind_v1",
        "run_dir": str(run_dir),
        "model": args.model,
        "groups": {"A": "blind(consumer=risk)", "B": "seen(consumer=critic)"},
    }
    (out_dir / "experiment_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    orchestrator = VNextOrchestrator(available_models=[args.model], output_dir=str(out_dir))

    # A 组：论证盲（新生产口径）
    gov_risk = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        layer_cards=layer_cards,
        consumer="risk",
    )
    risk_a = orchestrator._run_and_save(
        stage_key="risk",
        stage_name="risk_blind_A",
        model_cls=RiskBoundaryReport,
        payload={"governance_input": _model_dump(gov_risk)},
        filename="risk_boundary_report_blind.json",
    )

    # B 组：读论证（critic 版包 + 同一份输出要求，不设"只找盲区"禁令）
    seen_prompts = _build_seen_prompt_dir(out_dir)
    orchestrator_seen = VNextOrchestrator(
        available_models=[args.model],
        output_dir=str(out_dir),
        prompts_dir=str(seen_prompts),
    )
    gov_critic = orchestrator_seen._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        layer_cards=layer_cards,
    )
    risk_b = orchestrator_seen._run_and_save(
        stage_key="risk",
        stage_name="risk_seen_B",
        model_cls=RiskBoundaryReport,
        payload={"governance_input": _model_dump(gov_critic)},
        filename="risk_boundary_report_seen.json",
    )

    summary = {
        "blind_must_preserve_risks": len(getattr(risk_a, "must_preserve_risks", []) or []),
        "seen_must_preserve_risks": len(getattr(risk_b, "must_preserve_risks", []) or []),
        "blind_failure_conditions": len(getattr(risk_a, "failure_conditions", []) or []),
        "seen_failure_conditions": len(getattr(risk_b, "failure_conditions", []) or []),
        "artifacts": {
            "blind": str(out_dir / "risk_boundary_report_blind.json"),
            "seen": str(out_dir / "risk_boundary_report_seen.json"),
            "diagnostics": str(out_dir / "llm_stage_diagnostics.json"),
        },
    }
    (out_dir / "experiment_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
