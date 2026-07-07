from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .contracts import RunReviewFinding, RunReviewReport
except ImportError:
    from contracts import RunReviewFinding, RunReviewReport


INTERNAL_READER_PHRASES = [
    "批准",
    "审批",
    "放行",
    "分析框架完整",
    "质量闸门",
    "quality_gate",
    "adjudicator",
]

REQUIRED_PRICE_REFLECTION_CATEGORIES = {"credit", "rates", "valuation", "technical_panic", "liquidity"}
HIGH_PAYOFF_TERMS = ["高赔率", "赔率改善", "赔率变厚", "风险补偿变厚"]
NEGATIVE_PAYOFF_TERMS = ["赔率不利", "赔率偏向下行", "赔率不对称偏向下行", "风险收益比不利", "不支持重仓"]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _collect_refs(payload: Any) -> List[str]:
    refs: List[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "evidence_refs":
                refs.extend(str(item) for item in _as_list(value))
            else:
                refs.extend(_collect_refs(value))
    elif isinstance(payload, list):
        for item in payload:
            refs.extend(_collect_refs(item))
    return list(dict.fromkeys(ref for ref in refs if ref))


def _reader_text(final: Dict[str, Any]) -> str:
    reader = final.get("reader_final") if isinstance(final.get("reader_final"), dict) else {}
    parts = [
        reader.get("one_liner", ""),
        " ".join(str(item) for item in _as_list(reader.get("three_reasons"))),
    ]
    return " ".join(str(part) for part in parts if part)


def _payoff_language_mismatch(final: Dict[str, Any]) -> bool:
    stance_text = " ".join(
        str(part)
        for part in [
            final.get("final_stance", ""),
            _reader_text(final),
        ]
        if part
    )
    payoff_text = str(final.get("payoff_assessment") or "")
    if not stance_text or not payoff_text:
        return False
    says_high_payoff = any(term in stance_text for term in HIGH_PAYOFF_TERMS)
    says_negative_payoff = any(term in payoff_text for term in NEGATIVE_PAYOFF_TERMS)
    return says_high_payoff and says_negative_payoff


def _parse_date_text(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value)[:10]
    if len(text) != 10:
        return None
    return text


def _damodaran_erp_payload(analysis_packet: Dict[str, Any]) -> Dict[str, Any]:
    raw_data = analysis_packet.get("raw_data") if isinstance(analysis_packet.get("raw_data"), dict) else {}
    l4 = raw_data.get("L4") if isinstance(raw_data.get("L4"), dict) else {}
    item = l4.get("get_damodaran_us_implied_erp") if isinstance(l4.get("get_damodaran_us_implied_erp"), dict) else {}
    value = item.get("value") if isinstance(item.get("value"), dict) else {}
    return value if isinstance(value, dict) else {}


def _damodaran_review_finding(analysis_packet: Dict[str, Any], backtest_date: Optional[str]) -> RunReviewFinding:
    value = _damodaran_erp_payload(analysis_packet)
    windows = value.get("damodaran_erp_historical_percentiles", {}).get("windows", {}) if isinstance(value, dict) else {}
    window_5y = windows.get("5y") if isinstance(windows, dict) and isinstance(windows.get("5y"), dict) else {}
    window_10y = windows.get("10y") if isinstance(windows, dict) and isinstance(windows.get("10y"), dict) else {}
    cutoff = _parse_date_text(value.get("data_date") or value.get("damodaran_erp_historical_percentiles", {}).get("data_cutoff_date"))
    if backtest_date and cutoff and cutoff > backtest_date:
        return _finding(
            "data",
            "fail",
            f"Damodaran ERP 分位数据截止日 {cutoff} 晚于回测日 {backtest_date}，存在前视泄露风险。",
            ["analysis_packet.json:raw_data.L4.get_damodaran_us_implied_erp"],
            recommended_rule_update="Damodaran ERP percentile 必须先按 backtest_date 裁剪月度序列再计算。",
        )
    statuses = {str(window_5y.get("status") or ""), str(window_10y.get("status") or "")}
    artifact_ref = ["analysis_packet.json:raw_data.L4.get_damodaran_us_implied_erp.value.damodaran_erp_historical_percentiles"]
    if not value:
        return _finding("data", "observe", "Damodaran ERP 数据缺失，无法复盘官方月度 ERP 分位。", artifact_ref)
    if statuses <= {"available"}:
        return _finding(
            "data",
            "pass",
            "Damodaran ERP 官方月度分位可用："
            f"current={value.get('erp_t12m_adjusted_payout')}，"
            f"5Y={window_5y.get('percentile')}% ({window_5y.get('sample_count')} months)，"
            f"10Y={window_10y.get('percentile')}% ({window_10y.get('sample_count')} months)，"
            f"cutoff={cutoff or 'unknown'}。",
            artifact_ref,
            recommended_rule_update="报告和 prompt 必须继续把 Damodaran US implied ERP historical percentile 与 NDX PE/PB/Forward PE percentile 分开。",
        )
    return _finding(
        "data",
        "observe",
        "Damodaran ERP 官方月度分位不可完整使用："
        f"5Y status={window_5y.get('status')} sample={window_5y.get('sample_count')}/{window_5y.get('required_min_months')}；"
        f"10Y status={window_10y.get('status')} sample={window_10y.get('sample_count')}/{window_10y.get('required_min_months')}；"
        f"cutoff={cutoff or 'unknown'}。",
        artifact_ref,
        recommended_rule_update="样本不足或年度 fallback 时不得伪造 Damodaran ERP percentile。",
    )


def _feedback_contract_findings(
    inquiry_router_output: Dict[str, Any],
    investigation_reports: List[Dict[str, Any]],
) -> List[RunReviewFinding]:
    findings: List[RunReviewFinding] = []

    if inquiry_router_output:
        rejected = _as_list(inquiry_router_output.get("rejected_messages"))
        missing_reasons = [
            item.get("message_id", "unknown")
            for item in rejected
            if isinstance(item, dict) and not item.get("rejection_reason")
        ]
        if missing_reasons:
            findings.append(
                _finding(
                    "feedback",
                    "fail",
                    "InquiryRouter 有拒绝任务但缺少拒绝原因，后续无法审计为什么没有补查。",
                    ["inquiry_router_output.json"],
                    recommended_rule_update="每个 rejected InquiryMessage 必须记录 rejection_reason 和 trigger。",
                )
            )
        else:
            findings.append(
                _finding(
                    "feedback",
                    "pass",
                    "InquiryRouter 输出可审计；被拒绝的任务保留了拒绝原因和触发来源。",
                    ["inquiry_router_output.json"],
                )
            )

    if investigation_reports:
        required = {
            "finding",
            "is_deterministic_stub",
            "evidence_refs",
            "counter_evidence_refs",
            "claims_supported",
            "claims_challenged",
            "cannot_establish",
            "confidence",
            "limits",
            "source_authority",
            "effective_date",
        }
        missing_by_report: List[str] = []
        for report in investigation_reports:
            if not isinstance(report, dict):
                missing_by_report.append("unknown: not a dict")
                continue
            missing = sorted(field for field in required if field not in report)
            if missing:
                missing_by_report.append(f"{report.get('investigation_id', 'unknown')}: {', '.join(missing)}")
        if missing_by_report:
            findings.append(
                _finding(
                    "feedback",
                    "fail",
                    "InvestigationReport 缺少阶段 1 最小证据字段：" + "；".join(missing_by_report[:3]),
                    ["investigation_reports/*.json"],
                    recommended_rule_update="调查结果单必须从第一版就带证据、反证、不能证明项、来源权威和 effective_date。",
                )
            )
        else:
            findings.append(
                _finding(
                    "feedback",
                    "pass",
                    "InvestigationReport 已带最小证据、反证、限制、来源权威和 effective_date 字段。",
                    ["investigation_reports/*.json"],
                )
            )

    return findings


def _hypothesis_competition_findings(
    hypothesis_competition: Dict[str, Any],
    adjudication_history: Dict[str, Any],
) -> List[RunReviewFinding]:
    findings: List[RunReviewFinding] = []
    if not hypothesis_competition:
        findings.append(
            _finding(
                "competition",
                "fail",
                "缺少 hypothesis_competition，正式综合前没有最小竞争假说卷宗。",
                ["hypothesis_competition.json"],
                recommended_rule_update="Thesis 前必须生成至少两个竞争解释，或明确记录证据不足原因。",
            )
        )
        return findings

    hypotheses = _as_list(hypothesis_competition.get("hypotheses"))
    if len(hypotheses) >= 2:
        findings.append(
            _finding(
                "competition",
                "pass",
                f"正式综合前已有 {len(hypotheses)} 个竞争假说。",
                ["hypothesis_competition.json:hypotheses"],
            )
        )
    elif hypothesis_competition.get("insufficient_evidence_reason"):
        findings.append(
            _finding(
                "competition",
                "observe",
                "竞争假说少于两个，但已记录证据不足原因："
                + str(hypothesis_competition.get("insufficient_evidence_reason")),
                ["hypothesis_competition.json:insufficient_evidence_reason"],
            )
        )
    else:
        findings.append(
            _finding(
                "competition",
                "fail",
                "竞争假说少于两个，且没有说明为什么证据不足。",
                ["hypothesis_competition.json:hypotheses"],
                recommended_rule_update="缺少第二假说时必须显式降级，不能继续给强裁决。",
            )
        )

    forbidden = set(str(item) for item in _as_list(hypothesis_competition.get("forbidden_context_refs")))
    if "thesis_draft.json" in forbidden:
        findings.append(
            _finding(
                "competition",
                "pass",
                "Counter-Thesis 独立边界可见：首次反方构建禁止读取 Thesis。",
                ["counter_thesis.json:forbidden_context_refs", "hypothesis_competition.json:forbidden_context_refs"],
            )
        )
    else:
        findings.append(
            _finding(
                "competition",
                "fail",
                "Counter-Thesis 没有把 thesis_draft.json 列入 forbidden_context_refs，反方可能被主论点锚定。",
                ["counter_thesis.json", "hypothesis_competition.json"],
                recommended_rule_update="Counter-Thesis 首次生成只能读取 SynthesisPacket / Bridge V2，不能读取 Thesis。",
            )
        )

    fallback_warnings = _as_list(hypothesis_competition.get("fallback_warnings"))
    if fallback_warnings:
        findings.append(
            _finding(
                "competition",
                "observe",
                "主要矛盾或价格反映存在兜底痕迹，必须降级或显式标记："
                + "；".join(str(item) for item in fallback_warnings[:5]),
                ["hypothesis_competition.json:fallback_warnings"],
                recommended_rule_update="principal_contradiction / price_reflection_map 兜底生成时不能伪装成原生裁决。",
            )
        )

    change_records = _as_list(hypothesis_competition.get("downgrade_or_split_events"))
    if not change_records and adjudication_history:
        change_records = _as_list(adjudication_history.get("records"))
    if change_records:
        actionable = [
            item
            for item in change_records
            if isinstance(item, dict)
            and str(item.get("change_type") or "") in {"downgrade", "split", "reversal", "kept_unresolved"}
        ]
        if actionable:
            findings.append(
                _finding(
                    "competition",
                    "pass",
                    "强反证、调查缺口或兜底痕迹已进入非单调重判记录。",
                    ["hypothesis_competition.json:downgrade_or_split_events", "adjudication_history.json:records"],
                )
            )
        else:
            findings.append(
                _finding(
                    "competition",
                    "observe",
                    "adjudication_history 已建立初始版本，但本轮未发生降级、分叉或改判。",
                    ["adjudication_history.json:records"],
                )
            )
    else:
        findings.append(
            _finding(
                "competition",
                "observe",
                "未看到 adjudication_history 版本记录；新证据改变判断时可能难以复盘旧版本。",
                ["adjudication_history.json"],
                recommended_rule_update="竞争裁决必须保留旧判断、触发证据和改判原因。",
            )
        )

    return findings


def _evidence_claim_ledger_findings(
    evidence_registry: Dict[str, Any],
    final_claim_ledger: Dict[str, Any],
) -> List[RunReviewFinding]:
    findings: List[RunReviewFinding] = []
    passports = evidence_registry.get("passports") if isinstance(evidence_registry.get("passports"), dict) else {}
    if not evidence_registry:
        findings.append(
            _finding(
                "evidence",
                "fail",
                "缺少 evidence_registry，数据、事件、调查、假说和最终 claim 不能用同一种 evidence id 追问。",
                ["evidence_registry.json"],
                recommended_rule_update="阶段 4 必须生成统一 Evidence Passport 注册表。",
            )
        )
    elif not passports:
        findings.append(
            _finding(
                "evidence",
                "fail",
                "evidence_registry 存在但 passports 为空，证据注册表没有实际证据。",
                ["evidence_registry.json:passports"],
            )
        )
    else:
        kinds = {
            str(item.get("evidence_kind") or "")
            for item in passports.values()
            if isinstance(item, dict)
        }
        weak_without_rules = [
            evidence_id
            for evidence_id, item in passports.items()
            if isinstance(item, dict)
            and str(item.get("source_tier") or "") in {"candidate_external_material", "proxy", "derived_inference", "unknown"}
            and not _as_list(item.get("downgrade_rules"))
        ]
        if {"data", "investigation", "hypothesis"} & kinds:
            findings.append(
                _finding(
                    "evidence",
                    "pass",
                    "EvidenceRegistry 已注册主链数据、调查或假说证据，并保留统一 source tier / downgrade 规则。",
                    ["evidence_registry.json"],
                )
            )
        else:
            findings.append(
                _finding(
                    "evidence",
                    "observe",
                    "EvidenceRegistry 没看到 data/investigation/hypothesis 类型证据，最终追溯链可能不完整。",
                    ["evidence_registry.json:passports"],
                    recommended_rule_update="数据、调查和竞争假说都应进入统一 Evidence Passport。",
                )
            )
        if weak_without_rules:
            findings.append(
                _finding(
                    "evidence",
                    "fail",
                    "弱权限证据缺少 downgrade_rules，可能被误当作强证据："
                    + ", ".join(weak_without_rules[:8]),
                    ["evidence_registry.json:passports"],
                    recommended_rule_update="标题新闻、社交传闻、代理指标、派生假说必须带降级规则。",
                )
            )

    entries = _as_list(final_claim_ledger.get("entries")) if isinstance(final_claim_ledger, dict) else []
    if not final_claim_ledger:
        findings.append(
            _finding(
                "evidence",
                "fail",
                "缺少 final_claim_ledger，Final / Thesis 自然语言结论没有 claim-level 台账。",
                ["final_claim_ledger.json"],
                recommended_rule_update="Final 后必须生成 claim_id、claim_text、evidence_refs、counter_evidence_refs、inference_steps、falsification_conditions、verified。",
            )
        )
        return findings
    if not entries:
        findings.append(
            _finding(
                "evidence",
                "fail",
                "final_claim_ledger 存在但 entries 为空，重要最终结论不可追问。",
                ["final_claim_ledger.json:entries"],
            )
        )
        return findings

    required = {
        "claim_id",
        "claim_text",
        "claim_type",
        "evidence_refs",
        "counter_evidence_refs",
        "inference_steps",
        "falsification_conditions",
        "verified",
    }
    bad_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            bad_entries.append("unknown:not_a_dict")
            continue
        missing = sorted(field for field in required if field not in entry)
        thin = []
        for field in ("evidence_refs", "counter_evidence_refs", "inference_steps", "falsification_conditions"):
            if not _as_list(entry.get(field)):
                thin.append(field)
        if missing or thin:
            bad_entries.append(f"{entry.get('claim_id', 'unknown')}: missing={','.join(missing)} thin={','.join(thin)}")
    if bad_entries:
        findings.append(
            _finding(
                "evidence",
                "fail",
                "final_claim_ledger 有 claim 缺少阶段 4 必填字段或关键数组为空："
                + "；".join(bad_entries[:5]),
                ["final_claim_ledger.json:entries"],
                recommended_rule_update="每条重要 claim 必须可追到证据、反证、推理步骤和失效条件。",
            )
        )
    else:
        findings.append(
            _finding(
                "evidence",
                "pass",
                f"final_claim_ledger 已覆盖 {len(entries)} 条重要 Thesis/Final claim，且字段完整。",
                ["final_claim_ledger.json:entries"],
            )
        )

    gate = final_claim_ledger.get("publish_gate") if isinstance(final_claim_ledger.get("publish_gate"), dict) else {}
    if gate.get("status") in {"blocked", "downgraded"}:
        findings.append(
            _finding(
                "evidence",
                "observe" if gate.get("status") == "downgraded" else "fail",
                "Claim Ledger 发布闸门未完全通过："
                f"status={gate.get('status')} verified={gate.get('verified_count')}/{gate.get('entry_count')}。",
                ["final_claim_ledger.json:publish_gate"],
                recommended_rule_update="缺反证、缺失效条件或证据权限不足时，Final 必须降级或阻断强结论。",
            )
        )

    return findings


def _reader_exit_findings(golden_pit_checklist: Dict[str, Any]) -> List[RunReviewFinding]:
    if not golden_pit_checklist:
        return [
            _finding(
                "expression",
                "observe",
                "缺少 golden_pit_checklist，阶段 5 读者出口还不能回答“距买入/卖出条件还差什么证据”。",
                ["golden_pit_checklist.json"],
                recommended_rule_update="Final/ClaimLedger 后应生成只供读者出口消费的 golden_pit_checklist.json。",
            )
        ]
    entries = _as_list(golden_pit_checklist.get("entries"))
    required = {"condition", "evidence_refs", "current_status", "falsification_conditions", "changed_since_last_run"}
    bad_entries = []
    for item in entries:
        if not isinstance(item, dict):
            bad_entries.append("not_a_dict")
            continue
        missing = sorted(field for field in required if field not in item)
        if missing:
            bad_entries.append(f"{item.get('condition_id', 'unknown')}: missing={','.join(missing)}")
    no_backflow = str(golden_pit_checklist.get("no_backflow_rule") or "")
    if not entries or bad_entries:
        return [
            _finding(
                "expression",
                "fail",
                "golden_pit_checklist 字段不完整，读者出口无法审计条件差距："
                + "；".join(bad_entries[:5]),
                ["golden_pit_checklist.json:entries"],
                recommended_rule_update="每条黄金坑条件必须包含 condition/evidence_refs/current_status/falsification_conditions/changed_since_last_run。",
            )
        ]
    severity = "pass" if "must not feed back" in no_backflow or "不得" in no_backflow else "observe"
    return [
        _finding(
            "expression",
            severity,
            f"golden_pit_checklist 已覆盖 {len(entries)} 条读者条件，并声明只属于读者出口层。",
            ["golden_pit_checklist.json"],
            recommended_rule_update="" if severity == "pass" else "golden_pit_checklist 必须显式声明不得回流 L1-L5/Bridge/Thesis/Final。",
        )
    ]


def _finding(
    category: str,
    severity: str,
    finding: str,
    artifact_refs: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
    recommended_rule_update: str = "",
) -> RunReviewFinding:
    return RunReviewFinding(
        category=category,
        severity=severity,
        finding=finding,
        artifact_refs=artifact_refs or [],
        evidence_refs=evidence_refs or [],
        recommended_rule_update=recommended_rule_update,
    )


def build_run_review_report(
    *,
    run_dir: str = "",
    analysis_packet: Optional[Dict[str, Any]] = None,
    bridges: Optional[List[Dict[str, Any]]] = None,
    synthesis_packet: Optional[Dict[str, Any]] = None,
    thesis_draft: Optional[Dict[str, Any]] = None,
    risk_boundary_report: Optional[Dict[str, Any]] = None,
    schema_guard_report: Optional[Dict[str, Any]] = None,
    final_adjudication: Optional[Dict[str, Any]] = None,
    data_integrity_report: Optional[Dict[str, Any]] = None,
    run_summary: Optional[Dict[str, Any]] = None,
    inquiry_router_output: Optional[Dict[str, Any]] = None,
    investigation_reports: Optional[List[Dict[str, Any]]] = None,
    hypothesis_competition: Optional[Dict[str, Any]] = None,
    adjudication_history: Optional[Dict[str, Any]] = None,
    evidence_registry: Optional[Dict[str, Any]] = None,
    final_claim_ledger: Optional[Dict[str, Any]] = None,
    golden_pit_checklist: Optional[Dict[str, Any]] = None,
) -> RunReviewReport:
    analysis_packet = analysis_packet or {}
    bridges = bridges or []
    synthesis_packet = synthesis_packet or {}
    thesis_draft = thesis_draft or {}
    risk_boundary_report = risk_boundary_report or {}
    schema_guard_report = schema_guard_report or {}
    final_adjudication = final_adjudication or {}
    data_integrity_report = data_integrity_report or {}
    run_summary = run_summary or {}
    inquiry_router_output = inquiry_router_output or {}
    investigation_reports = investigation_reports or []
    hypothesis_competition = hypothesis_competition or {}
    adjudication_history = adjudication_history or {}
    evidence_registry = evidence_registry or {}
    final_claim_ledger = final_claim_ledger or {}
    golden_pit_checklist = golden_pit_checklist or {}

    findings: List[RunReviewFinding] = []

    meta = analysis_packet.get("meta", {}) if isinstance(analysis_packet.get("meta"), dict) else {}
    publish_status = data_integrity_report.get("publish_status") or ("blocked" if data_integrity_report.get("blocked") else "")
    boundaries = meta.get("backtest_data_boundaries") or analysis_packet.get("context", {}).get("backtest_data_boundaries", [])
    invariants = meta.get("strict_backtest_invariants") or analysis_packet.get("context", {}).get("strict_backtest_invariants", {})

    if publish_status in {"blocked", "unpublishable"} or data_integrity_report.get("blocked"):
        findings.append(
            _finding(
                "data",
                "fail",
                "DataIntegrity 阻断或不可发布，不能把报告继续当作可发布结论。",
                ["data_integrity_report.json"],
                recommended_rule_update="DataIntegrity blocked/unpublishable 必须继续作为发布闸门。",
            )
        )
    else:
        findings.append(
            _finding(
                "data",
                "pass",
                "DataIntegrity 未阻断；数据边界可进入后续判断。",
                ["data_integrity_report.json"],
            )
        )

    if meta.get("backtest_date") or run_summary.get("backtest_date"):
        if boundaries or invariants:
            findings.append(
                _finding(
                    "data",
                    "pass",
                    "回测边界或 strict invariant 已入包，缺口没有被静默抹平。",
                    ["analysis_packet.json", "run_summary.json"],
                )
            )
        else:
            findings.append(
                _finding(
                    "data",
                    "observe",
                    "这是回测/快照语境，但未看到 backtest_data_boundaries 或 strict_backtest_invariants。",
                    ["analysis_packet.json", "run_summary.json"],
                    recommended_rule_update="回测产物必须携带数据边界和 invariant 元数据。",
                )
            )

    findings.append(_damodaran_review_finding(analysis_packet, meta.get("backtest_date") or run_summary.get("backtest_date")))
    findings.extend(_feedback_contract_findings(inquiry_router_output, investigation_reports))
    findings.extend(_hypothesis_competition_findings(hypothesis_competition, adjudication_history))
    findings.extend(_evidence_claim_ledger_findings(evidence_registry, final_claim_ledger))
    findings.extend(_reader_exit_findings(golden_pit_checklist))

    if schema_guard_report:
        if schema_guard_report.get("passed") is False:
            issues = []
            issues.extend(_as_list(schema_guard_report.get("structural_issues")))
            issues.extend(_as_list(schema_guard_report.get("consistency_issues")))
            issues.extend(_as_list(schema_guard_report.get("missing_fields")))
            findings.append(
                _finding(
                    "final",
                    "fail",
                    "Schema Guard 未通过，不能把本轮报告理解为结构完整的可发布结论。"
                    + (" 示例: " + "；".join(str(item) for item in issues[:3]) if issues else ""),
                    ["schema_guard_report.json"],
                    recommended_rule_update="schema_guard_report.passed=false 必须进入 run_summary 质量状态和 Run Review fail。",
                )
            )
        else:
            findings.append(
                _finding(
                    "final",
                    "pass",
                    "Schema Guard 通过；关键结构、引用和一致性检查未发现阻断问题。",
                    ["schema_guard_report.json"],
                )
            )

    bridge = bridges[0] if bridges else {}
    normalization_notes = _as_list(bridge.get("normalization_notes")) if isinstance(bridge, dict) else []
    typed_conflicts = _as_list(bridge.get("typed_conflicts"))
    principal = bridge.get("principal_contradiction") if isinstance(bridge.get("principal_contradiction"), dict) else {}
    price_map = _as_list(bridge.get("price_reflection_map"))
    if not bridges:
        findings.append(_finding("bridge", "fail", "缺少 Bridge artifact，跨层关系无法复盘。", ["bridge_memos/bridge_0.json"]))
    elif not principal:
        findings.append(
            _finding(
                "bridge",
                "fail" if typed_conflicts else "observe",
                "Bridge 未输出 principal_contradiction；主要矛盾仍可能被 Thesis 自行脑补。",
                ["bridge_memos/bridge_0.json"],
                _collect_refs(typed_conflicts),
                "Bridge 必须原生输出主要矛盾；legacy 兜底只能作为兼容，不应长期依赖。",
            )
        )
    else:
        findings.append(
            _finding(
                "bridge",
                "pass",
                "Bridge 已输出主要矛盾，可供 Thesis 消费。",
                ["bridge_memos/bridge_0.json:principal_contradiction"],
                _collect_refs(principal),
            )
        )
    if normalization_notes:
        findings.append(
            _finding(
                "bridge",
                "observe",
                "Bridge 有代码归一化/兜底补全痕迹，需要区分模型原生理解和兼容层补齐字段: "
                + "；".join(str(item) for item in normalization_notes[:5]),
                ["bridge_memos/bridge_0.json:normalization_notes"],
                recommended_rule_update="Bridge 的 principal_contradiction 与 price_reflection_map 应尽量由模型原生输出；代码兜底只保留为兼容和复盘线索。",
            )
        )
    if not price_map:
        findings.append(
            _finding(
                "bridge",
                "observe",
                "Bridge 未输出 price_reflection_map；价格是否已反映风险仍缺结构化判断。",
                ["bridge_memos/bridge_0.json:price_reflection_map"],
                recommended_rule_update="Bridge 必须判断关键风险/叙事是否已进入价格。",
            )
        )
    else:
        categories = {str(item.get("category") or "") for item in price_map if isinstance(item, dict)}
        missing_categories = sorted(REQUIRED_PRICE_REFLECTION_CATEGORIES - categories)
        thin_items = [
            str(item.get("category") or item.get("target") or "price_reflection")
            for item in price_map
            if isinstance(item, dict)
            and (
                not item.get("rationale")
                or (not _as_list(item.get("counterevidence")) and not _as_list(item.get("counterevidence_refs")))
                or not item.get("action_implication")
            )
        ]
        if missing_categories:
            findings.append(
                _finding(
                    "bridge",
                    "observe",
                    "Bridge price_reflection_map 未覆盖五类价格反映："
                    + ", ".join(missing_categories),
                    ["bridge_memos/bridge_0.json:price_reflection_map"],
                    recommended_rule_update="价格反映地图至少拆成 credit/rates/valuation/technical_panic/liquidity 五类。",
                )
            )
        elif thin_items:
            findings.append(
                _finding(
                    "bridge",
                    "observe",
                    "Bridge price_reflection_map 覆盖五类，但部分项缺少反证或动作含义："
                    + ", ".join(thin_items[:5]),
                    ["bridge_memos/bridge_0.json:price_reflection_map"],
                    recommended_rule_update="每类价格反映必须同时写 reflected_state、证据、反证和动作影响。",
                )
            )
        else:
            findings.append(
                _finding(
                    "bridge",
                    "pass",
                    "Bridge price_reflection_map 已覆盖信用、利率、估值、技术恐慌、流动性五类，并包含反证与动作含义。",
                    ["bridge_memos/bridge_0.json:price_reflection_map"],
                )
            )

    thesis_principal = thesis_draft.get("principal_contradiction") if isinstance(thesis_draft.get("principal_contradiction"), dict) else {}
    if not thesis_principal:
        findings.append(
            _finding(
                "thesis",
                "fail",
                "Thesis 未结构化输出主要矛盾，后续 Final 可能退回单一立场。",
                ["thesis_draft.json:principal_contradiction"],
                recommended_rule_update="Thesis 必须消费 Bridge 主要矛盾并说明价格反映与行动含义。",
            )
        )
    elif not thesis_principal.get("price_reflection"):
        findings.append(
            _finding(
                "thesis",
                "observe",
                "Thesis 有主要矛盾，但未说明价格反映程度。",
                ["thesis_draft.json:principal_contradiction.price_reflection"],
                _collect_refs(thesis_principal),
            )
        )
    else:
        findings.append(
            _finding(
                "thesis",
                "pass",
                "Thesis 已把主要矛盾与价格反映绑定。",
                ["thesis_draft.json:principal_contradiction"],
                _collect_refs(thesis_principal),
            )
        )

    if not thesis_draft.get("priced_narrative") or not thesis_draft.get("payoff_assessment"):
        findings.append(
            _finding(
                "thesis",
                "observe",
                "Thesis 的价格叙事或赔率判断为空，容易回到风险清单式表达。",
                ["thesis_draft.json:priced_narrative", "thesis_draft.json:payoff_assessment"],
                recommended_rule_update="状态、价格、赔率三个面必须同时非空。",
            )
        )

    opportunity_costs = _as_list(risk_boundary_report.get("opportunity_costs"))
    confirmation_costs = _as_list(risk_boundary_report.get("confirmation_costs"))
    false_safety = _as_list(risk_boundary_report.get("false_safety_risks"))
    if not risk_boundary_report:
        findings.append(_finding("risk", "fail", "缺少 Risk Sentinel artifact。", ["risk_boundary_report.json"]))
    elif not opportunity_costs or not confirmation_costs:
        findings.append(
            _finding(
                "risk",
                "observe",
                "Risk Sentinel 未完整输出踏空/确认成本，双向风险仍不稳。",
                ["risk_boundary_report.json:opportunity_costs", "risk_boundary_report.json:confirmation_costs"],
                recommended_rule_update="等待确认必须被当作有成本的选择，而不是默认安全答案。",
            )
        )
    else:
        findings.append(
            _finding(
                "risk",
                "pass",
                "Risk Sentinel 已输出踏空/确认成本。",
                ["risk_boundary_report.json"],
                _collect_refs(opportunity_costs + confirmation_costs + false_safety),
            )
        )

    final_principal = final_adjudication.get("principal_contradiction") if isinstance(final_adjudication.get("principal_contradiction"), dict) else {}
    reader = final_adjudication.get("reader_final") if isinstance(final_adjudication.get("reader_final"), dict) else {}
    if not final_principal:
        findings.append(
            _finding(
                "final",
                "fail",
                "Final 未保留 principal_contradiction，读者可能看不到真正支配判断的矛盾。",
                ["final_adjudication.json:principal_contradiction"],
                recommended_rule_update="Final 必须把主要矛盾带进最终读者判断。",
            )
        )
    else:
        findings.append(
            _finding(
                "final",
                "pass",
                "Final 已保留主要矛盾。",
                ["final_adjudication.json:principal_contradiction"],
                _collect_refs(final_principal),
            )
        )

    if _payoff_language_mismatch(final_adjudication):
        findings.append(
            _finding(
                "final",
                "fail",
                "Final 赔率语言自相矛盾：final_stance/reader_final 使用高赔率表达，但 payoff_assessment 同时写赔率或风险收益比不利。",
                ["final_adjudication.json:final_stance", "final_adjudication.json:payoff_assessment", "final_adjudication.json:reader_final"],
                recommended_rule_update="Final 的最终立场、读者一句话和 payoff_assessment 必须方向一致；赔率不利时不得写成高赔率候选。",
            )
        )

    if not reader.get("one_liner"):
        findings.append(
            _finding(
                "expression",
                "fail",
                "reader_final.one_liner 为空，读者首屏结论不足。",
                ["final_adjudication.json:reader_final.one_liner"],
            )
        )
    else:
        internal_hits = [phrase for phrase in INTERNAL_READER_PHRASES if phrase.lower() in _reader_text(final_adjudication).lower()]
        if internal_hits:
            findings.append(
                _finding(
                    "expression",
                    "fail",
                    "读者结论混入内部审批话术：" + ", ".join(internal_hits),
                    ["final_adjudication.json:reader_final"],
                    recommended_rule_update="reader_final 只写读者行动语言，内部质检留在 quality_gate/adjudicator_notes。",
                )
            )
        else:
            findings.append(
                _finding(
                    "expression",
                    "pass",
                    "reader_final 未发现明显内部审批话术。",
                    ["final_adjudication.json:reader_final"],
                )
            )

    learning_updates = [
        finding.recommended_rule_update
        for finding in findings
        if finding.recommended_rule_update
    ]
    next_run_checks = [
        "检查 Bridge principal_contradiction 是否原生生成，而非只靠 normalize 兜底。",
        "检查 Thesis/Final 是否都保留主要矛盾、价格反映和行动含义。",
        "检查 Risk 是否同时输出下行风险、踏空风险和确认成本。",
        "检查 reader_final 是否没有内部审批话术。",
    ]

    return RunReviewReport(
        run_dir=run_dir,
        backtest_date=meta.get("backtest_date") or run_summary.get("backtest_date"),
        final_stance=final_adjudication.get("final_stance", ""),
        approval_status=str(final_adjudication.get("approval_status", "")),
        publish_status=str(publish_status or ""),
        attribution_findings=findings,
        learning_updates=list(dict.fromkeys(learning_updates)),
        next_run_checks=next_run_checks,
    )


def build_run_review_from_dir(run_dir: str | Path) -> RunReviewReport:
    run_path = Path(run_dir)
    bridge_dir = run_path / "bridge_memos"
    investigation_dir = run_path / "investigation_reports"
    bridges = [
        _load_json(path, {})
        for path in sorted(bridge_dir.glob("*.json"))
        if path.is_file()
    ]
    investigation_reports = [
        _load_json(path, {})
        for path in sorted(investigation_dir.glob("*.json"))
        if path.is_file()
    ]
    return build_run_review_report(
        run_dir=str(run_path),
        analysis_packet=_load_json(run_path / "analysis_packet.json", {}),
        bridges=bridges,
        synthesis_packet=_load_json(run_path / "synthesis_packet.json", {}),
        thesis_draft=_load_json(run_path / "thesis_draft.json", {}),
        risk_boundary_report=_load_json(run_path / "risk_boundary_report.json", {}),
        schema_guard_report=_load_json(run_path / "schema_guard_report.json", {}),
        final_adjudication=_load_json(run_path / "final_adjudication.json", {}),
        data_integrity_report=_load_json(run_path / "data_integrity_report.json", {}),
        run_summary=_load_json(run_path / "run_summary.json", {}),
        inquiry_router_output=_load_json(run_path / "inquiry_router_output.json", {}),
        investigation_reports=investigation_reports,
        hypothesis_competition=_load_json(run_path / "hypothesis_competition.json", {}),
        adjudication_history=_load_json(run_path / "adjudication_history.json", {}),
        evidence_registry=_load_json(run_path / "evidence_registry.json", {}),
        final_claim_ledger=_load_json(run_path / "final_claim_ledger.json", {}),
        golden_pit_checklist=_load_json(run_path / "golden_pit_checklist.json", {}),
    )


def write_run_review_report(run_dir: str | Path, output_path: str | Path | None = None) -> Path:
    report = build_run_review_from_dir(run_dir)
    target = Path(output_path) if output_path else Path(run_dir) / "run_review_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a vNext run review artifact.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    path = write_run_review_report(args.run_dir, args.output)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
