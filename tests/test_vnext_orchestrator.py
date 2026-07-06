import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    ApprovalStatus,
    BridgeMemo,
    ClaimLedger,
    CompetingHypothesis,
    Confidence,
    Critique,
    EvidenceRegistry,
    FinalAdjudication,
    HypothesisCompetition,
    InvestigationReport,
    KeySupportChain,
    ReaderFinal,
    RiskBoundaryReport,
    SynthesisPacket,
    ThesisDraft,
    TypedConflict,
)
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


def test_layer_stage_payload_enforces_stage0_runtime_boundaries(tmp_path: Path):
    event_ledger = {
        "events": [
            {
                "event_id": "event:fomc",
                "source_name": "Federal Reserve",
                "source_tier": "official_macro",
                "event_type": "policy_or_financial_conditions",
                "title": "FOMC statement",
                "published_at": "2026-04-24T18:00:00Z",
                "layers": ["L1", "L4"],
                "confidence": "high",
            }
        ]
    }
    data_json = {
        "timestamp_utc": "2026-04-24T00:00:00Z",
        "indicators": [
            {
                "layer": 1,
                "metric_name": "Fed Funds Rate",
                "function_id": "get_fed_funds_rate",
                "raw_data": {"name": "Fed Funds Rate", "value": {"level": 5.25}},
            },
            {
                "layer": 4,
                "metric_name": "NDX Valuation",
                "function_id": "get_ndx_pe_and_earnings_yield",
                "raw_data": {"name": "NDX Valuation", "value": {"PE_TTM": 32.5}},
            },
        ],
    }
    packet = AnalysisPacketBuilder().build(
        data_json,
        manual_overrides={
            "active": True,
            "date": "2026-04-24",
            "metrics": {
                "get_fed_funds_rate": {"value": {"level": 5.1}},
                "get_ndx_pe_and_earnings_yield": {"value": {"PE_TTM": 31.0}},
            },
        },
        event_ledger=event_ledger,
        allow_event_refs=True,
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    context_brief = orchestrator._build_context_brief(packet)

    payload = orchestrator._build_layer_stage_payload(packet, context_brief, "L1")

    assert set(payload) == {
        "context_brief",
        "layer",
        "layer_facts",
        "layer_raw_data",
        "manual_overrides",
        "runtime_boundary_policy_id",
    }
    assert payload["layer"] == "L1"
    assert list(payload["context_brief"]["layer_highlights"].keys()) == ["L1"]
    assert payload["context_brief"]["apparent_cross_layer_signals"] == []
    assert "get_fed_funds_rate" in payload["layer_raw_data"]
    assert "get_ndx_pe_and_earnings_yield" not in payload["layer_raw_data"]
    assert set(payload["manual_overrides"]["metrics"].keys()) == {"get_fed_funds_rate"}
    assert "event_refs" not in payload
    assert "candidate_cross_layer_links" not in payload
    assert "get_ndx_pe_and_earnings_yield" not in json.dumps(payload, ensure_ascii=False)
    assert payload["runtime_boundary_policy_id"] == "layer_runtime_input_policy_v1"
    assert "forbidden_runtime_inputs" not in json.dumps(payload, ensure_ascii=False)

    policy = orchestrator._build_layer_input_policy("L1")
    assert policy["schema_version"] == "layer_runtime_input_policy_v1"
    assert "candidate_cross_layer_links" in policy["forbidden_runtime_inputs"]
    assert "event_refs" in policy["forbidden_runtime_inputs"]
    assert "bridge_memos" in policy["forbidden_runtime_inputs"]
    assert "final_adjudication" in policy["forbidden_runtime_inputs"]
    assert "investigation_reports" in policy["forbidden_runtime_inputs"]
    assert "must not rewrite or be injected into L1-L5" in policy["no_backflow_rule"]
    assert "must not become L1-L5 evidence_ref" in policy["event_evidence_rule"]
    sanitized = orchestrator._sanitize_prompt_payload("l1_analyst", payload)
    assert "runtime_boundary_policy_id" not in sanitized


def test_thesis_prompt_receives_slim_object_run_gate(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    payload = {
        "synthesis_packet": {
            "packet_meta": {
                "data_date": "2026-04-24",
                "object_run_gate": {
                    "schema_version": "object_run_gate_v1",
                    "primary_object": "NDX",
                    "tradable_proxy": "QQQ",
                    "equal_weight_references": ["NDXE", "QEW"],
                    "date_boundary": "2026-04-24",
                    "methodology_boundary": "LONG_METHOD_BOUNDARY_SENTINEL",
                    "data_boundary": "LONG_DATA_BOUNDARY_SENTINEL",
                    "evidence_boundary": "LONG_EVIDENCE_BOUNDARY_SENTINEL",
                },
            }
        }
    }

    sanitized = orchestrator._sanitize_prompt_payload("thesis", payload)
    object_gate = sanitized["synthesis_packet"]["packet_meta"]["object_run_gate"]

    assert object_gate["primary_object"] == "NDX"
    assert object_gate["tradable_proxy"] == "QQQ"
    assert "prompt_note" in object_gate
    assert "methodology_boundary" not in object_gate
    assert "LONG_METHOD_BOUNDARY_SENTINEL" not in json.dumps(sanitized, ensure_ascii=False)


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


def test_unavailable_nested_none_indicator_is_not_analysis_required(tmp_path: Path):
    data_json = {
        "timestamp_utc": "2026-05-17T00:00:00Z",
        "backtest_date": "2025-04-09",
        "indicators": [
            {
                "layer": 3,
                "metric_name": "Advance Decline Line",
                "function_id": "get_advance_decline_line",
                "raw_data": {
                    "name": "Advance Decline Line",
                    "value": {"level": None, "date": None, "momentum": None},
                    "notes": "Failed to calculate advance decline line",
                },
                "error": None,
                "collection_timestamp_utc": "2026-05-17T00:00:00Z",
            }
        ],
    }
    packet = AnalysisPacketBuilder().build(data_json)
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))

    assert "get_advance_decline_line" not in orchestrator._analysis_required_function_ids(packet, "L3")
    manifest = orchestrator._layer_indicator_manifest(packet.raw_data["L3"])
    failed = [item for item in manifest if item["function_id"] == "get_advance_decline_line"][0]
    assert failed["analysis_required"] is False


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
                        "supporting_facts": ["L4.get_ndx_pe_and_earnings_yield", "L5.get_qqq_technical_indicators"],
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
                        "evidence_refs": ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
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
                    {"chain_description": "趋势尚未破坏", "evidence_refs": ["L5.get_qqq_technical_indicators"], "weight": 0.3}
                ],
                "retained_conflicts": [
                    {
                        "conflict_type": "L1_restrictive_vs_L4_expensive",
                        "severity": "high",
                        "description": "高利率与高估值并存。",
                        "implication": "估值压缩风险较高。",
                        "involved_layers": ["L1", "L4"],
                        "evidence_refs": ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
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
                        {"chain_description": "趋势尚未破坏", "evidence_refs": ["L5.get_qqq_technical_indicators"], "weight": 0.3}
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
                        "evidence_refs": ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
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
                    {"chain_description": "趋势尚未破坏", "evidence_refs": ["L5.get_qqq_technical_indicators"], "weight": 0.3}
                ],
                "must_preserve_risks": ["估值压缩风险", "趋势脆弱性"],
                "blocking_issues": [],
                "adjudicator_notes": "可以放行，但必须保留风险边界。",
                "evidence_refs": ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
            },
            ensure_ascii=False,
        ),
    }

    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine(responses),
    )
    (tmp_path / "cross_layer_questions.json").write_text(
        json.dumps(
            {
                "schema_version": "cross_layer_questions_v1",
                "questions": [
                    {
                        "question_id": "question:event_to_data:rates",
                        "direction": "event_to_data",
                        "question": "利率事件压力是否已被实际利率、VXN 或信用利差确认？",
                        "why_it_matters": "新闻事件只能提出线索，需要数据层确认。",
                        "requested_checks": ["实际利率", "VXN", "信用利差"],
                        "status": "open",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "event_layer_summary.json").write_text(
        json.dumps({"schema_version": "event_layer_summary_v1", "most_important_events": [{"event_cluster_id": "event_cluster:rates"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    result = orchestrator.run(_mock_packet())

    assert result["final_adjudication"].final_stance == "中性偏谨慎"
    assert result["schema_guard_report"].passed is True
    assert len(result["bridge_memos"]) == 2
    assert "L1.get_fed_funds_rate" in result["synthesis_packet"].evidence_index
    assert (tmp_path / "final_adjudication.json").exists()
    assert (tmp_path / "run_review_report.json").exists()
    assert (tmp_path / "bridge_memos" / "bridge_v2.json").exists()
    assert (tmp_path / "counter_thesis.json").exists()
    assert (tmp_path / "hypothesis_competition.json").exists()
    assert (tmp_path / "adjudication_history.json").exists()
    boundary_manifest = json.loads((tmp_path / "runtime_boundary_manifest.json").read_text(encoding="utf-8"))
    assert boundary_manifest["schema_version"] == "runtime_boundary_manifest_v1"
    assert "investigation_reports" in boundary_manifest["layer_input_policies"]["L1"]["forbidden_runtime_inputs"]
    assert "not injected into L1-L5 prompts" in boundary_manifest["purpose"]
    feedback_manifest = json.loads((tmp_path / "feedback_contract_manifest.json").read_text(encoding="utf-8"))
    assert feedback_manifest["schema_version"] == "feedback_contract_manifest_v1"
    assert feedback_manifest["message_contract"]["message_types"] == [
        "observation_inquiry",
        "event_challenge",
        "adjudication_gap",
        "evidence_upgrade_request",
    ]
    assert "source_authority" in feedback_manifest["investigation_report_contract"]["minimal_evidence_fields"]
    router_output = json.loads((tmp_path / "inquiry_router_output.json").read_text(encoding="utf-8"))
    assert router_output["schema_version"] == "inquiry_router_output_v1"
    assert len(router_output["agent_specs"]) <= 3
    message_types = {item["message_type"] for item in router_output["input_messages"]}
    assert {"adjudication_gap", "event_challenge", "observation_inquiry"}.issubset(message_types)
    assert all(spec["budget"]["max_tool_calls"] <= 1 for spec in router_output["agent_specs"])
    investigation_paths = sorted((tmp_path / "investigation_reports").glob("*.json"))
    assert investigation_paths
    investigation = json.loads(investigation_paths[0].read_text(encoding="utf-8"))
    assert "source_authority" in investigation
    assert investigation["is_deterministic_stub"] is True
    assert investigation["limits"]
    bridge_v2 = json.loads((tmp_path / "bridge_memos" / "bridge_v2.json").read_text(encoding="utf-8"))
    assert bridge_v2["bridge_type"] == "feedback_bridge_v2"
    assert bridge_v2["feedback_loop_summary"]["no_backflow_asserted"] is True
    assert bridge_v2["feedback_loop_summary"]["investigation_report_refs"]
    assert bridge_v2["investigation_effects"]
    counter_thesis = json.loads((tmp_path / "counter_thesis.json").read_text(encoding="utf-8"))
    assert "thesis_draft.json" in counter_thesis["forbidden_context_refs"]
    assert counter_thesis["prompt_input_audit"]["thesis_read"] is False
    assert counter_thesis["prompt_input_audit"]["thesis_exists_at_generation"] is False
    competition = json.loads((tmp_path / "hypothesis_competition.json").read_text(encoding="utf-8"))
    assert competition["schema_version"] == "hypothesis_competition_v1"
    assert len(competition["hypotheses"]) >= 2
    assert "thesis_draft.json" in competition["forbidden_context_refs"]
    assert competition["downgrade_or_split_events"]
    synthesis_packet = json.loads((tmp_path / "synthesis_packet.json").read_text(encoding="utf-8"))
    assert synthesis_packet["hypothesis_competition_summary"]["hypothesis_count"] >= 2
    assert len(synthesis_packet["competing_hypotheses"]) >= 2
    review = json.loads((tmp_path / "run_review_report.json").read_text(encoding="utf-8"))
    assert any(item["category"] == "feedback" for item in review["attribution_findings"])
    assert any(item["category"] == "competition" for item in review["attribution_findings"])
    assert any(item["category"] == "bridge" for item in review["attribution_findings"])
    assert (tmp_path / "synthesis_packet.json").exists()
    assert (tmp_path / "layer_cards" / "L1.json").exists()
    l1_context = json.loads((tmp_path / "layer_context_briefs" / "L1.json").read_text(encoding="utf-8"))
    assert list(l1_context["layer_highlights"].keys()) == ["L1"]
    assert l1_context["apparent_cross_layer_signals"] == []
    assert "L1 本层" in l1_context["data_summary"]
    assert "共" not in l1_context["data_summary"]
    manifest = json.loads((tmp_path / "stage_manifest.json").read_text(encoding="utf-8"))
    l1_checkpoint = manifest["artifacts"]["layer_cards/L1.json"]
    assert manifest["schema_version"] == "vnext_stage_manifest_v1"
    assert l1_checkpoint["checkpoint_reusable"] is True
    assert len(l1_checkpoint["sha256"]) == 64
    assert len(l1_checkpoint["input_sha256"]) == 64
    reflection = json.loads((tmp_path / "post_run_reflection_library.json").read_text(encoding="utf-8"))
    assert reflection["schema_version"] == "post_run_reflection_library_v1"
    assert "must not be injected" in reflection["boundary"]

    resumed = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
        resume_from_existing=True,
    ).run(_mock_packet())
    assert resumed["final_adjudication"].final_stance == "中性偏谨慎"
    resumed_diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert resumed_diagnostics["stages"]["l1"]["status"] == "resumed"
    assert resumed_diagnostics["stages"]["final_adjudicator"]["status"] == "resumed"


def test_checkpoint_resume_requires_matching_stage_payload(tmp_path: Path):
    first = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({"mini_stage": '{"value": "old"}'}),
    )
    old_result = first._run_and_save(
        stage_key="mini",
        stage_name="mini_stage",
        model_cls=MiniStageModel,
        payload={"example": "old"},
        filename="mini.json",
    )
    assert old_result.value == "old"

    manifest = json.loads((tmp_path / "stage_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["artifacts"]["mini.json"]["payload_sha256"]) == 64

    second_engine = FakeLLMEngine({"mini_stage": '{"value": "new"}'})
    second = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=second_engine,
        resume_from_existing=True,
    )
    new_result = second._run_and_save(
        stage_key="mini",
        stage_name="mini_stage",
        model_cls=MiniStageModel,
        payload={"example": "new"},
        filename="mini.json",
    )

    assert new_result.value == "new"
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["stages"]["mini_stage"]["status"] == "ok"


def test_orchestrator_resolves_relative_output_dir_before_saving_nested_paths(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir="relative_run",
        llm_engine=object(),
    )

    orchestrator._save_json(orchestrator.bridge_dir / "bridge_0.json", {"ok": True})

    assert (tmp_path / "relative_run" / "bridge_memos" / "bridge_0.json").exists()
    assert not (tmp_path / "relative_run" / "relative_run" / "bridge_memos" / "bridge_0.json").exists()


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
                        "evidence_refs": ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
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

    assert l1_overrides["metrics"] == {}
    assert l4_overrides["metrics"] == {}


def test_layer_manual_overrides_are_layer_local_when_active(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    data_json = {
        "timestamp_utc": "2026-04-24T00:00:00Z",
        "indicators": [
            {
                "layer": 1,
                "metric_name": "Fed Funds Rate",
                "function_id": "get_fed_funds_rate",
                "raw_data": {"name": "Fed Funds Rate", "value": {"level": 5.25}},
            },
            {
                "layer": 4,
                "metric_name": "NDX Valuation",
                "function_id": "get_ndx_pe_and_earnings_yield",
                "raw_data": {"name": "NDX Valuation", "value": {"PE_TTM": 32.5}},
            },
        ],
    }
    packet = AnalysisPacketBuilder().build(
        data_json,
        manual_overrides={
            "active": True,
            "date": "2026-04-24",
            "metrics": {
                "get_fed_funds_rate": {"value": {"level": 5.25}},
                "get_ndx_pe_and_earnings_yield": {"value": {"PE_TTM": 32.5}},
            },
        },
    )

    l1_overrides = orchestrator._build_layer_manual_overrides(packet, "L1")
    l4_overrides = orchestrator._build_layer_manual_overrides(packet, "L4")

    assert list(l1_overrides["metrics"].keys()) == ["get_fed_funds_rate"]
    assert list(l4_overrides["metrics"].keys()) == ["get_ndx_pe_and_earnings_yield"]


def test_schema_guard_rejects_bridge_dead_refs_and_bad_transmission_paths(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = _mock_packet()
    bridge = BridgeMemo.model_validate(
        {
            "bridge_type": "macro_valuation",
            "layers_connected": ["L1", "L4"],
            "cross_layer_claims": [
                {
                    "claim": "自由文本 ref 不可审计",
                    "supporting_facts": ["L1.净流动性收缩"],
                    "confidence": "medium",
                    "mechanism": "无法定位到真实指标卡。",
                }
            ],
            "typed_conflicts": [
                {
                    "conflict_id": "bad_conflict",
                    "conflict_type": "valuation_discount_rate",
                    "severity": "high",
                    "description": "引用不存在的证据。",
                    "implication": "应阻断 schema guard。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": ["L1.get_fake_metric"],
                }
            ],
            "transmission_paths": [
                {
                    "path_id": "transmission_path",
                    "source_layer": "L1",
                    "target_layer": "L4",
                    "mechanism": "折现率传导",
                    "evidence_refs": [],
                    "implication": "",
                },
                {
                    "path_id": "transmission_path",
                    "source_layer": "L1",
                    "target_layer": "L4",
                    "mechanism": "重复 ID",
                    "evidence_refs": ["L1.get_fed_funds_rate"],
                    "implication": "重复 ID 不可审计。",
                },
            ],
            "implication_for_ndx": "不可放行。",
        }
    )

    report = orchestrator._run_schema_guard(
        packet,
        [],
        [bridge],
        ThesisDraft.model_validate(
            {
                "environment_assessment": "环境偏紧。",
                "valuation_assessment": "估值偏高。",
                "timing_assessment": "趋势待确认。",
                "main_thesis": "测试。",
                "overall_confidence": "medium",
            }
        ),
        Critique.model_validate(
            {
                "overall_assessment": "测试。",
                "revision_direction": "测试。",
            }
        ),
        RiskBoundaryReport.model_validate({"must_preserve_risks": ["测试风险"]}),
    )

    joined = "\n".join(report.consistency_issues)
    assert report.passed is False
    assert "supporting_facts invalid" in joined
    assert "evidence_refs invalid" in joined
    assert "duplicate path_id" in joined
    assert "evidence_refs must not be empty" in joined
    assert "implication is required" in joined


def test_bridge_normalization_converts_claim_fact_sentences_to_evidence_refs(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    normalized = orchestrator._normalize_payload(
        "bridge",
        {
            "bridge_type": "macro_valuation",
            "layers_connected": ["L1", "L4"],
            "cross_layer_claims": [
                {
                    "claim": "盈利增长预期支撑高估值",
                    "supporting_facts": [
                        "L4 Forward PE 23.22 隐含盈利大幅增长",
                        "M7 EPS修正30d +3.05%",
                    ],
                    "confidence": "medium",
                    "mechanism": "盈利增长若兑现，可缓冲折现率压力。",
                }
            ],
            "typed_conflicts": [
                {
                    "conflict_id": "real_rate_vs_valuation",
                    "conflict_type": "L1_restrictive_vs_L4_expensive",
                    "severity": "high",
                    "description": "高实际利率与高估值并存。",
                    "mechanism": "折现率上行压制估值。",
                    "implication": "估值需要盈利兑现来支撑。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": [
                        "L1.get_fed_funds_rate",
                        "L4.get_ndx_pe_and_earnings_yield",
                    ],
                }
            ],
            "implication_for_ndx": "需要谨慎。",
        },
    )

    claim = normalized["cross_layer_claims"][0]

    assert claim["supporting_facts"] == ["L4.get_ndx_pe_and_earnings_yield"]
    assert "L4 Forward PE 23.22 隐含盈利大幅增长" in claim["supporting_fact_notes"]
    assert "cross_layer_claim_supporting_facts_normalized_to_evidence_refs" in normalized["normalization_notes"]


def test_layer_normalization_truncates_overlong_local_conclusion(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    normalized = orchestrator._normalize_payload(
        "l4_analyst",
        {
            "layer": "L4",
            "core_facts": [{"metric": "pe", "value": 32.5}],
            "local_conclusion": "估值结论" * 140,
            "confidence": "medium",
        },
    )

    assert len(normalized["local_conclusion"]) <= 500
    assert normalized["local_conclusion"].endswith("...")


def test_reviser_normalization_drops_empty_retained_conflicts(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    normalized = orchestrator._normalize_payload(
        "reviser",
        {
            "revised_thesis": {
                "retained_conflicts": [
                    {},
                    {"description": "L1 高利率与 L4 高估值并存"},
                ],
            }
        },
    )

    conflicts = normalized["revised_thesis"]["retained_conflicts"]

    assert len(conflicts) == 1
    assert conflicts[0]["conflict_type"] == "normalized_conflict"
    assert conflicts[0]["severity"] == "medium"
    assert conflicts[0]["description"] == "L1 高利率与 L4 高估值并存"
    assert conflicts[0]["involved_layers"] == ["L1", "L4"]


def test_schema_guard_rejects_cnn_submetric_high_conflict_without_aggregate_semantics(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = AnalysisPacketBuilder().build(
        {
            "timestamp_utc": "2026-04-24T00:00:00Z",
            "indicators": [
                {
                    "layer": 2,
                    "metric_name": "CNN Fear & Greed",
                    "function_id": "get_cnn_fear_greed_index",
                    "raw_data": {
                        "name": "CNN Fear & Greed",
                        "value": {
                            "score": 20,
                            "rating": "extreme fear",
                            "sub_metrics": {
                                "Market Momentum (S&P500)": {"score": 98.2, "rating": "extreme greed"}
                            },
                        },
                    },
                },
                {
                    "layer": 5,
                    "metric_name": "QQQ Technical",
                    "function_id": "get_qqq_technical_indicators",
                    "raw_data": {"name": "QQQ Technical", "value": {"sma_position": "below_200"}},
                },
            ],
        },
        manual_overrides={"active": False, "metrics": {}},
    )
    bridge = BridgeMemo.model_validate(
        {
            "bridge_type": "breadth_trend",
            "layers_connected": ["L2", "L5"],
            "cross_layer_claims": [],
            "typed_conflicts": [
                {
                    "conflict_id": "fgi_market_momentum_vs_trend",
                    "conflict_type": "sentiment_submetric_vs_price_trend",
                    "severity": "high",
                    "description": "Market Momentum 子项显示 extreme greed，但 L5 趋势疲弱。",
                    "mechanism": "单个情绪子项与价格趋势相反。",
                    "implication": "不应直接作为高严重度跨层冲突。",
                    "involved_layers": ["L2", "L5"],
                    "evidence_refs": ["L2.get_cnn_fear_greed_index", "L5.get_qqq_technical_indicators"],
                }
            ],
            "implication_for_ndx": "测试。",
        }
    )

    report = orchestrator._run_schema_guard(
        packet,
        [],
        [bridge],
        ThesisDraft.model_validate(
            {
                "environment_assessment": "测试。",
                "valuation_assessment": "测试。",
                "timing_assessment": "测试。",
                "main_thesis": "测试。",
                "overall_confidence": "medium",
            }
        ),
        Critique.model_validate({"overall_assessment": "测试。", "revision_direction": "测试。"}),
        RiskBoundaryReport.model_validate({"must_preserve_risks": ["测试风险"]}),
    )

    joined = "\n".join(report.consistency_issues)
    assert "composite sub-metric over-promotion" in joined


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


def test_layer_payload_normalization_coerces_dict_evidence_refs(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    normalized = orchestrator._normalize_payload(
        "l2_analyst",
        {
            "layer": "L2",
            "confidence": "medium",
            "indicator_analyses": [
                {
                    "function_id": "get_cnn_fear_greed_index",
                    "metric": "CNN Fear & Greed",
                    "narrative": "情绪偏弱。",
                    "reasoning_process": "总分低于 25。",
                    "evidence_refs": [
                        {"layer": "L2", "function_id": "get_cnn_fear_greed_index"},
                        {"ref": "L2.get_vix"},
                    ],
                }
            ],
        },
    )

    assert normalized["indicator_analyses"][0]["evidence_refs"] == [
        "L2.get_cnn_fear_greed_index",
        "L2.get_vix",
    ]


def test_layer_payload_normalization_wraps_core_facts_string(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    fact_text = "NDX/NDXE比率触及历史极值，Top10权重偏高，广度确认不足。"
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
            "core_facts": {"metric": "NDX/NDXE", "value": "extreme", "trend": "bullish"},
        },
    )

    assert normalized["core_facts"] == [
        {
            "metric": "NDX/NDXE",
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
    first_prompt = (tmp_path / "prompt_audit" / "mini_stage" / "attempt_1.prompt.txt").read_text(encoding="utf-8")
    second_prompt = (tmp_path / "prompt_audit" / "mini_stage" / "attempt_2.prompt.txt").read_text(encoding="utf-8")
    meta = json.loads((tmp_path / "prompt_audit" / "mini_stage" / "meta.json").read_text(encoding="utf-8"))

    assert result.value == "ok"
    assert engine.calls == 2
    assert "上一次返回未通过结构校验" in engine.prompts[1]
    assert "## System Message" in first_prompt
    assert "## User Message" in first_prompt
    assert "上一次返回未通过结构校验" in second_prompt
    assert (tmp_path / "prompt_audit" / "mini_stage" / "attempt_1.payload.json").exists()
    assert (tmp_path / "prompt_audit" / "mini_stage" / "attempt_1.response.raw.txt").exists()
    assert (tmp_path / "prompt_audit" / "mini_stage" / "output.validated.json").exists()
    assert meta["prompt_file"] == "prompt_audit/mini_stage/attempt_2.prompt.txt"
    assert meta["prompt_sha256"]
    assert diagnostics["stages"]["mini_stage"]["attempts"] == 2
    assert diagnostics["stages"]["mini_stage"]["errors"][0]["kind"] == "parse_error"
    assert diagnostics["stages"]["mini_stage"]["prompt_audit"]["latest_prompt_file"] == "prompt_audit/mini_stage/attempt_2.prompt.txt"


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


def test_price_reflection_map_is_expanded_to_required_categories(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    normalized = orchestrator._normalize_payload(
        "bridge",
        {
            "bridge_type": "macro_valuation",
            "layers_connected": ["L1", "L4"],
            "cross_layer_claims": [],
            "conflicts": [
                {
                    "conflict_type": "rates_vs_valuation",
                    "severity": "high",
                    "description": "真实利率仍高但估值压缩。",
                    "implication": "动作需要分层。",
                    "involved_layers": ["L1", "L4"],
                }
            ],
            "typed_conflicts": [
                {
                    "conflict_id": "rates_vs_valuation",
                    "conflict_type": "rates_vs_valuation",
                    "severity": "high",
                    "description": "真实利率仍高但估值压缩。",
                    "mechanism": "贴现率与风险补偿拉扯。",
                    "implication": "动作需要分层。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": ["L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield"],
                    "falsifiers": ["利率快速回落"],
                }
            ],
            "principal_contradiction": {
                "contradiction_id": "rates_vs_valuation",
                "summary": "利率压力与估值修复拉扯。",
                "price_reflection": "partially_reflected",
                "evidence_refs": ["L1.get_10y_real_rate", "L4.get_ndx_pe_and_earnings_yield"],
            },
            "price_reflection_map": [
                {
                    "category": "valuation",
                    "target": "valuation_risk_premium",
                    "reflected_state": "partially_reflected",
                    "rationale": "估值压缩说明坏消息部分进入价格。",
                    "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
                    "counterevidence": ["盈利继续下修会削弱估值吸引力。"],
                    "action_implication": "支持战术试探。",
                }
            ],
            "implication_for_ndx": "风险和赔率并存。",
            "key_uncertainties": ["信用是否恶化"],
        },
    )

    categories = {item["category"] for item in normalized["price_reflection_map"]}
    assert {"credit", "rates", "valuation", "technical_panic", "liquidity"} <= categories
    assert next(item for item in normalized["price_reflection_map"] if item["category"] == "credit")["reflected_state"] == "unclear"


def test_thesis_string_lists_are_normalized_to_structured_views(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    normalized = orchestrator._normalize_payload(
        "thesis",
        {
            "environment_assessment": "环境仍有压力。",
            "valuation_assessment": "估值压缩。",
            "timing_assessment": "技术恐慌。",
            "main_thesis": "高风险高赔率候选。",
            "time_horizon_views": ["短期高波动", "中期赔率改善", "长期看盈利与利率"],
            "portfolio_actions": ["核心仓守纪律", "战术仓分批", "等待者承认确认成本"],
            "reader_conclusion": {
                "one_liner": "风险仍高但赔率改善。",
                "three_reasons": ["风险仍在", "估值压缩", "等待有成本"],
                "time_horizon_summary": ["短期别追涨", "中期分批"],
                "action_summary": ["核心仓不砍", "战术仓试探"],
                "invalidation_summary": ["信用恶化"],
            },
            "principal_contradiction": {
                "contradiction_id": "panic_priced_vs_risk",
                "summary": "风险与赔率拉扯。",
                "price_reflection": "partially_reflected",
            },
            "overall_confidence": "medium",
        },
    )

    assert normalized["time_horizon_views"][0]["horizon"] == "same_day_or_days"
    assert normalized["time_horizon_views"][0]["view"] == "短期高波动"
    assert normalized["portfolio_actions"][1]["bucket"] == "tactical_position"
    assert normalized["portfolio_actions"][1]["action"] == "战术仓分批"
    assert normalized["reader_conclusion"]["time_horizon_summary"][0]["view"] == "短期别追涨"
    assert normalized["reader_conclusion"]["action_summary"][0]["action"] == "核心仓不砍"


def test_stub_investigation_does_not_downgrade_competition(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    base = CompetingHypothesis(
        hypothesis_id="hyp_base",
        hypothesis_text="主线解释：利率压力仍是主导。",
        support_evidence_refs=["L1.get_fed_funds_rate"],
        counter_evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
        diagnostic_evidence_refs=["L1.get_fed_funds_rate"],
        cannot_explain=["趋势仍强。"],
        falsification_conditions=["利率快速下行。"],
    )
    counter = CompetingHypothesis(
        hypothesis_id="hyp_counter",
        hypothesis_text="反方解释：价格可能已部分反映压力。",
        source="counter_thesis",
        support_evidence_refs=["L5.get_qqq_technical_indicators"],
        counter_evidence_refs=["L1.get_fed_funds_rate"],
        diagnostic_evidence_refs=["L5.get_qqq_technical_indicators"],
        cannot_explain=["不能证明估值便宜。"],
        falsification_conditions=["趋势跌破关键均线。"],
    )
    stub_report = InvestigationReport(
        originating_agent_id="agent_stub",
        is_deterministic_stub=True,
        finding="本轮未执行真实调查，仅登记缺口。",
        evidence_refs=["bridge_memos/bridge_0.json"],
        claims_challenged=["strong_single_path_adjudication"],
        cannot_establish=["价格反映程度不清。"],
        effective_date="2026-07-06",
    )

    records = orchestrator._build_adjudication_change_records(
        base_hypothesis=base,
        counter_hypotheses=[counter],
        investigation_reports=[stub_report],
        fallback_warnings=[],
        effective_date="2026-07-06",
    )

    assert records == []


def test_synthesis_packet_does_not_duplicate_bridge_v1_structure_from_bridge_v2(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = _mock_packet()
    context = orchestrator._build_context_brief(packet)
    layer_cards = []
    bridge_v1 = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        conflicts=[
            {
                "conflict_type": "rates_vs_valuation",
                "severity": "high",
                "description": "高利率与高估值并存。",
                "implication": "估值压缩风险仍需保留。",
                "involved_layers": ["L1", "L4"],
                "evidence_refs": ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
            }
        ],
        principal_contradiction={
            "contradiction_id": "rates_vs_valuation",
            "summary": "高利率与高估值并存。",
            "why_principal": "它决定估值承压与趋势韧性的拉扯。",
            "dominant_side": "利率压力。",
            "secondary_side": "趋势韧性。",
            "price_reflection": "partially_reflected",
            "action_implication": "保留风险边界。",
            "evidence_refs": ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
        },
        implication_for_ndx="保留张力。",
    )
    bridge_v2 = BridgeMemo.model_validate(
        {
            **bridge_v1.model_dump(mode="json"),
            "bridge_type": "feedback_bridge_v2",
            "feedback_loop_summary": {"input_bridge": "bridge_memos/bridge_0.json"},
        }
    )

    synthesis = orchestrator._build_synthesis_packet(packet, context, layer_cards, [bridge_v1, bridge_v2])

    assert len(synthesis.high_severity_conflicts) == 1
    assert len(synthesis.principal_contradictions) == 1
    feedback_summary = next(item for item in synthesis.bridge_summaries if item.bridge_type == "feedback_bridge_v2")
    assert feedback_summary.key_conflicts == []
    assert feedback_summary.principal_contradiction is None


def test_counter_thesis_uses_llm_when_available(tmp_path: Path):
    response = {
        "input_refs": ["synthesis_packet.json", "bridge_memos/bridge_0.json"],
        "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
        "hypotheses": [
            {
                "hypothesis_id": "hyp_counter_llm",
                "hypothesis_text": "反方解释：趋势证据说明市场可能已部分消化利率压力。",
                "source": "counter_thesis",
                "support_evidence_refs": ["L5.get_qqq_technical_indicators"],
                "counter_evidence_refs": ["L1.get_fed_funds_rate"],
                "diagnostic_evidence_refs": ["L5.get_qqq_technical_indicators"],
                "cannot_explain": ["不能证明估值便宜。"],
                "falsification_conditions": ["趋势跌破关键均线。"],
                "confidence": "low",
                "status": "candidate",
                "adjudication_reason": "用趋势证据挑战单一路径。",
            }
        ],
        "principal_counterargument": "趋势证据可能说明部分压力已被消化。",
        "cannot_establish": ["不能证明主线错误。"],
    }
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({"counter_thesis": json.dumps(response, ensure_ascii=False)}),
    )
    synthesis_packet = SynthesisPacket(
        evidence_index={
            "L1.get_fed_funds_rate": {"layer": "L1"},
            "L5.get_qqq_technical_indicators": {"layer": "L5"},
        },
        bridge_summaries=[],
    )
    bridge_v2 = BridgeMemo(bridge_type="feedback_bridge_v2", layers_connected=["L1", "L5"], implication_for_ndx="保留张力。")

    draft = orchestrator._build_counter_thesis(
        synthesis_packet=synthesis_packet,
        bridge_v2=bridge_v2,
        investigation_reports=[],
    )

    assert draft.hypotheses[0].source == "counter_thesis"
    assert draft.hypotheses[0].support_evidence_refs == ["L5.get_qqq_technical_indicators"]
    assert draft.prompt_input_audit["allowed_inputs_only"] is True
    assert draft.prompt_input_audit["thesis_read"] is False


def test_stage4_evidence_registry_and_final_claim_ledger_are_auditable(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = _mock_packet()
    synthesis_packet = SynthesisPacket(
        packet_meta=packet.meta,
        evidence_index={
            "L1.get_fed_funds_rate": {
                "layer": "L1",
                "function_id": "get_fed_funds_rate",
                "metric": "Fed Funds Rate",
                "canonical_question": "利率是否形成估值压力？",
                "misread_guards": ["不能证明估值便宜"],
                "permission_type": "fact",
            },
            "L4.get_ndx_pe_and_earnings_yield": {
                "layer": "L4",
                "function_id": "get_ndx_pe_and_earnings_yield",
                "metric": "NDX Valuation",
                "canonical_question": "估值是否昂贵？",
                "misread_guards": ["不能证明短线买点"],
                "permission_type": "fact",
            },
            "L5.get_qqq_technical_indicators": {
                "layer": "L5",
                "function_id": "get_qqq_technical_indicators",
                "metric": "QQQ Technical",
                "canonical_question": "趋势是否仍有效？",
                "misread_guards": ["不能证明估值便宜"],
                "permission_type": "technical",
            },
        },
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="rates_vs_valuation",
                conflict_type="rates_vs_valuation",
                severity="high",
                description="利率压力与高估值冲突。",
                implication="强结论必须保留风险边界。",
                involved_layers=["L1", "L4"],
                evidence_refs=["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
                falsifiers=["利率快速下行且盈利上修。"],
            )
        ],
    )
    investigation = InvestigationReport(
        originating_agent_id="agent_gap",
        finding="价格反映程度仍不能高置信确认。",
        evidence_refs=["L1.get_fed_funds_rate"],
        counter_evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
        claims_supported=["保留估值和利率张力"],
        claims_challenged=["强单一路径裁决"],
        cannot_establish=["不能证明压力已经完全反映"],
        confidence=Confidence.MEDIUM,
        limits=["no_backflow_to_l1_l5"],
        effective_date="2026-04-24",
    )
    competition = HypothesisCompetition(
        hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_base",
                hypothesis_text="主线解释：利率压力压制估值。",
                source="bridge_v2",
                support_evidence_refs=["L1.get_fed_funds_rate"],
                counter_evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
                diagnostic_evidence_refs=["L1.get_fed_funds_rate"],
                cannot_explain=["趋势仍强。"],
                falsification_conditions=["利率快速下行。"],
            ),
            CompetingHypothesis(
                hypothesis_id="hyp_counter",
                hypothesis_text="反方解释：趋势仍强说明价格可能已经部分消化利率压力。",
                source="counter_thesis",
                support_evidence_refs=["L5.get_qqq_technical_indicators"],
                counter_evidence_refs=["L1.get_fed_funds_rate"],
                diagnostic_evidence_refs=["L5.get_qqq_technical_indicators"],
                cannot_explain=["不能证明估值便宜。"],
                falsification_conditions=["趋势跌破关键均线。"],
            )
        ]
    )

    registry = orchestrator._build_evidence_registry(
        packet_model=packet,
        synthesis_packet=synthesis_packet,
        investigation_reports=[investigation],
        hypothesis_competition=competition,
    )
    synthesis_packet.competing_hypotheses = competition.hypotheses
    thesis = ThesisDraft(
        environment_assessment="利率仍有压力。",
        valuation_assessment="估值不便宜。",
        timing_assessment="趋势仍需观察。",
        main_thesis="NDX 仍处在利率压力与高估值拉扯中。",
        key_support_chains=[
            KeySupportChain(
                chain_description="利率压力约束估值。",
                evidence_refs=["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
                weight=0.7,
            )
        ],
        priced_narrative="市场可能部分反映利率压力，但仍不清楚。",
        payoff_assessment="赔率需要降级看待。",
        invalidation_conditions=["利率快速下行且盈利上修。"],
        overall_confidence=Confidence.MEDIUM,
    )
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="中性偏谨慎，保留利率与估值张力。",
        confidence=Confidence.MEDIUM,
        key_support_chains=thesis.key_support_chains,
        must_preserve_risks=["估值压力仍未解除。"],
        blocking_issues=[],
        evidence_refs=["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
        adjudicator_notes="Final 保留主要反证和失效条件。",
        reader_final=ReaderFinal(
            one_liner="NDX 不是无条件看多，仍要看利率和盈利是否配合。",
            three_reasons=["利率仍有压力", "估值不便宜", "反证未消失"],
            invalidation_summary=["利率快速下行且盈利上修。"],
            evidence_refs=["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
        ),
        invalidation_conditions=["利率快速下行且盈利上修。"],
    )

    ledger = orchestrator._build_final_claim_ledger(
        synthesis_packet=synthesis_packet,
        thesis=thesis,
        final_adjudication=final,
        evidence_registry=registry,
        effective_date="2026-04-24",
    )
    updated_registry = orchestrator._attach_claims_to_evidence_registry(registry, ledger)

    assert isinstance(registry, EvidenceRegistry)
    assert "L1.get_fed_funds_rate" in registry.passports
    assert "investigation_reports/" + investigation.investigation_id + ".json" in registry.passports
    assert "hyp_base" in registry.passports
    assert isinstance(ledger, ClaimLedger)
    assert ledger.entries
    assert all(entry.evidence_refs for entry in ledger.entries)
    assert all(entry.counter_evidence_refs for entry in ledger.entries)
    assert all(entry.falsification_conditions for entry in ledger.entries)
    market_entry = next(entry for entry in ledger.entries if entry.claim_type == "market_state")
    risk_entry = next(entry for entry in ledger.entries if entry.claim_type == "risk_boundary")
    assert set(market_entry.counter_evidence_refs) != set(risk_entry.counter_evidence_refs)
    assert market_entry.counter_evidence_method == "opposing_hypothesis_support_plus_typed_conflicts"
    assert updated_registry.passports["L1.get_fed_funds_rate"].linked_claim_ids
