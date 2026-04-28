"""GovernanceInputPacket unit tests — ensure narrow input preserves critical signals."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    AnalysisPacket,
    BridgeMemo,
    Confidence,
    Conflict,
    ContextBrief,
    CoreFact,
    GovernanceInputPacket,
    IndicatorAnalysis,
    KeySupportChain,
    LayerCard,
    ObjectiveFirewallSummary,
    SynthesisPacket,
    ThesisDraft,
    TypedConflict,
)
from agent_analysis.orchestrator import VNextOrchestrator


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
            "weight": 0.35,
        }
    ]
    assert "L1.get_10y_real_rate" in gov_input.key_evidence_refs
    assert "L4.get_ndx_pe_and_earnings_yield" in gov_input.key_evidence_refs


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

    # 确认 risk 和 final 仍明确禁止编造统计
    for name in ["risk_sentinel.md", "final_adjudicator.md"]:
        text = (prompt_dir / name).read_text(encoding="utf-8")
        assert "不得编造历史胜率、回测收益、样本区间或概率数字" in text, f"{name} missing ban on fabricated statistics"


# ── 辅助函数 ──

def _empty_layer_cards(*layers: str) -> list:
    return [_empty_layer_card(layer) for layer in layers]

def _four_empty_cards() -> list:
    return _empty_layer_cards("L1", "L2", "L4", "L5")

def _five_empty_cards() -> list:
    return _empty_layer_cards("L1", "L2", "L3", "L4", "L5")
