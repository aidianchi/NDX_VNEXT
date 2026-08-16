"""T47 常设检查 A 包（PC-01 ~ PC-10）。

只读机器检查：输入 = 一次 run 的落盘产物目录（``run_dir``），输出 = 结构化结果
列表。禁止调用 LLM、禁止联网、禁止写 run_dir。模块 import 无副作用。

任务书唯一来源：
``investigation_reports/20260813_architecture_northstar_revisit/T47-20检查_施工任务书_A.md``

每一条检查对应 03 根本审查总报告 §3 的 A 类发现：
    PC-01  A1（C3 版 critic/risk 分料身份）
    PC-02  A2（C3 版治理站引用全集对账）
    PC-03  A3 + 拍板②（final 只收修订稿+修订说明 + 机器对账；08-16 重裁）
    PC-04  A5（IA ref_authority unknown 占比告警）
    PC-05  A6（委托调查 vs 进 IA 报告数对账）
    PC-06  A7（CI 材料闭合性 + 立场字段检测）
    PC-07  A9（三明治反向断言：事件字段恒空）
    PC-08  A11（同名指标多值检测）
    PC-09  B1/B10（约束/指令引用键存在性）
    PC-10  B2（事件站措辞矛盾共存检测）
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# 03 报告 A5：基线 run ref_authority 34 条中 23 条 unknown（67.6%）。
# 阈值取 50%：超过即判定许可闸门半瘫。注释保留来源，便于日后按新 run 复核。
IA_REF_AUTHORITY_UNKNOWN_WARN_RATIO = 0.50

# A11 点名的同名指标键（大小写归一后比较）。这些键在不同 metric 条目下出现且数值
# 不一致时，即构成"一处错处处错"的数值矛盾供给。
MULTI_VALUE_METRIC_KEYS = {
    "pe",
    "trailingpe",
    "forwardpe",
    "earningsyield",
    "forwardearningsyield",
    "expected_return",
    "obv",
}

# B1/B10 点名的指令引用键（PC-09）。
INSTRUCTION_REF_KEYS = ("raw_data", "NO_DATA_AVAILABLE", "analysis_required")

# A7 点名的立场/仓位字段（PC-06）。
CI_FORBIDDEN_MATERIAL_TOKENS = ("dominant_side", "action_implication", "不宜重仓", "触发核心仓")


def _read_json(path: Path) -> Any:
    """读 JSON；编码统一 UTF-8。失败抛异常，由各 check 捕获。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json(value: Any) -> str:
    """canonical JSON：排序键、紧凑分隔符，用于逐字节身份比较。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_body(payload_file: Path) -> Dict[str, Any]:
    """读 ``attempt_N.payload.json``，返回其中真正发给模型的 payload 部分。

    正式 run 的 payload 文件顶层是 ``{"stage_key": ..., "payload": {...}}``；
    兼容没有外层包装的裸 payload。
    """
    data = _read_json(payload_file)
    if isinstance(data, dict) and "payload" in data and isinstance(data["payload"], dict):
        return data["payload"]
    if isinstance(data, dict):
        return data
    raise ValueError(f"payload 文件不是 dict: {payload_file}")


def _latest_attempt_file(directory: Path, pattern: str) -> Optional[Path]:
    """目录下匹配 ``pattern``（含 attempt 捕获组）的文件中取 attempt 最大者。"""
    best: Optional[Tuple[int, Path]] = None
    for path in directory.glob(pattern):
        match = re.search(r"attempt_(\d+)", path.name)
        if not match:
            continue
        attempt = int(match.group(1))
        if best is None or attempt > best[0]:
            best = (attempt, path)
    return best[1] if best else None


def _latest_payload(directory: Path) -> Path:
    """目录下最新的 ``attempt_N.payload.json``；找不到抛 FileNotFoundError。"""
    path = _latest_attempt_file(directory, "attempt_*.payload.json")
    if path is None:
        raise FileNotFoundError(f"缺失 artifact: {directory}/attempt_*.payload.json")
    return path


def _latest_prompt(directory: Path) -> Path:
    """目录下最新的 ``attempt_N.prompt.txt``；找不到抛 FileNotFoundError。"""
    path = _latest_attempt_file(directory, "attempt_*.prompt.txt")
    if path is None:
        raise FileNotFoundError(f"缺失 artifact: {directory}/attempt_*.prompt.txt")
    return path


def _missing(detail: str) -> Dict[str, Any]:
    return {"passed": False, "detail": detail}


def _result(check_id: str, name: str, passed: bool, detail: str, evidence: str) -> Dict[str, Any]:
    return {
        "check_id": check_id,
        "name": name,
        "passed": passed,
        "detail": detail,
        "evidence": evidence,
    }


def _guard(check_id: str, name: str, func, run_dir: Path) -> Dict[str, Any]:
    """单条检查 try/except：任何异常不得让整包崩。"""
    try:
        result = func(run_dir)
    except Exception as exc:  # noqa: BLE001 - 检查必须互相隔离
        return _result(
            check_id,
            name,
            False,
            f"check_error:{type(exc).__name__}:{exc}",
            "",
        )
    # 检查内部用 _missing() 快速返回时只带 passed/detail，这里统一补齐身份字段，
    # 保证聚合器拿到的每条结果都有完整契约键。
    if not isinstance(result, dict):
        return _result(check_id, name, False, f"check_error:非 dict 结果:{type(result).__name__}", "")
    return {
        "check_id": result.get("check_id", check_id),
        "name": result.get("name", name),
        "passed": bool(result.get("passed", False)),
        "detail": str(result.get("detail", "")),
        "evidence": str(result.get("evidence", "")),
    }


def _has_key_recursive(obj: Any, key: str) -> bool:
    if isinstance(obj, dict):
        for item_key, item_value in obj.items():
            if item_key == key:
                return True
            if _has_key_recursive(item_value, key):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _has_key_recursive(item, key):
                return True
    return False


def _iter_event_ref_containers(obj: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    """递归找出 ``event_refs`` / ``key_event_refs`` 键及其值。"""
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}/{key}" if path else key
            if key in {"event_refs", "key_event_refs"}:
                yield child_path, value
            yield from _iter_event_ref_containers(value, child_path)
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            yield from _iter_event_ref_containers(item, f"{path}[{index}]")


def _is_empty_collection(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


# ──────────────────────────────────────────────────────────────────────────
# PC-01
# ──────────────────────────────────────────────────────────────────────────

def _check_pc01(run_dir: Path) -> Dict[str, Any]:
    critic_dir = run_dir / "prompt_audit" / "critic"
    risk_dir = run_dir / "prompt_audit" / "risk"
    if not critic_dir.is_dir():
        return _missing("缺失 artifact: prompt_audit/critic")
    if not risk_dir.is_dir():
        return _missing("缺失 artifact: prompt_audit/risk")

    critic_gi = _payload_body(_latest_payload(critic_dir)).get("governance_input")
    risk_gi = _payload_body(_latest_payload(risk_dir)).get("governance_input")
    if not isinstance(critic_gi, dict):
        return _missing("缺失 artifact: critic governance_input")
    if not isinstance(risk_gi, dict):
        return _missing("缺失 artifact: risk governance_input")

    critic_thesis_main = critic_gi.get("thesis_main")
    risk_thesis_main = risk_gi.get("thesis_main")
    risk_chains = risk_gi.get("thesis_key_support_chains")
    risk_responses = risk_gi.get("thesis_hypothesis_responses")
    critic_ok = isinstance(critic_thesis_main, str) and bool(critic_thesis_main)
    risk_blind = (
        risk_thesis_main == ""
        and risk_chains == []
        and risk_responses == []
    )
    differ = _canonical_json(critic_gi) != _canonical_json(risk_gi)

    passed = critic_ok and risk_blind and differ
    detail = (
        f"critic.thesis_main={critic_thesis_main!r}; "
        f"risk.thesis_main={risk_thesis_main!r}, "
        f"risk.thesis_key_support_chains={risk_chains!r}, "
        f"risk.thesis_hypothesis_responses={risk_responses!r}; "
        f"governance_input 序列化{'不同' if differ else '逐字节相同'}"
    )
    return _result("PC-01", "critic/risk 分料身份检查（A1 的 C3 版）", passed, detail,
                   "prompt_audit/critic:governance_input vs prompt_audit/risk:governance_input")


# ──────────────────────────────────────────────────────────────────────────
# PC-02
# ──────────────────────────────────────────────────────────────────────────

def _thesis_evidence_refs(thesis: Dict[str, Any]) -> set:
    """收集 thesis_draft 中的全部 evidence_refs。

    与 ``_build_governance_input_packet`` 的收集面一致（key_support_chains、
    hypothesis_responses、portfolio_actions、time_horizon_views、
    reader_conclusion、principal_contradiction、secondary_contradictions、
    price_reflection_map）。额外收集 price_reflection_map 的
    ``counterevidence_refs``——A2 的病恰是这些反证位引用被 builder 漏掉，因此
    检查必须把它们算进"全集"，否则这条检查永远抓不住 A2。
    """
    refs: set = set()
    containers: List[Any] = []
    containers.extend(thesis.get("key_support_chains") or [])
    containers.extend(thesis.get("hypothesis_responses") or [])
    containers.extend(thesis.get("portfolio_actions") or [])
    containers.extend(thesis.get("time_horizon_views") or [])
    containers.append(thesis.get("reader_conclusion") or {})
    containers.append(thesis.get("principal_contradiction") or {})
    containers.extend(thesis.get("secondary_contradictions") or [])
    containers.extend(thesis.get("price_reflection_map") or [])

    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in ("evidence_refs", "counterevidence_refs"):
            value = container.get(key)
            if isinstance(value, list):
                refs.update(str(item) for item in value if isinstance(item, str))
    return refs


def _counter_thesis_evidence_refs(synthesis_packet: Dict[str, Any]) -> set:
    refs: set = set()
    for hypothesis in synthesis_packet.get("competing_hypotheses") or []:
        if not isinstance(hypothesis, dict):
            continue
        if hypothesis.get("source") != "counter_thesis":
            continue
        for key in ("support_evidence_refs", "counter_evidence_refs", "diagnostic_evidence_refs"):
            value = hypothesis.get(key)
            if isinstance(value, list):
                refs.update(str(item) for item in value if isinstance(item, str))
    return refs


def _typed_conflict_evidence_refs(synthesis_packet: Dict[str, Any]) -> set:
    refs: set = set()
    for conflict in synthesis_packet.get("high_severity_typed_conflicts") or []:
        if not isinstance(conflict, dict):
            continue
        value = conflict.get("evidence_refs")
        if isinstance(value, list):
            refs.update(str(item) for item in value if isinstance(item, str))
    return refs


def _risk_side_evidence_refs(synthesis_packet: Dict[str, Any]) -> set:
    """risk 论证盲分料应包含的引用集。

    与 ``_build_governance_input_packet`` 的 risk 分支一致：typed 冲突 + 普通
    高严重度冲突 + principal_contradictions 的 evidence_refs，再加每层
    layer_summaries.indicator_refs 的前 12 个。
    """
    refs: set = set()
    for conflict in synthesis_packet.get("high_severity_typed_conflicts") or []:
        if isinstance(conflict, dict):
            value = conflict.get("evidence_refs")
            if isinstance(value, list):
                refs.update(str(item) for item in value if isinstance(item, str))
    for conflict in synthesis_packet.get("high_severity_conflicts") or []:
        if isinstance(conflict, dict):
            value = conflict.get("evidence_refs")
            if isinstance(value, list):
                refs.update(str(item) for item in value if isinstance(item, str))
    for contradiction in synthesis_packet.get("principal_contradictions") or []:
        if isinstance(contradiction, dict):
            value = contradiction.get("evidence_refs")
            if isinstance(value, list):
                refs.update(str(item) for item in value if isinstance(item, str))
    for summary in synthesis_packet.get("layer_summaries") or []:
        if isinstance(summary, dict):
            value = summary.get("indicator_refs")
            if isinstance(value, list):
                refs.update(str(item) for item in value[:12] if isinstance(item, str))
    return refs


def _key_evidence_refs_of(governance_input: Dict[str, Any]) -> set:
    value = governance_input.get("key_evidence_refs")
    if isinstance(value, dict):
        return set(str(key) for key in value.keys())
    if isinstance(value, list):
        return set(str(item) for item in value if isinstance(item, str))
    return set()


def _check_pc02(run_dir: Path) -> Dict[str, Any]:
    thesis_path = run_dir / "thesis_draft.json"
    synthesis_path = run_dir / "synthesis_packet.json"
    if not thesis_path.exists():
        return _missing("缺失 artifact: thesis_draft.json")
    if not synthesis_path.exists():
        return _missing("缺失 artifact: synthesis_packet.json")

    thesis = _read_json(thesis_path)
    synthesis = _read_json(synthesis_path)
    if not isinstance(thesis, dict) or not isinstance(synthesis, dict):
        return _missing("缺失 artifact: thesis_draft.json/synthesis_packet.json 不是 dict")

    evidence_index = synthesis.get("evidence_index") or {}
    index_keys = set(evidence_index.keys()) if isinstance(evidence_index, dict) else set()

    thesis_refs = _thesis_evidence_refs(thesis)
    counter_refs = _counter_thesis_evidence_refs(synthesis)
    typed_conflict_refs = _typed_conflict_evidence_refs(synthesis)
    non_risk_required = (thesis_refs | counter_refs | typed_conflict_refs) & index_keys
    risk_required = _risk_side_evidence_refs(synthesis) & index_keys
    thesis_or_counter_refs = thesis_refs | counter_refs

    station_errors: List[str] = []
    station_dirs = ["critic", "reviser", "final_adjudicator"]
    for station in station_dirs:
        directory = run_dir / "prompt_audit" / station
        if not directory.is_dir():
            station_errors.append(f"{station}: 缺失 artifact: prompt_audit/{station}")
            continue
        gi = _payload_body(_latest_payload(directory)).get("governance_input")
        if not isinstance(gi, dict):
            station_errors.append(f"{station}: 缺失 artifact: governance_input")
            continue
        keys = _key_evidence_refs_of(gi) & index_keys
        missing = sorted(non_risk_required - keys)
        if missing:
            station_errors.append(f"{station} 缺 {len(missing)} 条: {missing[:5]}")

    risk_dir = run_dir / "prompt_audit" / "risk"
    if not risk_dir.is_dir():
        station_errors.append("risk: 缺失 artifact: prompt_audit/risk")
    else:
        gi = _payload_body(_latest_payload(risk_dir)).get("governance_input")
        if not isinstance(gi, dict):
            station_errors.append("risk: 缺失 artifact: governance_input")
        else:
            risk_keys = _key_evidence_refs_of(gi) & index_keys
            missing = sorted(risk_required - risk_keys)
            if missing:
                station_errors.append(f"risk 缺 {len(missing)} 条: {missing[:5]}")
            extra = sorted(risk_keys - risk_required)
            if extra:
                station_errors.append(f"risk 混入非冲突/层摘要引用 {len(extra)} 条: {extra[:5]}")

    passed = not station_errors
    detail = "; ".join(station_errors) if station_errors else (
        f"thesis/counter 并集 {len(non_risk_required)} 条、risk 分料 {len(risk_required)} 条，全部就位"
    )
    return _result(
        "PC-02",
        "治理站引用全集对账（A2 的 C3 版）",
        passed,
        detail,
        f"thesis_draft.json:{len(thesis_refs)}; synthesis_packet.json:counter={len(counter_refs)},"
        f"typed_conflict={len(typed_conflict_refs)}; evidence_index={len(index_keys)}",
    )


# ──────────────────────────────────────────────────────────────────────────
# PC-03
# ──────────────────────────────────────────────────────────────────────────

# final governance_input 的 thesis_* 字段 ↔ revised_thesis 原字段。
_THESIS_FIELD_MAP = {
    "thesis_main": "main_thesis",
    "thesis_environment": "environment_assessment",
    "thesis_valuation": "valuation_assessment",
    "thesis_timing": "timing_assessment",
    "thesis_confidence": "overall_confidence",
    "thesis_dependencies": "dependencies",
    "thesis_key_support_chains": "key_support_chains",
    "thesis_hypothesis_responses": "hypothesis_responses",
    "thesis_state_diagnosis": "state_diagnosis",
    "thesis_priced_narrative": "priced_narrative",
    "thesis_payoff_assessment": "payoff_assessment",
    "thesis_time_horizon_views": "time_horizon_views",
    "thesis_portfolio_actions": "portfolio_actions",
    "thesis_confirmation_cost": "confirmation_cost",
    "thesis_invalidation_conditions": "invalidation_conditions",
    "thesis_reader_conclusion": "reader_conclusion",
    "thesis_principal_contradiction": "principal_contradiction",
    "thesis_secondary_contradictions": "secondary_contradictions",
    "thesis_price_reflection_map": "price_reflection_map",
}


def _leaf_key_names(value: Any, acc: Optional[set] = None) -> set:
    """收集一棵 JSON 树里出现过的全部 dict 键名（叶子与容器都算）。

    PC-03 机器对账用：revision_claimed_fields 声称改过的字段名，必须是修订稿
    实物里真实出现过的键名——身份比对，不解析散文意思。
    """
    if acc is None:
        acc = set()
    if isinstance(value, dict):
        for key, item in value.items():
            acc.add(key)
            _leaf_key_names(item, acc)
    elif isinstance(value, list):
        for item in value:
            _leaf_key_names(item, acc)
    return acc


def _check_pc03(run_dir: Path) -> Dict[str, Any]:
    analysis_revised_path = run_dir / "analysis_revised.json"
    final_dir = run_dir / "prompt_audit" / "final_adjudicator"
    if not analysis_revised_path.exists():
        return _missing("缺失 artifact: analysis_revised.json")
    if not final_dir.is_dir():
        return _missing("缺失 artifact: prompt_audit/final_adjudicator")

    analysis_revised = _read_json(analysis_revised_path)
    final_gi = _payload_body(_latest_payload(final_dir)).get("governance_input")
    if not isinstance(analysis_revised, dict):
        return _missing("缺失 artifact: analysis_revised.json 不是 dict")
    if not isinstance(final_gi, dict):
        return _missing("缺失 artifact: final governance_input")

    revised_thesis = analysis_revised.get("revised_thesis")
    if not isinstance(revised_thesis, dict):
        return _missing("缺失 artifact: analysis_revised.revised_thesis")

    _missing_sentinel = object()
    mismatches: List[str] = []
    for final_key, revised_key in _THESIS_FIELD_MAP.items():
        if final_key not in final_gi:
            continue
        final_value = final_gi[final_key]
        revised_value = revised_thesis.get(revised_key, _missing_sentinel)
        matches_revised = (
            revised_value is not _missing_sentinel
            and _canonical_json(final_value) == _canonical_json(revised_value)
        )
        if not matches_revised:
            mismatches.append(final_key)

    revision_summary = final_gi.get("revision_summary")
    revision_ok = isinstance(revision_summary, str) and bool(revision_summary)
    # 2026-08-16 重裁：原稿不得再进终审输入——出现在 final governance_input 里就是
    # 供给回潮，必须报警（旧 run 的旧 payload 会如实报红，等新 run 自然转绿）。
    thesis_original_leaked = "thesis_original" in final_gi

    # ── 修订说明机器对账（08-16 新口径）：声称改过的字段必须逐项在修订稿实物
    #    里存在。老产物缺 revision_claimed_fields 时按"未声称"处理，不因缺字段判病。
    claimed_raw = analysis_revised.get("revision_claimed_fields")
    claimed_fields: List[str] = []
    claimed_shape_bad = False
    if claimed_raw is not None:
        if not isinstance(claimed_raw, list) or not all(
            isinstance(item, str) and bool(item) for item in claimed_raw
        ):
            claimed_shape_bad = True
        else:
            claimed_fields = [str(item) for item in claimed_raw]
    actual_leaf_names = _leaf_key_names(revised_thesis)
    missing_claimed = sorted({name for name in claimed_fields if name not in actual_leaf_names})
    if claimed_shape_bad:
        claimed_detail = "revision_claimed_fields 形状非法（须为非空字符串列表）"
    elif claimed_fields:
        claimed_detail = (
            f"revision_claimed_fields {len(claimed_fields)} 项"
            f"{'全部命中修订稿实物' if not missing_claimed else f'，{len(missing_claimed)} 项不在实物中: {missing_claimed}'}"
        )
    else:
        claimed_detail = "revision_claimed_fields 未提供或为空（老产物按未声称处理）"
    claimed_ok = not claimed_shape_bad and not missing_claimed

    if thesis_original_leaked:
        leak_detail = "thesis_original 仍出现在 final governance_input（08-16 重裁后属供给回潮）"
    else:
        leak_detail = "thesis_original 已从 final governance_input 移除（08-16 重裁口径）"

    passed = not mismatches and revision_ok and claimed_ok and not thesis_original_leaked
    detail = (
        f"{leak_detail}; revision_summary={'非空' if revision_ok else '空'}; "
        f"{claimed_detail}; "
        f"thesis_* 与 revised_thesis{'全部一致' if not mismatches else '不一致: ' + str(mismatches)}"
    )
    return _result("PC-03", "final 只收修订稿+修订说明+机器对账（A3 + 拍板②·08-16重裁）", passed, detail,
                   "prompt_audit/final_adjudicator:governance_input; analysis_revised.json")


# ──────────────────────────────────────────────────────────────────────────
# PC-04
# ──────────────────────────────────────────────────────────────────────────

def _load_ia_payload(run_dir: Path) -> Optional[Dict[str, Any]]:
    """从 IA 的 prompt_audit 落点提取 ``## 本轮输入`` 后的 JSON payload。

    正式落点是 ``prompt_audit/integrated_adjudicator/<timestamp>/attempt_N.prompt.txt``；
    若缺失则回退到摊开器留证 ``context_spread/full/integrated_adjudicator/...``。
    """
    candidates: List[Path] = []
    for base in (
        run_dir / "prompt_audit" / "integrated_adjudicator",
        run_dir / "context_spread" / "full" / "integrated_adjudicator",
    ):
        if base.is_dir():
            candidates.extend(base.glob("**/attempt_*.prompt.txt"))
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    text = latest.read_text(encoding="utf-8")
    marker = text.find("## 本轮输入")
    search_from = marker if marker >= 0 else 0
    for match in re.finditer(r"```json\s*\n(.*?)```", text[search_from:], re.S):
        try:
            payload = json.loads(match.group(1), strict=False)
        except Exception:
            continue
        if isinstance(payload, dict) and ("ref_authority" in payload or "allowed_investigation_ids" in payload):
            return payload
    # 兜底：全文找第一个含 IA 特征键的 JSON 块。
    for match in re.finditer(r"```json\s*\n(.*?)```", text, re.S):
        try:
            payload = json.loads(match.group(1), strict=False)
        except Exception:
            continue
        if isinstance(payload, dict) and ("ref_authority" in payload or "allowed_investigation_ids" in payload):
            return payload
    return None


def _check_pc04(run_dir: Path) -> Dict[str, Any]:
    payload = _load_ia_payload(run_dir)
    if payload is None:
        return _missing("缺失 artifact: integrated_adjudicator prompt payload（含 ref_authority）")

    authority = payload.get("ref_authority")
    if not isinstance(authority, dict) or not authority:
        return _result("PC-04", "IA ref_authority unknown 占比告警（A5）", False,
                       "ref_authority 缺失或为空", "integrated_adjudicator prompt payload")

    total = 0
    unknown = 0
    for info in authority.values():
        total += 1
        usage = info.get("usage") if isinstance(info, dict) else info
        if str(usage or "").strip().lower() == "unknown":
            unknown += 1
    ratio = unknown / total if total else 0.0
    passed = ratio <= IA_REF_AUTHORITY_UNKNOWN_WARN_RATIO
    detail = f"ref_authority {total} 条中 unknown {unknown} 条（{ratio:.1%}），阈值 {IA_REF_AUTHORITY_UNKNOWN_WARN_RATIO:.0%}"
    return _result("PC-04", "IA ref_authority unknown 占比告警（A5）", passed, detail,
                   "prompt_audit/integrated_adjudicator:payload.ref_authority")


# ──────────────────────────────────────────────────────────────────────────
# PC-05
# ──────────────────────────────────────────────────────────────────────────

def _check_pc05(run_dir: Path) -> Dict[str, Any]:
    router_path = run_dir / "inquiry_router_output.json"
    if not router_path.exists():
        return _missing("缺失 artifact: inquiry_router_output.json")
    payload = _load_ia_payload(run_dir)
    if payload is None:
        return _missing("缺失 artifact: integrated_adjudicator prompt payload（PC-05 对账目标）")

    router = _read_json(router_path)
    if not isinstance(router, dict):
        return _missing("缺失 artifact: inquiry_router_output.json 不是 dict")
    agent_specs = router.get("agent_specs")
    if not isinstance(agent_specs, list):
        return _missing("缺失 artifact: inquiry_router_output.agent_specs")

    allowed_ids = payload.get("allowed_investigation_ids")
    reports = payload.get("investigation_reports")
    gaps = payload.get("investigation_gaps")
    if not isinstance(allowed_ids, list):
        allowed_ids = []
    if not isinstance(reports, list):
        reports = []
    if not isinstance(gaps, list):
        gaps = []

    delegated = len(agent_specs)
    allowed = len(allowed_ids)
    reported = len(reports)
    gap_count = len(gaps)
    # C8 后失败调查 = 显性占位（investigation_gaps），不再静默缺席：
    # 委托数 = 非 stub 报告数 + 占位数；allowed_investigation_ids 只含非 stub。
    passed = delegated == allowed + gap_count and reported == allowed
    detail = (
        f"agent_specs={delegated}, allowed_investigation_ids={allowed}, "
        f"investigation_reports={reported}, investigation_gaps={gap_count}"
    )
    if not passed:
        detail += "；调查数对不上（可能是真静默缺席，也可能是占位装配未接线）"
    return _result("PC-05", "委托调查 vs 进 IA 报告数对账（A6）", passed, detail,
                   "inquiry_router_output.json:agent_specs vs IA payload:allowed_investigation_ids/investigation_reports/investigation_gaps")


# ──────────────────────────────────────────────────────────────────────────
# PC-06
# ──────────────────────────────────────────────────────────────────────────

def _check_pc06(run_dir: Path) -> Dict[str, Any]:
    ci_dir = run_dir / "prompt_audit" / "controlled_investigation"
    if not ci_dir.is_dir():
        return _missing("缺失 artifact: prompt_audit/controlled_investigation")

    prompts_by_investigation: Dict[str, Path] = {}
    for path in ci_dir.glob("inv_*.attempt_*.prompt.txt"):
        match = re.match(r"(inv_[0-9a-f]+)\.attempt_(\d+)\.prompt\.txt", path.name)
        if not match:
            continue
        investigation = match.group(1)
        attempt = int(match.group(2))
        previous = prompts_by_investigation.get(investigation)
        if previous is None:
            prompts_by_investigation[investigation] = path
        else:
            previous_match = re.match(r"(inv_[0-9a-f]+)\.attempt_(\d+)\.prompt\.txt", previous.name)
            previous_attempt = int(previous_match.group(2)) if previous_match else -1
            if attempt > previous_attempt:
                prompts_by_investigation[investigation] = path

    if not prompts_by_investigation:
        return _missing("缺失 artifact: controlled_investigation/*.prompt.txt")

    errors: List[str] = []
    block_count = 0
    for investigation in sorted(prompts_by_investigation):
        prompt_path = prompts_by_investigation[investigation]
        text = prompt_path.read_text(encoding="utf-8")
        blocks = re.findall(r"\[M(\d+)\][^\n]*\n(.*?)\[/M\1\]", text, re.S)
        if not blocks:
            errors.append(f"{investigation}: 未发现 [M#]...[/M#] 材料块")
            continue
        for number, body in blocks:
            block_count += 1
            block_id = f"{investigation}.M{number}"
            parse_error = None
            try:
                json.loads(body, strict=False)
            except Exception as exc:
                parse_error = f"{type(exc).__name__}: {exc}"
            if parse_error:
                errors.append(f"{block_id}: JSON 不闭合/不可解析（{parse_error}）")
            for token in CI_FORBIDDEN_MATERIAL_TOKENS:
                if token in body:
                    errors.append(f"{block_id}: 材料含立场/仓位字段 {token!r}（待 C6 装配点）")

    passed = not errors
    detail = "; ".join(errors[:10]) if errors else f"{len(prompts_by_investigation)} 份调查材料、{block_count} 个 [M#] 块全部闭合且无立场字段"
    return _result("PC-06", "CI 材料闭合性 + 立场字段检测（A7）", passed, detail,
                   f"prompt_audit/controlled_investigation:{len(prompts_by_investigation)} 份")


# ──────────────────────────────────────────────────────────────────────────
# PC-07
# ──────────────────────────────────────────────────────────────────────────

def _check_pc07(run_dir: Path) -> Dict[str, Any]:
    stage_dirs = ["bridge", "critic", "risk", "reviser", "final_adjudicator"]
    violations: List[str] = []
    checked = 0
    for station in stage_dirs:
        directory = run_dir / "prompt_audit" / station
        if not directory.is_dir():
            return _missing(f"缺失 artifact: prompt_audit/{station}")
        body = _payload_body(_latest_payload(directory))
        checked += 1
        for path, value in _iter_event_ref_containers(body):
            if not _is_empty_collection(value):
                violations.append(f"{station}:{path} 非空={str(value)[:80]}")

    passed = not violations
    detail = "事件字段恒空" if passed else "；".join(violations)
    return _result("PC-07", "事件字段恒空（A9 反向断言）", passed, detail,
                   f"prompt_audit/{'/'.join(stage_dirs)}:event_refs/key_event_refs")


# ──────────────────────────────────────────────────────────────────────────
# PC-08
# ──────────────────────────────────────────────────────────────────────────

def _collect_multi_value_leaves(obj: Any, source: str, path: str = "", out: Optional[Dict[str, List[Tuple[str, str]]]] = None) -> Dict[str, List[Tuple[str, str]]]:
    """收集指定指标键的数值叶。键名归一化后进 MULTI_VALUE_METRIC_KEYS 才收。"""
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}/{key}" if path else key
            normalized = str(key).lower()
            # 历史月序列（recent_records/numeric_summary 等）本就是多值时间序列，不算
            # 矛盾供给；只保留 latest_record 这种"同一当前值"的重复声明用于对账。
            in_history_series = "/monthly_series/" in child_path and "/latest_record/" not in child_path
            if (
                normalized in MULTI_VALUE_METRIC_KEYS
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and not in_history_series
            ):
                out.setdefault(normalized, []).append((child_path, repr(value)))
            _collect_multi_value_leaves(value, source, child_path, out)
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            _collect_multi_value_leaves(item, source, f"{path}[{index}]", out)
    return out


def _check_pc08(run_dir: Path) -> Dict[str, Any]:
    layer_stations = ["L1", "L2", "L3", "L4", "L5"]
    collected: Dict[str, List[Tuple[str, str]]] = {}
    for station in layer_stations:
        directory = run_dir / "prompt_audit" / station
        if not directory.is_dir():
            return _missing(f"缺失 artifact: prompt_audit/{station}")
        body = _payload_body(_latest_payload(directory))
        _collect_multi_value_leaves(body, station, station, collected)

    layer_cards_dir = run_dir / "layer_cards"
    if not layer_cards_dir.is_dir():
        return _missing("缺失 artifact: layer_cards")
    for card_path in sorted(layer_cards_dir.glob("L*.json")):
        card = _read_json(card_path)
        _collect_multi_value_leaves(card, card_path.stem, card_path.stem, collected)

    conflicts: List[str] = []
    for key in sorted(collected):
        entries = collected[key]
        distinct = {}
        for path, value in entries:
            distinct.setdefault(value, path)
        if len(distinct) > 1:
            samples = list(distinct.items())[:3]
            rendered = "、".join(f"{value}@{path}" for value, path in samples)
            conflicts.append(f"{key}: {rendered}")

    passed = not conflicts
    detail = "；".join(conflicts) if conflicts else "同名指标键数值一致"
    return _result("PC-08", "同名指标多值检测（A11）", passed, detail,
                   "prompt_audit/L1-L5 + layer_cards/*.json")


# ──────────────────────────────────────────────────────────────────────────
# PC-09
# ──────────────────────────────────────────────────────────────────────────

def _check_pc09(run_dir: Path) -> Dict[str, Any]:
    prompt_audit_dir = run_dir / "prompt_audit"
    if not prompt_audit_dir.is_dir():
        return _missing("缺失 artifact: prompt_audit")

    violations: List[str] = []
    checked = 0
    for station_dir in sorted(path for path in prompt_audit_dir.iterdir() if path.is_dir()):
        payload_file = _latest_attempt_file(station_dir, "attempt_*.payload.json")
        prompt_file = _latest_attempt_file(station_dir, "attempt_*.prompt.txt")
        if prompt_file is None:
            continue
        prompt_text = prompt_file.read_text(encoding="utf-8")
        mentioned = [key for key in INSTRUCTION_REF_KEYS if key in prompt_text]
        if not mentioned:
            continue
        if payload_file is None:
            violations.append(f"{station_dir.name}: 提示词点名 {mentioned}，但该站无 payload.json 可对账")
            continue
        payload = _payload_body(payload_file)
        for key in mentioned:
            if not _has_key_recursive(payload, key):
                violations.append(f"{station_dir.name}: 提示词点名 {key!r} 但 payload 无此键")
        checked += 1

    passed = not violations
    detail = "；".join(violations[:10]) if violations else "指令点名键与 payload 实际键一致"
    return _result("PC-09", "约束/指令引用键存在性（B1/B10）", passed, detail,
                   f"prompt_audit/*:{INSTRUCTION_REF_KEYS}")


# ──────────────────────────────────────────────────────────────────────────
# PC-10
# ──────────────────────────────────────────────────────────────────────────

def _check_pc10(run_dir: Path) -> Dict[str, Any]:
    prompt_audit_dir = run_dir / "prompt_audit"
    if not prompt_audit_dir.is_dir():
        return _missing("缺失 artifact: prompt_audit")

    station_dirs = sorted(
        path for path in prompt_audit_dir.iterdir()
        if path.is_dir() and (path.name.startswith("event_card_interpreter.") or path.name == "event_section_summary")
    )
    if not station_dirs:
        return _missing("缺失 artifact: prompt_audit/event_card_interpreter.* 与 event_section_summary")

    # B2 的成对矛盾措辞。A 侧："据报道/该媒体称"与强制措辞要求（开头/必须/弱来源）共存；
    # B 侧："措辞完全由你决定"或"没有固定说法"。
    side_a = re.compile(r"(?:据报道|该媒体称)[^\n]*(?:开头|必须|弱来源)|(?:开头|必须|弱来源)[^\n]*(?:据报道|该媒体称)")
    side_b = re.compile(r"措辞完全由你决定|没有固定说法")

    conflicts: List[str] = []
    for station_dir in station_dirs:
        prompt_file = _latest_prompt(station_dir)
        text = prompt_file.read_text(encoding="utf-8")
        has_a = bool(side_a.search(text))
        has_b = bool(side_b.search(text))
        if has_a and has_b:
            conflicts.append(f"{station_dir.name}: 强制措辞与'措辞完全由你决定'矛盾对共存")

    passed = not conflicts
    detail = "；".join(conflicts) if conflicts else "未发现 B2 矛盾措辞对"
    return _result("PC-10", "事件站措辞矛盾共存检测（B2）", passed, detail,
                   "prompt_audit/event_card_interpreter.* + event_section_summary")


# ──────────────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────────────

_CHECKS = [
    ("PC-01", "critic/risk 分料身份检查（A1 的 C3 版）", _check_pc01),
    ("PC-02", "治理站引用全集对账（A2 的 C3 版）", _check_pc02),
    ("PC-03", "final 只收修订稿+修订说明+机器对账（A3 + 拍板②·08-16重裁）", _check_pc03),
    ("PC-04", "IA ref_authority unknown 占比告警（A5）", _check_pc04),
    ("PC-05", "委托调查 vs 进 IA 报告数对账（A6）", _check_pc05),
    ("PC-06", "CI 材料闭合性 + 立场字段检测（A7）", _check_pc06),
    ("PC-07", "事件字段恒空（A9 反向断言）", _check_pc07),
    ("PC-08", "同名指标多值检测（A11）", _check_pc08),
    ("PC-09", "约束/指令引用键存在性（B1/B10）", _check_pc09),
    ("PC-10", "事件站措辞矛盾共存检测（B2）", _check_pc10),
]


def run_checks_a(run_dir: Path) -> List[Dict[str, Any]]:
    """对一次 run 的落盘产物目录执行 PC-01 ~ PC-10，返回结构化结果列表。

    只读；单条异常不崩整包；不写 run_dir。
    """
    return [_guard(check_id, name, func, run_dir) for check_id, name, func in _CHECKS]
