"""生造词黑名单的红灯测试。

守住三件事：
1. 名单能加载：config/coined_word_blacklist.json 每条登记都带
   word/source/registered 三件套，无空词、无重复词。
2. 已知生造词必须命中（「零垫」「对冲腿」「放榜」等清单原文照录的词）。
3. 正常研报句子零命中——精确匹配不得误伤「安全垫」「缓冲」这类正常用词。
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.coined_word_blacklist import BLACKLIST_PATH, load_blacklist, scan_text


def test_blacklist_file_loads_with_sources() -> None:
    data = json.loads(BLACKLIST_PATH.read_text(encoding="utf-8"))
    entries = data["words"]
    # 缺陷清单第一节共 26 条，含「甲 / 乙」变体拆分后登记数只会更多。
    assert len(entries) >= 26
    for entry in entries:
        assert entry["word"].strip()
        assert "缺陷" in entry["source"]
        assert entry["registered"] == "2026-09-22"
    words = [entry["word"] for entry in entries]
    assert len(words) == len(set(words))


def test_load_blacklist_returns_registered_words() -> None:
    words = load_blacklist()
    assert "零垫" in words
    assert "对冲腿" in words
    assert "放榜" in words


def test_scan_hits_known_coined_words() -> None:
    text = "它直接决定核心仓赔率（零垫意味着错误定价无缓冲）与战术仓触发"
    assert scan_text(text) == ["零垫"]
    hits = scan_text("盈利引擎是唯一在转的对冲腿，10-22起陆续放榜")
    assert hits == ["对冲腿", "放榜"]


def test_scan_dedupes_and_orders_by_first_occurrence() -> None:
    hits = scan_text("放榜之后再谈零垫，零垫结构下不抗单")
    assert hits == ["放榜", "零垫", "不抗单"]


def test_normal_report_sentences_have_zero_hits() -> None:
    sentences = [
        "指数较200日均线高出9.3%，盈利上修仍在继续，但利率处在十年高位，风险补偿偏薄。",
        "核心仓位可以继续持有，新增资金等待利差与盈利广度的确认信号。",
        "如果实际利率继续上行，估值倍数会进一步承压，届时需要降低仓位。",
        "安全垫仍然充足，折现率回落给了估值缓冲。",
    ]
    for sentence in sentences:
        assert scan_text(sentence) == [], sentence


def test_scan_with_custom_blacklist() -> None:
    assert scan_text("这里混进一个测试词甲", blacklist=["测试词甲"]) == ["测试词甲"]
    assert scan_text("正常文本", blacklist=["测试词甲"]) == []
