# -*- coding: utf-8 -*-
"""对账器：每条"事实"必须有出生证（三圈制度第三圈，五项度量第 3 项）。

读 dsh 的 session 落盘日志（我们的组合固定 compression: none + packChunks: false，
逐行直白 JSONL），对每张材料卡的 source_pointer 做机器校验：
1. pointer 的 call_id 必须真实存在于日志的 tool/call；
2. pointer 的 quote 必须逐字出现在该次 tool/result 的原文里（空白归一化后子串匹配）；
3. 来源档位：sell_side/social 弱档不进正文 → 降级；web_search 结果等无法定档的
   一律 unverified → 降级。

处理原则是降级标注不打回（"形式不得拒收内容"）：对不上的 fact 在
reconciliation 块里标注 downgraded 及原因码，下游（IA）须按解读对待。
对账通过率 = verified / total，机器自动出数。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.event_research.hooks.common import domain_tier

# 对账状态码（机器可 grep）。
STATUS_VERIFIED = "verified"
STATUS_POINTER_MISSING = "downgraded_pointer_missing"  # call_id 在日志里不存在
STATUS_QUOTE_NOT_FOUND = "downgraded_quote_not_found"  # 引文对不上原文
STATUS_WEAK_TIER = "downgraded_weak_tier"  # 弱档来源进了正文
STATUS_UNVERIFIED_SOURCE = "downgraded_source_unverified"  # 无法定档（如 web_search 结果）

BODY_ALLOWED_TIERS = ("official", "official_disclosure", "transcript", "mainstream_finance")
_TIER_TO_SOURCE_TIER = {
    "official": "official",
    "official_disclosure": "official",
    "transcript": "primary_news",
    "mainstream_finance": "primary_news",
    "sell_side": "aggregator_news",
    "social": "weak_social",
}


def _whitelist_policy(whitelist: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """档位口径以 config/event_source_whitelist.json 为准（单点维护）；
    调用方传入小 dict 做测试时回退到本模块常量。"""
    if whitelist and "_body_allowed_tiers" in whitelist:
        return {
            "body_allowed": tuple(whitelist["_body_allowed_tiers"]),
            "tier_map": whitelist.get("_tier_to_source_tier") or _TIER_TO_SOURCE_TIER,
        }
    return {"body_allowed": BODY_ALLOWED_TIERS, "tier_map": _TIER_TO_SOURCE_TIER}


def find_session_logs(session_root: Path) -> List[Path]:
    """session_root 下全部 session.jsonl（我们的组合写纯文本 JSONL）。"""
    return sorted(Path(session_root).glob("**/session.jsonl"))


def load_session_events(session_log: Path) -> List[Dict[str, Any]]:
    events = []
    with Path(session_log).open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 容忍半截行
    return events


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _result_text(message: Any) -> str:
    """ToolResultMessage → 纯文本。

    实测形状（0.1.1rc1）：message.content = [{"type": "tool-result",
    "toolCallId": ..., "content": [{"type": "text", "text": ...}]}]——文本在
    tool-result 块的嵌套 content 里。兼容纯 text 块与字符串两种退化形态。
    """
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    def _walk(blocks: Any) -> str:
        if not isinstance(blocks, list):
            return ""
        parts = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(_walk(block.get("content")))
        return "".join(parts)

    return _walk(content)


def index_tool_calls(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """call_id → {name, url, result_text}。tool/call 与 tool/result 按 callId 配对。"""
    calls: Dict[str, Dict[str, Any]] = {}
    for event in events:
        if event.get("type") != "tool/call":
            continue
        data = event.get("data") or {}
        call_id = data.get("callId")
        if not call_id:
            continue
        url = ""
        arguments = data.get("arguments")
        if isinstance(arguments, str):
            try:
                url = str(json.loads(arguments).get("url") or "")
            except json.JSONDecodeError:
                pass
        elif isinstance(arguments, dict):
            url = str(arguments.get("url") or "")
        calls[call_id] = {"name": data.get("name"), "url": url, "result_text": ""}
    for event in events:
        if event.get("type") != "tool/result":
            continue
        data = event.get("data") or {}
        message = data.get("message") or {}
        call_id = data.get("callId")
        if not call_id and isinstance(message, dict):
            source = message.get("source")
            if isinstance(source, dict):
                call_id = source.get("callId")
            if not call_id:
                content = message.get("content")
                if isinstance(content, list) and content and isinstance(content[0], dict):
                    call_id = content[0].get("toolCallId")
        if call_id in calls:
            calls[call_id]["result_text"] = _result_text(message)
    return calls


def reconcile_card(
    card: Dict[str, Any],
    tool_calls: Dict[str, Dict[str, Any]],
    whitelist: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对一张卡做"指回原文"校验，返回 reconciliation 块（不改写卡本身）。"""
    pointer = card.get("source_pointer") if isinstance(card, dict) else None
    call_id = pointer.get("call_id") if isinstance(pointer, dict) else None
    quote = pointer.get("quote") if isinstance(pointer, dict) else None

    call = tool_calls.get(call_id or "")
    if call is None:
        return {"status": STATUS_POINTER_MISSING, "detail": f"call_id 不存在：{call_id}"}

    if call["name"] != "web_fetch":
        return {
            "status": STATUS_UNVERIFIED_SOURCE,
            "detail": f"pointer 指向 {call['name']}（非 web_fetch），无法定档",
        }

    if not quote or _normalize(str(quote)) not in _normalize(call["result_text"]):
        return {"status": STATUS_QUOTE_NOT_FOUND, "detail": "引文未在该次抓取原文中找到"}

    tier = domain_tier(call["url"], whitelist)
    policy = _whitelist_policy(whitelist)
    if tier not in policy["body_allowed"]:
        return {
            "status": STATUS_WEAK_TIER if tier else STATUS_UNVERIFIED_SOURCE,
            "detail": f"来源档位 {tier or 'unverified'} 不进正文：{call['url']}",
        }

    return {"status": STATUS_VERIFIED, "source_tier_expected": policy["tier_map"][tier]}


def reconcile_cards(
    cards: List[Dict[str, Any]],
    session_root: Path,
    whitelist: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对一批卡对账，返回 {cards(带 reconciliation), pass_rate, verified, total}。"""
    tool_calls: Dict[str, Dict[str, Any]] = {}
    for log in find_session_logs(session_root):
        tool_calls.update(index_tool_calls(load_session_events(log)))

    results = []
    verified = 0
    for card in cards:
        reconciliation = reconcile_card(card, tool_calls, whitelist)
        if reconciliation["status"] == STATUS_VERIFIED:
            verified += 1
        results.append({**card, "reconciliation": reconciliation})
    total = len(cards)
    return {
        "cards": results,
        "verified": verified,
        "total": total,
        "pass_rate": (verified / total) if total else None,
    }
