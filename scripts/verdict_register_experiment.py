#!/usr/bin/env python
"""判决书"要求过载 vs 负面清单"对照实验（2026-09-23）。

起因：首考 run 20260923_193318 的判决正文（reasoned_verdict）被老板判定"不像研报"——
正文里满是说明书命令的复述（"第一条主要理由是""等待确认的代价要两面写"）。
老板质疑"负面清单+示范段"未必是症结。本实验用同一份已定稿判断材料跑两臂：

  A 组（已存在）：生产链路的 reasoned_verdict——终审说明书（约 15 条并行要求）的产物。
  B 组 minimal ：极简提示词——只交代身份、材料、读者，零格式要求、零清单。
  C 组 minimal+禁令：B 组加一条负面清单（禁用"主要理由/最强反对/改主意"路标词）。

若 B 明显好于 A → 病因是"要求过载"，负面清单是同类病；
若 B 仍然脚手架/缩句 → 病因更深（体裁模板贫瘠），示范段才有讨论价值；
若 C 明显好于 B → 负面清单有效，老板质疑可被证据部分驳回。

用法：
  .venv/bin/python scripts/verdict_register_experiment.py \
      --run-dir output/analysis/vnext/20260923_193318
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agent_analysis.llm_engine import LLMEngine  # noqa: E402

# 写给读者的判断素材：只留已定稿的判断内容，剔除内部闸门与审计字段
# （quality_gate / claim_ledger / adjudicator_notes 等是判官的内部账，不是文章素材）。
KEEP_KEYS = (
    "final_stance",
    "stance_label",
    "confidence",
    "reader_final",
    "state_diagnosis",
    "priced_narrative",
    "payoff_assessment",
    "key_support_chains",
    "must_preserve_risks",
    "confirmation_cost",
    "invalidation_conditions",
    "time_horizon_views",
    "portfolio_actions",
    "long_term_assessment",
    "principal_contradiction",
    "secondary_contradictions",
    "price_reflection_map",
)

BASE_PROMPT = """你是一家顶级投资机构的首席策略师，负责为本机构的旗舰研报撰写判决书正文。

下面这份 JSON 是本机构研究体系本轮对纳斯达克 100 指数的全部已定稿判断（数据截至 2026-09-21）：最终立场、主要理由、风险清单、分时间尺度的判断、三类资金的动作、改判条件、长期资产评估，都已经在里面写定。

你的读者是这份研报的订阅者：他持有纳斯达克 100 的核心仓位，每期只愿意花大约十分钟读这份判决书。他读完你的正文，应当拿到本期的全部精华——现在是什么判断、凭什么这么判断、什么情况下这个判断会改变。

你可以使用 JSON 里的任何数字与事实，但读者看不到这份 JSON，他只看你写的正文。
"""

NEGATIVE_LIST_CLAUSE = """
另外有一条禁令：正文里不许出现"主要理由""最强反对""改主意"这类路标词——理由、反对意见、改判条件都直接以判断句陈述，不设路标。
"""

JSON_HEADER = "\nJSON 如下：\n```json\n"
JSON_FOOTER = "\n```\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "output" / "experiments" / "verdict_register_20260923"))
    parser.add_argument("--model", default="deepseek-v4-flash")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    adjudication = json.loads((run_dir / "final_adjudication.json").read_text(encoding="utf-8"))
    materials = {key: adjudication[key] for key in KEEP_KEYS if key in adjudication}
    materials_json = json.dumps(materials, ensure_ascii=False, indent=1)
    (out_dir / "materials_pruned.json").write_text(materials_json, encoding="utf-8")

    arms = {
        "B_minimal": BASE_PROMPT,
        "C_minimal_plus_negative_list": BASE_PROMPT + NEGATIVE_LIST_CLAUSE,
    }
    manifest = {"experiment": "verdict_register_overload_v1", "run_dir": str(run_dir), "model": args.model, "arms": {}}

    engine = LLMEngine(available_models=[args.model])
    for arm_name, prompt_body in arms.items():
        prompt = prompt_body + JSON_HEADER + materials_json + JSON_FOOTER
        (out_dir / f"prompt_{arm_name}.txt").write_text(prompt, encoding="utf-8")
        result = engine.call_with_fallback(prompt, stage_name=f"experiment_{arm_name}")
        if not result:
            manifest["arms"][arm_name] = {"status": "failed"}
            print(f"[{arm_name}] 调用失败")
            continue
        (out_dir / f"verdict_{arm_name}.txt").write_text(result, encoding="utf-8")
        manifest["arms"][arm_name] = {"status": "ok", "chars": len(result)}
        print(f"[{arm_name}] 完成，{len(result)} 字 -> {out_dir / f'verdict_{arm_name}.txt'}")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
