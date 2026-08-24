# -*- coding: utf-8 -*-
"""材料卡：沿用原型四条镣铐校验，加 source_pointer（对账出生证）。

四条镣铐（事实/解读分离、来源分级、时间戳、needs_data_confirmation）的机器校验
直接复用原型 `scripts/layer2_supplement_prototype/prototype_loop.validate_material_card`，
单点维护。本模块只做两件事：
1. 弹出扩展字段 source_pointer 后调用原型校验（原型对未知字段是拒绝姿态）；
2. 校验 source_pointer 形状（指回哪次抓取 call_id + 原文引文 quote）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from layer2_supplement_prototype.prototype_loop import (  # noqa: E402
    GOVERNANCE_NOTE,
    validate_material_card,
)

from src.event_research.hooks.common import domain_tier  # noqa: E402

POINTER_FIELDS = ("call_id", "quote")

# G4 可选字段（2026-08-24 老板批）：改判条件 + 最强反方一句话。可选不强制
# （防"形式拒收内容"），出现则必须是非空字符串。
OPTIONAL_CARD_FIELDS = ("falsification", "counter_one_liner")


def validate_research_card(card: Dict[str, Any], now_utc: Optional[datetime] = None) -> List[str]:
    """校验一张二档材料卡，返回机器可 grep 的错误码列表（空 = 通过）。

    在原型错误码之外新增：`source_pointer_missing`、`source_pointer_not_object`、
    `source_pointer_call_id_empty`、`source_pointer_quote_empty`、`source_pointer_unknown_field:x`、
    `optional_field_empty:falsification` / `optional_field_empty:counter_one_liner`。

    域名口径差异：原型校验器写死了 9 个官方域（`source_url_domain_not_allowed`），
    二档搜索腿的白名单是 config/event_source_whitelist.json 的分档名单（老板
    2026-08-24 拍板扩容）——URL 在新白名单内（任一档）时，原型这条错误码不适用，滤掉。
    """
    if not isinstance(card, dict):
        return ["card_not_object"]

    pointer = card.get("source_pointer")
    base_card = {
        k: v
        for k, v in card.items()
        if k != "source_pointer" and k not in OPTIONAL_CARD_FIELDS
    }
    errors = validate_material_card(base_card, now_utc=now_utc)
    for field in OPTIONAL_CARD_FIELDS:
        if field in card and (not isinstance(card[field], str) or not card[field].strip()):
            errors.append(f"optional_field_empty:{field}")
    source_url = card.get("source_url")
    if (
        "source_url_domain_not_allowed" in errors
        and isinstance(source_url, str)
        and domain_tier(source_url) is not None
    ):
        errors.remove("source_url_domain_not_allowed")

    if pointer is None:
        errors.append("source_pointer_missing")
    elif not isinstance(pointer, dict):
        errors.append("source_pointer_not_object")
    else:
        for key in pointer.keys():
            if key not in POINTER_FIELDS:
                errors.append(f"source_pointer_unknown_field:{key}")
        if not isinstance(pointer.get("call_id"), str) or not pointer["call_id"].strip():
            errors.append("source_pointer_call_id_empty")
        if not isinstance(pointer.get("quote"), str) or not pointer["quote"].strip():
            errors.append("source_pointer_quote_empty")
    return errors


__all__ = ["GOVERNANCE_NOTE", "POINTER_FIELDS", "validate_research_card", "validate_material_card"]
