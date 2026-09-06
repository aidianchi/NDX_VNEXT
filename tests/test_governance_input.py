"""GovernanceInputPacket unit tests — ensure narrow input preserves critical signals."""

import ast
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    AnalysisPacket,
    AnalysisRevised,
    BridgeMemo,
    CompetingHypothesis,
    Confidence,
    Conflict,
    ContextBrief,
    CoreFact,
    Critique,
    EventInterpretationCard,
    EventSectionSummary,
    FinalAdjudication,
    PriceReflectionAssessment,
    PrincipalContradiction,
    GovernanceInputPacket,
    IndicatorAnalysis,
    KeySupportChain,
    LayerCard,
    ObjectiveFirewallSummary,
    RiskBoundaryReport,
    SchemaGuardReport,
    SecondaryContradiction,
    SynthesisPacket,
    ThesisDraft,
    TypedConflict,
)
from agent_analysis.orchestrator import (
    DYNAMIC_STAGE_KEY_CALL_SITES,
    PROMPT_FILES,
    STAGE_CONTRACT_PROMPT_REQUIREMENTS,
    VNextOrchestrator,
    _dump_governance_input,
)


def _empty_layer_card(layer: str) -> LayerCard:
    return LayerCard(
        layer=layer,
        core_facts=[CoreFact(metric="placeholder", value="n/a")],
        local_conclusion=f"{layer} placeholder",
        confidence=Confidence.MEDIUM,
    )


def _orchestrator(tmp_path: Path) -> VNextOrchestrator:
    return VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )


# ── 核心测试：高严重度 typed conflicts 不丢失 ──

def test_governance_input_preserves_high_severity_typed_conflicts(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    packet = AnalysisPacket(meta={"data_date": "2026-04-28"}, raw_data={})
    context = ContextBrief(data_summary="data", task_description="task")
    layer_cards = [
        LayerCard(
            layer="L1",
            core_facts=[CoreFact(metric="real_rate", value=1.95)],
            local_conclusion="流动性偏紧。",
            confidence=Confidence.MEDIUM,
            indicator_analyses=[
                IndicatorAnalysis(
                    function_id="get_10y_real_rate",
                    metric="10Y Real Rate",
                    narrative="真实利率偏高。",
                    reasoning_process="高实际利率压制成长股估值。",
                    evidence_refs=["L1.get_10y_real_rate"],
                    permission_type="fact",
                    canonical_question="真实贴现率是否在施压？",
                    misread_guards=["不仅是政策变量。"],
                    cross_validation_targets=["get_ndx_pe_and_earnings_yield"],
                    falsifiers=["盈利上修足以抵消折现率压力。"],
                    core_vs_tactical_boundary="核心框架指标。",
                )
            ],
        ),
        *_empty_layer_cards("L2", "L3", "L4", "L5"),
    ]
    bridge = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        typed_conflicts=[
            TypedConflict(
                conflict_id="real_rate_vs_valuation",
                conflict_type="valuation_discount_rate",
                severity="high",
                confidence="medium",
                description="高真实利率与高估值并存。",
                mechanism="真实利率提高折现率。",
                implication="估值压力必须保留。",
                involved_layers=["L1", "L4"],
                evidence_refs=["L1.get_10y_real_rate"],
                falsifiers=["盈利上修足以抵消折现率压力。"],
            ),
            TypedConflict(
                conflict_id="breadth_vs_trend",
                conflict_type="breadth_trend_divergence",
                severity="high",
                confidence="medium",
                description="指数上行但广度恶化。",
                mechanism="少数权重股拉动指数。",
                implication="趋势不可持续。",
                involved_layers=["L3", "L5"],
                evidence_refs=["L3.advance_decline"],
                falsifiers=["龙头贡献扩散到更广泛成分股。"],
            ),
        ],
        implication_for_ndx="需要保留两项冲突。",
    )

    synthesis = orchestrator._build_synthesis_packet(packet, context, layer_cards, [bridge])

    thesis = ThesisDraft(
        main_thesis="谨慎观望。",
        environment_assessment="宏观偏紧。",
        valuation_assessment="估值偏高。",
        timing_assessment="趋势向上但脆弱。",
        overall_confidence=Confidence.MEDIUM,
        retained_conflicts=[
            Conflict(
                conflict_type="valuation_discount_rate",
                severity="high",
                description="高利率 vs 高估值",
                implication="估值压力必须保留。",
                involved_layers=["L1", "L4"],
            ),
        ],
        dependencies=["盈利增速 > 10%"],
    )

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        layer_cards=layer_cards,
    )

    # 两个 high severity typed conflicts 都不应丢失
    assert len(gov_input.high_severity_typed_conflicts) == 2
    conflict_ids = {c["conflict_id"] for c in gov_input.high_severity_typed_conflicts}
    assert "real_rate_vs_valuation" in conflict_ids
    assert "breadth_vs_trend" in conflict_ids


# ── 核心测试：Objective Firewall 保留 ──

def test_governance_input_includes_objective_firewall(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    packet = AnalysisPacket(meta={"data_date": "2026-04-28"}, raw_data={})
    context = ContextBrief(data_summary="data", task_description="task")
    layer_cards = _five_empty_cards()
    bridge = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        implication_for_ndx="fine",
    )
    synthesis = orchestrator._build_synthesis_packet(packet, context, layer_cards, [bridge])
    thesis = ThesisDraft(
        main_thesis="中性。",
        environment_assessment="宏观中性。",
        valuation_assessment="估值中性。",
        timing_assessment="趋势中性。",
        overall_confidence=Confidence.MEDIUM,
        dependencies=[],
    )

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        layer_cards=layer_cards,
    )

    assert gov_input.objective_firewall_summary is not None
    firewall = gov_input.objective_firewall_summary
    assert "object_clear" in firewall
    assert "authority_clear" in firewall
    assert "cross_layer_verified" in firewall


# ── 核心测试：L3 数据缺口保留 ──

def test_governance_input_includes_l3_data_gaps(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    packet = AnalysisPacket(meta={"data_date": "2026-04-28"}, raw_data={
        "L3": {
            "get_qqq_component_breadth": {
                "function_id": "get_qqq_component_breadth",
                "metric_name": "QQQ Component Breadth",
                "error": "Data unavailable: breadth source timed out",
            }
        }
    })
    context = ContextBrief(data_summary="data", task_description="task")

    l3_card = LayerCard(
        layer="L3",
        core_facts=[CoreFact(metric="breadth_missing", value="n/a")],
        local_conclusion="广度数据缺失，L3 判断受限。",
        confidence=Confidence.LOW,
        risk_flags=["结构指标缺失", "breadth未知"],
        quality_self_check={
            "coverage_complete": False,
            "covered_function_ids": [],
            "missing_or_weak_indicators": ["get_qqq_component_breadth: Data unavailable"],
            "weak_reasoning_points": ["无法评估指数内部健康度"],
            "unresolved_internal_tensions": [],
            "confidence_limitations": ["广度数据缺失是 L3 主要限制"],
        },
    )
    layer_cards = _four_empty_cards() + [l3_card]

    bridge = BridgeMemo(
        bridge_type="breadth_trend",
        layers_connected=["L3", "L5"],
        implication_for_ndx="L3 数据缺失限制了跨层判断。",
    )
    synthesis = orchestrator._build_synthesis_packet(packet, context, layer_cards, [bridge])

    thesis = ThesisDraft(
        main_thesis="由于 L3 结构数据缺失，内部健康度判断受限。",
        environment_assessment="宏观偏紧。",
        valuation_assessment="估值偏高。",
        timing_assessment="趋势脆弱。",
        overall_confidence=Confidence.LOW,
        dependencies=["等待 L3 广度数据补全"],
    )

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        layer_cards=layer_cards,
    )

    # L3 数据缺口必须出现在 known_data_gaps 中
    l3_gaps = [g for g in gov_input.known_data_gaps if "L3" in g or "breadth" in g.lower() or "get_qqq_component_breadth" in g]
    assert len(l3_gaps) > 0, f"Expected L3 data gaps in known_data_gaps, got: {gov_input.known_data_gaps}"


