"""生造词黑名单：加载 config/coined_word_blacklist.json，对文本做精确命中扫描。

背景：L2 语言体检（research_fundamental/L2_language/defect_inventory.md 第一节）
从三份真实研报里查出 26 条生造词缺陷（典型如「零垫」）——没有公认定义、
系统自己生造的词。老板拍板建立黑名单机制：只登记已确认的生造词，报告装配时
精确匹配，防再犯不防初犯（新出现的生造词确认后补登进 JSON，不靠模糊匹配兜）。

本模块只做两件事：读名单、扫文本。接进报告器/流水线是后续阶段的活，这里不接。

匹配口径：子串包含即命中（``word in text``），不分词、不做模糊匹配；
返回按首次出现位置排序的去重命中词列表。重叠登记词（如「付清」与
「已大体付清」）在同一段文本里会各自命中，属于有意为之。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
BLACKLIST_PATH = REPO_ROOT / "config" / "coined_word_blacklist.json"


def load_blacklist(path: Union[str, Path] = BLACKLIST_PATH) -> List[str]:
    """读黑名单 JSON，返回登记词列表（按登记顺序）。

    名单是手工维护的登记册：空词或重复登记属于数据错误，直接报错，
    不静默放行。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    words = [entry["word"] for entry in data["words"]]
    if any(not word for word in words):
        raise ValueError("coined word blacklist contains empty entries")
    dupes = sorted({word for word in words if words.count(word) > 1})
    if dupes:
        raise ValueError(f"coined word blacklist has duplicate entries: {dupes}")
    return words


def scan_text(text: str, blacklist: Optional[Iterable[str]] = None) -> List[str]:
    """精确扫描 text，返回命中的黑名单词（去重，按首次出现位置排序）。"""
    words = list(blacklist) if blacklist is not None else load_blacklist()
    hits = [word for word in dict.fromkeys(words) if word and word in text]
    hits.sort(key=text.index)
    return hits
