import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    AnalysisPacket,
    BridgeMemo,
    Confidence,
    ContextBrief,
    CoreFact,
    IndicatorAnalysis,
    LayerCard,
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


def test_synthesis_packet_includes_objective_firewall_summary(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    packet = AnalysisPacket(meta={"data_date": "2026-04-24"}, raw_data={})
    context = ContextBrief(data_summary="data", task_description="task")
    layer_cards = [_empty_layer_card(layer) for layer in ["L2", "L3", "L4", "L5"]]
    layer_cards.insert(
        0,
        LayerCard(
            layer="L1",
            core_facts=[CoreFact(metric="real_rate", value=1.9)],
            local_conclusion="L1 偏紧。",
            confidence=Confidence.MEDIUM,
            indicator_analyses=[
                IndicatorAnalysis(
                    function_id="get_10y_real_rate",
                    metric="10Y Real Rate",
                    narrative="真实利率偏高。",
                    reasoning_process="真实利率偏高会压制成长股估值。",
                    evidence_refs=["L1.get_10y_real_rate"],
                    permission_type="fact",
                    canonical_question="真实贴现率是否正在给 NDX 估值施压？",
                    misread_guards=["不是单纯的政策变量。"],
                    cross_validation_targets=["get_ndx_pe_and_earnings_yield"],
                    falsifiers=["盈利上修足以抵消折现率压力。"],
                    core_vs_tactical_boundary="核心框架指标。",
                )
            ],
        ),
    )
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
            )
        ],
        implication_for_ndx="需要保留冲突。",
    )

    synthesis = orchestrator._build_synthesis_packet(packet, context, layer_cards, [bridge])
    firewall = synthesis.objective_firewall_summary

    assert firewall is not None
    assert firewall.object_clear is True
    assert firewall.authority_clear is True
    assert firewall.cross_layer_verified is True
    assert "盈利上修" in firewall.strongest_falsifier
    assert any("real_rate_vs_valuation" in item for item in firewall.unresolved_tensions)


def test_thesis_prompt_mentions_objective_firewall_summary(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )

    prompt = orchestrator._compose_thesis_prompt("body")

    assert "objective_firewall_summary" in prompt
    assert "指标发言权" in prompt
