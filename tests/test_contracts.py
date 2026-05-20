import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    Layer,
    Confidence,
    ApprovalStatus,
    ConflictSeverity,
    PermissionType,
    LayerCard,
    BridgeMemo,
    ThesisDraft,
    RiskBoundaryReport,
    AnalysisRevised,
    FinalAdjudication,
    PriceReflectionAssessment,
    PrincipalContradiction,
    ReaderFinal,
    SecondaryContradiction,
)


def test_layer_enum_values():
    assert Layer.L1.value == "L1"
    assert Layer.L5.value == "L5"


def test_confidence_enum_values():
    assert Confidence.HIGH.value == "high"
    assert Confidence.LOW.value == "low"


def test_approval_status_enum_values():
    assert ApprovalStatus.APPROVED_WITH_RESERVATIONS.value == "approved_with_reservations"


def test_conflict_severity_enum_values():
    assert ConflictSeverity.HIGH.value == "high"


def test_permission_type_enum_values():
    assert PermissionType.PROXY.value == "proxy"


def test_layer_analysis_serialization():
    analysis = LayerCard(
        layer=Layer.L1,
        core_facts=[{"metric": "fed_rate", "value": 5.25}],
        local_conclusion="流动性偏紧。",
        confidence=Confidence.MEDIUM,
        indicator_analyses=[],
    )
    data = analysis.model_dump()
    assert data["layer"] == "L1"
    assert data["local_conclusion"] == "流动性偏紧。"
    assert isinstance(data["generated_at"], datetime)


def test_layer_analysis_generated_at_is_utc():
    before = datetime.now(timezone.utc)
    analysis = LayerCard(
        layer=Layer.L4,
        core_facts=[{"metric": "pe", "value": 32.5}],
        local_conclusion="估值偏高。",
        confidence=Confidence.MEDIUM,
        indicator_analyses=[],
    )
    after = datetime.now(timezone.utc)
    assert before <= analysis.generated_at <= after
    assert analysis.generated_at.tzinfo is not None


def test_bridge_memo_generated_at_is_utc():
    before = datetime.now(timezone.utc)
    memo = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=[Layer.L1, Layer.L4],
        implication_for_ndx="高利率压制估值。",
    )
    after = datetime.now(timezone.utc)
    assert before <= memo.generated_at <= after


def test_thesis_draft_generated_at_is_utc():
    before = datetime.now(timezone.utc)
    thesis = ThesisDraft(
        environment_assessment="环境偏紧。",
        valuation_assessment="估值偏高。",
        timing_assessment="趋势存疑。",
        main_thesis="中性偏谨慎。",
        overall_confidence=Confidence.MEDIUM,
    )
    after = datetime.now(timezone.utc)
    assert before <= thesis.generated_at <= after


def test_risk_boundary_report_generated_at_is_utc():
    before = datetime.now(timezone.utc)
    report = RiskBoundaryReport(
        failure_conditions=[],
        boundary_status={},
        must_preserve_risks=[],
        conflict_matrix_check={},
    )
    after = datetime.now(timezone.utc)
    assert before <= report.generated_at <= after


def test_analysis_revised_generated_at_is_utc():
    before = datetime.now(timezone.utc)
    revised = AnalysisRevised(
        revision_summary="修订说明",
        accepted_critiques=[],
        rejected_critiques=[],
        revised_thesis={
            "environment_assessment": "环境偏紧。",
            "valuation_assessment": "估值偏高。",
            "timing_assessment": "趋势存疑。",
            "main_thesis": "中性偏谨慎。",
            "overall_confidence": Confidence.MEDIUM,
        },
    )
    after = datetime.now(timezone.utc)
    assert before <= revised.generated_at <= after


def test_final_adjudication_generated_at_is_utc():
    before = datetime.now(timezone.utc)
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="中性偏谨慎",
        confidence=Confidence.MEDIUM,
        key_support_chains=[],
        must_preserve_risks=[],
        blocking_issues=[],
        evidence_refs=[],
        adjudicator_notes="可以放行，但必须保留风险边界。",
    )
    after = datetime.now(timezone.utc)
    assert before <= final.generated_at <= after


def test_layer_analysis_core_facts_min_length():
    """LayerCard 要求 core_facts 至少有一条。"""
    try:
        LayerCard(
            layer=Layer.L1,
            core_facts=[],
            local_conclusion="测试",
            indicator_analyses=[],
        )
        assert False, "应该因为 core_facts 为空而验证失败"
    except Exception:
        pass


