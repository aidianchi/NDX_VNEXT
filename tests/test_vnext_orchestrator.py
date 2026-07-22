import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4
from agent_analysis.contracts import (
    AgentBudget,
    AgentSpec,
    ApprovalStatus,
    BridgeMemo,
    ClaimLedger,
    ClaimLedgerEntry,
    CompetingHypothesis,
    Confidence,
    ContextBrief,
    CoreFact,
    CounterThesisDraft,
    Critique,
    EvidencePassport,
    EvidenceRegistry,
    EventInterpretationCard,
    FinalAdjudication,
    GoldenPitChecklist,
    HypothesisCompetition,
    InquiryMessage,
    InquiryMessageType,
    InvestigationReport,
    IndicatorAnalysis,
    KeySupportChain,
    LayerCard,
    ReaderFinal,
    RiskBoundaryReport,
    SynthesisPacket,
    ThesisDraft,
    TypedConflict,
    UserDecisionCondition,
    UserDecisionProfile,
)
from agent_analysis import orchestrator as orchestrator_module
from agent_analysis.orchestrator import VNextOrchestrator
from agent_analysis.packet_builder import AnalysisPacketBuilder


@pytest.fixture(autouse=True)
def _register_mini_stage_inline_prompt():
    # 本文件多个测试使用合成 stage "mini"；生产代码现在要求 prompt 缺失时显式
    # 报错，所以测试必须自己声明这个 stage 的 inline prompt，不能依赖静默兜底。
    for synthetic_stage in ("mini", "test"):
        orchestrator_module.INLINE_PROMPTS[synthetic_stage] = "测试用合成 stage prompt：请返回严格合法的 JSON。"
    try:
        yield
    finally:
        for synthetic_stage in ("mini", "test"):
            orchestrator_module.INLINE_PROMPTS.pop(synthetic_stage, None)


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


class UniformEventCardFakeLLMEngine(FakeLLMEngine):
    def __init__(self, response):
        super().__init__({})
        self.response = response
        self.calls = []
        self.prompts = []

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None):
        self.calls.append(stage_name)
        self.prompts.append(prompt)
        return self.response


class MiniStageModel(BaseModel):
    value: str


class RefStageModel(BaseModel):
    evidence_refs: list[str] = Field(default_factory=list)


_VALID_REASONED_VERDICT = (
    "当前判断对象是纳斯达克100，姿态为中性偏谨慎，时间尺度覆盖未来数日到十二个月。"
    "第一条理由是政策利率仍高，折现压力没有解除 [L1.get_fed_funds_rate]，但趋势尚未破坏限制了结论强度。"
    "第二条理由是估值处于偏高水平 [L4.get_ndx_pe_and_earnings_yield]，不过盈利韧性意味着估值不能单独决定方向。"
    "第三条理由是价格趋势仍有支撑 [L5.get_qqq_technical_indicators]，但内部广度不足使这条证据只能支持等待而非追涨。"
    "综合来看，当前赔率不足以支持激进加仓，等待确认也会付出踏空代价。"
    "最强的反对解释是盈利与趋势会继续压过利率和估值压力，但本轮证据还不足以让它改变判断。"
)


def _event_card_response(event_id="event:abc", tier="official"):
    interpretation = "该事件可能改变折现率预期，但仍需数据确认。"
    if tier != "official":
        interpretation = "据报道，该事件可能改变盈利预期，但仍需正式数据确认。"
    return json.dumps(
        {
            "event_id": event_id,
            "fact_summary": "材料称公司发布了更新。",
            "interpretation": interpretation,
            "entities": ["NVDA"],
            "event_type": "company_news",
            "mechanism_hypothesis": {
                "financial_link": "discount_rate" if tier == "official" else "earnings_path",
                "hypothesis": "该事件可能通过折现率渠道影响纳指100估值。" if tier == "official" else "该事件可能通过盈利路径渠道影响纳指100。",
            },
            "supports_hypotheses": ["hyp_rates"],
            "refutes_hypotheses": [],
            "limitations": ["事件材料不能证明指数必须涨跌。"],
            "needs_data_confirmation": ["正式数据是否同步确认"],
            "upgrade_candidate": False,
            "passport": {
                "source": "模型不得决定",
                "tier": "模型不得决定",
                "published_at": "模型不得决定",
                "event_date": "模型不得决定",
                "effective_date": "模型不得决定",
            },
        },
        ensure_ascii=False,
    )


def _write_event_card_inputs(run_dir: Path, events, news_card_ids):
    (run_dir / "news_event_ledger.json").write_text(
        json.dumps({"events": events}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "event_mechanism_report.json").write_text(
        json.dumps(
            {
                "mainlines": [
                    {
                        "mainline_id": "macro_rate_valuation_pressure",
                        "news_card_ids": news_card_ids,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_event_card_candidate_selection_uses_only_three_triggers(tmp_path: Path):
    events = [
        {
            "event_id": "event:mainline",
            "title": "Mainline event",
            "source_name": "Official Source",
            "source_tier": "official",
            "event_type": "policy_news",
            "published_at": "2026-07-18T09:00:00Z",
            "event_date": "2026-07-18",
            "raw_text_available": True,
            "raw_text_excerpt": "Mainline body.",
        },
        {
            "event_id": "event:challenged",
            "title": "Challenged event",
            "source_name": "Media",
            "source_tier": "reliable_mainstream_report",
            "event_type": "company_news",
            "published_at": "2026-07-18T08:00:00Z",
            "event_date": "2026-07-18",
        },
        {
            "event_id": "event:calendar_today",
            "title": "Calendar landing",
            "source_name": "BLS",
            "source_tier": "official",
            "event_type": "official_calendar",
            "published_at": "2026-07-01T00:00:00Z",
            "event_date": "2026-07-18",
        },
        {
            "event_id": "event:untriggered",
            "title": "Background only",
            "source_name": "Media",
            "source_tier": "reliable_mainstream_report",
            "event_type": "company_news",
            "published_at": "2026-07-18T07:00:00Z",
            "event_date": "2026-07-18",
        },
    ]
    _write_event_card_inputs(tmp_path, events, ["news:mainline"])
    message = InquiryMessage(
        message_type=InquiryMessageType.EVENT_CHALLENGE,
        sender_stage="L2",
        target_stage="integrated_synthesis",
        trigger="事件需要追问。",
        question="这条事件是否有数据确认？",
        allowed_context_refs=["event_mechanism_report.json"],
        forbidden_context_refs=["layer_cards"],
        effective_date="2026-07-18",
        event_refs=["event:challenged"],
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )

    selected = orchestrator._select_event_card_candidates(
        effective_date="2026-07-18",
        feedback_messages=[message],
    )

    selected_by_id = {item["event_id"]: item for item in selected}
    assert set(selected_by_id) == {"event:mainline", "event:challenged", "event:calendar_today"}
    assert "mainline" in selected_by_id["event:mainline"]["trigger_reasons"]
    assert "inquiry_reference" in selected_by_id["event:challenged"]["trigger_reasons"]
    assert "official_calendar_landing" in selected_by_id["event:calendar_today"]["trigger_reasons"]


def test_event_card_generation_writes_audited_cards_without_analysis_packet_backflow(tmp_path: Path):
    event = {
        "event_id": "event:abc",
        "title": "Company update",
        "source_name": "Mainstream Media",
        "source_tier": "reliable_mainstream_report",
        "event_type": "company_news",
        "published_at": "2026-07-18T09:00:00Z",
        "event_date": "2026-07-18",
        "symbols": ["NVDA"],
        "raw_text_available": True,
        "raw_text_excerpt": "材料称公司发布了更新。",
    }
    _write_event_card_inputs(tmp_path, [event], ["news:abc"])
    (tmp_path / "analysis_packet.json").write_text('{"event_refs": {}}', encoding="utf-8")
    engine = UniformEventCardFakeLLMEngine(
        _event_card_response(event_id="event:wrong", tier="reliable_mainstream_report")
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    competition = HypothesisCompetition(
        hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_rates",
                hypothesis_text="利率约束仍是主线。",
                support_evidence_refs=["L1.rate"],
                diagnostic_evidence_refs=["L1.rate"],
                falsification_conditions=["利率回落"],
            )
        ]
    )

    artifact = orchestrator._build_event_interpretation_cards(
        effective_date="2026-07-18",
        feedback_messages=[],
        hypothesis_competition=competition,
    )

    assert artifact["schema_version"] == "event_interpretation_cards_v1"
    assert len(artifact["cards"]) == 1
    card = EventInterpretationCard.model_validate(artifact["cards"][0])
    assert card.event_id == "event:abc"
    assert card.passport.source == "Mainstream Media"
    assert card.passport.tier == "reliable_mainstream_report"
    assert card.passport.effective_date == "2026-07-18"
    assert card.interpretation.startswith("据报道")
    assert (tmp_path / "event_interpretation_cards.json").exists()
    assert (tmp_path / "event_interpretation_cards" / "event_abc.json").exists()
    assert json.loads((tmp_path / "analysis_packet.json").read_text(encoding="utf-8"))["event_refs"] == {}
    assert len(engine.calls) == 1
    assert "你是外部世界材料层的解读员" in engine.prompts[0]


def test_event_card_generation_hard_caps_llm_calls_at_ten(tmp_path: Path):
    events = [
        {
            "event_id": f"event:{index}",
            "title": f"Event {index}",
            "source_name": "Official Source",
            "source_tier": "official",
            "event_type": "policy_news",
            "published_at": "2026-07-18T09:00:00Z",
            "event_date": "2026-07-18",
            "raw_text_available": True,
            "raw_text_excerpt": "材料称公司发布了更新。",
        }
        for index in range(12)
    ]
    _write_event_card_inputs(tmp_path, events, [f"news:{index}" for index in range(12)])
    engine = UniformEventCardFakeLLMEngine(_event_card_response())
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )

    artifact = orchestrator._build_event_interpretation_cards(
        effective_date="2026-07-18",
        feedback_messages=[],
        hypothesis_competition=HypothesisCompetition(
            hypotheses=[
                CompetingHypothesis(
                    hypothesis_id="hyp_rates",
                    hypothesis_text="利率约束仍是主线。",
                    support_evidence_refs=["L1.rate"],
                    diagnostic_evidence_refs=["L1.rate"],
                    falsification_conditions=["利率回落"],
                )
            ]
        ),
    )

    assert len(artifact["cards"]) == 10
    assert artifact["selected_count"] == 10
    assert artifact["candidate_count_before_limit"] == 12
    card_calls = [call for call in engine.calls if call.startswith("event_card_interpreter")]
    summary_calls = [call for call in engine.calls if call.startswith("event_section_summary")]
    assert len(card_calls) == 10
    # Q3 章节总结是独立的单一阶段：允许少量重试，但不得放大成逐事件调用。
    assert len(summary_calls) <= 3
    assert len(engine.calls) == len(card_calls) + len(summary_calls)


def test_event_card_validator_accepts_equivalent_downgrade_and_translated_month_name(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    card = EventInterpretationCard.model_validate(
        json.loads(_event_card_response(tier="reliable_mainstream_report"))
    ).model_copy(
        update={
            "fact_summary": "该材料发布于2026年7月18日。",
            "interpretation": "该报道称事件可能影响盈利预期。",
            "limitations": ["未读全文，降级阅读：仅依据标题。"],
        }
    )
    event = {
        "source_tier": "reliable_mainstream_report",
        "title": "Update",
        "published_at": "Sat, 18 Jul 2026 09:00:00 GMT",
        "event_date": "",
        "raw_text_available": False,
        "raw_text_excerpt": "",
    }

    errors = orchestrator._event_card_validation_errors(
        card,
        event=event,
        allowed_hypothesis_ids={"hyp_rates"},
    )

    assert errors == []


def test_event_card_validator_still_rejects_weak_source_without_attribution(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    card = EventInterpretationCard.model_validate(
        json.loads(_event_card_response(tier="official"))
    )

    errors = orchestrator._event_card_validation_errors(
        card,
        event={
            "source_tier": "reliable_mainstream_report",
            "title": "Company update",
            "published_at": "2026-07-18",
            "event_date": "2026-07-18",
            "raw_text_available": True,
            "raw_text_excerpt": "材料称公司发布了更新。",
        },
        allowed_hypothesis_ids={"hyp_rates"},
    )

    assert any("non-official interpretation" in error for error in errors)


def test_event_card_validator_rejects_late_attribution_and_signed_number_reversal(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    card = EventInterpretationCard.model_validate(
        json.loads(_event_card_response(tier="official"))
    ).model_copy(
        update={
            "fact_summary": "公司股价下跌-10%。",
            "interpretation": "该事件可能影响盈利预期，据报道仍需确认。",
        }
    )

    errors = orchestrator._event_card_validation_errors(
        card,
        event={
            "source_tier": "reliable_mainstream_report",
            "title": "Company shares rose +10%",
            "published_at": "2026-07-18",
            "event_date": "2026-07-18",
            "raw_text_available": True,
            "raw_text_excerpt": "Company shares rose +10% after the update.",
        },
        allowed_hypothesis_ids={"hyp_rates"},
    )

    assert any("non-official interpretation" in error for error in errors)
    assert any("signed number direction" in error for error in errors)


def test_event_card_validator_rejects_material_absent_alternative_in_fact_summary(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    card = EventInterpretationCard.model_validate(
        json.loads(_event_card_response(tier="reliable_mainstream_report"))
    ).model_copy(
        update={
            "fact_summary": "标题称Kimi K3产品（或AI模型）进入美国股市。",
            "limitations": ["未读全文，降级阅读：仅依据标题。"],
        }
    )

    errors = orchestrator._event_card_validation_errors(
        card,
        event={
            "source_tier": "reliable_mainstream_report",
            "title": "China’s Kimi K3 Hits US Stock Markets",
            "published_at": "2026-07-18",
            "event_date": "2026-07-18",
            "raw_text_available": False,
            "raw_text_excerpt": "",
        },
        allowed_hypothesis_ids={"hyp_rates"},
    )

    assert any("alternative classification absent from material" in error for error in errors)


class RoutingFakeLLMEngine(FakeLLMEngine):
    def __init__(self, responses):
        super().__init__(responses)
        self.preferred_models_by_call = []
        self.successful_model = None

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None):
        self.preferred_models_by_call.append(list(preferred_models or []))
        self.successful_model = (preferred_models or ["fake"])[0]
        return self.responses[stage_name]


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


def test_load_prompt_never_uses_nested_legacy_copy(tmp_path: Path):
    prompts_dir = tmp_path / "prompt_root"
    nested_dir = prompts_dir / "prompts"
    nested_dir.mkdir(parents=True)
    (nested_dir / "l4_analyst.md").write_text("STALE_NESTED_L4_PROMPT", encoding="utf-8")
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path / "output"),
        prompts_dir=str(prompts_dir),
        llm_engine=FakeLLMEngine({}),
    )

    # l4_analyst has no INLINE_PROMPTS fallback, so a missing direct file must raise loudly
    # instead of silently reading the nested legacy copy or a generic placeholder string.
    with pytest.raises(RuntimeError, match="l4_analyst"):
        orchestrator._load_prompt("l4_analyst")


def test_load_prompt_uses_only_direct_file_in_configured_prompt_dir(tmp_path: Path):
    prompts_dir = tmp_path / "prompt_root"
    nested_dir = prompts_dir / "prompts"
    nested_dir.mkdir(parents=True)
    (prompts_dir / "l4_analyst.md").write_text("CURRENT_DIRECT_L4_PROMPT", encoding="utf-8")
    (nested_dir / "l4_analyst.md").write_text("STALE_NESTED_L4_PROMPT", encoding="utf-8")
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path / "output"),
        prompts_dir=str(prompts_dir),
        llm_engine=FakeLLMEngine({}),
    )

    assert orchestrator._load_prompt("l4_analyst") == "CURRENT_DIRECT_L4_PROMPT"


def test_load_prompt_falls_back_to_inline_prompt_when_file_missing(tmp_path: Path):
    prompts_dir = tmp_path / "prompt_root"
    prompts_dir.mkdir(parents=True)
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path / "output"),
        prompts_dir=str(prompts_dir),
        llm_engine=FakeLLMEngine({}),
    )

    # "bridge" has both a PROMPT_FILES entry and an INLINE_PROMPTS entry; when the
    # file is missing it should still fall back to the inline prompt instead of raising.
    assert orchestrator._load_prompt("bridge") == "你负责显式识别跨层支撑关系、冲突关系与关键不确定性。只返回合法 JSON。"


def test_load_prompt_raises_for_unknown_stage_without_inline_fallback(tmp_path: Path):
    prompts_dir = tmp_path / "prompt_root"
    prompts_dir.mkdir(parents=True)
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path / "output"),
        prompts_dir=str(prompts_dir),
        llm_engine=FakeLLMEngine({}),
    )

    with pytest.raises(RuntimeError, match="totally_unknown_stage"):
        orchestrator._load_prompt("totally_unknown_stage")


