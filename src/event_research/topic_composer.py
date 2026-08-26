# -*- coding: utf-8 -*-
"""出题官：把综合裁决后的残局酿成 0-2 份研究任务书（老板 2026-08-26 全盘重构裁决）。

背景教训：第一版缺口桥把三个"内部对质钩子"（needs_data_confirmation /
cross_layer_questions / adjudication_gap）直接搬进题库——那些是写给数据层的题，
IA 本来就会用数据作答。08-26 真实 run 把 20 条这种题端给老板，被骂醒：
好题目不是捡来的，是写出来的；残局是原料，课题是成品。

架构位置：主链 run 尾部，IA 之前（src/main.py）——老板 08-26 裁决：
出题和巡逻都在综合裁决之前，巡逻成果当天进当天裁决（经研究成果架），
不许推到下次 run。

输入 = 六站对抗后的残局（bridge 未解问题 + 跨层开放题）+ 最终判决的
主要矛盾 + 家里能力清单（evidence_registry 的指标清单，供出题官论证
"家里为什么答不了"）+ 在研名单；
输出 = run_dir/research_topics.json（topics 0-2 份 + data_gaps 清单）。
模型只写内容，机械字段（topic_id、时间戳）代码装配；形状校验不过的整体降级为空。

分流原则：缺数据 → data_gaps（数据链扩容待办，不花巡逻钱）；
缺外部世界 → topics（二档巡逻候选）。这个判断由最了解上下文的出题官做。

时效纪律（老板 08-26 第三次骂醒）：课题必须"现在能查"——验收标准要求的
材料必须在 effective_date 当天已经存在。明天才发生的事（如次日财报），
只能问事前的预期与仓位，不许问事后才存在的数据。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import agenda as agenda_mod
from .agenda import LEDGER_PATH, MATERIAL_CLASSES

ARTIFACT_NAME = "research_topics.json"
PROMPT_PATH = Path(__file__).parent / "topic_composer.md"

MAX_TOPICS = 2
_STAGE_NAME = "topic_composer"

_TOPIC_FIELDS = (
    "title",
    "why_now",
    "linked_contradiction",
    "known_at_home",
    "acceptance_criteria",
    "falsification",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _topic_id(title: str) -> str:
    """topic_id 由代码装配（机械字段不出答卷）：同一标题跨 run 幂等。"""
    return "topic:" + hashlib.sha1(title.strip().encode("utf-8")).hexdigest()[:12]


def _existing_topics(ledger_path: Path) -> List[str]:
    """在研 + 待研题目清单（喂给出题官防重复出题）。"""
    out = []
    for record in agenda_mod.current_agendas(ledger_path).values():
        if record.get("status") in {"active", "candidate"}:
            out.append(str(record.get("question") or ""))
    return [q for q in out if q][:20]


def _build_prompt_input(run_dir: Path, ledger_path: Path, effective_date: str) -> Dict[str, Any]:
    """出题官的输入全部来自 IA 之前的产物（六站对抗跑完、综合裁决未跑）。"""
    final = _load_json(run_dir / "final_adjudication.json")
    bridge = _load_json(run_dir / "bridge_memos" / "bridge_0.json")
    questions_payload = _load_json(run_dir / "cross_layer_questions.json")
    event_summary = _load_json(run_dir / "event_layer_summary.json")
    registry = _load_json(run_dir / "evidence_registry.json")

    # 家里能力清单：数据链能答什么，出题官必须对着它论证"家里答不了"。
    refs = sorted((registry.get("passports") or registry.get("refs") or {}).keys())
    capability = sorted({str(r).split("#")[0] for r in refs})

    open_questions = [
        {
            "question": str(q.get("question") or "")[:200],
            "requested_checks": [str(c)[:100] for c in (q.get("requested_checks") or [])][:5],
        }
        for q in (questions_payload.get("questions") or [])
        if isinstance(q, dict) and str(q.get("status") or "open") in {"open", "insufficient_data"}
    ]
    most_important = [
        str(e.get("minimum_fact") or e.get("title") or "")[:150]
        for e in (event_summary.get("most_important_events") or [])
        if isinstance(e, dict)
    ]
    return {
        "effective_date": effective_date,
        "final_stance": str(final.get("final_stance") or ""),
        "principal_contradiction": final.get("principal_contradiction") or bridge.get("principal_contradiction") or "",
        "reasoned_verdict": str(final.get("reasoned_verdict") or "")[:1200],
        # 残局：桥接承认自己没想明白的 + 事件层给数据层出的开放题
        "bridge_unresolved_questions": [str(q)[:200] for q in (bridge.get("unresolved_questions") or [])][:8],
        "bridge_key_uncertainties": [str(u)[:200] for u in (bridge.get("key_uncertainties") or [])][:8],
        "open_cross_layer_questions": open_questions[:8],
        "event_side_headlines": [m for m in most_important if m][:6],
        # 家里的能力边界：这些指标对应的题不许出（IA 会用数据答）
        "home_data_capabilities": capability[:120],
        "existing_topics": _existing_topics(ledger_path),
    }


def validate_topics(payload: Any) -> Dict[str, Any]:
    """形状校验（闸门只守形状）：返回 {"topics": [...], "data_gaps": [...], "no_topic_reason": str, "dropped": [...]}。

    每份任务书必须六字段非空、material_classes 合法；不合格的降级进 dropped（留痕不拒收）。
    """
    result: Dict[str, Any] = {"topics": [], "data_gaps": [], "no_topic_reason": "", "dropped": []}
    if not isinstance(payload, dict):
        result["dropped"].append({"reason": "payload_not_object"})
        return result

    for raw in (payload.get("topics") or [])[: MAX_TOPICS + 2]:  # 多出的直接进 dropped
        if not isinstance(raw, dict):
            result["dropped"].append({"reason": "topic_not_object"})
            continue
        missing = [f for f in _TOPIC_FIELDS if not str(raw.get(f) or "").strip()]
        classes = [c for c in (raw.get("material_classes") or []) if c in MATERIAL_CLASSES]
        if missing:
            result["dropped"].append({"title": str(raw.get("title") or "")[:60], "reason": f"fields_empty:{','.join(missing)}"})
            continue
        if not classes:
            result["dropped"].append({"title": str(raw.get("title") or "")[:60], "reason": "material_classes_invalid"})
            continue
        topic = {f: str(raw[f]).strip() for f in _TOPIC_FIELDS}
        topic["material_classes"] = classes[:2]
        topic["topic_id"] = _topic_id(topic["title"])
        result["topics"].append(topic)
    result["topics"] = result["topics"][:MAX_TOPICS]

    data_gaps = payload.get("data_gaps")
    if isinstance(data_gaps, list):
        result["data_gaps"] = [str(g).strip()[:300] for g in data_gaps if str(g or "").strip()][:8]
    result["no_topic_reason"] = str(payload.get("no_topic_reason") or "").strip()
    return result


def _parse_response(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """从模型响应里取 JSON 对象（容忍 ```json 围栏）。"""
    if not raw:
        return None
    text = raw.strip()
    if "```" in text:
        start = text.find("```")
        start = text.find("\n", start) + 1
        end = text.rfind("```")
        if start > 0 and end > start:
            text = text[start:end].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def compose_topics(
    run_dir: Path,
    *,
    llm_caller: Optional[Callable[..., Optional[str]]] = None,
    ledger_path: Path = LEDGER_PATH,
    effective_date: str = "",
) -> Dict[str, Any]:
    """出题官主流程。永远落盘 research_topics.json；失败降级为空题单（不阻断 run）。"""
    run_dir = Path(run_dir)
    artifact_path = run_dir / ARTIFACT_NAME

    def _finish(payload: Dict[str, Any]) -> Dict[str, Any]:
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return payload

    base: Dict[str, Any] = {
        "schema_version": "research_topics_v1",
        "generated_at_utc": _utc_now_iso(),
        "topics": [],
        "data_gaps": [],
        "no_topic_reason": "",
    }

    prompt_input = _build_prompt_input(run_dir, ledger_path, effective_date)
    has_residual = bool(
        prompt_input["bridge_unresolved_questions"]
        or prompt_input["bridge_key_uncertainties"]
        or prompt_input["open_cross_layer_questions"]
    )
    if not has_residual:
        base["no_topic_reason"] = "本期无残局（桥接无未解问题、跨层无开放题）。"
        return _finish(base)
    if llm_caller is None:
        base["no_topic_reason"] = "no_llm_caller"
        return _finish(base)

    try:
        template = PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        base["no_topic_reason"] = "prompt_file_missing"
        return _finish(base)

    prompt = (
        template
        + "\n\n## 本轮输入\n\n```json\n"
        + json.dumps(prompt_input, ensure_ascii=False, indent=1)
        + "\n```\n"
    )
    try:
        raw = llm_caller(prompt, stage_name=_STAGE_NAME)
    except Exception as exc:  # noqa: BLE001 - 出题官挂了不许炸主链
        base["no_topic_reason"] = f"llm_error:{type(exc).__name__}"
        return _finish(base)

    parsed = _parse_response(raw)
    validated = validate_topics(parsed)
    base.update(validated)
    if not validated["topics"] and not validated["no_topic_reason"]:
        base["no_topic_reason"] = "出题官未产出合格任务书（形状校验未过或模型放弃），详情见 dropped。"
    return _finish(base)
