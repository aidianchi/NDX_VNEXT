import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    AnalysisPacket,
    BridgeMemo,
    BridgeSynthesisItem,
    Confidence,
    ContradictionTransformationSignal,
    Conflict,
    ConflictSeverity,
    ContextBrief,
    CoreFact,
    LayerCard,
    PriceReflectionAssessment,
    PrincipalContradiction,
    ResonanceChain,
    SecondaryContradiction,
    TransmissionPath,
    TypedConflict,
)
from agent_analysis.orchestrator import VNextOrchestrator


def test_bridge_memo_accepts_v2_typed_map_fields():
    memo = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        typed_conflicts=[
            TypedConflict(
                conflict_id="real_rate_vs_valuation",
                conflict_type="valuation_discount_rate",
                severity="high",
                confidence="medium",
                description="高真实利率与高估值并存。",
                mechanism="真实利率提高折现率，压缩成长股估值容忍度。",
                implication="NDX 估值需要盈利强度或利率回落确认。",
                involved_layers=["L1", "L4"],
                evidence_refs=["L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield"],
                event_refs=["event:fomc"],
                falsifiers=["盈利上修足以抵消折现率压力。"],
            )
        ],
        resonance_chains=[
            ResonanceChain(
                chain_id="risk_on_trend",
                description="风险偏好和价格趋势同向。",
                involved_layers=["L2", "L5"],
                evidence_refs=["L2.get_vix", "L5.get_qqq_technical_indicators"],
                event_refs=["event:vix_context"],
                confirming_indicators=["get_vix", "get_qqq_technical_indicators"],
                mechanism="波动回落降低持仓压力，趋势更容易延续。",
                implication="短线执行环境改善。",
                falsifiers=["波动重新上行且价格跌破关键均线。"],
                confidence="medium",
            )
        ],
        transmission_paths=[
            TransmissionPath(
                path_id="rates_to_valuation",
                source_layer="L1",
                target_layer="L4",
                mechanism="真实利率通过折现率传导到估值倍数。",
                evidence_refs=["L1.get_10y_real_rate", "L4.get_equity_risk_premium"],
                event_refs=["event:rates_context"],
                implication="估值安全边际变薄。",
                confidence="medium",
            )
        ],
        principal_contradiction=PrincipalContradiction(
            contradiction_id="real_rate_vs_valuation",
            summary="高真实利率与估值修复并存。",
            why_principal="它决定估值压缩风险是否已转化为可行动赔率。",
            dominant_side="高真实利率仍压制核心仓置信度。",
            secondary_side="估值压缩可能提高战术赔率。",
            price_reflection="partially_reflected",
            action_implication="战术仓分批，核心仓守纪律。",
            conflict_refs=["real_rate_vs_valuation"],
            evidence_refs=["L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield"],
            transformation_signals=[
                ContradictionTransformationSignal(
                    signal="信用不再恶化且趋势守住恐慌低点",
                    direction="toward_payoff_repair",
                    implication="战术仓可提高一级。",
                    evidence_refs=["L2.get_credit_spreads", "L5.get_ta_indicators"],
                )
            ],
            unresolved_questions=["盈利能否抵消高真实利率？"],
        ),
        secondary_contradictions=[
            SecondaryContradiction(
                contradiction_id="breadth_vs_trend",
                summary="反弹质量仍受广度约束。",
                why_secondary="当前不是估值赔率判断的主导项。",
                action_constraint="限制加仓速度。",
                evidence_refs=["L3.get_market_breadth"],
            )
        ],
        price_reflection_map=[
            PriceReflectionAssessment(
                target="real_rate_vs_valuation",
                reflected_state="partially_reflected",
                rationale="估值压缩说明部分坏消息进入价格。",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
            )
        ],
        contradiction_transformation_signals=[
            ContradictionTransformationSignal(
                signal="信用继续恶化",
                direction="toward_risk_not_reflected",
                implication="战术仓降级。",
                evidence_refs=["L2.get_credit_spreads"],
            )
        ],
        unresolved_questions=["盈利能否抵消高真实利率？"],
        implication_for_ndx="需要保留利率-估值冲突。",
    )

    assert memo.typed_conflicts[0].severity == ConflictSeverity.HIGH
    assert memo.typed_conflicts[0].event_refs == ["event:fomc"]
    assert memo.resonance_chains[0].involved_layers[0] == "L2"
    assert memo.resonance_chains[0].confirming_indicators == ["get_vix", "get_qqq_technical_indicators"]
    assert memo.resonance_chains[0].falsifiers == ["波动重新上行且价格跌破关键均线。"]
    assert memo.transmission_paths[0].source_layer == "L1"
    assert memo.principal_contradiction.contradiction_id == "real_rate_vs_valuation"
    assert memo.price_reflection_map[0].reflected_state == "partially_reflected"