def test_governance_input_preserves_thesis_support_chain_evidence_outside_conflicts(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    packet = AnalysisPacket(meta={"data_date": "2026-04-28"}, raw_data={})
    context = ContextBrief(data_summary="data", task_description="task")

    l1_card = LayerCard(
        layer="L1",
        core_facts=[CoreFact(metric="real_rate", value=1.95)],
        local_conclusion="High real rates pressure valuation.",
        confidence=Confidence.MEDIUM,
        indicator_analyses=[
            IndicatorAnalysis(
                function_id="get_10y_real_rate",
                metric="10Y Real Rate",
                current_reading="1.95%",
                normalized_state="restrictive",
                narrative="Real rates remain restrictive.",
                reasoning_process="Higher real rates raise the discount-rate hurdle.",
                evidence_refs=["L1.get_10y_real_rate"],
            )
        ],
    )
    l4_card = LayerCard(
        layer="L4",
        core_facts=[CoreFact(metric="earnings_yield", value=3.3)],
        local_conclusion="Earnings yield is the direct valuation support reference.",
        confidence=Confidence.MEDIUM,
        indicator_analyses=[
            IndicatorAnalysis(
                function_id="get_ndx_pe_and_earnings_yield",
                metric="NDX Earnings Yield",
                current_reading="3.3%",
                normalized_state="expensive_but_supported",
                narrative="Earnings yield is thin but remains the thesis support reference.",
                reasoning_process="Valuation support must be checked against earnings yield, not only conflict evidence.",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
            )
        ],
    )
    layer_cards = [
        l1_card,
        _empty_layer_card("L2"),
        _empty_layer_card("L3"),
        l4_card,
        _empty_layer_card("L5"),
    ]

    bridge = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        typed_conflicts=[
            TypedConflict(
                conflict_id="real_rate_vs_valuation",
                conflict_type="valuation_discount_rate",
                severity="high",
                confidence="medium",
                description="High real rates conflict with elevated valuation.",
                mechanism="Real rates raise the discount rate.",
                implication="Valuation pressure must be retained.",
                involved_layers=["L1", "L4"],
                evidence_refs=["L1.get_10y_real_rate"],
                falsifiers=["Earnings growth offsets the discount-rate pressure."],
            )
        ],
        implication_for_ndx="Retain valuation pressure.",
    )
    synthesis = orchestrator._build_synthesis_packet(packet, context, layer_cards, [bridge])

    thesis = ThesisDraft(
        main_thesis="Neutral: valuation pressure remains, but earnings yield is the direct support check.",
        environment_assessment="Macro is restrictive.",
        valuation_assessment="Valuation is expensive but needs earnings-yield validation.",
        timing_assessment="Trend does not remove valuation risk.",
        overall_confidence=Confidence.MEDIUM,
        key_support_chains=[
            KeySupportChain(
                chain_description="Earnings yield is the thesis support evidence.",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
                weight=0.35,
            )
        ],
    )

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        layer_cards=layer_cards,
    )

    assert gov_input.thesis_key_support_chains == [
        {
            "chain_description": "Earnings yield is the thesis support evidence.",
            "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
            "event_refs": [],
            "weight": 0.35,
        }
    ]
    assert "L1.get_10y_real_rate" in gov_input.key_evidence_refs
    assert "L4.get_ndx_pe_and_earnings_yield" in gov_input.key_evidence_refs


def test_governance_input_carries_decision_semantics_fields(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    synthesis = SynthesisPacket(
        evidence_index={
            "L4.get_ndx_pe_and_earnings_yield": {"metric": "valuation"},
            "L5.get_ta_indicators": {"metric": "trend"},
        },
        principal_contradictions=[
            PrincipalContradiction(
                contradiction_id="panic_priced_vs_unconfirmed_risk",
                summary="风险未解除但价格可能已反映一部分坏消息。",
                why_principal="它决定战术仓是否应承认确认成本。",
                dominant_side="风险未解除。",
                secondary_side="赔率可能改善。",
                price_reflection="partially_reflected",
                action_implication="战术仓分批。",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
            )
        ],
    )
    thesis = ThesisDraft(
        main_thesis="高风险高赔率候选。",
        environment_assessment="风险偏高。",
        valuation_assessment="估值压缩。",
        timing_assessment="趋势未确认。",
        overall_confidence=Confidence.MEDIUM,
        state_diagnosis="恐慌冲击后。",
        priced_narrative="坏消息可能部分计入价格。",
        payoff_assessment="高风险高赔率候选。",
        time_horizon_views=[
            {
                "horizon": "one_to_three_months",
                "view": "赔率改善但信用未确认。",
                "action_implication": "战术仓分批。",
                "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
            }
        ],
        portfolio_actions=[
            {
                "bucket": "tactical_position",
                "action": "分批试探。",
                "rationale": "等待确认有机会成本。",
                "evidence_refs": ["L5.get_ta_indicators"],
            }
        ],
        confirmation_cost="等待全部确认可能错过赔率窗口。",
        invalidation_conditions=["信用继续恶化"],
        reader_conclusion={
            "one_liner": "风险高，但赔率可能改善。",
            "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
        },
        principal_contradiction=PrincipalContradiction(
            contradiction_id="panic_priced_vs_unconfirmed_risk",
            summary="风险未解除但价格可能已反映一部分坏消息。",
            why_principal="它决定动作是分批试探还是等待全部确认。",
            dominant_side="风险未解除。",
            secondary_side="赔率可能改善。",
            price_reflection="partially_reflected",
            action_implication="战术仓分批，等待现金承认确认成本。",
            evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
        ),
        secondary_contradictions=[
            SecondaryContradiction(
                contradiction_id="breadth_vs_trend",
                summary="广度约束反弹质量。",
                why_secondary="它约束加仓速度。",
                action_constraint="不支持一次性满仓。",
                evidence_refs=["L5.get_ta_indicators"],
            )
        ],
        price_reflection_map=[
            PriceReflectionAssessment(
                target="panic_priced_vs_unconfirmed_risk",
                reflected_state="partially_reflected",
                rationale="估值压缩说明坏消息部分计入价格。",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
            )
        ],
    )
    risk = RiskBoundaryReport(
        must_preserve_risks=["信用继续恶化风险"],
        opportunity_costs=[{"condition": "等待全部确认", "missed_payoff": "错过反弹"}],
        confirmation_costs=[{"wait_for": "趋势确认", "cost": "赔率变薄"}],
        false_safety_risks=["风险消失时价格也可能不便宜"],
    )

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        risk_report=risk,
    )

    assert gov_input.thesis_payoff_assessment == "高风险高赔率候选。"
    assert gov_input.thesis_time_horizon_views[0]["horizon"] == "one_to_three_months"
    assert gov_input.thesis_portfolio_actions[0]["bucket"] == "tactical_position"
    assert gov_input.thesis_confirmation_cost == "等待全部确认可能错过赔率窗口。"
    assert gov_input.thesis_reader_conclusion["one_liner"] == "风险高，但赔率可能改善。"
    assert gov_input.thesis_principal_contradiction["contradiction_id"] == "panic_priced_vs_unconfirmed_risk"
    assert gov_input.principal_contradictions[0]["price_reflection"] == "partially_reflected"
    assert gov_input.thesis_secondary_contradictions[0]["contradiction_id"] == "breadth_vs_trend"
    assert gov_input.thesis_price_reflection_map[0]["reflected_state"] == "partially_reflected"
    assert gov_input.opportunity_costs[0]["missed_payoff"] == "错过反弹"
    assert gov_input.confirmation_costs[0]["cost"] == "赔率变薄"
    assert gov_input.false_safety_risks == ["风险消失时价格也可能不便宜"]
    assert "L4.get_ndx_pe_and_earnings_yield" in gov_input.key_evidence_refs
    assert "L5.get_ta_indicators" in gov_input.key_evidence_refs


# ── C3 分料测试：risk = 论证盲，critic 默认行为不回退 ──

