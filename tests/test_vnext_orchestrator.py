import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.orchestrator import VNextOrchestrator
from agent_analysis.packet_builder import AnalysisPacketBuilder


class FakeLLMEngine:
    def __init__(self, responses):
        self.responses = responses
        self.token_usage = {"total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    def call_with_fallback(self, prompt, stage_name=""):
        return self.responses[stage_name]

    def extract_json(self, text, stage):
        return json.loads(text)

    def get_token_report(self):
        return self.token_usage


class SequencedFakeLLMEngine(FakeLLMEngine):
    def __init__(self, responses):
        super().__init__(responses)
        self.calls = {}

    def call_with_fallback(self, prompt, stage_name=""):
        self.calls[stage_name] = self.calls.get(stage_name, 0) + 1
        response = self.responses[stage_name]
        if isinstance(response, list):
            index = min(self.calls[stage_name] - 1, len(response) - 1)
            return response[index]
        return response


class MiniStageModel(BaseModel):
    value: str


class ParseRetryFakeLLMEngine:
    def __init__(self):
        self.calls = 0
        self.prompts = []

    def call_with_fallback(self, prompt, stage_name=""):
        self.calls += 1
        self.prompts.append(prompt)
        return "not-json" if self.calls == 1 else '{"value": "ok"}'

    def extract_json(self, text, stage):
        if text == "not-json":
            return None
        return json.loads(text)

    def get_token_report(self):
        return {}


def _mock_packet():
    data_json = {
        "timestamp_utc": "2026-04-24T00:00:00Z",
        "indicators": [
            {
                "layer": 1,
                "metric_name": "Fed Funds Rate",
                "function_id": "get_fed_funds_rate",
                "raw_data": {"name": "Fed Funds Rate", "value": {"level": 5.25, "trend": "rising"}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:01Z",
            },
            {
                "layer": 4,
                "metric_name": "NDX Valuation",
                "function_id": "get_ndx_pe_and_earnings_yield",
                "raw_data": {"name": "NDX Valuation", "value": {"PE_TTM": 32.5, "PE_TTM_percentile_5y": 78.0}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:06Z",
            },
            {
                "layer": 5,
                "metric_name": "QQQ Technical",
                "function_id": "get_qqq_technical_indicators",
                "raw_data": {"name": "QQQ Technical", "value": {"sma_position": "above_200", "macd_status": "bullish"}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:08Z",
            },
        ],
    }
    return AnalysisPacketBuilder().build(
        data_json,
        manual_overrides={
            "active": False,
            "date": "2026-04-24",
            "metrics": {
                "get_fed_funds_rate": {"value": {"level": 5.25}},
                "get_ndx_pe_and_earnings_yield": {"value": {"PE_TTM": 32.5}},
            },
        },
    )


def _indicator_analysis(function_id: str, metric: str, reading: str, narrative: str):
    return {
        "function_id": function_id,
        "metric": metric,
        "current_reading": reading,
        "normalized_state": "watch",
        "narrative": narrative,
        "reasoning_process": f"先确认 {metric} 的当前读数，再把读数放入本层因果框架中判断其对 NDX 的约束。",
        "first_principles_chain": ["当前读数", "本层机制", "局部结论"],
        "evidence_refs": [function_id],
        "cross_layer_implications": ["需要 Bridge 检查与其他层的共振或冲突"],
        "risk_flags": [],
        "confidence": "medium",
    }


def _quality_self_check(*function_ids: str):
    return {
        "coverage_complete": True,
        "covered_function_ids": list(function_ids),
        "missing_or_weak_indicators": [],
        "weak_reasoning_points": [],
        "unresolved_internal_tensions": [],
        "confidence_limitations": [],
    }


def test_backtest_skipped_indicator_is_not_analysis_required(tmp_path: Path):
    data_json = {
        "timestamp_utc": "2026-05-17T00:00:00Z",
        "backtest_date": "2025-04-09",
        "indicators": [
            {
                "layer": 4,
                "metric_name": "NDX Forward Earnings Quality",
                "function_id": "get_ndx_forward_earnings_quality",
                "raw_data": {
                    "name": "NDX Forward Earnings Quality",
                    "value": None,
                    "backtest_skipped": True,
                    "skip_reason": "latest-only source",
                    "data_quality": {"availability": "backtest_skipped"},
                },
                "error": None,
                "collection_timestamp_utc": "2026-05-17T00:00:00Z",
            }
        ],
    }
    packet = AnalysisPacketBuilder().build(data_json)
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))

    assert "get_ndx_forward_earnings_quality" not in orchestrator._analysis_required_function_ids(packet, "L4")
    manifest = orchestrator._layer_indicator_manifest(packet.raw_data["L4"])
    skipped = [item for item in manifest if item["function_id"] == "get_ndx_forward_earnings_quality"][0]
    assert skipped["analysis_required"] is False


def test_historical_percentile_string_is_sanitized(tmp_path: Path):
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))

    normalized = orchestrator._normalize_payload(
        "l4_analyst",
        {
            "layer": "L4",
            "core_facts": [
                {"metric": "pe", "value": 32.5, "historical_percentile": "Trendonify: 100% (10y), Danjuan 87%"},
                {"metric": "pb", "value": 8.1, "historical_percentile": "87.5%"},
            ],
        },
    )

    assert normalized["core_facts"][0]["historical_percentile"] is None
    assert "Trendonify" in normalized["core_facts"][0]["raw_data"]["historical_percentile_note"]
    assert normalized["core_facts"][1]["historical_percentile"] == 87.5