def test_orchestrator_derives_typed_conflicts_from_legacy_bridge_payload(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    normalized = orchestrator._normalize_payload(
        "bridge",
        {
            "bridge_type": "macro_valuation",
            "layers_connected": ["L1", "L4"],
            "conflicts": [
                {
                    "conflict_type": "L1_restrictive_vs_L4_expensive",
                    "severity": "high",
                    "description": "高真实利率与高估值并存。",
                    "implication": "估值压缩风险需要保留。",
                    "involved_layers": ["L1", "L4"],
                }
            ],
            "implication_for_ndx": "需要保留冲突。",
        },
    )

    assert normalized["typed_conflicts"][0]["conflict_id"] == "L1_restrictive_vs_L4_expensive"
    assert normalized["typed_conflicts"][0]["evidence_refs"] == []
    assert normalized["principal_contradiction"]["contradiction_id"] == "L1_restrictive_vs_L4_expensive"
    assert normalized["principal_contradiction"]["price_reflection"] == "unclear"
    assert normalized["price_reflection_map"][0]["target"] == "L1_restrictive_vs_L4_expensive"


def test_synthesis_packet_carries_bridge_v2_typed_map(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    packet = AnalysisPacket(
        meta={"data_date": "2026-04-24"},
        raw_data={},
        event_refs={
            "event:fomc": {
                "event_id": "event:fomc",
                "title": "FOMC statement",
                "usage_boundary": "event_ref only",
            }
        },
    )
    context = ContextBrief(data_summary="data", task_description="task")
    layer_cards = [
        LayerCard(
            layer=layer,
            core_facts=[CoreFact(metric="placeholder", value="n/a")],
            local_conclusion=f"{layer} conclusion",
            confidence=Confidence.MEDIUM,
        )
        for layer in ["L1", "L2", "L3", "L4", "L5"]
    ]
    legacy_conflict = Conflict(
        conflict_type="L1_restrictive_vs_L4_expensive",
        severity=ConflictSeverity.HIGH,
        description="高真实利率与高估值并存。",
        implication="估值压缩风险需要保留。",
        involved_layers=["L1", "L4"],
    )
    bridge = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        conflicts=[legacy_conflict],
        typed_conflicts=[
            TypedConflict(
                conflict_id="L1_restrictive_vs_L4_expensive",
                conflict_type="valuation_discount_rate",
                severity=ConflictSeverity.HIGH,
                confidence=Confidence.MEDIUM,
                description="高真实利率与高估值并存。",
                mechanism="真实利率提高折现率。",
                implication="估值压缩风险需要保留。",
                involved_layers=["L1", "L4"],
                evidence_refs=["L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield"],
                event_refs=["event:fomc"],
            )
        ],
        resonance_chains=[],
        transmission_paths=[],
        unresolved_questions=["盈利能否抵消？"],
        event_refs=["event:fomc"],
        principal_contradiction=PrincipalContradiction(
            contradiction_id="L1_restrictive_vs_L4_expensive",
            summary="高真实利率与高估值并存。",
            why_principal="它决定估值风险是否压倒赔率修复。",
            dominant_side="折现率压力仍在。",
            secondary_side="估值压缩带来赔率改善可能。",
            price_reflection="unclear",
            action_implication="保持战术动作纪律。",
            conflict_refs=["L1_restrictive_vs_L4_expensive"],
            evidence_refs=["L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield"],
        ),
        secondary_contradictions=[
            SecondaryContradiction(
                contradiction_id="trend_vs_breadth",
                summary="趋势与广度仍需验证。",
                why_secondary="不是当前估值冲突主导项。",
                action_constraint="限制加仓速度。",
                evidence_refs=["L5.get_ta_indicators"],
            )
        ],
        price_reflection_map=[
            PriceReflectionAssessment(
                target="L1_restrictive_vs_L4_expensive",
                reflected_state="unclear",
                rationale="Bridge 仍缺价格反映证据。",
                evidence_refs=["L1.get_10y_real_rate"],
            )
        ],
        implication_for_ndx="需要保留冲突。",
    )

    packet_out = orchestrator._build_synthesis_packet(packet, context, layer_cards, [bridge])
    summary = packet_out.bridge_summaries[0]

    assert isinstance(summary, BridgeSynthesisItem)
    assert summary.typed_conflicts[0]["conflict_id"] == "L1_restrictive_vs_L4_expensive"
    assert summary.event_refs == ["event:fomc"]
    assert summary.principal_contradiction["contradiction_id"] == "L1_restrictive_vs_L4_expensive"
    assert summary.secondary_contradictions[0]["contradiction_id"] == "trend_vs_breadth"
    assert summary.price_reflection_map[0]["reflected_state"] == "unclear"
    assert packet_out.principal_contradictions[0].contradiction_id == "L1_restrictive_vs_L4_expensive"
    assert packet_out.event_index["event:fomc"]["title"] == "FOMC statement"
    assert packet_out.high_severity_typed_conflicts[0].conflict_id == "L1_restrictive_vs_L4_expensive"


def test_bridge_prompt_requests_v2_typed_map(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )

    prompt = orchestrator._compose_bridge_prompt("body")

    assert "typed_conflicts" in prompt
    assert "resonance_chains" in prompt
    assert "confirming_indicators" in prompt
    assert "falsifiers" in prompt
    assert "transmission_paths" in prompt
    assert "principal_contradiction" in prompt
    assert "price_reflection_map" in prompt
    assert "contradiction_transformation_signals" in prompt
    assert "unresolved_questions" in prompt
    assert "event_refs" in prompt


def test_bridge_validator_requires_complete_resonance_chain_fields(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    bridge = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        resonance_chains=[
            ResonanceChain(
                chain_id="soft_chain",
                description="缺少硬证据的共振链。",
                involved_layers=["L1", "L4"],
                evidence_refs=[],
                confirming_indicators=[],
                mechanism="",
                implication="",
                falsifiers=[],
            )
        ],
        implication_for_ndx="谨慎。",
    )

    errors = orchestrator._validate_bridge_memo_v2(bridge)

    assert "bridge.resonance_chains[soft_chain].evidence_refs must not be empty." in errors
    assert "bridge.resonance_chains[soft_chain].confirming_indicators must not be empty." in errors
    assert "bridge.resonance_chains[soft_chain].mechanism is required." in errors
    assert "bridge.resonance_chains[soft_chain].falsifiers must not be empty." in errors


def test_bridge_normalize_coerces_top_level_event_refs_to_list(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )

    dict_payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L4"],
        "implication_for_ndx": "需要保留冲突。",
        "event_refs": {
            "event:6479503280a4bf43": {"title": "BLS release"},
            "event:f71e0fd17b6261c5": {"title": "NVDA 8-K"},
        },
    }
    normalized_dict = orchestrator._normalize_payload("bridge", dict_payload)
    assert isinstance(normalized_dict["event_refs"], list)
    assert normalized_dict["event_refs"] == [
        "event:6479503280a4bf43",
        "event:f71e0fd17b6261c5",
    ]
    assert BridgeMemo.model_validate(normalized_dict).event_refs == [
        "event:6479503280a4bf43",
        "event:f71e0fd17b6261c5",
    ]

    string_payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L4"],
        "implication_for_ndx": "需要保留冲突。",
        "event_refs": "event:single",
    }
    normalized_str = orchestrator._normalize_payload("bridge", string_payload)
    assert normalized_str["event_refs"] == ["event:single"]

    list_of_dicts_payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L4"],
        "implication_for_ndx": "需要保留冲突。",
        "event_refs": [
            {"event_id": "event:abc"},
            {"id": "event:def"},
        ],
    }
    normalized_lod = orchestrator._normalize_payload("bridge", list_of_dicts_payload)
    assert normalized_lod["event_refs"] == ["event:abc", "event:def"]

    none_payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L4"],
        "implication_for_ndx": "需要保留冲突。",
        "event_refs": None,
    }
    normalized_none = orchestrator._normalize_payload("bridge", none_payload)
    assert normalized_none["event_refs"] == []