def test_governance_input_risk_version_carries_no_thesis_content(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    synthesis = SynthesisPacket(
        evidence_index={
            "L1.get_10y_real_rate": {"layer": "L1"},
            "L4.get_ndx_pe_and_earnings_yield": {"layer": "L4"},
        },
        layer_summaries=[
            {
                "layer": "L1",
                "local_conclusion": "流动性偏紧。",
                "indicator_refs": ["L1.get_10y_real_rate"],
            }
        ],
    )
    thesis = ThesisDraft(
        main_thesis="谨慎观望：高利率压制估值。",
        environment_assessment="宏观偏紧。",
        valuation_assessment="估值偏高。",
        timing_assessment="趋势脆弱。",
        overall_confidence=Confidence.MEDIUM,
        dependencies=["盈利增速 > 10%"],
        key_support_chains=[
            KeySupportChain(
                chain_description="真实利率压制估值。",
                evidence_refs=["L1.get_10y_real_rate"],
                weight=0.5,
            )
        ],
        hypothesis_responses=[
            {
                "hypothesis_id": "hyp_1",
                "verdict": "absorb_partially",
                "reasoning": "部分吸收趋势解释。",
                "evidence_refs": ["L1.get_10y_real_rate"],
            }
        ],
        time_horizon_views=[
            {
                "horizon": "one_to_three_months",
                "view": "赔率中性。",
                "action_implication": "观望。",
                "evidence_refs": ["L1.get_10y_real_rate"],
            }
        ],
        portfolio_actions=[
            {
                "bucket": "tactical_position",
                "action": "等待。",
                "rationale": "等待确认。",
                "evidence_refs": ["L1.get_10y_real_rate"],
            }
        ],
        retained_conflicts=[
            Conflict(
                conflict_type="valuation_discount_rate",
                severity="high",
                description="高利率 vs 高估值",
                implication="估值压力必须保留。",
                involved_layers=["L1", "L4"],
            ),
        ],
        state_diagnosis="高压环境。",
        priced_narrative="坏消息部分计入价格。",
        payoff_assessment="风险收益中性。",
        confirmation_cost="等待确认有机会成本。",
        invalidation_conditions=["信用利差走阔"],
        reader_conclusion={"one_liner": "等待更明确信号。"},
        principal_contradiction=PrincipalContradiction(
            contradiction_id="panic_priced_vs_unconfirmed_risk",
            summary="风险未解除但价格可能已反映。",
            why_principal="决定战术仓节奏。",
            dominant_side="风险未解除。",
            secondary_side="赔率改善。",
            price_reflection="partially_reflected",
            action_implication="分批。",
            evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
        ),
        secondary_contradictions=[
            SecondaryContradiction(
                contradiction_id="breadth_vs_trend",
                summary="广度约束反弹质量。",
                why_secondary="约束加仓速度。",
                action_constraint="不支持满仓。",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
            )
        ],
        price_reflection_map=[
            PriceReflectionAssessment(
                target="panic_priced_vs_unconfirmed_risk",
                reflected_state="partially_reflected",
                rationale="估值压缩说明部分计入。",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
            )
        ],
    )

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="risk",
    )

    # 任务书要求至少查这五个；这里把全部 thesis_* 字段都查一遍
    assert gov_input.thesis_main == ""
    assert gov_input.thesis_environment == ""
    assert gov_input.thesis_valuation == ""
    assert gov_input.thesis_timing == ""
    assert gov_input.thesis_confidence == ""
    assert gov_input.thesis_dependencies == []
    assert gov_input.thesis_key_support_chains == []
    assert gov_input.thesis_hypothesis_responses == []
    assert gov_input.retained_conflict_types == []
    assert gov_input.thesis_state_diagnosis == ""
    assert gov_input.thesis_priced_narrative == ""
    assert gov_input.thesis_payoff_assessment == ""
    assert gov_input.thesis_time_horizon_views == []
    assert gov_input.thesis_portfolio_actions == []
    assert gov_input.thesis_confirmation_cost == ""
    assert gov_input.thesis_invalidation_conditions == []
    assert gov_input.thesis_reader_conclusion == {}
    assert gov_input.thesis_principal_contradiction is None
    assert gov_input.thesis_secondary_contradictions == []
    assert gov_input.thesis_price_reflection_map == []


def _minimal_blind_fixture():
    synthesis = SynthesisPacket(
        evidence_index={"L1.get_10y_real_rate": {"layer": "L1"}},
        layer_summaries=[
            {
                "layer": "L1",
                "local_conclusion": "流动性偏紧。",
                "indicator_refs": ["L1.get_10y_real_rate"],
            }
        ],
    )
    thesis = ThesisDraft(
        main_thesis="谨慎观望：高利率压制估值。",
        environment_assessment="宏观偏紧。",
        valuation_assessment="估值偏高。",
        timing_assessment="趋势脆弱。",
        overall_confidence=Confidence.MEDIUM,
    )
    return synthesis, thesis


def test_governance_input_risk_serialization_omits_thesis_keys(tmp_path: Path):
    # 论证盲形式收尾（配餐单/C3）：risk 包序列化结果里 thesis_* 键整个移除，
    # 不是以空值残留——空键出现在包和提示词里同样构成形式泄漏。
    orchestrator = _orchestrator(tmp_path)
    synthesis, thesis = _minimal_blind_fixture()

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="risk",
    )
    dumped = _dump_governance_input(gov_input, "risk")

    leaked = sorted(
        key for key in dumped if key.startswith("thesis_") or key == "retained_conflict_types"
    )
    assert leaked == []
    # 事实面不受牵连：layer_summaries 与冲突容器仍在包里。
    assert dumped["layer_summaries"]
    assert "high_severity_typed_conflicts" in dumped


def test_governance_input_critic_serialization_keeps_thesis_content(tmp_path: Path):
    # 回归：critic 默认路径不受影响——thesis_* 键与内容完整保留。
    orchestrator = _orchestrator(tmp_path)
    synthesis, thesis = _minimal_blind_fixture()

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
    )
    dumped = _dump_governance_input(gov_input, "critic")

    assert dumped["thesis_main"] == "谨慎观望：高利率压制估值。"
    assert dumped["thesis_environment"] == "宏观偏紧。"
    assert "thesis_key_support_chains" in dumped


def test_governance_input_risk_layer_summaries_critic_empty(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    synthesis = SynthesisPacket(
        evidence_index={"L4.get_ndx_pe_and_earnings_yield": {"layer": "L4"}},
        layer_summaries=[
            {
                "layer": "L4",
                "local_conclusion": "估值偏高。",
                "layer_synthesis": "估值压缩风险存在。",
                "indicator_refs": ["L4.get_ndx_pe_and_earnings_yield"],
                "key_evidence": ["NDX PE: 32.5"],
                "risk_flags": ["估值压缩"],
                "confidence": "medium",
            }
        ],
    )
    thesis = ThesisDraft(
        main_thesis="中性。",
        environment_assessment="中性。",
        valuation_assessment="中性。",
        timing_assessment="中性。",
        overall_confidence=Confidence.MEDIUM,
    )

    gov_input_risk = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="risk",
    )
    gov_input_critic = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
    )

    assert len(gov_input_risk.layer_summaries) == 1
    assert gov_input_risk.layer_summaries[0]["layer"] == "L4"
    assert gov_input_risk.layer_summaries[0]["local_conclusion"] == "估值偏高。"
    assert gov_input_risk.layer_summaries[0]["indicator_refs"] == ["L4.get_ndx_pe_and_earnings_yield"]
    assert gov_input_critic.layer_summaries == []


def test_governance_input_risk_key_evidence_refs_exclude_thesis_only_refs(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    synthesis = SynthesisPacket(
        evidence_index={
            "L1.conflict_ref": {"layer": "L1"},
            "L2.layer_ref": {"layer": "L2"},
            "L3.thesis_only_ref": {"layer": "L3"},
        },
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="c1",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="冲突描述。",
                implication="必须保留。",
                evidence_refs=["L1.conflict_ref"],
            )
        ],
        layer_summaries=[
            {
                "layer": "L2",
                "local_conclusion": "风险偏好恶化。",
                "indicator_refs": ["L2.layer_ref"],
            }
        ],
    )
    thesis = ThesisDraft(
        main_thesis="谨慎。",
        environment_assessment="偏紧。",
        valuation_assessment="偏高。",
        timing_assessment="脆弱。",
        overall_confidence=Confidence.MEDIUM,
        key_support_chains=[
            KeySupportChain(
                chain_description="只被 thesis 支撑链引用的证据。",
                evidence_refs=["L3.thesis_only_ref"],
                weight=0.3,
            )
        ],
    )

    gov_input_risk = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="risk",
    )
    gov_input_critic = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
    )

    # risk 论证盲：key_evidence_refs 只来自冲突与层摘要，不来自 thesis 支撑链
    assert "L1.conflict_ref" in gov_input_risk.key_evidence_refs
    assert "L2.layer_ref" in gov_input_risk.key_evidence_refs
    assert "L3.thesis_only_ref" not in gov_input_risk.key_evidence_refs

    # critic 默认行为不回退：thesis 支撑链引用的 ref 仍会进入 key_evidence_refs
    assert "L1.conflict_ref" in gov_input_critic.key_evidence_refs
    assert "L3.thesis_only_ref" in gov_input_critic.key_evidence_refs


def test_governance_input_risk_retry_injects_schema_feedback_without_thesis(tmp_path: Path):
    """schema_guard_retry 路径：risk 拿 schema 反馈，但仍然论证盲。"""
    orchestrator = _orchestrator(tmp_path)
    synthesis = SynthesisPacket(
        evidence_index={"L1.get_10y_real_rate": {"layer": "L1"}},
        layer_summaries=[],
    )
    thesis = ThesisDraft(
        main_thesis="谨慎。",
        environment_assessment="偏紧。",
        valuation_assessment="偏高。",
        timing_assessment="脆弱。",
        overall_confidence=Confidence.MEDIUM,
    )
    schema_report = SchemaGuardReport(
        passed=False,
        structural_issues=["thesis 缺字段"],
        missing_fields=["claim_ledger"],
    )

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        schema_report=schema_report,
        consumer="risk",
    )

    assert gov_input.schema_passed is False
    assert gov_input.schema_structural_issues == ["thesis 缺字段"]
    assert gov_input.schema_missing_fields == ["claim_ledger"]
    # retry 路径仍然论证盲
    assert gov_input.thesis_main == ""
    assert gov_input.thesis_key_support_chains == []