def test_orchestrator_runs_full_chain_with_fake_llm(tmp_path: Path):
    responses = {
        "l1": json.dumps(
            {
                "layer": "L1",
                "core_facts": [{"metric": "fed_rate", "value": 5.25}],
                "local_conclusion": "流动性偏紧。",
                "confidence": "medium",
                "risk_flags": ["tight_liquidity"],
                "cross_layer_hooks": [{"target_layer": "L4", "question": "估值能否承受高利率？", "priority": "high"}],
                "indicator_analyses": [
                    _indicator_analysis(
                        "get_fed_funds_rate",
                        "Fed Funds Rate",
                        "联邦基金利率 5.25，处于限制性区间",
                        "联邦基金利率维持高位，说明无风险收益率仍在压制高久期成长股估值。",
                    )
                ],
                "layer_synthesis": "L1 显示流动性约束仍偏紧，核心压力来自高政策利率。",
                "internal_conflict_analysis": "本层未出现宽松信号与紧缩信号的明显对冲。",
                "quality_self_check": _quality_self_check("get_fed_funds_rate"),
            },
            ensure_ascii=False,
        ),
        "l2": json.dumps(
            {
                "layer": "L2",
                "core_facts": [{"metric": "vix", "value": 18.0}],
                "local_conclusion": "风险偏好中性。",
                "confidence": "medium",
                "risk_flags": [],
                "cross_layer_hooks": [{"target_layer": "L4", "question": "情绪是否推高估值？", "priority": "medium"}],
                "indicator_analyses": [],
                "layer_synthesis": "L2 本次没有有效风险偏好指标输入，因此只保留最小层级判断。",
                "internal_conflict_analysis": "L2 缺少有效指标，无法判定波动率、信用与情绪之间是否存在真实背离。",
                "quality_self_check": _quality_self_check(),
            },
            ensure_ascii=False,
        ),
        "l3": json.dumps(
            {
                "layer": "L3",
                "core_facts": [{"metric": "breadth", "value": "weak"}],
                "local_conclusion": "内部健康度走弱。",
                "confidence": "medium",
                "risk_flags": ["weak_breadth"],
                "cross_layer_hooks": [{"target_layer": "L5", "question": "趋势是否缺乏广度？", "priority": "high"}],
                "indicator_analyses": [],
                "layer_synthesis": "L3 本次没有有效内部结构指标输入，因此内部健康度判断只能保持低信息量。",
                "internal_conflict_analysis": "L3 缺少广度和集中度指标，无法比较领导力质量与广度扩散之间的张力。",
                "quality_self_check": _quality_self_check(),
            },
            ensure_ascii=False,
        ),
        "l4": json.dumps(
            {
                "layer": "L4",
                "core_facts": [{"metric": "pe", "value": 32.5, "historical_percentile": 78.0}],
                "local_conclusion": "估值偏高。",
                "confidence": "medium",
                "risk_flags": ["expensive"],
                "cross_layer_hooks": [{"target_layer": "L1", "question": "高利率会否压缩估值？", "priority": "high"}],
                "indicator_analyses": [
                    _indicator_analysis(
                        "get_ndx_pe_and_earnings_yield",
                        "NDX Valuation",
                        "PE 32.5，估值偏高",
                        "NDX 估值处于偏高水平，若折现率维持高位，估值倍数更容易受到压缩。",
                    )
                ],
                "layer_synthesis": "L4 显示估值偏贵，能否维持取决于盈利韧性与利率约束。",
                "internal_conflict_analysis": "估值偏高与盈利韧性之间存在潜在张力。",
                "quality_self_check": _quality_self_check("get_ndx_pe_and_earnings_yield"),
            },
            ensure_ascii=False,
        ),
        "l5": json.dumps(
            {
                "layer": "L5",
                "core_facts": [{"metric": "trend", "value": "uptrend"}],
                "local_conclusion": "趋势仍向上。",
                "confidence": "medium",
                "risk_flags": ["trend_fragile"],
                "cross_layer_hooks": [{"target_layer": "L3", "question": "趋势是否空心化？", "priority": "high"}],
                "indicator_analyses": [
                    _indicator_analysis(
                        "get_qqq_technical_indicators",
                        "QQQ Technical",
                        "价格位于 200 日均线上方，MACD 偏多",
                        "价格趋势尚未破坏，但趋势质量需要由广度层验证，避免只看到价格而忽略结构脆弱性。",
                    )
                ],
                "layer_synthesis": "L5 显示趋势仍向上，但需要 L3 验证趋势是否有足够广度支撑。",
                "internal_conflict_analysis": "趋势信号偏多，但脆弱性来自潜在广度不足。",
                "quality_self_check": _quality_self_check("get_qqq_technical_indicators"),
            },
            ensure_ascii=False,
        ),
        "bridge": json.dumps(
            {
                "bridge_type": "macro_valuation",
                "layers_connected": ["L1", "L4", "L5"],
                "cross_layer_claims": [
                    {
                        "claim": "盈利韧性暂时支撑价格",
                        "supporting_facts": ["L4.pe", "L5.trend"],
                        "confidence": "medium",
                        "mechanism": "盈利预期尚未崩塌，价格得以维持。",
                    }
                ],
                "conflicts": [
                    {
                        "conflict_type": "L1_restrictive_vs_L4_expensive",
                        "severity": "high",
                        "description": "高利率与高估值并存。",
                        "implication": "估值压缩风险较高。",
                        "involved_layers": ["L1", "L4"],
                    }
                ],
                "implication_for_ndx": "环境与估值不匹配，需要谨慎。",
                "key_uncertainties": ["盈利能否继续超预期"],
            },
            ensure_ascii=False,
        ),
        "thesis": json.dumps(
            {
                "environment_assessment": "环境偏紧。",
                "valuation_assessment": "估值偏高。",
                "timing_assessment": "趋势仍在但质量存疑。",
                "main_thesis": "中性偏谨慎。",
                "key_support_chains": [
                    {"chain_description": "趋势尚未破坏", "evidence_refs": ["L5.trend"], "weight": 0.3}
                ],
                "retained_conflicts": [
                    {
                        "conflict_type": "L1_restrictive_vs_L4_expensive",
                        "severity": "high",
                        "description": "高利率与高估值并存。",
                        "implication": "估值压缩风险较高。",
                        "involved_layers": ["L1", "L4"],
                    }
                ],
                "dependencies": ["盈利韧性"],
                "overall_confidence": "medium",
            },
            ensure_ascii=False,
        ),
        "critic": json.dumps(
            {
                "overall_assessment": "主论点基本成立，但需要更明确风险边界。",
                "issues": [],
                "cross_layer_issues": ["需强调环境与估值冲突。"],
                "revision_direction": "保留高严重度冲突。",
            },
            ensure_ascii=False,
        ),
        "risk": json.dumps(
            {
                "failure_conditions": [{"condition": "盈利失速", "impact": "高"}],
                "boundary_status": {"valuation_compression": "warning"},
                "must_preserve_risks": ["估值压缩风险", "趋势脆弱性"],
                "conflict_matrix_check": {"C": True},
            },
            ensure_ascii=False,
        ),
        "reviser": json.dumps(
            {
                "revision_summary": "强化风险表述并保留核心冲突。",
                "accepted_critiques": ["保留高严重度冲突。"],
                "rejected_critiques": [],
                "revised_thesis": {
                    "environment_assessment": "环境偏紧。",
                    "valuation_assessment": "估值偏高。",
                    "timing_assessment": "趋势仍在但质量存疑。",
                    "main_thesis": "中性偏谨慎。",
                    "key_support_chains": [
                        {"chain_description": "趋势尚未破坏", "evidence_refs": ["L5.trend"], "weight": 0.3}
                    ],
                    "retained_conflicts": [
                        {
                            "conflict_type": "L1_restrictive_vs_L4_expensive",
                            "severity": "high",
                            "description": "高利率与高估值并存。",
                            "implication": "估值压缩风险较高。",
                            "involved_layers": ["L1", "L4"],
                        }
                    ],
                    "dependencies": ["盈利韧性"],
                    "overall_confidence": "medium",
                },
                "remaining_conflicts": [
                    {
                        "conflict_type": "L1_restrictive_vs_L4_expensive",
                        "severity": "high",
                        "description": "高利率与高估值并存。",
                        "implication": "估值压缩风险较高。",
                        "involved_layers": ["L1", "L4"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        "final_adjudicator": json.dumps(
            {
                "approval_status": "approved_with_reservations",
                "final_stance": "中性偏谨慎",
                "confidence": "medium",
                "key_support_chains": [
                    {"chain_description": "趋势尚未破坏", "evidence_refs": ["L5.trend"], "weight": 0.3}
                ],
                "must_preserve_risks": ["估值压缩风险", "趋势脆弱性"],
                "blocking_issues": [],
                "adjudicator_notes": "可以放行，但必须保留风险边界。",
                "evidence_refs": ["Bridge conflict", "Risk report"],
            },
            ensure_ascii=False,
        ),
    }

    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine(responses),
    )
    result = orchestrator.run(_mock_packet())

    assert result["final_adjudication"].final_stance == "中性偏谨慎"
    assert result["schema_guard_report"].passed is True
    assert "L1.get_fed_funds_rate" in result["synthesis_packet"].evidence_index
    assert (tmp_path / "final_adjudication.json").exists()
    assert (tmp_path / "synthesis_packet.json").exists()
    assert (tmp_path / "layer_cards" / "L1.json").exists()
    l1_context = json.loads((tmp_path / "layer_context_briefs" / "L1.json").read_text(encoding="utf-8"))
    assert list(l1_context["layer_highlights"].keys()) == ["L1"]
    assert l1_context["apparent_cross_layer_signals"] == []
    assert "L1 本层" in l1_context["data_summary"]
    assert "共" not in l1_context["data_summary"]


def test_layer_v2_contract_gap_retries_before_bridge_consumes_card(tmp_path: Path):
    base_responses = {
        "l2": json.dumps(
            {
                "layer": "L2",
                "core_facts": [{"metric": "vix", "value": 18.0}],
                "local_conclusion": "风险偏好中性。",
                "confidence": "medium",
                "risk_flags": [],
                "cross_layer_hooks": [{"target_layer": "L4", "question": "情绪是否推高估值？", "priority": "medium"}],
                "indicator_analyses": [],
                "layer_synthesis": "L2 本次没有有效风险偏好指标输入，因此只保留最小层级判断。",
                "internal_conflict_analysis": "L2 缺少有效指标，无法判定波动率、信用与情绪之间是否存在真实背离。",
                "quality_self_check": _quality_self_check(),
            },
            ensure_ascii=False,
        ),
        "l3": json.dumps(
            {
                "layer": "L3",
                "core_facts": [{"metric": "breadth", "value": "weak"}],
                "local_conclusion": "内部健康度走弱。",
                "confidence": "medium",
                "risk_flags": ["weak_breadth"],
                "cross_layer_hooks": [{"target_layer": "L5", "question": "趋势是否缺乏广度？", "priority": "high"}],
                "indicator_analyses": [],
                "layer_synthesis": "L3 本次没有有效内部结构指标输入，因此内部健康度判断只能保持低信息量。",
                "internal_conflict_analysis": "L3 缺少广度和集中度指标，无法比较领导力质量与广度扩散之间的张力。",
                "quality_self_check": _quality_self_check(),
            },
            ensure_ascii=False,
        ),
        "l4": json.dumps(
            {
                "layer": "L4",
                "core_facts": [{"metric": "pe", "value": 32.5, "historical_percentile": 78.0}],
                "local_conclusion": "估值偏高。",
                "confidence": "medium",
                "risk_flags": ["expensive"],
                "cross_layer_hooks": [{"target_layer": "L1", "question": "高利率会否压缩估值？", "priority": "high"}],
                "indicator_analyses": [
                    _indicator_analysis(
                        "get_ndx_pe_and_earnings_yield",
                        "NDX Valuation",
                        "PE 32.5，估值偏高",
                        "NDX 估值处于偏高水平，若折现率维持高位，估值倍数更容易受到压缩。",
                    )
                ],
                "layer_synthesis": "L4 显示估值偏贵，能否维持取决于盈利韧性与利率约束。",
                "internal_conflict_analysis": "估值偏高与盈利韧性之间存在潜在张力。",
                "quality_self_check": _quality_self_check("get_ndx_pe_and_earnings_yield"),
            },
            ensure_ascii=False,
        ),
        "l5": json.dumps(
            {
                "layer": "L5",
                "core_facts": [{"metric": "trend", "value": "uptrend"}],
                "local_conclusion": "趋势仍向上。",
                "confidence": "medium",
                "risk_flags": ["trend_fragile"],
                "cross_layer_hooks": [{"target_layer": "L3", "question": "趋势是否空心化？", "priority": "high"}],
                "indicator_analyses": [
                    _indicator_analysis(
                        "get_qqq_technical_indicators",
                        "QQQ Technical",
                        "价格位于 200 日均线上方，MACD 偏多",
                        "价格趋势尚未破坏，但趋势质量需要由广度层验证，避免只看到价格而忽略结构脆弱性。",
                    )
                ],
                "layer_synthesis": "L5 显示趋势仍向上，但需要 L3 验证趋势是否有足够广度支撑。",
                "internal_conflict_analysis": "趋势信号偏多，但脆弱性来自潜在广度不足。",
                "quality_self_check": _quality_self_check("get_qqq_technical_indicators"),
            },
            ensure_ascii=False,
        ),
        "bridge": json.dumps(
            {
                "bridge_type": "macro_valuation",
                "layers_connected": ["L1", "L4"],
                "cross_layer_claims": [],
                "conflicts": [
                    {
                        "conflict_type": "L1_restrictive_vs_L4_expensive",
                        "severity": "high",
                        "description": "高利率与高估值并存。",
                        "implication": "估值压缩风险较高。",
                        "involved_layers": ["L1", "L4"],
                    }
                ],
                "implication_for_ndx": "环境与估值不匹配，需要谨慎。",
                "key_uncertainties": ["盈利能否继续超预期"],
            },
            ensure_ascii=False,
        ),
        "thesis": json.dumps(
            {
                "environment_assessment": "环境偏紧。",
                "valuation_assessment": "估值偏高。",
                "timing_assessment": "趋势仍在但质量存疑。",
                "main_thesis": "中性偏谨慎。",
                "key_support_chains": [
                    {"chain_description": "宏观约束压制估值", "evidence_refs": ["L1.get_fed_funds_rate"], "weight": 0.5}
                ],
                "retained_conflicts": [
                    {
                        "conflict_type": "L1_restrictive_vs_L4_expensive",
                        "severity": "high",
                        "description": "高利率与高估值并存。",
                        "implication": "估值压缩风险较高。",
                        "involved_layers": ["L1", "L4"],
                    }
                ],
                "dependencies": ["盈利韧性"],
                "overall_confidence": "medium",
            },
            ensure_ascii=False,
        ),
        "critic": json.dumps(
            {
                "overall_assessment": "主论点基本成立，但需要更明确风险边界。",
                "issues": [],
                "cross_layer_issues": ["需强调环境与估值冲突。"],
                "revision_direction": "保留高严重度冲突。",
            },
            ensure_ascii=False,
        ),
        "risk": json.dumps(
            {
                "failure_conditions": [{"condition": "盈利失速", "impact": "高"}],
                "boundary_status": {"valuation_compression": "warning"},
                "must_preserve_risks": ["估值压缩风险"],
                "conflict_matrix_check": {"C": True},
            },
            ensure_ascii=False,
        ),
        "reviser": json.dumps(
            {
                "revision_summary": "强化风险表述并保留核心冲突。",
                "accepted_critiques": ["保留高严重度冲突。"],
                "rejected_critiques": [],
                "revised_thesis": {
                    "environment_assessment": "环境偏紧。",
                    "valuation_assessment": "估值偏高。",
                    "timing_assessment": "趋势仍在但质量存疑。",
                    "main_thesis": "中性偏谨慎。",
                    "key_support_chains": [
                        {"chain_description": "宏观约束压制估值", "evidence_refs": ["L1.get_fed_funds_rate"], "weight": 0.5}
                    ],
                    "retained_conflicts": [
                        {
                            "conflict_type": "L1_restrictive_vs_L4_expensive",
                            "severity": "high",
                            "description": "高利率与高估值并存。",
                            "implication": "估值压缩风险较高。",
                            "involved_layers": ["L1", "L4"],
                        }
                    ],
                    "dependencies": ["盈利韧性"],
                    "overall_confidence": "medium",
                },
                "remaining_conflicts": [
                    {
                        "conflict_type": "L1_restrictive_vs_L4_expensive",
                        "severity": "high",
                        "description": "高利率与高估值并存。",
                        "implication": "估值压缩风险较高。",
                        "involved_layers": ["L1", "L4"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        "final_adjudicator": json.dumps(
            {
                "approval_status": "approved_with_reservations",
                "final_stance": "中性偏谨慎",
                "confidence": "medium",
                "key_support_chains": [
                    {"chain_description": "宏观约束压制估值", "evidence_refs": ["L1.get_fed_funds_rate"], "weight": 0.5}
                ],
                "must_preserve_risks": ["估值压缩风险"],
                "blocking_issues": [],
                "adjudicator_notes": "可以放行，但必须保留风险边界。",
                "evidence_refs": ["L1.get_fed_funds_rate"],
            },
            ensure_ascii=False,
        ),
    }
    base_responses["l1"] = [
        json.dumps(
            {
                "layer": "L1",
                "core_facts": [{"metric": "fed_rate", "value": 5.25}],
                "local_conclusion": "流动性偏紧。",
                "confidence": "medium",
                "risk_flags": ["tight_liquidity"],
                "cross_layer_hooks": [{"target_layer": "L4", "question": "估值能否承受高利率？", "priority": "high"}],
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "layer": "L1",
                "core_facts": [{"metric": "fed_rate", "value": 5.25}],
                "local_conclusion": "流动性偏紧。",
                "confidence": "medium",
                "risk_flags": ["tight_liquidity"],
                "cross_layer_hooks": [{"target_layer": "L4", "question": "估值能否承受高利率？", "priority": "high"}],
                "indicator_analyses": [
                    _indicator_analysis(
                        "get_fed_funds_rate",
                        "Fed Funds Rate",
                        "联邦基金利率 5.25，处于限制性区间",
                        "联邦基金利率维持高位，说明无风险收益率仍在压制高久期成长股估值。",
                    )
                ],
                "layer_synthesis": "L1 显示流动性约束仍偏紧，核心压力来自高政策利率。",
                "internal_conflict_analysis": "本层未出现宽松信号与紧缩信号的明显对冲。",
                "quality_self_check": _quality_self_check("get_fed_funds_rate"),
            },
            ensure_ascii=False,
        ),
    ]

    engine = SequencedFakeLLMEngine(base_responses)
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
    )

    result = orchestrator.run(_mock_packet())

    assert engine.calls["l1"] == 2
    assert result["schema_guard_report"].passed is True
    assert "L1.get_fed_funds_rate" in result["synthesis_packet"].evidence_index
    saved_l1 = json.loads((tmp_path / "layer_cards" / "L1.json").read_text(encoding="utf-8"))
    assert saved_l1["indicator_analyses"][0]["function_id"] == "get_fed_funds_rate"


def test_layer_manual_overrides_are_layer_local(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = _mock_packet()

    l1_overrides = orchestrator._build_layer_manual_overrides(packet, "L1")
    l4_overrides = orchestrator._build_layer_manual_overrides(packet, "L4")

    assert list(l1_overrides["metrics"].keys()) == ["get_fed_funds_rate"]
    assert list(l4_overrides["metrics"].keys()) == ["get_ndx_pe_and_earnings_yield"]


def test_layer_indicator_manifest_carries_data_quality(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    manifest = orchestrator._layer_indicator_manifest(
        {
            "get_equity_risk_premium": {
                "function_id": "get_equity_risk_premium",
                "name": "NDX Simple Yield Gap",
                "value": {"level": -0.75},
                "source_name": "Calculated simple yield gap",
                "data_quality": {
                    "source_tier": "component_model",
                    "formula": "NDX FCF yield - 10Y Treasury yield",
                    "coverage": {"market_cap_coverage_pct": 92.5},
                },
            }
        }
    )

    assert manifest[0]["source_tier"] == "component_model"
    assert manifest[0]["data_quality"]["formula"] == "NDX FCF yield - 10Y Treasury yield"


def test_layer_payload_normalization_backfills_indicator_evidence_refs(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    normalized = orchestrator._normalize_payload(
        "l3_analyst",
        {
            "layer": "L3",
            "confidence": "medium",
            "indicator_analyses": [
                {
                    "function_id": "get_advance_decline_line",
                    "metric": "Advance Decline Line",
                    "narrative": "腾落线可用。",
                    "reasoning_process": "广度指标支持结构判断。",
                }
            ],
        },
    )

    assert normalized["indicator_analyses"][0]["evidence_refs"] == ["L3.get_advance_decline_line"]


def test_layer_payload_normalization_wraps_core_facts_string(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    fact_text = "QQQ/QQEW比率触及历史极值，Top10权重偏高，广度确认不足。"
    normalized = orchestrator._normalize_payload(
        "l3_analyst",
        {
            "layer": "L3",
            "confidence": "medium",
            "core_facts": fact_text,
        },
    )

    assert normalized["core_facts"] == [
        {
            "metric": fact_text[:80],
            "value": fact_text,
        }
    ]


def test_layer_payload_normalization_wraps_single_core_fact_dict(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    normalized = orchestrator._normalize_payload(
        "l3_analyst",
        {
            "layer": "L3",
            "confidence": "medium",
            "core_facts": {"metric": "QQQ/QQEW", "value": "extreme", "trend": "bullish"},
        },
    )

    assert normalized["core_facts"] == [
        {
            "metric": "QQQ/QQEW",
            "value": "extreme",
            "trend": "rising",
            "magnitude": None,
        }
    ]


def test_run_stage_records_parse_retry_diagnostics(tmp_path: Path):
    engine = ParseRetryFakeLLMEngine()
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
    )

    result = orchestrator._run_stage(
        stage_key="mini",
        stage_name="mini_stage",
        model_cls=MiniStageModel,
        payload={"example": "payload"},
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert result.value == "ok"
    assert engine.calls == 2
    assert "上一次返回未通过结构校验" in engine.prompts[1]
    assert diagnostics["stages"]["mini_stage"]["attempts"] == 2
    assert diagnostics["stages"]["mini_stage"]["errors"][0]["kind"] == "parse_error"


class FakeModelWithGeneratedAt(BaseModel):
    value: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class _ParseRetryWithTailEngine:
    """First call returns a long broken JSON ending with a sentinel; second call is valid."""

    SENTINEL = "BROKEN_TAIL_MARKER_FOR_TEST"

    def __init__(self):
        self.calls = 0
        self.prompts = []
        padding = "x" * 600
        self.broken_payload = (
            "{\n  \"value\": \"partial\",\n  \"more\": [\n    "
            + padding
            + "\n    \"unterminated string  // "
            + self.SENTINEL
        )

    def call_with_fallback(self, prompt, stage_name=""):
        self.calls += 1
        self.prompts.append(prompt)
        return self.broken_payload if self.calls == 1 else '{"value": "ok"}'

    def extract_json(self, text, stage):
        if text == self.broken_payload:
            return None
        return json.loads(text)

    def get_token_report(self):
        return {}


def test_run_stage_parse_error_feedback_includes_response_excerpt(tmp_path: Path):
    engine = _ParseRetryWithTailEngine()
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
    )

    result = orchestrator._run_stage(
        stage_key="mini",
        stage_name="mini_stage",
        model_cls=MiniStageModel,
        payload={"example": "payload"},
    )

    assert result.value == "ok"
    assert engine.calls == 2
    second_prompt = engine.prompts[1]
    assert "上一次返回未通过结构校验" in second_prompt
    assert engine.SENTINEL in second_prompt, (
        "Retry prompt should surface the tail of the broken response so the model "
        "can locate the syntax error instead of regenerating blind."
    )
    assert "response length" in second_prompt.lower() or "原始响应字符数" in second_prompt


def test_run_stage_overrides_llm_generated_at_hallucination(tmp_path: Path):
    """LLM 经常在 JSON 输出中编造 generated_at 值。
    _run_stage 必须在 model_validate 之前用代码实际运行时间强制覆盖，
    确保审计可追溯性。"""
    fake_hallucinated_date = "2025-03-31T00:00:00Z"
    fake_response = json.dumps(
        {"value": "ok", "generated_at": fake_hallucinated_date},
        ensure_ascii=False,
    )

    class _Engine:
        def call_with_fallback(self, prompt, stage_name=""):
            return fake_response

        def extract_json(self, text, stage):
            return json.loads(text)

        def get_token_report(self):
            return {}

    before = datetime.now(timezone.utc)
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=_Engine(),
    )
    result = orchestrator._run_stage(
        stage_key="test",
        stage_name="test_stage",
        model_cls=FakeModelWithGeneratedAt,
        payload={},
    )
    after = datetime.now(timezone.utc)

    assert result.value == "ok"
    assert isinstance(result.generated_at, datetime)
    assert before <= result.generated_at <= after, (
        f"generated_at 应为代码运行时间，但被 LLM 幻觉值覆盖: {result.generated_at}"
    )
    assert result.generated_at.isoformat() != fake_hallucinated_date, (
        "generated_at 必须被强制覆盖，不能保留 LLM 编造的日期"
    )


def test_l4_prompt_summarizes_long_series(tmp_path: Path):
    """L4 prompt 中的长序列（如 Damodaran monthly 120 条）必须被压缩为统计摘要，
    以降低 token 成本并避免注意力分散。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    long_series = [
        {"data_date": f"2020-{m:02d}-01", "erp": 5.0 + i * 0.1}
        for i, m in enumerate(range(1, 13))
    ]
    raw_data = {
        "get_damodaran_us_implied_erp": {
            "function_id": "get_damodaran_us_implied_erp",
            "value": {
                "current_erp": 4.24,
                "monthly_series": long_series,
            },
        },
        "get_ndx_pe_and_earnings_yield": {
            "function_id": "get_ndx_pe_and_earnings_yield",
            "value": {"PE_TTM": 36.6},
        },
    }
    summarized = orchestrator._summarize_l4_raw_data_for_prompt(raw_data)

    damodaran = summarized["get_damodaran_us_implied_erp"]["value"]
    assert "monthly_series" in damodaran
    summary = damodaran["monthly_series"]
    assert summary["count"] == 12
    assert summary["period_start"] == "2020-01-01"
    assert summary["period_end"] == "2020-12-01"
    assert "numeric_summary" in summary
    assert "erp" in summary["numeric_summary"]
    erp_stats = summary["numeric_summary"]["erp"]
    assert erp_stats["min"] == 5.0
    assert erp_stats["max"] == 6.1
    assert abs(erp_stats["mean"] - 5.55) < 0.01
    # 标量字段保持不变
    assert summarized["get_ndx_pe_and_earnings_yield"]["value"]["PE_TTM"] == 36.6


def test_l4_prompt_leaves_short_lists_intact(tmp_path: Path):
    """短列表（<=10 条）不应被摘要，保持原始内容。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    short_list = [{"data_date": f"2026-0{i}-01", "erp": 4.0 + i} for i in range(1, 4)]
    raw_data = {
        "get_test": {
            "value": {"short_series": short_list},
        },
    }
    summarized = orchestrator._summarize_l4_raw_data_for_prompt(raw_data)
    assert summarized["get_test"]["value"]["short_series"] == short_list
