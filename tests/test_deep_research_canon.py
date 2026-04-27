import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    AnalysisPacket,
    BridgeMemo,
    Confidence,
    Conflict,
    ConflictSeverity,
    CoreFact,
    Critique,
    IndicatorAnalysis,
    KeySupportChain,
    LayerCard,
    PermissionType,
    RiskBoundaryReport,
    ThesisDraft,
)
from agent_analysis.deep_research_canon import (
    INDICATOR_CANONS,
    build_layer_canon_prompt,
    build_object_canon,
    get_indicator_canon,
    get_layer_indicator_canons,
)
from agent_analysis.orchestrator import VNextOrchestrator
from agent_analysis.packet_builder import LAYER_FUNCTIONS


def test_object_canon_defines_ndx_and_proxy_boundaries():
    canon = build_object_canon()

    assert canon.primary_object == "NDX"
    assert canon.tradable_proxy == "QQQ"
    assert "QQQ 不是所有科技股" in " ".join(canon.methodology_boundaries)
    assert any("NDXE" in item or "QEW" in item for item in canon.methodology_boundaries)


def test_indicator_canon_explains_permission_and_falsifiers():
    canon = get_indicator_canon("get_10y_real_rate")

    assert canon.function_id == "get_10y_real_rate"
    assert canon.layer == "L1"
    assert canon.permission_type == PermissionType.FACT
    assert "真实贴现率" in canon.canonical_question
    assert any("不是单纯的政策变量" in item for item in canon.misread_guards)
    assert any("盈利" in item or "广度" in item for item in canon.falsifiers)
    assert canon.b_prompt


def test_indicator_canon_covers_all_packet_builder_functions():
    expected = set().union(*LAYER_FUNCTIONS.values())

    assert expected <= set(INDICATOR_CANONS)


def test_layer_canon_filters_to_current_layer_function_ids():
    layer_raw_data = {
        "get_10y_real_rate": {"metric_name": "10Y Real Rate", "value": {"level": 1.9}},
        "get_fed_funds_rate": {"metric_name": "Fed Funds Rate", "value": {"level": 5.25}},
        "get_macd_qqq": {"metric_name": "MACD", "value": {"signal": "bullish"}},
    }

    canons = get_layer_indicator_canons("L1", layer_raw_data)
    function_ids = {item.function_id for item in canons}

    assert function_ids == {"get_10y_real_rate", "get_fed_funds_rate"}


def test_layer_canon_prompt_is_static_and_layer_local():
    layer_raw_data = {
        "get_10y_real_rate": {"metric_name": "10Y Real Rate", "value": {"level": 1.9}},
        "get_fed_funds_rate": {"metric_name": "Fed Funds Rate", "value": {"level": 5.25}},
        "get_macd_qqq": {"metric_name": "MACD", "value": {"signal": "bullish"}},
    }

    prompt = build_layer_canon_prompt("L1", layer_raw_data)

    assert "ObjectCanon" in prompt
    assert "IndicatorCanon" in prompt
    assert "get_10y_real_rate" in prompt
    assert "get_fed_funds_rate" in prompt
    assert "get_macd_qqq" not in prompt
    assert "只提供静态规则" in prompt


def test_indicator_analysis_accepts_soft_canon_fields():
    analysis = IndicatorAnalysis(
        function_id="get_rsi_qqq",
        metric="RSI",
        narrative="RSI 偏高提示短线拥挤。",
        reasoning_process="RSI 属于技术节奏指标，只能说明短线超买/超卖。",
        permission_type="technical",
        canonical_question="当前交易节奏是否过热或过冷？",
        misread_guards=["不能用 RSI 证明估值便宜。"],
        cross_validation_targets=["get_qqq_technical_indicators", "get_atr_qqq"],
        falsifiers=["价格继续创新高且广度同步改善。"],
        core_vs_tactical_boundary="主要用于短线执行，不负责长期估值判断。",
    )

    assert analysis.permission_type == PermissionType.TECHNICAL
    assert "估值便宜" in analysis.misread_guards[0]