# ── 拍板③ + T46：counter 反方原文与反证引用进 critic/reviser/final，risk 恒空 ──

def test_governance_input_counter_thesis_refs_enter_critic_but_not_risk(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    synthesis = SynthesisPacket(
        evidence_index={
            "L1.conflict_ref": {"layer": "L1"},
            "L1.counter_only_ref": {"layer": "L1"},
        },
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="c1",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="冲突描述。",
                implication="必须保留。",
                evidence_refs=["L1.conflict_ref"],
            )
        ],
        competing_hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_counter_1",
                hypothesis_text="反方原文：趋势证据说明压力已部分消化。",
                source="counter_thesis",
                support_evidence_refs=["L1.counter_only_ref"],
                counter_evidence_refs=["L1.conflict_ref"],
                diagnostic_evidence_refs=[],
                status="candidate",
            )
        ],
    )
    thesis = ThesisDraft(
        main_thesis="谨慎观望。",
        environment_assessment="偏紧。",
        valuation_assessment="偏高。",
        timing_assessment="脆弱。",
        overall_confidence=Confidence.MEDIUM,
    )

    gov_critic = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
    )
    gov_risk = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="risk",
    )

    # counter 独有的 ref 必须进 critic 包
    assert gov_critic.counter_thesis_hypotheses == [
        {
            "hypothesis_id": "hyp_counter_1",
            "hypothesis_text": "反方原文：趋势证据说明压力已部分消化。",
            "status": "candidate",
            "support_evidence_refs": ["L1.counter_only_ref"],
            "counter_evidence_refs": ["L1.conflict_ref"],
            "diagnostic_evidence_refs": [],
        }
    ]
    assert "L1.counter_only_ref" in gov_critic.key_evidence_refs

    # risk 包 counter_thesis_hypotheses 恒空，且不并入 counter 独有 ref
    assert gov_risk.counter_thesis_hypotheses == []
    assert "L1.counter_only_ref" not in gov_risk.key_evidence_refs
    assert "L1.conflict_ref" in gov_risk.key_evidence_refs


# ── 拍板②（2026-08-16 重裁）：终审只收修订稿+修订说明，原稿只落盘 ──

def test_governance_input_final_drops_thesis_original_and_keeps_revision_summary(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    synthesis = SynthesisPacket(evidence_index={})
    thesis = ThesisDraft(
        main_thesis="原稿主论点。",
        environment_assessment="原稿环境。",
        valuation_assessment="原稿估值。",
        timing_assessment="原稿时机。",
        overall_confidence=Confidence.MEDIUM,
    )
    revised_thesis = ThesisDraft(
        main_thesis="修订稿主论点。",
        environment_assessment="修订稿环境。",
        valuation_assessment="修订稿估值。",
        timing_assessment="修订稿时机。",
        overall_confidence=Confidence.MEDIUM,
    )
    analysis_revised = AnalysisRevised(
        revision_summary="修订说明：吸收批评并改写主论点。",
        revised_thesis=revised_thesis,
    )

    gov_final = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=revised_thesis,
        analysis_revised=analysis_revised,
        consumer="final",
    )

    assert gov_final.thesis_main == "修订稿主论点。"
    # 新口径：thesis_original 从治理包整体移除，终审拿不到原稿；原稿只在磁盘审计。
    assert not hasattr(gov_final, "thesis_original")
    assert "thesis_original" not in gov_final.model_dump()
    assert gov_final.revision_summary == "修订说明：吸收批评并改写主论点。"


# ── 08-15 已批：reviser/final 去噪音字段 + 证据索引瘦身 ──

def test_governance_input_reviser_final_drop_noise_fields_and_slim_key_evidence(tmp_path: Path):
    orchestrator = _orchestrator(tmp_path)
    # 让 critic 的 pricing_expectation_ledger 非空，证明 reviser/final 确实清空。
    (tmp_path / "expectation_vs_realized.json").write_text(
        json.dumps(
            {
                "metric_authority": "supporting_only",
                "effective_date": "2026-04-28",
                "downgrade_rules": [],
                "status": "available_for_supporting_use",
                "earnings_expectations": {"status": "ok", "windows": []},
                "rate_path": {"status": "ok", "comparisons": []},
                "volatility_premium": {"status": "ok"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    long_series = [{"index": n, "note": "逐票审计明细" + "甲" * 100} for n in range(10)]
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-28"},
        evidence_index={
            "L1.long_ref": {
                "field_value": {
                    "value": {"aggregate": 1.5, "coverage": "full"},
                    "raw_series": long_series,
                }
            }
        },
        evidence_registry_summary={"schema_version": "evidence_registry_v1", "passport_count": 3},
        synthesis_guidance=["只能整合，不得重做指标分析。"],
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="c_long",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="冲突描述。",
                implication="必须保留。",
                evidence_refs=["L1.long_ref"],
            )
        ],
    )
    thesis = ThesisDraft(
        main_thesis="中性。",
        environment_assessment="中性。",
        valuation_assessment="中性。",
        timing_assessment="中性。",
        overall_confidence=Confidence.MEDIUM,
    )

    gov_critic = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
    )
    gov_reviser = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="reviser",
    )
    gov_final = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="final",
    )

    # critic 默认行为：synthesis_guidance / evidence_registry_summary 保留；
    # pricing_expectation_ledger 按配餐单 v0 对四个治理站一律不给（台账留磁盘审计）。
    assert gov_critic.synthesis_guidance == ["只能整合，不得重做指标分析。"]
    assert gov_critic.evidence_registry_summary["passport_count"] == 3
    assert gov_critic.pricing_expectation_ledger == {}

    # reviser/final 去噪音字段
    for gov_input in (gov_reviser, gov_final):
        assert gov_input.synthesis_guidance == []
        assert gov_input.evidence_registry_summary == {}
        assert gov_input.pricing_expectation_ledger == {}

    # reviser/final 的 key_evidence_refs 瘦身：ref key 集合不动、聚合字段逐字节不变、
    # 超长明细被压成 _prompt_summary。
    for gov_input in (gov_reviser, gov_final):
        assert set(gov_input.key_evidence_refs.keys()) == {"L1.long_ref"}
        field_value = gov_input.key_evidence_refs["L1.long_ref"]["field_value"]
        assert field_value["value"] == {"aggregate": 1.5, "coverage": "full"}
        assert field_value["raw_series"]["_prompt_summary"] is True
        assert field_value["raw_series"]["count"] == 10

    # critic 证据瘦身与 reviser/final 同管道（体检 #1-②，2026-09-05 老板批准施工；
    # run t70_glm_check_20260902 实测 critic/risk 证据包比 thesis 菜单还肥）：
    # ref key 集合不动、聚合字段逐字节不变、超长明细压成 _prompt_summary。
    # 去噪音字段（synthesis_guidance / evidence_registry_summary 清空）仍仅 reviser/final。
    assert set(gov_critic.key_evidence_refs.keys()) == {"L1.long_ref"}
    critic_field_value = gov_critic.key_evidence_refs["L1.long_ref"]["field_value"]
    assert critic_field_value["value"] == {"aggregate": 1.5, "coverage": "full"}
    assert critic_field_value["raw_series"]["_prompt_summary"] is True
    assert critic_field_value["raw_series"]["count"] == 10


# ── 护栏测试：governance prompt 中继续禁止编造历史概率 ──

def test_governance_prompts_still_ban_fabricated_statistics():
    prompt_dir = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"
    governance_prompts = [
        "critic.md",
        "risk_sentinel.md",
        "reviser.md",
        "final_adjudicator.md",
    ]

    banned_patterns = [
        "负收益概率",
        "回调概率",
        "样本：",
        "样本:",
        ">70%",
    ]

    for name in governance_prompts:
        text = (prompt_dir / name).read_text(encoding="utf-8")
        for phrase in banned_patterns:
            assert phrase not in text, f"{name} contains banned phrase: {phrase}"


# ── 防漂移闸门：校验函数会点名的东西，说明书里必须写过 ──