def test_final_adjudication_serialization_roundtrip():
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="中性偏谨慎",
        confidence=Confidence.MEDIUM,
        key_support_chains=[
            {"chain_description": "趋势未破坏", "evidence_refs": ["L5.trend"], "weight": 0.3}
        ],
        must_preserve_risks=["估值压缩风险"],
        blocking_issues=[],
        evidence_refs=["Bridge conflict"],
        adjudicator_notes="可以放行，但必须保留风险边界。",
    )
    data = final.model_dump()
    restored = FinalAdjudication.model_validate(data)
    assert restored.final_stance == "中性偏谨慎"
    assert restored.approval_status == ApprovalStatus.APPROVED_WITH_RESERVATIONS
    assert len(restored.key_support_chains) == 1
    assert restored.key_support_chains[0].weight == 0.3


def test_decision_semantics_fields_roundtrip():
    thesis = ThesisDraft(
        environment_assessment="风险偏高。",
        valuation_assessment="估值已有压缩。",
        timing_assessment="趋势尚未确认。",
        main_thesis="高风险高赔率候选。",
        overall_confidence=Confidence.MEDIUM,
        state_diagnosis="恐慌冲击后的高风险环境。",
        priced_narrative="价格已反映一部分坏消息。",
        payoff_assessment="高风险高赔率候选。",
        time_horizon_views=[
            {
                "horizon": "one_to_three_months",
                "view": "赔率改善但信用未确认。",
                "action_implication": "战术仓分批。",
            }
        ],
        portfolio_actions=[
            {
                "bucket": "tactical_position",
                "action": "分批试探。",
                "rationale": "等待确认有机会成本。",
            }
        ],
        confirmation_cost="等待全部确认会错过主要反弹段。",
        invalidation_conditions=["信用继续恶化"],
        reader_conclusion={"one_liner": "风险高，但赔率可能改善。"},
        principal_contradiction=PrincipalContradiction(
            contradiction_id="panic_priced_vs_unconfirmed_risk",
            summary="风险未解除但价格可能部分反映坏消息。",
            why_principal="它决定战术仓是否承认确认成本。",
            dominant_side="风险未解除。",
            secondary_side="赔率可能改善。",
            price_reflection="partially_reflected",
            action_implication="战术仓分批。",
            evidence_refs=["L4.valuation"],
        ),
        secondary_contradictions=[
            SecondaryContradiction(
                contradiction_id="breadth_vs_trend",
                summary="广度约束趋势质量。",
                why_secondary="它约束动作速度。",
                action_constraint="不支持无纪律满仓。",
            )
        ],
        price_reflection_map=[
            PriceReflectionAssessment(
                target="panic_priced_vs_unconfirmed_risk",
                reflected_state="partially_reflected",
                rationale="估值压缩说明部分坏消息进入价格。",
            )
        ],
    )
    data = thesis.model_dump()
    restored = ThesisDraft.model_validate(data)
    assert restored.payoff_assessment == "高风险高赔率候选。"
    assert restored.time_horizon_views[0].horizon == "one_to_three_months"
    assert restored.portfolio_actions[0].bucket == "tactical_position"
    assert restored.reader_conclusion.one_liner == "风险高，但赔率可能改善。"
    assert restored.principal_contradiction.price_reflection == "partially_reflected"
    assert restored.secondary_contradictions[0].contradiction_id == "breadth_vs_trend"
    assert restored.price_reflection_map[0].target == "panic_priced_vs_unconfirmed_risk"

    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="高风险高赔率候选",
        confidence=Confidence.MEDIUM,
        key_support_chains=[],
        must_preserve_risks=["信用继续恶化风险"],
        blocking_issues=[],
        evidence_refs=[],
        adjudicator_notes="内部质量说明。",
        reader_final=ReaderFinal(one_liner="读者结论。"),
        payoff_assessment="高风险高赔率候选。",
        principal_contradiction=thesis.principal_contradiction,
        price_reflection_map=thesis.price_reflection_map,
    )
    restored_final = FinalAdjudication.model_validate(final.model_dump())
    assert restored_final.reader_final.one_liner == "读者结论。"
    assert restored_final.principal_contradiction.contradiction_id == "panic_priced_vs_unconfirmed_risk"
