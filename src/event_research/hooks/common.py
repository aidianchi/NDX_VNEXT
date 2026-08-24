# -*- coding: utf-8 -*-
"""dsh Python hooks 的公共件：stdin/stdout 协议与域名分档查询。

协议（dsh-hooks-claude-code 桥）：stdin 一行 JSON；exit 2 = block（stderr 为理由）；
exit 0 且 stdout 输出 JSON = 结构化决定（permissionDecision / additionalContext）；
exit 0 无输出 = 放行。
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

# hooks 以独立进程运行（cwd 是 session 工作区），自己把 repo 根放进 sys.path。
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

WHITELIST_PATH = REPO_ROOT / "config" / "event_source_whitelist.json"


def read_hook_payload() -> Dict[str, Any]:
    """读 stdin 的一行 JSON hook 载荷。读不到返回空 dict（放行姿态）。"""
    try:
        line = sys.stdin.readline()
        return json.loads(line) if line.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def emit_deny(reason: str) -> None:
    """PreToolUse 结构化 deny。"""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


def emit_additional_context(context: str) -> None:
    """PostToolUse 附加上下文（给模型贴来源分级标签）。"""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": context,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


def emit_block(reason: str) -> None:
    """硬停（exit 2，stderr 为理由）——经费卡耗尽的 pre-step 拒绝用这个。"""
    sys.stderr.write(reason)
    sys.exit(2)


def load_whitelist(path: Path = WHITELIST_PATH) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def domain_tier(url: str, whitelist: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """URL → 白名单档位（official/mainstream_finance/sell_side/social）；不在白名单返回 None。

    匹配规则：host == domain 或 host 以 '.'+domain 结尾。
    """
    wl = whitelist if whitelist is not None else load_whitelist()
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    for tier, domains in wl["tiers"].items():
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return tier
    return None


def is_https(url: str) -> bool:
    try:
        return urllib.parse.urlparse(url).scheme.lower() == "https"
    except ValueError:
        return False