def test_stage_contracts_are_documented_in_their_prompts():
    """合约写在代码里、说明书写在 prompt 里，必须有机器闸门保证两边说的是同一件事。

    真实事故（run 20260724_223804）：reviser 同时挂着证据引用合法性和竞争假说回应两条
    合约，而 reviser.md 一条都没写。模型严格照着 prompt 的输出模板作答，于是必然缺字段、
    重试逐字复现、整条流水线 RuntimeError。两条缺口各崩过一次真实运行。

    这个测试是让"逐条打补丁"收敛的关键：新增 stage validator 时必须同步登记，
    否则下一次漂移会在这里红，而不是在下一次正式跑里红。
    """
    prompt_dir = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"

    for stage_key, required_keywords in STAGE_CONTRACT_PROMPT_REQUIREMENTS.items():
        prompt_name = PROMPT_FILES[stage_key]
        text = (prompt_dir / prompt_name).read_text(encoding="utf-8")
        for keyword in required_keywords:
            assert keyword in text, (
                f"{prompt_name} 未说明 stage `{stage_key}` 的合约要求 `{keyword}`："
                "validator 会因此判失败，但模型从未被告知该要求。"
                "请补 prompt，或在 STAGE_CONTRACT_PROMPT_REQUIREMENTS 中同步调整登记。"
            )


def test_governance_prompts_ban_fabricated_subfield_refs():
    """B 类命名空间纪律：合法子引用名由 evidence_index 给定，不等于模型看到的数据字段名。

    真实事故（同一 run 的 thesis attempt 1）：模型引用了 `L4.get_m7_buyback_flow#m7_quarterly_total`
    ——`m7_quarterly_total` 确实是该工具 value 里的真实字段名，但 evidence_index 的合法子引用
    用的是 authority 条目名（`m7_aggregate_and_yoy`）。模型"照实抄"反而违规。
    每个会拼 `parent#field` 的 stage 都必须被明确告知：只能使用索引里已存在的 ref。
    2026-08-31 T69 P2b：保留"从清单里选"的存在性义务，删除"逐字"吓阻修辞——
    refs 存在性由 _validate_stage_evidence_refs 守，不需要靠措辞恐吓。
    """
    prompt_dir = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"

    for name in ("thesis_builder.md", "reviser.md", "final_adjudicator.md"):
        text = (prompt_dir / name).read_text(encoding="utf-8")
        assert "不得自行拼接" in text, f"{name} 未禁止自行拼接 parent#field 子引用"
        assert "evidence_index" in text, f"{name} 未要求 evidence_ref 来自索引"
        # refs 纪律段的"逐字"吓阻已删（T69 P2b）；存在性义务保留。
        assert "逐字来自" not in text and "逐字存在" not in text, f"{name} 仍残留 refs 逐字吓阻修辞"

    # 确认 risk 和 final 仍明确禁止编造统计
    for name in ["risk_sentinel.md", "final_adjudicator.md"]:
        text = (prompt_dir / name).read_text(encoding="utf-8")
        assert "不得编造历史胜率、回测收益、样本区间或概率数字" in text, f"{name} missing ban on fabricated statistics"


def test_prompts_no_longer_carry_dead_format_clauses_t69_p2a():
    """T69 P2a（2026-08-31）提示词死条款清除的反向锁定：删掉的机械字段/字数窗口/
    吓阻修辞不得回流。

    清除依据（闸门宪法 v2 + 总账 2.1/2.2）：机械字段由 _compose_prompt 的契约字段
    规格机械注入、由 pydantic/model_validate 守；字数窗口是形状代理语义；"打回/逐字
    照抄/系统会拦截"是吓阻修辞，代码闸门与重试反馈已接管执法。"""
    prompt_dir = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"
    dead_clauses = {
        # ① 固定尾句代码装配（_ensure_event_section_boundary_sentence）、引用计数与
        # 100-1500 字窗口代码侧已删（T69 P0-3）。
        "event_section_summary.md": ["逐字保留", "至少引用两张", "100-1500"],
        # ② 背字段名/背报错文案整节删除。
        "counter_thesis.md": ["输出字段纪律", "逐字照抄", "Field required"],
        # ④ event_refs 由代码装配为空列表，提示词一个字都不必再提。
        "cross_layer_bridge.md": ["校验器会打回", "不需要输出 `event_refs`"],
        # ⑥ 600-1200 字数窗口与方括号计数（代码侧"≥3 括号组"已于 P0-4 删除）。
        "final_adjudicator.md": ["600-1200", "至少三个独立的方括号"],
        "integrated_adjudicator.md": ["600-1200"],
        # ⑧ 字数窗口与吓阻修辞（contracts.py 的 500 硬上限同批删除）。
        "critic.md": ["500 字符", "打回重写"],
        "l1_analyst.md": ["稳定超过 160"],
        "context_loader.md": ["300 字符"],
    }
    for name, clauses in dead_clauses.items():
        text = (prompt_dir / name).read_text(encoding="utf-8")
        for clause in clauses:
            assert clause not in text, f"{name} 仍残留已清除的死条款：{clause!r}"


def test_prompts_no_longer_carry_dead_format_clauses_t69_p2b():
    """T69 P2b（2026-08-31）反向锁定：③失效条件方向标签代码化 + P2a 施工新扫出的
    同族残留（五层分析师字数下限、reviser 300/500 字符、refs 逐字吓阻、bridge 注入段
    吓阻）不得回流。

    清除依据同 P2a：方向前缀由 InvalidationItem.direction 枚举 + 代码渲染接管
    （contracts.py InvalidationItem / FinalAdjudication._render_invalidation_conditions_from_items）；
    字数下限无对应代码闸门（层卡校验只查非空），是形状代理语义；refs 存在性义务保留、
    吓阻修辞删除。"""
    prompt_dir = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"
    dead_clauses = {
        # ③ 失效条件【转多】【转空】前缀条款删除——模型填 invalidation_items(direction
        # 枚举 + text)，标签由代码渲染（见 test_contracts.py 的 t69_p2b 测试组）。
        "final_adjudicator.md": ["每条必须以方向标签开头", "每条以【转多】或【转空】开头"],
        # 五层分析师字数下限（代码侧无对应 min_length，层卡校验只查非空）。
        "l2_analyst.md": ["稳定超过 180", "稳定超过 150"],
        "l3_analyst.md": ["稳定超过 180", "稳定超过 160"],
        "l4_analyst.md": ["稳定超过 180", "稳定超过 160"],
        "l5_analyst.md": ["稳定超过 180", "稳定超过 160"],
        # reviser 300/500 字符残留（代码侧上限 2026-07-26 已删，contracts.py 留有注释）。
        "reviser.md": ["最多300字符", "最多500字符"],
        # refs 逐字吓阻：保留"从清单里选"义务，删吓阻修辞。
        "counter_thesis.md": ["逐字来自 `allowed_evidence_refs`"],
    }
    for name, clauses in dead_clauses.items():
        text = (prompt_dir / name).read_text(encoding="utf-8")
        for clause in clauses:
            assert clause not in text, f"{name} 仍残留已清除的死条款：{clause!r}"


def test_prompts_no_longer_carry_id_echo_clauses_t69_p2c():
    """T69 P2c（2026-08-31）编号回声代码化的反向锁定：question_id / hypothesis_id 的
    "逐字回声"条款不得回流——模型只报序号（question_ordinal / hypothesis_ordinal），
    真编号由代码按输入清单顺序展开（同 T58/O15 conflict_ordinal 模式）。
    同族连清：l1 的 layer_synthesis 180 字下限（l2-l5 已于 P2b 清除）。"""
    prompt_dir = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"

    ia = (prompt_dir / "integrated_adjudicator.md").read_text(encoding="utf-8")
    assert "逐字复制" not in ia, "integrated_adjudicator.md 仍残留 question_id 逐字回声条款"
    assert "question_ordinal" in ia, "integrated_adjudicator.md 未告知模型报 question_ordinal"

    reviser = (prompt_dir / "reviser.md").read_text(encoding="utf-8")
    assert "逐字照抄" not in reviser, "reviser.md 仍残留 hypothesis_id 逐字照抄条款"
    assert "hypothesis_ordinal" in reviser, "reviser.md 未告知模型报 hypothesis_ordinal"

    thesis = (prompt_dir / "thesis_builder.md").read_text(encoding="utf-8")
    assert "hypothesis_ordinal" in thesis, "thesis_builder.md 未告知模型报 hypothesis_ordinal"
    assert "<candidate 假说的 hypothesis_id>" not in thesis, "thesis_builder.md 示例仍让模型回声 hypothesis_id"

    l1 = (prompt_dir / "l1_analyst.md").read_text(encoding="utf-8")
    assert "稳定超过 180" not in l1, "l1_analyst.md 仍残留 layer_synthesis 180 字下限"
    assert "归纳本层指标的方向与张力" in l1, "l1_analyst.md 未与 l2-l5 新措辞对齐"


# ── 辅助函数 ──

def _empty_layer_cards(*layers: str) -> list:
    return [_empty_layer_card(layer) for layer in layers]

