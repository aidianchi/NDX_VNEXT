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
- run_summary.json：对账通过率、预算是否耗尽、解析是否成功、发布闸门标记。
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
from src.event_research.budget import read_budget_state
from src.event_research.card import validate_research_card
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
        result = harness.run(agenda["question"])

    (run_dir / "final_response.md").write_text(result.final_response, encoding="utf-8")

    payload = parse_final_payload(result.final_response)
    parse_ok = payload is not None
    cards: List[Dict[str, Any]] = payload.get("cards", []) if payload else []
    for card in cards:
        card["validation_errors"] = validate_research_card(card)

    reconciliation = reconcile_cards(cards, run_dir / "sessions")
    budget_state = read_budget_state(run_dir)
    budget_exhausted = bool(budget_state and budget_state.get("exhausted"))

    with (run_dir / "material_cards.jsonl").open("w", encoding="utf-8") as f:
        for card in reconciliation["cards"]:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")

    # 发布闸门：解析失败 / 镣铐不过 / 预算耗尽半成品 → 不可作发布依据。
    shackles_failed = any(c["validation_errors"] for c in reconciliation["cards"])
    publishable = parse_ok and not shackles_failed and not budget_exhausted
    run_summary = {
        "agenda_id": agenda_id,
        "run_dir": str(run_dir),
        "model": MODEL,
        "finish_reason": result.finish_reason,
        "parse_ok": parse_ok,
        "cards_total": reconciliation["total"],
        "cards_verified": reconciliation["verified"],
        "reconcile_pass_rate": reconciliation["pass_rate"],
        "shackles_failed": shackles_failed,
        "budget": budget_state,
        "budget_exhausted": budget_exhausted,
        "publishable": publishable,
        "unpublishable_reason": (
            None
            if publishable
            else "budget_exhausted"
            if budget_exhausted
            else "parse_failed"
            if not parse_ok
            else "shackles_failed"
        ),
        "leads": (payload or {}).get("leads", []),
        "charter_feedback": (payload or {}).get("charter_feedback"),
        "note": "本材料是第二层候选材料，判断以第一层数据为准；产出流向 IA，不进数据主链。",
    }
    (run_dir / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    agenda_mod.append_status_change(
        agenda_id,
        "done",
        note=f"run_dir={run_dir} publishable={publishable}",
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