def test_l4_prompt_drops_audit_bookkeeping_without_dropping_metric_body(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    source_switches = [
        {
            "ticker": "AMAT",
            "field": "market_cap",
            "selected_source": "yahoo_quote_summary",
            "previous_source": None,
            "reason": "yfinance_missing",
        }
    ]

    prompt = orchestrator._compose_prompt(
        "l4_analyst",
        MiniStageModel,
        {
            "layer": "L4",
            "layer_raw_data": {
                "get_ndx_pe_and_earnings_yield": {
                    "function_id": "get_ndx_pe_and_earnings_yield",
                    "metric_name": "NDX PE and Earnings Yield",
                    "value": {
                        "PE_TTM": 36.6,
                        "EarningsYield": 2.73,
                        "Coverage": {
                            "market_cap_coverage_pct": 92.5,
                            "source_switches": source_switches,
                        },
                        "SourceReconciliation": {"source_switches": source_switches},
                    },
                    "unit": {"PE_TTM": "x", "EarningsYield": "%"},
                    "source_tier": "component_model",
                    "source_name": "Component model",
                    "date": "2026-07-07",
                    "data_quality": {
                        "source_tier": "component_model",
                        "formula": "weighted component valuation",
                        "source_switches": source_switches,
                        "large_rows": [{"row": i} for i in range(12)],
                    },
                    "notes": "synthetic valuation payload",
                    "manual_override_used": False,
                }
            },
        },
    )

    manifest_text = prompt.split("### 当前层指标清单\n", 1)[1].split("\n\n### 结构示例", 1)[0]
    runtime_input = prompt.split("## Runtime Input\n", 1)[1]

    assert "selected_source" not in prompt
    assert "source_switches" not in prompt
    assert '"value"' not in manifest_text
    assert "PE_TTM" not in manifest_text
    assert '"count": 12' in manifest_text
    assert '"row": 0' not in manifest_text
    assert '"PE_TTM": 36.6' in runtime_input
    assert '"EarningsYield": 2.73' in runtime_input
    assert "单位未标注" in prompt


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
                "reasoned_verdict": _VALID_REASONED_VERDICT,
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
    assert result["final_adjudication"].reasoned_verdict == _VALID_REASONED_VERDICT
    assert result["schema_guard_report"].passed is True
    assert len(result["bridge_memos"]) == 2
    assert "L1.get_fed_funds_rate" in result["synthesis_packet"].evidence_index
    assert (tmp_path / "final_adjudication.json").exists()
    saved_final = json.loads((tmp_path / "final_adjudication.json").read_text(encoding="utf-8"))
    assert saved_final["reasoned_verdict"] == _VALID_REASONED_VERDICT
    assert "reasoned_verdict_unresolved_refs" not in str(
        (saved_final.get("quality_gate") or {}).get("notes") or ""
    )
    assert (tmp_path / "run_review_report.json").exists()
    assert (tmp_path / "bridge_memos" / "bridge_v2.json").exists()
    assert (tmp_path / "counter_thesis.json").exists()
    assert (tmp_path / "hypothesis_competition.json").exists()
    assert (tmp_path / "adjudication_history.json").exists()
    boundary_manifest = json.loads((tmp_path / "runtime_boundary_manifest.json").read_text(encoding="utf-8"))
    assert boundary_manifest["schema_version"] == "runtime_boundary_manifest_v1"
    assert "investigation_reports" in boundary_manifest["layer_input_policies"]["L1"]["forbidden_runtime_inputs"]
    assert "UserDecisionProfile" in boundary_manifest["reader_exit_boundary"]
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
    assert resumed["final_adjudication"].reasoned_verdict == _VALID_REASONED_VERDICT
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


def test_schema_guard_tolerates_renamed_but_semantically_identical_conflict(tmp_path: Path, monkeypatch):
    # Fix 2 regression: Bridge's typed_conflicts (conflict_id="C1_...") and Thesis's
    # retained_conflicts (conflict_type carries a differently-worded id, simulating
    # the real E2E run) should be reconciled by exact-severity + same-description
    # semantic match, not flagged as a dropped high severity conflict.
    #
    # Also covers Fix 1 end-to-end: the bridge conflict cites
    # "L4.get_equity_risk_premium#level", which must resolve as a valid evidence
    # ref now that get_equity_risk_premium registers value["MetricAuthority"].
    monkeypatch.setattr(
        tools_L4,
        "get_ndx_pe_and_earnings_yield",
        lambda end_date=None: {
            "name": "NDX Valuation",
            "value": {"EarningsYield": 4.0, "FCFYield": 3.5},
            "data_quality": {"source_tier": "component_model"},
        },
    )
    monkeypatch.setattr(
        tools_L4,
        "get_10y_treasury",
        lambda end_date=None: {"value": {"level": 4.25}},
    )
    erp_payload = tools_L4.get_equity_risk_premium("2026-04-24")

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
                "raw_data": {"name": "Fed Funds Rate", "value": {"level": 5.25, "trend": "rising"}},
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:01Z",
            },
            {
                "layer": 4,
                "metric_name": "NDX Simple Yield Gap",
                "function_id": "get_equity_risk_premium",
                "raw_data": erp_payload,
                "error": None,
                "collection_timestamp_utc": "2026-04-24T00:00:07Z",
            },
        ],
    }
    packet = AnalysisPacketBuilder().build(
        data_json,
        manual_overrides={
            "active": False,
            "date": "2026-04-24",
            "metrics": {
                "get_fed_funds_rate": {"value": {"level": 5.25}},
            },
        },
    )

    description_text = (
        "NDX估值昂贵（PE 10年分位82%，简式收益差距-1.76%）与宏观环境紧缩"
        "（实际利率99%分位，净流动性动量转负）的对立。"
    )

    bridge = BridgeMemo.model_validate(
        {
            "bridge_type": "macro_valuation",
            "layers_connected": ["L1", "L4"],
            "cross_layer_claims": [],
            "typed_conflicts": [
                {
                    "conflict_id": "C1_expensive_vs_restrictive",
                    "conflict_type": "valuation_vs_macro",
                    "severity": "high",
                    "description": description_text,
                    "mechanism": "估值扩张与紧缩流动性相互对立。",
                    "implication": "需要同时权衡估值贵与流动性紧的双重压力。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": ["L1.get_fed_funds_rate", "L4.get_equity_risk_premium#level"],
                }
            ],
            "implication_for_ndx": "测试。",
        }
    )

    thesis = ThesisDraft.model_validate(
        {
            "environment_assessment": "环境偏紧。",
            "valuation_assessment": "估值偏高。",
            "timing_assessment": "趋势待确认。",
            "main_thesis": "测试。",
            "overall_confidence": "medium",
            "retained_conflicts": [
                {
                    # Deliberately a different id than the bridge's conflict_id/conflict_type,
                    # simulating the real run where Thesis echoed typed_conflicts differently.
                    "conflict_type": "L4_expensive_vs_L1_restrictive",
                    "severity": "high",
                    "description": description_text,
                    "implication": "需要同时权衡估值贵与流动性紧的双重压力。",
                    "involved_layers": ["L1", "L4"],
                }
            ],
        }
    )

    report = orchestrator._run_schema_guard(
        packet,
        [],
        [bridge],
        thesis,
        Critique.model_validate({"overall_assessment": "测试。", "revision_direction": "测试。"}),
        RiskBoundaryReport.model_validate({"must_preserve_risks": ["测试风险"]}),
    )

    assert not any("High severity conflicts missing" in issue for issue in report.consistency_issues)
    assert not any(
        "get_equity_risk_premium#level" in issue and "invalid" in issue
        for issue in report.consistency_issues
    )


