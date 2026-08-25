# -*- coding: utf-8 -*-
"""runner：用 dsh 底盘跑一条二档议程，产出带对账通过率的材料卡。

流程：装经费卡（budget.json）→ 渲染 dsh 组合（cordis.yml + hooks.json，绝对路径）
→ 注入人设（persona.md 镣铐语义层 + 本次议程）→ 锁 deepseek-v4-flash 跑
→ 解析产出（```json 块：cards/leads/charter_feedback）→ 四条镣铐校验（复用原型）
→ 对账（source_pointer 指回 session 日志原文）→ 落盘 + 账本记 done。

落盘（run_dir = output/event_research/runs/<agenda_id>_<时间戳>/）：
- budget.json / budget_state.json：经费卡卡面与钩子的查账回写；
- cordis.yml / hooks.json：本次渲染的 dsh 组合；
- sessions/：dsh 落盘日志（纯文本 JSONL）；
- material_cards.jsonl：每张卡 + 镣铐校验结果 + reconciliation 块；
- narrative_state.json：层内结论块（框架坐标/结论/多空最强论据/改判条件/缺席信号/与上期差异）；
- brief.md：给老板看的金字塔简报（第一屏三行：变没变/本期判断/认错条件）；
- run_summary.json：对账通过率、一手率、判断数字核对（G7 黄灯标注）、预算。
  二档无发布闸门（老板 08-25 裁决）：一切机器校验都是标注层，随产物走。

G2 跟踪名单：议程带 tracking_key 时，runner 把同一 key 最近一次巡逻的 narrative_state
作为"上期坐标"注入 prompt，本期必须更新同一口径并写清差异——同口径时间序列由此而来。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.event_research import agenda as agenda_mod
from src.event_research.brief import render_brief
from src.event_research.budget import read_budget_state
from src.event_research.card import GOVERNANCE_NOTE, validate_research_card
from src.event_research.narrative_check import check_narrative_numbers
from src.event_research.reconcile import reconcile_cards

PACKAGE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = PACKAGE_DIR / "dsh_profile"
PERSONA_PATH = PACKAGE_DIR / "persona.md"
RUNS_ROOT = Path("output/event_research/runs")

MODEL = "deepseek-v4-flash"  # 锁 flash（日常真实跑只挂 flash 的口径）

_JSON_BLOCK_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL)


def _render_templates(run_dir: Path) -> None:
    python_bin = REPO_ROOT / ".venv" / "bin" / "python"
    hooks_dir = PACKAGE_DIR / "hooks"
    cordis = (PROFILE_DIR / "cordis.yml.tmpl").read_text(encoding="utf-8").replace(
        "{{HOOKS_JSON_PATH}}", str(run_dir / "hooks.json")
    )
    hooks = (PROFILE_DIR / "hooks.json.tmpl").read_text(encoding="utf-8").replace(
        "{{PYTHON}}", str(python_bin)
    ).replace("{{HOOKS_DIR}}", str(hooks_dir))
    (run_dir / "cordis.yml").write_text(cordis, encoding="utf-8")
    (run_dir / "hooks.json").write_text(hooks, encoding="utf-8")


def _build_persona(agenda: Dict[str, Any]) -> str:
    persona = PERSONA_PATH.read_text(encoding="utf-8")
    classes = "、".join(agenda["material_classes"])
    return (
        f"{persona}\n\n## 本次议程\n\n"
        f"- 议程 ID：{agenda['agenda_id']}\n"
        f"- 材料类别：{classes}\n"
        f"- 议程问题：{agenda['question']}\n"
    )


def find_previous_narrative(
    tracking_key: str, runs_root: Path = RUNS_ROOT
) -> Optional[Dict[str, Any]]:
    """G2 跟踪名单：找同一 tracking_key 最近一次巡逻的叙事坐标（上期值）。"""
    best: Optional[Dict[str, Any]] = None
    runs_root = Path(runs_root)
    if not runs_root.exists():
        return None
    for summary_path in runs_root.glob("*/run_summary.json"):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if summary.get("tracking_key") != tracking_key:
            continue
        narrative = summary.get("narrative_state")
        if not narrative:
            continue
        if best is None or summary_path.parent.name > best["run_name"]:
            best = {"run_name": summary_path.parent.name, "narrative_state": narrative}
    return best


def _build_prompt(agenda: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> str:
    """用户消息 = 议程问题 + 当前 UTC（机械字段代码喂，不许模型估）+（若追踪中）上期坐标。"""
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prompt = (
        f"当前 UTC 时间：{now_utc}（所有卡的 collected_at_utc 一律填这个值，不许自己估）。\n\n"
        + agenda["question"]
    )
    if previous:
        prompt += (
            f"\n\n## 上期坐标（{previous['run_name']}，同一追踪对象）\n\n"
            f"```json\n{json.dumps(previous['narrative_state'], ensure_ascii=False, indent=2)}\n```\n\n"
            "本期必须更新同一口径，并在 narrative_state.previous_position_delta 写清与上期相比什么变了。"
        )
    return prompt


_NARRATIVE_STATE_FIELDS = (
    "framework_position",
    "conclusion",
    "bull_strongest",
    "bear_strongest",
    "falsification",
    "absence_signals",
    "previous_position_delta",
)


def validate_narrative_state(payload: Optional[Dict[str, Any]]) -> List[str]:
    """层内结论块的机器校验：字段齐全且非空。返回错误码列表（空 = 通过）。"""
    if not payload or not isinstance(payload.get("narrative_state"), dict):
        return ["narrative_state_missing"]
    state = payload["narrative_state"]
    errors = []
    for field in _NARRATIVE_STATE_FIELDS:
        value = state.get(field)
        if field == "absence_signals":
            if not isinstance(value, list) or not value:
                errors.append("narrative_state_absence_signals_empty")
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"narrative_state_field_empty:{field}")
    for key in state.keys():
        if key not in _NARRATIVE_STATE_FIELDS:
            errors.append(f"narrative_state_unknown_field:{key}")
    return errors


def tier_distribution(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """G6 一手率：卡的来源档分布 + 一手率（official 档占比）。"""
    dist: Dict[str, int] = {}
    for card in cards:
        tier = str(card.get("source_tier") or "missing")
        dist[tier] = dist.get(tier, 0) + 1
    total = len(cards)
    return {
        "by_source_tier": dist,
        "first_hand_rate": (dist.get("official", 0) / total) if total else None,
    }


def parse_final_payload(final_response: str) -> Optional[Dict[str, Any]]:
    """从最终消息提取最后一个 ```json 块并解析。失败返回 None（收下原文，标不可发布）。"""
    blocks = _JSON_BLOCK_RE.findall(final_response or "")
    for block in reversed(blocks):
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "cards" in payload:
            return payload
    return None


def run_agenda(
    agenda_id: str,
    ledger_path: Path = agenda_mod.LEDGER_PATH,
    runs_root: Path = RUNS_ROOT,
) -> Dict[str, Any]:
    """跑一条 active 状态的议程，返回 run_summary dict（同时落盘）。"""
    agenda = agenda_mod.get_agenda(agenda_id, ledger_path)
    if agenda is None:
        raise KeyError(f"议程不存在：{agenda_id}")
    if agenda["status"] != "active":
        raise ValueError(f"议程 {agenda_id} 状态是 {agenda['status']}，只跑 active")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # 必须绝对路径：runtime 子进程的 cwd 就是 run_dir，相对 cordis 路径会解析错。
    run_dir = (Path(runs_root) / f"{agenda_id}_{stamp}").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "budget.json").write_text(
        json.dumps({"agenda_id": agenda_id, "budget_cap": agenda["budget_cap"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    _render_templates(run_dir)

    tracking_key = agenda.get("tracking_key")
    previous = find_previous_narrative(tracking_key, runs_root) if tracking_key else None

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    from deepseek_harness import DeepSeekHarness

    with DeepSeekHarness(
        model=MODEL,
        cordis=str(run_dir / "cordis.yml"),
        session_root=str(run_dir / "sessions"),
        cwd=str(run_dir),
        env={
            "DSH_TELEMETRY_DISABLED": "1",
            "DSH_SYSTEM_PROMPT": _build_persona(agenda),
        },
    ) as harness:
        result = harness.run(_build_prompt(agenda, previous))

    (run_dir / "final_response.md").write_text(result.final_response, encoding="utf-8")

    payload = parse_final_payload(result.final_response)
    parse_ok = payload is not None
    cards: List[Dict[str, Any]] = payload.get("cards", []) if payload else []
    for card in cards:
        if isinstance(card, dict):
            # 机械字段不出答卷：治理行是固定字符串，代码装配，不靠模型手写。
            card["governance_note"] = GOVERNANCE_NOTE
        card["validation_errors"] = validate_research_card(card)

    narrative_state = (payload or {}).get("narrative_state")
    narrative_errors = validate_narrative_state(payload)
    if narrative_state:
        (run_dir / "narrative_state.json").write_text(
            json.dumps(narrative_state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    reconciliation = reconcile_cards(cards, run_dir / "sessions")
    budget_state = read_budget_state(run_dir)
    budget_exhausted = bool(budget_state and budget_state.get("exhausted"))

    with (run_dir / "material_cards.jsonl").open("w", encoding="utf-8") as f:
        for card in reconciliation["cards"]:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")

    # G7：判断段数字核对（纯标注黄灯，不进发布闸门——老板 08-24：避免乱拦）。
    number_check = check_narrative_numbers(narrative_state, reconciliation["cards"])

    # 老板 08-25 裁决：二档撤发布闸门——"闸门既然乱拦就不要有，措辞细节不是
    # 逻辑错误或编造"。所有机器校验（镣铐/对账/数字核对/结论字段）都是**标注层**，
    # 随产物走，不存在"不可发布"状态；只有"预算耗尽=半成品"这类事实标注。
    cards_with_errors = sum(1 for c in reconciliation["cards"] if c["validation_errors"])
    cards_downgraded = reconciliation["total"] - reconciliation["verified"]
    run_summary = {
        "agenda_id": agenda_id,
        "tracking_key": tracking_key,
        "previous_run": previous["run_name"] if previous else None,
        "run_dir": str(run_dir),
        "model": MODEL,
        "finish_reason": result.finish_reason,
        "parse_ok": parse_ok,
        "narrative_state": narrative_state,
        "narrative_observations": narrative_errors,
        "cards_total": reconciliation["total"],
        "cards_verified": reconciliation["verified"],
        "cards_downgraded": cards_downgraded,
        "cards_with_shackle_labels": cards_with_errors,
        "reconcile_pass_rate": reconciliation["pass_rate"],
        "tier_distribution": tier_distribution(cards),
        "narrative_number_check": number_check,
        "budget": budget_state,
        "budget_exhausted": budget_exhausted,
        "leads": (payload or {}).get("leads", []),
        "charter_feedback": (payload or {}).get("charter_feedback"),
        "note": "本材料是第二层候选材料，判断以第一层数据为准；层内结论以事件层身份流向 IA 对质，不进数据主链。",
    }
    (run_dir / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "brief.md").write_text(
        render_brief(run_summary, reconciliation["cards"]), encoding="utf-8"
    )

    agenda_mod.append_status_change(
        agenda_id,
        "done",
        note=f"run_dir={run_dir}",
        ledger_path=ledger_path,
    )
    return run_summary


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="跑一条事件层二档议程（dsh 底盘）")
    parser.add_argument("--agenda-id", required=True, help="议程账本里的 agenda_id（须为 active）")
    args = parser.parse_args(argv)
    summary = run_agenda(args.agenda_id)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