def _four_empty_cards() -> list:
    return _empty_layer_cards("L1", "L2", "L4", "L5")

def _five_empty_cards() -> list:
    return _empty_layer_cards("L1", "L2", "L3", "L4", "L5")


# ── 甲：输出字段规格由契约生成，形状漂移从结构上根除（2026-07-28 用户裁决） ──

def test_compose_prompt_embeds_contract_generated_field_spec(tmp_path: Path):
    """红灯：真实事故 run 20260728_110702——`claim_ledger` 在 final_adjudicator.md 里
    grep 命中 0 次，模型只能猜形状、猜成裸数组，终审第一次尝试即被 pydantic 拒、整跑硬崩。

    根治不是"记得把字段补进说明书"（那还是靠人），而是让说明书的字段规格**由契约生成**：
    只要字段在 pydantic 模型里，它就一定出现在 prompt 里，并且带上"对象 / 数组 / 是否可 null"。
    本用例锁定三件事：字段一个不漏、嵌套对象不会被渲染成数组、可选字段标注 null。
    """
    orchestrator = _orchestrator(tmp_path)
    spec = orchestrator._render_contract_field_spec(FinalAdjudication)

    # 1) 契约里的每个字段都必须出现，不允许有"说明书没提过"的字段。
    for name in FinalAdjudication.model_fields:
        assert f"`{name}`" in spec, f"契约字段 {name} 没有出现在自动生成的字段规格里"

    # 2) 事故字段的形状必须明确是对象、且点名 entries 子字段——这正是模型当初猜错的地方。
    claim_line = next(line for line in spec.splitlines() if line.startswith("- `claim_ledger`"))
    assert "对象 ClaimLedger" in claim_line
    assert "entries" in claim_line
    assert "数组，元素为" not in claim_line
    assert "或 null" in claim_line

    # 3) 列表型字段要标成数组并点明元素形状（否则模型可能回一个裸对象）。
    price_line = next(line for line in spec.splitlines() if line.startswith("- `price_reflection_map`"))
    assert "数组，元素为 对象 PriceReflectionAssessment" in price_line

    # 4) 必填 / 可选与 Literal 取值要如实呈现。
    confidence_line = next(line for line in spec.splitlines() if line.startswith("- `confidence`"))
    assert "必填" in confidence_line and "取值之一" in confidence_line


def test_compose_prompt_field_spec_declares_shape_authority(tmp_path: Path):
    """规格必须真的进 prompt，并且声明"形状冲突时以规格为准"。

    说明书正文里的手写 JSON 示例仍然保留（它们解释语义），但示例是人写的、会过期；
    自动生成的规格不会。两者冲突时必须有明确的优先级，否则模型只能猜。
    """
    orchestrator = _orchestrator(tmp_path)
    prompt = orchestrator._compose_prompt("final", FinalAdjudication, {"example": "payload"})

    assert "## 输出字段规格（由 FinalAdjudication 契约自动生成，形状以此为准）" in prompt
    assert "`claim_ledger`" in prompt
    assert "形状冲突时以规格为准" in prompt
    # 规格必须排在 Response Rules 之前，读到规则时形状已经交代过了。
    assert prompt.index("## 输出字段规格") < prompt.index("## Response Rules")


