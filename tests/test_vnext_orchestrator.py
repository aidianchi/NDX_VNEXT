import json
import os
import sys
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import BaseModel, Field, ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4
from agent_analysis.contracts import (
    AgentBudget,
    AgentSpec,
    AnalysisPacket,
    AnalysisRevised,
    ApprovalStatus,
    BridgeMemo,
    ClaimLedger,
    ClaimLedgerEntry,
    CompetingHypothesis,
    Confidence,
    Conflict,
    ContextBrief,
    CoreFact,
    CounterThesisDraft,
    Critique,
    EvidencePassport,
    EvidenceRegistry,
    EventInterpretationCard,
    EventSectionSummary,
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


def _event_interpretation_card_for_summary(event_id: str) -> EventInterpretationCard:
    """T36 event_section_summary 测试共用的最小合法 EventInterpretationCard 构造器。"""
    return EventInterpretationCard.model_validate(
        {
            "event_id": event_id,
            "fact_summary": "材料事实。",
            "interpretation": "该事件可能通过折现率渠道影响纳指100估值。",
            "event_type": "official_calendar",
            "mechanism_hypothesis": {
                "financial_link": "discount_rate",
                "hypothesis": "该事件可能通过折现率渠道影响纳指100估值。",
            },
            "limitations": ["事件材料不能证明指数必须涨跌。"],
            "passport": {
                "source": "Federal Reserve",
                "tier": "official",
                "published_at": "2026-07-31T18:00:00Z",
                "event_date": "2026-07-31",
                "effective_date": "2026-07-31",
            },
        }
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
            # 本用例的本意是"等价说法也要接受"。2026-07-30 起措辞不再受任何检查，
            # 本用例因此退化为"等价说法不会被别的规则误伤"的守门。
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



def test_event_card_validator_rejects_signed_number_reversal(tmp_path: Path):
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

    # 2026-07-30：归因措辞检查已删（措辞由代码渲染保证），本用例只守带符号数字方向。
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


def _oversized_constituent_list(count: int = 20) -> list:
    """真实事故复现：全成分逐票明细（如盈利修正的 constituents/flagged/invalid），
    每条都带一个唯一标记，方便断言"没在样本里的那条被砍掉了"。"""
    return [
        {
            "ticker": f"TICK{i:03d}",
            "weight_pct": 1.23,
            "slope": 0.045,
            "unique_marker": f"UNIQUE_ROW_MARKER_{i:03d}",
        }
        for i in range(count)
    ]


def _mini_synthesis_packet_dict_for_slimming_test() -> dict:
    big_list = _oversized_constituent_list()
    return {
        "packet_meta": {"data_date": "2026-07-25"},
        "context_summary": "数据日期 2026-07-25。",
        "layer_summaries": [{"layer": "L4", "local_conclusion": "估值偏高。", "confidence": "medium"}],
        "bridge_summaries": [{"bridge_type": "feedback_bridge_v2", "implication_for_ndx": "综合影响。"}],
        "high_severity_conflicts": [
            {
                "conflict_type": "L4_expensive_vs_L5_strong_trend",
                "severity": "high",
                "description": "冲突描述。",
                "implication": "对判断的影响。",
                "involved_layers": ["L4", "L5"],
            }
        ],
        "high_severity_typed_conflicts": [
            {
                "conflict_id": "c1",
                "conflict_type": "valuation_discount_rate",
                "severity": "high",
                "description": "冲突描述。",
                "implication": "对判断的影响。",
            }
        ],
        "principal_contradictions": [{"contradiction_id": "pc1", "summary": "主要矛盾。"}],
        "competing_hypotheses": [
            {
                "hypothesis_id": "hyp_1",
                "hypothesis_text": "反方假说。",
                "source": "counter_thesis",
                "status": "candidate",
            }
        ],
        "hypothesis_competition_summary": {"schema_version": "hypothesis_competition_v1", "hypothesis_count": 1},
        "adjudication_history": [{"version_id": "adj_1", "change_type": "kept_unresolved"}],
        "counter_thesis_boundary": {"input_refs": ["synthesis_packet.json"], "independence_verified": True},
        "objective_firewall_summary": {"object_clear": True, "authority_clear": True},
        "evidence_index": {
            "L4.get_ndx_pe_and_earnings_yield": {
                "layer": "L4",
                "function_id": "get_ndx_pe_and_earnings_yield",
                "metric": "NDX PE",
                "narrative": "估值叙事。",
            },
            "L4.get_ndx_earnings_revision_metrics#slope_30d": {
                "layer": "L4",
                "function_id": "get_ndx_earnings_revision_metrics",
                "field_name": "slope_30d",
                "field_value": {
                    "value": 0.040793811,
                    "unit": "decimal_change",
                    "coverage": {"included_constituents": 90, "total_constituents": 103},
                    "winsorized_weight_pct": 0.804847,
                    "constituents": big_list,
                },
            },
        },
        "event_index": {"event:demo": {"headline": "占位事件。"}},
        "evidence_registry_summary": {"schema_version": "evidence_registry_v1", "passport_count": 185},
        "synthesis_guidance": ["只能整合，不得重做指标分析。"],
    }


def test_thesis_prompt_drops_low_value_fields_and_keeps_required_ones(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    payload = {"synthesis_packet": _mini_synthesis_packet_dict_for_slimming_test()}

    sanitized = orchestrator._sanitize_prompt_payload("thesis", payload)
    sp = sanitized["synthesis_packet"]

    # 纯记账元数据：thesis_builder.md 从未要求过，只在 prompt 层丢弃
    for dropped_key in (
        "counter_thesis_boundary",
        "evidence_registry_summary",
    ):
        assert dropped_key not in sp, f"{dropped_key} should be dropped from the thesis prompt payload"

    # 2026-07-27 撤出丢弃清单：重复采样实验证明丢掉 hypothesis_competition_summary 会让
    # thesis 的 invalidation_conditions 从 [4,5,3] 稳定塌成 [2,2,2]（区间零重叠），因为
    # retained_disputes 正是"我哪里还不确定"——改判条件的原料。丢它只省 0.40% token。
    for retained_key in ("hypothesis_competition_summary", "adjudication_history"):
        assert retained_key in sp, (
            f"{retained_key} 必须保留在 thesis prompt 里：它承载未解决争议/降级审计链，"
            "丢弃只省 0.40% token 却系统性削弱改判条件（见 WORK_LOG 2026-07-27 重复采样实验）"
        )

    # thesis_builder.md「## 输入」重点字段清单 + 「对竞争假说的强制回应」：逐字段必须仍在
    for required_key in (
        "layer_summaries",
        "bridge_summaries",
        "high_severity_conflicts",
        "high_severity_typed_conflicts",
        "principal_contradictions",
        "competing_hypotheses",
        "objective_firewall_summary",
        "evidence_index",
        "event_index",
        "synthesis_guidance",
    ):
        assert required_key in sp, f"{required_key} must remain in the thesis prompt payload"

    # evidence_index 的 ref key 集合（含 #field 子 ref）逐字不变——两站的证据引用
    # 合法性校验完全依赖 key 是否存在
    assert set(sp["evidence_index"].keys()) == {
        "L4.get_ndx_pe_and_earnings_yield",
        "L4.get_ndx_earnings_revision_metrics#slope_30d",
    }

    # 聚合字段（value/coverage/winsorized_weight_pct）原样保留
    field_value = sp["evidence_index"]["L4.get_ndx_earnings_revision_metrics#slope_30d"]["field_value"]
    assert field_value["value"] == 0.040793811
    assert field_value["coverage"] == {"included_constituents": 90, "total_constituents": 103}
    assert field_value["winsorized_weight_pct"] == 0.804847

    # 超长逐票明细被压缩为 count+sample 摘要
    constituents = field_value["constituents"]
    assert constituents["_prompt_summary"] is True
    assert constituents["count"] == 20
    assert len(constituents["sample"]) == 3

    # 没进样本的那些行必须真的从 prompt 文本里消失，不是换了个位置藏起来
    serialized = json.dumps(sanitized, ensure_ascii=False)
    assert "UNIQUE_ROW_MARKER_010" not in serialized
    assert "UNIQUE_ROW_MARKER_000" in serialized  # 前 2 条样本之一
    assert "UNIQUE_ROW_MARKER_019" in serialized  # 末 1 条样本
    assert "L4.get_ndx_earnings_revision_metrics#slope_30d" in serialized


def test_counter_thesis_prompt_drops_evidence_registry_summary_and_slims_evidence_index(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    synthesis_dict = _mini_synthesis_packet_dict_for_slimming_test()
    # _counter_thesis_prompt_payload 已经在构造阶段 pop 掉这 4 个自我循环字段；
    # 这里模拟它构造完之后的样子，只验证 _sanitize_prompt_payload 的 counter_thesis 分支。
    for key in ("competing_hypotheses", "hypothesis_competition_summary", "adjudication_history", "counter_thesis_boundary"):
        synthesis_dict.pop(key, None)
    payload = {
        "synthesis_packet_without_self_reference": synthesis_dict,
        "bridge_v1_structure": [{"bridge_type": "bridge_v1", "implication_for_ndx": "占位。"}],
        "bridge_v2_feedback_summary": {"schema_version": "bridge_v2_feedback_summary_v1"},
        "non_stub_investigation_reports": [],
        "allowed_evidence_refs": [
            "L4.get_ndx_pe_and_earnings_yield",
            "L4.get_ndx_earnings_revision_metrics#slope_30d",
        ],
        "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
        "output_contract": "CounterThesisDraft",
    }

    sanitized = orchestrator._sanitize_prompt_payload("counter_thesis", payload)
    sp = sanitized["synthesis_packet_without_self_reference"]

    # counter_thesis.md「## 输入边界」清单也没要求它
    assert "evidence_registry_summary" not in sp

    # ref key 集合不变
    assert set(sp["evidence_index"].keys()) == {
        "L4.get_ndx_pe_and_earnings_yield",
        "L4.get_ndx_earnings_revision_metrics#slope_30d",
    }
    constituents = sp["evidence_index"]["L4.get_ndx_earnings_revision_metrics#slope_30d"]["field_value"]["constituents"]
    assert constituents["_prompt_summary"] is True
    assert constituents["count"] == 20

    # counter_thesis 独立性边界 / 证据合法性契约必须逐字不受影响
    assert sanitized["allowed_evidence_refs"] == payload["allowed_evidence_refs"]
    assert sanitized["forbidden_context_refs"] == payload["forbidden_context_refs"]
    assert sanitized["bridge_v1_structure"] == payload["bridge_v1_structure"]
    assert sanitized["bridge_v2_feedback_summary"] == payload["bridge_v2_feedback_summary"]
    assert sanitized["output_contract"] == "CounterThesisDraft"


def test_slim_long_list_for_prompt_only_compresses_lists_past_both_thresholds():
    big_list = _oversized_constituent_list(count=20)
    small_list = [{"ticker": "AAPL", "weight_pct": 7.7}, {"ticker": "MSFT", "weight_pct": 6.5}]

    slimmed_big = VNextOrchestrator._slim_long_list_for_prompt(big_list)
    assert isinstance(slimmed_big, dict)
    assert slimmed_big["_prompt_summary"] is True
    assert slimmed_big["count"] == 20
    sampled_markers = {item["unique_marker"] for item in slimmed_big["sample"]}
    assert sampled_markers == {"UNIQUE_ROW_MARKER_000", "UNIQUE_ROW_MARKER_001", "UNIQUE_ROW_MARKER_019"}

    # 短列表不满足条数阈值，原样透传
    slimmed_small = VNextOrchestrator._slim_long_list_for_prompt(small_list)
    assert slimmed_small == small_list


def test_slim_evidence_index_for_prompt_keeps_aggregates_and_only_compresses_lists(tmp_path: Path):
    """C2-A 口径锁定：field_value 键不得整删，聚合字段逐字节不变，只有超长列表被压成摘要。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    payload = {"synthesis_packet": _mini_synthesis_packet_dict_for_slimming_test()}

    sanitized = orchestrator._slim_evidence_index_for_prompt(payload, "synthesis_packet")
    sp = sanitized["synthesis_packet"]

    # A 档：ref key 集合（含 parent#field 子 ref）压缩前后完全一致
    assert set(sp["evidence_index"].keys()) == {
        "L4.get_ndx_pe_and_earnings_yield",
        "L4.get_ndx_earnings_revision_metrics#slope_30d",
    }

    child_ref = "L4.get_ndx_earnings_revision_metrics#slope_30d"
    # A 档：field_value 键仍然存在（键不得整删）
    assert "field_value" in sp["evidence_index"][child_ref]
    field_value = sp["evidence_index"][child_ref]["field_value"]

    # 聚合字段逐字节不变
    assert field_value["value"] == 0.040793811
    assert field_value["unit"] == "decimal_change"
    assert field_value["coverage"] == {"included_constituents": 90, "total_constituents": 103}

    # 超长列表被压成 {"_prompt_summary": True, "count": ..., "sample": ..., "note": ...} 形态
    constituents = field_value["constituents"]
    assert isinstance(constituents, dict)
    assert constituents["_prompt_summary"] is True
    assert constituents["count"] == 20
    assert len(constituents["sample"]) == 3
    assert "note" in constituents


def test_run_thesis_end_to_end_prompt_file_omits_oversized_constituent_rows(tmp_path: Path):
    """端到端：经过真实 _run_stage / _compose_prompt 落到磁盘的 prompt 文本里，
    没进样本的逐票明细行必须真的消失，而不是只在单元测试里裁过一次。"""
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-07-25"},
        evidence_index={
            "L4.get_ndx_pe_and_earnings_yield": {"layer": "L4", "narrative": "估值叙事。"},
            "L4.get_ndx_earnings_revision_metrics#slope_30d": {
                "layer": "L4",
                "field_name": "slope_30d",
                "field_value": {
                    "value": 0.0408,
                    "coverage": {"included_constituents": 90},
                    "constituents": _oversized_constituent_list(),
                },
            },
        },
        competing_hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_1",
                hypothesis_text="反方假说。",
                source="counter_thesis",
                status="candidate",
            )
        ],
    )
    valid_response = {
        "environment_assessment": "环境评估。",
        "valuation_assessment": "估值评估。",
        "timing_assessment": "择时评估。",
        "main_thesis": "主论点。",
        "hypothesis_responses": [
            {
                "hypothesis_id": "hyp_1",
                "verdict": "absorb_partially",
                "reasoning": "部分吸收该假说。",
                "evidence_refs": [],
            }
        ],
        "overall_confidence": "medium",
    }
    engine = FakeLLMEngine({"thesis": json.dumps(valid_response, ensure_ascii=False)})
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine)

    orchestrator._run_thesis(synthesis)

    prompt_text = (tmp_path / "prompt_audit" / "thesis" / "attempt_1.prompt.txt").read_text(encoding="utf-8")
    assert "UNIQUE_ROW_MARKER_010" not in prompt_text
    assert "UNIQUE_ROW_MARKER_000" in prompt_text
    assert "L4.get_ndx_earnings_revision_metrics#slope_30d" in prompt_text
    assert "0.0408" in prompt_text


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
    # B6：指标清单不再重复供给 data_quality（完整块只在 Runtime Input 一份）。
    assert '"data_quality"' not in manifest_text
    assert "large_rows" not in manifest_text
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
                # T28：本次全链条 fake run 的两条竞争假说都以 kept_unresolved 落地
                # （无受控调查挑战但 counter_thesis 走确定性兜底触发 fallback_warnings，
                # 见 `_build_adjudication_change_records`），扩大后的触发集合要求逐一
                # 回应；id 由 `_stable_hypothesis_id` 对本测试固定的假说文本取哈希，
                # 是确定性值，不是随机数。
                "hypothesis_responses": [
                    {
                        "hypothesis_id": "hyp_base_a6e6834ec0",
                        "verdict": "accept_and_revise",
                        "reasoning": "当前证据下仍以主线解释为主，采纳并保留监测项。",
                        "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
                    },
                    {
                        "hypothesis_id": "hyp_counter_ee07162fa7",
                        "verdict": "absorb_partially",
                        "reasoning": "部分吸收反方观察，但仍缺少独立验证。",
                        "evidence_refs": ["L5.get_qqq_technical_indicators"],
                    },
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
    # counter_thesis 曾是唯一没接进检查点机制的叙事站：它用 _save_json 直接落盘，
    # manifest 里 stage_key / payload_sha256 都是 None，也没有 _load_stage_checkpoint。
    # 后果是一条缺失引发整条级联——续跑必然重跑反方 → 竞争假说变了 → thesis 的
    # expected_payload 指纹对不上 → thesis / reviser / final 跟着全部重跑并静默覆盖
    # 已产出的产物（真实事故 run 20260728_110702，首跑那批验收样本因此消失），
    # 与 `--resume-run-dir` 帮助文字里"verified stage checkpoints are reused"不符。
    # 本夹具没有注册 counter_thesis 响应，反方站必然走确定性兜底。兜底稿是降级产物、
    # 不是"已验证"结果，按设计**不得**被当检查点复用——所以这里断言的是"没被复用"，
    # 且 manifest 显式标了不可复用。成功路径的复用由
    # test_counter_thesis_checkpoint_is_reused_on_resume 覆盖。
    counter_checkpoint = json.loads(
        (tmp_path / "stage_manifest.json").read_text(encoding="utf-8")
    )["artifacts"]["counter_thesis.json"]
    assert counter_checkpoint["stage_key"] == "counter_thesis"
    assert len(counter_checkpoint["payload_sha256"]) == 64
    assert counter_checkpoint["checkpoint_reusable"] is False
    assert resumed_diagnostics["stages"]["counter_thesis"]["status"] != "resumed"
    # 兜底稿是确定性的，重跑产物一致 → 下游 payload 指纹不变 → thesis/reviser 仍能复用。
    assert resumed_diagnostics["stages"]["thesis"]["status"] == "resumed"
    assert resumed_diagnostics["stages"]["reviser"]["status"] == "resumed"


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
                # T28：本测试的两条竞争假说同样以 kept_unresolved 落地（counter_thesis
                # 走确定性兜底 → fallback_warnings 非空 → 全体降级），扩大后的触发集合
                # 要求逐一回应。id 由假说文本哈希确定性生成，与全链条测试同值。
                "hypothesis_responses": [
                    {
                        "hypothesis_id": "hyp_base_a6e6834ec0",
                        "verdict": "accept_and_revise",
                        "reasoning": "主线解释在当前证据下成立，采纳并保留监测项。",
                        "evidence_refs": ["L1.get_fed_funds_rate"],
                    },
                    {
                        "hypothesis_id": "hyp_counter_ee07162fa7",
                        "verdict": "absorb_partially",
                        "reasoning": "部分吸收反方观察，张力未解决。",
                        "evidence_refs": ["L1.get_fed_funds_rate"],
                    },
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


def test_layer_manual_overrides_inactive_carries_no_date_key(tmp_path: Path):
    """PC-12/B5：未启用的手工配置连 date 键都不进各层 payload（空串占位同样是
    占位痕迹）；2026-08-17 确认跑实测五层全红于 date=''。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = _mock_packet()

    for layer in ("L1", "L2", "L3", "L4", "L5"):
        overrides = orchestrator._build_layer_manual_overrides(packet, layer)
        assert overrides["active"] is False
        assert "date" not in overrides


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


def _schema_guard_conflict_case(tmp_path: Path, thesis_conflict: dict):
    """桥给一条 high 冲突，正方用自己的措辞重述它——只有编号能认亲。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    bridge = BridgeMemo.model_validate(
        {
            "bridge_type": "macro_valuation",
            "layers_connected": ["L1", "L4"],
            "typed_conflicts": [
                {
                    "conflict_id": "T1_real_rate_valuation_tension",
                    "conflict_type": "rate_vs_valuation",
                    "severity": "high",
                    "description": "L1 实际利率极端高位，L4 估值分位仅中位。",
                    "implication": "估值压缩风险未被定价。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": ["L1.get_fed_funds_rate"],
                }
            ],
            "implication_for_ndx": "保留张力。",
        }
    )
    return orchestrator._run_schema_guard(
        _mock_packet(),
        [],
        [bridge],
        ThesisDraft.model_validate(
            {
                "environment_assessment": "环境偏紧。",
                "valuation_assessment": "估值偏高。",
                "timing_assessment": "趋势待确认。",
                "main_thesis": "测试。",
                "retained_conflicts": [thesis_conflict],
                "overall_confidence": "medium",
            }
        ),
        Critique.model_validate({"overall_assessment": "测试。", "revision_direction": "测试。"}),
        RiskBoundaryReport.model_validate({"must_preserve_risks": ["测试风险"]}),
    )


def test_schema_guard_matches_retained_conflict_by_upstream_conflict_id(tmp_path: Path):
    """红灯：真实 run 20260728_222759——闸门谎报"高严重度冲突被抹平"，冲突其实一条没丢。

    `Conflict` 契约当时**根本没有 conflict_id 字段**，闸门只能拿 `conflict_type` 认亲；
    而正方本来就该用自己的话重述冲突，它把桥的 `rate_vs_valuation` 写成
    `real_rate_vs_valuation`，一词之差即判丢失。语义兜底是 `_normalize_conflict_text`
    的逐字相等，遇到改写必然失效——也就是说，只要正方好好干活（改写而非复制），
    闸门就会误报。

    这条误报比一般 bug 更危险：它往"系统抹平了跨层冲突"这个方向说谎，而"冲突是资产"
    是本项目的常驻边界之一。照着它去"修"正方，修的是一个不存在的病。

    修法是把编号通道补上（契约加 conflict_id + 说明书要求原样沿用 + 闸门两侧对称取
    {conflict_id, conflict_type} 并集），而不是放宽闸门。
    """
    report = _schema_guard_conflict_case(
        tmp_path,
        {
            "conflict_id": "T1_real_rate_valuation_tension",
            # 类型名与描述都被正方改写过——这是它该做的事，不该因此被判丢失。
            "conflict_type": "real_rate_vs_valuation",
            "severity": "high",
            "description": "L1 实际利率 2.43% 处 10 年 99.6 分位，L4 估值安全垫不足。",
            "implication": "偏防守。",
            "involved_layers": ["L1", "L4"],
        },
    )

    joined = "\n".join(report.consistency_issues)
    assert "High severity conflicts missing" not in joined, (
        "正方已用 conflict_id 认领了这条高严重度冲突，闸门不得再报丢失"
    )


def test_schema_guard_flags_missing_conflict_id_as_possible_id_gap(tmp_path: Path):
    """编号真的没传下来时仍要报警，但必须说清"可能只是编号没沿用"。

    "冲突被抹平"和"编号没传下来"后果天差地别，报错文案不区分，读的人就会误判。
    闸门本身不放宽——放宽等于拆掉"冲突是资产"这条边界的守卫。
    """
    report = _schema_guard_conflict_case(
        tmp_path,
        {
            "conflict_type": "real_rate_vs_valuation",
            "severity": "high",
            "description": "L1 实际利率极高，L4 估值安全垫不足。",
            "implication": "偏防守。",
            "involved_layers": ["L1", "L4"],
        },
    )

    joined = "\n".join(report.consistency_issues)
    assert "High severity conflicts missing" in joined
    assert "T1_real_rate_valuation_tension" in joined
    assert "无一条带 conflict_id" in joined, "必须提示这可能是编号缺失而非冲突丢失"


def test_event_section_summary_errors_carry_prefixed_citation_example(tmp_path: Path):
    """红灯：event_section_summary 连续四次真实 run 全灭（0725_145833 / 0725_232410 /
    0728_110702 / 0728_222759），每次都静默吞掉报告的"外部世界"整节。

    事件编号自带 `event:` 前缀，而引用写法是 `[card:<event_id>]`，拼起来是
    `[card:event:xxx]`——看着像重复前缀，模型本能地删掉一层。于是两条规则互相卡死：
    正文去前缀则与清单不一致；按重试反馈"两边必须一致"把清单也去掉前缀，又落到
    allowed_ids 之外。模型两次都不算错，它只是从没被告知编号真正长什么样。

    修法不是去前缀容错（那等于默许写错还把错误藏起来），而是让报错自带可执行示例，
    并在 payload 里直接给出现成的引用串供其原样抄写。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    allowed = {"event:3a4f8fe4369bd167", "event:4c46665e1c0dbd9e"}
    summary = EventSectionSummary.model_validate(
        {
            # 正文去掉了 event: 前缀，清单保留——真实 attempt 1 的原样复现。
            "summary_text": (
                "据报道，两则材料指向同一方向 [card:3a4f8fe4369bd167]，"
                "该媒体称另一则亦然 [card:4c46665e1c0dbd9e]。" + "补充说明。" * 30
                + "以上事件材料不构成主证据，判断以数据层为准。"
            ),
            "cited_event_ids": sorted(allowed),
        }
    )

    errors = orchestrator._event_section_summary_validation_errors(
        summary,
        allowed_ids=allowed,
        effective_date="2026-07-28",
        title_only_majority=False,
    )

    mismatch = next((e for e in errors if "cited_event_ids must exactly match" in e), "")
    assert mismatch, "正文与清单不一致时必须报错"
    assert "[card:event:3a4f8fe4369bd167]" in mismatch, (
        "报错必须给出带前缀的合法写法，否则模型只会把两边都改成错的那一边"
    )
    assert "3a4f8fe4369bd167" in mismatch and "event:3a4f8fe4369bd167" in mismatch, (
        "报错必须同时列出两侧差集，模型才知道该往哪边改"
    )


def test_event_section_summary_payload_hands_model_a_ready_made_citation(tmp_path: Path):
    """治本的一半：别让模型从 `[card:<event_id>]` 这个占位模式自己拼引用串。

    它一拼就会把 `event:` 前缀当成重复而删掉（见
    test_event_section_summary_errors_carry_prefixed_citation_example 的事故记录）。
    payload 里直接给出可原样抄写的完整串，猜的余地就没有了。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    def _card(event_id: str) -> EventInterpretationCard:
        return EventInterpretationCard.model_validate(
            {
                "event_id": event_id,
                "fact_summary": "材料事实。",
                "interpretation": "该事件可能通过折现率渠道影响纳指100估值。",
                "event_type": "official_calendar",
                "mechanism_hypothesis": {
                    "financial_link": "discount_rate",
                    "hypothesis": "该事件可能通过折现率渠道影响纳指100估值。",
                },
                "limitations": ["事件材料不能证明指数必须涨跌。"],
                "passport": {
                    "source": "Federal Reserve",
                    "tier": "official",
                    "published_at": "2026-07-28T18:00:00Z",
                    "event_date": "2026-07-28",
                    "effective_date": "2026-07-28",
                },
            }
        )

    captured: dict = {}

    def _capture(*, payload, **kwargs):
        captured["payload"] = payload
        raise RuntimeError("stop before llm call")

    orchestrator._run_stage = _capture
    orchestrator._build_event_section_summary(
        [_card("event:3a4f8fe4369bd167"), _card("event:4c46665e1c0dbd9e")],
        events_by_id={},
        effective_date="2026-07-28",
    )

    cards = captured["payload"]["event_cards"]
    assert [c["citation"] for c in cards] == [
        "[card:event:3a4f8fe4369bd167]",
        "[card:event:4c46665e1c0dbd9e]",
    ], "每张卡都要带一个可原样抄写的完整引用串"
    # B3 修复：output_contract 已从 payload 移除，引用规则并入 boundary.citation_rule。
    assert "output_contract" not in captured["payload"]
    assert "citation_rule" in captured["payload"]["boundary"]
    assert "不要删改 id" in captured["payload"]["boundary"]["citation_rule"]


def test_event_section_summary_payload_includes_needs_data_confirmation(tmp_path: Path):
    """T47 红灯：同一批事件卡，integrated_adjudicator 材料里每张都带
    needs_data_confirmation（契约 contracts.EventInterpretationCard 本就有此字段），
    event_section_summary 的 compact_cards 手工挑字段时漏了它（真实 run
    20260731_002156：adjudicator 10/10 张带、summary 0/10 张带）。
    总结模型要履行"如实说明哪些判断还缺正式数据确认"的提示词要求，
    就必须在输入材料里看得见这个字段；截断风格照 limitations（[:3]）。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    confirmations = {
        "event:aaa111": ["L1 联邦基金利率是否同步确认"],
        "event:bbb222": ["L4 盈利预期是否上修", "L2 信用利差是否走阔"],
        "event:ccc333": [],
        "event:ddd444": [f"待确认项{i}" for i in range(5)],
    }
    cards = [
        _event_interpretation_card_for_summary(event_id).model_copy(
            update={"needs_data_confirmation": needs}
        )
        for event_id, needs in confirmations.items()
    ]

    captured: dict = {}

    def _capture(*, payload, **kwargs):
        captured["payload"] = payload
        raise RuntimeError("stop before llm call")

    orchestrator._run_stage = _capture
    orchestrator._build_event_section_summary(
        cards,
        events_by_id={},
        effective_date="2026-07-31",
    )

    payload_cards = captured["payload"]["event_cards"]
    assert len(payload_cards) == len(confirmations)
    for payload_card in payload_cards:
        event_id = payload_card["event_id"]
        assert "needs_data_confirmation" in payload_card, (
            f"compact card {event_id} 缺 needs_data_confirmation 字段——"
            "总结模型看不到它就无法说明哪些判断还缺正式数据确认"
        )
        expected = confirmations[event_id][:3]
        assert payload_card["needs_data_confirmation"] == expected, (
            f"{event_id} 的 needs_data_confirmation 值必须原样透传（照 limitations "
            f"风格截断到前 3 条），期望 {expected}，实际 "
            f"{payload_card['needs_data_confirmation']}"
        )


# ---------------------------------------------------------------------------
# T36：event_section_summary 永不因 JSON 外壳解析失败而整节消失
#
# 病根（真实 run 20260731_002156，两次尝试均复现，原始响应见
# tests/fixtures/event_section_summary_20260731_002156_attempt1_unescaped_quote.raw.txt）：
# 模型在 summary_text 正文里写了未转义的半角双引号
# （`这为"AI投资究竟是价值破坏还是生产性资本支出"这一竞争假说`），json.loads 报
# `Expecting ',' delimiter`。旧代码把这类 parse_error 当作整站失败：
# `_build_event_section_summary` 的 except 分支返回 `(None, ...)`，报告里"外部世界"
# 整节消失，即使模型已经写出了完整、可读、正确引用了 5 张卡的正文。
#
# 修法不是继续加 JSON 语法容错（那治标不治本，任何新的转义/逃逸组合都能再复现一次），
# 而是釜底抽薪：cited_event_ids 本来就是从同一段正文里代码可以自己扫出来的重复劳动
# （模型已经在正文里内联写了 [card:event:xxx]，还要求它在清单里把同样的编号再抄一遍，
# 正是这份重复逼出了 JSON 外壳），删掉这项要求；再给"JSON 解析不出来"这一种失败模式
# （且仅此一种，不含内容违规）开一条兜底：原始文本直接当 summary_text 收下、编号照样
# 从文本里扫，照常渲染，但必须在产出里留痕降级、接上既有终审质量闸门标记"不作发布依据"。
# ---------------------------------------------------------------------------


def test_event_section_summary_extracts_cited_ids_from_inline_card_markers():
    """红灯覆盖点②：编号导出——正文含 [card:event:x] 标记，cited_event_ids 必须
    正确导出、去重、保序。这条独立于任何 LLM 调用，直接测试新增的提取工具函数。"""
    text = (
        "先引用一张 [card:event:aaa111]，再引用另一张 [card:event:bbb222]，"
        "随后重复提到第一张 [card:event:aaa111]（同一事件在正文里被提了两次）。"
    )
    ids = VNextOrchestrator._extract_cited_event_ids_from_text(text)
    assert ids == ["event:aaa111", "event:bbb222"], (
        "必须按首次出现顺序去重，不能丢单，也不能把重复引用算成两条"
    )


def test_event_section_summary_extracts_cited_ids_filters_by_allowed_ids_when_given():
    """`allowed_ids` 给定时只保留本轮真实存在的卡号——供降级兜底路径使用，
    防止未经身份校验的编号被当成合法索引收下。"""
    text = "[card:event:real1] [card:event:not_a_real_card] [card:event:real2]"
    ids = VNextOrchestrator._extract_cited_event_ids_from_text(
        text, allowed_ids={"event:real1", "event:real2"}
    )
    assert ids == ["event:real1", "event:real2"]


class _RawTextReplayFakeLLMEngine:
    """把真实捕获的原始响应文本原样重放给 `_run_stage`，`extract_json` 委托给真正的
    `LLMEngine.extract_json`（而不是玩具版 `json.loads`），这样 parse_error 的判定
    路径与生产环境逐字节一致——包括它"尝试轻量修复、修复不了就返回 None"的行为。
    """

    def __init__(self, raw_response: str):
        from agent_analysis.llm_engine import LLMEngine

        self.raw_response = raw_response
        self.token_usage = {"total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
        self._real_engine = LLMEngine(available_models=[])
        self.calls = 0

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None):
        self.calls += 1
        return self.raw_response

    def extract_json(self, text, stage):
        return self._real_engine.extract_json(text, stage)

    def get_token_report(self):
        return self.token_usage


def test_event_section_summary_survives_real_unescaped_quote_parse_error(tmp_path: Path):
    """红灯覆盖点①：真实复现。喂真实捕获的、带未转义半角双引号的响应（run
    20260731_002156，两次尝试均如此失败）进解析路径。

    改前：两次尝试都 parse_error 耗尽重试，`_build_event_section_summary` 返回
    `(None, "RuntimeError: ...")`——"外部世界"整节从报告消失。
    改后：拿到非空 `summary_text`（原始正文兜底）、从中扫出全部 5 个真实事件编号、
    `index_degraded` 留痕为 "parse_error"，且 `_build_event_section_summary` 的
    第二个返回值非空——不能被当作未受任何影响的正常产出。
    """
    raw_text = (
        Path(__file__).parent
        / "fixtures"
        / "event_section_summary_20260731_002156_attempt1_unescaped_quote.raw.txt"
    ).read_text(encoding="utf-8")

    # 确认这段夹具真的会让标准 json.loads 报未转义引号错——红灯前提不是凭空断言的。
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw_text)

    real_event_ids = [
        "event:b8f43b7603daa04c",
        "event:75be16e97675b582",
        "event:0a457426cdb8f17f",
        "event:3935663507f48598",
        "event:ef79ac6a9ed352a4",
    ]
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=_RawTextReplayFakeLLMEngine(raw_text),
    )
    cards = [_event_interpretation_card_for_summary(eid) for eid in real_event_ids]

    summary_dict, summary_failure = orchestrator._build_event_section_summary(
        cards, events_by_id={}, effective_date="2026-07-31",
    )

    assert summary_dict is not None, (
        "T36 之前：parse_error 耗尽重试后整节消失（summary_dict 是 None）。"
        "现在必须收到降级正文，而不是把整节判定为失败。"
    )
    assert summary_dict["summary_text"].strip(), "降级正文不能是空串"
    assert "AI投资究竟是价值破坏还是生产性资本支出" in summary_dict["summary_text"], (
        "降级正文必须是模型真实写出的原始内容，不能是代码拼的占位句"
    )
    assert set(summary_dict["cited_event_ids"]) == set(real_event_ids), (
        f"必须从原始正文里扫出全部 5 个真实事件编号，实际：{summary_dict['cited_event_ids']}"
    )
    assert summary_dict.get("index_degraded") == "parse_error", (
        "牙齿：走了降级路径必须在产出里写明降级原因"
    )
    assert summary_failure, "第二个返回值必须非空，标记这次调用受到了降级影响"
    # 兜底不能只做到"没丢内容"，还要做到"用户读得下去"：整段原始响应直接当正文收下，
    # 报告那一节会把 `{ "summary_text": …, "cited_event_ids": [ … ] }` 的花括号和字段名
    # 渲染给用户看。那是"收下了但没读懂"，满足了不拒收的字面、没满足它的目的。
    salvaged = summary_dict["summary_text"]
    assert not salvaged.lstrip().startswith("{"), f"降级正文不得以 JSON 外壳开头：{salvaged[:60]!r}"
    assert '"summary_text"' not in salvaged, "降级正文里不得残留字段名"
    assert "cited_event_ids" not in salvaged, "降级正文里不得残留后续字段的 JSON 结构"


def test_salvage_text_field_from_broken_json_never_becomes_a_new_rejection_point():
    """`_salvage_text_field_from_broken_json` 是降级路径里的降级路径——它自己绝不许失败。

    真实代价（run 20260731_002156）：外壳其实完好，只是正文里的未转义半角双引号把
    JSON 从第 2 行截断。捞正文靠的是形状（键名、引号、下一个键的起点），不理解内容；
    捞不出来时必须原样返回入参，否则这道兜底会变成新的拒收点，把刚救回来的内容又丢一次。
    """
    orchestrator_cls = VNextOrchestrator
    broken = '{\n  "summary_text": "他说"这话"很关键。\\n第二段。",\n  "cited_event_ids": [\n    "event:a"\n  ]\n}'
    salvaged = orchestrator_cls._salvage_text_field_from_broken_json(broken, "summary_text")
    assert salvaged.startswith("他说"), salvaged
    assert "cited_event_ids" not in salvaged, "下一个键之后的内容必须被截掉"
    assert "\n第二段。" in salvaged, "标准 JSON 转义（\\n）必须被还原成真实换行"

    # 三种捞不出来的情形，一律原样返回，绝不抛错、绝不返回空
    for pathological in ("这根本不是 JSON，就是一段普通中文正文", "", '{"other_field": "x"}'):
        assert orchestrator_cls._salvage_text_field_from_broken_json(
            pathological, "summary_text"
        ) == pathological, f"捞不出来时必须原样返回：{pathological!r}"


def test_event_section_summary_unknown_cited_id_still_rejected_end_to_end(tmp_path: Path):
    """红灯覆盖点③：身份比对没被放松。cited_event_ids 改为代码导出后，正文里写一个
    不在本轮 allowed_ids 里的编号，必须仍被判非法、不许放行——不能因为不再要求模型
    自报清单，就顺带放松了"引用必须能在本轮卡片里查到"这条身份校验。

    构造一个**能被正常 JSON 解析**、但正文引用了一个虚构编号的响应，两次尝试都如此
    （所以不会走 T36 新增的 parse_error 兜底——那条兜底只接 parse_error，这里测的正是
    它没有被滥用成"什么脏内容都放行"的后门）。预期：耗尽重试后仍然失败。
    """
    body = (
        "据报道，本轮材料围绕利率路径与AI资本开支两条主线展开，官方纪要与媒体转述"
        "相互补充，具体传导仍需数据层确认，材料质量以标题为主、正文有限。"
    )
    bad_response = json.dumps(
        {
            "summary_text": (
                f"{body} [card:event:real_card] [card:event:not_in_this_run]"
                "以上事件材料不构成主证据，判断以数据层为准。"
            ),
        },
        ensure_ascii=False,
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=UniformEventCardFakeLLMEngine(bad_response),
    )
    cards = [
        _event_interpretation_card_for_summary("event:real_card"),
        _event_interpretation_card_for_summary("event:another_real_card"),
    ]

    summary_dict, summary_failure = orchestrator._build_event_section_summary(
        cards, events_by_id={}, effective_date="2026-07-31",
    )

    assert summary_dict is None, (
        "代码导出 cited_event_ids 不能变成放松身份比对的后门：引用了本轮不存在的"
        "编号，必须仍然判失败，不能被 T36 的降级兜底悄悄放行"
        "（该兜底只接受 parse_error，这里是结构清楚的 contract_validation_error）"
    )
    assert summary_failure and "outside this run" in summary_failure, (
        f"失败原因应指向未知编号，而不是别的失败模式：{summary_failure}"
    )


def test_annotate_event_section_summary_degradation_appends_quality_note_and_marks_unpublishable(tmp_path: Path):
    """红灯覆盖点④：牙齿。走降级路径时必须在终审质量闸门留痕，让发布流程能看到
    "这节内容未经索引校验、不可作发布依据"这个信号——对齐 reviser_degraded_
    unrevised_thesis / counter_thesis_degraded_deterministic_fallback 已经在用的
    同一份 `final.quality_gate.notes` 机制（见 test_degraded_reviser_marks_final_
    quality_gate），不新造一套。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    def _final() -> FinalAdjudication:
        return FinalAdjudication(
            approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
            final_stance="中性偏谨慎",
            confidence=Confidence.MEDIUM,
            must_preserve_risks=["估值压缩风险"],
            adjudicator_notes="保留风险边界。",
        )

    final = _final()
    # 注：FinalAdjudication 有一条既有的 model_validator，reasoned_verdict 为空时会
    # 自动生成一条"判决正文缺失"的 quality_gate——这里不假设初始状态是 None，只验证
    # 降级信号被追加了进去，与既有备注共存（_append_final_quality_note 本就是追加语义）。
    baseline_notes = str(final.quality_gate.notes if final.quality_gate else "")
    assert "event_section_summary_index_degraded" not in baseline_notes

    degraded_cards_artifact = {
        "section_summary": {
            "summary_text": "……",
            "cited_event_ids": ["event:x"],
            "index_degraded": "parse_error",
        },
    }
    orchestrator._annotate_event_section_summary_degradation(final, degraded_cards_artifact)

    assert final.quality_gate is not None, "降级信号必须写入终审质量闸门，不能悄无声息"
    assert "event_section_summary_index_degraded:parse_error" in final.quality_gate.notes, (
        f"质量闸门备注必须点名降级原因，实际：{final.quality_gate.notes!r}"
    )

    # 反向对照：没有降级时不应该额外写入这条特定备注——不能把"总是留一条无意义的
    # 痕迹"误当成牙齿。
    clean_final = _final()
    orchestrator._annotate_event_section_summary_degradation(
        clean_final, {"section_summary": {"summary_text": "……", "cited_event_ids": ["event:x"]}}
    )
    clean_notes = str(clean_final.quality_gate.notes if clean_final.quality_gate else "")
    assert "event_section_summary_index_degraded" not in clean_notes, (
        "未走降级路径时不应该产生这条特定的质量闸门备注"
    )



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


def test_layer_indicator_manifest_drops_duplicate_data_quality(tmp_path: Path):
    # B6 修复：指标清单只列导航字段；data_quality 完整块只在 Runtime Input 一份。
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
    assert "data_quality" not in manifest[0]


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
        model_mode="default",  # 显式走 legacy 模式，单独验证 pro-first 路由表
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


def test_run_stage_uses_stage_model_routing_for_mechanical_stages(tmp_path: Path):
    """机械活儿站点（事件卡解读/事件汇总）路由表应 flash 优先、pro 作为失败降级，
    与判断脊梁站点（如 thesis，见上一条测试）pro 优先的顺序相反。"""
    engine = RoutingFakeLLMEngine({"event_card_interpreter": '{"value": "ok"}'})
    orchestrator = VNextOrchestrator(
        available_models=["deepseek-v4-flash", "deepseek-v4-pro"],
        output_dir=str(tmp_path),
        llm_engine=engine,
    )

    result = orchestrator._run_stage(
        stage_key="event_card_interpreter",
        stage_name="event_card_interpreter",
        model_cls=MiniStageModel,
        payload={"example": "payload"},
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert result.value == "ok"
    assert engine.preferred_models_by_call[0][0] == "deepseek-v4-flash"
    assert diagnostics["stages"]["event_card_interpreter"]["model_routing"]["preferred_models"][0] == "deepseek-v4-flash"
    assert diagnostics["stages"]["event_card_interpreter"]["model"] == "deepseek-v4-flash"


def test_run_stage_all_flash_mode_for_cognitive_stages(tmp_path: Path):
    """all_flash 模式下认知裁决站点（thesis）也应 flash 优先：
    用户诉求是"所有 Agent 全部走 Flash"，不能再让认知阶段默认抢跑 pro。"""
    engine = RoutingFakeLLMEngine({"thesis": '{"value": "ok"}'})
    orchestrator = VNextOrchestrator(
        available_models=["deepseek-v4-flash", "deepseek-v4-pro"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        model_mode="all_flash",
    )

    result = orchestrator._run_stage(
        stage_key="thesis",
        stage_name="thesis",
        model_cls=MiniStageModel,
        payload={"example": "payload"},
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert result.value == "ok"
    assert engine.preferred_models_by_call[0][0] == "deepseek-v4-flash"
    assert diagnostics["stages"]["thesis"]["model_routing"]["active_mode"] == "all_flash"
    assert diagnostics["stages"]["thesis"]["model_routing"]["preferred_models"][0] == "deepseek-v4-flash"
    assert diagnostics["stages"]["thesis"]["model"] == "deepseek-v4-flash"


def test_run_stage_default_mode_is_all_flash_per_owner_ruling(tmp_path: Path):
    """老板 08-16 裁（O8）：config 默认模式已切 all_flash——认知阶段 flash 优先，
    诊断里 active_mode 标记 all_flash，pro 只作失败兜底。"""
    engine = RoutingFakeLLMEngine({"thesis": '{"value": "ok"}'})
    orchestrator = VNextOrchestrator(
        available_models=["deepseek-v4-flash", "deepseek-v4-pro"],
        output_dir=str(tmp_path),
        llm_engine=engine,
    )

    orchestrator._run_stage(
        stage_key="thesis",
        stage_name="thesis",
        model_cls=MiniStageModel,
        payload={"example": "payload"},
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert engine.preferred_models_by_call[0][0] == "deepseek-v4-flash"
    assert diagnostics["stages"]["thesis"]["model_routing"]["active_mode"] == "all_flash"
    assert diagnostics["stages"]["thesis"]["model_routing"]["preferred_models"][0] == "deepseek-v4-flash"


def test_run_stage_all_flash_mode_via_env_var(tmp_path: Path, monkeypatch):
    """NDX_MODEL_MODE=all_flash 环境变量与显式传参等价，均可把认知阶段切到 flash 优先。"""
    monkeypatch.setenv("NDX_MODEL_MODE", "all_flash")
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
    assert engine.preferred_models_by_call[0][0] == "deepseek-v4-flash"
    assert diagnostics["stages"]["thesis"]["model_routing"]["active_mode"] == "all_flash"


def test_stage_model_routing_unknown_mode_falls_back_to_default(tmp_path: Path):
    """未注册的模式名回退到 default，不抛异常、不改变既有行为。"""
    engine = RoutingFakeLLMEngine({"thesis": '{"value": "ok"}'})
    orchestrator = VNextOrchestrator(
        available_models=["deepseek-v4-flash", "deepseek-v4-pro"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        model_mode="does_not_exist",
    )

    orchestrator._run_stage(
        stage_key="thesis",
        stage_name="thesis",
        model_cls=MiniStageModel,
        payload={"example": "payload"},
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert engine.preferred_models_by_call[0][0] == "deepseek-v4-pro"
    assert diagnostics["stages"]["thesis"]["model_routing"]["active_mode"] == "default"


class _StrictToolSchemaRecordingFakeLLMEngine(FakeLLMEngine):
    """记录 `call_with_fallback` 每次实际收到的 strict_tool_schema/strict_tool_name，
    用于验证 `_run_stage` 只在明确传入时才把它们递给引擎——绝大多数调用不传，
    行为必须和试点之前完全一致。"""

    def __init__(self, responses):
        super().__init__(responses)
        self.calls_kwargs: list = []

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None, **kwargs):
        self.calls_kwargs.append(kwargs)
        return self.responses[stage_name]


def test_run_stage_passes_strict_tool_schema_only_when_provided(tmp_path: Path):
    """DeepSeek strict function calling 试点（2026-07-26）的接线验证：
    - 不传 strict_tool_schema（绝大多数 stage 的真实调用方式）→ 引擎完全收不到
      这个关键字参数，调用形态与试点之前逐字节相同。
    - 传了 strict_tool_schema → 引擎收到 schema 和 tool 名（未指定时有默认名）。
    """
    engine = _StrictToolSchemaRecordingFakeLLMEngine(
        {"critic": '{"value": "ok"}', "bridge": '{"value": "ok"}'}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )

    orchestrator._run_stage(
        stage_key="critic", stage_name="critic", model_cls=MiniStageModel, payload={}
    )
    assert "strict_tool_schema" not in engine.calls_kwargs[-1]
    assert "strict_tool_name" not in engine.calls_kwargs[-1]

    schema = {"type": "object", "properties": {}, "additionalProperties": False, "required": []}
    orchestrator._run_stage(
        stage_key="bridge",
        stage_name="bridge",
        model_cls=MiniStageModel,
        payload={},
        strict_tool_schema=schema,
    )
    assert engine.calls_kwargs[-1]["strict_tool_schema"] == schema
    assert engine.calls_kwargs[-1]["strict_tool_name"] == "emit_bridge_output"


def test_run_stage_records_strict_tool_schema_enabled_flag(tmp_path: Path):
    """T44④：llm_stage_diagnostics.json 逐站条目必须留痕 strict_tool_schema_enabled——
    反映该站本次实际是否启用了严格模式（本次调用有没有真的传 strict_tool_schema），
    不是全局笼统一个猜测值。"""
    engine = _StrictToolSchemaRecordingFakeLLMEngine(
        {"critic": '{"value": "ok"}', "bridge": '{"value": "ok"}'}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )

    orchestrator._run_stage(
        stage_key="critic", stage_name="critic", model_cls=MiniStageModel, payload={}
    )
    schema = {"type": "object", "properties": {}, "additionalProperties": False, "required": []}
    orchestrator._run_stage(
        stage_key="bridge",
        stage_name="bridge",
        model_cls=MiniStageModel,
        payload={},
        strict_tool_schema=schema,
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["stages"]["critic"]["strict_tool_schema_enabled"] is False
    assert diagnostics["stages"]["bridge"]["strict_tool_schema_enabled"] is True


def test_strict_tool_schema_for_stage_defaults_off(tmp_path: Path, monkeypatch):
    """开关默认关闭：不设置环境变量时，即使是试点白名单里的 bridge 站点也拿不到
    schema——这是刻意的显式 opt-in，不是配置文件，方便用户按需临时开关。"""
    monkeypatch.delenv("NDX_STRICT_TOOL_CALLING_STAGES", raising=False)
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    assert orchestrator._strict_tool_schema_for_stage("bridge", BridgeMemo) is None


def test_strict_tool_schema_for_stage_honors_allowlist(tmp_path: Path, monkeypatch):
    """环境变量只能作为白名单的子集选择：白名单外的站点即使被点名也不启用；
    白名单内（2026-08-16 扩围后含 reviser / final / critic）的站点点名后必须启用。"""
    monkeypatch.setenv("NDX_STRICT_TOOL_CALLING_STAGES", "critic,final,reviser,thesis,risk")
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    assert orchestrator._strict_tool_schema_for_stage("risk", RiskBoundaryReport) is None
    assert orchestrator._strict_tool_schema_for_stage("critic", Critique) is not None
    assert orchestrator._strict_tool_schema_for_stage("final", FinalAdjudication) is not None
    assert orchestrator._strict_tool_schema_for_stage("reviser", AnalysisRevised) is not None
    # 反面：白名单内的站点，环境变量点名后必须真的启用（钉住本次扩围）。
    assert orchestrator._strict_tool_schema_for_stage("thesis", ThesisDraft) is not None


def test_strict_tool_schema_for_stage_enabled_for_bridge_via_env_var(tmp_path: Path, monkeypatch):
    """真正开启的路径：环境变量包含 "bridge" 时，返回一份已经过 strict 校验的
    schema（不是原始未处理的 model_json_schema()）。"""
    monkeypatch.setenv("NDX_STRICT_TOOL_CALLING_STAGES", "bridge")
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )

    schema = orchestrator._strict_tool_schema_for_stage("bridge", BridgeMemo)

    assert schema is not None
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())


# --- T58/O15：thesis/reviser 冲突引用改"报序号"（conflict_ordinal → 代码展开编号）---
#
# 接替 T34①/T42④ 的 conflict_id enum 选单。历史事故链：run 20260730_114704 模型把
# `TC1_restrictive_macro_vs_moderate_valuation` 抄成 `C1_…`——"让模型抄/选编号字符串"
# 这条通道本身不可靠。O15 裁决：模型只报"第几条"（conflict_ordinal，1-based），
# 编号由代码映射回填，抄写笔误物理不可能。下面钉住这条修法本身：strict schema 里
# conflict_id 被物理摘除、conflict_ordinal 注入 [1..N]∪null；零候选时序号字段一并
# 摘除（语义上必须为 null）；序号→编号映射与越界反馈。测试只钉行为契约，不钉某一版
# sanitize 输出的具体形状（直接 items / anyOf 包裹两种形态都必须命中，理由同 T34①
# 原注释：sanitize 逻辑在并行演进，形态漂移时注入不得静默失效）。


def test_enforce_thesis_conflict_ordinal_handles_direct_items_ref_path(tmp_path: Path):
    """形态一：`retained_conflicts` 是必填数组，`items` 是指向 `$defs.Conflict`
    的 `$ref`（当前 sanitize_json_schema_for_strict_tool_calling 对非 anyOf
    分支内的 $ref 不做内联展开，真实产出就是这个形状）。
    行为契约：conflict_id 从模型面向 schema 物理摘除；conflict_ordinal 注入
    [1..N]∪null 的 enum；conflict_type 等其余字段不被顺手改写。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    schema = {
        "properties": {
            "retained_conflicts": {
                "type": "array",
                "items": {"$ref": "#/$defs/Conflict"},
            }
        },
        "$defs": {
            "Conflict": {
                "type": "object",
                "properties": {
                    "conflict_ordinal": {"type": ["integer", "null"]},
                    "conflict_id": {"type": ["string", "null"]},
                    "conflict_type": {"type": "string"},
                },
                "required": ["conflict_ordinal", "conflict_id", "conflict_type"],
            }
        },
    }

    result = orchestrator._enforce_thesis_conflict_ordinal(
        schema,
        ["TC_01", "TC_02"],
    )

    conflict_schema = result["$defs"]["Conflict"]
    assert "conflict_id" not in conflict_schema["properties"]
    assert conflict_schema["properties"]["conflict_ordinal"]["enum"] == [1, 2, None]
    assert conflict_schema["required"] == ["conflict_ordinal", "conflict_type"]
    # 未涉及的字段必须保持原样，不能被顺手改写。
    assert "enum" not in conflict_schema["properties"]["conflict_type"]


def test_enforce_thesis_conflict_ordinal_handles_nullable_anyof_items_path(tmp_path: Path):
    """形态二：`retained_conflicts` 被 T34②（非必填容器字段可空化）改写成
    `{"anyOf": [{"type": "array", "items": {...}}, {"type": "null"}]}`，且
    `items` 内的 `$ref` 已被内联展开成真实 object（这是 fix_anyof 对 anyOf
    分支内 $ref 的既有处理方式）。摘除与注入不能硬编码 `properties.retained_
    conflicts.items` 这条路径，否则在这种形态下会直接找不到目标字段、静默
    放弃——模型就又能自己填 conflict_id。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    schema = {
        "properties": {
            "retained_conflicts": {
                "anyOf": [
                    {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "conflict_ordinal": {"type": ["integer", "null"]},
                                "conflict_id": {"type": ["string", "null"]},
                                "conflict_type": {"type": "string"},
                            },
                        },
                    },
                    {"type": "null"},
                ]
            }
        },
    }

    result = orchestrator._enforce_thesis_conflict_ordinal(schema, ["TC_01"])

    item_properties = result["properties"]["retained_conflicts"]["anyOf"][0]["items"]["properties"]
    assert "conflict_id" not in item_properties
    assert item_properties["conflict_ordinal"]["enum"] == [1, None]


def test_enforce_thesis_conflict_ordinal_removes_ordinal_when_no_candidates(tmp_path: Path):
    """本轮 bridge 零冲突时，序号无处可指——按设计 conflict_ordinal 必须为 null，
    所以连序号字段本身也从模型面向 schema 摘除（模型物理上无法输出它），而不是
    注入空 enum 或 `enum: [null]`（部分 provider 会直接拒绝这类请求）。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    schema = {
        "properties": {
            "retained_conflicts": {
                "type": "array",
                "items": {"$ref": "#/$defs/Conflict"},
            }
        },
        "$defs": {
            "Conflict": {
                "type": "object",
                "properties": {
                    "conflict_ordinal": {"type": ["integer", "null"]},
                    "conflict_id": {"type": ["string", "null"]},
                },
                "required": ["conflict_ordinal", "conflict_id"],
            }
        },
    }

    result = orchestrator._enforce_thesis_conflict_ordinal(schema, [])

    conflict_schema = result["$defs"]["Conflict"]
    assert "conflict_id" not in conflict_schema["properties"]
    assert "conflict_ordinal" not in conflict_schema["properties"]
    assert conflict_schema["required"] == []


def test_collect_thesis_conflict_id_candidates_covers_all_three_sources_and_dedupes(tmp_path: Path):
    """enum 候选集合必须只取模型这一轮真的看得见的 conflict_id：
    `high_severity_typed_conflicts[]`、`high_severity_conflicts[]`（同名字段，
    legacy Conflict 模型）、`bridge_summaries[].typed_conflicts[]`（dict，Bridge
    v2 原始输出）。三个来源出现同一个 ID 时必须去重，模型看不见的 ID 不该
    出现在候选集合里。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-24"},
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="TC1_restrictive_macro_vs_moderate_valuation",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="宏观限制性与估值温和并存。",
                implication="强结论必须保留风险边界。",
                involved_layers=["L1", "L4"],
            )
        ],
        high_severity_conflicts=[
            Conflict(
                conflict_id="C2_legacy_conflict",
                conflict_type="legacy_conflict_type",
                severity="high",
                description="legacy 冲突描述。",
                implication="legacy 影响。",
                involved_layers=["L4", "L5"],
            )
        ],
        bridge_summaries=[
            {
                "bridge_type": "macro_valuation",
                "typed_conflicts": [
                    # 与 high_severity_typed_conflicts 里的 ID 重复，必须去重。
                    {"conflict_id": "TC1_restrictive_macro_vs_moderate_valuation", "conflict_type": "x"},
                    {"conflict_id": "TC3_liquidity_vs_breadth", "conflict_type": "y"},
                ],
            }
        ],
    )

    candidates = orchestrator._collect_thesis_conflict_id_candidates(synthesis)

    assert candidates == [
        "TC1_restrictive_macro_vs_moderate_valuation",
        "C2_legacy_conflict",
        "TC3_liquidity_vs_breadth",
    ]


def test_enforce_reviser_conflict_ordinal_covers_both_conflict_paths(tmp_path: Path):
    """T58/O15（接替 T42④）：reviser 的 `revised_thesis.retained_conflicts` 与
    `remaining_conflicts` 都要重新产出 Conflict——两条路径的 conflict_id 都必须
    摘除、conflict_ordinal 都必须注入序号 enum；两条路径最终指向同一个
    `$defs.Conflict` 时重复改写无副作用。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )

    def _schema():
        return {
            "properties": {
                "revised_thesis": {"$ref": "#/$defs/ThesisDraft"},
                "remaining_conflicts": {"type": "array", "items": {"$ref": "#/$defs/Conflict"}},
            },
            "$defs": {
                "ThesisDraft": {
                    "properties": {
                        "retained_conflicts": {"type": "array", "items": {"$ref": "#/$defs/Conflict"}},
                    }
                },
                "Conflict": {
                    "properties": {
                        "conflict_ordinal": {"type": ["integer", "null"]},
                        "conflict_id": {"type": ["string", "null"]},
                    },
                    "required": ["conflict_ordinal", "conflict_id"],
                },
            },
        }

    result = orchestrator._enforce_reviser_conflict_ordinal(
        _schema(),
        ["TC_01", "TC_03"],
    )
    conflict_schema = result["$defs"]["Conflict"]
    assert "conflict_id" not in conflict_schema["properties"]
    assert conflict_schema["properties"]["conflict_ordinal"]["enum"] == [1, 2, None]
    assert conflict_schema["required"] == ["conflict_ordinal"]

    empty = orchestrator._enforce_reviser_conflict_ordinal(_schema(), [])
    empty_schema = empty["$defs"]["Conflict"]
    assert "conflict_id" not in empty_schema["properties"]
    assert "conflict_ordinal" not in empty_schema["properties"]


def test_run_thesis_wires_conflict_ordinal_menu_into_strict_schema_when_enabled(tmp_path: Path, monkeypatch):
    """接线验证：`_run_thesis` 必须把本轮 `synthesis_packet` 实际给出的冲突清单
    动态接进严格 schema——conflict_id 从模型面向 schema 摘除、conflict_ordinal
    注入 [1..N]∪null，不能是每次 run 都一样的静态 `model_json_schema()`。同时
    钉住"未启用严格模式时行为逐字节不变"：不设环境变量时，engine 完全收不到
    strict_tool_schema/strict_tool_name。"""
    valid_thesis = {
        "environment_assessment": "环境偏紧。",
        "valuation_assessment": "估值偏高。",
        "timing_assessment": "趋势仍在。",
        "main_thesis": "主线仍成立。",
        "hypothesis_responses": [],
        "overall_confidence": "medium",
    }
    engine = _StrictToolSchemaRecordingFakeLLMEngine({"thesis": json.dumps(valid_thesis, ensure_ascii=False)})
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-24"},
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="TC1_restrictive_macro_vs_moderate_valuation",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="宏观限制性与估值温和并存。",
                implication="强结论必须保留风险边界。",
                involved_layers=["L1", "L4"],
            )
        ],
    )

    # 未启用严格模式：行为必须与试点之前逐字节相同——engine 完全收不到这两个 kwarg。
    monkeypatch.delenv("NDX_STRICT_TOOL_CALLING_STAGES", raising=False)
    orchestrator_disabled = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path / "disabled"), llm_engine=engine
    )
    orchestrator_disabled._run_thesis(synthesis)
    assert "strict_tool_schema" not in engine.calls_kwargs[-1]
    assert "strict_tool_name" not in engine.calls_kwargs[-1]

    # 启用严格模式（thesis 在白名单内）：schema 必须真的按本轮 candidate 动态收紧。
    monkeypatch.setenv("NDX_STRICT_TOOL_CALLING_STAGES", "thesis")
    orchestrator_enabled = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path / "enabled"), llm_engine=engine
    )
    orchestrator_enabled._run_thesis(synthesis)
    strict_schema = engine.calls_kwargs[-1]["strict_tool_schema"]
    items_node = strict_schema["properties"]["retained_conflicts"].get("items")
    if items_node is None:
        items_node = next(
            branch["items"]
            for branch in strict_schema["properties"]["retained_conflicts"]["anyOf"]
            if isinstance(branch, dict) and "items" in branch
        )
    conflict_object = items_node
    if "$ref" in items_node:
        conflict_object = strict_schema["$defs"][items_node["$ref"].rsplit("/", 1)[-1]]
    assert "conflict_id" not in conflict_object["properties"]
    assert conflict_object["properties"]["conflict_ordinal"]["enum"] == [1, None]


