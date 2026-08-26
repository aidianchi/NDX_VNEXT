# -*- coding: utf-8 -*-
"""缺口桥：主链跑完留下的未解疑点 → 事件层二档的巡逻候选题目。

T60 设计稿 3.1 节来源②（老板 2026-08-25 裁定建桥）：规则早已定义
（底账 needs_data_confirmation 与 adjudication_gap → 议程候选，老板点头激活），
本模块是那座代码桥。主链 run 收尾时由 src/main.py 调用一次。

两个来源（严格按设计稿点名，不多收）：
- 底账 needs_data_confirmation：run_dir/event_mechanism_report.json 的
  event_research_cards[].needs_data_confirmation（已按主线聚合的待确认项）；
- adjudication_gap：run_dir/inquiry_messages.json 里
  message_type == "adjudication_gap" 的 InquiryMessage（Bridge 暴露的未解问题）。

每条疑点转成 source="gap" 的议程，初始状态 candidate（老板在报告里看到后激活，
设计稿 3.1：候选→老板激活，成熟后再议自动化）。

去重靠 gap_ref：同一疑点跨 run 不重复入帐——
底账条目用疑点文本哈希（ndc:<sha1 前 12 位>），adjudication_gap 用其稳定
message_id（inq:<message_id>，orchestrator 里 sha1 生成，同一问题跨 run 幂等）。
已入帐过的 gap_ref 一律跳过，不问状态：老板关闭过的题不复活，做完的题不重来。

桥只搬题不判题：泛化文本（如"来源是否可追溯"）不在此过滤，
候选的取舍是老板激活时的事（形式不得拒收内容）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .agenda import LEDGER_PATH, append_agenda, load_ledger

# 缺口候选的默认材料类：巡逻研究的是市场叙事，默认挂"③被相信的事"；
# 老板激活时如题目另有所指可改（agenda 契约要求非空，这里给一个合理默认）。
DEFAULT_GAP_MATERIAL_CLASSES = ["③被相信的事"]

_MECHANISM_REPORT = "event_mechanism_report.json"
_INQUIRY_MESSAGES = "inquiry_messages.json"


def _stable_text_ref(text: str) -> str:
    """ndc:<sha1 前 12 位>：同一疑点文本跨 run 得到同一键。"""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"ndc:{digest}"


def _load_json_list(path: Path, key: str) -> List[Dict[str, Any]]:
    """读 {key: [...]} 形状的 artifact；文件不存在返回空（事件层未开时属正常）。"""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    items = payload.get(key) if isinstance(payload, dict) else None
    return [it for it in items if isinstance(it, dict)] if isinstance(items, list) else []


def _collect_needs_data_confirmation(run_dir: Path) -> List[Tuple[str, str]]:
    """底账来源：返回 [(gap_ref, question), ...]，question 带主线标题作上下文。"""
    out: List[Tuple[str, str]] = []
    cards = _load_json_list(run_dir / _MECHANISM_REPORT, "event_research_cards")
    for card in cards:
        title = str(card.get("title") or "").strip()
        items = card.get("needs_data_confirmation")
        if not isinstance(items, list):
            continue
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            question = f"「{title}」待确认：{text}" if title else text
            out.append((_stable_text_ref(text), question))
    return out


def _collect_adjudication_gaps(run_dir: Path) -> List[Tuple[str, str]]:
    """adjudication_gap 来源：InquiryMessage 的 message_id 是稳定 sha1，直接作键。"""
    out: List[Tuple[str, str]] = []
    messages = _load_json_list(run_dir / _INQUIRY_MESSAGES, "messages")
    for msg in messages:
        if msg.get("message_type") != "adjudication_gap":
            continue
        question = str(msg.get("question") or "").strip()
        if not question:
            continue
        message_id = str(msg.get("message_id") or "").strip()
        gap_ref = f"inq:{message_id}" if message_id else _stable_text_ref(question)
        out.append((gap_ref, question))
    return out


def harvest_gap_candidates(
    run_dir: Path,
    ledger_path: Path = LEDGER_PATH,
    material_classes: Optional[List[str]] = None,
    budget_cap: Optional[int] = None,
) -> Dict[str, Any]:
    """把 run_dir 里的未解疑点转成候选议程，返回 harvesting 小结（进 run_summary）。

    幂等：同一 run 跑两遍、或不同 run 留下同一疑点，第二遍全部记 skipped。
    budget_cap：候选议程的经费卡额度；None 用账本默认（3000 万），同步巡逻
    场景由 sync_patrol 传入日常档小额度。
    """
    run_dir = Path(run_dir)
    classes = list(material_classes or DEFAULT_GAP_MATERIAL_CLASSES)

    existing_refs = {
        str(record.get("gap_ref"))
        for record in load_ledger(ledger_path)
        if record.get("record_type") == "agenda" and record.get("gap_ref")
    }

    sources = {
        "needs_data_confirmation": _collect_needs_data_confirmation(run_dir),
        "adjudication_gap": _collect_adjudication_gaps(run_dir),
    }

    added: List[Dict[str, Any]] = []
    skipped = 0
    seen_this_run = set()
    counts: Dict[str, int] = {}
    for source_kind, items in sources.items():
        kept = 0
        for gap_ref, question in items:
            if gap_ref in existing_refs or gap_ref in seen_this_run:
                skipped += 1
                continue
            record = append_agenda(
                question,
                source="gap",
                material_classes=classes,
                budget_cap=budget_cap,
                ledger_path=ledger_path,
                gap_ref=gap_ref,
            )
            seen_this_run.add(gap_ref)
            added.append({"agenda_id": record["agenda_id"], "gap_ref": gap_ref, "source_kind": source_kind})
            kept += 1
        counts[source_kind] = kept

    return {
        "status": "ok",
        "candidates_added": len(added),
        "skipped_duplicates": skipped,
        "by_source": counts,
        "agendas": added,
    }
