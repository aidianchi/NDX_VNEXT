import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    AnalysisRevised,
    ApprovalStatus,
    Confidence,
    FinalAdjudication,
    IndicatorAnalysis,
    Layer,
    LayerCard,
    CoreFact,
    ThesisDraft,
)
from agent_analysis.legacy_adapter import adapt_vnext_to_legacy


def _base_contracts():
    card = LayerCard(
        layer=Layer.L1,
        core_facts=[
            CoreFact(metric="fed_rate", value=5.25, historical_percentile=85.0, trend="rising", magnitude="high"),
        ],
        local_conclusion="流动性环境偏紧，高利率仍在压制高估值资产。",
        confidence=Confidence.MEDIUM,
        risk_flags=["restrictive_policy"],
        notes="如果降息推迟，高估值资产的折现压力会继续停留在高位。",
    )
    thesis = ThesisDraft(
        environment_assessment="宏观流动性偏紧，但市场仍在等待政策转向。",
        valuation_assessment="估值承压。",
        timing_assessment="趋势尚未完全破坏。",
        main_thesis="中性偏谨慎。",
        dependencies=["需要看到降息路径更清晰。"],
        overall_confidence=Confidence.MEDIUM,
    )
    revised = AnalysisRevised(
        revision_summary="补强了高利率压制估值的解释。",
        accepted_critiques=["保留高利率与高估值之间的冲突。"],
        revised_thesis=thesis,
    )
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="中性偏谨慎",
        confidence=Confidence.MEDIUM,
        must_preserve_risks=["高利率与高估值并存时，估值压缩风险显著。"],
        adjudicator_notes="可放行，但必须保留利率约束。",
    )
    return final, revised, [card]


def test_adapter_produces_legacy_keys():
    final, revised, cards = _base_contracts()

    result = adapt_vnext_to_legacy(final, revised, cards, [], {"confidence_percent": 95.0})
    logic = result["__LOGIC__"]

    assert "market_regime_analysis" in logic
    assert "layer_conclusions" in logic
    assert "indicator_narratives" in logic
    assert "revision_summary" in logic


def test_adapter_uses_data_json_metric_names_and_populates_reasoning_process():
    final, revised, cards = _base_contracts()
    data_json = {
        "indicators": [
            {
                "layer": 1,
                "metric_name": "Fed Funds Rate",
                "function_id": "get_fed_funds_rate",
                "raw_data": {
                    "value": {
                        "level": 5.25,
                        "trend": "rising",
                        "relativity": {"percentile_10y": 0.85},
                    }
                },
            }
        ]
    }
    risk_report = {
        "must_preserve_risks": ["高利率会继续压制高估值资产。"],
        "conflict_matrix_check": {"C_expensive_valuation_vs_strong_trend": True},
    }

    result = adapt_vnext_to_legacy(
        final,
        revised,
        cards,
        [],
        {"confidence_percent": 95.0},
        data_json=data_json,
        risk_boundary_report=risk_report,
    )
    items = result["__LOGIC__"]["indicator_narratives"]["layer_1"]

    assert len(items) == 1
    assert items[0]["metric"] == "Fed Funds Rate"
    assert "5.25" in items[0]["narrative"]
    assert items[0]["reasoning_process"]
    assert "高利率" in items[0]["reasoning_process"]
    assert result["__LOGIC__"]["market_regime_analysis"]["identified_conflict_scenario_ID"] == "C"


def test_adapter_prefers_native_indicator_analyses_over_synthetic_fallback():
    final, revised, cards = _base_contracts()
    cards[0].indicator_analyses = [
        IndicatorAnalysis(
            function_id="get_fed_funds_rate",
            metric="Fed Funds Rate",
            current_reading="5.25%，限制性",
            normalized_state="restrictive",
            narrative="原生叙事：政策利率仍在限制性区间。",
            reasoning_process="原生推理：先看政策利率绝对水平，再推导折现率对成长股估值的压制。",
            first_principles_chain=["政策利率高", "无风险利率高", "估值倍数受压"],
            evidence_refs=["L1.get_fed_funds_rate"],
            cross_layer_implications=["需要 L4 验证估值承压"],
            confidence="medium",
        )
    ]
    data_json = {
        "indicators": [
            {
                "layer": 1,
                "metric_name": "Fed Funds Rate",
                "function_id": "get_fed_funds_rate",
                "raw_data": {"value": {"level": 5.25}},
            }
        ]
    }

    result = adapt_vnext_to_legacy(
        final,
        revised,
        cards,
        [],
        {"confidence_percent": 95.0},
        data_json=data_json,
    )
    item = result["__LOGIC__"]["indicator_narratives"]["layer_1"][0]

    assert item["narrative"] == "原生叙事：政策利率仍在限制性区间。"
    assert "原生推理" in item["reasoning_process"]
    assert "政策利率高" in item["reasoning_process"]


def test_adapter_declares_compatibility_only_role():
    final, revised, cards = _base_contracts()

    result = adapt_vnext_to_legacy(final, revised, cards, [], {"confidence_percent": 95.0})
    native = result["__LOGIC__"]["vnext_native_artifacts"]

    assert native["adapter_policy"]["legacy_adapter_role"] == "compatibility_mapping_only"
    assert native["adapter_policy"]["primary_reasoning_source"] == "vnext_artifacts"