def test_field_spec_exposes_constrained_nested_subfield_types(tmp_path: Path):
    """红灯：真实事故 run 20260728_222759——L1 两次尝试全挂，整跑死在第一站。

    甲把嵌套对象的**字段名**写进了规格，却没写子字段的**类型**：core_facts 渲染成
    `对象 CoreFact{metric, value, historical_percentile, trend, magnitude, raw_data}`。
    可 `magnitude` 是 Literal["extreme"…"low"]、`raw_data` 是 dict——规格里都只剩一个名字。

    甲上线前这两个字段在整份 L1 prompt 里出现 0 次，模型压根不填（run 20260728_110702
    五层 57 条 core_facts，magnitude / raw_data 填充率 0/0），于是校验一直通过。甲点名之后
    模型开始填：第一次把 raw_data 填成字符串（9 个 dict_type 错），重试修好 raw_data 又把
    magnitude 填成 -4.9 这类数字（9 个 literal_error），两次尝试用尽、L1 硬失败。

    教训：**只报字段名不报类型，比压根不提更危险**——它把模型从"不填"推到"乱填"。
    本用例扫描所有 stage 契约，凡是嵌套对象里"猜错就硬失败"的子字段（Literal、dict），
    规格里必须带类型，且不得因为字段数上限被截断掉（`TypedConflict.status` 排第 12、
    `CompetingHypothesis.status` 排第 10，正是被截断的两个）。
    """
    source = (
        Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "orchestrator.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    import agent_analysis.contracts as contracts_module

    stage_models: Dict[str, type] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "_run_stage":
            continue
        model_arg = {kw.arg: kw for kw in node.keywords}.get("model_cls")
        if model_arg is None or not isinstance(model_arg.value, ast.Name):
            continue
        model_cls = getattr(contracts_module, model_arg.value.id, None)
        if model_cls is not None and getattr(model_cls, "model_fields", None):
            stage_models[model_arg.value.id] = model_cls

    assert stage_models, "静态扫描没找到任何 _run_stage 的 model_cls——扫描器本身坏了"

    orchestrator = _orchestrator(tmp_path)

    def _constrained_subfields(annotation, seen=frozenset()) -> Dict[type, List[str]]:
        """穷举该注解可达的、所有深度的"猜错就硬失败"子字段。

        这里刻意**不引用** `_CONTRACT_SPEC_MAX_NESTED_DEPTH`：期望值若由实现常量推导，
        把常量调小就能让测试自己闭嘴，闸门等于不存在。要求是绝对的——契约里任何一个
        枚举 / 对象子字段，模型都必须被告知类型；将来真出现更深一层的枚举，这里当场红，
        由人决定是抬高钻取深度还是把契约拍平。
        """
        import typing

        found: Dict[type, List[str]] = {}
        origin = typing.get_origin(annotation)
        if origin is not None:
            for arg in typing.get_args(annotation):
                found.update(_constrained_subfields(arg, seen))
            return found
        sub_fields = getattr(annotation, "model_fields", None)
        if sub_fields is None or annotation in seen:
            return found

        def _hard_typed(inner) -> bool:
            # list 也算：run 20260728_222759 终审把 List[str] 的 uncertainty_notes
            # 写成一整句话被拒，证伪了"复数字段名足以暗示数组"。
            if typing.get_origin(inner) in (typing.Literal, dict, list, set, tuple):
                return True
            return any(_hard_typed(arg) for arg in typing.get_args(inner))

        names = [name for name, f in sub_fields.items() if _hard_typed(f.annotation)]
        if names:
            found[annotation] = names
        # 继续往下钻：ClaimLedgerEntry 的三个枚举就藏在 claim_ledger.entries[] 的第二层。
        for f in sub_fields.values():
            found.update(_constrained_subfields(f.annotation, seen | {annotation}))
        return found

    missing: List[str] = []
    for model_name, model_cls in sorted(stage_models.items()):
        spec = orchestrator._render_contract_field_spec(model_cls)
        for field_name, field in model_cls.model_fields.items():
            line = next(
                (l for l in spec.splitlines() if l.startswith(f"- `{field_name}`")), ""
            )
            for sub_model, sub_names in _constrained_subfields(field.annotation).items():
                for sub_name in sub_names:
                    # 字段名出现还不够：必须带上冒号后的类型，否则模型只能猜。
                    if f"{sub_name}:" not in line:
                        missing.append(
                            f"{model_name}.{field_name} -> "
                            f"{sub_model.__name__}.{sub_name}"
                        )

    assert not missing, (
        "这些嵌套子字段在自动生成的规格里只有名字、没有类型（Literal 的取值范围 / dict 的对象形状）："
        f"{missing}。模型会照着名字乱填，pydantic 当场硬拒——run 20260728_222759 就是这么死的。"
    )


# ── T29：严格模式的离线体检——别拿花钱的真实跑去撞可穷举的 schema 问题 ──

def _stage_contracts() -> Dict[str, type]:
    """静态扫描 orchestrator 里所有 `_run_stage(model_cls=<Name>)` 的契约类。"""
    import agent_analysis.contracts as contracts_module

    source = (
        Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "orchestrator.py"
    ).read_text(encoding="utf-8")
    models: Dict[str, type] = {}
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "_run_stage":
            continue
        arg = {kw.arg: kw for kw in node.keywords}.get("model_cls")
        if arg is None or not isinstance(arg.value, ast.Name):
            continue
        model_cls = getattr(contracts_module, arg.value.id, None)
        if model_cls is not None and getattr(model_cls, "model_fields", None):
            models[arg.value.id] = model_cls
    return models


def test_strict_tool_schema_meets_provider_constraints():
    """红灯：严格模式已经被真实 run 证伪过两次，两次都栽在 schema 转换上。

    `anyOf` 节点缺顶层 type、思考模式与 tool_choice 不兼容——这类问题**可以被程序
    穷举**，不该靠一次花钱的真实跑去撞。本用例把 provider 的硬要求写死成断言：
    每个 object 节点必须 `additionalProperties: false` 且 `required` 覆盖全部属性；
    不得残留 minLength/maxLength/minItems/maxItems/format；`anyOf` 分支若全是原始
    类型（不含 array/object）就必须已经塌缩成 type 数组（否则 DeepSeek 要求同级有
    type）；`anyOf` 分支里含 array/object 的必须保留 anyOf 原样（探针验证过这种
    形态被接受，塌缩反而会撞 400）。

    2026-07-30 增补（②③ 联动的红灯）：`type` 数组本身也不得出现 array/object——
    这是 fix_anyof 的潜伏雷被真实探针证伪过的形态。真实探针错误原文：
    `{'error': {'message': "unknown variant 'array', expected one of string,
    number, integer, boolean, null", ...}}`；`{"type": ["array","null"]}` 会被
    DeepSeek 400 直接拒绝，正确形态是保留 `anyOf: [<array schema>, {"type":
    "null"}]`。

    "没有属性的 object" 单独由下一个用例的登记表管——那是契约设计问题，不是转换 bug。
    """
    from agent_analysis.llm_engine import sanitize_json_schema_for_strict_tool_calling

    violations: List[str] = []

    def _walk(node, path: str, model_name: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                if node.get("additionalProperties") is not False:
                    violations.append(f"{model_name}:{path} object 缺 additionalProperties:false")
                if set(node.get("required") or []) != set(node["properties"]):
                    violations.append(f"{model_name}:{path} required 未覆盖全部 properties")
            if "anyOf" in node and "type" not in node:
                branches = node["anyOf"]
                if all(
                    isinstance(b, dict)
                    and b.get("type") not in ("object", "array", None)
                    and "properties" not in b
                    for b in branches
                ):
                    violations.append(f"{model_name}:{path} anyOf 分支全为原始类型却未塌缩成 type")
            type_value = node.get("type")
            if isinstance(type_value, list):
                invalid_variants = [
                    t for t in type_value if t not in ("string", "number", "integer", "boolean", "null")
                ]
                if invalid_variants:
                    violations.append(
                        f"{model_name}:{path} type 数组含 {invalid_variants}——"
                        "DeepSeek 探针实测对此类形态直接 400："
                        "\"unknown variant 'array', expected one of string, number, "
                        "integer, boolean, null\"（真实错误原文），这类节点必须保留 "
                        "anyOf 结构，不能塌缩进 type 数组"
                    )
            for keyword in ("minLength", "maxLength", "minItems", "maxItems", "format"):
                if keyword in node:
                    violations.append(f"{model_name}:{path} 残留不受支持的关键字 {keyword}")
            for key, value in node.items():
                _walk(value, f"{path}.{key}", model_name)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, f"{path}[{index}]", model_name)

    contracts = _stage_contracts()
    assert contracts, "静态扫描没找到任何 stage 契约——扫描器本身坏了"
    for name, model_cls in sorted(contracts.items()):
        _walk(sanitize_json_schema_for_strict_tool_calling(model_cls.model_json_schema()), "$", name)

    assert not violations, (
        "这些节点不满足 DeepSeek strict function calling 的硬要求，开启严格模式会被 API 拒："
        f"{violations}"
    )


def test_strict_tool_schema_free_form_objects_are_registered():
    """自由形态 object（`Dict[str, Any]` / `extra=allow`）必须逐条登记，不许无声新增。

    严格模式实测报错 "An object with no properties is not allowed"——也就是说，契约里
    每多一个自由形态字段，就多一个站点无法开启严格模式。这不是转换能修的，是契约设计
    的取舍，必须有人显式做决定。

    登记表同时写清"这个字段由谁填"，因为它决定修法：代码事后填的字段本就不该出现在
    给模型的 schema 里，删掉即可；模型真会填的才需要权衡。
    """
    from agent_analysis.llm_engine import (
        STRICT_SCHEMA_FREE_FORM_OBJECTS,
        sanitize_json_schema_for_strict_tool_calling,
    )

    found: List[str] = []

    def _walk(node, path: str, model_name: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" not in node:
                found.append(f"{model_name}:{path}")
            for key, value in node.items():
                _walk(value, f"{path}.{key}", model_name)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, f"{path}[{index}]", model_name)

    for name, model_cls in sorted(_stage_contracts().items()):
        _walk(sanitize_json_schema_for_strict_tool_calling(model_cls.model_json_schema()), "$", name)

    code_filled = {
        key for key, reason in STRICT_SCHEMA_FREE_FORM_OBJECTS.items()
        if str(reason).startswith("代码填")
    }
    unregistered = sorted(set(found) - set(STRICT_SCHEMA_FREE_FORM_OBJECTS))
    stale = sorted(set(STRICT_SCHEMA_FREE_FORM_OBJECTS) - set(found) - code_filled)
    left_code_filled = sorted(set(found) & code_filled)
    assert not unregistered, (
        f"新增了未登记的自由形态 object：{unregistered}。"
        "它会让对应 stage 无法开启严格模式——请登记并写清由谁填，或把字段类型收窄。"
    )
    assert not stale, (
        f"登记表里这些条目已经不存在了：{stale}。修好了就从表里删掉，别留过期登记。"
    )
    assert not left_code_filled, (
        f"这些登记为'代码填'的自由对象应被 sanitizer 剪掉，却仍在发给模型的 schema 里："
        f"{left_code_filled}"
    )
    for key, reason in STRICT_SCHEMA_FREE_FORM_OBJECTS.items():
        assert "填" in reason, f"登记项 {key} 没写清由谁填——那是决定修法的关键信息"


def test_strict_eligible_stage_schemas_have_no_free_form_objects():
    """严格模式白名单内的站，sanitize 后不得残留"无 properties 的 object"。

    2026-08-16 T44：final/reviser/critic 纳入白名单的前提，就是 sanitizer
    把登记为"代码填"的自由对象从发给模型的 schema 里剪掉；这条守护测试
    防止将来白名单扩进一个还带着自由对象的站，真跑时被 DeepSeek 400 拒绝。
    """
    from agent_analysis.llm_engine import sanitize_json_schema_for_strict_tool_calling

    stage_models = {
        "bridge": BridgeMemo,
        "thesis": ThesisDraft,
        "event_card_interpreter": EventInterpretationCard,
        "event_section_summary": EventSectionSummary,
        "reviser": AnalysisRevised,
        "final": FinalAdjudication,
        "critic": Critique,
    }
    offenders = []
    for stage, model_cls in stage_models.items():
        schema = sanitize_json_schema_for_strict_tool_calling(model_cls.model_json_schema())

        def _walk(node, path):
            if isinstance(node, dict):
                if node.get("type") == "object" and "properties" not in node:
                    offenders.append(f"{stage}:{path}")
                for key, value in node.items():
                    _walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    _walk(value, f"{path}[{index}]")

        _walk(schema, "$")
    assert not offenders, (
        f"严格模式白名单内的站，sanitize 后仍有无 properties 的 object：{offenders}。"
        "代码填的自由对象应被 sanitizer 剪掉；模型填的对象则说明该站还不该进严格白名单。"
    )


# ── 丙：登记不能靠人记得——反射枚举所有带 validator 的 stage（2026-07-28 用户裁决） ──

def test_every_validator_bearing_stage_is_registered_in_prompt_requirements():
    """红灯：加了 stage validator 却忘了登记 → 合约会考、说明书没写、模型必挂。

    `STAGE_CONTRACT_PROMPT_REQUIREMENTS` 此前是**手填**的：新增一条 validator 不会强迫
    任何人去登记表里加一行。真实代价：`_validate_bridge_memo_v2` 硬性要求 resonance_chains
    的 confirming_indicators / falsifiers 非空，而 cross_layer_bridge.md 里这两个词各出现
    0 次——真实 run 20260728_110702 的 bridge 因此重试一次，烧掉一次 11 万 token 的调用。

    本用例静态扫描 orchestrator.py 里所有 `self._run_stage(...)` 调用，凡是带了
    `validator=` 且 stage_key 是字面量的，都必须在登记表里有一行；stage_key 是运行时
    拼出来的调用点必须落在显式豁免名单里，并写清豁免理由。这样"忘了登记"从"靠人记得"
    变成"测试当场红"。
    """
    source = (
        Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "orchestrator.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    literal_stages: Dict[str, int] = {}
    dynamic_sites: List[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "_run_stage"):
            continue
        keywords = {kw.arg: kw for kw in node.keywords}
        if "validator" not in keywords:
            continue
        stage_key = keywords.get("stage_key")
        if stage_key is not None and isinstance(stage_key.value, ast.Constant):
            literal_stages[str(stage_key.value.value)] = node.lineno
        else:
            dynamic_sites.append(node.lineno)

    assert literal_stages, "静态扫描没找到任何带 validator 的 _run_stage 调用——扫描器本身坏了"

    unregistered = {
        stage: line
        for stage, line in literal_stages.items()
        if stage not in STAGE_CONTRACT_PROMPT_REQUIREMENTS
    }
    assert not unregistered, (
        f"这些 stage 挂了 validator 却没有登记进 STAGE_CONTRACT_PROMPT_REQUIREMENTS："
        f"{unregistered}（键是 stage_key，值是 orchestrator.py 行号）。"
        "合约会因此判失败，但模型从未被告知该要求——请补 prompt 并登记关键词。"
    )

    # 豁免必须看得见：运行时拼 stage_key 的调用点数量变化时，这里要有人重新裁决一次。
    assert len(dynamic_sites) == len(DYNAMIC_STAGE_KEY_CALL_SITES), (
        f"带 validator 但 stage_key 为动态值的 _run_stage 调用点有 {len(dynamic_sites)} 处"
        f"（行号 {dynamic_sites}），而豁免名单登记了 {len(DYNAMIC_STAGE_KEY_CALL_SITES)} 条。"
        "新增动态调用点必须显式登记豁免理由，不能沉默跳过。"
    )
    for stage, reason in DYNAMIC_STAGE_KEY_CALL_SITES.items():
        assert reason.strip(), f"豁免项 {stage} 没有写理由——豁免必须带理由"


def test_registered_prompt_requirement_keywords_are_not_vacuous():
    """登记表本身也要防退化：不许用空串或单字符关键词把闸门骗过去。"""
    for stage, keywords in STAGE_CONTRACT_PROMPT_REQUIREMENTS.items():
        assert keywords, f"stage `{stage}` 登记了空的关键词元组，等于没登记"
        for keyword in keywords:
            assert len(str(keyword).strip()) >= 2, (
                f"stage `{stage}` 的登记关键词 `{keyword}` 过短，"
                "几乎必然在任何 prompt 里命中，起不到闸门作用"
            )


# ── 单一事实源闸门（2026-07-28 全仓审计的产物） ──

def test_metric_authority_usage_vocabulary_has_exactly_one_source():
    """红灯：证据权限等级此前分两处各存一份，且已经漂移。

    `_field_authority_from_payload` 里的 `usage_rank` 既当排序表又当白名单，而 36 行
    之后的 `_field_authority_usages` 另写了一份 `allowed` 集合。`usage_rank` 漏收
    `validation_only`（"经第三方交叉校验的值"，`tools_L4.py` 有 6 处真实产出），于是
    真实 usage 一进合并逻辑就被静默改写成 `audit_only`，报告里"这条证据为何被降级"
    的审计文案与工具本意对不上——直接戳中"可审计推理链"。

    修法是合并成一份 `METRIC_AUTHORITY_USAGE_RANK`，白名单从它的键派生。
    """
    from agent_analysis.orchestrator import METRIC_AUTHORITY_USAGE_RANK

    orchestrator = VNextOrchestrator.__new__(VNextOrchestrator)

    # 1) 白名单与排序表必须是同一份事实，不允许再各写一份。
    assert orchestrator._field_authority_usages(
        {name: {"usage": name} for name in METRIC_AUTHORITY_USAGE_RANK}
    ) == set(METRIC_AUTHORITY_USAGE_RANK)

    # 2) 事故形态：validation_only 必须原样保留，不得被改写成 audit_only。
    merged = orchestrator._field_authority_from_payload(
        {"value": {"MetricAuthority": {"pe_vs_yahoo": {"usage": "validation_only"}}}}
    )
    assert merged["pe_vs_yahoo"]["usage"] == "validation_only"

    # 3) 两来源冲突时仍取更保守的一档（既有语义不得被本次修复削弱）。
    conflicted = orchestrator._field_authority_from_payload(
        {
            "value": {"MetricAuthority": {"f": {"usage": "core_allowed"}}},
            "data_quality": {"metric_authority": {"f": {"usage": "supporting_only"}}},
        }
    )
    assert conflicted["f"]["usage"] == "supporting_only"

    # 4) 真正未知的 usage 仍然要被兜底成 audit_only，不能借这次放宽混进来。
    unknown = orchestrator._field_authority_from_payload(
        {"value": {"MetricAuthority": {"f": {"usage": "totally_made_up"}}}}
    )
    assert unknown["f"]["usage"] == "audit_only"


def test_price_reflection_category_list_has_exactly_one_source():
    """红灯：五类价格反映名单此前在 orchestrator 与 run_review 各存一份字面量。

    两者当时内容一致，但没有任何机制保证它们一起变——改一处漏一处，复盘检查会开始
    要求或放过错误的类别，而且不会报错。现在统一派生自
    `contracts.PRICE_REFLECTION_CATEGORY_KEYS`。
    """
    from agent_analysis.contracts import PRICE_REFLECTION_CATEGORY_KEYS
    from agent_analysis.orchestrator import PRICE_REFLECTION_CATEGORIES
    from agent_analysis.run_review import REQUIRED_PRICE_REFLECTION_CATEGORIES

    assert set(PRICE_REFLECTION_CATEGORIES) == set(PRICE_REFLECTION_CATEGORY_KEYS), (
        "orchestrator 的富字典键与唯一名单漂移了——新增/删除类别时两处必须一起改"
    )
    assert REQUIRED_PRICE_REFLECTION_CATEGORIES == set(PRICE_REFLECTION_CATEGORY_KEYS)
    # 富字典每一类都要写全 target/label/hint，否则代码补齐时会拼出空文案。
    for name, meta in PRICE_REFLECTION_CATEGORIES.items():
        assert meta.get("target") and meta.get("label") and meta.get("hint"), name


# ── T70 P-B（2026-09-02 人话工程）：事实卡输入（构造即忠实）──

def test_t70_governance_input_carries_fact_card_for_final(tmp_path: Path):
    """事实卡=本段允许出现的数字菜单（指标名+读数+ref+权限档），由代码装配。

    写作层只从卡里选用数字，数字写错=装配 bug（自检响了修管道，不打回模型）。
    risk 是论证盲分料，不带事实卡。"""
    orchestrator = _orchestrator(tmp_path)
    synthesis = SynthesisPacket(
        evidence_index={
            "L1.get_10y_real_rate": {
                "layer": "L1",
                "function_id": "get_10y_real_rate",
                "metric": "10Y Real Rate",
                "current_reading": "2.35%，10年分位99.3%",
                "permission_type": "core_allowed",
            },
            "L4.get_m7_capex_cycle#m7_quarterly_total": {
                "layer": "L4",
                "function_id": "get_m7_capex_cycle",
                "metric": "M7 Capex",
                "parent_evidence_ref": "L4.get_m7_capex_cycle",
                "field_name": "m7_quarterly_total",
                "field_value": "542.1亿美元",
                "field_authority": {"usage": "supporting_only"},
            },
        },
    )
    thesis = ThesisDraft(
        main_thesis="中性。",
        environment_assessment="宏观中性。",
        valuation_assessment="估值中性。",
        timing_assessment="趋势中性。",
        overall_confidence=Confidence.MEDIUM,
        dependencies=[],
        key_support_chains=[
            KeySupportChain(
                chain_description="利率压制估值。",
                evidence_refs=["L1.get_10y_real_rate", "L4.get_m7_capex_cycle#m7_quarterly_total"],
                weight=0.6,
            )
        ],
    )

    gov_input = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="final",
    )
    card = getattr(gov_input, "fact_card", None)
    assert card, "final 的 governance input 必须带事实卡"
    by_ref = {entry["ref"]: entry for entry in card}
    assert by_ref["L1.get_10y_real_rate"]["reading"] == "2.35%，10年分位99.3%"
    assert by_ref["L1.get_10y_real_rate"]["label"] == "10Y Real Rate"
    child = by_ref["L4.get_m7_capex_cycle#m7_quarterly_total"]
    assert child["reading"] == "542.1亿美元"
    assert child["authority"] == "supporting_only"  # 权限档跟着数字走，不得冒充强证据

    gov_risk = orchestrator._build_governance_input_packet(
        synthesis_packet=synthesis,
        thesis=thesis,
        consumer="risk",
    )
    assert not getattr(gov_risk, "fact_card", []), "risk 论证盲不带事实卡"
