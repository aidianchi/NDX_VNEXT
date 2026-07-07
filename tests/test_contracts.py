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
    AgentBudget,
    AgentSpec,
    AdjudicationChangeRecord,
    AdjudicationHistory,
    ClaimLedger,
    ClaimLedgerEntry,
    CompetingHypothesis,
    CounterThesisDraft,
    EvidencePassport,
    EvidenceRegistry,
    EvidenceSourceAuthority,
    HypothesisCompetition,
    InquiryMessage,
    InquiryMessageType,
    InvestigationReport,
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


def test_feedback_message_types_are_strongly_typed_and_serializable():
    for message_type in InquiryMessageType:
        message = InquiryMessage(
            message_type=message_type,
            sender_stage="bridge",
            target_stage="L2",
            trigger="Bridge 发现关键证据缺口。",
            question="历史上类似缺口是否存在反证？",
            allowed_context_refs=["bridge_memos/bridge_0.json"],
            forbidden_context_refs=["thesis_draft.json", "final_adjudication.json"],
            effective_date="2026-07-06",
        )
        data = message.model_dump(mode="json")
        assert data["message_type"] == message_type.value
        assert data["allowed_context_refs"] == ["bridge_memos/bridge_0.json"]
        assert data["forbidden_context_refs"] == ["thesis_draft.json", "final_adjudication.json"]


def test_agent_spec_declares_context_budget_stop_and_success_contracts():
    spec = AgentSpec(
        originating_message_id="inq_test",
        research_question="L3 广度背离是否足以挑战趋势判断？",
        allowed_context_refs=["layer_cards/L3.json", "bridge_memos/bridge_0.json"],
        forbidden_context_refs=["thesis_draft.json", "final_adjudication.json"],
        allowed_tools=["read_allowed_artifacts"],
        budget=AgentBudget(max_tool_calls=0, max_minutes=0, max_source_refs=0),
        stop_conditions=["budget_exhausted"],
        success_criteria=["separate evidence and counter evidence"],
        required_output={"contract": "InvestigationReport"},
    )
    data = spec.model_dump(mode="json")
    assert data["budget"]["max_tool_calls"] == 0
    assert "thesis_draft.json" in data["forbidden_context_refs"]
    assert data["required_output"]["contract"] == "InvestigationReport"


def test_investigation_report_carries_minimal_evidence_and_authority_fields():
    report = InvestigationReport(
        originating_agent_id="agent_test",
        finding="广度证据不足以单独推翻趋势，但会降低趋势质量置信度。",
        evidence_refs=["L3.get_percent_above_ma"],
        counter_evidence_refs=["L5.get_qqq_technical_indicators"],
        claims_supported=["breadth_quality_constrains_trend"],
        claims_challenged=["trend_is_broadly_confirmed"],
        cannot_establish=["不能证明估值便宜"],
        confidence=Confidence.MEDIUM,
        limits=["只基于允许 artifacts，不读取 Thesis 或 Final。"],
        source_authority=[
            EvidenceSourceAuthority(
                evidence_ref="L3.get_percent_above_ma",
                source_ref="analysis_packet.raw_data.L3",
                source_tier="formal_data_source",
                authority_note="正式数据侧指标，但只能说明广度，不能证明估值。",
                supports=["breadth_quality_constrains_trend"],
                limitations=["不能说明估值是否便宜"],
            )
        ],
        effective_date="2026-07-06",
    )
    data = report.model_dump(mode="json")
    assert data["source_authority"][0]["source_tier"] == "formal_data_source"
    assert data["counter_evidence_refs"] == ["L5.get_qqq_technical_indicators"]
    assert data["cannot_establish"] == ["不能证明估值便宜"]


def test_evidence_passport_and_claim_ledger_stage4_contracts_roundtrip():
    registry = EvidenceRegistry(
        effective_date="2026-07-06",
        passports={
            "L1.get_10y_real_rate": EvidencePassport(
                evidence_id="L1.get_10y_real_rate",
                evidence_kind="data",
                source_ref="FRED",
                source_tier="official",
                permission_type=PermissionType.FACT,
                authority_model={
                    "can_support": "观察真实利率压力",
                    "cannot_support": ["不能证明估值便宜"],
                },
                downgrade_rules=[],
                effective_date="2026-07-06",
                verified=True,
            )
        },
    )
    ledger = ClaimLedger(
        effective_date="2026-07-06",
        entries=[
            ClaimLedgerEntry(
                claim_id="claim:final:rates",
                source_stage="final",
                claim_text="真实利率仍是估值压力的重要来源。",
                claim_type="market_state",
                evidence_refs=["L1.get_10y_real_rate"],
                counter_evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
                inference_steps=["真实利率影响折现率。"],
                falsification_conditions=["真实利率快速回落。"],
                verified=True,
                authority_status="verified",
            )
        ],
        publish_gate={"status": "pass"},
    )

    restored_registry = EvidenceRegistry.model_validate(registry.model_dump(mode="json"))
    restored_ledger = ClaimLedger.model_validate(ledger.model_dump(mode="json"))

    assert restored_registry.passports["L1.get_10y_real_rate"].source_tier == "official"
    assert restored_ledger.entries[0].claim_id == "claim:final:rates"
    assert restored_ledger.entries[0].verified is True


