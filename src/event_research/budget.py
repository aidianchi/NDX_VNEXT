# -*- coding: utf-8 -*-
"""经费卡：每次调研一张 token 预算卡（三圈制度第二圈）。

设计（T60 3.2，老板 2026-08-24 拍板默认 3000 万 token）：
- 每次调用前查余额：dsh 的 Python hook（hooks/budget_gate.py）在 agent 每一步
  发请求前折叠 session 落盘日志里的 usage，超卡即硬停（pre-step reject，
  请求根本不发出去，超支不可能偷偷发生）。
- 耗尽即停、产出如实标"半成品"：硬停后已采材料照常落盘，run_summary 标注
  budget_exhausted=true。
- dsh 的 tokenMeter 语义是"当前请求的上下文压力"而非累计消耗，所以累计账
  由本模块自己 fold：遍历 assistant/message 事件的 usage 求和。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

# usage 求和口径：输入 + 输出 + 缓存读 + 缓存写（reasoningTokens 与 output
# 互斥口径见 dsh packages/llm/llm/src/types.ts，不重复计入）。
_USAGE_FIELDS = ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens")

BUDGET_STATE_FILENAME = "budget_state.json"


def fold_usage_from_transcript(transcript_path: Path) -> int:
    """从 session 落盘日志（纯 JSONL，compression: none）折叠累计 token 消耗。

    容忍半截行（日志可能正在写入）：坏行跳过。
    """
    spent = 0
    path = Path(transcript_path)
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "assistant/message":
                continue
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            usage = data.get("usage")
            if not isinstance(usage, dict):
                continue
            for field in _USAGE_FIELDS:
                value = usage.get(field)
                if isinstance(value, (int, float)):
                    spent += int(value)
    return spent


def check_budget(run_dir: Path, transcript_path: Path) -> Dict[str, Any]:
    """查余额：读 run_dir/budget.json 的卡面额度，fold 已花费，回写 budget_state.json。

    返回 {budget_cap, spent, remaining, exhausted}。budget.json 缺失视为无卡（报错由调用方定）。
    """
    run_dir = Path(run_dir)
    budget_file = run_dir / "budget.json"
    if not budget_file.exists():
        raise FileNotFoundError(f"经费卡缺失：{budget_file}")
    cap = json.loads(budget_file.read_text(encoding="utf-8"))["budget_cap"]
    spent = fold_usage_from_transcript(transcript_path)
    state = {
        "budget_cap": cap,
        "spent": spent,
        "remaining": cap - spent,
        "exhausted": spent >= cap,
    }
    (run_dir / BUDGET_STATE_FILENAME).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return state


def read_budget_state(run_dir: Path) -> Optional[Dict[str, Any]]:
    """读 hook 回写的预算状态（runner 用来判定是否预算耗尽的半成品）。"""
    state_file = Path(run_dir) / BUDGET_STATE_FILENAME
    if not state_file.exists():
        return None
    return json.loads(state_file.read_text(encoding="utf-8"))