def test_bridge_normalize_coerces_nested_event_refs_without_stringifying_dicts(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )

    payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L4"],
        "implication_for_ndx": "需要保留冲突。",
        "typed_conflicts": [
            {
                "conflict_id": "C1",
                "conflict_type": "macro_valuation",
                "severity": "high",
                "confidence": "high",
                "description": "冲突描述",
                "mechanism": "机制",
                "implication": "含义",
                "involved_layers": ["L1", "L4"],
                "evidence_refs": ["L1.x"],
                "event_refs": {"event:abc": {"title": "FOMC"}},
                "falsifiers": ["利率回落"],
            }
        ],
        "resonance_chains": [
            {
                "chain_id": "R1",
                "description": "共振描述",
                "mechanism": "机制",
                "implication": "含义",
                "confidence": "medium",
                "involved_layers": ["L2", "L5"],
                "evidence_refs": ["L2.x"],
                "event_refs": [{"event_id": "event:def"}],
                "confirming_indicators": ["L5.x"],
                "falsifiers": ["风险偏好逆转"],
            }
        ],
        "transmission_paths": [
            {
                "path_id": "T1",
                "source_layer": "L1",
                "target_layer": "L4",
                "mechanism": "传导机制",
                "implication": "传导含义",
                "confidence": "medium",
                "evidence_refs": ["L1.y"],
                "event_refs": {"event:ghi": {"title": "CPI"}},
            }
        ],
    }

    normalized = orchestrator._normalize_payload("bridge", payload)

    assert normalized["typed_conflicts"][0]["event_refs"] == ["event:abc"]
    assert normalized["resonance_chains"][0]["event_refs"] == ["event:def"]
    assert normalized["transmission_paths"][0]["event_refs"] == ["event:ghi"]
    assert BridgeMemo.model_validate(normalized)


