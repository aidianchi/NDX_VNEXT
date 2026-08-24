# -*- coding: utf-8 -*-
"""议程账本：事件层二档的出题口（三圈制度第一圈）。

账本文件 `output/state_ledger/event_agenda.jsonl`，只追加不改写。
每条议程 = {record_type, agenda_id, source, question, material_classes,
budget_cap, status, created_at}；状态变更以 status_change 记录追加，编号永不复用。

三个来源（T60 设计稿 3.1，老板 2026-08-24 拍板）：
- charter：宪章常备巡逻职责 → 命题即 active；
- gap：底账 needs_data_confirmation / IA adjudication_gap → 候选 candidate，老板激活；
- boss：老板临时命题 → 命题即 active。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# 老板 2026-08-24 拍板：经费卡默认额度 3000 万 token。
DEFAULT_BUDGET_CAP = 30_000_000

LEDGER_PATH = Path("output/state_ledger/event_agenda.jsonl")

SOURCE_VALUES = ("charter", "gap", "boss")
# candidate=候选（待老板激活） active=已激活 done=已完成 closed=关闭（不再做）
STATUS_VALUES = ("candidate", "active", "done", "closed")

MATERIAL_CLASSES = (
    "①已发生的事",
    "②将发生的事",
    "③被相信的事",
    "④规则语境",
    "⑤历史语境",
)

# gap 来源的初始状态是候选（老板 2026-08-24 拍板：候选→老板激活）；
# charter / boss 命题即激活。
_INITIAL_STATUS = {"charter": "active", "gap": "candidate", "boss": "active"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_agenda_id() -> str:
    """EV-<yyyymmdd>-<6位随机>；随机段保证永不复用。"""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"EV-{day}-{uuid.uuid4().hex[:6]}"


def append_agenda(
    question: str,
    source: str,
    material_classes: List[str],
    budget_cap: Optional[int] = None,
    ledger_path: Path = LEDGER_PATH,
) -> Dict[str, Any]:
    """追加一条新议程，返回写入的记录。source 决定初始状态。"""
    if source not in SOURCE_VALUES:
        raise ValueError(f"source 必须是 {SOURCE_VALUES} 之一，收到 {source!r}")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question 不能为空")
    if not material_classes or not all(c in MATERIAL_CLASSES for c in material_classes):
        raise ValueError(f"material_classes 必须非空且每项属于 {MATERIAL_CLASSES}")
    cap = DEFAULT_BUDGET_CAP if budget_cap is None else int(budget_cap)
    if cap <= 0:
        raise ValueError("budget_cap 必须是正整数")

    record = {
        "record_type": "agenda",
        "agenda_id": _new_agenda_id(),
        "source": source,
        "question": question.strip(),
        "material_classes": list(material_classes),
        "budget_cap": cap,
        "status": _INITIAL_STATUS[source],
        "created_at": _utc_now_iso(),
    }
    _append_record(record, ledger_path)
    return record


def append_status_change(
    agenda_id: str,
    new_status: str,
    note: str = "",
    ledger_path: Path = LEDGER_PATH,
) -> Dict[str, Any]:
    """追加一条状态变更（激活候选、标记完成/关闭）。"""
    if new_status not in STATUS_VALUES:
        raise ValueError(f"new_status 必须是 {STATUS_VALUES} 之一，收到 {new_status!r}")
    record = {
        "record_type": "status_change",
        "agenda_id": agenda_id,
        "new_status": new_status,
        "note": note,
        "created_at": _utc_now_iso(),
    }
    _append_record(record, ledger_path)
    return record


def _append_record(record: Dict[str, Any], ledger_path: Path) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_ledger(ledger_path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    """读全部记录（原始顺序）。文件不存在返回空列表。"""
    if not ledger_path.exists():
        return []
    records = []
    with ledger_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def current_agendas(ledger_path: Path = LEDGER_PATH) -> Dict[str, Dict[str, Any]]:
    """折叠账本 → {agenda_id: 最新状态的议程}。status_change 覆盖 status。"""
    agendas: Dict[str, Dict[str, Any]] = {}
    for record in load_ledger(ledger_path):
        if record.get("record_type") == "agenda":
            agendas[record["agenda_id"]] = dict(record)
        elif record.get("record_type") == "status_change":
            target = agendas.get(record["agenda_id"])
            if target is not None:
                target["status"] = record["new_status"]
                if record.get("note"):
                    target.setdefault("status_notes", []).append(record["note"])
    return agendas


def get_agenda(agenda_id: str, ledger_path: Path = LEDGER_PATH) -> Optional[Dict[str, Any]]:
    return current_agendas(ledger_path).get(agenda_id)