def test_schema_guard_still_flags_genuinely_dropped_high_conflict(tmp_path: Path):
    # Fix 2 regression counterpart: when Thesis drops a high severity conflict
    # entirely (no id match, no semantic match), Schema Guard must still catch it.
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
            "cross_layer_claims": [],
            "typed_conflicts": [
                {
                    "conflict_id": "C1_expensive_vs_restrictive",
                    "conflict_type": "valuation_vs_macro",
                    "severity": "high",
                    "description": "NDX估值昂贵与宏观环境紧缩的对立。",
                    "mechanism": "估值扩张与紧缩流动性相互对立。",
                    "implication": "需要同时权衡估值贵与流动性紧的双重压力。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": ["L1.get_fed_funds_rate"],
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
                "environment_assessment": "环境偏紧。",
                "valuation_assessment": "估值偏高。",
                "timing_assessment": "趋势待确认。",
                "main_thesis": "测试。",
                "overall_confidence": "medium",
                "retained_conflicts": [],
            }
        ),
        Critique.model_validate({"overall_assessment": "测试。", "revision_direction": "测试。"}),
        RiskBoundaryReport.model_validate({"must_preserve_risks": ["测试风险"]}),
    )

    joined = "\n".join(report.consistency_issues)
    assert "High severity conflicts missing" in joined
    assert "C1_expensive_vs_restrictive" in joined


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


def test_run_stage_uses_stage_model_routing_for_cognitive_stages(tmp_path: Path):
    engine = RoutingFakeLLMEngine({"thesis": '{"value": "ok"}'})
    orchestrator = VNextOrchestrator(
        available_models=["deepseek-v4-flash", "deepseek-v4-pro"],
        output_dir=str(tmp_path),
        llm_engine=engine,
    )

    result = orchestrator._run_stage(
        stage_key="thesis",
        stage_name="thesis",
        model_cls=MiniStageModel,
        payload={"example": "payload"},
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert result.value == "ok"
    assert engine.preferred_models_by_call[0][0] == "deepseek-v4-pro"
    assert diagnostics["stages"]["thesis"]["model_routing"]["preferred_models"][0] == "deepseek-v4-pro"
    assert diagnostics["stages"]["thesis"]["model"] == "deepseek-v4-pro"


def test_thesis_retries_until_every_candidate_hypothesis_has_auditable_response(tmp_path: Path):
    invalid = {
        "environment_assessment": "环境偏紧。",
        "valuation_assessment": "估值偏高。",
        "timing_assessment": "趋势仍在但质量存疑。",
        "main_thesis": "主线仍成立，但必须回应竞争解释。",
        "hypothesis_responses": [
            {
                "hypothesis_id": "hyp_counter_1",
                "verdict": "reject",
                "reasoning": "趋势证据不足以推翻估值压力。",
                "evidence_refs": [],
            }
        ],
        "overall_confidence": "medium",
    }
    valid = {
        **invalid,
        "hypothesis_responses": [
            {
                "hypothesis_id": "hyp_counter_1",
                "verdict": "reject",
                "reasoning": "正式估值证据构成反证。",
                "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
            },
            {
                "hypothesis_id": "hyp_counter_2",
                "verdict": "absorb_partially",
                "reasoning": "部分吸收趋势解释，但仍缺少广度确认。",
                "evidence_refs": ["L5.get_qqq_technical_indicators"],
            },
        ],
    }
    engine = SequencedFakeLLMEngine(
        {"thesis": [json.dumps(invalid, ensure_ascii=False), json.dumps(valid, ensure_ascii=False)]}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
    )
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-24"},
        evidence_index={
            "L4.get_ndx_pe_and_earnings_yield": {"layer": "L4"},
            "L5.get_qqq_technical_indicators": {"layer": "L5"},
        },
        competing_hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_counter_1",
                hypothesis_text="估值压力可能仍未反映。",
                source="counter_thesis",
                status="candidate",
            ),
            CompetingHypothesis(
                hypothesis_id="hyp_counter_2",
                hypothesis_text="趋势可能已经吸收部分压力。",
                source="counter_thesis",
                status="candidate",
            ),
            CompetingHypothesis(
                hypothesis_id="hyp_leading",
                hypothesis_text="当前主线解释。",
                source="bridge_v2",
                status="leading",
            ),
        ],
    )

    thesis = orchestrator._run_thesis(synthesis)

    assert engine.calls["thesis"] == 2
    assert {response.hypothesis_id for response in thesis.hypothesis_responses} == {
        "hyp_counter_1",
        "hyp_counter_2",
    }
    assert thesis.hypothesis_responses[0].evidence_refs == ["L4.get_ndx_pe_and_earnings_yield"]
    retry_prompt = (tmp_path / "prompt_audit" / "thesis" / "attempt_2.prompt.txt").read_text(encoding="utf-8")
    assert "hyp_counter_2" in retry_prompt
    assert "reject requires at least one evidence_ref" in retry_prompt

    governance = orchestrator._build_governance_input_packet(synthesis, thesis)

    assert [response.hypothesis_id for response in governance.thesis_hypothesis_responses] == [
        "hyp_counter_1",
        "hyp_counter_2",
    ]
    assert "L4.get_ndx_pe_and_earnings_yield" in governance.key_evidence_refs
    assert "L5.get_qqq_technical_indicators" in governance.key_evidence_refs


def test_thesis_hypothesis_response_validator_rejects_duplicates_and_refs_outside_index(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-24"},
        evidence_index={"L4.get_ndx_pe_and_earnings_yield": {"layer": "L4"}},
        competing_hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_counter",
                hypothesis_text="估值压力可能仍未反映。",
                source="counter_thesis",
                status="candidate",
            )
        ],
    )
    base = {
        "environment_assessment": "环境偏紧。",
        "valuation_assessment": "估值偏高。",
        "timing_assessment": "趋势待确认。",
        "main_thesis": "保留竞争解释。",
        "overall_confidence": "medium",
    }
    duplicate = ThesisDraft.model_validate(
        {
            **base,
            "hypothesis_responses": [
                {
                    "hypothesis_id": "hyp_counter",
                    "verdict": "absorb_partially",
                    "reasoning": "部分吸收。",
                },
                {
                    "hypothesis_id": "hyp_counter",
                    "verdict": "reject",
                    "reasoning": "驳回。",
                    "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
                },
            ],
        }
    )
    invalid_ref = ThesisDraft.model_validate(
        {
            **base,
            "hypothesis_responses": [
                {
                    "hypothesis_id": "hyp_counter",
                    "verdict": "reject",
                    "reasoning": "驳回。",
                    "evidence_refs": ["L9.fake_ref"],
                }
            ],
        }
    )

    assert any(
        "duplicate hypothesis_responses" in error
        for error in orchestrator._validate_thesis_hypothesis_responses(duplicate, synthesis)
    )
    assert any(
        "outside evidence_index" in error
        for error in orchestrator._validate_thesis_hypothesis_responses(invalid_ref, synthesis)
    )


def test_thesis_resume_rejects_legacy_checkpoint_without_candidate_responses(tmp_path: Path):
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-24"},
        evidence_index={"L4.get_ndx_pe_and_earnings_yield": {"layer": "L4"}},
        competing_hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_counter",
                hypothesis_text="估值压力可能仍未反映。",
                source="counter_thesis",
                status="candidate",
            )
        ],
    )
    valid_payload = {
        "environment_assessment": "环境偏紧。",
        "valuation_assessment": "估值偏高。",
        "timing_assessment": "趋势待确认。",
        "main_thesis": "保留竞争解释。",
        "hypothesis_responses": [
            {
                "hypothesis_id": "hyp_counter",
                "verdict": "reject",
                "reasoning": "估值证据构成反证。",
                "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
            }
        ],
        "overall_confidence": "medium",
    }
    first = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({"thesis": json.dumps(valid_payload, ensure_ascii=False)}),
    )
    first._run_thesis(synthesis)

    checkpoint_path = tmp_path / "thesis_draft.json"
    legacy_payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    legacy_payload.pop("hypothesis_responses", None)
    checkpoint_path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")
    manifest_path = tmp_path / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["thesis_draft.json"]["sha256"] = first._sha256_file(checkpoint_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    second_engine = SequencedFakeLLMEngine({"thesis": json.dumps(valid_payload, ensure_ascii=False)})
    second = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=second_engine,
        resume_from_existing=True,
    )
    thesis = second._run_thesis(synthesis)

    assert second_engine.calls["thesis"] == 1
    assert thesis.hypothesis_responses[0].hypothesis_id == "hyp_counter"
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["stages"]["thesis"]["status"] == "ok"


def test_thesis_builder_prompt_keeps_work_order_r7_block_exact():
    prompt = Path(orchestrator_module.__file__).with_name("prompts").joinpath("thesis_builder.md").read_text(encoding="utf-8")
    required_block = (
        "## 对竞争假说的强制回应\n"
        "`synthesis_packet.competing_hypotheses` 里每一个 status 为 candidate 的假说，你必须在 `hypothesis_responses` 里逐一回应，三选一：接受并修正判断（accept_and_revise）、部分吸收（absorb_partially）、驳回（reject）。驳回必须引用具体的反证 evidence_ref，不许用\"证据不足\"四个字一笔带过——证据不足时的诚实选项是 absorb_partially 并写明缺哪条证据。你的主论点如果无法回应某个假说最强的那条证据，就不许假装没看见它。"
    )

    assert prompt.count(required_block) == 1


