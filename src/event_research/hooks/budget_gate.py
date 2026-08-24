# -*- coding: utf-8 -*-
"""经费卡闸（UserPromptSubmit → agent/pre-step 卡口）。

dsh 每发一次模型请求前经过这里：折叠 session 日志的累计 token 消耗，
达到经费卡额度即 exit 2 硬停（请求不发出去）。状态回写 run 目录的
budget_state.json，供 runner 判定"预算耗尽的半成品"。

hook 进程 cwd = session 工作区（runner 设为 run 目录），经费卡在 cwd/budget.json。
"""

from __future__ import annotations

import sys
from pathlib import Path

from common import REPO_ROOT, read_hook_payload  # noqa: F401  (sys.path 副作用)

from src.event_research.budget import check_budget


def main() -> None:
    payload = read_hook_payload()
    transcript = payload.get("transcript_path")
    run_dir = Path(payload.get("cwd") or ".")
    try:
        state = check_budget(run_dir, Path(transcript) if transcript else run_dir / "no_transcript")
    except FileNotFoundError:
        # 经费卡缺失 = 配置错误，宁可放行也不误判；runner 落盘时会发现缺卡。
        return
    if state["exhausted"]:
        from common import emit_block

        emit_block(
            f"经费卡耗尽：已花 {state['spent']} token，卡面 {state['budget_cap']}。"
            "停止继续调用；请把已采材料按'预算耗尽的半成品'如实收尾。"
        )


if __name__ == "__main__":
    main()
    sys.exit(0)