def test_orchestrator_backfills_missing_soft_canon_fields(tmp_path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )

    normalized = orchestrator._normalize_indicator_analysis(
        {
            "function_id": "get_10y_real_rate",
            "metric": "10Y Real Rate",
            "narrative": "真实利率偏高。",
            "reasoning_process": "真实利率偏高会压制成长股估值。",
        }
    )

    assert normalized["permission_type"] == "fact"
    assert "真实贴现率" in normalized["canonical_question"]
    assert normalized["misread_guards"]
    assert normalized["cross_validation_targets"]
    assert normalized["falsifiers"]
    assert normalized["core_vs_tactical_boundary"]


def test_orchestrator_layer_prompt_injects_only_current_layer_canon(tmp_path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    prompt = orchestrator._compose_layer_prompt(
        "l1_analyst",
        "body",
        {
            "layer": "L1",
            "layer_raw_data": {
                "get_10y_real_rate": {"metric_name": "10Y Real Rate"},
                "get_macd_qqq": {"metric_name": "MACD"},
            },
        },
    )

    assert "Deep Research Canon" in prompt
    assert "get_10y_real_rate" in prompt
    assert "真实贴现率" in prompt
    assert "get_macd_qqq" not in prompt


def test_orchestrator_full_layer_prompt_runtime_input_excludes_cross_layer_indicator(tmp_path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    prompt = orchestrator._compose_prompt(
        "l1_analyst",
        LayerCard,
        {
            "layer": "L1",
            "layer_raw_data": {
                "get_10y_real_rate": {"metric_name": "10Y Real Rate"},
                "get_macd_qqq": {"metric_name": "MACD"},
            },
        },
    )

    assert "get_10y_real_rate" in prompt
    assert "get_macd_qqq" not in prompt


def test_schema_guard_warns_but_does_not_fail_missing_soft_canon_fields(tmp_path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    packet = AnalysisPacket(
        meta={},
        raw_data={
            "L1": {
                "get_10y_real_rate": {
                    "metric_name": "10Y Real Rate",
                    "value": {"level": 1.9},
                    "error": None,
                }
            },
            "L2": {},
            "L3": {},
            "L4": {},
            "L5": {},
        },
    )
    l1_analysis = IndicatorAnalysis(
        function_id="get_10y_real_rate",
        metric="10Y Real Rate",
        narrative="真实利率偏高。",
        reasoning_process="真实利率偏高会提高成长股折现率。",
        evidence_refs=["L1.get_10y_real_rate"],
    )
    cards = [
        LayerCard(
            layer="L1",
            core_facts=[CoreFact(metric="real_rate", value=1.9)],
            local_conclusion="L1 偏紧。",
            confidence=Confidence.MEDIUM,
            indicator_analyses=[l1_analysis],
            layer_synthesis="L1 偏紧。",
            internal_conflict_analysis="无明显层内冲突。",
        ),
        *[
            LayerCard(
                layer=layer,
                core_facts=[CoreFact(metric="placeholder", value="n/a")],
                local_conclusion=f"{layer} 输入为空。",
                confidence=Confidence.LOW,
                indicator_analyses=[],
                layer_synthesis=f"{layer} 输入为空。",
                internal_conflict_analysis="无有效指标。",
            )
            for layer in ["L2", "L3", "L4", "L5"]
        ],
    ]
    conflict = Conflict(
        conflict_type="L1_real_rate_vs_L4_valuation",
        severity=ConflictSeverity.HIGH,
        description="高真实利率需要估值层确认。",
        implication="估值承压风险需要保留。",
        involved_layers=["L1", "L4"],
    )
    bridge = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        conflicts=[conflict],
        implication_for_ndx="需要保留估值压力。",
    )
    thesis = ThesisDraft(
        environment_assessment="L1 偏紧。",
        valuation_assessment="需要 L4 确认。",
        timing_assessment="未知。",
        main_thesis="中性偏谨慎。",
        key_support_chains=[KeySupportChain(chain_description="真实利率约束", evidence_refs=["L1.get_10y_real_rate"], weight=0.5)],
        retained_conflicts=[conflict],
        dependencies=["盈利需要确认。"],
        overall_confidence=Confidence.MEDIUM,
    )
    critique = Critique(overall_assessment="可用。", revision_direction="保留冲突。")
    risk = RiskBoundaryReport(must_preserve_risks=["真实利率约束估值。"])

    report = orchestrator._run_schema_guard(packet, cards, [bridge], thesis, critique, risk)

    assert report.passed is True
    assert not report.missing_fields
    assert any("soft canon fields" in item for item in report.suggested_fixes)


def test_schema_guard_warns_but_does_not_fail_weak_l3_structural_coverage(tmp_path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    packet = AnalysisPacket(
        meta={},
        raw_data={
            "L1": {},
            "L2": {},
            "L3": {
                "get_qqq_qqew_ratio": {
                    "metric_name": "QQQ/QEW Ratio",
                    "value": {"level": 1.15},
                    "error": None,
                }
            },
            "L4": {},
            "L5": {},
        },
    )
    cards = [
        LayerCard(
            layer=layer,
            core_facts=[CoreFact(metric="placeholder", value="n/a")],
            local_conclusion=f"{layer} 输入为空。",
            confidence=Confidence.LOW,
            indicator_analyses=[],
            layer_synthesis=f"{layer} 输入为空。",
            internal_conflict_analysis="无有效指标。",
        )
        for layer in ["L1", "L2", "L4", "L5"]
    ]
    cards.insert(
        2,
        LayerCard(
            layer="L3",
            core_facts=[CoreFact(metric="qqq_qew", value=1.15)],
            local_conclusion="L3 只看到集中度代理。",
            confidence=Confidence.LOW,
            indicator_analyses=[
                IndicatorAnalysis(
                    function_id="get_qqq_qqew_ratio",
                    metric="QQQ/QEW Ratio",
                    narrative="集中度偏高。",
                    reasoning_process="市值加权相对等权更强，说明头部贡献较大。",
                    evidence_refs=["L3.get_qqq_qqew_ratio"],
                )
            ],
            layer_synthesis="L3 只能判断集中度代理，无法确认完整广度。",
            internal_conflict_analysis="缺少 A/D 与均线广度确认。",
        ),
    )
    conflict = Conflict(
        conflict_type="L3_concentration_vs_L5_trend",
        severity=ConflictSeverity.HIGH,
        description="集中度风险需要趋势层确认。",
        implication="趋势质量置信度下降。",
        involved_layers=["L3", "L5"],
    )
    bridge = BridgeMemo(
        bridge_type="breadth_trend",
        layers_connected=["L3", "L5"],
        conflicts=[conflict],
        implication_for_ndx="需要保留集中度张力。",
    )
    thesis = ThesisDraft(
        environment_assessment="未知。",
        valuation_assessment="未知。",
        timing_assessment="未知。",
        main_thesis="中性。",
        key_support_chains=[KeySupportChain(chain_description="集中度张力", evidence_refs=["L3.get_qqq_qqew_ratio"], weight=0.4)],
        retained_conflicts=[conflict],
        dependencies=["需要更多广度数据。"],
        overall_confidence=Confidence.LOW,
    )
    critique = Critique(overall_assessment="可用。", revision_direction="保留 L3 数据边界。")
    risk = RiskBoundaryReport(must_preserve_risks=["L3 广度覆盖不足。"])

    report = orchestrator._run_schema_guard(packet, cards, [bridge], thesis, critique, risk)

    assert report.passed is True
    assert any("L3 structural priority" in item for item in report.suggested_fixes)
