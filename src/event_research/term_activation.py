"""词表活化机制（T67/W7，2026-08-27 老板批准施工）。

设计稿：`investigation_reports/20260826_第三层治理施工工单/W6c_词表活化设计稿.md` §3。
边界原则：什么新闻进池子是采集边界，归老板；本模块**只出候选，不出决定**——
机器把"系统够不着的新主题"原句搬进候选账，词进不进正式词表由老板在控制台圈选，
每次变更写双账留痕（overrides + change_log），防静默增删。

三本账（均 append-only，与既有台账同居 output/state_ledger/）：
- term_candidates.jsonl      候选账：record_type=candidate / status_change
- keyword_table_overrides.json 增量词表：当前生效的老板圈选结果
- keyword_change_log.jsonl   留痕账：每一次 adopt/reject/remove 一行

use 枚举 {pool, body_fetch}：pool=入池相关度打分，body_fetch=正文抓取闸门。
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TERM_CANDIDATES_LEDGER = Path("output/state_ledger/term_candidates.jsonl")
KEYWORD_OVERRIDES_PATH = Path("output/state_ledger/keyword_table_overrides.json")
KEYWORD_CHANGE_LOG_PATH = Path("output/state_ledger/keyword_change_log.jsonl")

USE_VALUES = ("pool", "body_fetch")
ACTION_VALUES = ("adopt", "reject", "remove")
MAX_RAW_TEXT_LEN = 200


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def _candidate_id(raw_text: str) -> str:
    return "tc_" + hashlib.sha1(_normalize_text(raw_text).encode("utf-8")).hexdigest()[:12]


def _append_record(record: Dict[str, Any], ledger_path: Path) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_candidates(ledger_path: Path = TERM_CANDIDATES_LEDGER) -> List[Dict[str, Any]]:
    """读取候选账并折叠为每条 candidate_id 的最新状态（append-only 台账惯例）。"""
    if not Path(ledger_path).is_file():
        return []
    latest: Dict[str, Dict[str, Any]] = {}
    with Path(ledger_path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # 单行坏不整包崩：候选收集是旁路
            cid = str(record.get("candidate_id") or "")
            if not cid:
                continue
            merged = dict(latest.get(cid, {}))
            merged.update({k: v for k, v in record.items() if v is not None})
            latest[cid] = merged
    return sorted(latest.values(), key=lambda r: str(r.get("proposed_at_utc") or ""))


# --------------------------------------------------------------------------
# 第 1 步：候选收集（机械搬运原句，零 LLM）
# --------------------------------------------------------------------------

def collect_term_candidates(
    run_dir: Path,
    ledger_path: Path = TERM_CANDIDATES_LEDGER,
) -> Dict[str, Any]:
    """扫 run_dir 下 narrative_state.json 的缺席信号、research_topics.json 的 data_gaps，
    把原句追加进候选账。幂等：同 id 已在账即跳过。任何失败返回 status=skipped，
    绝不让主链红——候选收集是旁路。

    返回 harvesting 小结（照 gap_bridge.harvest_gap_candidates 模式）。
    """
    run_dir = Path(run_dir)
    raw_items: List[tuple] = []  # (raw_text, source)

    ns_path = run_dir / "narrative_state.json"
    if ns_path.is_file():
        try:
            narrative = json.loads(ns_path.read_text(encoding="utf-8"))
            for signal in narrative.get("absence_signals") or []:
                text = str(signal or "").strip()
                if text:
                    raw_items.append((text[:MAX_RAW_TEXT_LEN], "absence_signal"))
        except (json.JSONDecodeError, OSError):
            pass

    rt_path = run_dir / "research_topics.json"
    if rt_path.is_file():
        try:
            topics_doc = json.loads(rt_path.read_text(encoding="utf-8"))
            for gap in topics_doc.get("data_gaps") or []:
                text = str(gap or "").strip()
                if text:
                    raw_items.append((text[:MAX_RAW_TEXT_LEN], "topic_data_gap"))
        except (json.JSONDecodeError, OSError):
            pass

    if not raw_items:
        return {"status": "skipped", "reason": "no_candidate_sources", "added": 0, "skipped": 0}

    known_ids = {
        str(record.get("candidate_id"))
        for record in load_candidates(ledger_path)
        if record.get("record_type") == "candidate"
    }
    added: List[Dict[str, Any]] = []
    skipped = 0
    for raw_text, source in raw_items:
        cid = _candidate_id(raw_text)
        if cid in known_ids:
            skipped += 1
            continue
        record = {
            "record_type": "candidate",
            "candidate_id": cid,
            "raw_text": raw_text,
            "source": source,
            "source_run_dir": run_dir.name,
            "suggested_use": "manual_review",
            "status": "candidate",
            "proposed_at_utc": _utc_now_iso(),
        }
        _append_record(record, ledger_path)
        known_ids.add(cid)
        added.append({"candidate_id": cid, "source": source})

    return {
        "status": "ok",
        "candidates_added": len(added),
        "skipped_duplicates": skipped,
        "by_source": {"absence_signal": sum(1 for a in added if a["source"] == "absence_signal"),
                      "topic_data_gap": sum(1 for a in added if a["source"] == "topic_data_gap")},
        "candidates": added,
    }


# --------------------------------------------------------------------------
# 第 2 步：增量词表读取与合并
# --------------------------------------------------------------------------

def load_keyword_overrides(path: Path = KEYWORD_OVERRIDES_PATH) -> Dict[str, List[str]]:
    """读增量词表，按 use 分拣并 casefold 规范。文件不存在 = 机制未启用，返回空表。
    带 mtime 缓存：采集一批新闻要判几十次标题，不值得每次重读小 json；
    路径或 mtime 变了自动失效（控制台圈选后下次采集即生效）。"""
    cache_key = ("path", Path(path).resolve(), "mtime", Path(path).stat().st_mtime_ns if Path(path).is_file() else None)
    cached = getattr(load_keyword_overrides, "_cache", None)
    if cached and cached[0] == cache_key:
        return cached[1]
    overrides: Dict[str, List[str]] = {use: [] for use in USE_VALUES}
    if Path(path).is_file():
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
            for entry in doc.get("terms") or []:
                use = str(entry.get("use") or "")
                term = _normalize_text(entry.get("term") or "")
                if use in USE_VALUES and term and term not in overrides[use]:
                    overrides[use].append(term)
        except (json.JSONDecodeError, OSError):
            pass  # 半截文件宁可当没启用，红灯由 PC-29 负责
    load_keyword_overrides._cache = (cache_key, overrides)  # type: ignore[attr-defined]
    return overrides


# --------------------------------------------------------------------------
# 第 3 步：老板圈选（adopt/reject/remove），原子写双账
# --------------------------------------------------------------------------

def adopt_term(
    candidate_id: str,
    term: str,
    use: str,
    decided_by: str = "owner",
    candidates_path: Path = TERM_CANDIDATES_LEDGER,
    overrides_path: Path = KEYWORD_OVERRIDES_PATH,
    change_log_path: Path = KEYWORD_CHANGE_LOG_PATH,
) -> Dict[str, Any]:
    """收编候选词入正式增量词表：overrides 更新 + 留痕一行 + 候选标 adopted，
    同一次调用内完成（双账+状态三写必同步发生）。"""
    if use not in USE_VALUES:
        raise ValueError(f"use 必须是 {USE_VALUES} 之一，收到 {use!r}")
    term_norm = _normalize_text(term)
    if not term_norm:
        raise ValueError("term 不能为空")

    known = {str(r.get("candidate_id")) for r in load_candidates(candidates_path)}
    if candidate_id not in known:
        raise ValueError(f"candidate_id 不存在：{candidate_id}")

    overrides_doc = _read_overrides_doc(overrides_path)
    # 同词同用途重复收编幂等跳过；同词异用途允许（一个词可以既影响打分又触发抓正文）
    if not any(
        str(e.get("term")) == term_norm and str(e.get("use")) == use
        for e in overrides_doc["terms"]
    ):
        overrides_doc["terms"].append({
            "term": term_norm,
            "use": use,
            "adopted_at_utc": _utc_now_iso(),
            "source_candidate_id": candidate_id,
            "decided_by": decided_by,
        })
        _write_overrides_doc(overrides_doc, overrides_path)

    change = {
        "action": "adopt",
        "term": term_norm,
        "use": use,
        "candidate_id": candidate_id,
        "decided_by": decided_by,
        "logged_at_utc": _utc_now_iso(),
    }
    _append_record(change, change_log_path)
    append_candidate_status(candidate_id, "adopted", candidates_path=candidates_path)
    return change


def reject_term(
    candidate_id: str,
    note: str = "",
    decided_by: str = "owner",
    candidates_path: Path = TERM_CANDIDATES_LEDGER,
    change_log_path: Path = KEYWORD_CHANGE_LOG_PATH,
) -> Dict[str, Any]:
    """驳回候选：留在账上标 rejected，永不复活（设计稿 §3：不勾的死在账上）。"""
    known = {str(r.get("candidate_id")) for r in load_candidates(candidates_path)}
    if candidate_id not in known:
        raise ValueError(f"candidate_id 不存在：{candidate_id}")
    change = {
        "action": "reject",
        "candidate_id": candidate_id,
        "note": note[:200],
        "decided_by": decided_by,
        "logged_at_utc": _utc_now_iso(),
    }
    _append_record(change, change_log_path)
    append_candidate_status(candidate_id, "rejected", candidates_path=candidates_path)
    return change


def remove_term(
    term: str,
    use: str,
    decided_by: str = "owner",
    candidates_path: Path = TERM_CANDIDATES_LEDGER,
    overrides_path: Path = KEYWORD_OVERRIDES_PATH,
    change_log_path: Path = KEYWORD_CHANGE_LOG_PATH,
) -> Dict[str, Any]:
    """从生效词表移除一词（边界治理完整闭环：加了还能删，删也留痕）。"""
    if use not in USE_VALUES:
        raise ValueError(f"use 必须是 {USE_VALUES} 之一，收到 {use!r}")
    term_norm = _normalize_text(term)
    overrides_doc = _read_overrides_doc(overrides_path)
    remaining = [
        e for e in overrides_doc["terms"]
        if not (str(e.get("term")) == term_norm and str(e.get("use")) == use)
    ]
    removed = len(remaining) < len(overrides_doc["terms"])
    overrides_doc["terms"] = remaining
    _write_overrides_doc(overrides_doc, overrides_path)
    change = {
        "action": "remove",
        "term": term_norm,
        "use": use,
        "decided_by": decided_by,
        "removed_existed": removed,
        "logged_at_utc": _utc_now_iso(),
    }
    _append_record(change, change_log_path)
    return change


def append_candidate_status(
    candidate_id: str,
    new_status: str,
    note: str = "",
    candidates_path: Path = TERM_CANDIDATES_LEDGER,
) -> None:
    """候选状态变更（adopted / rejected）。追加记录带 status 字段，与 candidate
    首条同名字段——load_candidates 折叠时以最新一条为准，老板圈选后状态即翻面。"""
    _append_record({
        "record_type": "status_change",
        "candidate_id": candidate_id,
        "status": new_status,
        "note": note,
        "created_at_utc": _utc_now_iso(),
    }, candidates_path)


def _read_overrides_doc(overrides_path: Path) -> Dict[str, Any]:
    if Path(overrides_path).is_file():
        try:
            doc = json.loads(Path(overrides_path).read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("terms"), list):
                doc.setdefault("schema_version", "keyword_table_overrides_v1")
                return doc
        except (json.JSONDecodeError, OSError):
            pass
    return {"schema_version": "keyword_table_overrides_v1", "updated_at_utc": "", "terms": []}


def _write_overrides_doc(doc: Dict[str, Any], overrides_path: Path) -> None:
    doc["updated_at_utc"] = _utc_now_iso()
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# 第 4 步：机器闸门（PC-29 复用）：三账一致 + 形状完整
# --------------------------------------------------------------------------

def verify_keyword_ledgers(
    candidates_path: Path = TERM_CANDIDATES_LEDGER,
    overrides_path: Path = KEYWORD_OVERRIDES_PATH,
    change_log_path: Path = KEYWORD_CHANGE_LOG_PATH,
) -> Optional[List[str]]:
    """校验形状与身份比对（闸门不判意思）。全部通过返回 None，否则问题清单。

    三条不变式：
    ① overrides 每条 adopt 记录必须在留痕账有对应 action=adopt 且同词同用途；
    ② 留痕账每条 action=adopt/remove/reject 引用的 candidate_id 必须存在于候选账
       （remove 不带 candidate_id 是全局移除，豁免）；
    ③ 所有记录字段形状完整（枚举值合法、时间戳非空）。
    未启用机制（三账全缺）返回 None——不打扰未启用者。"""
    paths_exist = [p.is_file() for p in (candidates_path, overrides_path, change_log_path)]
    if not any(paths_exist):
        return None

    problems: List[str] = []
    candidates = load_candidates(candidates_path)
    candidate_ids = {str(r.get("candidate_id")) for r in candidates}

    change_entries: List[Dict[str, Any]] = []
    if change_log_path.is_file():
        with Path(change_log_path).open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    problems.append(f"change_log:{lineno}: 非法 JSON 行")
                    continue
                change_entries.append(entry)
                action = str(entry.get("action") or "")
                if action not in ACTION_VALUES:
                    problems.append(f"change_log:{lineno}: action 非法 {action!r}")
                if not str(entry.get("logged_at_utc") or ""):
                    problems.append(f"change_log:{lineno}: 缺 logged_at_utc")
                cid = str(entry.get("candidate_id") or "")
                if cid and cid not in candidate_ids:
                    problems.append(f"change_log:{lineno}: candidate_id 不存在 {cid}")

    adopted_pairs = {
        (str(e.get("term")), str(e.get("use")))
        for e in change_entries
        if str(e.get("action")) == "adopt"
    }

    if overrides_path.is_file():
        try:
            doc = json.loads(Path(overrides_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            problems.append(f"overrides: 文件不可读 {type(exc).__name__}")
            doc = None
        if doc is not None:
            if str(doc.get("schema_version") or "") != "keyword_table_overrides_v1":
                problems.append("overrides: schema_version 不是 keyword_table_overrides_v1")
            terms = doc.get("terms")
            if not isinstance(terms, list):
                problems.append("overrides: terms 不是数组")
                terms = []
            for i, entry in enumerate(terms):
                term = _normalize_text(str(entry.get("term") or ""))
                use = str(entry.get("use") or "")
                if not term:
                    problems.append(f"overrides[{i}]: term 为空")
                if use not in USE_VALUES:
                    problems.append(f"overrides[{i}]: use 非法 {use!r}")
                elif (term, use) not in adopted_pairs:
                    problems.append(f"overrides[{i}]: 词 {term!r}/{use} 无对应 adopt 留痕（静默增删嫌疑）")
                if not str(entry.get("decided_by") or ""):
                    problems.append(f"overrides[{i}]: 缺 decided_by")

    return problems or None