def test_run_thesis_maps_conflict_ordinal_to_id_and_retries_out_of_range(tmp_path: Path):
    """T58/O15 端到端：模型报 conflict_ordinal 序号，产物里的 conflict_id 由代码
    按本轮清单映射回填；模型顺手自填的 conflict_id 一律不采信（ordinal 留空 =
    本站新发现，编号清空）。序号越界走既有"带错误反馈重试"通道，反馈写明合法范围。"""
    base_thesis = {
        "environment_assessment": "环境偏紧。",
        "valuation_assessment": "估值偏高。",
        "timing_assessment": "趋势仍在。",
        "main_thesis": "主线仍成立。",
        "hypothesis_responses": [],
        "overall_confidence": "medium",
    }
    candidates_synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-24"},
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="TC_01",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="宏观限制性与估值温和并存。",
                implication="强结论必须保留风险边界。",
                involved_layers=["L1", "L4"],
            ),
            TypedConflict(
                conflict_id="TC_02",
                conflict_type="liquidity_vs_breadth",
                severity="high",
                description="流动性收紧与广度健康并存。",
                implication="保留张力。",
                involved_layers=["L1", "L5"],
            ),
        ],
    )

    def _conflict(ordinal, conflict_id=None):
        body = {
            "conflict_ordinal": ordinal,
            "conflict_type": "valuation_discount_rate",
            "severity": "high",
            "description": "宏观限制性与估值温和并存。",
            "implication": "偏防守。",
            "involved_layers": ["L1", "L4"],
        }
        if conflict_id is not None:
            body["conflict_id"] = conflict_id
        return body

    # 1) 正常映射 + 模型自填 conflict_id 被覆盖 + ordinal 留空时编号清空。
    engine = FakeLLMEngine({"thesis": json.dumps({
        **base_thesis,
        "retained_conflicts": [
            _conflict(2, conflict_id="模型编造的_TC_99"),
            _conflict(None, conflict_id="模型编造的_TC_01"),
        ],
    }, ensure_ascii=False)})
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path / "mapped"), llm_engine=engine
    )
    thesis = orchestrator._run_thesis(candidates_synthesis)
    assert thesis.retained_conflicts[0].conflict_id == "TC_02"
    assert thesis.retained_conflicts[1].conflict_id is None

    # 2) 越界序号被拒、反馈写明合法范围，修正后收下。
    invalid = {**base_thesis, "retained_conflicts": [_conflict(5)]}
    valid = {**base_thesis, "retained_conflicts": [_conflict(1)]}
    retry_engine = SequencedFakeLLMEngine(
        {"thesis": [json.dumps(invalid, ensure_ascii=False), json.dumps(valid, ensure_ascii=False)]}
    )
    orchestrator_retry = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path / "retry"), llm_engine=retry_engine
    )
    thesis_retry = orchestrator_retry._run_thesis(candidates_synthesis)
    assert thesis_retry.retained_conflicts[0].conflict_id == "TC_01"
    errors = orchestrator_retry.stage_diagnostics["stages"]["thesis"]["errors"]
    assert errors and errors[0]["kind"] == "contract_validation_error"
    assert "合法取值是 1..2" in errors[0]["message"]

    # 3) 零候选（上游零冲突）时序号必须留空，非空即校验错误。
    empty_synthesis = SynthesisPacket(packet_meta={"data_date": "2026-04-24"})
    engine_empty = FakeLLMEngine({"thesis": json.dumps({
        **base_thesis, "retained_conflicts": [_conflict(1)],
    }, ensure_ascii=False)})
    orchestrator_empty = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path / "empty"), llm_engine=engine_empty
    )
    with pytest.raises(RuntimeError, match="thesis failed"):
        orchestrator_empty._run_thesis(empty_synthesis)
    errors_empty = orchestrator_empty.stage_diagnostics["stages"]["thesis"]["errors"]
    assert any("清单为空" in str(error.get("message")) for error in errors_empty)


