# -*- coding: utf-8 -*-
"""G7 叙事层数字核对（2026-08-24 老板批的省版）。

原则（老板原话要点）：AI 的注意力放在研究本身，绝不让它做抄写/套格式的蠢事
——所以不让模型多写一个字，由代码事后核对：判断段落里出现的每个带单位数字，
必须能在本次巡逻的证据卡里找到同一个数（单位归一后等值）。找不到 → 标
"ungrounded_number"（黄灯标注，**不拦截发布**——先跑一段时间证明不误判，
再议是否升级红灯；老板 08-24 明确"代码容易误判，一定要避免乱拦"）。

只认带单位的数字（金额/百分比/基点）——年份、日期、期数这类裸数字不查，
查了必乱拦。单位换算是确定性算术（$1B=10亿，$1T=1万亿，100bp=1%），
不判意思；跨币种（美元/人民币）不做换算，各算各的——宁可漏报不可误判。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# 数字+单位：$500B / 2200亿 / 1.5万亿美元 / 39.4% / 90bp / $4.1万亿
_NUMBER_RE = re.compile(
    r"(?P<cur_pre>\$)?(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>万亿|亿|万|B|M|T|bp|%|％)\s*(?P<cur_post>美元|美金|元)?"
)

# 金额档 → 以"亿"为基准的倍率
_MAGNITUDE = {"万": 0.0001, "亿": 1.0, "万亿": 10000.0, "M": 0.01, "B": 10.0, "T": 10000.0}

# 判断段的哪些字段要查
_NARRATIVE_TEXT_FIELDS = (
    "framework_position",
    "conclusion",
    "bull_strongest",
    "bear_strongest",
    "falsification",
    "previous_position_delta",
)

# 证据卡里作为核对底的文本字段
_CARD_TEXT_FIELDS = ("fact_summary", "interpretation", "limitations", "needs_data_confirmation")

_CARD_REF_RE = re.compile(r"\bc(\d+)\b")


def _extract_numbers(text: str) -> List[Tuple[float, str, str]]:
    """从文本提取 (归一值, 口径, 原文片段)。口径：currency / percent。"""
    found = []
    for m in _NUMBER_RE.finditer(text or ""):
        raw_value = m.group("value").replace(",", "")
        try:
            value = float(raw_value)
        except ValueError:
            continue
        unit = m.group("unit")
        if unit in ("%", "％"):
            found.append((round(value, 4), "percent", m.group(0)))
        elif unit == "bp":
            found.append((round(value / 100.0, 4), "percent", m.group(0)))
        else:
            factor = _MAGNITUDE[unit]
            # 带币种标记（$ / 美元 / 美金）记为 currency_usd，裸记 currency
            kind = "currency_usd" if (m.group("cur_pre") or m.group("cur_post") in ("美元", "美金")) else "currency"
            found.append((round(value * factor, 4), kind, m.group(0)))
    return found


def _card_texts(cards: List[Dict[str, Any]]) -> str:
    parts = []
    for card in cards:
        for field in _CARD_TEXT_FIELDS:
            value = card.get(field)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(v) for v in value)
        pointer = card.get("source_pointer")
        if isinstance(pointer, dict) and isinstance(pointer.get("quote"), str):
            parts.append(pointer["quote"])
    return "\n".join(parts)


def check_narrative_numbers(
    narrative_state: Optional[Dict[str, Any]],
    cards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """核对判断段的数字是否都能在证据卡里找到。返回核对报告（纯标注，不拦截）。

    报告字段：
    - checked：查了多少个数字；
    - ungrounded：找不到依据的数字清单（字段 + 原文片段）；
    - card_refs：判断里引用了哪些卡（c1/c2 形态）；
    - anchored：判断是否至少挂了一张卡（一张没挂 = 判断无锚，同样只是标注）。
    """
    if not isinstance(narrative_state, dict):
        return {"checked": 0, "ungrounded": [], "card_refs": [], "anchored": False}

    card_text = _card_texts(cards)
    grounded = {(v, k) for v, k, _ in _extract_numbers(card_text)}
    # 裸记 currency 与 currency_usd 互通（同域默认美元口径，宁可漏报）
    loose_grounded = {(v, "currency") for v, k in grounded if k.startswith("currency")} | {
        (v, "currency_usd") for v, k in grounded if k.startswith("currency")
    }
    grounded |= loose_grounded

    checked = 0
    ungrounded: List[Dict[str, str]] = []
    card_refs: set = set()
    for field in _NARRATIVE_TEXT_FIELDS:
        value = narrative_state.get(field)
        if not isinstance(value, str):
            continue
        card_refs.update(f"c{n}" for n in _CARD_REF_RE.findall(value))
        for num, kind, raw in _extract_numbers(value):
            checked += 1
            if (num, kind) not in grounded:
                ungrounded.append({"field": field, "text": raw, "normalized": f"{num}|{kind}"})

    return {
        "checked": checked,
        "ungrounded": ungrounded,
        "card_refs": sorted(card_refs),
        "anchored": bool(card_refs),
    }
