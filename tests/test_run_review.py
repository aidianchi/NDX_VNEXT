import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.run_review import build_run_review_from_dir, build_run_review_report


def test_run_review_attributes_missing_main_chain_fields():
    report = build_run_review_report(
        run_dir="output/analysis/vnext/test",
        analysis_packet={"meta": {"backtest_date": "2025-04-09"}},
        bridges=[
            {
                "typed_conflicts": [
                    {
                        "conflict_id": "risk_vs_payoff",
                        "severity": "high",
                        "description": "风险仍高但价格可能已反映坏消息。",
                        "evidence_refs": ["L4.valuation"],
                    }
                ]
            }
        ],
        thesis_draft={
            "priced_narrative": "",
            "payoff_assessment": "",
        },
        risk_boundary_report={
            "must_preserve_risks": ["信用恶化风险"],
        },
        final_adjudication={
            "final_stance": "中性偏谨慎",
            "approval_status": "approved_with_reservations",
            "reader_final": {"one_liner": "批准进入最终报告。"},
        },
        data_integrity_report={"publish_status": "publishable"},
    )

    findings = {(item.category, item.severity) for item in report.attribution_findings}

    assert ("bridge", "fail") in findings
    assert ("thesis", "fail") in findings
    assert ("risk", "observe") in findings
    assert ("final", "fail") in findings
    assert ("expression", "fail") in findings
    assert any("reader_final" in item.recommended_rule_update for item in report.attribution_findings)