def test_thesis_prompt_hides_conflict_id_and_appends_ordinal_menu(tmp_path: Path):
    """T58/O15 非 strict 路径（默认路径）同样物理摘除：thesis 提示词的「输出字段
    规格」里不得再出现 conflict_id（模型在输出侧无处可抄），且末尾附「冲突清单
    （按序号引用）」——清单内容/顺序与 `_collect_thesis_conflict_id_candidates`
    完全一致（同一份清单，序号映射才不会指错）。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-24"},
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="TC_01",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="宏观限制性与估值温和并存。",
                implication="强结论必须保留风险边界。",
                involved_layers=["L1", "L4"],
            )
        ],
    )
    candidates = orchestrator._collect_thesis_conflict_id_candidates(synthesis)
    prompt = orchestrator._compose_prompt(
        "thesis",
        ThesisDraft,
        {"synthesis_packet": synthesis.model_dump(mode="json")},
        prompt_appendix=orchestrator._render_conflict_ordinal_menu(candidates),
    )

    spec_section = prompt.split("## 输出字段规格", 1)[1].split("## 冲突清单（按序号引用）", 1)[0]
    assert "conflict_id" not in spec_section
    assert "conflict_ordinal" in spec_section
    assert "## 冲突清单（按序号引用）" in prompt
    assert "第 1 条：TC_01" in prompt


def test_conflict_ordinal_menu_renders_empty_state():
    """零候选时清单必须明说"一律留 null"——否则模型会自己发明序号。"""
    menu = VNextOrchestrator._render_conflict_ordinal_menu([])
    assert "一律留 null" in menu
    assert "第 1 条：" not in menu  # 清单条目形态（带冒号）一条都不能有


def test_map_conflict_ordinals_to_ids_unit_cases(tmp_path: Path):
    """序号映射的单元级钉住：合法映射、ordinal 留空时清空模型自填编号、
    越界一律报错且反馈写明合法范围、零候选时非空序号非法。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    candidates = ["TC_01", "TC_02"]
    conflicts = [
        Conflict(
            conflict_ordinal=2,
            conflict_id="模型乱填的",
            conflict_type="a",
            severity="high",
            description="d",
            implication="i",
            involved_layers=["L1"],
        ),
        Conflict(
            conflict_ordinal=None,
            conflict_id="模型乱填的",
            conflict_type="b",
            severity="medium",
            description="d",
            implication="i",
            involved_layers=["L2"],
        ),
    ]
    assert orchestrator._map_conflict_ordinals_to_ids(conflicts, candidates, "thesis") == []
    assert conflicts[0].conflict_id == "TC_02"
    assert conflicts[1].conflict_id is None

    bad = [
        Conflict(
            conflict_ordinal=99,  # 越界：清单只有 2 条
            conflict_type="a",
            severity="high",
            description="d",
            implication="i",
            involved_layers=["L1"],
        )
    ]
    errors = orchestrator._map_conflict_ordinals_to_ids(bad, candidates, "thesis")
    assert errors and "1..2" in errors[0]

    errors_empty = orchestrator._map_conflict_ordinals_to_ids(bad, [], "thesis")
    assert errors_empty and "清单为空" in errors_empty[0]


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
            {
                "hypothesis_id": "hyp_leading",
                "verdict": "accept_and_revise",
                "reasoning": "主线解释在当前证据下仍然成立，予以采纳并保留监测项。",
                "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
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
        "hyp_leading",
    }
    assert thesis.hypothesis_responses[0].evidence_refs == ["L4.get_ndx_pe_and_earnings_yield"]
    retry_prompt = (tmp_path / "prompt_audit" / "thesis" / "attempt_2.prompt.txt").read_text(encoding="utf-8")
    assert "hyp_counter_2" in retry_prompt
    assert "reject requires at least one evidence_ref" in retry_prompt

    governance = orchestrator._build_governance_input_packet(synthesis, thesis)

    assert [response.hypothesis_id for response in governance.thesis_hypothesis_responses] == [
        "hyp_counter_1",
        "hyp_counter_2",
        "hyp_leading",
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


# ── T28 红灯测试：越有争议（kept_unresolved）的假说越不能被免于回应 ──
#
# 真实事故机制（investigation_reports/20260727_handoff_open_threads/HANDOFF.md T28）：
# `_run_hypothesis_competition` 一旦触发降级（受控调查提出挑战，或存在
# fallback_warnings），就会把全部假说（含反方、含 base）统一改判为
# kept_unresolved。旧版 `_validate_thesis_hypothesis_responses` 只收集
# status == "candidate" 的假说 id，降级之后 candidate 集合归零，合约整体空转——
# 四次真实 run 里三次（20260719_130534 / 20260725_145833 / 20260725_232410）
# candidate 数为 0，thesis 交零回应也能通过校验。下面三个用例锁定 T28 的修复：
# kept_unresolved 现在必须被回应，absorb_partially 是合格回应，reject 仍须带证据。

def _kept_unresolved_synthesis_fixture():
    """复刻真实 run 20260725_232410 的形状：两条假说全部是 kept_unresolved。"""
    return SynthesisPacket(
        packet_meta={"data_date": "2026-07-25"},
        evidence_index={
            "L1.get_10y_real_rate": {"layer": "L1"},
            "L4.get_ndx_pe_and_earnings_yield": {"layer": "L4"},
        },
        competing_hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_base_f3d40c16e7",
                hypothesis_text="主线解释：宏观环境持续收紧与盈利增长支撑估值之间的矛盾。",
                source="bridge_v2",
                status="kept_unresolved",
                adjudication_reason="存在调查反证、证据缺口或兜底痕迹，不能形成单一路径裁决。",
            ),
            CompetingHypothesis(
                hypothesis_id="cth_01",
                hypothesis_text="反方：盈利基本面改善，市场可能过度定价了利率风险。",
                source="counter_thesis",
                status="kept_unresolved",
                adjudication_reason="存在调查反证、证据缺口或兜底痕迹，不能形成单一路径裁决。",
            ),
        ],
    )