def test_bridge_normalize_dedupes_transmission_path_ids_and_fills_implication(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )

    payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L2", "L4", "L5"],
        "implication_for_ndx": "需要保留冲突。",
        "typed_conflicts": [
            {
                "conflict_id": "real_rate_vs_valuation",
                "conflict_type": "macro_valuation",
                "severity": "high",
                "confidence": "high",
                "description": "实际利率与估值冲突。",
                "mechanism": "折现率上升压缩估值。",
                "implication": "核心仓要谨慎。",
                "involved_layers": ["L1", "L4"],
                "evidence_refs": ["L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield"],
                "falsifiers": ["实际利率回落"],
            }
        ],
        "transmission_paths": [
            {
                "path_id": "transmission_path",
                "source_layer": "L1",
                "target_layer": "L4",
                "mechanism": "实际利率上升传导到估值压缩。",
                "evidence_refs": ["L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield"],
            },
            {
                "path_id": "transmission_path",
                "source_layer": "L2",
                "target_layer": "L5",
                "mechanism": "信用压力传导到价格趋势。",
                "evidence_refs": ["L2.get_hy_oas_bp", "L5.get_qqq_technical_indicators"],
            },
        ],
    }

    normalized = orchestrator._normalize_payload("bridge", payload)

    paths = normalized["transmission_paths"]
    assert [item["path_id"] for item in paths] == ["l1_to_l4_1", "l2_to_l5_2"]
    assert paths[0]["implication"] == "实际利率上升传导到估值压缩。"
    assert paths[1]["implication"] == "信用压力传导到价格趋势。"
    memo = BridgeMemo.model_validate(normalized)
    assert orchestrator._validate_bridge_memo_v2(memo) == []


def test_bridge_prompt_anchors_event_refs_as_string_list(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )

    prompt = orchestrator._compose_bridge_prompt("body")

    assert "BridgeMemo.event_refs" in prompt
    assert "List[str]" in prompt
    assert '["event:' in prompt