def test_competing_hypothesis_contract_requires_auditable_adjudication_fields():
    base = CompetingHypothesis(
        hypothesis_id="hyp_base",
        hypothesis_text="主线解释：高估值与高利率是主要矛盾。",
        source="bridge_v2",
        support_evidence_refs=["L1.real_rate", "L4.valuation"],
        counter_evidence_refs=["investigation_reports/inv_gap.json"],
        diagnostic_evidence_refs=["L4.valuation"],
        cannot_explain=["为何趋势仍强。"],
        falsification_conditions=["真实利率快速回落且盈利上修。"],
        confidence=Confidence.MEDIUM,
        status="kept_unresolved",
        adjudication_reason="调查报告保留价格反映缺口。",
    )
    counter = CompetingHypothesis(
        hypothesis_id="hyp_counter",
        hypothesis_text="反方解释：趋势强说明市场已部分消化估值压力。",
        source="counter_thesis",
        support_evidence_refs=["L5.trend"],
        counter_evidence_refs=["L4.valuation"],
        diagnostic_evidence_refs=["L5.trend"],
        cannot_explain=["不能证明估值便宜。"],
        falsification_conditions=["趋势跌破关键均线。"],
    )
    counter_thesis = CounterThesisDraft(
        input_refs=["synthesis_packet.json", "bridge_memos/bridge_v2.json"],
        forbidden_context_refs=["thesis_draft.json", "final_adjudication.json"],
        hypotheses=[counter],
        principal_counterargument=counter.hypothesis_text,
    )
    record = AdjudicationChangeRecord(
        version_id="adj_1",
        previous_hypothesis_id=base.hypothesis_id,
        new_hypothesis_id=counter.hypothesis_id,
        trigger_evidence_refs=["investigation_reports/inv_gap.json"],
        change_type="kept_unresolved",
        old_status="candidate",
        new_status="kept_unresolved",
        reason="强反证不足以反转，但足以禁止单一路径吸收。",
        effective_date="2026-07-06",
    )
    competition = HypothesisCompetition(
        input_refs=["synthesis_packet.json", "bridge_memos/bridge_v2.json"],
        forbidden_context_refs=["thesis_draft.json"],
        hypotheses=[base, counter],
        downgrade_or_split_events=[record],
        retained_disputes=["价格反映程度仍未解决。"],
        fallback_warnings=["price_reflection_map_derived_by_code"],
    )
    history = AdjudicationHistory(
        effective_date="2026-07-06",
        records=[record],
        current_hypothesis_ids=[base.hypothesis_id, counter.hypothesis_id],
    )

    restored = HypothesisCompetition.model_validate(competition.model_dump(mode="json"))

    assert counter_thesis.forbidden_context_refs == ["thesis_draft.json", "final_adjudication.json"]
    assert restored.hypotheses[0].counter_evidence_refs == ["investigation_reports/inv_gap.json"]
    assert restored.downgrade_or_split_events[0].change_type == "kept_unresolved"
    assert history.records[0].reason.startswith("强反证")


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


def test_counter_thesis_draft_tolerates_observed_llm_field_variants():
    # 形状取自 2026-07-07 真实 run 中两次被 schema 拒绝的 LLM 返回。
    attempt_1_like = {
        "hypotheses": [
            {
                "source": "counter_thesis",
                "hypothesis_text": "反方：盈利韧性足以消化估值压力。",
                "support_evidence_refs": ["L4.get_ndx_forward_earnings_quality"],
                "counter_evidence_refs": ["L1.get_net_liquidity_momentum"],
                "diagnostic_evidence_refs": ["L1.get_copper_gold_ratio"],
                "cannot_explain": ["无法解释广度走弱。"],
                "falsification_conditions": ["盈利预期下修。"],
            }
        ],
    }
    draft = CounterThesisDraft.model_validate(attempt_1_like)
    assert draft.hypotheses[0].hypothesis_id.startswith("hyp_")

    attempt_2_like = {
        "cannot_establish": "反方无法建立：利率已确认下行。",
        "hypotheses": [
            {
                "hypothesis_id": "counter_hypothesis_1",
                "hypothesis_text": "反方：净流动性转负不等于折现率上行。",
                "support_evidence_refs": "L4.get_ndx_pe_and_earnings_yield",
                "counter_evidence_refs": ["L1.get_net_liquidity_momentum"],
                "diagnostic_evidence_refs": ["L2.get_hyg_momentum"],
                "what_it_cannot_explain": "无法解释拥挤度上升。",
                "failure_conditions": "利率数据确认折现率显著上行。",
                "source": "counter_thesis",
            }
        ],
    }
    draft2 = CounterThesisDraft.model_validate(attempt_2_like)
    assert draft2.cannot_establish == ["反方无法建立：利率已确认下行。"]
    hypothesis = draft2.hypotheses[0]
    assert hypothesis.support_evidence_refs == ["L4.get_ndx_pe_and_earnings_yield"]
    assert hypothesis.cannot_explain == ["无法解释拥挤度上升。"]
    assert hypothesis.falsification_conditions == ["利率数据确认折现率显著上行。"]