def test_kept_unresolved_hypotheses_with_zero_responses_are_now_blocked(tmp_path: Path):
    """改前该场景能通过校验（旧 candidate_ids 为空集，合约空转）；改后必须被拦下。

    这是 T19 事故之外的第二个真实缺陷：run 20260725_232410 里 thesis 对两条
    kept_unresolved 假说交了 0 条回应，且 `_validate_thesis_hypothesis_responses`
    在旧触发集合下判定合法——直接复现该 run 的真实 payload 形状。
    """
    synthesis = _kept_unresolved_synthesis_fixture()
    thesis = ThesisDraft(
        environment_assessment="环境偏紧。",
        valuation_assessment="估值缺乏安全垫。",
        timing_assessment="趋势转弱。",
        main_thesis="主线：估值压缩与广度恶化共振。",
        overall_confidence="medium",
        hypothesis_responses=[],  # 真实 run 20260725_232410 就是空列表
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    errors = orchestrator._validate_thesis_hypothesis_responses(thesis, synthesis)

    assert any("hyp_base_f3d40c16e7" in error and "kept_unresolved" in error for error in errors)
    assert any("cth_01" in error and "kept_unresolved" in error for error in errors)
    assert any("missing from hypothesis_responses" in error for error in errors)


def test_kept_unresolved_hypothesis_answered_with_absorb_partially_passes(tmp_path: Path):
    """正向用例：kept_unresolved 用 absorb_partially 承认张力未解决，不强求下确定结论。"""
    synthesis = _kept_unresolved_synthesis_fixture()
    thesis = ThesisDraft(
        environment_assessment="环境偏紧。",
        valuation_assessment="估值缺乏安全垫。",
        timing_assessment="趋势转弱。",
        main_thesis="主线：估值压缩与广度恶化共振，反方张力未解决。",
        overall_confidence="medium",
        hypothesis_responses=[
            {
                "hypothesis_id": "hyp_base_f3d40c16e7",
                "verdict": "accept_and_revise",
                "reasoning": "当前证据下仍以主线解释为主，采纳并保留监测项。",
                "evidence_refs": ["L1.get_10y_real_rate"],
            },
            {
                "hypothesis_id": "cth_01",
                "verdict": "absorb_partially",
                "reasoning": "承认反方张力未解决：盈利修正数据待验证前无法证伪或证实。",
                "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
            },
        ],
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    errors = orchestrator._validate_thesis_hypothesis_responses(thesis, synthesis)

    assert errors == []


def test_kept_unresolved_reject_without_evidence_ref_still_blocked(tmp_path: Path):
    """回归：kept_unresolved 假说也不能用"证据不足"当挡箭牌驳回——reject 仍须带 evidence_ref。"""
    synthesis = _kept_unresolved_synthesis_fixture()
    thesis = ThesisDraft(
        environment_assessment="环境偏紧。",
        valuation_assessment="估值缺乏安全垫。",
        timing_assessment="趋势转弱。",
        main_thesis="主线：估值压缩与广度恶化共振。",
        overall_confidence="medium",
        hypothesis_responses=[
            {
                "hypothesis_id": "hyp_base_f3d40c16e7",
                "verdict": "accept_and_revise",
                "reasoning": "采纳主线。",
                "evidence_refs": ["L1.get_10y_real_rate"],
            },
            {
                "hypothesis_id": "cth_01",
                "verdict": "reject",
                "reasoning": "证据不足，直接驳回。",
                "evidence_refs": [],
            },
        ],
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )

    errors = orchestrator._validate_thesis_hypothesis_responses(thesis, synthesis)

    assert any("reject requires at least one evidence_ref" in error for error in errors)


def test_reviser_kept_unresolved_responses_explicitly_emptied_still_fails(tmp_path: Path):
    """真实样本 20260719_130534 的最小复现：thesis 对 kept_unresolved 假说交了 2 条
    回应（accept_and_revise + absorb_partially），但 reviser 把
    revised_thesis.hypothesis_responses 显式交成空列表——键存在（非缺席），
    不触发遗漏继承，必须被 validator 硬拦。这是本次扩大触发集合后，reviser 站
    第一次真正会为 kept_unresolved 假说消失而报警（旧触发集合下这个场景合法，
    是 T19「漏字段」症状在 kept_unresolved 语境下的真实样本）。
    """
    synthesis = _kept_unresolved_synthesis_fixture()
    thesis = ThesisDraft(
        environment_assessment="环境偏紧。",
        valuation_assessment="估值缺乏安全垫。",
        timing_assessment="趋势转弱。",
        main_thesis="主线：估值压缩与广度恶化共振。",
        overall_confidence="medium",
        hypothesis_responses=[
            {
                "hypothesis_id": "hyp_base_f3d40c16e7",
                "verdict": "accept_and_revise",
                "reasoning": "采纳主线，保留监测项。",
                "evidence_refs": ["L1.get_10y_real_rate"],
            },
            {
                "hypothesis_id": "cth_01",
                "verdict": "absorb_partially",
                "reasoning": "承认反方张力未解决。",
                "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
            },
        ],
    )
    reviser_payload = {
        "revision_summary": "吸收批评并保留张力。",
        "accepted_critiques": [],
        "rejected_critiques": [],
        "revised_thesis": {
            "environment_assessment": "环境偏紧，实际利率处极端高位。",
            "valuation_assessment": "估值缺乏安全垫，ERP 低分位。",
            "timing_assessment": "价格跌破中短期均线。",
            "main_thesis": "修订后主线：估值压缩与广度恶化共振。",
            "overall_confidence": "medium",
            "hypothesis_responses": [],  # 键存在但被清空——不是遗漏，是主动抹平
        },
        "remaining_conflicts": [],
    }
    engine = SequencedFakeLLMEngine({"reviser": [json.dumps(reviser_payload, ensure_ascii=False)]})
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    with pytest.raises(RuntimeError, match="missing from hypothesis_responses"):
        orchestrator._run_stage(
            stage_key="reviser",
            stage_name="reviser",
            model_cls=AnalysisRevised,
            payload={"example": "payload"},
            pre_validate_transform=lambda parsed: orchestrator._sanitize_reviser_evidence_refs(
                orchestrator._carry_forward_reviser_thesis_fields(parsed, thesis),
                synthesis.evidence_index,
            ),
            validator=lambda candidate: (
                orchestrator._validate_stage_evidence_refs(
                    candidate, set(synthesis.evidence_index.keys()), "reviser"
                )
                + orchestrator._validate_thesis_hypothesis_responses(
                    candidate.revised_thesis, synthesis
                )
            ),
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
    """R7 工单（WORK_LOG.md:435）在 2026-07-27 T28 扩大了触发集合：从"仅 candidate"
    扩到"非 downgraded"（含 leading / kept_unresolved），因为受控调查触发降级后会把
    全部假说统一改判为 kept_unresolved，旧触发集合下 candidate 集合归零、合约整体
    空转。这里锁的是扩大后的新措辞，防止再次漂移回旧的"仅 candidate"表述。"""
    prompt = Path(orchestrator_module.__file__).with_name("prompts").joinpath("thesis_builder.md").read_text(encoding="utf-8")
    required_block = (
        "## 对竞争假说的强制回应\n"
        "`synthesis_packet.competing_hypotheses` 里除 `status` 为 `downgraded`（已被裁决出局）之外的每一个假说——`candidate`、`leading`、`kept_unresolved`、`split`——你都必须在 `hypothesis_responses` 里逐一回应，三选一：接受并修正判断（accept_and_revise）、部分吸收（absorb_partially）、驳回（reject）。`leading` 通常是你主论点所依据的主线假说，也要求显式回应，写清楚为什么接受，不能因为它是自己的主线就默认略过。`kept_unresolved` 表示这条假说还没有被单一路径裁决出胜负、张力尚未解决，合格回应可以是 absorb_partially（承认张力未解决，并写明还缺哪条证据），不强求给出确定的 accept_and_revise 或 reject——诚实保留未解决的争议，比强行下结论更符合纪律。驳回（reject）无论对方是什么状态，都必须引用具体的反证 evidence_ref，不许用\"证据不足\"四个字一笔带过——证据不足时的诚实选项是 absorb_partially 并写明缺哪条证据。你的主论点如果无法回应某个假说最强的那条证据，就不许假装没看见它。"
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


def test_sanitize_reviser_ref_list_covers_coerce_drop_mixed_and_unknown_parent(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    evidence_index = {
        "L1.get_fed_funds_rate": {"mixed_field_authority": False},
        "L4.get_ndx_earnings_revision_metrics": {"mixed_field_authority": True},
    }
    warnings: list[str] = []

    # Case 1: parent non-mixed and present -> coerce to parent.
    sanitized = orchestrator._sanitize_reviser_ref_list(
        ["L1.get_fed_funds_rate#some_field"], evidence_index, "owner1", warnings
    )
    assert sanitized == ["L1.get_fed_funds_rate"]
    assert any("coerced" in w for w in warnings)

    # Case 2: parent mixed_field_authority -> must be dropped, never coerced.
    warnings.clear()
    sanitized = orchestrator._sanitize_reviser_ref_list(
        ["L4.get_ndx_earnings_revision_metrics#yoy_pct"], evidence_index, "owner2", warnings
    )
    assert sanitized == []
    assert any("dropped" in w and "mixed_field_authority" in w for w in warnings)

    # Case 3: parent does not exist in evidence_index -> dropped.
    warnings.clear()
    sanitized = orchestrator._sanitize_reviser_ref_list(
        ["L9.get_totally_fake_metric#nope"], evidence_index, "owner3", warnings
    )
    assert sanitized == []
    assert any("dropped" in w for w in warnings)

    # Legal refs pass through untouched, no warnings.
    warnings.clear()
    sanitized = orchestrator._sanitize_reviser_ref_list(
        ["L1.get_fed_funds_rate"], evidence_index, "owner4", warnings
    )
    assert sanitized == ["L1.get_fed_funds_rate"]
    assert warnings == []


def test_reviser_illegal_refs_are_sanitized_and_do_not_raise_runtime_error(tmp_path: Path):
    """真实事故复现的最小化回归：reviser 幻觉出非法 parent#field 引用时，净化逻辑
    必须在结构校验之前把可退回的退回、把不可退回的丢弃，让 stage 一次通过而不是
    RuntimeError 中止；mixed_field_authority 的父级绝不能被 coerce。"""
    evidence_index = {
        "L4.get_ndx_earnings_revision_metrics": {
            "layer": "L4",
            "function_id": "get_ndx_earnings_revision_metrics",
            "mixed_field_authority": True,
        },
        "L4.get_ndx_earnings_revision_metrics#slope_30d": {
            "layer": "L4",
            "parent_evidence_ref": "L4.get_ndx_earnings_revision_metrics",
            "field_name": "slope_30d",
        },
        "L1.get_fed_funds_rate": {
            "layer": "L1",
            "function_id": "get_fed_funds_rate",
            "mixed_field_authority": False,
        },
    }
    reviser_payload = {
        "revision_summary": "修订说明。",
        "accepted_critiques": [],
        "rejected_critiques": [],
        "revised_thesis": {
            "environment_assessment": "环境评估。",
            "valuation_assessment": "估值评估。",
            "timing_assessment": "时机评估。",
            "main_thesis": "主论点。",
            "overall_confidence": "medium",
            "key_support_chains": [
                {
                    "chain_description": "链条A_可退回",
                    "evidence_refs": ["L1.get_fed_funds_rate#some_field"],
                    "weight": 0.5,
                },
                {
                    "chain_description": "链条B_混合父级只能丢弃",
                    "evidence_refs": ["L4.get_ndx_earnings_revision_metrics#yoy_pct"],
                    "weight": 0.3,
                },
                {
                    "chain_description": "链条C_父级不存在但保留合法ref",
                    "evidence_refs": [
                        "L9.get_totally_fake_metric#nope",
                        "L1.get_fed_funds_rate",
                    ],
                    "weight": 0.2,
                },
            ],
            "reader_conclusion": {
                "one_liner": "读者结论。",
                "evidence_refs": ["L4.get_ndx_earnings_revision_metrics#yoy_pct"],
            },
        },
    }
    engine = SequencedFakeLLMEngine(
        {"reviser": [json.dumps(reviser_payload, ensure_ascii=False)]}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    result = orchestrator._run_stage(
        stage_key="reviser",
        stage_name="reviser",
        model_cls=AnalysisRevised,
        payload={"example": "payload"},
        pre_validate_transform=lambda parsed: orchestrator._sanitize_reviser_evidence_refs(
            parsed, evidence_index
        ),
        validator=lambda candidate: orchestrator._validate_stage_evidence_refs(
            candidate, set(evidence_index.keys()), "reviser"
        ),
    )

    # No retry was needed: sanitization made the first attempt pass structural + contract validation.
    assert engine.calls["reviser"] == 1

    chains = result.revised_thesis.key_support_chains
    chain_a = next(c for c in chains if c.chain_description == "链条A_可退回")
    assert chain_a.evidence_refs == ["L1.get_fed_funds_rate"]

    # Mixed-authority parent must never be coerced -> chain B has zero legal refs left
    # and is dropped entirely, not just left with an empty (or coerced-parent) ref list.
    assert not any(c.chain_description == "链条B_混合父级只能丢弃" for c in chains)

    chain_c = next(c for c in chains if c.chain_description == "链条C_父级不存在但保留合法ref")
    assert chain_c.evidence_refs == ["L1.get_fed_funds_rate"]

    # reader_conclusion is a singleton (not a list item) so it cannot be dropped wholesale;
    # its illegal mixed-parent ref is sanitized down to an empty list instead.
    assert result.revised_thesis.reader_conclusion.evidence_refs == []

    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["stages"]["reviser"]["status"] == "ok"
    sanitization_log = diagnostics.get("reviser_evidence_ref_sanitization", [])
    assert any("coerced" in entry for entry in sanitization_log)
    assert any(
        "mixed_field_authority" in entry and "dropped" in entry for entry in sanitization_log
    )


# ── Reviser 遗漏继承（omission-only carry-forward）回归 ──
#
# 真实事故（run 20260724_223804）：reviser 两次尝试输出的 revised_thesis 键集合逐字
# 相同，且恰好等于 reviser.md 输出模板列出的字段——hypothesis_responses 从不在其中，
# 因为该字段在 reviser 的 prompt 里根本没有出现过。结果是 candidate 假说回应缺失、
# 重试无法自愈、整条约 25 分钟的流水线 RuntimeError 中止。

def _reviser_carry_forward_fixture():
    """返回 (synthesis, thesis, reviser_payload_without_hypothesis_responses)。"""
    synthesis = SynthesisPacket(
        packet_meta={"data_date": "2026-04-24"},
        evidence_index={
            "L1.get_10y_real_rate": {"layer": "L1"},
            "L4.get_ndx_pe_and_earnings_yield": {"layer": "L4"},
        },
        competing_hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_counter_33b7f68546",
                hypothesis_text="反方：证据缺口足以推翻主线。",
                source="counter_thesis",
                status="candidate",
            ),
        ],
    )
    thesis = ThesisDraft(
        environment_assessment="环境偏紧。",
        valuation_assessment="估值缺乏安全垫。",
        timing_assessment="趋势转弱。",
        main_thesis="主线：估值压缩与广度恶化共振。",
        overall_confidence=Confidence.MEDIUM,
        hypothesis_responses=[
            {
                "hypothesis_id": "hyp_counter_33b7f68546",
                "verdict": "reject",
                "reasoning": "主要矛盾不依赖单一数据，多层硬证据已构成充分风险画面。",
                "evidence_refs": [
                    "L1.get_10y_real_rate",
                    "L4.get_ndx_pe_and_earnings_yield",
                ],
            }
        ],
    )
    # 复刻真实 attempt_1/attempt_2 的形状：revised_thesis 里完全没有 hypothesis_responses 这个键。
    reviser_payload = {
        "revision_summary": "吸收批评并保留张力。",
        "accepted_critiques": ["Critic 指出的跨层逻辑跳跃"],
        "rejected_critiques": [],
        "revised_thesis": {
            "environment_assessment": "环境偏紧，实际利率处极端高位。",
            "valuation_assessment": "估值缺乏安全垫，ERP 低分位。",
            "timing_assessment": "价格跌破中短期均线。",
            "main_thesis": "修订后主线：估值压缩与广度恶化共振，赔率不利。",
            "overall_confidence": "medium",
            "key_support_chains": [
                {
                    "chain_description": "实际利率压制久期资产估值",
                    "evidence_refs": ["L1.get_10y_real_rate"],
                    "weight": 0.6,
                }
            ],
        },
        "remaining_conflicts": [],
    }
    return synthesis, thesis, reviser_payload


def _run_reviser_stage(orchestrator, synthesis, thesis, raw_response: str):
    """按生产调用点（orchestrator._run_analysis 中 reviser 那一段）的完全相同接线跑一次。"""
    return orchestrator._run_stage(
        stage_key="reviser",
        stage_name="reviser",
        model_cls=AnalysisRevised,
        payload={"example": "payload"},
        pre_validate_transform=lambda parsed: orchestrator._sanitize_reviser_evidence_refs(
            orchestrator._carry_forward_reviser_thesis_fields(parsed, thesis),
            synthesis.evidence_index,
        ),
        validator=lambda candidate: (
            orchestrator._validate_stage_evidence_refs(
                candidate, set(synthesis.evidence_index.keys()), "reviser"
            )
            + orchestrator._validate_thesis_hypothesis_responses(
                candidate.revised_thesis, synthesis
            )
        ),
    )


def test_reviser_omitted_hypothesis_responses_are_carried_forward_from_thesis(tmp_path: Path):
    """遗漏（键缺席）→ 从 thesis 原稿原样继承、打标记、留痕，stage 一次通过不再硬崩。

    这是 run 20260724_223804 的最小复现：修复前此用例必然 RuntimeError
    ("candidate hypothesis hyp_counter_33b7f68546 is missing from hypothesis_responses.")。
    """
    synthesis, thesis, reviser_payload = _reviser_carry_forward_fixture()
    engine = SequencedFakeLLMEngine(
        {"reviser": [json.dumps(reviser_payload, ensure_ascii=False)]}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    result = _run_reviser_stage(orchestrator, synthesis, thesis, "")

    # 一次通过：不再靠重试抽奖。
    assert engine.calls["reviser"] == 1

    responses = result.revised_thesis.hypothesis_responses
    assert [item.hypothesis_id for item in responses] == ["hyp_counter_33b7f68546"]
    # 原稿裁决必须原样搬运——代码永不生成回应内容。
    assert responses[0].verdict == "reject"
    assert responses[0].reasoning == thesis.hypothesis_responses[0].reasoning
    assert responses[0].evidence_refs == [
        "L1.get_10y_real_rate",
        "L4.get_ndx_pe_and_earnings_yield",
    ]
    # 必须可被下游和审计区识别为"本轮未修订"，不能伪装成 reviser 自己的判断。
    assert getattr(responses[0], "carried_forward_from_thesis", False) is True

    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["stages"]["reviser"]["status"] == "ok"
    carry_log = diagnostics.get("reviser_thesis_field_carry_forward", [])
    assert any("hypothesis_responses" in entry for entry in carry_log)


def test_reviser_explicit_empty_hypothesis_responses_still_fails(tmp_path: Path):
    """主动交空数组 = 主动抹平候选假说，必须继续硬拦——继承逻辑不得成为后门。"""
    synthesis, thesis, reviser_payload = _reviser_carry_forward_fixture()
    reviser_payload["revised_thesis"]["hypothesis_responses"] = []
    engine = SequencedFakeLLMEngine(
        {"reviser": [json.dumps(reviser_payload, ensure_ascii=False)]}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    with pytest.raises(RuntimeError, match="missing from hypothesis_responses"):
        _run_reviser_stage(orchestrator, synthesis, thesis, "")

    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert "reviser_thesis_field_carry_forward" not in diagnostics


def test_reviser_own_hypothesis_responses_are_never_overwritten(tmp_path: Path):
    """reviser 自己作答时必须尊重它的答案，继承只补遗漏，不做覆盖。"""
    synthesis, thesis, reviser_payload = _reviser_carry_forward_fixture()
    reviser_payload["revised_thesis"]["hypothesis_responses"] = [
        {
            "hypothesis_id": "hyp_counter_33b7f68546",
            "verdict": "absorb_partially",
            "reasoning": "修订后部分吸收反方，承认盈利数据缺口。",
            "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
        }
    ]
    engine = SequencedFakeLLMEngine(
        {"reviser": [json.dumps(reviser_payload, ensure_ascii=False)]}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    result = _run_reviser_stage(orchestrator, synthesis, thesis, "")
    response = result.revised_thesis.hypothesis_responses[0]

    assert response.verdict == "absorb_partially"
    assert getattr(response, "carried_forward_from_thesis", False) is False
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert "reviser_thesis_field_carry_forward" not in diagnostics


def test_reviser_carried_forward_reject_without_evidence_still_fails(tmp_path: Path):
    """继承来源本身不合法时，继承不得把非法内容洗白——validator 仍须拦下。"""
    synthesis, thesis, reviser_payload = _reviser_carry_forward_fixture()
    thesis.hypothesis_responses[0].evidence_refs = []
    engine = SequencedFakeLLMEngine(
        {"reviser": [json.dumps(reviser_payload, ensure_ascii=False)]}
    )
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    with pytest.raises(RuntimeError, match="reject requires at least one evidence_ref"):
        _run_reviser_stage(orchestrator, synthesis, thesis, "")


def test_degraded_analysis_revised_preserves_thesis_and_declares_degradation(tmp_path: Path):
    """reviser 软着陆：兜底产物必须沿用原稿、保留冲突、并显式声明未经修订。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
        max_node_retries=2,
    )
    _, thesis, _ = _reviser_carry_forward_fixture()
    thesis.retained_conflicts = [
        Conflict(
            conflict_type="L1_high_real_rate_vs_L4_medium_valuation",
            severity="high",
            description="高实际利率与估值并存",
            involved_layers=["L1", "L4"],
            implication="估值安全垫不足，赔率偏薄。",
        )
    ]

    degraded = orchestrator._build_degraded_analysis_revised(thesis, "reviser failed after 2 attempts: ...")

    # 兜底沿用原稿，因此天然满足 reviser 所受的同一组合约（原稿已通过）。
    assert degraded.revised_thesis.main_thesis == thesis.main_thesis
    assert degraded.revised_thesis.hypothesis_responses[0].hypothesis_id == "hyp_counter_33b7f68546"
    # 冲突是资产：兜底不得顺手抹平。
    assert [c.conflict_type for c in degraded.remaining_conflicts] == [
        "L1_high_real_rate_vs_L4_medium_valuation"
    ]
    # 降级必须机器可读、人眼可见。
    assert degraded.degraded_fallback["stage"] == "reviser"
    assert "[degraded]" in degraded.revision_summary
    assert "未经修订" in degraded.revision_summary

    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["reviser_degraded_fallback"][0]["attempts"] == 2


def test_degraded_reviser_checkpoint_is_not_reused_on_resume(tmp_path: Path):
    """一次修订失败不得被续跑永久固化：降级产物不是成功结果，续跑必须重跑 reviser。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
        max_node_retries=2,
        resume_from_existing=True,
    )
    _, thesis, _ = _reviser_carry_forward_fixture()
    payload = {"governance_input": {"thesis_main": thesis.main_thesis}}

    # 先落一份正常修订产物：续跑应当复用。
    healthy = AnalysisRevised(revision_summary="正常修订。", revised_thesis=thesis)
    orchestrator._save_json("analysis_revised.json", healthy)
    orchestrator._record_stage_artifact(
        tmp_path / "analysis_revised.json",
        stage_key="reviser",
        stage_name="reviser",
        payload=payload,
    )
    assert orchestrator._load_reviser_checkpoint(payload) is not None

    # 换成降级兜底产物：续跑必须忽略它并重跑。
    degraded = orchestrator._build_degraded_analysis_revised(thesis, "reviser failed after 2 attempts")
    orchestrator._save_json("analysis_revised.json", degraded)
    orchestrator._record_stage_artifact(
        tmp_path / "analysis_revised.json",
        stage_key="reviser",
        stage_name="reviser",
        payload=payload,
    )
    assert orchestrator._load_reviser_checkpoint(payload) is None


def test_counter_thesis_checkpoint_is_reused_on_resume(tmp_path: Path):
    """成功产出的反方稿必须能被续跑复用；兜底稿必须被拒。

    真实事故 run 20260728_110702：`counter_thesis.json` 此前用 `_save_json` 直接落盘，
    manifest 里 stage_key / payload_sha256 都是 None，也没有 `_load_stage_checkpoint`。
    结果续跑必然重跑反方 → 竞争假说变了 → thesis 的 expected_payload 指纹对不上 →
    thesis / reviser / final 跟着全部重跑并**静默覆盖**已产出的产物（那次首跑的 3 条
    假说验收样本因此永久消失），与 `--resume-run-dir` 帮助文字里
    "verified stage checkpoints are reused" 不符。裁决为修行为而非修文档。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
        resume_from_existing=True,
    )
    payload = {"synthesis_packet_without_self_reference": {"packet_meta": {"data_date": "2026-07-28"}}}
    draft = CounterThesisDraft(
        principal_counterargument="反方：利率已近顶部，回调是介入机会。",
        hypotheses=[
            CompetingHypothesis(
                hypothesis_id="cth_01",
                hypothesis_text="盈利上修足以消化当前估值。",
                source="counter_thesis",
                status="kept_unresolved",
            )
        ],
    )

    # 1) 正常产出的反方稿：登记为可复用，续跑取得回来。
    orchestrator._save_json("counter_thesis.json", draft)
    orchestrator._record_stage_artifact(
        tmp_path / "counter_thesis.json",
        stage_key="counter_thesis",
        stage_name="counter_thesis",
        payload=payload,
        checkpoint_reusable=True,
    )
    reused = orchestrator._load_stage_checkpoint(
        "counter_thesis.json",
        CounterThesisDraft,
        stage_key="counter_thesis",
        stage_name="counter_thesis",
        expected_payload=payload,
    )
    assert reused is not None
    assert [item.hypothesis_id for item in reused.hypotheses] == ["cth_01"]

    # 2) 上游输入变了就不许复用（既有 payload 指纹语义不得被新登记削弱）。
    assert orchestrator._load_stage_checkpoint(
        "counter_thesis.json",
        CounterThesisDraft,
        stage_key="counter_thesis",
        stage_name="counter_thesis",
        expected_payload={"synthesis_packet_without_self_reference": {"packet_meta": {"data_date": "2026-07-29"}}},
    ) is None

    # 3) 兜底稿：模板凑数不是"已验证"结果，续跑必须重试而不是把它固化下去。
    orchestrator._record_stage_artifact(
        tmp_path / "counter_thesis.json",
        stage_key="counter_thesis",
        stage_name="counter_thesis",
        payload=payload,
        checkpoint_reusable=False,
    )
    assert orchestrator._load_stage_checkpoint(
        "counter_thesis.json",
        CounterThesisDraft,
        stage_key="counter_thesis",
        stage_name="counter_thesis",
        expected_payload=payload,
    ) is None


def test_resume_overwrite_of_verified_artifact_leaves_a_trace(tmp_path: Path):
    """续跑覆盖已验证产物不再无迹可寻。

    行为不变（重跑就该写新结果），但 manifest 必须留下被覆盖那份的指纹，
    让"我当时读到的那份还在不在"事后可查——run 20260728_110702 的教训。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
        resume_from_existing=True,
    )
    payload = {"governance_input": {"thesis_main": "第一版"}}
    first = CounterThesisDraft(principal_counterargument="第一版反方论证。")
    orchestrator._save_json("counter_thesis.json", first)
    orchestrator._record_stage_artifact(
        tmp_path / "counter_thesis.json",
        stage_key="counter_thesis",
        stage_name="counter_thesis",
        payload=payload,
    )
    first_sha = orchestrator.stage_manifest["artifacts"]["counter_thesis.json"]["sha256"]
    assert "overwritten_in_resume" not in orchestrator.stage_manifest["artifacts"]["counter_thesis.json"]

    second = CounterThesisDraft(principal_counterargument="第二版反方论证，内容不同。")
    orchestrator._save_json("counter_thesis.json", second)
    orchestrator._record_stage_artifact(
        tmp_path / "counter_thesis.json",
        stage_key="counter_thesis",
        stage_name="counter_thesis",
        payload=payload,
    )

    trace = orchestrator.stage_manifest["artifacts"]["counter_thesis.json"].get("overwritten_in_resume")
    assert trace is not None, "续跑覆盖了已登记产物却没有留痕"
    assert trace["previous_sha256"] == first_sha


def test_degraded_reviser_marks_final_quality_gate(tmp_path: Path):
    """降级必须传导到质量闸门，由发布闸门决定能不能发，而不是悄悄变成正常报告。"""
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
    )

    orchestrator._append_final_quality_note(final, "reviser_degraded_unrevised_thesis")

    assert "reviser_degraded_unrevised_thesis" in final.quality_gate.notes


def test_critic_overall_assessment_has_no_length_cap(tmp_path: Path):
    """2026-07-26 数字规则重构：`Critique.overall_assessment` 原有的 `max_length=200`
    经复核确认无任何下游依据（不进入固定宽度展示位，纯属人为限制，且真实事故
    run 20260725_232410 已证明它经常不够表达"幸存的最强反对意见"），已移除。

    这条测试锁定"移除生效"这件事本身：一段远超原 200 字符上限的文本必须一次
    通过，不再触发任何重试。"""
    base = {
        "issues": [],
        "cross_layer_issues": [],
        "revision_direction": "保留主要论点，补充证据引用。",
    }
    long_assessment = "这是一段远超过原 200 字符上限的总体评估文本，" * 15
    assert len(long_assessment) > 200
    engine = SequencedFakeLLMEngine({
        "critic": [json.dumps({**base, "overall_assessment": long_assessment}, ensure_ascii=False)]
    })
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    result = orchestrator._run_stage(
        stage_key="critic",
        stage_name="critic",
        model_cls=Critique,
        payload={"example": "payload"},
    )

    assert result.overall_assessment == long_assessment
    assert engine.calls["critic"] == 1


def test_critic_stage_retries_after_overlong_revision_direction(tmp_path: Path):
    """`Critique.revision_direction` 仍保留长度上限（2026-07-26 从 300 放宽到 500，
    不是移除）——这条测试锁定"写长了仍能靠重试自愈"这条安全网继续有效。"""
    base = {
        "issues": [],
        "cross_layer_issues": [],
        "overall_assessment": "未发现重大问题，最强反对意见是盈利修正数据置信度偏低。",
    }
    engine = SequencedFakeLLMEngine({
        "critic": [
            json.dumps({**base, "revision_direction": "过长的修订方向文本" * 60}, ensure_ascii=False),
            json.dumps({**base, "revision_direction": "保留主要论点，补充证据引用。"}, ensure_ascii=False),
        ]
    })
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )

    result = orchestrator._run_stage(
        stage_key="critic",
        stage_name="critic",
        model_cls=Critique,
        payload={"example": "payload"},
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert result.revision_direction == "保留主要论点，补充证据引用。"
    assert engine.calls["critic"] == 2
    assert diagnostics["stages"]["critic"]["errors"][0]["kind"] == "schema_validation_error"
    assert "revision_direction" in diagnostics["stages"]["critic"]["errors"][0]["message"]


def test_layer_prompt_documents_local_conclusion_as_required_field(tmp_path: Path):
    """真实事故复现（run 20260725_232410）：`LayerCard.local_conclusion` 是必填字段
    （无默认值，`max_length=500`），但五层共享的 `_compose_layer_prompt` 契约段此前
    只在"layer_synthesis 不能只重复 local_conclusion"这一句里提到它的名字，从未指示
    模型必须输出这个字段——L4 站点当天就因为 `local_conclusion Field required` 被
    打回重试一次。

    这是与 reviser/counter_thesis/critic 同型的 Class A 规格漂移，区别在于它的"说明书"
    不是一个静态 prompt 文件，而是 `_compose_layer_prompt` 动态拼接的共享契约文本——
    所以不适合塞进 `STAGE_CONTRACT_PROMPT_REQUIREMENTS`（那套机制假设每个 stage 对应
    一个静态文件），改用直接调用 `_compose_layer_prompt` 断言拼接结果的方式验证。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    prompt = orchestrator._compose_layer_prompt(
        "l4_analyst",
        "占位 prompt 正文。",
        {"layer": "L4", "layer_raw_data": {}},
    )

    assert "local_conclusion" in prompt
    assert "500" in prompt
    assert "必填" in prompt


def test_annotate_percentile_scales_declares_0_1_and_0_100(tmp_path: Path):
    """B7 修复：percentile 数值叶必须带机器生成的刻度声明，杜绝 0-1/0-100 混用。"""
    annotated = VNextOrchestrator._annotate_percentile_scales(
        {
            "relativity": {"percentile_5y": 0.74},
            "historical": {"percentile_10y": 74.0},
            "mixed": {"percentile_5y": 0.2, "percentile_10y": 20.0},
        }
    )
    assert annotated["relativity"]["percentile_scale"] == "0-1"
    assert annotated["historical"]["percentile_scale"] == "0-100"
    assert annotated["mixed"]["percentile_scale"] == "mixed"


def test_align_metric_names_to_canon_for_layer_prompt(tmp_path: Path):
    """C12 修复：发给模型的 metric_name 必须与 IndicatorCanon 注册名逐字一致。"""
    aligned = VNextOrchestrator._align_metric_names_to_canon(
        "L1",
        {
            "get_10y_real_rate": {
                "function_id": "get_10y_real_rate",
                "metric_name": "某个和 canon 不一致的名字",
            },
        },
    )
    assert aligned["get_10y_real_rate"]["metric_name"] == "10Y Real Rate"


def test_metric_name_single_authority_across_prompt_assembly_validator(tmp_path: Path):
    """T54 确认跑实战（2026-08-17 t54_confirm L1 两连败）：采集长名与 canon 注册名
    不一致时（get_10y2y_spread_bp：材料带 '10Y-2Y Treasury Spread'，canon 注册
    '10Y-2Y Spread'），提示词副本、批 5 装配层、契约校验器必须解出同一个名字——
    各立来源时模型被两套名字来回抽鞭，装配强制其一后变成每跑必挂。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=object()
    )
    raw = {
        "get_10y2y_spread_bp": {
            "function_id": "get_10y2y_spread_bp",
            "metric_name": "10Y-2Y Treasury Spread",
            "name": "10Y-2Y Treasury Spread",
        }
    }

    # 校验器侧（packet.raw_data 路径）
    packet = SimpleNamespace(raw_data={"L1": raw})
    expected = orchestrator._analysis_required_indicator_map(packet, "L1")
    assert expected == {"get_10y2y_spread_bp": "10Y-2Y Spread"}

    # 装配侧（stage payload 路径）：模型填长名也必须被回正为同一个 canon 名
    parsed = {
        "indicator_analyses": [
            {
                "function_id": "get_10y2y_spread_bp",
                "metric": "10Y-2Y Treasury Spread",
                "narrative": "利差倒挂。",
                "reasoning_process": "曲线形态。",
                "evidence_refs": ["L1.get_10y2y_spread_bp"],
            }
        ]
    }
    assembled = orchestrator._assemble_stage_mechanical_fields(
        "l1_analyst", parsed, {"layer_raw_data": raw}
    )
    assert assembled["indicator_analyses"][0]["metric"] == "10Y-2Y Spread"

    # 提示词侧（C12 对齐）
    aligned = VNextOrchestrator._align_metric_names_to_canon("L1", raw)
    assert aligned["get_10y2y_spread_bp"]["metric_name"] == "10Y-2Y Spread"


def test_canonical_metric_name_falls_back_when_canon_unknown(tmp_path: Path):
    """canon 不认识的指标：退回材料自带 metric_name / name（旧行为不变）。"""
    indicator = {"function_id": "no_such_indicator", "metric_name": "材料名", "name": "别名"}
    assert (
        VNextOrchestrator._canonical_metric_name("no_such_indicator", indicator) == "材料名"
    )
    assert VNextOrchestrator._canonical_metric_name("no_such_indicator", {"name": "别名"}) == "别名"


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
            json.dumps({**base, "reasoned_verdict": "过长" * 1501}, ensure_ascii=False),  # 上限已放宽至 3000（2026-07-26）
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


def test_final_stage_retries_when_reasoned_verdict_has_zero_citations(tmp_path: Path):
    """真实事故复现（run 20260725_232410）：终审一次通过，reasoned_verdict 514 字、
    内容连贯、数字详实，却零处方括号引用——final_adjudicator.md 明确说这是"硬要求，
    一个都没有等于整段作废"，但当时的 validator 链只查结构化 evidence_refs 字段，
    从不检查判决正文里的方括号引用，于是模型交零引用也能一次通过。

    修复后：final 阶段的 validator 链新增 `_validate_reasoned_verdict_refs`，零引用
    触发重试，重试反馈原样喂回模型，第二次尝试补上引用即可通过——不需要碰
    prompt，因为说明书本来就给了正确格式的例子，这不是"模型不知道规则"。
    """
    base = {
        "approval_status": "approved_with_reservations",
        "final_stance": "中性偏谨慎",
        "confidence": "medium",
        "must_preserve_risks": ["估值压缩风险"],
        "blocking_issues": [],
        "adjudicator_notes": "保留风险边界。",
    }
    zero_citation_verdict = (
        "当前NDX市场处在宏观利率极端压制估值与微观盈利改善之间的拉锯状态。"
        "主导矛盾是实际利率处于历史极值与盈利修正持续向上之间的冲突。"
        "风险面目前占优：简式收益差距为负，安全垫不足，广度恶化和技术结构偏空强化了下行压力。"
        "信用市场总体宽松但尾部分化，暴露了结构性脆弱。价格已部分反映利率压力，但剩余估值压缩风险未充分定价。"
        "盈利上修预期部分计入，但对失望风险定价不足。赔率偏不利：利率、估值和趋势类别指向补偿变薄，"
        "信用和流动性提供部分缓冲，但不足以扭转方向。核心仓位应维持偏低配置，战术仓可极轻仓试短线反弹，严格止损。"
        "主要风险是利率继续上行或盈利下修导致估值进一步压缩，等待成本在于错过短期技术性修复或盈利超预期带来的反弹。"
    )
    engine = SequencedFakeLLMEngine({
        "final_adjudicator": [
            json.dumps({**base, "reasoned_verdict": zero_citation_verdict}, ensure_ascii=False),
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
        validator=lambda candidate: orchestrator._validate_reasoned_verdict_refs(
            candidate, {"L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield", "L5.get_qqq_technical_indicators"}
        ),
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    # 零引用不该一次通过：必须重试，第二次带引用的版本才被接受。
    assert engine.calls["final_adjudicator"] == 2
    assert result.reasoned_verdict == _VALID_REASONED_VERDICT
    assert diagnostics["stages"]["final_adjudicator"]["errors"][0]["kind"] == "contract_validation_error"
    assert "found zero citations" in diagnostics["stages"]["final_adjudicator"]["errors"][0]["message"]


def test_reasoned_verdict_requires_three_distinct_citations_for_three_reasons(tmp_path: Path):
    """只查"至少一条引用"会放过真实事故形态：单段连续文字 + 一条引用即可蒙混过关。

    final_adjudicator.md:243-245 要求总-分-总结构、中间按"最有分量的三条理由"展开，
    且"三条主要理由每条必须至少带一个方括号标注的 evidence_ref"。三条理由各至少
    一条 ⇒ 至少三条不同引用。这不是新拍的数字，是把说明书里已写死的结构提到强制等级。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    allowed = {
        "L1.get_fed_funds_rate",
        "L4.get_ndx_pe_and_earnings_yield",
        "L5.get_qqq_technical_indicators",
    }

    class _V:
        def __init__(self, verdict): self.reasoned_verdict = verdict

    # 单段连续文字、只挂一条引用 —— 正是 20260725_232410 的失败形态，必须被拦下。
    single = orchestrator._validate_reasoned_verdict_refs(
        _V("宏观与微观拉锯，风险面占优，赔率偏不利 [L1.get_fed_funds_rate]。"), allowed
    )
    assert single and "at least 3 distinct citations" in single[0]

    # 两条也不够：说明书要的是三条理由。
    two = orchestrator._validate_reasoned_verdict_refs(
        _V("理由一 [L1.get_fed_funds_rate]；理由二 [L4.get_ndx_pe_and_earnings_yield]。"), allowed
    )
    assert two and "at least 3 distinct citations" in two[0]

    # 同一条引用重复三次不算三条理由（去重后仍是 1）。
    dup = orchestrator._validate_reasoned_verdict_refs(
        _V("一 [L1.get_fed_funds_rate] 二 [L1.get_fed_funds_rate] 三 [L1.get_fed_funds_rate]。"),
        allowed,
    )
    assert dup and "at least 3 distinct citations" in dup[0]

    # 三条不同引用 —— 通过。
    ok = orchestrator._validate_reasoned_verdict_refs(
        _V(
            "第一，利率压制估值 [L1.get_fed_funds_rate]；"
            "第二，估值安全垫薄 [L4.get_ndx_pe_and_earnings_yield]；"
            "第三，趋势质量差 [L5.get_qqq_technical_indicators]。"
        ),
        allowed,
    )
    assert ok == []

    # 引用越界仍然优先拦下（既有语义不得被新规则削弱）。
    illegal = orchestrator._validate_reasoned_verdict_refs(
        _V("一 [L1.get_fed_funds_rate] 二 [L4.get_ndx_pe_and_earnings_yield] 三 [L9.fake_ref]。"),
        allowed,
    )
    assert illegal and "outside evidence_index" in illegal[0]


def test_reasoned_verdict_tolerates_comma_joined_refs_inside_one_bracket(tmp_path: Path):
    """红灯：真实事故 run 20260728_110702——两条合法 ref 被逗号合并进同一个方括号，
    旧解析把整段当成一个 ref，两条都合法却被判"引用不在索引内"，终审两次尝试后整跑硬崩。

    这是 2026-07-27 把"至少一条引用"收紧为"至少三条不同引用"之后的第一次真实 run，
    收紧恰好把模型推向了"一个方括号塞多条"的写法。修法是解析容忍逗号合并（每一段仍要
    逐字合法），同时把计数改成"方括号组数 ≥ 3 且不同引用 ≥ 3"——后者比单纯数引用条数
    更贴近 final_adjudicator.md 原文，防止"一段文字里一个方括号塞三条"重新蒙混过关。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    allowed = {
        "L1.get_10y_real_rate",
        "L4.get_equity_risk_premium#level",
        "L3.get_advance_decline_line",
        "L5.get_obv_qqq",
    }

    class _V:
        def __init__(self, verdict): self.reasoned_verdict = verdict

    # 事故原文形态：合法 ref 被逗号合并。三个方括号组、四条不同引用 —— 必须放行。
    merged = orchestrator._validate_reasoned_verdict_refs(
        _V(
            "第一，实际利率与风险补偿同时紧 [L1.get_10y_real_rate, L4.get_equity_risk_premium#level]；"
            "第二，广度与量能背离 [L3.get_advance_decline_line, L5.get_obv_qqq]；"
            "第三，趋势质量存疑 [L5.get_obv_qqq]。"
        ),
        allowed,
    )
    assert merged == []

    # 容忍形状不等于放松合法性：合并串里混进越界 ref，仍须逐段拆开后拦下。
    illegal = orchestrator._validate_reasoned_verdict_refs(
        _V(
            "第一 [L1.get_10y_real_rate, L9.fake_ref]；"
            "第二 [L3.get_advance_decline_line]；"
            "第三 [L5.get_obv_qqq]。"
        ),
        allowed,
    )
    assert illegal and "outside evidence_index" in illegal[0] and "L9.fake_ref" in illegal[0]

    # 反向防线：一段连续文字、只有一个方括号却塞满三条合法 ref —— 正是收紧要堵的洞，
    # 不能因为"拆开后有三条不同引用"就放行。
    one_bracket = orchestrator._validate_reasoned_verdict_refs(
        _V(
            "宏观、广度与量能同时走弱，赔率不利 "
            "[L1.get_10y_real_rate, L3.get_advance_decline_line, L5.get_obv_qqq]。"
        ),
        allowed,
    )
    assert one_bracket and "3 separate [bracket] groups" in one_bracket[0]


def test_reasoned_verdict_flags_numbers_absent_from_stage_payload(tmp_path: Path):
    """T42②：判决正文里的百分数/小数必须逐字出现在终审实际收到的 payload 中。
    "报告里写的 2.3%，原始 payload 里找不找得到 2.3%"是身份比对，不是语义判断。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    allowed = {
        "L1.get_fed_funds_rate",
        "L4.get_ndx_pe_and_earnings_yield",
        "L5.get_qqq_technical_indicators",
    }

    class _V:
        def __init__(self, verdict): self.reasoned_verdict = verdict

    verdict = (
        "第一，实际利率 2.3% 压制估值 [L1.get_fed_funds_rate]；"
        "第二，估值分位 87.2% 偏高 [L4.get_ndx_pe_and_earnings_yield]；"
        "第三，趋势质量一般 [L5.get_qqq_technical_indicators]。"
    )
    source_text = json.dumps(
        {
            "governance_input": {
                "key_evidence_refs": {
                    "L1.get_fed_funds_rate": {"current_reading": "实际利率 2.3%"},
                    "L4.get_ndx_pe_and_earnings_yield": {"current_reading": "分位 87.2%"},
                }
            }
        },
        ensure_ascii=False,
    )

    assert orchestrator._validate_reasoned_verdict_refs(_V(verdict), allowed, source_text=source_text) == []

    fabricated = verdict.replace("2.3%", "9.9%")
    errors = orchestrator._validate_reasoned_verdict_refs(_V(fabricated), allowed, source_text=source_text)
    assert errors and "9.9%" in errors[0]

    # 不传 source_text 的既有调用点不启用数字存在性比对，行为不变。
    assert orchestrator._validate_reasoned_verdict_refs(_V(fabricated), allowed) == []


def test_final_conflict_responses_requires_retained_high_conflict_ids(tmp_path: Path):
    """T42③：终审必须用编号覆盖 thesis 保留的高严重度冲突——编号没出现就是没
    回应，不判回应对措辞（身份比对）。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    thesis = ThesisDraft.model_validate(
        {
            "environment_assessment": "环境偏紧。",
            "valuation_assessment": "估值偏高。",
            "timing_assessment": "趋势仍在。",
            "main_thesis": "中性偏谨慎。",
            "overall_confidence": "medium",
            "retained_conflicts": [
                {
                    "conflict_id": "TC1_restrictive_macro_vs_moderate_valuation",
                    "conflict_type": "rates_vs_valuation",
                    "severity": "high",
                    "description": "高利率与高估值并存。",
                    "implication": "估值压缩风险。",
                    "involved_layers": ["L1", "L4"],
                }
            ],
        }
    )

    def _final(*, conflict_refs=(), notes="保留风险边界。"):
        return FinalAdjudication(
            approval_status=ApprovalStatus.APPROVED_WITH_RESERVATIONS,
            final_stance="中性偏谨慎",
            confidence=Confidence.MEDIUM,
            must_preserve_risks=["估值压缩风险"],
            adjudicator_notes=notes,
            principal_contradiction={"contradiction_id": "rates_vs_valuation", "conflict_refs": list(conflict_refs)},
        )

    ok = _final(conflict_refs=["TC1_restrictive_macro_vs_moderate_valuation"])
    assert orchestrator._validate_final_conflict_responses(ok, thesis) == []

    missing = _final()
    errors = orchestrator._validate_final_conflict_responses(missing, thesis)
    assert errors and "TC1_restrictive_macro_vs_moderate_valuation" in errors[0]


def test_final_claim_ledger_is_code_built_and_stripped_from_model_answer(tmp_path: Path):
    """T54 批 6：claim_ledger 整本由代码重建（`_build_final_claim_ledger`），模型答卷里的
    claim_ledger（任何形状，含 20260728 事故那种裸列表）在归一化阶段直接摘除——
    不进契约校验，'猜错形状烧重试'的事故面从结构上消除。契约侧的裸列表宽容校验
    同步下线：直接 model_validate 裸列表现在必须报错（不再有形状迁就）。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    parsed = {
        "approval_status": "approved_with_reservations",
        "claim_ledger": [{"claim_id": "x", "claim_text": "模型编的台账"}],
    }

    normalized = orchestrator._normalize_payload("final", parsed)

    assert "claim_ledger" not in normalized

    base = {
        "approval_status": "approved_with_reservations",
        "final_stance": "中性偏谨慎",
        "confidence": "medium",
        "must_preserve_risks": ["估值压缩风险"],
        "adjudicator_notes": "保留跨层张力。",
        "reasoned_verdict": "略。" * 200,
    }
    entry = {
        "claim_id": "FINAL_CLAIM_1",
        "source_stage": "final",
        "claim_text": "实际利率处于极端高位，压制估值。",
        "claim_type": "market_state",
    }
    # 裸列表宽容校验已随批 6 下线：直接对契约喂裸列表必须报错。
    with pytest.raises(ValidationError):
        FinalAdjudication.model_validate({**base, "claim_ledger": [entry]})
    # 代码重建的合法对象形态不受影响（checkpoint 复用路径）。
    normal = FinalAdjudication.model_validate({**base, "claim_ledger": {"entries": [entry]}})
    assert [item.claim_id for item in normal.claim_ledger.entries] == ["FINAL_CLAIM_1"]


def test_final_prompt_no_longer_asks_model_to_fill_claim_ledger():
    """T54 批 6 提示词同步：模型侧填写要求已撤——不再教形状，明示代码装配。"""
    text = (
        Path(__file__).resolve().parents[1]
        / "src" / "agent_analysis" / "prompts" / "final_adjudicator.md"
    ).read_text(encoding="utf-8")

    assert "形状是硬约束" not in text
    assert "不用你输出" in text


def test_final_stage_retries_when_reasoned_verdict_cites_illegal_ref(tmp_path: Path):
    """零引用之外的另一半：引用了不在 evidence_index 里的 ref，同样必须重试，
    不能靠 `_validate_stage_evidence_refs`（只查结构化字段）蒙混过关。"""
    base = {
        "approval_status": "approved_with_reservations",
        "final_stance": "中性偏谨慎",
        "confidence": "medium",
        "must_preserve_risks": ["估值压缩风险"],
        "blocking_issues": [],
        "adjudicator_notes": "保留风险边界。",
    }
    illegal_ref_verdict = _VALID_REASONED_VERDICT.replace(
        "[L1.get_fed_funds_rate]", "[L9.fabricated_metric]", 1
    )
    engine = SequencedFakeLLMEngine({
        "final_adjudicator": [
            json.dumps({**base, "reasoned_verdict": illegal_ref_verdict}, ensure_ascii=False),
            json.dumps({**base, "reasoned_verdict": _VALID_REASONED_VERDICT}, ensure_ascii=False),
        ]
    })
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )
    allowed = {"L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield", "L5.get_qqq_technical_indicators"}

    result = orchestrator._run_stage(
        stage_key="final",
        stage_name="final_adjudicator",
        model_cls=FinalAdjudication,
        payload={"example": "payload"},
        validator=lambda candidate: orchestrator._validate_reasoned_verdict_refs(candidate, allowed),
    )
    diagnostics = json.loads((tmp_path / "llm_stage_diagnostics.json").read_text(encoding="utf-8"))

    assert engine.calls["final_adjudicator"] == 2
    assert result.reasoned_verdict == _VALID_REASONED_VERDICT
    assert "outside evidence_index" in diagnostics["stages"]["final_adjudicator"]["errors"][0]["message"]


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


class _RealParsingFakeLLMEngine:
    """第一次返回坏 JSON、第二次返回好 JSON；`extract_json` 与 `diagnose_json_error`
    都委托给真正的 `LLMEngine`（而不是玩具版 `json.loads`），保证 parse_error 的
    判定与错误定位路径和生产环境逐字节一致。
    """

    def __init__(self, broken_payload: str):
        from agent_analysis.llm_engine import LLMEngine

        self.broken_payload = broken_payload
        self.calls = 0
        self.prompts = []
        self._real_engine = LLMEngine(available_models=[])

    def call_with_fallback(self, prompt, stage_name=""):
        self.calls += 1
        self.prompts.append(prompt)
        return self.broken_payload if self.calls == 1 else '{"value": "ok"}'

    def extract_json(self, text, stage):
        return self._real_engine.extract_json(text, stage)

    def diagnose_json_error(self, text):
        return self._real_engine.diagnose_json_error(text)

    def get_token_report(self):
        return {}


def test_run_stage_parse_error_feedback_locates_real_error_not_tail(tmp_path: Path):
    """T47 红灯：真实事故 run 20260731_002156——响应第 3 行 fact_summary 内嵌
    未转义 ASCII 双引号导致解析失败，但旧重试反馈写"请检查最后未闭合的数组、
    对象或字符串"并附末尾 400 字符（末尾语法完好），把错误位置指错了。

    修复后：反馈必须以真实 JSON 语法错误位置为主（错误信息 + 行:列 + 出错点
    前后窗口），末尾片段只作次要参考。
    """
    padding = "y" * 600
    broken_payload = (
        '{\n'
        '  "value": "ok",\n'
        '  "fact_summary": "材料称 "通胀见顶" 后市场反弹",\n'
        '  "padding": "' + padding + '"\n'
        '}'
    )
    # 红灯前提不是凭空断言：这段响应真的会让标准 json.loads 在第 3 行报错，
    # 且响应总长超过 400 字符——末尾片段语法完好、看不到出错位置，
    # 旧反馈只附末尾等于把模型指向一个没有错的地方。
    with pytest.raises(json.JSONDecodeError) as exc_info:
        json.loads(broken_payload)
    assert exc_info.value.lineno == 3
    assert len(broken_payload) > 400

    engine = _RealParsingFakeLLMEngine(broken_payload)
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
    assert "JSON 语法错误定位" in second_prompt, (
        "修复后重试反馈必须给出真实解析错误定位，而不是只附末尾片段"
    )
    assert "第 3 行" in second_prompt, (
        "错误发生在第 3 行（fact_summary 内嵌未转义双引号），反馈必须带上真实行号"
    )
    assert "请检查最后未闭合的数组、对象或字符串" not in second_prompt, (
        "拿到真实错误定位时，不许再保留这句把模型指向末尾的误导措辞"
    )


def test_run_stage_parse_error_feedback_unclosed_tail_still_points_near_end(tmp_path: Path):
    """末尾真的未闭合时，新定位必须仍然指向末尾附近——行为不能比旧的末尾片段差。"""
    sentinel = "BROKEN_TAIL_MARKER_FOR_TEST"
    padding = "x" * 600
    broken_payload = (
        "{\n  \"value\": \"partial\",\n  \"more\": [\n    "
        + padding
        + "\n    \"unterminated string  // "
        + sentinel
    )
    with pytest.raises(json.JSONDecodeError):
        json.loads(broken_payload)

    engine = _RealParsingFakeLLMEngine(broken_payload)
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
    assert "JSON 语法错误定位" in second_prompt
    assert sentinel in second_prompt, (
        "末尾未闭合时，错误定位窗口必须覆盖末尾哨兵——不能把真实在末尾的错误指到别处"
    )


def test_run_stage_parse_error_feedback_falls_back_to_tail_when_no_locatable_error(tmp_path: Path):
    """回退路径锁死：响应是合法 JSON 但不是对象（例如数组）时，extract_json 返回
    非 dict 同样走 parse_error 分支，但拿不到 JSONDecodeError——反馈必须回退到
    原有末尾片段行为，行为与改前一致。"""
    sentinel = "TAIL_FALLBACK_MARKER_FOR_TEST"
    padding = "z" * 600
    broken_payload = '["' + padding + '", "' + sentinel + '"]'
    # 红灯前提：这段响应是合法 JSON（数组），json.loads 不报错——没有可定位的语法错误。
    assert isinstance(json.loads(broken_payload), list)

    engine = _RealParsingFakeLLMEngine(broken_payload)
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
    assert "请检查最后未闭合的数组、对象或字符串" in second_prompt, (
        "拿不到真实错误定位时必须回退到原有末尾片段行为"
    )
    assert sentinel in second_prompt, "回退路径仍须把末尾片段带给模型"


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


class _CounterThesisFieldNameFakeLLMEngine(FakeLLMEngine):
    """模拟真实事故（run 20260724_223804）里那种"严格照 prompt 抄字段名"的模型：
    prompt 正文里没有逐字给出 `hypothesis_text` / `falsification_conditions` 时，
    它会像真实事故一样自己猜字段名（猜成 summary+statement、falsification_signals）；
    prompt 写清楚了，它就照抄。

    这个 fake engine 特意读取真正传入的 prompt 文本（由 `_compose_prompt` 拼接，
    其中包含 `counter_thesis.md` 的真实内容和重试反馈），而不是无条件返回固定
    canned 响应——只有这样，"counter_thesis.md 修复前后跑同一条测试"才能真实地
    由红转绿，而不是靠改测试本身的期望值。

    副作用（如实复现，不是 bug）：第一次尝试失败后，重试反馈文本里会带上上一次
    pydantic 报错原文（其中恰好含有 `hypothesis_text` 字样），这与真实事故的 attempt 2
    行为一致——模型从报错文本里学会了 `hypothesis_text`，但仍然猜错了
    `falsification_conditions`，因为第一次报错从未触达那条合约。
    """

    def __init__(self):
        super().__init__({})
        self.calls: dict[str, int] = {}

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None):
        self.calls[stage_name] = self.calls.get(stage_name, 0) + 1
        teaches_hypothesis_text = "hypothesis_text" in prompt
        teaches_falsification_conditions = "falsification_conditions" in prompt

        hypothesis: dict = {
            "hypothesis_id": "cth_01",
            "source": "counter_thesis",
            "support_evidence_refs": ["L1.get_fed_funds_rate"],
            "counter_evidence_refs": [],
            "diagnostic_evidence_refs": ["L1.get_fed_funds_rate"],
        }
        if teaches_hypothesis_text:
            hypothesis["hypothesis_text"] = "反方核心论点：盈利加速对冲利率压力，当前回调是布局窗口。"
        else:
            # 真实事故 attempt 1：模型不知道字段叫 hypothesis_text，猜成 summary/statement。
            hypothesis["summary"] = "反方核心论点：盈利加速对冲利率压力，当前回调是布局窗口。"
            hypothesis["statement"] = "详细展开的论证文本。"
        if teaches_falsification_conditions:
            hypothesis["falsification_conditions"] = ["10Y实际利率维持高位且盈利修正转负。"]
        else:
            # 真实事故 attempt 2：模型猜成 falsification_signals，falsification_conditions 留空。
            hypothesis["falsification_signals"] = ["10Y实际利率维持高位且盈利修正转负。"]

        payload = {
            "hypotheses": [hypothesis],
            "principal_counterargument": "反方论点的一句话概述。",
            "cannot_establish": [],
        }
        return json.dumps(payload, ensure_ascii=False)


def test_counter_thesis_field_names_reproduce_real_incident_until_prompt_documents_them(tmp_path: Path):
    """真实事故复现（run 20260724_223804，counter_thesis 两次尝试全部失败）：

    - attempt 1：`hypotheses.0.hypothesis_text` 缺失 —— pydantic 结构校验直接报错。
    - attempt 2：`falsification_conditions must not be empty` —— 合约校验报错。

    根因不是模型能力问题：`_validate_counter_thesis_draft` 和 `CompetingHypothesis`
    要求的字段，`counter_thesis.md` 从未逐字写过，模型只能凭经验猜（猜成
    summary/statement、falsification_signals），两次都没猜中，约 28 万 prompt token
    被两次尝试烧光，最终退回确定性兜底稿。

    本测试用一个"严格照 prompt 抄字段名"的 fake engine：prompt 正文没写全字段名时，
    它复现真实事故的错误猜测；写全了，它就照抄产出合法结构。因此：
    - **修复 `counter_thesis.md` 之前**跑这条测试：`_run_stage` 因两次尝试都不合法、
      耗尽重试后抛 `RuntimeError`（红，忠实复现两条真实错误）。
    - **修复之后**：prompt 已经逐字教会字段名，第一次尝试就通过校验（绿）。
    """
    engine = _CounterThesisFieldNameFakeLLMEngine()
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=engine,
        max_node_retries=2,
    )
    allowed_refs = {"L1.get_fed_funds_rate"}

    result = orchestrator._run_stage(
        stage_key="counter_thesis",
        stage_name="counter_thesis",
        model_cls=CounterThesisDraft,
        payload={"allowed_evidence_refs": sorted(allowed_refs)},
        validator=lambda candidate: orchestrator._validate_counter_thesis_draft(candidate, allowed_refs),
    )

    # 字段名教对了，模型第一次就能产出合法结构，不需要靠重试抽奖。
    assert engine.calls["counter_thesis"] == 1
    assert result.hypotheses[0].hypothesis_text
    assert result.hypotheses[0].falsification_conditions


def test_counter_thesis_deterministic_fallback_surfaces_in_competition_fallback_warnings(
    tmp_path: Path, monkeypatch
):
    """反方降级可见度对齐 reviser：counter_thesis 两次尝试失败退回确定性兜底稿时，
    此前只留痕在 counter_thesis.json 自己的 prompt_input_audit 里，终审判决书完全看
    不出这次反方论证其实是模板凑数（不像 reviser 那样有 degraded_fallback 显式标记并
    传导进 quality_gate）。这条测试锁定修复后的行为：兜底发生时，
    `HypothesisCompetition.fallback_warnings` 必须携带一条可识别的信号，供下游
    （_run_analysis 里紧邻 reviser_degraded_unrevised_thesis 的那段代码）转成终审质量
    闸门备注。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    bridge_v2 = BridgeMemo(
        bridge_type="feedback_bridge_v2",
        layers_connected=["L1", "L4"],
        implication_for_ndx="保留张力。",
        principal_contradiction={
            "contradiction_id": "rates_vs_valuation",
            "summary": "高利率与高估值并存。",
            "why_principal": "决定估值承压程度。",
            "dominant_side": "利率约束。",
            "secondary_side": "盈利韧性。",
            "price_reflection": "partially_reflected",
            "evidence_refs": ["L1.get_fed_funds_rate"],
        },
    )
    # 模拟 counter_thesis 两次尝试全部失败、走 _build_deterministic_counter_thesis 兜底
    # 的真实路径：直接让 _build_counter_thesis 产出一个带 fallback_reason 的 draft，
    # 不需要真的驱动两次 LLM 失败重试。
    fallback_draft = CounterThesisDraft(
        hypotheses=[],
        prompt_input_audit={"fallback_reason": "counter_thesis failed after 2 attempts: ..."},
    )
    monkeypatch.setattr(orchestrator, "_build_counter_thesis", lambda **_: fallback_draft)

    competition = orchestrator._build_hypothesis_competition(
        synthesis_packet=SynthesisPacket(
            evidence_index={"L1.get_fed_funds_rate": {"evidence_ref": "L1.get_fed_funds_rate"}}
        ),
        bridge_v2=bridge_v2,
        investigation_reports=[],
        effective_date="2026-07-25",
    )

    assert "counter_thesis_deterministic_fallback" in competition.fallback_warnings


def test_counter_thesis_success_does_not_add_fallback_warning(tmp_path: Path, monkeypatch):
    """反面用例：counter_thesis 正常产出（无 fallback_reason）时，不能被误标成降级。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    bridge_v2 = BridgeMemo(
        bridge_type="feedback_bridge_v2",
        layers_connected=["L1", "L4"],
        implication_for_ndx="保留张力。",
    )
    healthy_draft = CounterThesisDraft(hypotheses=[], prompt_input_audit={})
    monkeypatch.setattr(orchestrator, "_build_counter_thesis", lambda **_: healthy_draft)

    competition = orchestrator._build_hypothesis_competition(
        synthesis_packet=SynthesisPacket(evidence_index={}),
        bridge_v2=bridge_v2,
        investigation_reports=[],
        effective_date="2026-07-25",
    )

    assert "counter_thesis_deterministic_fallback" not in competition.fallback_warnings


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


def _t35_erp_test_packet():
    """真实事故复现材料：真实 run 20260730_114704 的 `analysis_packet.json` 里
    `L4.get_damodaran_us_implied_erp` 是 availability=available、source_tier=official、
    `value.erp_t12m_adjusted_payout=4.3`——字段真实存在、取数成功、来源官方，但这个函数
    从未构造过 MetricAuthority（L4 17 个 get_* 函数里 10 个都没有）。"""
    packet = _mock_packet()
    packet.raw_data["L4"]["get_damodaran_us_implied_erp"] = {
        "value": {"erp_t12m_adjusted_payout": 4.3},
        "data_quality": {
            "availability": "available",
            "source_name": "Damodaran implied ERP",
            "source_tier": "official",
            "effective_date": "2026-04-24",
        },
    }
    return packet


def _t35_schema_guard_report(orchestrator: "VNextOrchestrator", packet, evidence_ref: str, conflict_id: str):
    bridge = BridgeMemo.model_validate(
        {
            "bridge_type": "macro_valuation",
            "layers_connected": ["L1", "L4"],
            "typed_conflicts": [
                {
                    "conflict_id": conflict_id,
                    "conflict_type": "valuation_discount_rate",
                    "severity": "high",
                    "description": "隐含股权风险溢价与实际利率对折现率的含义相互矛盾。",
                    "implication": "估值压缩风险的定价存在分歧。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": [evidence_ref],
                }
            ],
            "implication_for_ndx": "保留张力。",
        }
    )
    return orchestrator._run_schema_guard(
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
        Critique.model_validate({"overall_assessment": "测试。", "revision_direction": "测试。"}),
        RiskBoundaryReport.model_validate({"must_preserve_risks": ["测试风险"]}),
    )


def test_schema_guard_treats_real_value_field_without_metric_authority_as_valid_ref(tmp_path: Path):
    """红灯：真实事故 run 20260730_114704——schema_guard 报
    `BridgeMemo[0].typed_conflicts[TC1_...].evidence_refs invalid:
    L4.get_damodaran_us_implied_erp#erp_t12m_adjusted_payout`。核过原始产物：字段真实
    存在、取数成功、来源官方。它被判非法的唯一原因是 `valid_evidence_refs` 的子引用
    来源只读 `_field_authority_from_payload`（人工登记的 MetricAuthority 表），而这个
    函数从未登记过 MetricAuthority——"字段存不存在"（身份）被"这个字段够不够格支撑
    强结论"（权限分级）那张人工表冒充了。方案 A：valid_evidence_refs 的子引用来源改为
    MetricAuthority 键与 raw_payload["value"] 真实顶层键的并集，闸门变回纯粹的身份比对。
    """
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    packet = _t35_erp_test_packet()
    real_ref = "L4.get_damodaran_us_implied_erp#erp_t12m_adjusted_payout"
    report = _t35_schema_guard_report(orchestrator, packet, real_ref, "TC1_erp_vs_real_rate")
    joined = "\n".join(report.consistency_issues)
    assert real_ref not in joined, joined


def test_schema_guard_still_rejects_ref_to_field_that_does_not_exist(tmp_path: Path):
    """反例：闸门没有被放松成"什么都放行"——`value` 里真的不存在的字段名仍须判非法，
    否则就不是身份比对而是彻底放行。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    packet = _t35_erp_test_packet()
    fake_ref = "L4.get_damodaran_us_implied_erp#does_not_exist_field"
    report = _t35_schema_guard_report(orchestrator, packet, fake_ref, "TC2_fabricated_field")
    joined = "\n".join(report.consistency_issues)
    assert fake_ref in joined, joined
    assert "evidence_refs invalid" in joined


def test_field_authority_from_payload_byte_identical_for_registered_metric_authority_payload(tmp_path: Path):
    """钉住红线：修复①绝不能改动②`_field_authority_from_payload` 对已登记 MetricAuthority
    payload 的返回值——一个字都不能变。现有 7 个已登记函数的权限是统一的，一旦凭空塞入
    `audit_only`，这 7 个会集体被判 mixed_field_authority 而降级（orchestrator.py:2891/
    2898，`field_usages = self._field_authority_usages(field_authority)` /
    `mixed_field_authority = len(field_usages) > 1`）。这里直接比对返回值逐字节相同，
    并确认 mixed_field_authority 没有被新引入。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    raw_payload = {
        "value": {
            "level": 5.25,
            "trend": "rising",
            "MetricAuthority": {
                "level": {"usage": "core_allowed", "authority": "official_fact"},
                "trend": {"usage": "core_allowed", "authority": "official_fact"},
            },
        },
        "data_quality": {"source_tier": "official"},
    }
    expected = {
        "level": {"usage": "core_allowed", "authority": "official_fact"},
        "trend": {"usage": "core_allowed", "authority": "official_fact"},
    }
    authority = orchestrator._field_authority_from_payload(raw_payload)
    assert authority == expected
    usages = orchestrator._field_authority_usages(authority)
    assert usages == {"core_allowed"}
    assert len(usages) == 1  # mixed_field_authority 不应被新引入


def test_verify_claim_entry_falls_back_to_parent_authority_for_legal_unregistered_field_ref(tmp_path: Path):
    """回落：合法但没有字段级 passport 的 ref（真实存在的字段，没有 MetricAuthority 登记）
    必须拿到父级 passport 的权限，不能被判成"查无此证据"而静默降级/阻断。
    `_build_evidence_registry` 只对 MetricAuthority 登记过的字段建字段级 passport
    （orchestrator.py:2930 `for field, field_rule in field_authority.items():`）——放行
    更多真实字段之后，这些字段在 registry.passports 里没有对应条目，必须靠父级
    authority_model["real_value_fields"] 做身份比对回落，而不是让
    `_resolve_claim_evidence_ref` 直接判它不存在。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    registry = EvidenceRegistry(
        effective_date="2026-07-30",
        passports={
            "L4.get_damodaran_us_implied_erp": EvidencePassport(
                evidence_id="L4.get_damodaran_us_implied_erp",
                evidence_kind="data",
                source_tier="official",
                authority_model={"real_value_fields": ["erp_t12m_adjusted_payout"]},
                verified=True,
            ),
        },
    )
    entry = ClaimLedgerEntry(
        claim_id="claim:test:erp-field-fallback",
        source_stage="final",
        claim_text="隐含股权风险溢价（税后支付调整口径）约为 4.3%。",
        claim_type="valuation",
        evidence_refs=["L4.get_damodaran_us_implied_erp#erp_t12m_adjusted_payout"],
        counter_evidence_refs=["L1.get_10y_real_rate"],
        inference_steps=["ERP 口径核验"],
        falsification_conditions=["ERP 口径被重新定义"],
    )
    result = orchestrator._verify_claim_entry(entry, registry)
    assert "unverifiable_evidence_refs" not in result.downgrade_reason
    assert result.authority_status != "blocked"
    assert result.verified is True, result.downgrade_reason


def test_verify_claim_entry_does_not_fall_back_for_fabricated_field_name(tmp_path: Path):
    """反例：父级存在，但字段名是幻觉/笔误——身份比对不通过，不能被"回落"洗白成合法引用。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    registry = EvidenceRegistry(
        effective_date="2026-07-30",
        passports={
            "L4.get_damodaran_us_implied_erp": EvidencePassport(
                evidence_id="L4.get_damodaran_us_implied_erp",
                evidence_kind="data",
                source_tier="official",
                authority_model={"real_value_fields": ["erp_t12m_adjusted_payout"]},
                verified=True,
            ),
        },
    )
    entry = ClaimLedgerEntry(
        claim_id="claim:test:erp-field-fabricated",
        source_stage="final",
        claim_text="一个编造出来的字段。",
        claim_type="valuation",
        evidence_refs=["L4.get_damodaran_us_implied_erp#totally_made_up_field"],
        counter_evidence_refs=["L1.get_10y_real_rate"],
        inference_steps=["测试"],
        falsification_conditions=["测试"],
    )
    result = orchestrator._verify_claim_entry(entry, registry)
    assert (
        "unverifiable_evidence_refs:L4.get_damodaran_us_implied_erp#totally_made_up_field"
        in result.downgrade_reason
    )


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
    # 2026-07-30 用户裁决：降级措辞检查整条删除（先后两个实现都在真实 run 上误伤合格
    # 产出），保证改由报告渲染承担——见 tests/test_wo_r1_reporter.py 的
    # test_weak_source_labelling_is_code_driven_not_model_worded。这里验证的是"不再拦"：
    # 正文一个降级词都没有、且全部被引卡都属弱来源，也不应产生任何错误。
    assert validate(no_caveat, allowed_ids=allowed, effective_date="2026-07-19", title_only_majority=False) == []
    assert validate(
        no_caveat, allowed_ids=allowed, effective_date="2026-07-19",
        title_only_majority=True, downgrade_required_ids=set(allowed),
    ) == []

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
    # 弱来源卡不带任何降级措辞，也不再产生降级类报错——保证已移交报告渲染。
    # （该夹具正文短且含"必然改变市场定价"，仍会触发长度与禁止型规则，那两条是保留的。）
    assert not [
        err
        for err in validate(
            weak_without_attribution,
            allowed_ids=allowed,
            effective_date="2026-07-19",
            title_only_majority=False,
            downgrade_required_ids={"event_aaa11111"},
        )
        if "downgrade" in err or "caveat" in err or "降级" in err
    ]

    attributed = EventSectionSummary.model_validate({
        **weak_without_attribution.model_dump(),
        "summary_text": (
                "据报道，某事件可能改变市场定价，另一事件提供补充线索；据报道，两张卡共同提出了政策路径、"
            "盈利兑现与风险偏好能否同步变化的问题，但这些都只是待数据确认的线索，不能据此推导指数方向。"
            " [card:event_aaa11111] [card:event_bbb22222]"
            "以上事件材料不构成主证据，判断以数据层为准。"
        ),
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


# ── T47 C6 装配点：④ 去预置 state / 预置跨层结论 ──

def test_layer_stage_payload_purifies_preloaded_state(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = AnalysisPacket(
        meta={"data_date": "2026-04-28"},
        raw_data={},
        facts_by_layer={
            "L1": {
                "state": "restrictive",
                "summary": "L1状态: 流动性偏紧。关键事实: 实际利率 1.95%。缺口=信用利差未读。",
                "key_metrics": ["get_10y_real_rate"],
            }
        },
    )
    context = orchestrator._build_context_brief(packet)

    payload = orchestrator._build_layer_stage_payload(packet, context, "L1")

    assert "state" not in payload["layer_facts"]
    assert not payload["layer_facts"]["summary"].startswith("状态:")
    assert payload["layer_facts"]["summary"].startswith("关键事实:")
    assert "缺口=信用利差未读。" in payload["layer_facts"]["summary"]

    # 落盘 analysis_packet 仍含 state（审计本体不动）
    orchestrator._save_json("analysis_packet.json", packet)
    saved = json.loads((tmp_path / "analysis_packet.json").read_text(encoding="utf-8"))
    assert saved["facts_by_layer"]["L1"]["state"] == "restrictive"
    assert "L1状态: 流动性偏紧。" in saved["facts_by_layer"]["L1"]["summary"]


def test_run_bridge_payload_drops_event_refs_and_purifies_cross_layer_signals(
    tmp_path: Path, monkeypatch
):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    packet = AnalysisPacket(
        meta={"data_date": "2026-04-28"},
        raw_data={},
        event_refs={"event:news_001": {"title": "事件新闻"}},
    )
    context = ContextBrief(
        data_summary="data",
        task_description="task",
        layer_highlights={"L1": ["流动性偏紧"]},
        apparent_cross_layer_signals=["预置跨层信号"],
        special_attention=["原有关注"],
    )
    captured = {}

    def fake_run_stage(self, **kwargs):
        captured.update(kwargs.get("payload") or {})
        return BridgeMemo(
            bridge_type="macro_valuation",
            layers_connected=["L1", "L4"],
            implication_for_ndx="fine",
        )

    monkeypatch.setattr(VNextOrchestrator, "_run_stage", fake_run_stage)

    orchestrator._run_bridge(packet, context, [])

    assert "event_refs" not in captured
    assert captured["context_brief"]["apparent_cross_layer_signals"] == []
    assert captured["context_brief"]["layer_highlights"] == {}
    assert captured["context_brief"]["special_attention"] == ["检查高严重度冲突是否被完整保留。"]
    assert captured["context_brief"]["data_summary"] == "data"
    assert captured["context_brief"]["task_description"] == "task"


def test_validate_bridge_memo_v2_rejects_event_prefixed_evidence_refs(tmp_path: Path):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    bridge_with_event_ref = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        typed_conflicts=[
            TypedConflict(
                conflict_id="event_backed_conflict",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="冲突描述。",
                mechanism="事件不应作为证据。",
                implication="必须保留。",
                involved_layers=["L1", "L4"],
                evidence_refs=["event:news_001"],
                falsifiers=["正式数据出现。"],
            )
        ],
        implication_for_ndx="fine",
    )

    errors = orchestrator._validate_bridge_memo_v2(bridge_with_event_ref)

    assert any("事件不得作为 evidence_ref" in error for error in errors)

    bridge_ok = BridgeMemo(
        bridge_type="macro_valuation",
        layers_connected=["L1", "L4"],
        typed_conflicts=[
            TypedConflict(
                conflict_id="ordinary_conflict",
                conflict_type="valuation_discount_rate",
                severity="high",
                description="冲突描述。",
                mechanism="正式数据支撑。",
                implication="必须保留。",
                involved_layers=["L1", "L4"],
                evidence_refs=["L1.get_fed_funds_rate"],
                falsifiers=["正式数据出现。"],
            )
        ],
        implication_for_ndx="fine",
    )

    assert orchestrator._validate_bridge_memo_v2(bridge_ok) == []


# ── T47 C6 装配点：⑥ 受控调查材料截断标注 + 立场字段剥离 ──

def test_controlled_investigation_material_strips_stance_fields_and_marks_truncation(
    tmp_path: Path,
):
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=FakeLLMEngine({}),
    )
    ref = "layer_cards/L1.json"
    path = tmp_path / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "dominant_side": "利率压力。",
                "action_implication": "保留风险边界。",
                "action_constraint": "不支持重仓",
                "仓位事实": "保证金仓位处于低位",  # 合法事实键，按白名单规则不得误删
                "rates_block": "实际利率约束" + "甲" * 6000,
                "unrelated": "不相关材料",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    materials = orchestrator._read_allowed_context_notes(
        [ref],
        max_refs=1,
        question="实际利率能确认什么？",
    )

    assert len(materials) == 1
    material = materials[0]
    assert "dominant_side" not in material
    assert "action_implication" not in material
    assert "action_constraint" not in material
    assert "不支持重仓" not in material
    assert "_stance_fields_stripped" in material
    assert "_material_truncated" in material
    # 白名单外的事实键必须保留：直接测剥离函数（材料截断可能把无关键切出视野）
    stripped, removed = orchestrator._strip_material_stance_fields(
        {"dominant_side": "x", "仓位事实": "保证金仓位处于低位"}
    )
    assert removed == ["dominant_side"]
    assert stripped["仓位事实"] == "保证金仓位处于低位"
    assert material.endswith("[/M1]")
    assert len(material) <= 4000
    # 材料块本体必须是可解析的完整 JSON（PC-06 机器检查要求）
    import re as _re
    body = _re.search(r"\[M1\][^\n]*\n(.*?)\[/M1\]", material, _re.S).group(1)
    assert json.loads(body)["_material_truncated"] is True



# ---------------------------------------------------------------------------
# T54 批 4：编号体系——typed_conflicts 权威、id 代码重发、legacy 反向重建
# （规范：investigation_reports/20260817_T54_文书字段代码装配/02_编号规范.md）
# ---------------------------------------------------------------------------

def _bridge_conflicts_payload(conflicts, typed_conflicts, **extra):
    payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L4"],
        "conflicts": conflicts,
        "typed_conflicts": typed_conflicts,
        "implication_for_ndx": "保留张力。",
    }
    payload.update(extra)
    return payload


def _typed(conflict_id, conflict_type="rate_vs_valuation", severity="high", refs=None):
    return {
        "conflict_id": conflict_id,
        "conflict_type": conflict_type,
        "severity": severity,
        "description": f"{conflict_type} 描述",
        "implication": f"{conflict_type} 影响",
        "evidence_refs": refs if refs is not None else ["L1.get_fed_funds_rate", "L4.get_ndx_pe_and_earnings_yield"],
    }


def test_bridge_typed_conflicts_authoritative_ids_reissued_legacy_rebuilt(tmp_path: Path):
    """typed 是权威容器：id 一律重发 TC_01…；legacy conflicts 由 typed 反向重建
    （08-17 的"同长同 type 对齐"止血被本规范取代）；模型原 id 进 normalization_notes。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    payload = _bridge_conflicts_payload(
        conflicts=[
            {"conflict_id": "描述性甲", "conflict_type": "rate_vs_valuation", "severity": "high", "description": "d1"},
            {"conflict_id": "描述性乙", "conflict_type": "growth_vs_policy", "severity": "medium", "description": "d2"},
        ],
        typed_conflicts=[_typed("模型编的id")],
    )

    normalized = orchestrator._normalize_payload("bridge", payload)

    assert [c["conflict_id"] for c in normalized["typed_conflicts"]] == ["TC_01"]
    # legacy 反向重建：以 typed 为准（模型自填的两条 legacy 被权威容器取代），id 同源。
    assert len(normalized["conflicts"]) == 1
    legacy = normalized["conflicts"][0]
    assert legacy["conflict_id"] == "TC_01"
    assert legacy["conflict_type"] == "rate_vs_valuation"
    assert legacy["severity"] == "high"
    assert legacy["description"] == "rate_vs_valuation 描述"
    # involved_layers 从 evidence_refs 前缀派生。
    assert legacy["involved_layers"] == ["L1", "L4"]
    assert normalized["typed_conflicts"][0]["involved_layers"] == ["L1", "L4"]
    notes = normalized["normalization_notes"]
    assert "legacy_conflicts_rebuilt_from_typed_conflicts" in notes
    assert any(note.startswith("conflict_ids_reassigned_by_code:") and "模型编的id" in note for note in notes)


def test_bridge_id_reissue_remaps_contradiction_references(tmp_path: Path):
    """重发 id 后，同一 payload 内对旧 id 的精确匹配引用必须重接：
    principal/secondary contradiction 的 id 与 conflict_refs、price_reflection_map.target。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    payload = _bridge_conflicts_payload(
        conflicts=[],
        typed_conflicts=[_typed("旧id甲"), _typed("旧id乙", conflict_type="growth_vs_policy", severity="medium")],
        principal_contradiction={
            "contradiction_id": "旧id甲",
            "conflict_refs": ["旧id甲"],
            "summary": "主要矛盾",
            "evidence_refs": ["L1.get_fed_funds_rate"],
        },
        secondary_contradictions=[{"contradiction_id": "旧id乙", "summary": "次要矛盾"}],
        price_reflection_map=[{"target": "旧id甲", "reflected_state": "partially_reflected", "category": "rates"}],
    )

    normalized = orchestrator._normalize_payload("bridge", payload)

    assert normalized["principal_contradiction"]["contradiction_id"] == "TC_01"
    assert normalized["principal_contradiction"]["conflict_refs"] == ["TC_01"]
    assert normalized["secondary_contradictions"][0]["contradiction_id"] == "TC_02"
    rate_entries = [e for e in normalized["price_reflection_map"] if e.get("target") == "TC_01"]
    assert rate_entries and rate_entries[0]["category"] == "rates"


def test_bridge_resonance_and_transmission_ids_reissued(tmp_path: Path):
    """chain_id/path_id 由代码按序重发（RC_01…/TP_01…），模型自填 id 不保留。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    payload = _bridge_conflicts_payload(
        conflicts=[],
        typed_conflicts=[_typed("TC_01")],
        resonance_chains=[
            {
                "chain_id": "模型链id",
                "description": "共振",
                "involved_layers": ["L1", "L4"],
                "evidence_refs": ["L1.get_fed_funds_rate"],
                "confirming_indicators": ["期限利差"],
                "mechanism": "m",
                "implication": "i",
                "falsifiers": ["f"],
            }
        ],
        transmission_paths=[
            {"path_id": "p1", "source_layer": "L1", "target_layer": "L4", "mechanism": "m1", "evidence_refs": ["L1.get_fed_funds_rate"], "implication": "i1"},
            {"path_id": "p2", "source_layer": "L4", "target_layer": "L5", "mechanism": "m2", "evidence_refs": ["L1.get_fed_funds_rate"], "implication": "i2"},
        ],
    )

    normalized = orchestrator._normalize_payload("bridge", payload)

    assert [c["chain_id"] for c in normalized["resonance_chains"]] == ["RC_01"]
    assert [p["path_id"] for p in normalized["transmission_paths"]] == ["TP_01", "TP_02"]


def test_counter_thesis_hypothesis_ids_and_source_are_code_assembled(tmp_path: Path):
    """counter 假说的 hypothesis_id 由代码发放（`_stable_hypothesis_id` 内容哈希，
    同文同 id、幂等），source 恒为 counter_thesis；模型自填 id 不保留。"""
    response = {
        "hypotheses": [
            {
                "hypothesis_id": "hyp_custom_模型编的",
                "hypothesis_text": "反方解释：趋势证据说明市场可能已部分消化利率压力。",
                "source": "bridge_v2",
                "support_evidence_refs": ["L5.get_qqq_technical_indicators"],
                "counter_evidence_refs": ["L1.get_fed_funds_rate"],
                "diagnostic_evidence_refs": ["L5.get_qqq_technical_indicators"],
                "cannot_explain": ["不能证明估值便宜。"],
                "falsification_conditions": ["趋势跌破关键均线。"],
            }
        ],
        "principal_counterargument": "趋势证据可能说明部分压力已被消化。",
        "cannot_establish": [],
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
    bridge_v2 = BridgeMemo(
        bridge_type="feedback_bridge_v2", layers_connected=["L1", "L5"], implication_for_ndx="保留张力。"
    )

    draft = orchestrator._build_counter_thesis(
        synthesis_packet=synthesis_packet,
        bridge_v2=bridge_v2,
        investigation_reports=[],
    )

    expected_id = orchestrator._stable_hypothesis_id(
        "counter", "反方解释：趋势证据说明市场可能已部分消化利率压力。"
    )
    assert [h.hypothesis_id for h in draft.hypotheses] == [expected_id]
    assert draft.hypotheses[0].hypothesis_id != "hyp_custom_模型编的"
    assert all(h.source == "counter_thesis" for h in draft.hypotheses)


def test_horizon_and_bucket_enums_snap_to_canonical(tmp_path: Path):
    """horizon/bucket 是固定三档：合法值原样保留；拼写出界按位置兜底值回正（不发明别名）。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )

    kept = orchestrator._normalize_time_horizon_view({"horizon": "one_to_three_months", "view": "v"}, index=0)
    assert kept["horizon"] == "one_to_three_months"
    snapped = orchestrator._normalize_time_horizon_view({"horizon": "短期内", "view": "v"}, index=0)
    assert snapped["horizon"] == "same_day_or_days"

    kept_bucket = orchestrator._normalize_portfolio_action({"bucket": "waiting_cash", "action": "a"}, index=0)
    assert kept_bucket["bucket"] == "waiting_cash"
    snapped_bucket = orchestrator._normalize_portfolio_action({"bucket": "核心仓", "action": "a"}, index=1)
    assert snapped_bucket["bucket"] == "tactical_position"



# ---------------------------------------------------------------------------
# T54 批 1：固定字面量/时间戳类机械字段由代码装配（机械字段不出答卷）
# ---------------------------------------------------------------------------

def test_counter_thesis_mechanical_literals_are_code_assembled(tmp_path: Path):
    """schema_version / independence_boundary 是固定字面量——模型填错也由代码装配覆盖。"""
    response = {
        "schema_version": "counter_thesis_v99_llm_invented",
        "independence_boundary": "模型编造的边界声明",
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
            }
        ],
        "principal_counterargument": "趋势证据可能说明部分压力已被消化。",
        "cannot_establish": [],
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
    bridge_v2 = BridgeMemo(
        bridge_type="feedback_bridge_v2", layers_connected=["L1", "L5"], implication_for_ndx="保留张力。"
    )

    draft = orchestrator._build_counter_thesis(
        synthesis_packet=synthesis_packet,
        bridge_v2=bridge_v2,
        investigation_reports=[],
    )

    assert draft.schema_version == "counter_thesis_v1"
    assert draft.independence_boundary == CounterThesisDraft.model_fields["independence_boundary"].default


def test_controlled_investigation_mechanical_fields_are_code_assembled(tmp_path: Path, monkeypatch):
    """钉测试（确认既有装配不回流）：investigation_id / originating_agent_id /
    is_deterministic_stub / effective_date 由代码装配——模型塞了值也一律被覆盖。"""
    monkeypatch.setenv("CONTROLLED_INVESTIGATION_LLM_ENABLED", "1")
    response = json.dumps(
        {
            "investigation_id": "inv_llm_invented",
            "originating_agent_id": "agent_llm_invented",
            "is_deterministic_stub": True,
            "effective_date": "1999-01-01",
            "finding": "材料确认实际利率仍构成约束 [M1]。",
            "claims_supported": ["实际利率约束仍在 [M1]"],
            "claims_challenged": [],
            "counter_evidence_refs": ["[M1]"],
            "cannot_establish": ["缺少估值材料 [M1]"],
            "confidence": "medium",
            "limits": ["只读取 [M1]"],
        },
        ensure_ascii=False,
    )
    engine = SequencedFakeLLMEngine({"controlled_investigation": response})
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    spec, message = _controlled_investigation_inputs(tmp_path)

    report = orchestrator._build_investigation_report(spec, message)

    assert report.investigation_id != "inv_llm_invented"
    assert report.originating_agent_id == spec.agent_id
    assert report.is_deterministic_stub is False
    assert report.effective_date == message.effective_date



# ---------------------------------------------------------------------------
# T54 批 2：payload 单值直装（机械字段不出答卷）
# ---------------------------------------------------------------------------

def test_layer_card_identity_and_coverage_fields_are_code_assembled(tmp_path: Path):
    """layer 由 stage_key 派生；covered_function_ids / coverage_complete 由
    indicator_analyses ∩ 输入 analysis_required 指标集派生——模型填错一律覆盖；
    自检的判断类字段（weak_reasoning_points 等）不动；quality_self_check 整个缺失
    时不代造（那是校验器该拦的形状病，闸门不放松）。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    input_payload = {
        "layer_raw_data": {
            "get_fed_funds_rate": {"function_id": "get_fed_funds_rate", "metric_name": "Fed Funds Rate"},
            "get_10y_breakeven": {"function_id": "get_10y_breakeven", "error": "source unavailable"},
        }
    }
    parsed = {
        "layer": "L4",  # 模型填错层号
        "indicator_analyses": [
            {
                "function_id": "get_fed_funds_rate",
                "metric": "Fed Funds Rate",
                "narrative": "n",
                "reasoning_process": "r",
            }
        ],
        "quality_self_check": {
            "covered_function_ids": ["模型瞎填的_id"],
            "coverage_complete": False,
            "weak_reasoning_points": ["模型自己的判断，必须保留"],
        },
    }

    out = orchestrator._assemble_stage_mechanical_fields("l1_analyst", parsed, input_payload)

    assert out["layer"] == "L1"
    # get_10y_breakeven 标了 error → analysis_required=False，不要求覆盖。
    assert out["quality_self_check"]["covered_function_ids"] == ["get_fed_funds_rate"]
    assert out["quality_self_check"]["coverage_complete"] is True
    assert out["quality_self_check"]["weak_reasoning_points"] == ["模型自己的判断，必须保留"]

    # 反例：该分析的指标没分析 → coverage_complete 必须被代码判 False（模型自报 True 不算数）。
    parsed_missing = {
        "indicator_analyses": [],
        "quality_self_check": {"coverage_complete": True},
    }
    out2 = orchestrator._assemble_stage_mechanical_fields("l1_analyst", parsed_missing, input_payload)
    assert out2["quality_self_check"]["coverage_complete"] is False
    assert out2["quality_self_check"]["covered_function_ids"] == []

    # quality_self_check 整个缺失：不代造，留给校验器拦。
    out3 = orchestrator._assemble_stage_mechanical_fields("l1_analyst", {"indicator_analyses": []}, input_payload)
    assert "quality_self_check" not in out3

    # 非层站（如 bridge）：不碰。
    bridge_parsed = {"layer": "L9"}
    out4 = orchestrator._assemble_stage_mechanical_fields("bridge", bridge_parsed, {})
    assert out4["layer"] == "L9"


def test_event_card_type_and_entities_are_code_assembled(tmp_path: Path):
    """event_type / entities 是采集底账字段（采集标签），由代码按 event 装配——
    模型填错或编造的一律覆盖。"""
    event = {
        "event_id": "event:abc",
        "title": "Company update",
        "source_name": "Mainstream Media",
        "source_tier": "reliable_mainstream_report",
        "event_type": "policy_news",
        "published_at": "2026-07-18T09:00:00Z",
        "event_date": "2026-07-18",
        "symbols": ["AAPL"],
        "raw_text_available": True,
        "raw_text_excerpt": "材料称公司发布了更新。",
    }
    _write_event_card_inputs(tmp_path, [event], ["news:abc"])
    (tmp_path / "analysis_packet.json").write_text('{"event_refs": {}}', encoding="utf-8")
    response = json.loads(_event_card_response(event_id="event:abc", tier="reliable_mainstream_report"))
    response["event_type"] = "company_news"  # 模型填错采集标签
    response["entities"] = ["NVDA", "TSLA"]  # 模型编造实体
    engine = UniformEventCardFakeLLMEngine(json.dumps(response, ensure_ascii=False))
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

    card = artifact["cards"][0]
    assert card["event_type"] == "policy_news"
    assert card["entities"] == ["AAPL"]


def test_revision_claimed_fields_are_computed_by_code_diff(tmp_path: Path):
    """revision_claimed_fields 由代码 diff（thesis 原稿 vs revised_thesis 顶层字段）
    装配——模型自报一律覆盖；generated_at 是时间戳，不参与 diff。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    thesis = ThesisDraft(
        main_thesis="旧主论点。",
        environment_assessment="宏观偏紧。",
        valuation_assessment="估值偏高。",
        timing_assessment="趋势脆弱。",
        overall_confidence=Confidence.MEDIUM,
    )
    revised = json.loads(thesis.model_dump_json())
    revised["main_thesis"] = "新主论点。"

    parsed = {"revised_thesis": revised, "revision_claimed_fields": ["模型自报的假话"]}
    out = orchestrator._inject_revision_claimed_fields(parsed, thesis)
    assert out["revision_claimed_fields"] == ["main_thesis"]

    # 未修订（含 degraded 兜底路径）：diff 为空，claimed 必须也是空——不许模型自报"改了"。
    parsed_unchanged = {
        "revised_thesis": json.loads(thesis.model_dump_json()),
        "revision_claimed_fields": ["main_thesis"],
    }
    out2 = orchestrator._inject_revision_claimed_fields(parsed_unchanged, thesis)
    assert out2["revision_claimed_fields"] == []



# ---------------------------------------------------------------------------
# T54 批 5：function_id/metric 抄回配对——模型自报 + 代码校验回正，绝不硬配
# ---------------------------------------------------------------------------

def test_indicator_function_id_typo_is_corrected_against_input_keys(tmp_path: Path):
    """function_id 拼写错误有唯一高相似近邻时代码回正；metric 同步强制为输入
    metric_name；evidence_refs 里的自引用同步改写。绝不是按位置硬配。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    input_payload = {
        "layer_raw_data": {
            "get_10y2y_spread_bp": {"function_id": "get_10y2y_spread_bp", "metric_name": "10Y-2Y Spread"},
            "get_fed_funds_rate": {"function_id": "get_fed_funds_rate", "metric_name": "Fed Funds Rate"},
        }
    }
    parsed = {
        "indicator_analyses": [
            {
                "function_id": "get_10y2y_spread",  # 模型抄错（少 _bp 后缀）
                "metric": "模型瞎写的名字",
                "narrative": "n",
                "reasoning_process": "r",
                "evidence_refs": ["L1.get_10y2y_spread"],
            }
        ],
        "quality_self_check": {},
    }

    out = orchestrator._assemble_stage_mechanical_fields("l1_analyst", parsed, input_payload)

    analysis = out["indicator_analyses"][0]
    assert analysis["function_id"] == "get_10y2y_spread_bp"
    assert analysis["metric"] == "10Y-2Y Spread"
    assert analysis["evidence_refs"] == ["L1.get_10y2y_spread_bp"]
    assert out["quality_self_check"]["covered_function_ids"] == ["get_10y2y_spread_bp"]


def test_indicator_function_id_unmatchable_is_left_for_validator_rejection(tmp_path: Path):
    """配不上唯一高相似近邻的 function_id 不动——交给校验器拒收重试（绝不硬配）。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    input_payload = {
        "layer_raw_data": {
            "get_fed_funds_rate": {"function_id": "get_fed_funds_rate", "metric_name": "Fed Funds Rate"},
        }
    }
    parsed = {
        "indicator_analyses": [
            {
                "function_id": "get_totally_invented_metric",
                "metric": "Invented",
                "narrative": "n",
                "reasoning_process": "r",
                "evidence_refs": ["L1.get_totally_invented_metric"],
            }
        ],
        "quality_self_check": {},
    }

    out = orchestrator._assemble_stage_mechanical_fields("l1_analyst", parsed, input_payload)

    assert out["indicator_analyses"][0]["function_id"] == "get_totally_invented_metric"
    assert out["quality_self_check"]["covered_function_ids"] == []
    assert out["quality_self_check"]["coverage_complete"] is False


def test_layer_card_validator_rejects_unknown_function_ids(tmp_path: Path):
    """校验器新增硬拦：indicator_analyses 的 function_id 不在输入键集里 → 拒收重试
    （收紧：此前只对"漏分析"报错，"多出来的幻觉 id"静默通过）。"""
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=FakeLLMEngine({})
    )
    card = LayerCard.model_validate(
        {
            "layer": "L1",
            "core_facts": [{"metric": "m", "value": 1}],
            "local_conclusion": "结论。",
            "confidence": "medium",
            "layer_synthesis": "综合。",
            "internal_conflict_analysis": "冲突分析。",
            "quality_self_check": {"covered_function_ids": ["get_fed_funds_rate"], "coverage_complete": True},
            "indicator_analyses": [
                {
                    "function_id": "get_fed_funds_rate",
                    "metric": "Fed Funds Rate",
                    "narrative": "n",
                    "reasoning_process": "r",
                    "evidence_refs": ["L1.get_fed_funds_rate"],
                },
                {
                    "function_id": "get_invented_indicator",
                    "metric": "Invented",
                    "narrative": "n",
                    "reasoning_process": "r",
                    "evidence_refs": ["L1.get_invented_indicator"],
                },
            ],
        }
    )

    errors = orchestrator._validate_layer_card_v2(card, "L1", {"get_fed_funds_rate": "Fed Funds Rate"})

    assert any("get_invented_indicator" in error and "not an input function_id" in error for error in errors)
