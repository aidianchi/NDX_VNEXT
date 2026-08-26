# -*- coding: utf-8 -*-
"""对账器：每条"事实"必须有出生证（三圈制度第三圈，五项度量第 3 项）。

读 dsh 的 session 落盘日志（我们的组合固定 compression: none + packChunks: false，
逐行直白 JSONL），对每张材料卡的 source_pointer 做机器校验：
1. pointer 的 url 必须真实出现在日志的 web_fetch 抓取记录里；
2. pointer 的 quote 必须对得上该 url 的抓取原文——先空白归一化逐字子串匹配，
   对不上再做 3-gram 模糊匹配（相似度 ≥ 0.8 算对上。老板 2026-08-26 拍板：
   实测 12 张降级卡全是"差几个字"的真引文，相似度 0.83-0.97，逐字匹配误伤）；
3. 来源档位：sell_side/social 弱档不进正文 → 降级。

处理原则是降级标注不打回（"形式不得拒收内容"）：对不上的 fact 在
reconciliation 块里标注 downgraded 及原因码，下游（IA）按解读对待——
降级卡以"仅解读"身份进裁决视野，只是没有事实资格。
对账通过率 = verified / total，机器自动出数。

历史注：早期版本让模型在 pointer 里抄 30 位随机 call_id，实测模型会编造
以假乱真的编号（2026-08-24 第四期巡逻 0/4）——机械字段不出答卷，契约
改为模型只填 url+quote，绑定由代码做。
"""

from __future__ import annotations

import difflib
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


# 引文模糊匹配阈值（老板 2026-08-26 拍板）：真实降级数据相似度 0.83-0.97，
# 编造引文一般 < 0.5，0.8 把两者分开。
QUOTE_SIMILARITY_THRESHOLD = 0.8


def _shingles(text: str, n: int = 3) -> set:
    """字符 n-gram 集合；短文本退化为整串一个元素。"""
    if len(text) <= n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def quote_similarity(quote: str, text: str) -> float:
    """引文对原文的相似度：先 3-gram 锚点定位，再对锚点邻域做编辑距离比对。

    中文插几个字（"的""基本"）会打掉一串 3-gram，纯 shingle 包含率误伤；
    所以命中 shingle 只用来定位候选位置，真正打分交给该位置前后窗口的
    SequenceMatcher 编辑距离——插入/替换/截断都只扣很少的分数，
    而整句编造的引文连锚点都没有，直接 0 分。
    """
    nq = _normalize(quote)
    nt = _normalize(text)
    if not nq:
        return 0.0
    if nq in nt:
        return 1.0
    # 找锚点：引文的 shingle 在原文中的对齐位置（原文位置 - 引文位置）
    anchors = set()
    for i in range(0, max(1, len(nq) - 2), 3):
        shingle = nq[i : i + 3]
        start = nt.find(shingle)
        while start != -1:
            anchors.add(start - i)
            start = nt.find(shingle, start + 1)
    if not anchors:
        return 0.0
    margin = len(nq)  # 锚点可能在引文任何位置，窗口要盖住整个引文
    best = 0.0
    for anchor in anchors:
        lo = max(0, anchor - margin)
        window = nt[lo : anchor + len(nq) + margin]
        ratio = difflib.SequenceMatcher(None, nq, window, autojunk=False).ratio()
        # ratio = 2*M/(len(引文)+len(窗口))，窗口比引文长会稀释；
        # 折算成"引文被原文覆盖的比例" = M/len(引文)，插入多余字符只扣很少的分数。
        coverage = ratio * (len(nq) + len(window)) / (2 * len(nq))
        best = max(best, min(1.0, coverage))
    return best


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
    """对一张卡做"指回原文"校验，返回 reconciliation 块（不改写卡本身）。

    出生证按 url 解析（08-24 修订：模型只填 url+quote，代码对回抓取记录）：
    同一 url 可能被多次抓取，任一一次的原文命中引文即算对上。
    """
    pointer = card.get("source_pointer") if isinstance(card, dict) else None
    url = pointer.get("url").strip() if isinstance(pointer, dict) and isinstance(pointer.get("url"), str) else None
    quote = pointer.get("quote") if isinstance(pointer, dict) else None

    if not url:
        return {"status": STATUS_POINTER_MISSING, "detail": "source_pointer 缺 url"}

    matches = [c for c in tool_calls.values() if c["name"] == "web_fetch" and c["url"] == url]
    if not matches:
        return {"status": STATUS_POINTER_MISSING, "detail": f"该 url 未被抓取过：{url}"}

    best = max((quote_similarity(str(quote or ""), c["result_text"]) for c in matches), default=0.0)
    if best < QUOTE_SIMILARITY_THRESHOLD:
        return {
            "status": STATUS_QUOTE_NOT_FOUND,
            "detail": f"引文对不上该 url 的抓取原文（最高相似度 {best:.2f}，阈值 {QUOTE_SIMILARITY_THRESHOLD}）",
        }

    tier = domain_tier(url, whitelist)
    policy = _whitelist_policy(whitelist)
    if tier not in policy["body_allowed"]:
        return {
            "status": STATUS_WEAK_TIER if tier else STATUS_UNVERIFIED_SOURCE,
            "detail": f"来源档位 {tier or 'unverified'} 不进正文：{url}",
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
