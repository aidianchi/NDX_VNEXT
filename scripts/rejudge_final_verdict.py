#!/usr/bin/env python
"""首考素材离线重判（改写后的真实生产提示词，2026-09-24）。

老板批准的验证路径：说明书与字段说明改写后，不重跑整条流水线，而是拿首考
run 20260923_193318 prompt_audit 里归档的 final 站真实输入 payload，走
`_run_final_adjudicator_stage` 完整生产路径——新说明书 + 新字段规格（contracts.py）
+ 同一份输入 + 同一套运行时校验（引用存在性、正文数字 token 比对、冲突回应核对）
+ 同一套重试与降级逻辑。产物的 reasoned_verdict 拿去对照老板的批改清单逐条核对。

用法：
  .venv/bin/python scripts/rejudge_final_verdict.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agent_analysis.contracts import AnalysisRevised, SynthesisPacket  # noqa: E402
from agent_analysis.orchestrator import VNextOrchestrator  # noqa: E402

RUN_DIR = REPO_ROOT / "output" / "analysis" / "vnext" / "20260923_193318"
OUT_DIR = REPO_ROOT / "output" / "experiments" / (sys.argv[1] if len(sys.argv) > 1 else "verdict_rejudge_20260924")


def main() -> int:
    archived = json.loads(
        (RUN_DIR / "prompt_audit" / "final_adjudicator" / "attempt_1.payload.json").read_text(encoding="utf-8")
    )
    payload = archived["payload"]
    final_source_text = json.dumps(payload, ensure_ascii=False, default=str)
    synthesis_packet = SynthesisPacket.model_validate(
        json.loads((RUN_DIR / "synthesis_packet.json").read_text(encoding="utf-8"))
    )
    analysis_revised = AnalysisRevised.model_validate(
        json.loads((RUN_DIR / "analysis_revised.json").read_text(encoding="utf-8"))
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    orchestrator = VNextOrchestrator(
        available_models=["deepseek-v4-flash"],
        output_dir=str(OUT_DIR),
    )
    final = orchestrator._run_final_adjudicator_stage(
        final_payload=payload,
        synthesis_packet=synthesis_packet,
        analysis_revised=analysis_revised,
        final_source_text=final_source_text,
    )

    out_path = OUT_DIR / "final_adjudication_rejudged.json"
    out_path.write_text(final.model_dump_json(indent=2), encoding="utf-8")
    print(f"重判完成 -> {out_path}")
    print(f"approval_status={final.approval_status} confidence={final.confidence} stance_label={final.stance_label}")
    print(f"reasoned_verdict 字数: {len(final.reasoned_verdict)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