def test_reviser_final_evidence_refs_outside_index_trigger_retry(tmp_path: Path):
    engine = SequencedFakeLLMEngine(
        {
            "final_adjudicator": [
                '{"evidence_refs": ["L9.fake_ref"]}',
                '{"evidence_refs": ["L1.get_fed_funds_rate"]}',
            ]
        }
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    result = orchestrator._run_stage(
        stage_key="final",
        stage_name="final_adjudicator",
        model_cls=RefStageModel,
        payload={"example": "payload"},
        validator=lambda candidate: orchestrator._validate_stage_evidence_refs(
            candidate,
            {"L1.get_fed_funds_rate"},
            "final",
        ),
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert result.evidence_refs == ["L1.get_fed_funds_rate"]
    assert engine.calls["final_adjudicator"] == 2
    assert diagnostics["stages"]["final_adjudicator"]["errors"][0]["kind"] == "contract_validation_error"
    assert "evidence_ref_source_validation failed" in diagnostics["stages"]["final_adjudicator"]["errors"][0]["message"]


def test_final_stage_retries_after_overlong_reasoned_verdict(tmp_path: Path):
    base = {
        "approval_status": "approved_with_reservations",
        "final_stance": "中性偏谨慎",
        "confidence": "medium",
        "must_preserve_risks": ["估值压缩风险"],
        "blocking_issues": [],
        "adjudicator_notes": "保留风险边界。",
    }
    engine = SequencedFakeLLMEngine({
        "final_adjudicator": [
            json.dumps({**base, "reasoned_verdict": "过长" * 651}, ensure_ascii=False),
            json.dumps({**base, "reasoned_verdict": _VALID_REASONED_VERDICT}, ensure_ascii=False),
        ]
    })
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    result = orchestrator._run_stage(
        stage_key="final",
        stage_name="final_adjudicator",
        model_cls=FinalAdjudication,
        payload={"example": "payload"},
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert result.reasoned_verdict == _VALID_REASONED_VERDICT
    assert engine.calls["final_adjudicator"] == 2
    assert diagnostics["stages"]["final_adjudicator"]["errors"][0]["kind"] == "schema_validation_error"
    assert "reasoned_verdict" in diagnostics["stages"]["final_adjudicator"]["errors"][0]["message"]


def test_reasoned_verdict_ref_validation_is_non_blocking_and_normalized(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    body = (
        "当前判断对象是纳斯达克100，姿态为中性偏谨慎。"
        "实际利率仍构成折现压力 [ l1.get_10y_real_rate ]，但趋势反证限制结论强度。"
        "估值补偿仍薄，盈利韧性则构成反面证据。价格趋势尚有支撑，内部广度不足限制追涨。"
        "当前赔率不足以支持激进加仓，等待确认也会付出踏空代价。"
        "最强反对解释是盈利与趋势会继续占优，但本轮证据不足以改变判断。"
    )
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="中性偏谨慎",
        confidence=Confidence.MEDIUM,
        must_preserve_risks=["估值压缩风险"],
        adjudicator_notes="保留风险边界。",
        reasoned_verdict=(body * 2)[:700],
    )

    orchestrator._annotate_reasoned_verdict_refs(final, {"L1.get_10y_real_rate"})

    notes = final.quality_gate.notes if final.quality_gate is not None else ""
    assert "reasoned_verdict_unresolved_refs" not in notes

    final.reasoned_verdict = final.reasoned_verdict.replace(
        "[ l1.get_10y_real_rate ]", "[L9.fake_ref]", 1
    )
    orchestrator._annotate_reasoned_verdict_refs(final, {"L1.get_10y_real_rate"})
    assert "reasoned_verdict_unresolved_refs:L9.fake_ref" in final.quality_gate.notes


def test_reasoned_verdict_without_any_ref_gets_degraded_note(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="中性偏谨慎",
        confidence=Confidence.MEDIUM,
        must_preserve_risks=["估值压缩风险"],
        adjudicator_notes="保留风险边界。",
        reasoned_verdict="没有引用的判决正文。" * 30,
    )

    orchestrator._annotate_reasoned_verdict_refs(final, {"L1.get_10y_real_rate"})

    assert "reasoned_verdict_missing_refs" in final.quality_gate.notes


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


def _controlled_investigation_inputs(tmp_path: Path):
    artifact = tmp_path / "layer_cards" / "L1.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "layer_synthesis": "实际利率仍高，但政策路径存在不确定性。",
                "risk_flags": ["高利率压制估值"],
                "unrelated": "不相关材料",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    message = InquiryMessage(
        message_id="inq_controlled",
        message_type=InquiryMessageType.ADJUDICATION_GAP,
        sender_stage="bridge",
        target_stage="bridge",
        trigger="利率与估值冲突未决。",
        question="实际利率材料能确认什么、挑战什么？",
        allowed_context_refs=["layer_cards/L1.json"],
        forbidden_context_refs=["thesis_draft.json", "final_adjudication.json"],
        effective_date="2026-07-14",
    )
    spec = AgentSpec(
        agent_id="agent_controlled",
        originating_message_id=message.message_id,
        research_question=message.question,
        allowed_context_refs=list(message.allowed_context_refs),
        forbidden_context_refs=list(message.forbidden_context_refs),
        allowed_tools=["read_allowed_artifacts"],
        budget=AgentBudget(max_tool_calls=0, max_minutes=1, max_source_refs=3),
        stop_conditions=["materials_exhausted"],
        success_criteria=["separate support and challenge"],
        required_output={"contract": "InvestigationReport"},
    )
    return spec, message


def test_controlled_investigation_llm_output_is_non_stub_and_audited(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    response = json.dumps(
        {
            "finding": "材料确认实际利率仍构成约束，但不能确认估值一定下跌 [M1]。",
            "claims_supported": ["实际利率约束仍在 [M1]"],
            "claims_challenged": ["高利率必然导致指数下跌 [M1]"],
            "counter_evidence_refs": ["[M1]"],
            "cannot_establish": ["缺少估值与盈利材料，不能确认价格方向 [M1]"],
            "confidence": "medium",
            "limits": ["只读取 [M1]，没有外部研究"],
        },
        ensure_ascii=False,
    )
    engine = SequencedFakeLLMEngine({"controlled_investigation": response})
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    spec, message = _controlled_investigation_inputs(tmp_path)

    report = orchestrator._build_investigation_report(spec, message)

    assert report.is_deterministic_stub is False
    assert report.claims_challenged
    assert "no_real_investigation_performed" not in report.limits
    assert engine.calls["controlled_investigation"] == 1
    audit_prompts = list((tmp_path / "prompt_audit" / "controlled_investigation").glob("*.prompt.txt"))
    assert audit_prompts
    prompt = audit_prompts[0].read_text(encoding="utf-8")
    assert "[M1]" in prompt
    assert "实际利率仍高" in prompt


def test_real_investigation_challenge_creates_downgrade_record(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    base = CompetingHypothesis(
        hypothesis_id="hyp_base",
        hypothesis_text="主线解释",
        support_evidence_refs=["L1.get_fed_funds_rate"],
        diagnostic_evidence_refs=["L1.get_fed_funds_rate"],
        falsification_conditions=["利率回落"],
    )
    report = InvestigationReport(
        originating_agent_id="agent_real",
        is_deterministic_stub=False,
        finding="材料挑战单一路径。",
        evidence_refs=["layer_cards/L1.json"],
        claims_challenged=["高利率必然压低指数"],
        cannot_establish=["价格方向"],
        effective_date="2026-07-14",
    )

    records = orchestrator._build_adjudication_change_records(
        base_hypothesis=base,
        counter_hypotheses=[],
        investigation_reports=[report],
        fallback_warnings=[],
        effective_date="2026-07-14",
    )

    assert records
    assert records[0].change_type == "kept_unresolved"
    assert records[0].trigger_evidence_refs == ["layer_cards/L1.json"]


def test_real_investigation_propagates_through_bridge_and_hypothesis_competition(
    tmp_path: Path,
    monkeypatch,
):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    report = InvestigationReport(
        originating_agent_id="agent_real",
        is_deterministic_stub=False,
        finding="材料挑战单一路径 [M1]。",
        evidence_refs=["layer_cards/L1.json"],
        claims_challenged=["高利率必然压低指数 [M1]"],
        cannot_establish=["价格方向仍不能确认 [M1]"],
        effective_date="2026-07-14",
    )
    bridge_v1 = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        principal_contradiction={
            "contradiction_id": "rates_vs_valuation",
            "summary": "高利率与高估值并存。",
            "why_principal": "决定估值承压程度。",
            "dominant_side": "利率约束。",
            "secondary_side": "盈利韧性。",
            "price_reflection": "partially_reflected",
            "evidence_refs": ["L1.get_fed_funds_rate"],
        },
        implication_for_ndx="保留争议。",
    )
    router_output = orchestrator_module.InquiryRouterOutput()

    bridge_v2 = orchestrator._build_bridge_v2(
        packet_model=_mock_packet(),
        layer_cards=[],
        bridge_v1=bridge_v1,
        router_output=router_output,
        investigation_reports=[report],
    )

    assert bridge_v2.investigation_effects[0]["is_deterministic_stub"] is False
    assert bridge_v2.feedback_loop_summary["changed_judgment_count"] == 1
    assert "价格方向仍不能确认 [M1]" in bridge_v2.key_uncertainties

    counter = CompetingHypothesis(
        hypothesis_id="hyp_counter",
        hypothesis_text="反方解释：价格可能已部分反映压力。",
        source="counter_thesis",
        support_evidence_refs=["L1.get_fed_funds_rate"],
        diagnostic_evidence_refs=["L1.get_fed_funds_rate"],
        falsification_conditions=["价格反映证据转弱。"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_build_counter_thesis",
        lambda **_: CounterThesisDraft(hypotheses=[counter]),
    )

    competition = orchestrator._build_hypothesis_competition(
        synthesis_packet=SynthesisPacket(
            evidence_index={"L1.get_fed_funds_rate": {"evidence_ref": "L1.get_fed_funds_rate"}}
        ),
        bridge_v2=bridge_v2,
        investigation_reports=[report],
        effective_date="2026-07-14",
    )

    assert competition.downgrade_or_split_events
    assert competition.downgrade_or_split_events[0].trigger_evidence_refs == ["layer_cards/L1.json"]


def test_controlled_investigation_two_failures_fall_back_to_stub(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    engine = SequencedFakeLLMEngine(
        {"controlled_investigation": ["not-json", '{"finding": "missing required shape"}']}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    spec, message = _controlled_investigation_inputs(tmp_path)

    report = orchestrator._build_investigation_report(spec, message)

    assert report.is_deterministic_stub is True
    assert "llm_investigation_failed_fell_back_to_stub" in report.limits
    assert engine.calls["controlled_investigation"] == 2


def test_controlled_investigation_rejects_forbidden_ref_in_assembly(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    spec, message = _controlled_investigation_inputs(tmp_path)
    spec.allowed_context_refs.append("final_adjudication.json")

    with pytest.raises(ValueError, match="forbidden_context_ref"):
        orchestrator._build_investigation_report(spec, message)


def test_controlled_investigation_disabled_preserves_stub_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "0")
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    spec, message = _controlled_investigation_inputs(tmp_path)

    report = orchestrator._build_investigation_report(spec, message)

    assert report.is_deterministic_stub is True
    assert "no_real_investigation_performed" in report.limits
    assert "llm_investigation_failed_fell_back_to_stub" not in report.limits


def test_controlled_investigation_wraps_single_list_field_without_rewriting_content(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    response = json.dumps(
        {
            "finding": "材料不足，无法确认方向 [M1]。",
            "claims_supported": [],
            "claims_challenged": [],
            "counter_evidence_refs": [],
            "cannot_establish": ["缺少价格材料 [M1]"],
            "confidence": "low",
            "limits": "仅依据 [M1]",
        },
        ensure_ascii=False,
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=SequencedFakeLLMEngine({"controlled_investigation": response}),
    )
    spec, message = _controlled_investigation_inputs(tmp_path)

    report = orchestrator._build_investigation_report(spec, message)

    assert report.is_deterministic_stub is False
    assert report.limits[0] == "仅依据 [M1]"


def test_controlled_investigation_flattens_claim_material_pair_to_contract_string(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    response = json.dumps(
        {
            "finding": "材料确认约束仍在 [M1]。",
            "claims_supported": [{"claim": "实际利率约束仍在", "material_ref": "[M1]"}],
            "claims_challenged": [],
            "counter_evidence_refs": [],
            "cannot_establish": ["不能确认价格方向 [M1]"],
            "confidence": "medium",
            "limits": ["仅依据 [M1]"],
        },
        ensure_ascii=False,
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=SequencedFakeLLMEngine({"controlled_investigation": response}),
    )
    spec, message = _controlled_investigation_inputs(tmp_path)

    report = orchestrator._build_investigation_report(spec, message)

    assert report.claims_supported == ["实际利率约束仍在 [M1]"]


def test_controlled_investigation_retries_then_falls_back_when_material_citations_missing(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    response = json.dumps(
        {
            "finding": "材料不足，无法确认方向。",
            "claims_supported": [],
            "claims_challenged": [],
            "counter_evidence_refs": [],
            "cannot_establish": ["缺少价格材料"],
            "confidence": "low",
            "limits": ["仅依据给定材料"],
        },
        ensure_ascii=False,
    )
    engine = SequencedFakeLLMEngine({"controlled_investigation": response})
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    spec, message = _controlled_investigation_inputs(tmp_path)
    second_artifact = tmp_path / "layer_cards" / "L2.json"
    second_artifact.write_text('{"risk_flags": ["信用分层"]}', encoding="utf-8")
    spec.allowed_context_refs.append("layer_cards/L2.json")

    report = orchestrator._build_investigation_report(spec, message)

    assert report.is_deterministic_stub is True
    assert "llm_investigation_failed_fell_back_to_stub" in report.limits
    assert engine.calls["controlled_investigation"] == 2


def test_controlled_investigation_single_material_citation_normalization_is_audited(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    response = json.dumps(
        {
            "finding": "唯一材料只能确认利率约束。",
            "claims_supported": ["实际利率约束仍在"],
            "claims_challenged": [],
            "counter_evidence_refs": [],
            "cannot_establish": ["不能确认价格方向"],
            "confidence": "low",
            "limits": ["仅依据唯一材料"],
        },
        ensure_ascii=False,
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=SequencedFakeLLMEngine({"controlled_investigation": response}),
    )
    spec, message = _controlled_investigation_inputs(tmp_path)

    report = orchestrator._build_investigation_report(spec, message)

    assert report.finding.endswith("[M1]")
    assert report.claims_supported == ["实际利率约束仍在 [M1]"]
    assert report.cannot_establish == ["不能确认价格方向 [M1]"]
    assert report.normalization_notes == [
        "single_material_citation_normalized_to_M1:finding,claims_supported[0],cannot_establish[0]"
    ]


def test_controlled_investigation_multi_material_absence_scope_is_audited(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    second_artifact = tmp_path / "layer_cards" / "L2.json"
    second_artifact.parent.mkdir(parents=True, exist_ok=True)
    second_artifact.write_text('{"risk_flags": ["信用分层"]}', encoding="utf-8")
    response = json.dumps(
        {
            "finding": "两份材料都不足以确认价格方向 [M1][M2]。",
            "claims_supported": [],
            "claims_challenged": [],
            "counter_evidence_refs": [],
            "cannot_establish": ["缺少价格序列，不能确认方向"],
            "confidence": "low",
            "limits": ["仅依据两份材料"],
        },
        ensure_ascii=False,
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=SequencedFakeLLMEngine({"controlled_investigation": response}),
    )
    spec, message = _controlled_investigation_inputs(tmp_path)
    spec.allowed_context_refs.append("layer_cards/L2.json")

    report = orchestrator._build_investigation_report(spec, message)

    assert report.cannot_establish == ["缺少价格序列，不能确认方向 [M1][M2]"]
    assert report.normalization_notes == [
        "cannot_establish_absence_scope_normalized_to_all_materials:0"
    ]


def test_controlled_investigation_finding_uses_only_explicit_output_citation_union(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    second_artifact = tmp_path / "layer_cards" / "L2.json"
    second_artifact.parent.mkdir(parents=True, exist_ok=True)
    second_artifact.write_text('{"risk_flags": ["信用分层"]}', encoding="utf-8")
    response = json.dumps(
        {
            "finding": "两份材料给出相反线索。",
            "claims_supported": ["实际利率约束仍在 [M1]"],
            "claims_challenged": ["信用压力尚未扩散 [M2]"],
            "counter_evidence_refs": ["[M2]"],
            "cannot_establish": ["不能确认价格方向 [M1][M2]"],
            "confidence": "medium",
            "limits": ["仅依据两份材料"],
        },
        ensure_ascii=False,
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=SequencedFakeLLMEngine({"controlled_investigation": response}),
    )
    spec, message = _controlled_investigation_inputs(tmp_path)
    spec.allowed_context_refs.append("layer_cards/L2.json")

    report = orchestrator._build_investigation_report(spec, message)

    assert report.finding == "两份材料给出相反线索。 [M1][M2]"
    assert report.normalization_notes == [
        "finding_citations_normalized_from_explicit_output_refs:M1,M2"
    ]


def test_controlled_investigation_rejects_limits_that_deny_reported_numbers(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    response = json.dumps(
        {
            "finding": "材料只提供单条报道数字 [M1]。",
            "claims_supported": ["报道写明盘后上涨 10% [M1]"],
            "claims_challenged": [],
            "counter_evidence_refs": [],
            "cannot_establish": ["缺少后续价格序列 [M1]"],
            "confidence": "low",
            "limits": ["材料不包含实际市场数据，也未分析具体数字"],
        },
        ensure_ascii=False,
    )
    engine = SequencedFakeLLMEngine({"controlled_investigation": response})
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    spec, message = _controlled_investigation_inputs(tmp_path)
    artifact = tmp_path / "layer_cards" / "L1.json"
    artifact.write_text('{"event": "盘后上涨 10%"}', encoding="utf-8")

    report = orchestrator._build_investigation_report(spec, message)

    assert report.is_deterministic_stub is True
    assert "llm_investigation_failed_fell_back_to_stub" in report.limits
    assert engine.calls["controlled_investigation"] == 2


def test_controlled_investigation_evidence_refs_only_include_readable_json(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    response = json.dumps(
        {
            "finding": "可读材料只确认实际利率约束 [M1]。",
            "claims_supported": ["实际利率约束仍在 [M1]"],
            "claims_challenged": [],
            "counter_evidence_refs": [],
            "cannot_establish": ["缺少估值材料，不能确认方向 [M1]"],
            "confidence": "low",
            "limits": ["只读取可用材料"],
        },
        ensure_ascii=False,
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=SequencedFakeLLMEngine({"controlled_investigation": response}),
    )
    spec, message = _controlled_investigation_inputs(tmp_path)
    spec.allowed_context_refs.append("synthesis_packet.pending")

    report = orchestrator._build_investigation_report(spec, message)

    assert report.evidence_refs == ["layer_cards/L1.json"]
    assert [item.evidence_ref for item in report.source_authority] == ["layer_cards/L1.json"]


def test_controlled_investigation_marks_bridge_as_derived_unknown_authority(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )

    assert orchestrator._source_tier_for_allowed_ref("bridge_memos/bridge_0.json") == "unknown"
    assert orchestrator._source_tier_for_allowed_ref("synthesis_packet.pending") == "unknown"


def test_controlled_investigation_material_excerpt_limits_and_keyword_priority(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    refs = []
    for index in range(4):
        ref = f"layer_cards/L{index + 1}.json"
        path = tmp_path / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "rates_block": "实际利率约束" + "甲" * 6000,
                    "unrelated": "不相关材料" + "乙" * 6000,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        refs.append(ref)

    materials = orchestrator._read_allowed_context_notes(
        refs,
        max_refs=4,
        question="实际利率能确认什么？",
    )

    assert len(materials) == 3
    assert all(len(material) <= 4000 for material in materials)
    assert sum(map(len, materials)) <= 12000
    assert all("rates_block" in material for material in materials)
    assert all("unrelated" not in material for material in materials)
    assert [material.endswith(f"[/M{index}]") for index, material in enumerate(materials, 1)] == [
        True,
        True,
        True,
    ]


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


def test_field_authority_merge_uses_the_most_restrictive_usage(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    authority = orchestrator._field_authority_from_payload({
        "value": {"MetricAuthority": {"level": {"usage": "core_allowed", "authority": "official_fact"}}},
        "data_quality": {
            "metric_authority": {
                "level": {"usage": "supporting_only", "authority": "proxy_or_derived_observation"},
            },
        },
    })

    assert authority["level"]["usage"] == "supporting_only"
    assert authority["level"]["authority"] == "proxy_or_derived_observation"
    malformed = orchestrator._field_authority_from_payload({
        "value": {"MetricAuthority": {"mystery": {"usage": "super_core"}}},
    })
    assert malformed["mystery"]["usage"] == "audit_only"


def test_unavailable_evidence_passports_are_never_verified(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = _mock_packet()
    packet.raw_data["L2"] = {
        "get_vix": {
            "name": "VIX",
            "value": {"level": None},
            "data_quality": {
                "availability": "unavailable",
                "source_name": "CBOE via market-data provider",
                "source_tier": "official_provider",
                "effective_date": "2026-04-24",
                "metric_authority": {"level": {"usage": "supporting_only"}},
            },
        },
    }
    synthesis_packet = SynthesisPacket(
        packet_meta=packet.meta,
        evidence_index={
            "L2.get_vix": {
                "layer": "L2",
                "function_id": "get_vix",
                "permission_type": "fact",
            },
        },
        bridge_summaries=[],
    )

    registry = orchestrator._build_evidence_registry(
        packet_model=packet,
        synthesis_packet=synthesis_packet,
        investigation_reports=[],
        hypothesis_competition=HypothesisCompetition(hypotheses=[]),
    )

    assert registry.passports["L2.get_vix"].verified is False
    assert registry.passports["L2.get_vix#level"].verified is False
    assert "evidence_unavailable" in registry.passports["L2.get_vix"].downgrade_rules
    assert "evidence_value_missing" in registry.passports["L2.get_vix#level"].downgrade_rules


def test_evidence_registry_registers_exact_nested_state_variable_ref(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    packet = _mock_packet()
    packet.raw_data["L2"] = {
        "get_vix": {
            "value": {"level": 18.0, "historical_stats": {"percentile_10y": 0.72}},
            "data_quality": {
                "availability": "available",
                "source_name": "market data provider",
                "source_tier": "official_provider",
                "effective_date": "2026-04-24",
                "metric_authority": {"historical_stats": {"usage": "supporting_only"}},
            },
        },
    }
    synthesis = SynthesisPacket(
        packet_meta=packet.meta,
        evidence_index={"L2.get_vix": {"layer": "L2", "function_id": "get_vix", "permission_type": "fact"}},
        bridge_summaries=[],
    )

    registry = orchestrator._build_evidence_registry(
        packet_model=packet,
        synthesis_packet=synthesis,
        investigation_reports=[],
        hypothesis_competition=HypothesisCompetition(hypotheses=[]),
    )

    ref = "L2.get_vix#historical_stats.percentile_10y"
    assert ref in registry.passports
    assert registry.passports[ref].verified is True
    assert registry.passports[ref].authority_model["state_variable_key"] == "risk_appetite.vix_percentile_10y"


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
                evidence_refs=["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield", "known_data_gaps"],
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
        evidence_refs=["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield", "L5.get_ta_indicators"],
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
    # LLM 混入的说明性 token（如 known_data_gaps）应被剔除并记录，而不是冒充缺失证据去阻断发布。
    assert all("known_data_gaps" not in entry.evidence_refs for entry in ledger.entries)
    assert any(
        "known_data_gaps" in list(getattr(entry, "dropped_non_evidence_tokens", []) or [])
        for entry in ledger.entries
    )
    # 幻觉引用名若是某类 claim 唯一的同层证据，必须阻断该 claim；
    # 不能再用其他层的强证据为它“洗白”。
    assert any(entry.claim_type == "timing" and entry.authority_status == "blocked" for entry in ledger.entries)
    assert market_entry.authority_status != "blocked"
    assert ledger.publish_gate["status"] == "blocked"
    assert any("unverifiable_evidence_refs:L5.get_ta_indicators" in (entry.downgrade_reason or "") for entry in ledger.entries)
    assert any(entry.claim_type == "valuation" for entry in ledger.entries)
    assert any(entry.claim_type == "timing" for entry in ledger.entries)
    # layer_scope 放宽后：valuation claim 允许引用 L1（cross_validation_targets 里的
    # get_10y_real_rate 同类利率证据），但仍不能引用 L5（技术指标不能证明估值便宜）。
    valuation_entry = next(entry for entry in ledger.entries if entry.claim_type == "valuation")
    assert "L1.get_fed_funds_rate" in valuation_entry.evidence_refs
    assert "L5.get_ta_indicators" not in valuation_entry.evidence_refs


def test_field_authority_is_persisted_and_applied_per_claimed_wind_metric(tmp_path: Path):
    field_authority = {
        "PE": {"usage": "core_allowed", "authority": "licensed_provider_wind_index_fundamentals"},
        "PB": {"usage": "core_allowed", "authority": "licensed_provider_wind_index_fundamentals"},
        "RiskPremium": {"usage": "supporting_only", "authority": "provider_label_definition_unverified"},
        "ForwardPE": {"usage": "supporting_only", "authority": "synthetic_supporting_for_test"},
        "EarningsYield": {"usage": "core_allowed", "authority": "synthetic_core_for_test"},
        "PS": {"usage": "rejected", "authority": "synthetic_rejected_for_test"},
    }
    packet = AnalysisPacketBuilder().build(
        {
            "timestamp_utc": "2026-07-10T00:00:00Z",
            "indicators": [
                {
                    "layer": 4,
                    "metric_name": "Wind NDX Valuation and Risk Premium Snapshot",
                    "function_id": "get_ndx_wind_valuation_snapshot",
                    "raw_data": {
                        "name": "Wind NDX Valuation and Risk Premium Snapshot",
                        "value": {
                            "PE": 35.2,
                            "PB": 10.3,
                            "PS": 7.4,
                            "ForwardPE": 31.0,
                            "EarningsYield": 2.84,
                            "RiskPremium": 1.1,
                            "MetricAuthority": field_authority,
                        },
                        "source_tier": "licensed_provider/Wind",
                        "source_name": "Wind index_data.get_index_fundamentals",
                    },
                    "error": None,
                    "collection_timestamp_utc": "2026-07-10T00:00:01Z",
                }
            ],
        },
        manual_overrides={"active": False, "metrics": {}},
    )
    evidence_ref = "L4.get_ndx_wind_valuation_snapshot"
    synthesis_packet = SynthesisPacket(
        packet_meta=packet.meta,
        evidence_index={
            evidence_ref: {
                "layer": "L4",
                "function_id": "get_ndx_wind_valuation_snapshot",
                "canonical_question": "NDX 估值与风险补偿处于什么位置？",
                "permission_type": "fact",
                "source_tier": "licensed_provider/Wind",
            }
        },
        bridge_summaries=[],
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    registry = orchestrator._build_evidence_registry(
        packet_model=packet,
        synthesis_packet=synthesis_packet,
        investigation_reports=[],
        hypothesis_competition=HypothesisCompetition(),
    )
    generated_synthesis = orchestrator._build_synthesis_packet(
        packet,
        ContextBrief(data_summary="synthetic", task_description="field authority test"),
        [
            LayerCard(
                layer="L4",
                core_facts=[CoreFact(metric="Wind NDX Valuation", value=35.2)],
                local_conclusion="仅测试字段级证据引用。",
                confidence=Confidence.MEDIUM,
                indicator_analyses=[
                    IndicatorAnalysis(
                        function_id="get_ndx_wind_valuation_snapshot",
                        metric="Wind NDX Valuation and Risk Premium Snapshot",
                        current_reading="Wind PE 35.2。",
                        narrative="仅测试字段级证据引用。",
                        reasoning_process="读取显式字段后按字段权限引用。",
                        evidence_refs=[f"{evidence_ref}#PE"],
                    )
                ],
            )
        ],
        [],
    )

    parent_passport = registry.passports[evidence_ref]
    assert parent_passport.authority_model["field_authority"] == field_authority
    assert parent_passport.authority_model["mixed_field_authority"] is True
    assert parent_passport.verified is False
    assert "mixed_field_authority" in parent_passport.downgrade_rules
    assert registry.passports[f"{evidence_ref}#PE"].authority_model["field_usage"] == "core_allowed"
    assert registry.passports[f"{evidence_ref}#PB"].authority_model["field_usage"] == "core_allowed"
    assert registry.passports[f"{evidence_ref}#PS"].authority_model["field_usage"] == "rejected"
    assert registry.passports[f"{evidence_ref}#RiskPremium"].authority_model["field_usage"] == "supporting_only"
    assert generated_synthesis.evidence_index[evidence_ref]["mixed_field_authority"] is True
    assert generated_synthesis.evidence_index[f"{evidence_ref}#PE"]["field_authority"]["usage"] == "core_allowed"

    def verify(claim_text: str, refs: list[str]) -> ClaimLedgerEntry:
        return orchestrator._verify_claim_entry(
            ClaimLedgerEntry(
                claim_id="claim:test:" + str(len(claim_text)),
                source_stage="final",
                claim_text=claim_text,
                claim_type="valuation",
                evidence_refs=refs,
                counter_evidence_refs=["counter:test"],
                inference_steps=["字段级权限检查"],
                falsification_conditions=["字段口径被重新核验"],
            ),
            registry,
        )

    for parent_claim_text in [
        "NDX 估值昂贵。",
        "Wind PE（市盈率）为 35.2 倍。",
        "Wind ForwardPE 为 31 倍。",
        "Wind EarningsYield 为 2.84%。",
    ]:
        parent_claim = verify(parent_claim_text, [evidence_ref])
        assert parent_claim.authority_status == "downgraded"
        assert "mixed_field_authority_parent_ref" in parent_claim.downgrade_reason
        assert parent_claim.evidence_field_refs == []

    pe_claim = verify("Wind PE（市盈率）为 35.2 倍。", [f"{evidence_ref}#PE"])
    risk_premium_claim = verify(
        "Wind RiskPremium（风险溢价）为 1.1。",
        [f"{evidence_ref}#RiskPremium"],
    )
    rejected_ps_claim = verify("Wind PS（市销率）为 7.4 倍。", [f"{evidence_ref}#PS"])

    assert pe_claim.authority_status == "verified"
    assert pe_claim.evidence_field_refs == [f"{evidence_ref}#PE"]
    assert risk_premium_claim.authority_status == "downgraded"
    assert "field_authority_supporting_only" in risk_premium_claim.downgrade_reason
    assert risk_premium_claim.evidence_field_refs == [f"{evidence_ref}#RiskPremium"]
    assert rejected_ps_claim.authority_status == "blocked"
    assert "field_authority_rejected" in rejected_ps_claim.downgrade_reason
    assert rejected_ps_claim.evidence_field_refs == [f"{evidence_ref}#PS"]
    assert orchestrator._validate_stage_evidence_refs(
        RefStageModel(evidence_refs=[f"{evidence_ref}#PE"]),
        set(registry.passports),
        "final",
    ) == []


def _claim_gate_test_registry() -> EvidenceRegistry:
    """工单#13 claim gate 稳定化测试专用的最小注册表：两条独立强证据（official/licensed_provider，
    无字段限权）+ 一条真实复现过方差的弱字段引用（third-party proxy tier、field_usage=validation_only，
    对齐 u1_experiment_baseline_r2 实跑数据里的 L4.get_ndx_pe_and_earnings_yield#EarningsYield）+
    两条纯弱证据（供"只有弱证据"回归锚点测试用）。"""
    return EvidenceRegistry(
        effective_date="2026-07-10",
        passports={
            "L1.get_10y_real_rate": EvidencePassport(
                evidence_id="L1.get_10y_real_rate",
                evidence_kind="data",
                source_tier="official",
                verified=True,
            ),
            "L4.get_equity_risk_premium": EvidencePassport(
                evidence_id="L4.get_equity_risk_premium",
                evidence_kind="data",
                source_tier="licensed_provider",
                verified=True,
            ),
            "L4.get_ndx_pe_and_earnings_yield#EarningsYield": EvidencePassport(
                evidence_id="L4.get_ndx_pe_and_earnings_yield#EarningsYield",
                evidence_kind="data",
                source_tier="proxy",
                authority_model={
                    "parent_evidence_ref": "L4.get_ndx_pe_and_earnings_yield",
                    "field_name": "EarningsYield",
                    "field_usage": "validation_only",
                },
                verified=True,
            ),
            "L5.get_adx_qqq": EvidencePassport(
                evidence_id="L5.get_adx_qqq",
                evidence_kind="data",
                source_tier="derived_inference",
                verified=True,
            ),
            "L5.get_qqq_technical_indicators": EvidencePassport(
                evidence_id="L5.get_qqq_technical_indicators",
                evidence_kind="data",
                source_tier="proxy",
                verified=True,
            ),
        },
    )


def _claim_gate_test_orchestrator(tmp_path: Path) -> VNextOrchestrator:
    return VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )


def test_claim_gate_stable_across_llm_ref_citation_variants(tmp_path: Path):
    """工单#13 核心验收：同一份判断，两次 LLM 措辞只差"是否顺带多引用一条 validation_only
    交叉校验字段"，verified 结果必须一致——修复前这一差异会把 verified 从 True 翻成 False
    （对齐 u1 基线三连 7/8、1/8、7/8 与 P5 复现出的方差）。"""
    orchestrator = _claim_gate_test_orchestrator(tmp_path)
    registry = _claim_gate_test_registry()

    def build_entry(evidence_refs: list[str]) -> ClaimLedgerEntry:
        return ClaimLedgerEntry(
            claim_id="claim:test:variant-" + str(len(evidence_refs)),
            source_stage="final",
            claim_text="NDX 当前估值偏贵，实际利率高位对折现率构成压力。",
            claim_type="valuation",
            evidence_refs=evidence_refs,
            counter_evidence_refs=["L1.get_10y_real_rate"],
            inference_steps=["估值与利率交叉校验"],
            falsification_conditions=["实际利率显著回落"],
        )

    # "run A" 措辞：只引用两条强证据。
    run_a = orchestrator._verify_claim_entry(
        build_entry(["L1.get_10y_real_rate", "L4.get_equity_risk_premium"]), registry
    )
    # "run B" 措辞：内容判断完全相同，只是顺带多引用了一条弱字段做交叉校验。
    run_b = orchestrator._verify_claim_entry(
        build_entry(
            [
                "L1.get_10y_real_rate",
                "L4.get_equity_risk_premium",
                "L4.get_ndx_pe_and_earnings_yield#EarningsYield",
            ]
        ),
        registry,
    )

    assert run_a.verified is True
    assert run_b.verified is True, run_b.downgrade_reason
    assert run_a.authority_status == run_b.authority_status == "verified"

    # 同一份输入反复跑 5 次，逐次结果必须完全一致（方差=0）。
    entry = build_entry(
        ["L1.get_10y_real_rate", "L4.get_equity_risk_premium", "L4.get_ndx_pe_and_earnings_yield#EarningsYield"]
    )
    replays = [orchestrator._verify_claim_entry(entry, registry) for _ in range(5)]
    signatures = {(r.verified, r.authority_status, r.downgrade_reason) for r in replays}
    assert len(signatures) == 1, replays


def test_claim_gate_regression_only_weak_evidence_still_downgrades(tmp_path: Path):
    """回归锚点：真正的孤证（只有弱/代理证据、没有任何独立强证据）必须仍然被抓住并降级——
    对齐 20260712_221916 E2E run 里 price_reflection claim 只引用 L5 技术指标被判
    only_weak_or_derived_evidence_refs 的真实命中。稳定化不能放松这条真实校验。"""
    orchestrator = _claim_gate_test_orchestrator(tmp_path)
    registry = _claim_gate_test_registry()
    entry = ClaimLedgerEntry(
        claim_id="claim:test:weak-only",
        source_stage="thesis",
        claim_text="价格已经反映了短期技术面走弱。",
        claim_type="price_reflection",
        evidence_refs=["L5.get_adx_qqq", "L5.get_qqq_technical_indicators"],
        counter_evidence_refs=["L5.get_adx_qqq"],
        inference_steps=["技术面读数"],
        falsification_conditions=["动能指标反转"],
    )
    result = orchestrator._verify_claim_entry(entry, registry)
    assert result.verified is False
    assert "only_weak_or_derived_evidence_refs" in result.downgrade_reason
    assert result.authority_status == "downgraded"


def test_claim_gate_regression_field_authority_weak_ref_alone_still_downgrades(tmp_path: Path):
    """孤证变体：唯一引用就是那条 validation_only 字段（没有任何独立强证据同框）时，
    比例原则不应该豁免它——field_authority 检查必须仍然生效。"""
    orchestrator = _claim_gate_test_orchestrator(tmp_path)
    registry = _claim_gate_test_registry()
    entry = ClaimLedgerEntry(
        claim_id="claim:test:field-only",
        source_stage="final",
        claim_text="盈利收益率显示估值偏贵。",
        claim_type="valuation",
        evidence_refs=["L4.get_ndx_pe_and_earnings_yield#EarningsYield"],
        counter_evidence_refs=["L1.get_10y_real_rate"],
        inference_steps=["盈利收益率交叉校验"],
        falsification_conditions=["盈利收益率回升"],
    )
    result = orchestrator._verify_claim_entry(entry, registry)
    assert result.verified is False
    assert "field_authority_validation_only" in result.downgrade_reason


def test_claim_gate_normalizes_evidence_ref_case_whitespace_and_hash_spacing(tmp_path: Path):
    """规范化边界：LLM 写出的 ref 大小写、首尾/内部空白、"# " 间距变体都必须能解析到同一条
    registry 证据，不能被误判成"引用不存在"；但真正的笔误/幻觉引用名不能被规范化洗白。"""
    orchestrator = _claim_gate_test_orchestrator(tmp_path)
    registry = _claim_gate_test_registry()
    entry = ClaimLedgerEntry(
        claim_id="claim:test:normalization",
        source_stage="final",
        claim_text="实际利率高位叠加估值贵，风险溢价偏低。",
        claim_type="valuation",
        evidence_refs=[
            "  L1.get_10y_real_rate  ",  # 首尾空白
            "l4.get_equity_risk_premium",  # 大小写变体
            "L4.get_ndx_pe_and_earnings_yield #EarningsYield",  # "#" 前多余空格
            "L1.get_10y_real_rate_typo",  # 真笔误，不应被规范化救回
        ],
        counter_evidence_refs=["L1.get_10y_real_rate"],
        inference_steps=["规范化匹配测试"],
        falsification_conditions=["占位失效条件"],
    )
    result = orchestrator._verify_claim_entry(entry, registry)
    # 唯一应该出现在"无法核验"清单里的只有真笔误；三条格式变体都必须成功解析到规范 key。
    assert result.downgrade_reason.count("unverifiable_evidence_refs:") == 1
    unverifiable_section = result.downgrade_reason.split("unverifiable_evidence_refs:", 1)[1].split("；", 1)[0]
    assert unverifiable_section.split(",") == ["L1.get_10y_real_rate_typo"]
    # 规范化后应解析为规范 key 形式（紧凑、大小写与 registry 一致）。
    assert "L4.get_ndx_pe_and_earnings_yield#EarningsYield" in result.evidence_field_refs


def test_stage5_golden_pit_checklist_defers_cross_run_diff_even_if_previous_exists(tmp_path: Path):
    previous_dir = tmp_path / "20260706_000000"
    current_dir = tmp_path / "20260707_000000"
    previous_dir.mkdir()
    previous_payload = {
        "entries": [
            {
                "condition_id": "buy_value_discount_confirmed",
                "condition": "价值买入纪律",
                "current_status": "met",
            }
        ]
    }
    (previous_dir / "golden_pit_checklist.json").write_text(json.dumps(previous_payload), encoding="utf-8")
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(current_dir),
        llm_engine=FakeLLMEngine({}),
    )
    ledger = ClaimLedger(
        effective_date="2026-07-07",
        entries=[
            ClaimLedgerEntry(
                claim_id="claim:thesis:valuation",
                source_stage="thesis",
                claim_text="估值安全垫仍不足。",
                claim_type="valuation",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
                counter_evidence_refs=["L1.get_10y_real_rate"],
                inference_steps=["估值仍需要利率和盈利确认。"],
                falsification_conditions=["估值分位明显回落。"],
                verified=True,
                authority_status="verified",
            ),
            ClaimLedgerEntry(
                claim_id="claim:thesis:timing",
                source_stage="thesis",
                claim_text="趋势尚未破坏。",
                claim_type="timing",
                evidence_refs=["L5.get_qqq_technical_indicators"],
                counter_evidence_refs=["L3.get_ndx_ndxe_ratio"],
                inference_steps=["价格趋势仍在。"],
                falsification_conditions=["趋势跌破关键均线。"],
                verified=True,
                authority_status="verified",
            ),
            ClaimLedgerEntry(
                claim_id="claim:final:risk",
                source_stage="final",
                claim_text="风险边界仍需保留。",
                claim_type="risk_boundary",
                evidence_refs=["L1.get_10y_real_rate"],
                counter_evidence_refs=["L5.get_qqq_technical_indicators"],
                inference_steps=["高利率约束估值容错。"],
                falsification_conditions=["真实利率快速回落。"],
                verified=True,
                authority_status="verified",
            ),
        ],
    )
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="中性偏谨慎。",
        confidence=Confidence.MEDIUM,
        key_support_chains=[],
        must_preserve_risks=["风险边界仍需保留。"],
        blocking_issues=[],
        adjudicator_notes="保留条件式结论。",
        state_diagnosis="估值未到黄金坑，趋势未坏。",
    )
    # 显式构造档案：测试不得依赖仓库 config/user_decision_profile.json 的全局状态。
    profile = UserDecisionProfile(
        configuration_status="configured",
        buy_disciplines=[
            UserDecisionCondition(
                condition_id="buy_value_discount_confirmed",
                side="buy",
                label="价值买入纪律",
                discipline="估值安全垫、风险边界和时机证据同时可追问时，黄金坑才是候选。",
                required_claim_types=["valuation", "risk_boundary", "timing"],
            )
        ],
        sell_disciplines=[],
    )

    checklist = orchestrator._build_golden_pit_checklist(
        final_claim_ledger=ledger,
        decision_profile=profile,
        final_adjudication=final,
        effective_date="2026-07-07",
    )

    assert isinstance(checklist, GoldenPitChecklist)
    assert checklist.previous_checklist_ref == ""
    assert "暂缓" in checklist.changed_since_last_run_summary[0]
    assert any(item.condition_id == "buy_value_discount_confirmed" for item in checklist.entries)
    buy_item = next(item for item in checklist.entries if item.condition_id == "buy_value_discount_confirmed")
    assert buy_item.current_status == "not_met"
    assert buy_item.changed_since_last_run["changed"] is False
    assert buy_item.changed_since_last_run["status"] == "deferred_until_run_quality_stable"
    assert "暂缓" in buy_item.changed_since_last_run["summary"]
    assert "must not feed back" in checklist.no_backflow_rule


def test_stage5_profile_conditions_use_metric_predicates_before_claim_text_fallback(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    ledger = ClaimLedger(
        effective_date="2026-07-07",
        entries=[
            ClaimLedgerEntry(
                claim_id="claim:thesis:valuation",
                source_stage="thesis",
                claim_text="估值安全垫仍不足。",
                claim_type="valuation",
                evidence_refs=["L4.get_ndx_pe_and_earnings_yield"],
                counter_evidence_refs=["L1.get_10y_real_rate"],
                inference_steps=["估值仍偏高。"],
                falsification_conditions=["估值分位明显回落。"],
                verified=True,
                authority_status="verified",
            )
        ],
    )
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="中性偏谨慎。",
        confidence=Confidence.MEDIUM,
        key_support_chains=[],
        must_preserve_risks=[],
        blocking_issues=[],
        adjudicator_notes="保留条件式结论。",
    )
    profile = UserDecisionProfile(
        configuration_status="configured",
        buy_disciplines=[
            UserDecisionCondition(
                condition_id="buy_metric_value_zone",
                side="buy",
                label="估值买入区",
                discipline="按台账变量判断。",
                required_claim_types=["valuation"],
                metric_predicates={
                    "logic": "all_of",
                    "predicates": [{
                        "var": "valuation.forward_pe",
                        "op": "<=",
                        "value": 20,
                        "unit": "pe_multiple",
                        "threshold_status": "confirmed",
                    }],
                },
            )
        ],
        sell_disciplines=[
            UserDecisionCondition(
                condition_id="sell_text_fallback",
                side="sell",
                label="旧兜底",
                discipline="没有谓词时才读 claim 文本。",
                required_claim_types=["valuation"],
            )
        ],
    )

    checklist = orchestrator._build_golden_pit_checklist(
        final_claim_ledger=ledger,
        decision_profile=profile,
        final_adjudication=final,
        effective_date="2026-07-07",
        state_variables={"valuation.forward_pe": 18.5},
    )

    metric_item = next(item for item in checklist.entries if item.condition_id == "buy_metric_value_zone")
    fallback_item = next(item for item in checklist.entries if item.condition_id == "sell_text_fallback")
    assert metric_item.current_status == "met"
    assert metric_item.status_method == "metric_predicates"
    assert metric_item.status_evidence["results"][0]["actual"] == 18.5
    assert fallback_item.status_method == "claim_text_fallback"


def test_profile_predicate_uses_only_its_state_variable_evidence_ref(tmp_path: Path):
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))
    ledger = ClaimLedger(
        effective_date="2026-07-17",
        entries=[ClaimLedgerEntry(
            claim_id="claim:valuation",
            source_stage="final",
            claim_text="估值条件式观察。",
            claim_type="valuation",
            evidence_refs=["L4.get_ndx_pe_and_earnings_yield", "L1.get_10y_real_rate"],
            counter_evidence_refs=[],
            inference_steps=["条件式。"],
            falsification_conditions=["另一条并不属于该谓词的失效条件。"],
            verified=True,
            authority_status="verified",
        )],
    )
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="条件式。",
        confidence=Confidence.MEDIUM,
        key_support_chains=[], must_preserve_risks=[], blocking_issues=[], adjudicator_notes="",
    )
    profile = UserDecisionProfile(configuration_status="configured", buy_disciplines=[UserDecisionCondition(
        condition_id="forward_pe_zone",
        side="buy",
        label="远期估值区",
        discipline="只按远期市盈率判断。",
        required_claim_types=["valuation"],
        metric_predicates={"logic": "all_of", "predicates": [{
            "var": "valuation.forward_pe", "op": "<=", "value": 20,
            "unit": "pe_multiple", "threshold_status": "confirmed",
        }]},
    )])

    checklist = orchestrator._build_golden_pit_checklist(
        final_claim_ledger=ledger,
        decision_profile=profile,
        final_adjudication=final,
        effective_date="2026-07-17",
        state_variables={"valuation.forward_pe": 19.0},
    )
    item = next(entry for entry in checklist.entries if entry.condition_id == "forward_pe_zone")

    assert item.evidence_refs == ["L4.get_ndx_pe_and_earnings_yield#ForwardPE"]
    assert "L1.get_10y_real_rate" not in item.evidence_refs
    assert item.falsification_conditions == ["若 valuation.forward_pe 不再满足 <= 20 pe_multiple，则该条件失效。"]


def test_derived_profile_predicate_cites_every_raw_input(tmp_path: Path):
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))
    condition = UserDecisionCondition(
        condition_id="drawdown_zone",
        side="buy",
        label="回撤区",
        discipline="按通道回撤观察。",
        required_claim_types=["timing"],
        metric_predicates={"predicates": [{
            "var": "trend.drawdown_from_donchian_upper_pct",
            "op": ">=", "value": 5.0, "unit": "percent", "threshold_status": "confirmed",
        }]},
    )

    refs, _ = orchestrator._predicate_refs_and_falsifiers(condition)

    assert refs == [
        "L5.get_donchian_channels_qqq#upper",
        "L5.get_multi_scale_ma_position#current_price",
    ]


def test_profile_predicate_fails_closed_when_registered_evidence_is_unverified(tmp_path: Path):
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))
    ref = "L4.get_ndx_pe_and_earnings_yield#ForwardPE"
    registry = EvidenceRegistry(
        effective_date="2026-07-17",
        passports={ref: EvidencePassport(
            evidence_id=ref,
            evidence_kind="data",
            source_tier="licensed_provider",
            verified=False,
            downgrade_rules=["evidence_unavailable"],
        )},
    )
    profile = UserDecisionProfile(configuration_status="configured", buy_disciplines=[UserDecisionCondition(
        condition_id="forward_pe_zone",
        side="buy",
        label="远期估值区",
        discipline="只按远期市盈率判断。",
        required_claim_types=["valuation"],
        metric_predicates={"predicates": [{
            "var": "valuation.forward_pe", "op": "<=", "value": 20,
            "unit": "pe_multiple", "threshold_status": "confirmed",
        }]},
    )])
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="条件式。", confidence=Confidence.MEDIUM,
        key_support_chains=[], must_preserve_risks=[], blocking_issues=[], adjudicator_notes="",
    )

    checklist = orchestrator._build_golden_pit_checklist(
        final_claim_ledger=ClaimLedger(effective_date="2026-07-17", entries=[]),
        decision_profile=profile,
        final_adjudication=final,
        effective_date="2026-07-17",
        state_variables={"valuation.forward_pe": 18.0},
        evidence_registry=registry,
    )
    item = next(entry for entry in checklist.entries if entry.condition_id == "forward_pe_zone")

    assert item.current_status == "insufficient_evidence"
    assert item.status_method == "evidence_registry_gate"
    assert item.status_evidence["unverified_predicate_refs"] == [ref]


def test_unconfirmed_or_wrong_unit_profile_threshold_fails_closed(tmp_path: Path):
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))

    unconfirmed, _ = orchestrator._evaluate_metric_predicates(
        {"predicates": [{"var": "valuation.forward_pe", "op": "<=", "value": 20, "unit": "pe_multiple", "threshold_status": "unconfirmed"}]},
        {"valuation.forward_pe": 18.0},
    )
    wrong_unit, details = orchestrator._evaluate_metric_predicates(
        {"predicates": [{"var": "valuation.forward_pe", "op": "<=", "value": 20, "unit": "percent", "threshold_status": "confirmed"}]},
        {"valuation.forward_pe": 18.0},
    )

    assert unconfirmed == "insufficient_evidence"
    assert wrong_unit == "insufficient_evidence"
    assert details["results"][0]["status"] == "unit_mismatch"


def test_empty_profile_is_explicitly_visible_in_reader_exit(tmp_path: Path):
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))
    final = FinalAdjudication(
        approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        final_stance="条件式。", confidence=Confidence.MEDIUM,
        key_support_chains=[], must_preserve_risks=[], blocking_issues=[], adjudicator_notes="",
    )
    checklist = orchestrator._build_golden_pit_checklist(
        final_claim_ledger=ClaimLedger(effective_date="2026-07-17", entries=[]),
        decision_profile=UserDecisionProfile(
            configuration_status="unconfigured",
            configuration_issues=["no_confirmed_buy_or_sell_disciplines"],
        ),
        final_adjudication=final,
        effective_date="2026-07-17",
        state_variables={},
    )

    item = next(entry for entry in checklist.entries if entry.condition_id == "profile_disciplines_unconfigured")
    assert item.current_status == "insufficient_evidence"
    assert item.status_method == "profile_configuration_gate"


def test_profile_adapter_whitelists_reader_exit_and_drops_private_amounts(tmp_path: Path):
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({}))
    profile = orchestrator._decision_profile_from_config_documents(
        {"reader_exit": {"configuration_status": "unconfigured", "buy_disciplines": [], "sell_disciplines": []}},
        {
            "net_worth_snapshot": {"approx_total_cny": 123456789},
            "buckets": {"liquidity": {"floor_cny": 987654}},
            "reader_exit": {"configuration_status": "unconfigured", "configuration_issues": ["awaiting_user_confirmation"]},
        },
    )
    dumped = profile.model_dump(mode="json")

    assert "net_worth_snapshot" not in dumped
    assert "buckets" not in dumped
    assert "123456789" not in json.dumps(dumped)
    assert "987654" not in json.dumps(dumped)


def test_event_section_summary_validator_enforces_citation_and_boundary_contract():
    from agent_analysis.contracts import EventSectionSummary
    from agent_analysis.orchestrator import VNextOrchestrator

    validate = VNextOrchestrator._event_section_summary_validation_errors
    allowed = {"event_aaa11111", "event_bbb22222", "event_ccc33333"}
    body = "据报道，本轮事件围绕利率预期与AI资本开支展开，事件材料给数据层提出了利率路径与盈利确认两类问题，" \
        "官方纪要与媒体报道相互补充但均需数据确认，材料质量以标题为主、正文有限，解读均以据报道口径降档处理。"

    good = EventSectionSummary(
        summary_text=f"{body} [card:event_aaa11111] [card:event_bbb22222]以上事件材料不构成主证据，判断以数据层为准。",
        cited_event_ids=["event_aaa11111", "event_bbb22222"],
    )
    assert validate(good, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=True) == []

    # 引用声明与正文不一致
    mismatch = good.model_copy(update={"cited_event_ids": ["event_aaa11111"]})
    assert any("exactly match" in err for err in validate(mismatch, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=True))

    # 引用了本轮不存在的卡
    foreign = EventSectionSummary(
        summary_text=f"{body} [card:event_zzz99999] [card:event_aaa11111]以上事件材料不构成主证据，判断以数据层为准。",
        cited_event_ids=["event_zzz99999", "event_aaa11111"],
    )
    assert any("outside this run" in err for err in validate(foreign, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=True))

    # 缺结尾边界句
    unbounded = EventSectionSummary(
        summary_text=f"{body} [card:event_aaa11111] [card:event_bbb22222]",
        cited_event_ids=["event_aaa11111", "event_bbb22222"],
    )
    assert any("boundary sentence" in err for err in validate(unbounded, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=True))

    # 越权引用 L1-L5 数据 ref
    leaking = EventSectionSummary(
        summary_text=f"{body} L1.get_10y_real_rate [card:event_aaa11111] [card:event_bbb22222]以上事件材料不构成主证据，判断以数据层为准。",
        cited_event_ids=["event_aaa11111", "event_bbb22222"],
    )
    assert any("L1-L5" in err for err in validate(leaking, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=True))

    # codex P1 修复：多数材料仅标题时，总结必须诚实声明质量限制
    body_no_caveat = "据报道，本轮事件围绕利率预期与AI资本开支展开，两条重要新闻分别涉及美联储表态和芯片出口管制，" \
        "两者均可能影响科技股估值方向，具体传导路径仍需后续数据确认。"
    no_caveat = EventSectionSummary(
        summary_text=f"{body_no_caveat} [card:event_aaa11111] [card:event_bbb22222]以上事件材料不构成主证据，判断以数据层为准。",
        cited_event_ids=["event_aaa11111", "event_bbb22222"],
    )
    assert validate(no_caveat, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=False) == []
    assert any(
        "quality limitation" in err
        for err in validate(no_caveat, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=True)
    )

    # codex P1 修复：绝不能把 effective_date 之后的日期写进历史总结（事后信息回流）
    future_leak = EventSectionSummary(
        summary_text=f"{body} 后续在 2026-07-25 得到证实 [card:event_aaa11111] [card:event_bbb22222]以上事件材料不构成主证据，判断以数据层为准。",
        cited_event_ids=["event_aaa11111", "event_bbb22222"],
    )
    assert any(
        "beyond effective_date" in err
        for err in validate(future_leak, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=True)
    )

    # 少数仅标题/弱来源卡也必须在自己的引用附近降级，不能靠“未过半”逃过全局规则。
    weak_without_attribution = EventSectionSummary(
        summary_text=(
            "某事件必然改变市场定价，另一事件提供补充线索，具体传导仍待数据确认。"
            " [card:event_aaa11111] [card:event_bbb22222]"
            "以上事件材料不构成主证据，判断以数据层为准。"
        ),
        cited_event_ids=["event_aaa11111", "event_bbb22222"],
    )
    errors = validate(
        weak_without_attribution,
        allowed_ids=allowed,
        effective_date="2026-07-19",
        title_only_majority=False,
        downgrade_required_ids={"event_aaa11111"},
    )
    assert any("downgrade-required card" in err for err in errors)

    attributed = weak_without_attribution.model_copy(update={
        "summary_text": (
                "据报道，某事件可能改变市场定价，另一事件提供补充线索；据报道，两张卡共同提出了政策路径、"
            "盈利兑现与风险偏好能否同步变化的问题，但这些都只是待数据确认的线索，不能据此推导指数方向。"
            " [card:event_aaa11111] [card:event_bbb22222]"
            "以上事件材料不构成主证据，判断以数据层为准。"
        )
    })
    assert validate(
        attributed,
        allowed_ids=allowed,
        effective_date="2026-07-19",
        title_only_majority=False,
        downgrade_required_ids={"event_aaa11111"},
    ) == []

    hindsight = attributed.model_copy(update={
        "summary_text": attributed.summary_text.replace("可能改变", "后来已得到确认并直接导致指数上涨，改变")
    })
    assert any(
        "hindsight or deterministic" in err
        for err in validate(
            hindsight,
            allowed_ids=allowed,
            effective_date="2026-07-19",
            title_only_majority=False,
            downgrade_required_ids={"event_aaa11111"},
        )
    )

    chinese_future_date = attributed.model_copy(update={
        "summary_text": attributed.summary_text.replace("政策路径", "2026年7月25日的后续结果与政策路径")
    })
    assert any(
        "beyond effective_date" in err
        for err in validate(
            chinese_future_date,
            allowed_ids=allowed,
            effective_date="2026-07-19",
            title_only_majority=False,
            downgrade_required_ids={"event_aaa11111"},
        )
    )

    slash_future_date = attributed.model_copy(update={
        "summary_text": attributed.summary_text.replace("政策路径", "2026/07/25 的后续结果与政策路径")
    })
    assert any(
        "beyond effective_date" in err
        for err in validate(
            slash_future_date,
            allowed_ids=allowed,
            effective_date="2026-07-19",
            title_only_majority=False,
            downgrade_required_ids={"event_aaa11111"},
        )
    )

    for wording in (
        "后续结果显示事件甲确实改变了市场定价",
        "据报道，事件甲直接导致估值重估并压低风险偏好",
    ):
        candidate = attributed.model_copy(update={
            "summary_text": (
                f"{wording}，另一事件仅提供待确认线索。 [card:event_aaa11111] [card:event_bbb22222]"
                "以上事件材料不构成主证据，判断以数据层为准。"
            )
        })
        assert any(
            "hindsight or deterministic" in err
            for err in validate(
                candidate,
                allowed_ids=allowed,
                effective_date="2026-07-19",
                title_only_majority=False,
                downgrade_required_ids={"event_aaa11111"},
            )
        )

    attribution_only_in_prior_sentence = attributed.model_copy(update={
        "summary_text": (
            "据报道，第一张卡只提供待确认线索。第二张弱来源卡被写成确定事实"
            " [card:event_aaa11111] [card:event_bbb22222]"
            "以上事件材料不构成主证据，判断以数据层为准。"
        )
    })
    assert any(
        "downgrade-required card" in err
        for err in validate(
            attribution_only_in_prior_sentence,
            allowed_ids=allowed,
            effective_date="2026-07-19",
            title_only_majority=False,
            downgrade_required_ids={"event_aaa11111", "event_bbb22222"},
        )
    )

    ascii_boundary_bypass = attributed.model_copy(update={
        "summary_text": (
            "据报道，第一张卡只供参考 [card:event_aaa11111]. "
            "第二张弱来源卡被写成确定事实 [card:event_bbb22222]"
            "以上事件材料不构成主证据，判断以数据层为准。"
        )
    })
    assert any(
        "downgrade-required card" in err
        for err in validate(
            ascii_boundary_bypass,
            allowed_ids=allowed,
            effective_date="2026-07-19",
            title_only_majority=False,
            downgrade_required_ids={"event_aaa11111", "event_bbb22222"},
        )
    )

    for wording in ("后续结果\n显示事件甲改变市场定价", "据报道，事件甲直接\n导致估值重估"):
        cross_line = attributed.model_copy(update={
            "summary_text": (
                f"{wording}，另一事件仅提供待确认线索。 [card:event_aaa11111] [card:event_bbb22222]"
                "以上事件材料不构成主证据，判断以数据层为准。"
            )
        })
        assert any(
            "hindsight or deterministic" in err
            for err in validate(
                cross_line,
                allowed_ids=allowed,
                effective_date="2026-07-19",
                title_only_majority=False,
                downgrade_required_ids={"event_aaa11111"},
            )
        )

    for wording in ("据报道，随后指数上涨", "据报道，此后市场\n走弱"):
        hindsight_market_move = attributed.model_copy(update={
            "summary_text": (
                f"{wording}，但这一反应仍需正式数据核验。 [card:event_aaa11111] [card:event_bbb22222]"
                "以上事件材料不构成主证据，判断以数据层为准。"
            )
        })
        assert any(
            "hindsight or deterministic" in err
            for err in validate(
                hindsight_market_move,
                allowed_ids=allowed,
                effective_date="2026-07-19",
                title_only_majority=False,
                downgrade_required_ids={"event_aaa11111"},
            )
        )
