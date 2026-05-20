import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.run_review import build_run_review_report


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
