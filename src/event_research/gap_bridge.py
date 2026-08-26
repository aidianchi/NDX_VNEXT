# -*- coding: utf-8 -*-
"""缺口桥：出题官写好的研究任务书 → 事件层二档的巡逻候选题目。

T60 设计稿 3.1 节来源②（老板 2026-08-25 裁定建桥，2026-08-26 全盘重构）：
主链 run 收尾时由 src/main.py 调用一次。

货源（重构后唯一来源）：run_dir/research_topics.json —— 出题官
（topic_composer.py）从 IA 裁决残局酿成的任务书。重构前的三个旧货源
（底账 needs_data_confirmation / inquiry_messages adjudication_gap /
cross_layer_questions）经 08-26 真实 run 验证全是"家里数据能答"的内向题
（20 条候选被老板当场否决），已废除——内部对质钩子留在内部通道（IA 作答），
只有出题官判过"家里答不了、答案活在外部世界"的课题才进题库。

每条课题转成 source="gap" 的议程，初始状态 candidate（老板在控制台圈题后激活）。
去重靠 gap_ref=topic:<标题哈希>：同一课题跨 run 不重复入帐；已入帐过的一律跳过，
不问状态——老板关闭过的题不复活，做完的题不重来。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agenda import LEDGER_PATH, MATERIAL_CLASSES, append_agenda, load_ledger

_RESEARCH_TOPICS = "research_topics.json"


def _stable_text_ref(text: str) -> str:
    """topic_id 缺失时的兜底键：同一标题文本跨 run 得到同一键。"""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"topic:{digest}"


def _load_topics(path: Path) -> List[Dict[str, Any]]:
    """读 research_topics.json 的 topics 列表；文件不存在返回空（出题官未跑属正常）。"""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    topics = payload.get("topics") if isinstance(payload, dict) else None
    return [t for t in topics if isinstance(t, dict)] if isinstance(topics, list) else []


def harvest_gap_candidates(
    run_dir: Path,
    ledger_path: Path = LEDGER_PATH,
    budget_cap: Optional[int] = None,
) -> Dict[str, Any]:
    """把出题官的任务书转成候选议程，返回 harvesting 小结（进 run_summary）。

    幂等：同一 run 跑两遍、或不同 run 产出同一课题，第二遍全部记 skipped。
    budget_cap：候选议程的经费卡额度；None 用账本默认，同步巡逻场景由
    sync_patrol 传入日常档小额度。
    """
    run_dir = Path(run_dir)

    existing_refs = {
        str(record.get("gap_ref"))
        for record in load_ledger(ledger_path)
        if record.get("record_type") == "agenda" and record.get("gap_ref")
    }

    added: List[Dict[str, Any]] = []
    skipped = 0
    for topic in _load_topics(run_dir / _RESEARCH_TOPICS):
        title = str(topic.get("title") or "").strip()
        if not title:
            continue
        topic_id = str(topic.get("topic_id") or "").strip()
        if topic_id.startswith("topic:"):
            gap_ref = topic_id
        elif topic_id:
            gap_ref = f"topic:{topic_id}"
        else:
            gap_ref = _stable_text_ref(title)
        material_classes = [c for c in (topic.get("material_classes") or []) if c in MATERIAL_CLASSES] or ["③被相信的事"]
        brief = {k: topic.get(k) for k in ("why_now", "linked_contradiction", "known_at_home", "acceptance_criteria", "falsification") if topic.get(k)}
        if gap_ref in existing_refs:
            skipped += 1
            continue
        record = append_agenda(
            title,
            source="gap",
            material_classes=material_classes,
            budget_cap=budget_cap,
            ledger_path=ledger_path,
            gap_ref=gap_ref,
            topic_brief=brief,
        )
        existing_refs.add(gap_ref)
        added.append({"agenda_id": record["agenda_id"], "gap_ref": gap_ref})

    return {
        "status": "ok",
        "candidates_added": len(added),
        "skipped_duplicates": skipped,
        "by_source": {"research_topic": len(added)},
        "agendas": added,
    }