def test_run_review_from_dir_reads_schema_guard_report(tmp_path):
    (tmp_path / "schema_guard_report.json").write_text(
        json.dumps(
            {
                "passed": False,
                "quality_status": "review_required",
                "structural_issues": ["Bridge 缺少 typed_conflicts evidence_refs"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "data_integrity_report.json").write_text('{"publish_status":"publishable"}', encoding="utf-8")
    (tmp_path / "final_adjudication.json").write_text(
        json.dumps(
            {
                "final_stance": "测试",
                "approval_status": "approved_with_reservations",
                "reader_final": {"one_liner": "测试结论。"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_run_review_from_dir(tmp_path)

    assert any(
        item.category == "final" and item.severity == "fail" and "Schema Guard 未通过" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_audits_rejected_inquiry_router_messages():
    report = build_run_review_report(
        inquiry_router_output={
            "rejected_messages": [
                {
                    "message_id": "inq_missing_context",
                    "message_type": "observation_inquiry",
                    "status": "rejected",
                    "rejection_reason": "missing_allowed_context_refs",
                    "trigger": "L1 数据异常。",
                }
            ]
        },
        data_integrity_report={"publish_status": "publishable"},
    )

    assert any(
        item.category == "feedback" and item.severity == "pass" and "拒绝原因" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_fails_investigation_report_missing_minimal_fields():
    report = build_run_review_report(
        investigation_reports=[
            {
                "investigation_id": "inv_bad",
                "originating_agent_id": "agent_bad",
                "finding": "只有结论，没有证据字段。",
                "effective_date": "2026-07-06",
            }
        ],
        data_integrity_report={"publish_status": "publishable"},
    )

    assert any(
        item.category == "feedback" and item.severity == "fail" and "最小证据字段" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_audits_hypothesis_competition_and_independent_counter_thesis():
    report = build_run_review_report(
        data_integrity_report={"publish_status": "publishable"},
        hypothesis_competition={
            "schema_version": "hypothesis_competition_v1",
            "forbidden_context_refs": ["thesis_draft.json", "final_adjudication.json"],
            "hypotheses": [
                {
                    "hypothesis_id": "hyp_base",
                    "hypothesis_text": "主线解释。",
                    "support_evidence_refs": ["L4.valuation"],
                    "counter_evidence_refs": ["investigation_reports/inv_gap.json"],
                    "diagnostic_evidence_refs": ["L4.valuation"],
                    "cannot_explain": ["价格反映不清。"],
                    "falsification_conditions": ["估值压力解除。"],
                },
                {
                    "hypothesis_id": "hyp_counter",
                    "hypothesis_text": "反方解释。",
                    "support_evidence_refs": ["investigation_reports/inv_gap.json"],
                    "counter_evidence_refs": ["L4.valuation"],
                    "diagnostic_evidence_refs": ["investigation_reports/inv_gap.json"],
                    "cannot_explain": ["不能证明主线错误。"],
                    "falsification_conditions": ["反证被正式数据排除。"],
                },
            ],
            "downgrade_or_split_events": [
                {
                    "version_id": "adj_1",
                    "change_type": "kept_unresolved",
                    "trigger_evidence_refs": ["investigation_reports/inv_gap.json"],
                    "reason": "强反证进入争议保留。",
                }
            ],
        },
        adjudication_history={"records": []},
    )

    assert any(
        item.category == "competition" and item.severity == "pass" and "竞争假说" in item.finding
        for item in report.attribution_findings
    )
    assert any(
        item.category == "competition" and item.severity == "pass" and "禁止读取 Thesis" in item.finding
        for item in report.attribution_findings
    )
    assert any(
        item.category == "competition" and item.severity == "pass" and "非单调重判记录" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_fails_when_hypothesis_competition_missing():
    report = build_run_review_report(data_integrity_report={"publish_status": "publishable"})

    assert any(
        item.category == "competition" and item.severity == "fail" and "缺少 hypothesis_competition" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_audits_stage4_evidence_registry_and_claim_ledger():
    report = build_run_review_report(
        data_integrity_report={"publish_status": "publishable"},
        evidence_registry={
            "schema_version": "evidence_registry_v1",
            "passports": {
                "L1.get_10y_real_rate": {
                    "evidence_id": "L1.get_10y_real_rate",
                    "evidence_kind": "data",
                    "source_tier": "official",
                    "downgrade_rules": [],
                    "verified": True,
                },
                "hyp_base": {
                    "evidence_id": "hyp_base",
                    "evidence_kind": "hypothesis",
                    "source_tier": "derived_inference",
                    "downgrade_rules": ["derived_inference_cannot_replace_underlying_evidence"],
                    "verified": False,
                },
            },
        },
        final_claim_ledger={
            "schema_version": "claim_ledger_v1",
            "entries": [
                {
                    "claim_id": "claim:final:rates",
                    "claim_text": "真实利率仍压制估值。",
                    "claim_type": "market_state",
                    "evidence_refs": ["L1.get_10y_real_rate"],
                    "counter_evidence_refs": ["hyp_base"],
                    "inference_steps": ["真实利率影响折现率。"],
                    "falsification_conditions": ["真实利率快速回落。"],
                    "verified": True,
                    "authority_status": "verified",
                }
            ],
            "publish_gate": {"status": "pass", "entry_count": 1, "verified_count": 1},
        },
    )

    assert any(
        item.category == "evidence" and item.severity == "pass" and "EvidenceRegistry" in item.finding
        for item in report.attribution_findings
    )
    assert any(
        item.category == "evidence" and item.severity == "pass" and "final_claim_ledger" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_passes_stage5_golden_pit_checklist_when_complete():
    report = build_run_review_report(
        data_integrity_report={"publish_status": "publishable"},
        golden_pit_checklist={
            "schema_version": "golden_pit_checklist_v1",
            "no_backflow_rule": "GoldenPitChecklist must not feed back into L1-L5 or upstream prompts.",
            "entries": [
                {
                    "condition_id": "buy_value_discount_confirmed",
                    "condition": "价值买入纪律",
                    "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
                    "current_status": "not_met",
                    "falsification_conditions": ["估值安全垫明显改善。"],
                    "changed_since_last_run": {"changed": False},
                }
            ],
        },
    )

    assert any(
        item.category == "expression" and item.severity == "pass" and "golden_pit_checklist" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_passes_when_main_chain_fields_exist():
    principal = {
        "contradiction_id": "panic_priced_vs_unconfirmed_risk",
        "summary": "风险未解除但价格可能部分反映坏消息。",
        "price_reflection": "partially_reflected",
        "evidence_refs": ["L4.valuation"],
    }
    report = build_run_review_report(
        run_dir="output/analysis/vnext/test",
        analysis_packet={
            "meta": {
                "backtest_date": "2025-04-09",
                "backtest_data_boundaries": [{"function_id": "x"}],
                "strict_backtest_invariants": {"schema_version": "v1"},
            }
        },
        bridges=[
            {
                "principal_contradiction": principal,
                "price_reflection_map": [
                    {
                        "target": "panic_priced_vs_unconfirmed_risk",
                        "reflected_state": "partially_reflected",
                    }
                ],
            }
        ],
        thesis_draft={
            "principal_contradiction": principal,
            "priced_narrative": "坏消息部分进入价格。",
            "payoff_assessment": "高风险高赔率候选。",
        },
        risk_boundary_report={
            "must_preserve_risks": ["信用恶化风险"],
            "opportunity_costs": [{"condition": "等待全部确认"}],
            "confirmation_costs": [{"wait_for": "趋势确认"}],
        },
        final_adjudication={
            "final_stance": "高风险高赔率候选",
            "approval_status": "approved_with_reservations",
            "principal_contradiction": principal,
            "reader_final": {"one_liner": "风险高，但赔率可能改善。"},
        },
        data_integrity_report={"publish_status": "publishable"},
    )

    categories = {(item.category, item.severity) for item in report.attribution_findings}

    assert ("bridge", "pass") in categories
    assert ("thesis", "pass") in categories
    assert ("risk", "pass") in categories
    assert ("final", "pass") in categories
    assert ("expression", "pass") in categories


def test_run_review_observes_thin_price_reflection_map():
    report = build_run_review_report(
        run_dir="output/analysis/vnext/test",
        analysis_packet={"meta": {"backtest_date": "2025-04-09"}},
        bridges=[
            {
                "principal_contradiction": {"summary": "风险与赔率拉扯。", "price_reflection": "partially_reflected"},
                "price_reflection_map": [
                    {
                        "category": "valuation",
                        "target": "valuation_risk_premium",
                        "reflected_state": "partially_reflected",
                        "rationale": "估值压缩。",
                    }
                ],
            }
        ],
        thesis_draft={
            "principal_contradiction": {"summary": "风险与赔率拉扯。", "price_reflection": "partially_reflected"},
            "priced_narrative": "坏消息部分进入价格。",
            "payoff_assessment": "高风险高赔率候选。",
        },
        risk_boundary_report={
            "must_preserve_risks": ["信用恶化风险"],
            "opportunity_costs": [{"condition": "等待全部确认"}],
            "confirmation_costs": [{"wait_for": "趋势确认"}],
        },
        final_adjudication={
            "final_stance": "高风险高赔率候选",
            "approval_status": "approved_with_reservations",
            "principal_contradiction": {"summary": "风险与赔率拉扯。", "price_reflection": "partially_reflected"},
            "reader_final": {"one_liner": "风险高，但赔率可能改善。"},
        },
        data_integrity_report={"publish_status": "publishable"},
    )

    assert any(
        item.category == "bridge"
        and item.severity == "observe"
        and "credit" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_fails_inconsistent_high_payoff_final_language():
    principal = {
        "contradiction_id": "valuation_vs_rates",
        "summary": "估值和利率拉扯。",
        "price_reflection": "partially_reflected",
        "evidence_refs": ["L4.valuation"],
    }
    report = build_run_review_report(
        bridges=[
            {
                "principal_contradiction": principal,
                "price_reflection_map": [
                    {
                        "category": "credit",
                        "target": "credit",
                        "reflected_state": "unclear",
                        "rationale": "信用未确认。",
                        "counterevidence": ["信用可能恶化。"],
                        "action_implication": "限制动作。",
                    },
                    {
                        "category": "rates",
                        "target": "rates",
                        "reflected_state": "not_reflected",
                        "rationale": "利率压力仍在。",
                        "counterevidence": ["利率可能回落。"],
                        "action_implication": "限制核心仓。",
                    },
                    {
                        "category": "valuation",
                        "target": "valuation",
                        "reflected_state": "partially_reflected",
                        "rationale": "估值已有压缩。",
                        "counterevidence": ["盈利可能下修。"],
                        "action_implication": "只支持战术。",
                    },
                    {
                        "category": "technical_panic",
                        "target": "technical",
                        "reflected_state": "partially_reflected",
                        "rationale": "短线恐慌部分释放。",
                        "counterevidence": ["跌破低点会失效。"],
                        "action_implication": "需要触发条件。",
                    },
                    {
                        "category": "liquidity",
                        "target": "liquidity",
                        "reflected_state": "unclear",
                        "rationale": "流动性不清楚。",
                        "counterevidence": ["流动性可能收缩。"],
                        "action_implication": "保留复核。",
                    },
                ],
            }
        ],
        thesis_draft={
            "principal_contradiction": principal,
            "priced_narrative": "坏消息部分进入价格。",
            "payoff_assessment": "风险收益比不利。",
        },
        risk_boundary_report={
            "must_preserve_risks": ["估值压缩"],
            "opportunity_costs": [{"condition": "等待确认"}],
            "confirmation_costs": [{"wait_for": "趋势确认"}],
        },
        final_adjudication={
            "final_stance": "高赔率候选，战术仓分批。",
            "approval_status": "approved_with_reservations",
            "principal_contradiction": principal,
            "payoff_assessment": "当前赔率不对称偏向下行，整体风险收益比不利。",
            "reader_final": {"one_liner": "风险高但高赔率，动作要分批。"},
        },
        data_integrity_report={"publish_status": "publishable"},
    )

    assert any(
        item.category == "final"
        and item.severity == "fail"
        and "赔率语言自相矛盾" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_reports_damodaran_erp_percentile_boundary():
    report = build_run_review_report(
        analysis_packet={
            "raw_data": {
                "L4": {
                    "get_damodaran_us_implied_erp": {
                        "value": {
                            "data_date": "2026-05-01",
                            "erp_t12m_adjusted_payout": 4.24,
                            "damodaran_erp_historical_percentiles": {
                                "windows": {
                                    "5y": {"percentile": 42.7, "status": "available", "sample_count": 60, "required_min_months": 60},
                                    "10y": {"percentile": 37.5, "status": "available", "sample_count": 120, "required_min_months": 120},
                                }
                            },
                        }
                    }
                }
            }
        },
        data_integrity_report={"publish_status": "publishable"},
    )

    assert any(
        item.category == "data"
        and item.severity == "pass"
        and "Damodaran ERP 官方月度分位可用" in item.finding
        and "5Y=42.7%" in item.finding
        and "10Y=37.5%" in item.finding
        for item in report.attribution_findings
    )


def test_run_review_fails_damodaran_erp_percentile_after_backtest_date():
    report = build_run_review_report(
        analysis_packet={
            "meta": {"backtest_date": "2025-04-09"},
            "raw_data": {
                "L4": {
                    "get_damodaran_us_implied_erp": {
                        "value": {
                            "data_date": "2026-05-01",
                            "erp_t12m_adjusted_payout": 4.24,
                            "damodaran_erp_historical_percentiles": {
                                "windows": {
                                    "5y": {"percentile": 42.7, "status": "available", "sample_count": 60, "required_min_months": 60},
                                    "10y": {"percentile": 37.5, "status": "available", "sample_count": 120, "required_min_months": 120},
                                }
                            },
                        }
                    }
                }
            },
        },
        data_integrity_report={"publish_status": "publishable"},
    )

    assert any(
        item.category == "data"
        and item.severity == "fail"
        and "晚于回测日" in item.finding
        for item in report.attribution_findings
    )
