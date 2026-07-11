from __future__ import annotations

import json
import logging
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

try:
    from .contracts import (
        AgentBudget,
        AnalysisPacket,
        AnalysisRevised,
        BridgeMemo,
        AdjudicationChangeRecord,
        AdjudicationHistory,
        ClaimLedger,
        ClaimLedgerEntry,
        CompetingHypothesis,
        ContextBrief,
        Critique,
        EvidencePassport,
        EvidenceRegistry,
        CounterThesisDraft,
        Confidence,
        EvidenceSourceAuthority,
        FinalAdjudication,
        GoldenPitChecklist,
        GoldenPitChecklistItem,
        GovernanceInputPacket,
        HypothesisCompetition,
        InquiryMessage,
        InquiryMessageType,
        InquiryRouterOutput,
        InvestigationReport,
        LayerCard,
        ObjectiveFirewallSummary,
        OutcomeReviewReport,
        SynthesisPacket,
        LayerSynthesisItem,
        BridgeSynthesisItem,
        RiskBoundaryReport,
        RunReviewReport,
        SchemaGuardReport,
        ThesisDraft,
        UserDecisionCondition,
        UserDecisionProfile,
    )
    from .deep_research_canon import L3_STRUCTURAL_PRIORITY_FUNCTIONS, build_layer_canon_prompt, get_indicator_canon
    from .few_shot import build_layer_few_shot_prompt
    from .inquiry_router import InquiryRouter
    from .llm_engine import LLMEngine
    from .packet_builder import indicator_payload_unavailable_reason
    from .run_review import build_run_review_report
    from .outcome_review import build_outcome_review_report
except ImportError:
    from contracts import (
        AgentBudget,
        AnalysisPacket,
        AnalysisRevised,
        BridgeMemo,
        AdjudicationChangeRecord,
        AdjudicationHistory,
        ClaimLedger,
        ClaimLedgerEntry,
        CompetingHypothesis,
        ContextBrief,
        Critique,
        EvidencePassport,
        EvidenceRegistry,
        CounterThesisDraft,
        Confidence,
        EvidenceSourceAuthority,
        FinalAdjudication,
        GoldenPitChecklist,
        GoldenPitChecklistItem,
        GovernanceInputPacket,
        HypothesisCompetition,
        InquiryMessage,
        InquiryMessageType,
        InquiryRouterOutput,
        InvestigationReport,
        LayerCard,
        ObjectiveFirewallSummary,
        OutcomeReviewReport,
        SynthesisPacket,
        LayerSynthesisItem,
        BridgeSynthesisItem,
        RiskBoundaryReport,
        RunReviewReport,
        SchemaGuardReport,
        ThesisDraft,
        UserDecisionCondition,
        UserDecisionProfile,
    )
    from deep_research_canon import L3_STRUCTURAL_PRIORITY_FUNCTIONS, build_layer_canon_prompt, get_indicator_canon
    from few_shot import build_layer_few_shot_prompt
    from inquiry_router import InquiryRouter
    from llm_engine import LLMEngine
    from packet_builder import indicator_payload_unavailable_reason
    from run_review import build_run_review_report
    from outcome_review import build_outcome_review_report

try:
    from ..data_availability import has_meaningful_observation_value
except ImportError:
    from data_availability import has_meaningful_observation_value

try:
    from ..data_evidence import data_evidence_issues, normalize_source_tier_for_evidence_passport
except ImportError:
    from data_evidence import data_evidence_issues, normalize_source_tier_for_evidence_passport

try:
    from ..state_ledger import extract_state_variables
except ImportError:
    from state_ledger import extract_state_variables

logger = logging.getLogger(__name__)

PROMPT_FILES = {
    "l1_analyst": "l1_analyst.md",
    "l2_analyst": "l2_analyst.md",
    "l3_analyst": "l3_analyst.md",
    "l4_analyst": "l4_analyst.md",
    "l5_analyst": "l5_analyst.md",
    "bridge": "cross_layer_bridge.md",
    "thesis": "thesis_builder.md",
    "counter_thesis": "counter_thesis.md",
    "critic": "critic.md",
    "risk": "risk_sentinel.md",
    "reviser": "reviser.md",
    "final": "final_adjudicator.md",
}

PROMPT_AUDIT_BOOKKEEPING_FIELDS = {
    "source_switches",
    "StaleReferences",
    "HistoryOfMarket",
    "raw_wind_payload_compact",
}
MANIFEST_DATA_QUALITY_LIST_LIMIT = 10
MANIFEST_DATA_QUALITY_OBJECT_CHAR_LIMIT = 1200

INLINE_PROMPTS = {
    "bridge": "你负责显式识别跨层支撑关系、冲突关系与关键不确定性。只返回合法 JSON。",
    "thesis": "你负责把 synthesis_packet 整合成状态、价格、赔率、动作和失效条件，并保留未解决冲突。只返回合法 JSON。",
    "counter_thesis": "你负责在 Thesis 之前提出独立反方假说，只读取允许输入并返回合法 JSON。",
    "critic": "你负责攻击 ThesisDraft 的逻辑弱点、证据跳跃和过度谨慎导致的错过赔率风险。只返回合法 JSON。",
    "risk": "你负责保留下行风险、踏空风险、确认成本、失效条件与必须保留的风险提示。只返回合法 JSON。",
    "reviser": "你负责吸收 critique/risk/schema 反馈后修订 thesis，保留决策语义和冲突，不能自动改得更保守。只返回合法 JSON。",
    "final": "你负责分离内部 quality_gate 与 reader_final，给出状态、价格、赔率、动作和失效条件。只返回合法 JSON。",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


_SEVERITY_HIGH_MEDIUM = frozenset({"high", "medium"})
_EVIDENCE_REF_PATTERN = re.compile(r"L[1-5]\.[A-Za-z_][A-Za-z0-9_]*(?:#[A-Za-z_][A-Za-z0-9_]*)?")
_AUTHORITY_OVERREACH_RULES: Dict[str, List[tuple[str, str]]] = {
    "technical": [
        (r"(估值便宜|估值低估|undervalued|cheap valuation)", "technical_indicator_claims_valuation"),
        (r"(技术|均线|RSI|MACD|ADX|ATR|价格|趋势|超买|超卖).{0,20}(证明|说明|表明).{0,12}(估值便宜|估值低估|基本面改善|盈利改善)", "technical_indicator_overclaims_valuation_or_fundamentals"),
        (r"(基本面已经改善|盈利已经改善|fundamentals? (have )?improved)", "technical_indicator_claims_fundamentals"),
        (r"(大买|强烈买入|all[- ]?in)", "technical_indicator_outputs_strong_action"),
    ],
    "proxy": [
        (r"(官方事实|官方真理|official fact|official truth)", "proxy_marked_as_official_fact"),
        (r"(代理|proxy).{0,20}(证明|proves?).{0,20}(真实|actual|official)", "proxy_overclaims_actual_or_official_state"),
    ],
    "composite": [
        (r"(单一原因|唯一原因|sole cause|single cause)", "composite_overclaims_single_cause"),
        (r"(官方事实|official fact)", "composite_marked_as_official_fact"),
    ],
    "structural": [
        (r"(证明|说明|表明).{0,12}(短线买点|短线卖点|立刻买入|立刻卖出)", "structural_indicator_claims_tactical_timing"),
    ],
}

PRICE_REFLECTION_CATEGORIES: Dict[str, Dict[str, str]] = {
    "credit": {
        "target": "credit_stress",
        "label": "信用",
        "hint": "信用利差、融资压力或信用风险是否已被价格反映",
    },
    "rates": {
        "target": "rates_discount_rate",
        "label": "利率",
        "hint": "名义/真实利率和贴现率压力是否已被价格反映",
    },
    "valuation": {
        "target": "valuation_risk_premium",
        "label": "估值",
        "hint": "估值压缩、ERP 或盈利风险补偿是否已被价格反映",
    },
    "technical_panic": {
        "target": "technical_panic_positioning",
        "label": "技术恐慌",
        "hint": "恐慌、波动、趋势破坏或反抽是否已被价格反映",
    },
    "liquidity": {
        "target": "liquidity_conditions",
        "label": "流动性",
        "hint": "政策/市场流动性冲击与修复是否已被价格反映",
    },
}


def _severity_is_high_or_medium(conflict: Any) -> bool:
    return str(_enum_value(conflict.severity)) in _SEVERITY_HIGH_MEDIUM


def _layer_has_usable_raw_data(layer_payload: Any) -> bool:
    if not isinstance(layer_payload, dict):
        return False
    for indicator_payload in layer_payload.values():
        if not isinstance(indicator_payload, dict):
            continue
        if indicator_payload.get("error"):
            continue
        if _indicator_payload_unavailable_for_object_firewall(indicator_payload):
            continue
        if "value" in indicator_payload:
            if has_meaningful_observation_value(indicator_payload.get("value")):
                return True
            continue
        if has_meaningful_observation_value(indicator_payload):
            return True
    return False


def _indicator_payload_unavailable_for_object_firewall(payload: Dict[str, Any]) -> bool:
    return indicator_payload_unavailable_reason(payload) is not None


class VNextOrchestrator:
    """Lightweight real-LLM orchestrator for the vNext chain."""

    def __init__(
        self,
        *,
        available_models: List[str],
        output_dir: str,
        prompts_dir: Optional[str] = None,
        llm_engine: Optional[Any] = None,
        max_node_retries: int = 2,
        schema_guard_retry: bool = True,
        resume_from_existing: bool = False,
    ) -> None:
        if not llm_engine and not available_models:
            raise ValueError("At least one available model is required.")
        self.available_models = available_models
        self.output_dir = Path(output_dir).resolve()
        self.prompts_dir = Path(prompts_dir) if prompts_dir else Path(__file__).with_name("prompts")
        self.llm_engine = llm_engine or LLMEngine(available_models=available_models)
        self.max_node_retries = max_node_retries
        self.schema_guard_retry = schema_guard_retry
        self.resume_from_existing = resume_from_existing
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.layer_cards_dir = self.output_dir / "layer_cards"
        self.layer_context_dir = self.output_dir / "layer_context_briefs"
        self.bridge_dir = self.output_dir / "bridge_memos"
        self.investigation_reports_dir = self.output_dir / "investigation_reports"
        self.prompt_audit_dir = self.output_dir / "prompt_audit"
        self.layer_cards_dir.mkdir(exist_ok=True)
        self.layer_context_dir.mkdir(exist_ok=True)
        self.bridge_dir.mkdir(exist_ok=True)
        self.investigation_reports_dir.mkdir(exist_ok=True)
        self.prompt_audit_dir.mkdir(exist_ok=True)
        self.stage_diagnostics: Dict[str, Any] = {"schema_version": "vnext_llm_stage_diagnostics_v1", "stages": {}}
        self.stage_manifest_path = self.output_dir / "stage_manifest.json"
        self.stage_manifest = self._load_stage_manifest()
        self.stage_model_routing = self._load_stage_model_routing()

    def run(self, packet: AnalysisPacket | Dict[str, Any]) -> Dict[str, Any]:
        packet_model = packet if isinstance(packet, AnalysisPacket) else AnalysisPacket.model_validate(packet)
        self._save_json("analysis_packet.json", packet_model)
        self._save_json("runtime_boundary_manifest.json", self._build_runtime_boundary_manifest())
        self._save_json("feedback_contract_manifest.json", self._build_feedback_contract_manifest())

        context_brief = self._build_context_brief(packet_model)
        self._save_json("context_brief.json", context_brief)

        layer_cards = self._run_layer_cards(packet_model, context_brief)
        bridge_v1 = self._run_bridge(packet_model, context_brief, layer_cards)
        feedback_messages = self._build_feedback_inquiry_messages(packet_model, layer_cards, bridge_v1)
        inquiry_router_output = self._route_feedback_inquiries(feedback_messages)
        investigation_reports = self._run_controlled_investigations(inquiry_router_output)
        bridge_v2 = self._build_bridge_v2(
            packet_model=packet_model,
            layer_cards=layer_cards,
            bridge_v1=bridge_v1,
            router_output=inquiry_router_output,
            investigation_reports=investigation_reports,
        )
        bridge_memos = [bridge_v1, bridge_v2]
        synthesis_packet = self._build_synthesis_packet(packet_model, context_brief, layer_cards, bridge_memos)
        hypothesis_competition = self._build_hypothesis_competition(
            synthesis_packet=synthesis_packet,
            bridge_v2=bridge_v2,
            investigation_reports=investigation_reports,
            effective_date=self._effective_date(packet_model),
        )
        synthesis_packet.competing_hypotheses = hypothesis_competition.hypotheses
        synthesis_packet.hypothesis_competition_summary = self._hypothesis_competition_summary(hypothesis_competition)
        synthesis_packet.adjudication_history = list(hypothesis_competition.downgrade_or_split_events)
        synthesis_packet.counter_thesis_boundary = {
            "input_refs": list(hypothesis_competition.input_refs),
            "forbidden_context_refs": list(hypothesis_competition.forbidden_context_refs),
            "independence_verified": "thesis_draft.json" in set(hypothesis_competition.forbidden_context_refs),
        }
        evidence_registry = self._build_evidence_registry(
            packet_model=packet_model,
            synthesis_packet=synthesis_packet,
            investigation_reports=investigation_reports,
            hypothesis_competition=hypothesis_competition,
        )
        synthesis_packet.evidence_registry_summary = self._evidence_registry_summary(evidence_registry)
        self._save_json("synthesis_packet.json", synthesis_packet)
        self._save_json("evidence_registry.json", evidence_registry)
        thesis = self._run_thesis(synthesis_packet)

        gov_input_critic = self._build_governance_input_packet(
            synthesis_packet=synthesis_packet,
            thesis=thesis,
            layer_cards=layer_cards,
        )
        critique = self._run_and_save(
            stage_key="critic",
            stage_name="critic",
            model_cls=Critique,
            payload={"governance_input": _model_dump(gov_input_critic)},
            filename="critique.json",
        )

        risk_report = self._run_and_save(
            stage_key="risk",
            stage_name="risk",
            model_cls=RiskBoundaryReport,
            payload={"governance_input": _model_dump(gov_input_critic)},
            filename="risk_boundary_report.json",
        )

        schema_report = self._run_schema_guard(packet_model, layer_cards, bridge_memos, thesis, critique, risk_report)
        self._save_json("schema_guard_report.json", schema_report)

        # Schema Guard retry: if enabled and structural issues found, re-run thesis/critic/risk once
        # with the schema issues injected into governance input, then re-check.
        if self.schema_guard_retry and not schema_report.passed and (schema_report.structural_issues or schema_report.missing_fields):
            logger.warning(
                "Schema Guard detected structural issues; retrying thesis/critic/risk with "
                "schema feedback injected into governance input."
            )
            gov_input_critic_retry = self._build_governance_input_packet(
                synthesis_packet=synthesis_packet,
                thesis=thesis,
                layer_cards=layer_cards,
                schema_report=schema_report,
            )
            critique = self._run_and_save(
                stage_key="critic",
                stage_name="critic_retry",
                model_cls=Critique,
                payload={"governance_input": _model_dump(gov_input_critic_retry)},
                filename="critique.json",
            )
            risk_report = self._run_and_save(
                stage_key="risk",
                stage_name="risk_retry",
                model_cls=RiskBoundaryReport,
                payload={"governance_input": _model_dump(gov_input_critic_retry)},
                filename="risk_boundary_report.json",
            )
            schema_report = self._run_schema_guard(
                packet_model, layer_cards, bridge_memos, thesis, critique, risk_report
            )
            self._save_json("schema_guard_report.json", schema_report)
            if not schema_report.passed:
                logger.warning(
                    "Schema Guard still failing after retry; continuing with residual issues. "
                    "Structural: %s; Consistency: %s",
                    schema_report.structural_issues,
                    schema_report.consistency_issues,
                )

        gov_input_reviser = self._build_governance_input_packet(
            synthesis_packet=synthesis_packet,
            thesis=thesis,
            critique=critique,
            risk_report=risk_report,
            schema_report=schema_report,
            layer_cards=layer_cards,
        )
        analysis_revised = self._run_and_save(
            stage_key="reviser",
            stage_name="reviser",
            model_cls=AnalysisRevised,
            payload={"governance_input": _model_dump(gov_input_reviser)},
            filename="analysis_revised.json",
            validator=lambda candidate: self._validate_stage_evidence_refs(
                candidate,
                set(synthesis_packet.evidence_index.keys()),
                "reviser",
            ),
        )

        gov_input_final = self._build_governance_input_packet(
            synthesis_packet=synthesis_packet,
            thesis=analysis_revised.revised_thesis,
            critique=critique,
            risk_report=risk_report,
            schema_report=schema_report,
            analysis_revised=analysis_revised,
            layer_cards=layer_cards,
        )
        final_payload = {
            "governance_input": _model_dump(gov_input_final),
        }
        final_adjudication = self._load_stage_checkpoint(
            "final_adjudication.json",
            FinalAdjudication,
            stage_key="final",
            stage_name="final_adjudicator",
            expected_payload=final_payload,
        )
        if final_adjudication is None:
            final_adjudication = self._run_stage(
                stage_key="final",
                stage_name="final_adjudicator",
                model_cls=FinalAdjudication,
                payload=final_payload,
                validator=lambda candidate: self._validate_stage_evidence_refs(
                    candidate,
                    set(synthesis_packet.evidence_index.keys()),
                    "final",
                ),
            )
            token_report = self.llm_engine.get_token_report() if hasattr(self.llm_engine, "get_token_report") else {}
            final_adjudication.token_usage = token_report
            self._save_json("final_adjudication.json", final_adjudication)
            self._record_stage_artifact(
                self.output_dir / "final_adjudication.json",
                stage_key="final",
                stage_name="final_adjudicator",
                payload=final_payload,
            )
        final_claim_ledger = self._build_final_claim_ledger(
            synthesis_packet=synthesis_packet,
            thesis=analysis_revised.revised_thesis,
            final_adjudication=final_adjudication,
            evidence_registry=evidence_registry,
            effective_date=self._effective_date(packet_model),
            risk_report=risk_report,
        )
        final_adjudication.claim_ledger = final_claim_ledger
        evidence_registry = self._attach_claims_to_evidence_registry(evidence_registry, final_claim_ledger)
        # Persist the enriched final artifact as well as the standalone ledger.
        # Otherwise the in-memory final has a claim gate that the saved final omits.
        self._save_json("final_adjudication.json", final_adjudication)
        self._record_stage_artifact(
            self.output_dir / "final_adjudication.json",
            stage_key="final",
            stage_name="final_adjudicator",
            payload=final_payload,
        )
        self._save_json("final_claim_ledger.json", final_claim_ledger)
        self._save_json("evidence_registry.json", evidence_registry)
        user_decision_profile = self._load_user_decision_profile()
        golden_pit_checklist = self._build_golden_pit_checklist(
            final_claim_ledger=final_claim_ledger,
            decision_profile=user_decision_profile,
            final_adjudication=final_adjudication,
            effective_date=self._effective_date(packet_model),
            state_variables=extract_state_variables(_model_dump(packet_model))[0],
        )
        self._save_json("user_decision_profile.json", user_decision_profile)
        self._save_json("golden_pit_checklist.json", golden_pit_checklist)
        run_review_report = self._build_run_review_report(
            packet_model=packet_model,
            bridge_memos=bridge_memos,
            synthesis_packet=synthesis_packet,
            thesis=thesis,
            risk_report=risk_report,
            schema_report=schema_report,
            final_adjudication=final_adjudication,
            hypothesis_competition=hypothesis_competition,
        )
        self._save_json("run_review_report.json", run_review_report)
        outcome_review_report = self._build_outcome_review_report(
            packet_model=packet_model,
            final_adjudication=final_adjudication,
        )
        self._save_json("outcome_review_report.json", outcome_review_report)
        reflection_library = self._build_post_run_reflection_library(
            run_review_report=run_review_report,
            outcome_review_report=outcome_review_report,
            schema_report=schema_report,
        )
        self._save_json("post_run_reflection_library.json", reflection_library)

        return {
            "context_brief": context_brief,
            "layer_cards": layer_cards,
            "bridge_memos": bridge_memos,
            "synthesis_packet": synthesis_packet,
            "hypothesis_competition": hypothesis_competition,
            "evidence_registry": evidence_registry,
            "thesis_draft": thesis,
            "critique": critique,
            "risk_boundary_report": risk_report,
            "schema_guard_report": schema_report,
            "analysis_revised": analysis_revised,
            "final_adjudication": final_adjudication,
            "final_claim_ledger": final_claim_ledger,
            "user_decision_profile": user_decision_profile,
            "golden_pit_checklist": golden_pit_checklist,
            "run_review_report": run_review_report,
            "outcome_review_report": outcome_review_report,
            "post_run_reflection_library": reflection_library,
            "output_dir": str(self.output_dir),
        }

    def _build_run_review_report(
        self,
        *,
        packet_model: AnalysisPacket,
        bridge_memos: List[BridgeMemo],
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        risk_report: RiskBoundaryReport,
        schema_report: SchemaGuardReport,
        final_adjudication: FinalAdjudication,
        hypothesis_competition: Optional[HypothesisCompetition] = None,
    ) -> RunReviewReport:
        data_integrity = {}
        data_integrity_path = self.output_dir / "data_integrity_report.json"
        if data_integrity_path.exists():
            try:
                data_integrity = json.loads(data_integrity_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data_integrity = {}
        inquiry_router_output = {}
        inquiry_router_path = self.output_dir / "inquiry_router_output.json"
        if inquiry_router_path.exists():
            try:
                inquiry_router_output = json.loads(inquiry_router_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                inquiry_router_output = {}
        investigation_reports = []
        for report_path in sorted(self.investigation_reports_dir.glob("*.json")):
            try:
                investigation_reports.append(json.loads(report_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return build_run_review_report(
            run_dir=str(self.output_dir),
            analysis_packet=_model_dump(packet_model),
            bridges=[_model_dump(memo) for memo in bridge_memos],
            synthesis_packet=_model_dump(synthesis_packet),
            thesis_draft=_model_dump(thesis),
            risk_boundary_report=_model_dump(risk_report),
            schema_guard_report=_model_dump(schema_report),
            final_adjudication=_model_dump(final_adjudication),
            data_integrity_report=data_integrity,
            inquiry_router_output=inquiry_router_output,
            investigation_reports=investigation_reports,
            hypothesis_competition=_model_dump(hypothesis_competition) if hypothesis_competition is not None else self._load_local_json(self.output_dir / "hypothesis_competition.json", {}),
            adjudication_history=self._load_local_json(self.output_dir / "adjudication_history.json", {}),
            evidence_registry=self._load_local_json(self.output_dir / "evidence_registry.json", {}),
            final_claim_ledger=self._load_local_json(self.output_dir / "final_claim_ledger.json", {}),
            golden_pit_checklist=self._load_local_json(self.output_dir / "golden_pit_checklist.json", {}),
        )

    def _build_outcome_review_report(
        self,
        *,
        packet_model: AnalysisPacket,
        final_adjudication: FinalAdjudication,
    ) -> OutcomeReviewReport:
        meta = packet_model.meta if isinstance(packet_model.meta, dict) else {}
        backtest_date = meta.get("backtest_date")
        if not backtest_date:
            return OutcomeReviewReport(
                run_dir=str(self.output_dir),
                backtest_date=meta.get("data_date"),
                source="not_run_for_live_or_non_backtest_context",
                market_outcome_label="not_applicable",
                caution_review="非历史回测语境，不接入后验 QQQ 表现。",
                aggression_review="非历史回测语境，不接入后验 QQQ 表现。",
                prompt_leakage_checks=["Outcome Review skipped because packet has no backtest_date."],
            )
        return build_outcome_review_report(
            run_dir=str(self.output_dir),
            backtest_date=backtest_date,
            final_adjudication=_model_dump(final_adjudication),
        )

    def _build_post_run_reflection_library(
        self,
        *,
        run_review_report: RunReviewReport,
        outcome_review_report: OutcomeReviewReport,
        schema_report: SchemaGuardReport,
    ) -> Dict[str, Any]:
        run_updates = list(getattr(run_review_report, "learning_updates", []) or [])
        outcome_updates = list(getattr(outcome_review_report, "learning_updates", []) or [])
        next_checks = list(getattr(run_review_report, "next_run_checks", []) or [])
        items: List[Dict[str, Any]] = []
        for index, text in enumerate(dict.fromkeys(run_updates + outcome_updates), start=1):
            if not str(text).strip():
                continue
            items.append(
                {
                    "id": f"reflection_{index}",
                    "source": "run_review_or_outcome_review",
                    "lesson": str(text),
                    "allowed_use": "manual_rule_update_or_test_design_for_future_runs",
                    "runtime_prompt_use": "forbidden_for_current_run",
                }
            )
        return {
            "schema_version": "post_run_reflection_library_v1",
            "generated_at": _utc_now().isoformat(),
            "run_dir": str(self.output_dir),
            "boundary": (
                "This artifact is generated after Final. It must not be injected into L1-L5, "
                "Bridge, Thesis, Risk, Reviser, or Final prompts for the current run."
            ),
            "schema_guard_quality_status": getattr(schema_report, "quality_status", ""),
            "items": items,
            "next_run_checks": next_checks,
            "eligible_destinations": ["tests", "documentation", "future prompt/manual rule revisions"],
        }

    def _run_layer_cards(self, packet: AnalysisPacket, context_brief: ContextBrief) -> List[LayerCard]:
        cards: List[LayerCard] = []
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            layer_payload = self._build_layer_stage_payload(packet, context_brief, layer)
            self._save_json(self.layer_context_dir / f"{layer}.json", layer_payload["context_brief"])
            checkpoint = self._load_stage_checkpoint(
                self.layer_cards_dir / f"{layer}.json",
                LayerCard,
                stage_key=f"{layer.lower()}_analyst",
                stage_name=layer.lower(),
                expected_payload=layer_payload,
            )
            if checkpoint is not None:
                cards.append(checkpoint)
                continue
            card = self._run_stage(
                stage_key=f"{layer.lower()}_analyst",
                stage_name=layer.lower(),
                model_cls=LayerCard,
                payload=layer_payload,
                validator=lambda card, layer=layer: self._validate_layer_card_v2(
                    card,
                    layer,
                    self._analysis_required_indicator_map(packet, layer),
                ),
            )
            if str(card.layer) != layer and getattr(card.layer, "value", None) != layer:
                raise ValueError(f"{layer} analyst returned mismatched layer: {card.layer}")
            cards.append(card)
            self._save_json(self.layer_cards_dir / f"{layer}.json", card)
            self._record_stage_artifact(
                self.layer_cards_dir / f"{layer}.json",
                stage_key=f"{layer.lower()}_analyst",
                stage_name=layer.lower(),
                payload=layer_payload,
            )
        return cards

    def _build_layer_stage_payload(
        self,
        packet: AnalysisPacket,
        context_brief: ContextBrief,
        layer: str,
    ) -> Dict[str, Any]:
        layer = layer.upper()
        layer_context_brief = self._build_layer_context_brief(packet, context_brief, layer)
        return {
            "context_brief": _model_dump(layer_context_brief),
            "layer": layer,
            "layer_facts": _model_dump(packet.facts_by_layer.get(layer)),
            "layer_raw_data": packet.raw_data.get(layer, {}),
            "manual_overrides": self._build_layer_manual_overrides(packet, layer),
            "runtime_boundary_policy_id": "layer_runtime_input_policy_v1",
        }

    def _build_layer_input_policy(self, layer: str) -> Dict[str, Any]:
        layer = layer.upper()
        return {
            "schema_version": "layer_runtime_input_policy_v1",
            "layer": layer,
            "allowed_runtime_inputs": [
                f"context_brief.layer_highlights.{layer}",
                f"facts_by_layer.{layer}",
                f"raw_data.{layer}",
                f"manual_overrides.metrics filtered to raw_data.{layer} function_id values",
                "ObjectCanon and same-layer IndicatorCanon as static rules only",
            ],
            "forbidden_runtime_inputs": [
                "facts_by_layer.other_layers",
                "raw_data.other_layers",
                "candidate_cross_layer_links",
                "context_brief.apparent_cross_layer_signals",
                "event_refs",
                "news_layer_analysis",
                "event_narrative_ledger",
                "event_mechanism_report",
                "integrated_synthesis_report",
                "bridge_memos",
                "synthesis_packet",
                "thesis_draft",
                "critique",
                "risk_boundary_report",
                "analysis_revised",
                "final_adjudication",
                "investigation_reports",
                "post_run_reflection_library",
            ],
            "no_backflow_rule": (
                "InvestigationReport, integrated reports, Bridge, Thesis, Risk, Reviser, "
                "and Final artifacts must not rewrite or be injected into L1-L5 layer cards."
            ),
            "event_evidence_rule": (
                "Events, news, browser output, and sidecars are event/background material only "
                "unless upgraded by a formal data-source path; they must not become L1-L5 evidence_ref."
            ),
        }

    def _build_runtime_boundary_manifest(self) -> Dict[str, Any]:
        return {
            "schema_version": "runtime_boundary_manifest_v1",
            "purpose": "Stage 0 audit artifact; not injected into L1-L5 prompts.",
            "fixed_chain": [
                "L1-L5 layer analysts",
                "Bridge",
                "SynthesisPacket",
                "Thesis",
                "Critic",
                "Risk",
                "SchemaGuard",
                "Reviser",
                "Final",
                "ReaderExit(UserDecisionProfile + GoldenPitChecklist)",
            ],
            "layer_input_policies": {
                layer: self._build_layer_input_policy(layer)
                for layer in ["L1", "L2", "L3", "L4", "L5"]
            },
            "no_backflow_rule": (
                "Integrated reports, event reports, future InvestigationReport artifacts, "
                "Bridge, Thesis, Risk, Reviser, Final, UserDecisionProfile, GoldenPitChecklist, "
                "and post-run reflection artifacts "
                "must not rewrite or be injected into L1-L5 layer cards."
            ),
            "reader_exit_boundary": (
                "UserDecisionProfile and golden_pit_checklist.json are reader-exit translation artifacts only. "
                "They are generated after Final/ClaimLedger and must not enter L1-L5, Bridge, Thesis, Critic, "
                "Risk, Reviser, Final, or hypothesis competition prompts."
            ),
            "evidence_boundary": (
                "event_refs, news, browser output, sidecars, and future investigation outputs "
                "are not L1-L5 evidence_ref unless promoted through a formal data-source path."
            ),
            "prompt_noise_boundary": (
                "This manifest is stored as an artifact for audit; L1-L5 prompts receive only "
                "their layer-local context, facts, raw data, and filtered manual overrides."
            ),
        }

    def _build_feedback_contract_manifest(self) -> Dict[str, Any]:
        runtime_budget = AgentBudget(max_tool_calls=1, max_minutes=1, max_source_refs=3)
        router = InquiryRouter(max_agent_specs=3, default_budget=runtime_budget)
        return {
            "schema_version": "feedback_contract_manifest_v1",
            "purpose": "Stage 1 audit artifact; defines controlled inquiry messages, task sheets, and investigation reports.",
            "message_contract": {
                "contract": "InquiryMessage",
                "message_types": [
                    "observation_inquiry",
                    "event_challenge",
                    "adjudication_gap",
                    "evidence_upgrade_request",
                ],
                "required_fields": [
                    "message_id",
                    "message_type",
                    "sender_stage",
                    "target_stage",
                    "trigger",
                    "question",
                    "allowed_context_refs",
                    "forbidden_context_refs",
                    "effective_date",
                ],
            },
            "agent_spec_contract": {
                "contract": "AgentSpec",
                "required_fields": [
                    "agent_id",
                    "originating_message_id",
                    "research_question",
                    "allowed_context_refs",
                    "forbidden_context_refs",
                    "allowed_tools",
                    "budget",
                    "stop_conditions",
                    "success_criteria",
                    "required_output",
                ],
                "budget_visible": True,
                "stop_conditions_required": True,
            },
            "investigation_report_contract": {
                "contract": "InvestigationReport",
                "required_fields": router.policy_manifest()["required_investigation_output_fields"],
                "minimal_evidence_fields": [
                    "evidence_refs",
                    "counter_evidence_refs",
                    "claims_supported",
                    "claims_challenged",
                    "cannot_establish",
                    "source_authority",
                ],
            },
            "router_policy": router.policy_manifest(),
            "runtime_budget": runtime_budget.model_dump(mode="json"),
            "no_backflow_rule": (
                "InquiryMessage, AgentSpec, and InvestigationReport are feedback artifacts. "
                "They may be audited or consumed by later Bridge/integrated synthesis stages, "
                "but must not rewrite or be injected into L1-L5 layer cards."
            ),
        }

    def _build_initial_inquiry_router_output(self) -> Dict[str, Any]:
        return InquiryRouter(max_agent_specs=3).route([]).model_dump(mode="json")

    def _effective_date(self, packet: AnalysisPacket) -> str:
        meta = packet.meta if isinstance(packet.meta, dict) else {}
        return str(meta.get("data_date") or meta.get("backtest_date") or meta.get("timestamp_utc") or _utc_now().date().isoformat())

    def _load_stage_model_routing(self) -> Dict[str, Any]:
        path = Path(__file__).resolve().parents[2] / "config" / "stage_model_routing.json"
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
            except Exception as exc:
                logger.warning("Failed to load stage model routing from %s: %s", path, exc)
        return {
            "schema_version": "stage_model_routing_v1_default",
            "stage_preferences": {
                "counter_thesis": ["deepseek-v4-pro", "deepseek-v4-flash"],
                "thesis": ["deepseek-v4-pro", "deepseek-v4-flash"],
                "reviser": ["deepseek-v4-pro", "deepseek-v4-flash"],
                "final": ["deepseek-v4-pro", "deepseek-v4-flash"],
            },
        }

    def _preferred_models_for_stage(self, stage_key: str) -> List[str]:
        preferences = self.stage_model_routing.get("stage_preferences", {})
        raw = preferences.get(stage_key, []) if isinstance(preferences, dict) else []
        ordered: List[str] = []
        for model_key in raw:
            if model_key in self.available_models and model_key not in ordered:
                ordered.append(model_key)
        return ordered

    def _stable_inquiry_id(self, message_type: InquiryMessageType, parts: List[Any]) -> str:
        seed = "|".join(str(part or "") for part in [message_type.value] + parts)
        return f"inq_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"

    def _feedback_forbidden_refs(self) -> List[str]:
        return [
            "layer_cards.other_layers_runtime_data",
            "thesis_draft.json",
            "critique.json",
            "risk_boundary_report.json",
            "analysis_revised.json",
            "final_adjudication.json",
            "post_run_reflection_library.json",
        ]

    def _build_feedback_inquiry_messages(
        self,
        packet: AnalysisPacket,
        layer_cards: List[LayerCard],
        bridge_v1: BridgeMemo,
    ) -> List[InquiryMessage]:
        effective_date = self._effective_date(packet)
        forbidden_refs = self._feedback_forbidden_refs()
        messages: List[InquiryMessage] = []

        for question in list(dict.fromkeys(getattr(bridge_v1, "unresolved_questions", []) or []))[:2]:
            messages.append(
                InquiryMessage(
                    message_id=self._stable_inquiry_id(InquiryMessageType.ADJUDICATION_GAP, ["bridge_unresolved", question]),
                    message_type=InquiryMessageType.ADJUDICATION_GAP,
                    sender_stage="bridge",
                    target_stage="inquiry_router",
                    trigger="Bridge V1 unresolved_questions 暴露仍需二次核查的问题。",
                    question=str(question),
                    allowed_context_refs=["bridge_memos/bridge_0.json", "synthesis_packet.pending"],
                    forbidden_context_refs=forbidden_refs,
                    effective_date=effective_date,
                )
            )

        principal = getattr(bridge_v1, "principal_contradiction", None)
        principal_dict = _model_dump(principal) if principal is not None else {}
        principal_needs_review = (
            not principal_dict
            or not principal_dict.get("evidence_refs")
            or str(principal_dict.get("price_reflection") or "").lower() in {"", "unclear", "unknown"}
            or "principal_contradiction_derived_by_code" in (getattr(bridge_v1, "normalization_notes", []) or [])
        )
        if principal_needs_review:
            messages.append(
                InquiryMessage(
                    message_id=self._stable_inquiry_id(InquiryMessageType.ADJUDICATION_GAP, ["principal_gap", principal_dict.get("contradiction_id")]),
                    message_type=InquiryMessageType.ADJUDICATION_GAP,
                    sender_stage="bridge",
                    target_stage="inquiry_router",
                    trigger="Bridge V1 的主要矛盾、证据或价格反映仍有缺口。",
                    question="主要矛盾是否有足够证据支撑？价格反映判断是否需要保留为未解决？",
                    allowed_context_refs=["bridge_memos/bridge_0.json"],
                    forbidden_context_refs=forbidden_refs,
                    effective_date=effective_date,
                )
            )

        messages.extend(self._build_event_challenge_messages(effective_date, forbidden_refs))
        messages.extend(self._build_observation_inquiry_messages(packet, layer_cards, effective_date, forbidden_refs))

        deduped: List[InquiryMessage] = []
        seen = set()
        for message in messages:
            if message.message_id in seen:
                continue
            seen.add(message.message_id)
            deduped.append(message)
        self._save_json(
            "inquiry_messages.json",
            {"schema_version": "inquiry_messages_v1", "messages": [_model_dump(message) for message in deduped]},
        )
        return deduped

    def _build_event_challenge_messages(
        self,
        effective_date: str,
        forbidden_refs: List[str],
    ) -> List[InquiryMessage]:
        questions_path = self.output_dir / "cross_layer_questions.json"
        summary_path = self.output_dir / "event_layer_summary.json"
        questions_payload = self._load_local_json(questions_path, {})
        raw_questions = _as_list(questions_payload.get("questions")) if isinstance(questions_payload, dict) else []
        messages: List[InquiryMessage] = []
        for question in raw_questions:
            if not isinstance(question, dict):
                continue
            if question.get("direction") != "event_to_data":
                continue
            if str(question.get("status") or "open") not in {"open", "insufficient_data"}:
                continue
            question_text = str(question.get("question") or "").strip()
            if not question_text:
                continue
            messages.append(
                InquiryMessage(
                    message_id=self._stable_inquiry_id(InquiryMessageType.EVENT_CHALLENGE, [question.get("question_id"), question_text]),
                    message_type=InquiryMessageType.EVENT_CHALLENGE,
                    sender_stage="L2",
                    target_stage="integrated_synthesis",
                    trigger=str(question.get("why_it_matters") or "L2 事件账本提出需要数据层压力测试的开放问题。"),
                    question=question_text,
                    allowed_context_refs=[
                        "cross_layer_questions.json",
                        "event_layer_summary.json",
                        "event_mechanism_report.json",
                        "bridge_memos/bridge_0.json",
                    ],
                    forbidden_context_refs=forbidden_refs,
                    effective_date=effective_date,
                )
            )
        if messages or not summary_path.exists():
            return messages[:2]

        rejection = {
            "schema_version": "event_challenge_rejections_v1",
            "generated_at": _utc_now().isoformat(),
            "status": "rejected",
            "reason": "event_layer_present_but_no_open_event_to_data_questions",
            "trigger": "L2 事件层存在，但没有可转成 event_challenge 的开放问题。",
            "source_refs": ["event_layer_summary.json", "cross_layer_questions.json"],
        }
        self._save_json("event_challenge_rejections.json", rejection)
        return []

    def _build_observation_inquiry_messages(
        self,
        packet: AnalysisPacket,
        layer_cards: List[LayerCard],
        effective_date: str,
        forbidden_refs: List[str],
    ) -> List[InquiryMessage]:
        messages: List[InquiryMessage] = []
        for card in layer_cards:
            layer_label = str(_enum_value(card.layer))
            quality = getattr(card, "quality_self_check", None)
            missing = list(getattr(quality, "missing_or_weak_indicators", []) or []) if quality else []
            flags = list(getattr(card, "risk_flags", []) or [])
            combined = [str(item) for item in missing + flags if str(item).strip()]
            anomaly_text = next(
                (
                    item
                    for item in combined
                    if any(token in item.lower() for token in ["missing", "weak", "缺", "不足", "data", "异常", "breadth", "广度"])
                ),
                "",
            )
            if not anomaly_text:
                continue
            messages.append(
                InquiryMessage(
                    message_id=self._stable_inquiry_id(InquiryMessageType.OBSERVATION_INQUIRY, [layer_label, anomaly_text]),
                    message_type=InquiryMessageType.OBSERVATION_INQUIRY,
                    sender_stage=layer_label,
                    target_stage="L2",
                    trigger=f"{layer_label} 发现数据缺口或异常：{anomaly_text}",
                    question=f"{layer_label} 的数据缺口或异常是否有可见语境、历史相似背景或反证需要保留？",
                    allowed_context_refs=[f"layer_cards/{layer_label}.json", "bridge_memos/bridge_0.json"],
                    forbidden_context_refs=forbidden_refs,
                    effective_date=effective_date,
                )
            )
            break
        return messages[:1]

    def _route_feedback_inquiries(self, messages: List[InquiryMessage]) -> InquiryRouterOutput:
        router = InquiryRouter(
            max_agent_specs=3,
            default_budget=AgentBudget(max_tool_calls=1, max_minutes=1, max_source_refs=3),
        )
        router_output = router.route(messages)
        self._save_json("inquiry_router_output.json", router_output)
        self._save_json(
            "feedback_loop_manifest.json",
            {
                "schema_version": "feedback_loop_manifest_v1",
                "generated_at": _utc_now().isoformat(),
                "phase": "stage_2_minimal_feedback_loop",
                "max_agent_specs": 3,
                "message_count": len(messages),
                "accepted_agent_specs": len(router_output.agent_specs),
                "rejected_messages": len(router_output.rejected_messages),
                "budget_enforced": all(spec.budget.max_tool_calls <= 1 for spec in router_output.agent_specs),
                "no_backflow_rule": "InvestigationReport and Bridge V2 are downstream artifacts; they must not rewrite L1-L5 layer cards.",
            },
        )
        return router_output

    def _run_controlled_investigations(self, router_output: InquiryRouterOutput) -> List[InvestigationReport]:
        message_by_id = {message.message_id: message for message in router_output.input_messages}
        reports: List[InvestigationReport] = []
        for spec in router_output.agent_specs:
            message = message_by_id.get(spec.originating_message_id)
            if message is None:
                continue
            report = self._build_investigation_report(spec, message)
            reports.append(report)
            report_path = self.investigation_reports_dir / f"{report.investigation_id}.json"
            self._save_json(report_path, report)
        return reports

    def _build_investigation_report(self, spec: Any, message: InquiryMessage) -> InvestigationReport:
        investigation_id = f"inv_{hashlib.sha1(spec.agent_id.encode('utf-8')).hexdigest()[:12]}"
        context_notes = self._read_allowed_context_notes(spec.allowed_context_refs, spec.budget.max_source_refs)
        message_type = message.message_type
        if message_type == InquiryMessageType.EVENT_CHALLENGE:
            finding = "本轮未执行真实调查，仅登记事件挑战缺口；事件材料仍不能升级为 L1-L5 主证据。"
            claims_challenged: List[str] = []
            cannot_establish = ["事件是否已经因果性改变 NDX 走势", "事件材料是否可直接成为 L1-L5 evidence_ref"]
            confidence = Confidence.LOW
        elif message_type == InquiryMessageType.OBSERVATION_INQUIRY:
            finding = "本轮未执行真实调查，仅登记数据异常或缺口；二次综合只能把它作为待核查限制。"
            claims_challenged = []
            cannot_establish = ["缺口背后的外部原因", "历史相似样本的胜率或收益"]
            confidence = Confidence.LOW
        else:
            finding = "本轮未执行真实调查，仅登记 Bridge 裁决缺口；现有 allowed artifacts 不能自动强化或反驳主结论。"
            claims_challenged = []
            cannot_establish = ["主要矛盾已经完全解决", "价格反映程度已经高置信确定"]
            confidence = Confidence.LOW

        source_authority = [
            EvidenceSourceAuthority(
                evidence_ref=ref,
                source_ref=ref,
                source_tier=self._source_tier_for_allowed_ref(ref),
                authority_note="受控调查只读取 AgentSpec.allowed_context_refs；该引用不自动升级为 L1-L5 evidence_ref。",
                supports=[message.question],
                limitations=["不能回写 L1-L5 layer card", "不能替代正式数据源升级流程"],
            )
            for ref in spec.allowed_context_refs[: spec.budget.max_source_refs or len(spec.allowed_context_refs)]
        ]
        return InvestigationReport(
            investigation_id=investigation_id,
            originating_agent_id=spec.agent_id,
            is_deterministic_stub=True,
            finding=finding,
            evidence_refs=list(spec.allowed_context_refs[: spec.budget.max_source_refs or len(spec.allowed_context_refs)]),
            counter_evidence_refs=[],
            claims_supported=[],
            claims_challenged=claims_challenged,
            cannot_establish=cannot_establish,
            confidence=confidence,
            limits=[
                "stage_2_minimal_deterministic_investigation_only",
                "no_external_research_performed",
                "no_real_investigation_performed",
                "no_backflow_to_l1_l5",
                f"allowed_context_notes={len(context_notes)}",
            ],
            source_authority=source_authority,
            effective_date=message.effective_date,
        )

    def _read_allowed_context_notes(self, refs: List[str], max_refs: int) -> List[str]:
        notes: List[str] = []
        for ref in refs[: max_refs or len(refs)]:
            path = (self.output_dir / ref).resolve()
            try:
                path.relative_to(self.output_dir)
            except ValueError:
                notes.append(f"{ref}: rejected_outside_run_dir")
                continue
            if not path.exists() or not path.is_file():
                notes.append(f"{ref}: artifact_not_found_or_symbolic_ref")
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                notes.append(f"{ref}: unreadable_json")
                continue
            if isinstance(payload, dict):
                keys = ", ".join(sorted(str(key) for key in list(payload.keys())[:8]))
                notes.append(f"{ref}: keys={keys}")
            else:
                notes.append(f"{ref}: {type(payload).__name__}")
        return notes

    def _source_tier_for_allowed_ref(self, ref: str) -> str:
        if ref.startswith("event_") or ref.startswith("cross_layer_questions"):
            return "candidate_external_material"
        if ref.startswith("layer_cards/") or ref.startswith("bridge_memos/") or ref == "synthesis_packet.pending":
            return "formal_data_source"
        return "unknown"

    def _build_bridge_v2(
        self,
        *,
        packet_model: AnalysisPacket,
        layer_cards: List[LayerCard],
        bridge_v1: BridgeMemo,
        router_output: InquiryRouterOutput,
        investigation_reports: List[InvestigationReport],
    ) -> BridgeMemo:
        effects: List[Dict[str, Any]] = []
        for report in investigation_reports:
            changed = bool(
                not getattr(report, "is_deterministic_stub", False)
                and report.claims_challenged
                and "strong_single_path_adjudication" not in report.claims_challenged
            )
            effects.append(
                {
                    "investigation_id": report.investigation_id,
                    "originating_agent_id": report.originating_agent_id,
                    "is_deterministic_stub": bool(getattr(report, "is_deterministic_stub", False)),
                    "effect_on_judgment": "downgraded_or_kept_unresolved" if changed else "stub_gap_recorded_no_judgment_change",
                    "finding": report.finding,
                    "confidence": _enum_value(report.confidence),
                    "evidence_refs": list(report.evidence_refs),
                    "cannot_establish": list(report.cannot_establish),
                }
            )

        accepted_ids = {spec.originating_message_id for spec in router_output.agent_specs}
        rejected_questions = [
            {
                "message_id": decision.message_id,
                "message_type": _enum_value(decision.message_type),
                "rejection_reason": decision.rejection_reason,
                "trigger": decision.trigger,
            }
            for decision in router_output.rejected_messages
        ]
        report_refs = [f"investigation_reports/{report.investigation_id}.json" for report in investigation_reports]
        old_principal = _model_dump(getattr(bridge_v1, "principal_contradiction", None))
        if not isinstance(old_principal, dict):
            old_principal = {}
        unresolved_questions = list(dict.fromkeys(
            list(getattr(bridge_v1, "unresolved_questions", []) or [])
            + [
                item
                for report in investigation_reports
                for item in list(report.cannot_establish)
            ]
        ))
        if old_principal:
            old_principal.setdefault("unresolved_questions", [])
            old_principal["unresolved_questions"] = list(dict.fromkeys(
                list(old_principal.get("unresolved_questions") or []) + unresolved_questions[:4]
            ))
        layers_connected = list(getattr(bridge_v1, "layers_connected", []) or [])
        if len(layers_connected) < 2:
            layers_connected = [card.layer for card in layer_cards[:2]]

        bridge_v2_payload = {
            "bridge_type": "feedback_bridge_v2",
            "layers_connected": layers_connected[:5],
            "cross_layer_claims": [],
            "conflicts": [_model_dump(item) for item in getattr(bridge_v1, "conflicts", []) or []],
            "typed_conflicts": [_model_dump(item) for item in getattr(bridge_v1, "typed_conflicts", []) or []],
            "resonance_chains": [_model_dump(item) for item in getattr(bridge_v1, "resonance_chains", []) or []],
            "transmission_paths": [_model_dump(item) for item in getattr(bridge_v1, "transmission_paths", []) or []],
            "principal_contradiction": old_principal or None,
            "secondary_contradictions": [_model_dump(item) for item in getattr(bridge_v1, "secondary_contradictions", []) or []],
            "price_reflection_map": [_model_dump(item) for item in getattr(bridge_v1, "price_reflection_map", []) or []],
            "contradiction_transformation_signals": [_model_dump(item) for item in getattr(bridge_v1, "contradiction_transformation_signals", []) or []],
            "unresolved_questions": unresolved_questions[:12],
            "implication_for_ndx": (
                "Bridge V2 已读取受控 InvestigationReport。"
                "若调查未能建立新证据，二次综合必须保留原有张力并降低强裁决倾向。"
            ),
            "key_uncertainties": list(dict.fromkeys(
                list(getattr(bridge_v1, "key_uncertainties", []) or [])
                + [item for report in investigation_reports for item in list(report.cannot_establish)]
            ))[:12],
            "event_refs": list(dict.fromkeys(getattr(bridge_v1, "event_refs", []) or [])),
            "normalization_notes": list(dict.fromkeys(
                list(getattr(bridge_v1, "normalization_notes", []) or [])
                + ["bridge_v2_deterministic_feedback_loop"]
            )),
            "investigation_effects": effects,
            "feedback_loop_summary": {
                "schema_version": "bridge_v2_feedback_summary_v1",
                "input_bridge": "bridge_memos/bridge_0.json",
                "input_messages": len(router_output.input_messages),
                "accepted_messages": sorted(accepted_ids),
                "rejected_messages": rejected_questions,
                "investigation_report_refs": report_refs,
                "changed_judgment_count": sum(1 for item in effects if item["effect_on_judgment"] == "downgraded_or_kept_unresolved"),
                "unchanged_or_unresolved_count": sum(1 for item in effects if item["effect_on_judgment"] != "downgraded_or_kept_unresolved"),
                "no_backflow_asserted": True,
            },
        }
        bridge_v2 = BridgeMemo.model_validate(bridge_v2_payload)
        self._save_json(self.bridge_dir / "bridge_v2.json", bridge_v2)
        return bridge_v2

    def _build_hypothesis_competition(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
        effective_date: str,
    ) -> HypothesisCompetition:
        counter_thesis = self._build_counter_thesis(
            synthesis_packet=synthesis_packet,
            bridge_v2=bridge_v2,
            investigation_reports=investigation_reports,
        )
        base_hypothesis = self._build_base_hypothesis_from_bridge(
            bridge_v2=bridge_v2,
            investigation_reports=investigation_reports,
        )
        hypotheses = [base_hypothesis] + list(counter_thesis.hypotheses)
        hypotheses = self._dedupe_hypotheses(hypotheses)

        fallback_warnings = self._competition_fallback_warnings(bridge_v2)
        downgrade_records = self._build_adjudication_change_records(
            base_hypothesis=base_hypothesis,
            counter_hypotheses=counter_thesis.hypotheses,
            investigation_reports=investigation_reports,
            fallback_warnings=fallback_warnings,
            effective_date=effective_date,
        )
        leading_id = "" if downgrade_records else base_hypothesis.hypothesis_id
        retained_disputes = list(dict.fromkeys(
            list(getattr(bridge_v2, "unresolved_questions", []) or [])
            + [item for report in investigation_reports for item in list(report.cannot_establish)]
            + [record.reason for record in downgrade_records if record.reason]
        ))[:12]
        if leading_id:
            hypotheses = [
                hypothesis.model_copy(update={"status": "leading", "adjudication_reason": "当前证据未触发改判，暂列主导解释。"})
                if hypothesis.hypothesis_id == leading_id else hypothesis
                for hypothesis in hypotheses
            ]
        elif hypotheses:
            hypotheses = [
                hypothesis.model_copy(update={"status": "kept_unresolved", "adjudication_reason": "存在调查反证、证据缺口或兜底痕迹，不能形成单一路径裁决。"})
                for hypothesis in hypotheses
            ]

        competition = HypothesisCompetition(
            input_refs=["synthesis_packet.json", "bridge_memos/bridge_v2.json", "investigation_reports/*.json"],
            forbidden_context_refs=["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
            hypotheses=hypotheses,
            leading_hypothesis_id=leading_id,
            retained_disputes=retained_disputes,
            downgrade_or_split_events=downgrade_records,
            insufficient_evidence_reason="" if len(hypotheses) >= 2 else "少于两个可竞争解释；只能保留证据不足状态。",
            fallback_warnings=fallback_warnings,
            principal_contradiction_quality=self._principal_contradiction_quality(bridge_v2),
            price_reflection_quality=self._price_reflection_quality(bridge_v2),
            adjudication_notes=[
                "Counter-Thesis 首次生成发生在 Thesis 之前，且禁止读取 thesis_draft.json。",
                "InvestigationReport 只影响假说状态、争议保留和重判记录，不回写 L1-L5。",
                "principal_contradiction / price_reflection 如有兜底痕迹，必须在裁决中降级或显式标记。",
            ],
        )
        history = AdjudicationHistory(
            effective_date=effective_date,
            records=downgrade_records
            or [
                AdjudicationChangeRecord(
                    version_id="adj_initial_v1",
                    previous_hypothesis_id="",
                    new_hypothesis_id=leading_id,
                    trigger_evidence_refs=[],
                    change_type="initial",
                    old_status="none",
                    new_status="leading" if leading_id else "insufficient_evidence",
                    reason="建立阶段 3 初始竞争裁决记录。",
                    effective_date=effective_date,
                )
            ],
            current_hypothesis_ids=[hypothesis.hypothesis_id for hypothesis in hypotheses],
        )
        self._save_json("counter_thesis.json", counter_thesis)
        self._save_json("hypothesis_competition.json", competition)
        self._save_json("adjudication_history.json", history)
        self._save_json(
            "competition_adjudication_manifest.json",
            {
                "schema_version": "competition_adjudication_manifest_v1",
                "phase": "stage_3_minimal_competition",
                "counter_thesis_independent": "thesis_draft.json" in set(counter_thesis.forbidden_context_refs),
                "hypothesis_count": len(hypotheses),
                "leading_hypothesis_id": leading_id,
                "downgrade_or_split_count": len(downgrade_records),
                "no_backflow_rule": "Competition artifacts may be read by Thesis and governance stages, but must not rewrite L1-L5 layer cards.",
            },
        )
        return competition

    def _build_counter_thesis(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
    ) -> CounterThesisDraft:
        payload = self._counter_thesis_prompt_payload(
            synthesis_packet=synthesis_packet,
            bridge_v2=bridge_v2,
            investigation_reports=investigation_reports,
        )
        allowed_refs = set(synthesis_packet.evidence_index.keys())
        fallback_reason = ""
        try:
            draft = self._run_stage(
                stage_key="counter_thesis",
                stage_name="counter_thesis",
                model_cls=CounterThesisDraft,
                payload=payload,
                validator=lambda candidate: self._validate_counter_thesis_draft(candidate, allowed_refs),
            )
            draft = self._normalize_counter_thesis_draft(draft, allowed_refs)
        except Exception as exc:
            logger.warning("counter_thesis LLM stage failed; using deterministic fallback: %s", exc)
            fallback_reason = str(exc)
            draft = self._build_deterministic_counter_thesis(
                synthesis_packet=synthesis_packet,
                bridge_v2=bridge_v2,
                investigation_reports=investigation_reports,
                fallback_reason=fallback_reason,
            )

        audit = self._counter_thesis_prompt_input_audit(payload)
        if fallback_reason:
            audit["fallback_reason"] = fallback_reason[:500]
        return draft.model_copy(
            update={
                "input_refs": ["synthesis_packet.json", "bridge_memos/bridge_0.json", "investigation_reports/*.json"],
                "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
                "prompt_input_audit": audit,
            }
        )

    def _counter_thesis_prompt_payload(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
    ) -> Dict[str, Any]:
        synthesis_payload = _model_dump(synthesis_packet)
        for key in (
            "competing_hypotheses",
            "hypothesis_competition_summary",
            "adjudication_history",
            "counter_thesis_boundary",
        ):
            synthesis_payload.pop(key, None)
        bridge_v1_summaries = [
            item
            for item in _as_list(synthesis_payload.get("bridge_summaries"))
            if isinstance(item, dict) and str(item.get("bridge_type") or "") != "feedback_bridge_v2"
        ]
        non_stub_reports = [
            _model_dump(report)
            for report in investigation_reports
            if not getattr(report, "is_deterministic_stub", False)
        ]
        return {
            "synthesis_packet_without_self_reference": synthesis_payload,
            "bridge_v1_structure": bridge_v1_summaries[:1],
            "bridge_v2_feedback_summary": _model_dump(getattr(bridge_v2, "feedback_loop_summary", {})),
            "non_stub_investigation_reports": non_stub_reports,
            "allowed_evidence_refs": sorted(synthesis_packet.evidence_index.keys()),
            "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
            "output_contract": "CounterThesisDraft",
        }

    def _validate_counter_thesis_draft(self, draft: CounterThesisDraft, allowed_refs: set[str]) -> List[str]:
        errors: List[str] = []
        if not draft.hypotheses:
            errors.append("CounterThesisDraft.hypotheses must contain at least one hypothesis.")
        for index, hypothesis in enumerate(draft.hypotheses):
            for field_name in ("support_evidence_refs", "counter_evidence_refs", "diagnostic_evidence_refs"):
                refs = [str(ref) for ref in getattr(hypothesis, field_name, []) or []]
                invalid = [ref for ref in refs if ref not in allowed_refs]
                if invalid:
                    errors.append(f"hypotheses[{index}].{field_name} contains refs outside evidence_index: {invalid[:5]}")
            if not hypothesis.support_evidence_refs:
                errors.append(f"hypotheses[{index}].support_evidence_refs must not be empty.")
            if not hypothesis.diagnostic_evidence_refs:
                errors.append(f"hypotheses[{index}].diagnostic_evidence_refs must not be empty.")
            if not hypothesis.falsification_conditions:
                errors.append(f"hypotheses[{index}].falsification_conditions must not be empty.")
        return errors

    def _normalize_counter_thesis_draft(self, draft: CounterThesisDraft, allowed_refs: set[str]) -> CounterThesisDraft:
        hypotheses: List[CompetingHypothesis] = []
        for hypothesis in draft.hypotheses[:2]:
            support_refs = [ref for ref in hypothesis.support_evidence_refs if ref in allowed_refs]
            counter_refs = [ref for ref in hypothesis.counter_evidence_refs if ref in allowed_refs]
            diagnostic_refs = [ref for ref in hypothesis.diagnostic_evidence_refs if ref in allowed_refs]
            text = " ".join(str(hypothesis.hypothesis_text or "").split())
            if not text or not support_refs or not diagnostic_refs:
                continue
            hypotheses.append(
                hypothesis.model_copy(
                    update={
                        "hypothesis_id": hypothesis.hypothesis_id or self._stable_hypothesis_id("counter", text),
                        "hypothesis_text": text,
                        "source": "counter_thesis",
                        "support_evidence_refs": support_refs[:10],
                        "counter_evidence_refs": counter_refs[:10],
                        "diagnostic_evidence_refs": diagnostic_refs[:10],
                        "source_refs": ["synthesis_packet.json", "bridge_memos/bridge_0.json", "investigation_reports/*.json"],
                    }
                )
            )
        return draft.model_copy(
            update={
                "hypotheses": hypotheses,
                "principal_counterargument": draft.principal_counterargument or (hypotheses[0].hypothesis_text if hypotheses else ""),
            }
        )

    def _counter_thesis_prompt_input_audit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        forbidden_refs = {"thesis_draft.json", "analysis_revised.json", "final_adjudication.json"}
        hits: List[str] = []

        def walk(value: Any, path: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"forbidden_context_refs", "forbidden_artifacts"}:
                        continue
                    walk(child, f"{path}.{key}" if path else str(key))
                return
            if isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
                return
            text = str(value)
            for ref in forbidden_refs:
                if ref in text:
                    hits.append(f"{path}:{ref}")

        walk(payload)
        prompt_files = sorted(str(path.relative_to(self.output_dir)) for path in self._prompt_audit_stage_dir("counter_thesis").glob("attempt_*.prompt.txt"))
        return {
            "measurement": "payload_tree_scan_excluding_forbidden_context_declarations",
            "thesis_exists_at_generation": (self.output_dir / "thesis_draft.json").exists(),
            "thesis_read": any("thesis_draft.json" in hit for hit in hits),
            "allowed_inputs_only": not hits,
            "forbidden_payload_refs": hits,
            "prompt_audit_files": prompt_files,
            "forbidden_context_refs": sorted(forbidden_refs),
        }

    def _build_deterministic_counter_thesis(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
        fallback_reason: str = "",
    ) -> CounterThesisDraft:
        principal = _model_dump(getattr(bridge_v2, "principal_contradiction", None))
        if not isinstance(principal, dict):
            principal = {}
        investigation_evidence = list(dict.fromkeys(
            ref
            for report in investigation_reports
            if not getattr(report, "is_deterministic_stub", False)
            for ref in list(report.evidence_refs)
            if ref in synthesis_packet.evidence_index
        ))
        unresolved = list(dict.fromkeys(
            list(getattr(bridge_v2, "unresolved_questions", []) or [])
            + [item for report in investigation_reports for item in list(report.cannot_establish)]
        ))
        base_refs = list(dict.fromkeys(
            list(principal.get("evidence_refs") or [])
            + [ref for conflict in synthesis_packet.high_severity_typed_conflicts for ref in list(conflict.evidence_refs)]
        ))
        counter_text = (
            "反方解释：现有证据更像是未解决张力和证据缺口，"
            "不足以支持把补查结果吸收到单一主线。"
        )
        if unresolved:
            counter_text += f" 关键缺口：{unresolved[0]}"
        counter_hypothesis = CompetingHypothesis(
            hypothesis_id=self._stable_hypothesis_id("counter", counter_text),
            hypothesis_text=counter_text,
            source="deterministic_fallback",
            support_evidence_refs=investigation_evidence or base_refs[:3],
            counter_evidence_refs=base_refs[:6],
            diagnostic_evidence_refs=list(dict.fromkeys(investigation_evidence + base_refs))[:8],
            cannot_explain=["如果后续正式数据源补齐并确认主要矛盾已解决，反方只能保留为历史争议。"],
            falsification_conditions=list(dict.fromkeys(
                [item for report in investigation_reports for item in list(report.cannot_establish)]
                + ["Bridge V2 原生给出充分 price_reflection_map 且关键反证被正式证据排除。"]
            ))[:8],
            confidence=Confidence.LOW if not investigation_evidence else Confidence.MEDIUM,
            status="candidate",
            adjudication_reason="反方只读取 SynthesisPacket / Bridge V2 / InvestigationReport，用于挑战单一路径吸收。",
            source_refs=["synthesis_packet.json", "bridge_memos/bridge_v2.json", "investigation_reports/*.json"],
        )
        return CounterThesisDraft(
            input_refs=["synthesis_packet.json", "bridge_memos/bridge_v2.json", "investigation_reports/*.json"],
            forbidden_context_refs=["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
            hypotheses=[counter_hypothesis],
            principal_counterargument=counter_text,
            cannot_establish=unresolved[:10] or ["反方不能证明主线错误，只能证明证据不足或争议仍需保留。"],
            prompt_input_audit={
                "thesis_exists_at_generation": (self.output_dir / "thesis_draft.json").exists(),
                "thesis_read": False,
                "allowed_inputs_only": True,
                "fallback_reason": fallback_reason[:500],
                "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"],
            },
        )

    def _build_base_hypothesis_from_bridge(
        self,
        *,
        bridge_v2: BridgeMemo,
        investigation_reports: List[InvestigationReport],
    ) -> CompetingHypothesis:
        principal = _model_dump(getattr(bridge_v2, "principal_contradiction", None))
        if not isinstance(principal, dict):
            principal = {}
        support_refs = list(dict.fromkeys(principal.get("evidence_refs") or []))
        typed_refs = [
            ref
            for conflict in getattr(bridge_v2, "typed_conflicts", []) or []
            for ref in list(getattr(conflict, "evidence_refs", []) or [])
        ]
        if not support_refs:
            support_refs = list(dict.fromkeys(typed_refs))[:8]
        counter_refs = list(dict.fromkeys(
            ref
            for report in investigation_reports
            if report.claims_challenged
            for ref in list(report.evidence_refs)
        ))
        transformation_signals = _as_list(principal.get("transformation_signals"))
        falsifiers = []
        for item in transformation_signals:
            signal = item.get("signal") if isinstance(item, dict) else item
            if str(signal or "").strip():
                falsifiers.append(str(signal))
        for conflict in getattr(bridge_v2, "typed_conflicts", []) or []:
            falsifiers.extend(str(item) for item in list(getattr(conflict, "falsifiers", []) or []))
        text = principal.get("summary") or "主线解释：Bridge V2 的主要矛盾仍是当前综合判断的基础。"
        return CompetingHypothesis(
            hypothesis_id=self._stable_hypothesis_id("base", text),
            hypothesis_text="主线解释：" + str(text).removeprefix("主线解释："),
            source="bridge_v2",
            support_evidence_refs=support_refs[:10],
            counter_evidence_refs=counter_refs[:8],
            diagnostic_evidence_refs=list(dict.fromkeys(support_refs + typed_refs + counter_refs))[:10],
            cannot_explain=list(dict.fromkeys(
                list(getattr(bridge_v2, "unresolved_questions", []) or [])
                + [item for report in investigation_reports for item in list(report.cannot_establish)]
            ))[:10],
            falsification_conditions=list(dict.fromkeys(falsifiers))[:10] or ["关键价格反映或主要矛盾证据被正式证据反驳。"],
            confidence=Confidence.MEDIUM if support_refs else Confidence.LOW,
            status="candidate",
            adjudication_reason="来自 Bridge V2 的主要矛盾候选，等待与反方假说比较。",
            source_refs=["bridge_memos/bridge_v2.json"],
        )

    def _build_adjudication_change_records(
        self,
        *,
        base_hypothesis: CompetingHypothesis,
        counter_hypotheses: List[CompetingHypothesis],
        investigation_reports: List[InvestigationReport],
        fallback_warnings: List[str],
        effective_date: str,
    ) -> List[AdjudicationChangeRecord]:
        records: List[AdjudicationChangeRecord] = []
        trigger_refs = list(dict.fromkeys(
            ref
            for report in investigation_reports
            if not getattr(report, "is_deterministic_stub", False)
            and (report.claims_challenged or report.counter_evidence_refs)
            for ref in list(report.evidence_refs)
        ))
        if trigger_refs or fallback_warnings:
            records.append(
                AdjudicationChangeRecord(
                    version_id="adj_stage3_downgrade_v1",
                    previous_hypothesis_id=base_hypothesis.hypothesis_id,
                    new_hypothesis_id=counter_hypotheses[0].hypothesis_id if counter_hypotheses else "",
                    trigger_evidence_refs=trigger_refs,
                    change_type="kept_unresolved" if trigger_refs else "downgrade",
                    old_status="candidate",
                    new_status="kept_unresolved",
                    reason=(
                        "受控调查挑战了强单一路径裁决，或 principal_contradiction / price_reflection 存在兜底痕迹；"
                        "本轮保留旧主线但降级为争议状态。"
                    ),
                    effective_date=effective_date,
                )
            )
        return records

    def _hypothesis_competition_summary(self, competition: HypothesisCompetition) -> Dict[str, Any]:
        return {
            "schema_version": competition.schema_version,
            "hypothesis_count": len(competition.hypotheses),
            "leading_hypothesis_id": competition.leading_hypothesis_id,
            "retained_disputes": list(competition.retained_disputes),
            "downgrade_or_split_count": len(competition.downgrade_or_split_events),
            "fallback_warnings": list(competition.fallback_warnings),
            "principal_contradiction_quality": competition.principal_contradiction_quality,
            "price_reflection_quality": competition.price_reflection_quality,
        }

    def _dedupe_hypotheses(self, hypotheses: List[CompetingHypothesis]) -> List[CompetingHypothesis]:
        deduped: List[CompetingHypothesis] = []
        seen = set()
        for hypothesis in hypotheses:
            if hypothesis.hypothesis_id in seen:
                continue
            seen.add(hypothesis.hypothesis_id)
            deduped.append(hypothesis)
        return deduped

    def _stable_hypothesis_id(self, prefix: str, text: str) -> str:
        return f"hyp_{prefix}_{hashlib.sha1(str(text).encode('utf-8')).hexdigest()[:10]}"

    def _competition_fallback_warnings(self, bridge: BridgeMemo) -> List[str]:
        notes = list(getattr(bridge, "normalization_notes", []) or [])
        warnings = []
        for note in notes:
            note_text = str(note)
            if "principal_contradiction" in note_text or "price_reflection" in note_text:
                warnings.append(note_text)
        if getattr(bridge, "principal_contradiction", None) is None:
            warnings.append("principal_contradiction_missing")
        if not list(getattr(bridge, "price_reflection_map", []) or []):
            warnings.append("price_reflection_map_missing")
        return list(dict.fromkeys(warnings))

    def _principal_contradiction_quality(self, bridge: BridgeMemo) -> str:
        if getattr(bridge, "principal_contradiction", None) is None:
            return "missing"
        notes = " ".join(str(item) for item in getattr(bridge, "normalization_notes", []) or [])
        return "fallback" if "principal_contradiction" in notes else "native"

    def _price_reflection_quality(self, bridge: BridgeMemo) -> str:
        if not list(getattr(bridge, "price_reflection_map", []) or []):
            return "missing"
        notes = " ".join(str(item) for item in getattr(bridge, "normalization_notes", []) or [])
        return "fallback" if "price_reflection" in notes else "native"

    def _build_evidence_registry(
        self,
        *,
        packet_model: AnalysisPacket,
        synthesis_packet: SynthesisPacket,
        investigation_reports: List[InvestigationReport],
        hypothesis_competition: HypothesisCompetition,
    ) -> EvidenceRegistry:
        effective_date = self._effective_date(packet_model)
        passports: Dict[str, EvidencePassport] = {}

        for evidence_id, item in list(synthesis_packet.evidence_index.items()):
            if "#" in evidence_id:
                continue
            raw_payload = self._raw_payload_for_evidence_ref(packet_model, evidence_id)
            quality = raw_payload.get("data_quality") if isinstance(raw_payload.get("data_quality"), dict) else {}
            permission = item.get("permission_type") if isinstance(item, dict) else ""
            issues = data_evidence_issues(raw_payload, function_id=evidence_id.split(".", 1)[-1], backtest_date=packet_model.meta.get("backtest_date") if isinstance(packet_model.meta, dict) else None) if raw_payload else {"hard_block": [], "degraded": [], "audit_warn": []}
            downgrade_rules = [issue["code"] for issue in issues.get("hard_block", []) + issues.get("degraded", []) if isinstance(issue, dict)]
            item_source_tier = item.get("source_tier") if isinstance(item, dict) else ""
            source_tier = self._normalize_source_tier(
                quality.get("source_tier") or item_source_tier or raw_payload.get("source_tier")
            )
            field_authority = self._field_authority_from_payload(raw_payload)
            field_usages = self._field_authority_usages(field_authority)
            mixed_field_authority = len(field_usages) > 1
            parent_usage = next(iter(field_usages), "") if len(field_usages) == 1 else ""
            parent_downgrade_rules = list(downgrade_rules)
            if mixed_field_authority:
                parent_downgrade_rules.append("mixed_field_authority")
            elif parent_usage and parent_usage != "core_allowed":
                parent_downgrade_rules.append(f"field_authority_{parent_usage}")
            passports[evidence_id] = EvidencePassport(
                evidence_id=evidence_id,
                evidence_kind="data",
                source_ref=str(quality.get("source_name") or quality.get("provider") or evidence_id),
                source_tier=source_tier,
                permission_type=permission or None,
                authority_model={
                    "can_support": item.get("canonical_question") if isinstance(item, dict) else "",
                    "cannot_support": list(item.get("misread_guards") or []) if isinstance(item, dict) else [],
                    "requires_confirmation": list(item.get("cross_validation_targets") or []) if isinstance(item, dict) else [],
                    "field_authority": field_authority,
                    "field_usages": sorted(field_usages),
                    "field_usage": parent_usage,
                    "mixed_field_authority": mixed_field_authority,
                },
                downgrade_rules=list(dict.fromkeys(parent_downgrade_rules)),
                data_quality=quality,
                effective_date=str(quality.get("effective_date") or effective_date),
                verified=(
                    source_tier not in {"unknown"}
                    and not issues.get("hard_block")
                    and not mixed_field_authority
                    and parent_usage != "rejected"
                ),
                limitations=list(item.get("misread_guards") or []) if isinstance(item, dict) else [],
            )
            for field, field_rule in field_authority.items():
                if not isinstance(field_rule, dict):
                    continue
                field_ref = f"{evidence_id}#{field}"
                usage = str(field_rule.get("usage") or "").strip().lower()
                field_rules = list(downgrade_rules)
                if usage and usage != "core_allowed":
                    field_rules.append(f"field_authority_{usage}")
                passports[field_ref] = EvidencePassport(
                    evidence_id=field_ref,
                    evidence_kind="data",
                    source_ref=str(quality.get("source_name") or quality.get("provider") or evidence_id),
                    source_tier=source_tier,
                    permission_type=permission or None,
                    authority_model={
                        "parent_evidence_ref": evidence_id,
                        "field_name": field,
                        "field_usage": usage,
                        "field_authority": field_rule,
                        "can_support": item.get("canonical_question") if isinstance(item, dict) else "",
                        "cannot_support": list(item.get("misread_guards") or []) if isinstance(item, dict) else [],
                    },
                    downgrade_rules=list(dict.fromkeys(field_rules)),
                    data_quality=quality,
                    effective_date=str(quality.get("effective_date") or effective_date),
                    verified=(
                        source_tier not in {"unknown"}
                        and not issues.get("hard_block")
                        and usage != "rejected"
                    ),
                    limitations=list(item.get("misread_guards") or []) if isinstance(item, dict) else [],
                )

        for event_passport in self._event_passports(effective_date):
            passports[event_passport.evidence_id] = event_passport

        for report in investigation_reports:
            evidence_id = f"investigation_reports/{report.investigation_id}.json"
            tiers = [self._normalize_source_tier(item.source_tier) for item in report.source_authority]
            source_tier = "formal_data_source" if "formal_data_source" in tiers else (tiers[0] if tiers else "unknown")
            report_downgrade_rules = ["investigation_is_downstream_no_l1_l5_backflow", *list(report.limits)]
            if getattr(report, "is_deterministic_stub", False):
                report_downgrade_rules.append("deterministic_stub_not_real_investigation")
            passports[evidence_id] = EvidencePassport(
                evidence_id=evidence_id,
                evidence_kind="investigation",
                source_ref=report.originating_agent_id,
                source_tier=source_tier,
                authority_model={
                    "can_support": list(report.claims_supported),
                    "cannot_support": list(report.cannot_establish),
                    "counter_evidence_refs": list(report.counter_evidence_refs),
                },
                downgrade_rules=report_downgrade_rules,
                effective_date=report.effective_date,
                verified=bool(
                    not getattr(report, "is_deterministic_stub", False)
                    and report.finding
                    and report.evidence_refs
                    and report.cannot_establish
                ),
                limitations=list(report.cannot_establish),
            )

        for hypothesis in hypothesis_competition.hypotheses:
            passports[hypothesis.hypothesis_id] = EvidencePassport(
                evidence_id=hypothesis.hypothesis_id,
                evidence_kind="hypothesis",
                source_ref="hypothesis_competition.json",
                source_tier="derived_inference",
                authority_model={
                    "support_evidence_refs": list(hypothesis.support_evidence_refs),
                    "counter_evidence_refs": list(hypothesis.counter_evidence_refs),
                    "diagnostic_evidence_refs": list(hypothesis.diagnostic_evidence_refs),
                    "cannot_explain": list(hypothesis.cannot_explain),
                },
                downgrade_rules=["derived_inference_cannot_replace_underlying_evidence"],
                effective_date=effective_date,
                verified=bool(hypothesis.support_evidence_refs and hypothesis.counter_evidence_refs and hypothesis.falsification_conditions),
                limitations=list(hypothesis.cannot_explain),
            )

        downgrade_summary = [
            {
                "evidence_id": passport.evidence_id,
                "reason": list(passport.downgrade_rules),
                "source_tier": passport.source_tier,
            }
            for passport in passports.values()
            if passport.downgrade_rules or not passport.verified
        ][:80]
        return EvidenceRegistry(
            effective_date=effective_date,
            passports=passports,
            source_tier_policy=self._source_tier_policy(),
            downgrade_summary=downgrade_summary,
        )

    def _raw_payload_for_evidence_ref(self, packet: AnalysisPacket, evidence_ref: str) -> Dict[str, Any]:
        if "." not in evidence_ref:
            return {}
        layer, function_id = evidence_ref.split(".", 1)
        function_id = function_id.split("#", 1)[0]
        layer_data = packet.raw_data.get(layer, {}) if isinstance(packet.raw_data, dict) else {}
        payload = layer_data.get(function_id) if isinstance(layer_data, dict) else {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _field_authority_from_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        value = raw_payload.get("value") if isinstance(raw_payload.get("value"), dict) else {}
        value_field_authority = value.get("MetricAuthority") if isinstance(value.get("MetricAuthority"), dict) else {}
        quality = raw_payload.get("data_quality") if isinstance(raw_payload.get("data_quality"), dict) else {}
        quality_field_authority = quality.get("metric_authority") if isinstance(quality.get("metric_authority"), dict) else {}
        return value_field_authority or quality_field_authority

    @staticmethod
    def _field_authority_usages(field_authority: Dict[str, Any]) -> set[str]:
        return {
            str(rule.get("usage") or "").strip().lower() or "unknown"
            for rule in field_authority.values()
            if isinstance(rule, dict)
        }

    def _normalize_source_tier(self, value: Any) -> str:
        return normalize_source_tier_for_evidence_passport(value)

    def _event_passports(self, effective_date: str) -> List[EvidencePassport]:
        payload = self._load_local_json(self.output_dir / "event_narrative_ledger.json", {})
        claims = [
            claim
            for event in _as_list(payload.get("events")) if isinstance(event, dict)
            for claim in _as_list(event.get("claims")) if isinstance(claim, dict)
        ]
        passports: List[EvidencePassport] = []
        for claim in claims:
            claim_id = str(claim.get("claim_id") or "").strip()
            if not claim_id:
                continue
            claim_type = str(claim.get("claim_type") or "")
            verified = claim_type in {"official_fact", "company_disclosure", "data_release_claim"} and bool(claim.get("source_url") or claim.get("source_name"))
            source_tier = "candidate_external_material"
            if claim_type in {"official_fact", "company_disclosure", "data_release_claim"}:
                source_tier = "official"
            passports.append(
                EvidencePassport(
                    evidence_id=claim_id,
                    evidence_kind="event",
                    source_ref=str(claim.get("source_url") or claim.get("source_name") or claim.get("source_event_id") or claim_id),
                    source_tier=source_tier,
                    authority_model={
                        "claim_type": claim_type,
                        "can_support": claim.get("what_it_can_support", ""),
                        "cannot_support": claim.get("what_it_cannot_support", ""),
                        "needs_data_confirmation": claim.get("needs_data_confirmation", True),
                    },
                    downgrade_rules=self._event_downgrade_rules(claim),
                    effective_date=effective_date,
                    verified=verified and not claim.get("needs_data_confirmation"),
                    limitations=_as_list(claim.get("counterevidence_or_limits")) + [str(claim.get("what_it_cannot_support") or "")],
                )
            )
        return passports

    def _event_downgrade_rules(self, claim: Dict[str, Any]) -> List[str]:
        rules = ["event_material_cannot_be_l1_l5_primary_evidence"]
        if claim.get("needs_data_confirmation"):
            rules.append("event_claim_requires_data_confirmation")
        if not claim.get("source_url"):
            rules.append("event_claim_missing_source_url")
        if claim.get("raw_text_available") is False:
            rules.append("event_claim_title_only_or_unread_full_text")
        if str(claim.get("claim_type") or "") in {"narrative_claim", "rumor_claim", "interpretation_claim", "view_claim"}:
            rules.append("non_official_event_claim_cannot_support_strong_market_conclusion")
        return list(dict.fromkeys(rules))

    def _source_tier_policy(self) -> Dict[str, Any]:
        return {
            "schema_version": "source_tier_policy_v1",
            "can_support_strong_data_claim": ["official", "licensed_provider", "licensed_manual", "formal_data_source"],
            "must_not_support_strong_data_claim": ["candidate_external_material", "proxy", "derived_inference", "unknown"],
            "downgrade_rules": [
                "headline/news/social/event materials stay candidate until upgraded through a formal data-source path.",
                "proxy indicators cannot be described as official fact.",
                "technical indicators cannot prove valuation cheapness or fundamental improvement.",
                "derived hypotheses and final claims cannot replace their underlying evidence_refs.",
                "missing counter evidence or falsification conditions downgrades final claims.",
            ],
        }

    def _evidence_registry_summary(self, registry: EvidenceRegistry) -> Dict[str, Any]:
        by_kind: Dict[str, int] = {}
        by_tier: Dict[str, int] = {}
        for passport in registry.passports.values():
            by_kind[passport.evidence_kind] = by_kind.get(passport.evidence_kind, 0) + 1
            by_tier[passport.source_tier] = by_tier.get(passport.source_tier, 0) + 1
        return {
            "schema_version": registry.schema_version,
            "passport_count": len(registry.passports),
            "by_kind": by_kind,
            "by_source_tier": by_tier,
            "downgrade_count": len(registry.downgrade_summary),
            "source_tier_policy_ref": "evidence_registry.json:source_tier_policy",
        }

    def _build_final_claim_ledger(
        self,
        *,
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        final_adjudication: FinalAdjudication,
        evidence_registry: EvidenceRegistry,
        effective_date: str,
        risk_report: Optional[RiskBoundaryReport] = None,
    ) -> ClaimLedger:
        entries: List[ClaimLedgerEntry] = []
        common_refs = self._compact_string_refs(
            [ref for chain in getattr(final_adjudication, "key_support_chains", []) or [] for ref in chain.evidence_refs]
            + list(getattr(final_adjudication, "evidence_refs", []) or [])
            + [ref for chain in getattr(thesis, "key_support_chains", []) or [] for ref in chain.evidence_refs]
        )

        def add(source_stage: str, claim_type: str, claim_text: str, evidence_refs: List[str], inference_steps: List[str], falsifiers: List[str]) -> None:
            text = " ".join(str(claim_text or "").split())
            if not text:
                return
            claim_id = f"claim:{source_stage}:{hashlib.sha1((claim_type + '|' + text).encode('utf-8')).hexdigest()[:12]}"
            raw_refs = self._compact_string_refs(evidence_refs or common_refs)
            # valuation 放宽到 {L1, L3, L4}：deep_research_canon.get_ndx_pe_and_earnings_yield 的
            # cross_validation_targets 显式包含 get_10y_real_rate（L1）与 get_ndx_ndxe_ratio（L3），
            # 二者是估值判断的合法交叉验证证据；仍排除 L2/L5，"技术指标/情绪不能证明估值便宜"的红线不变。
            # risk_boundary 不设层级白名单：风险表述的合法来源覆盖全部层，限制无意义。
            layer_scope = {
                "valuation": {"L1", "L3", "L4"},
                "timing": {"L2", "L3", "L5"},
                "price_reflection": {"L5"},
            }.get(claim_type)
            if layer_scope:
                raw_refs = [ref for ref in raw_refs if str(ref).split(".", 1)[0] in layer_scope]
            # LLM 有时把 "known_data_gaps" 一类说明性 token 混进 evidence refs；
            # 只保留形如 L#.func 或注册表内的真实引用，其余记录为被剔除 token，不让它冒充缺失证据去阻断发布。
            entry_refs = [
                ref
                for ref in raw_refs
                if ref in evidence_registry.passports or _EVIDENCE_REF_PATTERN.fullmatch(ref)
            ]
            dropped_tokens = [ref for ref in raw_refs if ref not in entry_refs]
            counter_refs, counter_method = self._claim_specific_counter_refs(
                claim_type=claim_type,
                synthesis_packet=synthesis_packet,
                thesis=thesis,
                final_adjudication=final_adjudication,
            )
            falsification_conditions, falsifier_method = self._claim_specific_falsifiers(
                claim_type=claim_type,
                provided_falsifiers=falsifiers,
                synthesis_packet=synthesis_packet,
                thesis=thesis,
                final_adjudication=final_adjudication,
                risk_report=risk_report,
            )
            entry = ClaimLedgerEntry(
                claim_id=claim_id,
                source_stage=source_stage,  # type: ignore[arg-type]
                claim_text=text,
                claim_type=claim_type,  # type: ignore[arg-type]
                evidence_refs=entry_refs,
                counter_evidence_refs=counter_refs,
                inference_steps=self._compact_strings(inference_steps),
                falsification_conditions=falsification_conditions,
                counter_evidence_method=counter_method,
                falsifier_method=falsifier_method,
                dropped_non_evidence_tokens=dropped_tokens,
            )
            entries.append(self._verify_claim_entry(entry, evidence_registry))

        add(
            "thesis",
            "market_state",
            thesis.main_thesis,
            common_refs,
            [thesis.environment_assessment, thesis.valuation_assessment, thesis.timing_assessment],
            list(getattr(thesis, "invalidation_conditions", []) or []),
        )
        add("thesis", "valuation", thesis.valuation_assessment, common_refs, [thesis.valuation_assessment], list(getattr(thesis, "invalidation_conditions", []) or []))
        add("thesis", "timing", thesis.timing_assessment, common_refs, [thesis.timing_assessment], list(getattr(thesis, "invalidation_conditions", []) or []))
        add("thesis", "price_reflection", getattr(thesis, "priced_narrative", ""), common_refs, [getattr(thesis, "payoff_assessment", "")], list(getattr(thesis, "invalidation_conditions", []) or []))
        add("final", "market_state", final_adjudication.final_stance, common_refs, [final_adjudication.adjudicator_notes], list(final_adjudication.invalidation_conditions or []))
        add("final", "market_state", getattr(final_adjudication.reader_final, "one_liner", ""), list(getattr(final_adjudication.reader_final, "evidence_refs", []) or []) + common_refs, list(getattr(final_adjudication.reader_final, "three_reasons", []) or []), list(getattr(final_adjudication.reader_final, "invalidation_summary", []) or []))
        add("final", "risk_boundary", "；".join(str(item) for item in list(final_adjudication.must_preserve_risks or [])[:6]), common_refs, ["Final 必须保留 Risk Sentinel 和主要矛盾中的风险边界。"], list(final_adjudication.invalidation_conditions or []))
        add("final", "action_translation", "；".join(str(getattr(action, "action", "")) for action in list(getattr(final_adjudication, "portfolio_actions", []) or [])[:4]), common_refs, [str(getattr(action, "rationale", "")) for action in list(getattr(final_adjudication, "portfolio_actions", []) or [])[:4]], list(final_adjudication.invalidation_conditions or []))

        publish_gate = self._claim_ledger_publish_gate(entries)
        return ClaimLedger(
            effective_date=effective_date,
            entries=entries,
            publish_gate=publish_gate,
        )

    def _verify_claim_entry(self, entry: ClaimLedgerEntry, registry: EvidenceRegistry) -> ClaimLedgerEntry:
        missing_refs = [ref for ref in entry.evidence_refs if ref not in registry.passports]
        registered_refs = [ref for ref in entry.evidence_refs if ref in registry.passports]
        weak_refs = [
            ref
            for ref in registered_refs
            if registry.passports[ref].source_tier in {"candidate_external_material", "proxy", "derived_inference", "unknown"}
        ]
        reasons = []
        block = False
        evidence_field_refs = [ref for ref in registered_refs if "#" in ref]
        field_authority_records: List[tuple[str, str, str, str, bool]] = []
        for ref in registered_refs:
            passport = registry.passports[ref]
            authority_model = passport.authority_model if isinstance(passport.authority_model, dict) else {}
            if "#" in ref:
                field = str(authority_model.get("field_name") or ref.rsplit("#", 1)[-1])
                field_rule = authority_model.get("field_authority") if isinstance(authority_model.get("field_authority"), dict) else {}
                usage = str(authority_model.get("field_usage") or field_rule.get("usage") or "unknown").strip().lower()
                field_authority_records.append((ref, field, usage, passport.source_tier, passport.verified))
            elif authority_model.get("mixed_field_authority"):
                reasons.append(f"mixed_field_authority_parent_ref:{ref}")
            else:
                parent_usage = str(authority_model.get("field_usage") or "").strip().lower()
                if parent_usage in {"supporting_only", "validation_only", "audit_only", "unknown"}:
                    reasons.append(f"field_authority_{parent_usage}_parent_ref:{ref}")
                elif parent_usage == "rejected":
                    reasons.append(f"field_authority_rejected_parent_ref:{ref}")
                    block = True
        if not entry.evidence_refs:
            reasons.append("missing_evidence_refs")
            block = True
        if missing_refs:
            # 比例原则：个别引用无法核验（多为模型笔误/幻觉引用名）时点名降级；
            # 只有当没有任何可核验引用时，才等同于证据缺失而阻断。
            reasons.append("unverifiable_evidence_refs:" + ",".join(missing_refs[:5]))
            if not registered_refs:
                block = True
        if not entry.counter_evidence_refs:
            reasons.append("missing_counter_evidence_refs")
        if not entry.falsification_conditions:
            reasons.append("missing_falsification_conditions")
        if getattr(entry, "counter_evidence_method", "") == "not_claim_specific":
            reasons.append("counter_evidence_not_claim_specific")
        if getattr(entry, "falsifier_method", "") == "not_claim_specific":
            reasons.append("falsification_conditions_not_claim_specific")
        if weak_refs and not any(registry.passports[ref].source_tier in {"official", "licensed_provider", "licensed_manual", "formal_data_source"} for ref in registered_refs):
            reasons.append("only_weak_or_derived_evidence_refs")
        supporting_field_refs = [
            field_ref
            for field_ref, _, usage, _, _ in field_authority_records
            if usage in {"supporting_only", "validation_only", "audit_only", "unknown", ""}
        ]
        rejected_field_refs = [field_ref for field_ref, _, usage, _, _ in field_authority_records if usage == "rejected"]
        if supporting_field_refs:
            usages = sorted({usage or "unknown" for ref, _, usage, _, _ in field_authority_records if ref in supporting_field_refs})
            reasons.append("field_authority_" + "_or_".join(usages) + ":" + ",".join(supporting_field_refs))
        if rejected_field_refs:
            reasons.append("field_authority_rejected:" + ",".join(rejected_field_refs))
            rejected_fields = {field for _, field, usage, _, _ in field_authority_records if usage == "rejected"}
            strong_tiers = {"official", "licensed_provider", "licensed_manual", "formal_data_source"}
            rescued_fields = {
                field
                for _, field, usage, source_tier, passport_verified in field_authority_records
                if usage == "core_allowed" and source_tier in strong_tiers and passport_verified
            }
            if not rejected_fields.issubset(rescued_fields):
                block = True
        verified = not reasons
        return entry.model_copy(
            update={
                "verified": verified,
                "authority_status": "verified" if verified else ("blocked" if block else "downgraded"),
                "downgrade_reason": "；".join(reasons),
                "evidence_field_refs": list(dict.fromkeys(evidence_field_refs)),
            }
        )

    def _claim_ledger_publish_gate(self, entries: List[ClaimLedgerEntry]) -> Dict[str, Any]:
        blocked = [entry.claim_id for entry in entries if entry.authority_status == "blocked"]
        downgraded = [entry.claim_id for entry in entries if entry.authority_status == "downgraded"]
        status = "pass" if entries and not blocked and not downgraded else ("blocked" if blocked else "downgraded")
        return {
            "status": status,
            "entry_count": len(entries),
            "verified_count": sum(1 for entry in entries if entry.verified),
            "blocked_claim_ids": blocked,
            "downgraded_claim_ids": downgraded,
            "rule": "重要 final/thesis claim 必须同时有 evidence_refs、counter_evidence_refs、inference_steps、falsification_conditions，且证据权限不能越权。",
        }

    def _attach_claims_to_evidence_registry(self, registry: EvidenceRegistry, ledger: ClaimLedger) -> EvidenceRegistry:
        passports = dict(registry.passports)
        for entry in ledger.entries:
            passports[entry.claim_id] = EvidencePassport(
                evidence_id=entry.claim_id,
                evidence_kind="final_claim",
                source_ref=f"final_claim_ledger.json:{entry.claim_id}",
                source_tier="derived_inference",
                authority_model={
                    "claim_type": entry.claim_type,
                    "evidence_refs": list(entry.evidence_refs),
                    "counter_evidence_refs": list(entry.counter_evidence_refs),
                },
                downgrade_rules=[entry.downgrade_reason] if entry.downgrade_reason else ["derived_final_claim_requires_underlying_evidence"],
                effective_date=ledger.effective_date,
                verified=entry.verified,
                limitations=["Final claim is not primary evidence; inspect underlying evidence_refs."],
            )
            for ref in entry.evidence_refs + entry.counter_evidence_refs:
                passport = passports.get(ref)
                if passport is None:
                    continue
                linked = list(passport.linked_claim_ids)
                if entry.claim_id not in linked:
                    linked.append(entry.claim_id)
                passports[ref] = passport.model_copy(update={"linked_claim_ids": linked})
        return registry.model_copy(update={"passports": passports, "downgrade_summary": self._registry_downgrade_summary(passports)})

    def _registry_downgrade_summary(self, passports: Dict[str, EvidencePassport]) -> List[Dict[str, Any]]:
        return [
            {
                "evidence_id": passport.evidence_id,
                "reason": list(passport.downgrade_rules),
                "source_tier": passport.source_tier,
            }
            for passport in passports.values()
            if passport.downgrade_rules or not passport.verified
        ][:120]

    def _claim_counter_refs(self, synthesis_packet: SynthesisPacket, thesis: ThesisDraft, final_adjudication: FinalAdjudication) -> List[str]:
        refs: List[str] = []
        for conflict in list(synthesis_packet.high_severity_typed_conflicts or []):
            refs.extend(list(getattr(conflict, "evidence_refs", []) or []))
        for hypothesis in list(synthesis_packet.competing_hypotheses or []):
            refs.extend(list(getattr(hypothesis, "counter_evidence_refs", []) or []))
        for item in list(getattr(thesis, "price_reflection_map", []) or []) + list(getattr(final_adjudication, "price_reflection_map", []) or []):
            refs.extend(list(getattr(item, "counterevidence_refs", []) or []))
        return self._compact_string_refs(refs)

    def _claim_falsifiers(self, thesis: ThesisDraft, final_adjudication: FinalAdjudication, synthesis_packet: SynthesisPacket) -> List[str]:
        items: List[str] = []
        items.extend(str(item) for item in list(getattr(thesis, "invalidation_conditions", []) or []))
        items.extend(str(item) for item in list(getattr(final_adjudication, "invalidation_conditions", []) or []))
        reader = getattr(final_adjudication, "reader_final", None)
        if reader is not None:
            items.extend(str(item) for item in list(getattr(reader, "invalidation_summary", []) or []))
        for hypothesis in list(synthesis_packet.competing_hypotheses or []):
            items.extend(str(item) for item in list(getattr(hypothesis, "falsification_conditions", []) or []))
        return self._compact_strings(items)

    def _claim_specific_counter_refs(
        self,
        *,
        claim_type: str,
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        final_adjudication: FinalAdjudication,
    ) -> tuple[List[str], str]:
        competing_support_refs = [
            ref
            for hypothesis in list(synthesis_packet.competing_hypotheses or [])
            if str(getattr(hypothesis, "source", "")) in {"counter_thesis", "deterministic_fallback", "investigation"}
            for ref in list(getattr(hypothesis, "support_evidence_refs", []) or [])
        ]
        typed_conflict_refs = [
            ref
            for conflict in list(synthesis_packet.high_severity_typed_conflicts or [])
            for ref in list(getattr(conflict, "evidence_refs", []) or [])
        ]
        price_counter_refs = [
            ref
            for item in list(getattr(thesis, "price_reflection_map", []) or []) + list(getattr(final_adjudication, "price_reflection_map", []) or [])
            for ref in list(getattr(item, "counterevidence_refs", []) or [])
        ]
        invalidation_related_refs = [
            ref
            for view in list(getattr(final_adjudication, "time_horizon_views", []) or []) + list(getattr(thesis, "time_horizon_views", []) or [])
            for ref in list(getattr(view, "evidence_refs", []) or [])
        ]

        if claim_type == "market_state":
            refs = self._compact_string_refs(competing_support_refs + typed_conflict_refs)
            return refs, "opposing_hypothesis_support_plus_typed_conflicts" if refs else "not_claim_specific"
        if claim_type == "price_reflection":
            refs = self._compact_string_refs(price_counter_refs + competing_support_refs)
            return refs, "price_reflection_counterevidence" if refs else "not_claim_specific"
        if claim_type == "risk_boundary":
            refs = self._compact_string_refs(typed_conflict_refs + price_counter_refs)
            return refs, "risk_conflicts_and_price_counterevidence" if refs else "not_claim_specific"
        if claim_type == "valuation":
            refs = self._compact_string_refs(typed_conflict_refs + price_counter_refs + competing_support_refs)
            return refs, "valuation_conflicts_and_opposing_support" if refs else "not_claim_specific"
        if claim_type == "timing":
            refs = self._compact_string_refs(invalidation_related_refs + competing_support_refs)
            return refs, "timing_invalidation_and_opposing_support" if refs else "not_claim_specific"
        if claim_type == "action_translation":
            refs = self._compact_string_refs(invalidation_related_refs + competing_support_refs + price_counter_refs)
            return refs, "action_invalidation_related_refs" if refs else "not_claim_specific"
        refs = self._compact_string_refs(price_counter_refs + typed_conflict_refs)
        return refs, "typed_conflicts_or_price_counterevidence" if refs else "not_claim_specific"

    def _claim_specific_falsifiers(
        self,
        *,
        claim_type: str,
        provided_falsifiers: List[str],
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        final_adjudication: FinalAdjudication,
        risk_report: Optional[RiskBoundaryReport],
    ) -> tuple[List[str], str]:
        provided = self._compact_strings(provided_falsifiers)
        if claim_type in {"market_state", "price_reflection"}:
            hypothesis_falsifiers = [
                item
                for hypothesis in list(synthesis_packet.competing_hypotheses or [])
                for item in list(getattr(hypothesis, "falsification_conditions", []) or [])
            ]
            result = self._compact_strings(provided + hypothesis_falsifiers)
            return result, "claim_invalidation_plus_hypothesis_falsifiers" if result else "not_claim_specific"
        if claim_type == "risk_boundary":
            risk_items: List[str] = []
            if risk_report is not None:
                risk_items.extend(str(item) for item in list(getattr(risk_report, "must_preserve_risks", []) or []))
                risk_items.extend(str(item.get("condition") or item.get("risk") or item) for item in list(getattr(risk_report, "failure_conditions", []) or []) if isinstance(item, dict))
                risk_items.extend(str(item) for item in list(getattr(risk_report, "false_safety_risks", []) or []))
            result = self._compact_strings(risk_items + provided)
            return result, "risk_sentinel_failure_conditions" if result else "not_claim_specific"
        if claim_type == "action_translation":
            action_conditions = [
                condition
                for action in list(getattr(final_adjudication, "portfolio_actions", []) or []) + list(getattr(thesis, "portfolio_actions", []) or [])
                for condition in list(getattr(action, "conditions", []) or [])
            ]
            result = self._compact_strings(provided + action_conditions)
            return result, "action_conditions_and_invalidation" if result else "not_claim_specific"
        if claim_type in {"valuation", "timing"}:
            hypothesis_falsifiers = [
                item
                for hypothesis in list(synthesis_packet.competing_hypotheses or [])
                for item in list(getattr(hypothesis, "falsification_conditions", []) or [])
            ]
            result = self._compact_strings(provided + hypothesis_falsifiers)
            return result, f"{claim_type}_claim_invalidation_plus_hypothesis_falsifiers" if result else "not_claim_specific"
        result = self._compact_strings(provided)
        return result, "provided_claim_falsifiers" if result else "not_claim_specific"

    def _load_user_decision_profile(self) -> UserDecisionProfile:
        path = Path(__file__).resolve().parents[2] / "config" / "user_decision_profile.json"
        if path.exists():
            try:
                return UserDecisionProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning("Failed to load user decision profile from %s: %s", path, exc)
        return UserDecisionProfile(
            buy_disciplines=[
                UserDecisionCondition(
                    condition_id="buy_value_discount_confirmed",
                    side="buy",
                    label="价值买入纪律",
                    discipline="只有当估值安全垫、风险边界和必要的时机证据同时可追问时，才把黄金坑视为候选。",
                    required_claim_types=["valuation", "risk_boundary", "timing"],
                )
            ],
            sell_disciplines=[
                UserDecisionCondition(
                    condition_id="sell_trend_or_risk_breaks",
                    side="sell",
                    label="趋势卖出纪律",
                    discipline="若趋势证据转弱或风险边界被触发，优先保护长期复利基地，不用估值叙事硬扛。",
                    required_claim_types=["timing", "risk_boundary"],
                )
            ],
        )

    def _build_golden_pit_checklist(
        self,
        *,
        final_claim_ledger: ClaimLedger,
        decision_profile: UserDecisionProfile,
        final_adjudication: FinalAdjudication,
        effective_date: str,
        state_variables: Optional[Dict[str, Any]] = None,
    ) -> GoldenPitChecklist:
        selected = [
            entry
            for entry in list(final_claim_ledger.entries or [])
            if entry.claim_type in {"valuation", "timing", "risk_boundary"}
        ]
        entries: List[GoldenPitChecklistItem] = []
        for entry in selected:
            status = self._checklist_status_from_claim(entry)
            item = GoldenPitChecklistItem(
                condition_id=f"claim:{entry.claim_id}",
                condition=entry.claim_text,
                discipline_side="claim",
                source_claim_ids=[entry.claim_id],
                evidence_refs=list(entry.evidence_refs),
                current_status=status,
                falsification_conditions=list(entry.falsification_conditions),
                status_method="claim_authority_status",
                status_evidence={"authority_status": entry.authority_status, "verified": entry.verified},
            )
            entries.append(item.model_copy(update={"changed_since_last_run": self._deferred_cross_run_change(item)}))

        profile_conditions = list(decision_profile.buy_disciplines or []) + list(decision_profile.sell_disciplines or [])
        for condition in profile_conditions:
            matched = [entry for entry in selected if entry.claim_type in set(condition.required_claim_types)]
            evidence_refs = self._compact_string_refs([ref for entry in matched for ref in entry.evidence_refs], limit=24)
            falsifiers = self._compact_strings([item for entry in matched for item in entry.falsification_conditions], limit=12)
            status, status_method, status_evidence = self._profile_condition_status(condition, matched, state_variables or {})
            item = GoldenPitChecklistItem(
                condition_id=condition.condition_id,
                condition=f"{condition.label}：{condition.discipline}",
                discipline_side=condition.side,
                source_claim_ids=[entry.claim_id for entry in matched],
                evidence_refs=evidence_refs,
                current_status=status,  # type: ignore[arg-type]
                falsification_conditions=falsifiers,
                status_method=status_method,
                status_evidence=status_evidence,
            )
            entries.append(item.model_copy(update={"changed_since_last_run": self._deferred_cross_run_change(item)}))

        changed_summary = [
            "跨 run 变化对比暂缓启用：需等待 claim schema、数据源覆盖和 Run Review 通过历史稳定后再前置。"
        ]
        return GoldenPitChecklist(
            effective_date=effective_date,
            previous_checklist_ref="",
            current_state=getattr(final_adjudication, "state_diagnosis", "") or getattr(final_adjudication.reader_final, "one_liner", "") or final_adjudication.final_stance,
            changed_since_last_run_summary=changed_summary,
            entries=entries,
        )

    def _checklist_status_from_claim(self, entry: ClaimLedgerEntry) -> str:
        if entry.verified:
            return "met"
        if entry.authority_status == "blocked":
            return "insufficient_evidence"
        return "not_met"

    def _profile_condition_status(
        self,
        condition: UserDecisionCondition,
        matched: List[ClaimLedgerEntry],
        state_variables: Dict[str, Any],
    ) -> tuple[str, str, Dict[str, Any]]:
        metric_predicates = getattr(condition, "metric_predicates", {}) or {}
        if isinstance(metric_predicates, dict) and metric_predicates:
            status, details = self._evaluate_metric_predicates(metric_predicates, state_variables)
            return status, "metric_predicates", details

        fallback_evidence = {
            "reason": "condition_has_no_metric_predicates",
            "matched_claim_ids": [entry.claim_id for entry in matched],
        }
        if not matched:
            return "insufficient_evidence", "claim_text_fallback", fallback_evidence
        if any(entry.authority_status == "blocked" for entry in matched):
            fallback_evidence["blocked_claim_ids"] = [entry.claim_id for entry in matched if entry.authority_status == "blocked"]
            return "insufficient_evidence", "claim_text_fallback", fallback_evidence
        required_types = set(condition.required_claim_types)
        present_types = {entry.claim_type for entry in matched}
        if required_types and not required_types.issubset(present_types):
            fallback_evidence["missing_claim_types"] = sorted(required_types - present_types)
            return "insufficient_evidence", "claim_text_fallback", fallback_evidence
        if any(not entry.verified for entry in matched):
            fallback_evidence["unverified_claim_ids"] = [entry.claim_id for entry in matched if not entry.verified]
            return "not_met", "claim_text_fallback", fallback_evidence

        by_type: Dict[str, List[ClaimLedgerEntry]] = {}
        for entry in matched:
            by_type.setdefault(str(entry.claim_type), []).append(entry)

        if condition.side == "buy":
            checks = []
            if "valuation" in required_types:
                checks.append(any(self._claim_text_supports_buy("valuation", entry.claim_text) for entry in by_type.get("valuation", [])))
            if "timing" in required_types:
                checks.append(any(self._claim_text_supports_buy("timing", entry.claim_text) for entry in by_type.get("timing", [])))
            if "risk_boundary" in required_types:
                checks.append(any(self._claim_text_supports_buy("risk_boundary", entry.claim_text) for entry in by_type.get("risk_boundary", [])))
            fallback_evidence["claim_text_checks"] = checks
            return ("met" if checks and all(checks) else "not_met"), "claim_text_fallback", fallback_evidence
        if condition.side == "sell":
            checks = [self._claim_text_supports_sell(entry.claim_type, entry.claim_text) for entry in matched]
            fallback_evidence["claim_text_checks"] = checks
            return ("met" if any(checks) else "not_met"), "claim_text_fallback", fallback_evidence
        return ("met" if all(entry.verified for entry in matched) else "not_met"), "claim_text_fallback", fallback_evidence

    def _evaluate_metric_predicates(self, expression: Dict[str, Any], state_variables: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        logic = str(expression.get("logic") or "all_of")
        raw_predicates = expression.get("predicates") if isinstance(expression.get("predicates"), list) else []
        results = []
        missing = False
        for predicate in raw_predicates:
            if not isinstance(predicate, dict):
                results.append({"status": "invalid_predicate", "predicate": predicate})
                missing = True
                continue
            variable = str(predicate.get("var") or "")
            op = str(predicate.get("op") or "")
            expected = predicate.get("value")
            actual = state_variables.get(variable)
            if actual is None:
                results.append(
                    {
                        "var": variable,
                        "op": op,
                        "expected": expected,
                        "actual": None,
                        "met": None,
                        "status": "missing_variable",
                        "threshold_status": predicate.get("threshold_status", ""),
                    }
                )
                missing = True
                continue
            met = self._evaluate_single_metric_predicate(actual, op, expected)
            results.append(
                {
                    "var": variable,
                    "op": op,
                    "expected": expected,
                    "actual": actual,
                    "met": met,
                    "status": "evaluated",
                    "threshold_status": predicate.get("threshold_status", ""),
                }
            )
        evaluated = [item for item in results if item.get("met") is not None]
        if not raw_predicates or missing or len(evaluated) != len(raw_predicates):
            status = "insufficient_evidence"
        elif logic == "any_of":
            status = "met" if any(bool(item.get("met")) for item in evaluated) else "not_met"
        else:
            status = "met" if all(bool(item.get("met")) for item in evaluated) else "not_met"
        return status, {
            "logic": logic,
            "predicate_count": len(raw_predicates),
            "results": results,
            "state_variable_source": "state_ledger.extract_state_variables",
        }

    def _evaluate_single_metric_predicate(self, actual: Any, op: str, expected: Any) -> bool:
        if op in {"==", "!="}:
            result = str(actual) == str(expected)
            return result if op == "==" else not result
        try:
            actual_number = float(actual)
            expected_number = float(expected)
        except (TypeError, ValueError):
            return False
        if op == "<":
            return actual_number < expected_number
        if op == "<=":
            return actual_number <= expected_number
        if op == ">":
            return actual_number > expected_number
        if op == ">=":
            return actual_number >= expected_number
        return False

    def _claim_text_supports_buy(self, claim_type: str, text: str) -> bool:
        raw = str(text or "")
        negative = re.search(r"不足|不便宜|偏贵|昂贵|未到|不支持|压力|恶化|破坏|脆弱|风险仍|风险边界仍需保留", raw)
        if negative:
            return False
        if claim_type == "valuation":
            return bool(re.search(r"便宜|低估|折价|安全垫|回落|改善|赔率改善|风险溢价改善", raw))
        if claim_type == "timing":
            return bool(re.search(r"趋势未破坏|趋势确认|企稳|转强|时机改善", raw))
        if claim_type == "risk_boundary":
            return bool(re.search(r"风险可承受|风险缓和|未触发|边界安全|压力缓和", raw))
        return False

    def _claim_text_supports_sell(self, claim_type: str, text: str) -> bool:
        raw = str(text or "")
        if claim_type == "timing":
            return bool(re.search(r"趋势破坏|跌破|转弱|失守|下行确认", raw))
        if claim_type == "risk_boundary":
            return bool(re.search(r"风险触发|边界突破|风险恶化|压力升级|信用恶化|流动性冲击", raw))
        return False

    def _deferred_cross_run_change(self, item: GoldenPitChecklistItem) -> Dict[str, Any]:
        return {
            "changed": False,
            "status": "deferred_until_run_quality_stable",
            "previous_status": "",
            "current_status": item.current_status,
            "summary": "跨 run 变化对比暂缓；当前只展示本轮状态与条件证据差距。",
        }

    def _compact_string_refs(self, values: List[Any], limit: int = 20) -> List[str]:
        return self._compact_strings([value for value in values if isinstance(value, str) and value], limit=limit)

    def _compact_strings(self, values: List[Any], limit: int = 20) -> List[str]:
        items: List[str] = []
        for value in values:
            text = " ".join(str(value or "").split())
            if text and text not in items:
                items.append(text)
            if len(items) >= limit:
                break
        return items

    def _load_local_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _run_bridge(
        self,
        packet: AnalysisPacket,
        context_brief: ContextBrief,
        layer_cards: List[LayerCard],
    ) -> BridgeMemo:
        bridge_payload = {
            "context_brief": _model_dump(context_brief),
            "candidate_cross_layer_links": [_model_dump(link) for link in packet.candidate_cross_layer_links],
            "layer_cards": [_model_dump(card) for card in layer_cards],
        }
        if packet.event_refs:
            bridge_payload["event_refs"] = packet.event_refs
        checkpoint = self._load_stage_checkpoint(
            self.bridge_dir / "bridge_0.json",
            BridgeMemo,
            stage_key="bridge",
            stage_name="bridge",
            expected_payload=bridge_payload,
        )
        if checkpoint is not None:
            return checkpoint
        bridge = self._run_stage(
            stage_key="bridge",
            stage_name="bridge",
            model_cls=BridgeMemo,
            payload=bridge_payload,
            validator=self._validate_bridge_memo_v2,
        )
        self._save_json(self.bridge_dir / "bridge_0.json", bridge)
        self._record_stage_artifact(
            self.bridge_dir / "bridge_0.json",
            stage_key="bridge",
            stage_name="bridge",
            payload=bridge_payload,
        )
        return bridge

    def _run_thesis(self, synthesis_packet: SynthesisPacket) -> ThesisDraft:
        thesis_payload = {
            "synthesis_packet": _model_dump(synthesis_packet),
        }
        checkpoint = self._load_stage_checkpoint(
            "thesis_draft.json",
            ThesisDraft,
            stage_key="thesis",
            stage_name="thesis",
            expected_payload=thesis_payload,
        )
        if checkpoint is not None:
            return checkpoint
        thesis = self._run_stage(
            stage_key="thesis",
            stage_name="thesis",
            model_cls=ThesisDraft,
            payload=thesis_payload,
        )
        self._save_json("thesis_draft.json", thesis)
        self._record_stage_artifact(
            self.output_dir / "thesis_draft.json",
            stage_key="thesis",
            stage_name="thesis",
            payload=thesis_payload,
        )
        return thesis

    def _build_synthesis_packet(
        self,
        packet: AnalysisPacket,
        context_brief: ContextBrief,
        layer_cards: List[LayerCard],
        bridge_memos: List[BridgeMemo],
    ) -> SynthesisPacket:
        layer_summaries: List[LayerSynthesisItem] = []
        bridge_summaries: List[BridgeSynthesisItem] = []
        high_conflicts = []
        high_typed_conflicts = []
        principal_contradictions = []
        evidence_index: Dict[str, Dict[str, Any]] = {}

        for card in layer_cards:
            layer_label = getattr(card.layer, "value", str(card.layer))
            indicator_refs: List[str] = []
            key_evidence: List[str] = []
            for analysis in card.indicator_analyses:
                ref = f"{layer_label}.{analysis.function_id}"
                indicator_refs.append(ref)
                raw_payload = self._raw_payload_for_evidence_ref(packet, ref)
                field_authority = self._field_authority_from_payload(raw_payload)
                field_usages = self._field_authority_usages(field_authority)
                raw_quality = raw_payload.get("data_quality") if isinstance(raw_payload.get("data_quality"), dict) else {}
                evidence_item = {
                    "layer": layer_label,
                    "function_id": analysis.function_id,
                    "metric": analysis.metric,
                    "current_reading": analysis.current_reading,
                    "normalized_state": analysis.normalized_state,
                    "narrative": analysis.narrative,
                    "reasoning_process": analysis.reasoning_process,
                    "first_principles_chain": analysis.first_principles_chain,
                    "cross_layer_implications": analysis.cross_layer_implications,
                    "risk_flags": analysis.risk_flags,
                    "permission_type": _enum_value(analysis.permission_type),
                    "canonical_question": analysis.canonical_question,
                    "misread_guards": analysis.misread_guards,
                    "cross_validation_targets": analysis.cross_validation_targets,
                    "falsifiers": analysis.falsifiers,
                    "core_vs_tactical_boundary": analysis.core_vs_tactical_boundary,
                    "confidence": _enum_value(analysis.confidence),
                    "source_tier": raw_payload.get("source_tier") or raw_quality.get("source_tier"),
                    "mixed_field_authority": len(field_usages) > 1,
                }
                evidence_index[ref] = evidence_item
                value = raw_payload.get("value") if isinstance(raw_payload.get("value"), dict) else {}
                for field, field_rule in field_authority.items():
                    if not isinstance(field_rule, dict):
                        continue
                    evidence_index[f"{ref}#{field}"] = {
                        "layer": layer_label,
                        "function_id": analysis.function_id,
                        "metric": analysis.metric,
                        "parent_evidence_ref": ref,
                        "field_name": field,
                        "field_value": value.get(field),
                        "field_authority": field_rule,
                        "permission_type": _enum_value(analysis.permission_type),
                        "canonical_question": analysis.canonical_question,
                        "misread_guards": analysis.misread_guards,
                        "source_tier": evidence_item.get("source_tier"),
                    }
                if analysis.current_reading:
                    key_evidence.append(f"{analysis.metric}: {analysis.current_reading}")
                else:
                    key_evidence.append(f"{analysis.metric}: {analysis.narrative[:160]}")

            if not key_evidence:
                for fact in card.core_facts[:4]:
                    ref = f"{layer_label}.{fact.metric}"
                    indicator_refs.append(ref)
                    evidence_index[ref] = {
                        "layer": layer_label,
                        "metric": fact.metric,
                        "value": fact.value,
                        "historical_percentile": fact.historical_percentile,
                        "trend": _enum_value(fact.trend),
                        "magnitude": _enum_value(fact.magnitude),
                    }
                    key_evidence.append(f"{fact.metric}: {fact.value}")

            layer_summaries.append(
                LayerSynthesisItem(
                    layer=card.layer,
                    local_conclusion=card.local_conclusion,
                    layer_synthesis=card.layer_synthesis or card.notes,
                    indicator_refs=indicator_refs[:12],
                    key_evidence=key_evidence[:8],
                    risk_flags=card.risk_flags,
                    internal_conflict_analysis=card.internal_conflict_analysis,
                    cross_layer_hooks=[
                        f"{_enum_value(hook.target_layer)}: {hook.question}"
                        for hook in card.cross_layer_hooks
                    ],
                    confidence=card.confidence,
                )
            )

        for memo in bridge_memos:
            is_feedback_bridge = str(getattr(memo, "bridge_type", "")) == "feedback_bridge_v2"
            # H3: Include both high and medium severity conflicts so Thesis is aware
            # of all meaningful cross-layer tensions, not just the highest severity ones.
            if not is_feedback_bridge:
                high_conflicts.extend(
                    conflict for conflict in memo.conflicts if _severity_is_high_or_medium(conflict)
                )
                high_typed_conflicts.extend(
                    conflict for conflict in memo.typed_conflicts if _severity_is_high_or_medium(conflict)
                )
            if not is_feedback_bridge and getattr(memo, "principal_contradiction", None) is not None:
                principal_contradictions.append(memo.principal_contradiction)
            bridge_summaries.append(
                BridgeSynthesisItem(
                    bridge_type=memo.bridge_type,
                    layers_connected=memo.layers_connected,
                    key_claims=[] if is_feedback_bridge else [claim.claim for claim in memo.cross_layer_claims],
                    key_conflicts=[
                        f"{conflict.conflict_type}: {conflict.description}"
                        for conflict in memo.conflicts
                    ] if not is_feedback_bridge else [],
                    typed_conflicts=[] if is_feedback_bridge else [_model_dump(conflict) for conflict in memo.typed_conflicts],
                    resonance_chains=[] if is_feedback_bridge else [_model_dump(chain) for chain in memo.resonance_chains],
                    transmission_paths=[] if is_feedback_bridge else [_model_dump(path) for path in memo.transmission_paths],
                    principal_contradiction=(
                        None
                        if is_feedback_bridge
                        else _model_dump(memo.principal_contradiction) if getattr(memo, "principal_contradiction", None) is not None else None
                    ),
                    secondary_contradictions=[] if is_feedback_bridge else [_model_dump(item) for item in memo.secondary_contradictions],
                    price_reflection_map=[] if is_feedback_bridge else [_model_dump(item) for item in memo.price_reflection_map],
                    contradiction_transformation_signals=[] if is_feedback_bridge else [_model_dump(item) for item in memo.contradiction_transformation_signals],
                    unresolved_questions=memo.unresolved_questions,
                    event_refs=list(dict.fromkeys(getattr(memo, "event_refs", []) or [])),
                    implication_for_ndx=memo.implication_for_ndx,
                    key_uncertainties=memo.key_uncertainties,
                )
            )

        objective_firewall = self._build_objective_firewall_summary(packet, layer_cards, bridge_memos)

        return SynthesisPacket(
            packet_meta=packet.meta,
            context_summary=(
                f"{context_brief.data_summary} "
                f"{context_brief.task_description}"
            ).strip(),
            layer_summaries=layer_summaries,
            bridge_summaries=bridge_summaries,
            high_severity_conflicts=high_conflicts,
            high_severity_typed_conflicts=high_typed_conflicts,
            principal_contradictions=principal_contradictions,
            objective_firewall_summary=objective_firewall,
            evidence_index=evidence_index,
            event_index=packet.event_refs,
            synthesis_guidance=[
                "必须消费 objective_firewall_summary：若 object_clear、authority_clear、cross_layer_verified 任一为 false，主结论必须降置信度并保留警示。",
                "Thesis 只能整合 synthesis_packet，不得重新分析原始指标。",
                "必须保留 high_severity_conflicts，不能为了叙事流畅而抹平张力。",
                "必须显式消费 principal_contradictions / Bridge principal_contradiction：先判断当前主要矛盾，再判断价格是否已经反映风险，最后才给动作。",
                "必须显式消费 competing_hypotheses / hypothesis_competition_summary：正式综合前至少比较主线解释和反方解释；若证据不足，必须降级或保留争议。",
                "必须尊重 evidence_registry_summary：数据、事件、调查、假说和最终 claim 使用同一种 evidence id；弱权限证据不能越权支撑强结论。",
                "mixed_field_authority=true 的函数级父 evidence ref 只能表示混合容器；具体字段结论必须使用 evidence_index 中的 #FieldName 子 ref。",
                "Thesis / Final 的重要自然语言结论会进入 final_claim_ledger；缺证据、缺反证、缺失效条件或证据权限不足时必须降级。",
                "所有 key_support_chains 的 evidence_refs 必须来自 evidence_index 或 bridge_summaries。",
                "event_refs 与 evidence_refs 分离：事件只能写成解释/触发/观察背景，不能用来证明估值、广度、利率或趋势结论。",
            ],
        )

    def _build_objective_firewall_summary(
        self,
        packet: AnalysisPacket,
        layer_cards: List[LayerCard],
        bridge_memos: List[BridgeMemo],
    ) -> ObjectiveFirewallSummary:
        warnings: List[str] = []
        unresolved_tensions: List[str] = []
        falsifiers: List[str] = []

        # F3: Check investment object clarity — verify raw_data has expected L1-L5 layers
        # with actual content. If the packet is empty or has no layer data, object is unclear.
        # Note: raw_data keys are already uppercase "L1"-"L5" (set by packet_builder LAYER_NAMES).
        expected_layers = {"L1", "L2", "L3", "L4", "L5"}
        raw_data_layers = {
            layer
            for layer in expected_layers
            if _layer_has_usable_raw_data(packet.raw_data.get(layer))
        }
        # object_clear requires at least 3 of 5 layers to have data (partial data is acceptable
        # but complete absence suggests the investment object is not properly defined)
        object_clear = len(raw_data_layers) >= 3
        if not object_clear:
            present = sorted(raw_data_layers) if raw_data_layers else ["none"]
            warnings.append(
                f"Investment object unclear: only {len(raw_data_layers)}/5 layers "
                f"have data ({', '.join(present)}). Expected L1-L5 coverage."
            )

        known_items = []
        for card in layer_cards:
            for item in card.indicator_analyses:
                try:
                    get_indicator_canon(item.function_id)
                except KeyError:
                    continue
                known_items.append(item)

        authority_clear = all(
            item.permission_type
            and item.canonical_question
            and item.misread_guards
            and item.cross_validation_targets
            and item.falsifiers
            for item in known_items
        )
        if known_items and not authority_clear:
            warnings.append("Some known indicators are missing permission or falsifier fields.")
        authority_overreach = self._find_indicator_authority_overreach(known_items)
        if authority_overreach:
            authority_clear = False
            for issue in authority_overreach:
                warnings.append(
                    "Indicator authority overreach: "
                    f"{issue['function_id']} ({issue['permission_type']}) -> {issue['rule_id']}"
                )
        for item in known_items:
            falsifiers.extend(item.falsifiers)

        structural_bridge_memos = [
            memo
            for memo in bridge_memos
            if str(getattr(memo, "bridge_type", "")) != "feedback_bridge_v2"
        ]
        typed_conflicts = [
            conflict
            for memo in structural_bridge_memos
            for conflict in memo.typed_conflicts
        ]
        legacy_conflicts = [
            conflict
            for memo in structural_bridge_memos
            for conflict in memo.conflicts
        ]
        # F4: cross_layer_verified means "bridge has verified cross-layer logic",
        # i.e. bridge memos exist and contain meaningful cross-layer analysis.
        # Previously this was inverted: conflicts present → True, no conflicts → False.
        cross_layer_verified = bool(bridge_memos)
        if not cross_layer_verified:
            warnings.append("No bridge memos produced; cross-layer logic cannot be verified.")

        for conflict in typed_conflicts:
            if str(_enum_value(conflict.severity)) == "high" or conflict.status == "unresolved":
                unresolved_tensions.append(f"{conflict.conflict_id}: {conflict.description}")
            falsifiers.extend(conflict.falsifiers)
        for conflict in legacy_conflicts:
            if str(_enum_value(conflict.severity)) == "high":
                unresolved_tensions.append(f"{conflict.conflict_type}: {conflict.description}")

        data_date = packet.meta.get("data_date") or packet.meta.get("timestamp_utc")
        timing_clear = bool(data_date) or not packet.meta
        if not timing_clear:
            warnings.append("Packet has no data_date or timestamp_utc; timing alignment cannot be verified.")

        return ObjectiveFirewallSummary(
            object_clear=object_clear,
            authority_clear=authority_clear if known_items else False,
            timing_clear=timing_clear,
            cross_layer_verified=cross_layer_verified,
            strongest_falsifier=falsifiers[0] if falsifiers else "",
            unresolved_tensions=unresolved_tensions,
            warnings=warnings,
        )

    def _find_indicator_authority_overreach(self, items: List[Any]) -> List[Dict[str, str]]:
        issues: List[Dict[str, str]] = []
        for item in items:
            permission_type = str(_enum_value(getattr(item, "permission_type", "")) or "").strip().lower()
            rules = _AUTHORITY_OVERREACH_RULES.get(permission_type, [])
            if not rules:
                continue
            text = self._indicator_authority_text(item)
            for pattern, rule_id in rules:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    issues.append(
                        {
                            "function_id": str(getattr(item, "function_id", "unknown")),
                            "permission_type": permission_type,
                            "rule_id": rule_id,
                        }
                    )
                    break
        return issues

    def _indicator_authority_text(self, item: Any) -> str:
        fields = [
            getattr(item, "current_reading", ""),
            getattr(item, "normalized_state", ""),
            getattr(item, "narrative", ""),
            getattr(item, "reasoning_process", ""),
        ]
        for list_field in ("first_principles_chain", "cross_layer_implications", "risk_flags"):
            value = getattr(item, list_field, [])
            if isinstance(value, list):
                fields.extend(str(part) for part in value)
            else:
                fields.append(str(value))
        return "\n".join(str(field) for field in fields if field)

    def _build_governance_input_packet(
        self,
        synthesis_packet: SynthesisPacket,
        thesis: ThesisDraft,
        critique: Optional[Critique] = None,
        risk_report: Optional[RiskBoundaryReport] = None,
        schema_report: Optional[SchemaGuardReport] = None,
        analysis_revised: Optional[AnalysisRevised] = None,
        layer_cards: Optional[List[LayerCard]] = None,
    ) -> GovernanceInputPacket:
        """Build a compressed governance input packet for Critic / Risk / Reviser / Final.

        Reduces token bloat by only including what governance stages need:
        - Thesis essentials (not full artifact)
        - High severity typed conflicts (must not be lost)
        - Objective firewall summary
        - Schema guard essentials
        - Must-preserve risks
        - Thesis support chains and their evidence refs
        - Key evidence refs (subset related to high-severity conflicts and thesis support chains)
        - Known data gaps (especially L3 breadth)
        """
        # ── Thesis summary ──
        thesis_confidence = getattr(thesis.overall_confidence, "value", str(thesis.overall_confidence)) if thesis.overall_confidence else "medium"
        retained_conflict_types = [
            getattr(conflict, "conflict_type", str(conflict))
            for conflict in thesis.retained_conflicts
        ]

        # ── Key evidence refs: high-severity conflicts plus Thesis support chains ──
        all_evidence_refs: set = set()
        all_event_refs: set = set()
        for conflict in synthesis_packet.high_severity_typed_conflicts:
            refs = getattr(conflict, "evidence_refs", []) if hasattr(conflict, "evidence_refs") else conflict.get("evidence_refs", [])
            all_evidence_refs.update(refs)
            event_refs = getattr(conflict, "event_refs", []) if hasattr(conflict, "event_refs") else conflict.get("event_refs", [])
            all_event_refs.update(event_refs)

        # Also collect event_refs from bridge summaries (Bridge may have marked
        # events at the memo level that don't appear in typed conflicts).
        for bridge_summary in synthesis_packet.bridge_summaries:
            all_event_refs.update(bridge_summary.get("event_refs", []) if isinstance(bridge_summary, dict) else getattr(bridge_summary, "event_refs", []) or [])

        thesis_key_support_chains = [_model_dump(chain) for chain in thesis.key_support_chains]
        for chain in thesis.key_support_chains:
            all_evidence_refs.update(chain.evidence_refs)
            all_event_refs.update(getattr(chain, "event_refs", []) or [])
        for action in getattr(thesis, "portfolio_actions", []) or []:
            all_evidence_refs.update(getattr(action, "evidence_refs", []) or [])
        for view in getattr(thesis, "time_horizon_views", []) or []:
            all_evidence_refs.update(getattr(view, "evidence_refs", []) or [])
        reader_conclusion = _model_dump(getattr(thesis, "reader_conclusion", {}) or {})
        if isinstance(reader_conclusion, dict):
            all_evidence_refs.update(reader_conclusion.get("evidence_refs", []) or [])
        thesis_principal_contradiction = _model_dump(getattr(thesis, "principal_contradiction", None))
        if not isinstance(thesis_principal_contradiction, dict):
            thesis_principal_contradiction = None
        thesis_secondary_contradictions = [
            _model_dump(item) for item in getattr(thesis, "secondary_contradictions", []) or []
        ]
        thesis_price_reflection_map = [
            _model_dump(item) for item in getattr(thesis, "price_reflection_map", []) or []
        ]
        for item in [thesis_principal_contradiction] + thesis_secondary_contradictions + thesis_price_reflection_map:
            if isinstance(item, dict):
                all_evidence_refs.update(item.get("evidence_refs", []) or [])

        key_evidence_refs: Dict[str, Dict[str, Any]] = {}
        for ref in sorted(all_evidence_refs):
            if ref in synthesis_packet.evidence_index:
                key_evidence_refs[ref] = synthesis_packet.evidence_index[ref]

        key_event_refs: Dict[str, Dict[str, Any]] = {}
        for ref in sorted(all_event_refs):
            if ref in synthesis_packet.event_index:
                key_event_refs[ref] = synthesis_packet.event_index[ref]

        # ── Known data gaps: collect from layer cards, schema, and bridge ──
        known_data_gaps: List[str] = []
        if layer_cards:
            for card in layer_cards:
                if card.quality_self_check:
                    missing = getattr(card.quality_self_check, "missing_or_weak_indicators", [])
                    known_data_gaps.extend(missing)

        if schema_report is not None:
            if schema_report.structural_issues:
                known_data_gaps.extend(f"[schema] {issue}" for issue in schema_report.structural_issues)
            if schema_report.missing_fields:
                known_data_gaps.extend(f"[schema] {field}" for field in schema_report.missing_fields)

        # L3 广度缺失（特别重要）
        if layer_cards:
            for card in layer_cards:
                layer_label = getattr(card.layer, "value", str(card.layer))
                if layer_label == "L3":
                    l3_warnings = [f"[L3] {flag}" for flag in card.risk_flags if "breadth" in flag.lower() or "结构" in flag]
                    if l3_warnings:
                        known_data_gaps.extend(l3_warnings)

        # Bridge 未解决问题
        unresolved_questions: List[str] = []
        for bridge_summary in synthesis_packet.bridge_summaries:
            unresolved = bridge_summary.unresolved_questions if bridge_summary.unresolved_questions else []
            unresolved_questions.extend(unresolved)

        # ── Schema guard summary ──
        schema_passed = schema_report.passed if schema_report is not None else True
        schema_structural = schema_report.structural_issues if schema_report is not None else []
        schema_consistency = schema_report.consistency_issues if schema_report is not None else []
        schema_missing = schema_report.missing_fields if schema_report is not None else []

        # ── Must-preserve risks (from Risk Sentinel, if available) ──
        must_preserve_risks = list(risk_report.must_preserve_risks) if risk_report is not None else []
        opportunity_costs = [_model_dump(item) for item in getattr(risk_report, "opportunity_costs", [])] if risk_report is not None else []
        confirmation_costs = [_model_dump(item) for item in getattr(risk_report, "confirmation_costs", [])] if risk_report is not None else []
        false_safety_risks = list(getattr(risk_report, "false_safety_risks", []) or []) if risk_report is not None else []

        # ── Critique summary (for reviser / final) ──
        critique_overall = critique.overall_assessment if critique is not None else None
        critique_cross_layer = critique.cross_layer_issues if critique is not None else []

        # ── Revision summary (for final) ──
        revision_summary = analysis_revised.revision_summary if analysis_revised is not None else None

        # ── Objective firewall ──
        obj_firewall = _model_dump(synthesis_packet.objective_firewall_summary) if synthesis_packet.objective_firewall_summary is not None else None

        # ── Typed conflicts as dicts ──
        high_severity_typed = [_model_dump(conflict) for conflict in synthesis_packet.high_severity_typed_conflicts]
        principal_contradictions = [
            _model_dump(item) for item in getattr(synthesis_packet, "principal_contradictions", []) or []
        ]

        return GovernanceInputPacket(
            thesis_main=thesis.main_thesis or "",
            thesis_environment=thesis.environment_assessment or "",
            thesis_valuation=thesis.valuation_assessment or "",
            thesis_timing=thesis.timing_assessment or "",
            thesis_confidence=thesis_confidence,
            thesis_dependencies=list(thesis.dependencies) if thesis.dependencies else [],
            thesis_key_support_chains=thesis_key_support_chains,
            retained_conflict_types=retained_conflict_types,
            thesis_state_diagnosis=getattr(thesis, "state_diagnosis", "") or "",
            thesis_priced_narrative=getattr(thesis, "priced_narrative", "") or "",
            thesis_payoff_assessment=getattr(thesis, "payoff_assessment", "") or "",
            thesis_time_horizon_views=[_model_dump(item) for item in getattr(thesis, "time_horizon_views", []) or []],
            thesis_portfolio_actions=[_model_dump(item) for item in getattr(thesis, "portfolio_actions", []) or []],
            thesis_confirmation_cost=getattr(thesis, "confirmation_cost", "") or "",
            thesis_invalidation_conditions=list(getattr(thesis, "invalidation_conditions", []) or []),
            thesis_reader_conclusion=reader_conclusion if isinstance(reader_conclusion, dict) else {},
            thesis_principal_contradiction=thesis_principal_contradiction,
            thesis_secondary_contradictions=thesis_secondary_contradictions,
            thesis_price_reflection_map=thesis_price_reflection_map,
            high_severity_typed_conflicts=high_severity_typed,
            principal_contradictions=principal_contradictions,
            objective_firewall_summary=obj_firewall,
            schema_passed=schema_passed,
            schema_structural_issues=list(schema_structural),
            schema_consistency_issues=list(schema_consistency),
            schema_missing_fields=list(schema_missing),
            must_preserve_risks=must_preserve_risks,
            opportunity_costs=opportunity_costs,
            confirmation_costs=confirmation_costs,
            false_safety_risks=false_safety_risks,
            key_evidence_refs=key_evidence_refs,
            key_event_refs=key_event_refs,
            evidence_registry_summary=dict(getattr(synthesis_packet, "evidence_registry_summary", {}) or {}),
            known_data_gaps=list(dict.fromkeys(known_data_gaps)),  # 去重
            unresolved_questions=list(dict.fromkeys(unresolved_questions)),  # 去重
            synthesis_guidance=list(synthesis_packet.synthesis_guidance) if synthesis_packet.synthesis_guidance else [],
            critique_overall=critique_overall,
            critique_cross_layer_issues=list(critique_cross_layer),
            revision_summary=revision_summary,
        )

    def _build_context_brief(self, packet: AnalysisPacket) -> ContextBrief:
        layer_highlights: Dict[str, List[str]] = {}
        special_attention: List[str] = []
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            facts = packet.facts_by_layer.get(layer)
            summaries = []
            if facts:
                summaries = [item.get("summary", "") for item in facts.core_signals[:3] if item.get("summary")]
                if not summaries and facts.summary:
                    summaries = [facts.summary]
            layer_highlights[layer] = summaries
        for link in packet.candidate_cross_layer_links[:4]:
            special_attention.append(link.description)
        return ContextBrief(
            data_summary=(
                f"数据日期 {packet.meta.get('data_date')}，"
                f"共 {packet.meta.get('indicator_successful', 0)}/{packet.meta.get('indicator_total', 0)} 个指标成功。"
            ),
            layer_highlights=layer_highlights,
            apparent_cross_layer_signals=[link.description for link in packet.candidate_cross_layer_links[:4]],
            task_description="基于五层框架完成 Layer -> Bridge -> Thesis -> Governance -> Final 的完整分析链路。",
            special_attention=special_attention or ["检查高严重度冲突是否被完整保留。"],
        )

    def _build_layer_context_brief(self, packet: AnalysisPacket, context_brief: ContextBrief, layer: str) -> ContextBrief:
        """Build a layer-local brief for L1-L5 analysts.

        Layer analysts should not see other layers' current readings or Python-generated
        cross-layer state claims before they form their own local interpretation.
        Bridge and later stages still receive the global context brief.
        """
        layer = layer.upper()
        layer_highlights = {
            layer: list(context_brief.layer_highlights.get(layer, []))
        }
        return ContextBrief(
            data_summary=self._build_layer_data_summary(packet, layer),
            layer_highlights=layer_highlights,
            apparent_cross_layer_signals=[],
            task_description=(
                f"只完成 {layer} 的本层分析：先基于本层数据生成指标级推理，"
                "再输出本层综合、层内冲突和需要 Bridge 后续验证的问题。"
            ),
            special_attention=[
                "可以使用静态五层职责边界来路由验证问题，但不要读取或推断其他层当前状态。",
                "不得因为最终报告需要完整结论而提前吸收其他层叙事。",
            ],
        )

    def _build_layer_data_summary(self, packet: AnalysisPacket, layer: str) -> str:
        """Return a data summary scoped to the current layer only."""
        layer_data = packet.raw_data.get(layer, {})
        if not isinstance(layer_data, dict):
            total = 0
            successful = 0
        else:
            total = sum(1 for item in layer_data.values() if isinstance(item, dict))
            successful = sum(
                1
                for item in layer_data.values()
                if isinstance(item, dict) and not item.get("error")
            )
        return (
            f"数据日期 {packet.meta.get('data_date')}，"
            f"{layer} 本层 {successful}/{total} 个指标成功。"
        )

    def _build_layer_manual_overrides(self, packet: AnalysisPacket, layer: str) -> Dict[str, Any]:
        """Filter manual overrides so layer analysts only see metrics in their own layer."""
        overrides = packet.manual_overrides if isinstance(packet.manual_overrides, dict) else {}
        if not overrides.get("active"):
            return {
                "active": False,
                "date": overrides.get("date", ""),
                "metrics": {},
            }
        layer_data = packet.raw_data.get(layer, {})
        layer_function_ids = set(layer_data.keys()) if isinstance(layer_data, dict) else set()
        metrics = overrides.get("metrics", {}) if isinstance(overrides.get("metrics"), dict) else {}
        return {
            "active": bool(overrides.get("active")),
            "date": overrides.get("date", ""),
            "metrics": {
                function_id: metric
                for function_id, metric in metrics.items()
                if function_id in layer_function_ids
            },
        }

    def _run_stage(
        self,
        *,
        stage_key: str,
        stage_name: str,
        model_cls: Type[Any],
        payload: Dict[str, Any],
        validator: Optional[Callable[[Any], List[str]]] = None,
    ) -> Any:
        prompt = self._compose_prompt(stage_key, model_cls, payload)
        preferred_models = self._preferred_models_for_stage(stage_key)
        last_error = ""
        stage_record: Dict[str, Any] = {
            "stage_key": stage_key,
            "stage_name": stage_name,
            "attempts": 0,
            "errors": [],
            "prompt_chars": len(prompt),
            "status": "running",
            "model_routing": {
                "schema_version": self.stage_model_routing.get("schema_version", ""),
                "preferred_models": preferred_models,
                "fallback_chain": [model for model in self.available_models if model not in preferred_models],
            },
            "prompt_audit": {
                "stage_dir": self._prompt_audit_relpath(stage_name),
                "attempts": [],
            },
        }
        self.stage_diagnostics["stages"][stage_name] = stage_record
        self._save_stage_diagnostics()
        for attempt in range(1, self.max_node_retries + 1):
            stage_record["attempts"] = attempt
            active_prompt = prompt
            if last_error:
                active_prompt = (
                    f"{prompt}\n\n上一次返回未通过结构校验，错误如下：\n{last_error}\n"
                    "请仅输出修正后的 JSON 对象，不要附加任何解释。"
                )
            attempt_record = self._capture_prompt_attempt(
                stage_key=stage_key,
                stage_name=stage_name,
                attempt=attempt,
                active_prompt=active_prompt,
                payload=payload,
                retry_feedback=last_error,
            )
            stage_record["prompt_chars"] = len(active_prompt)
            stage_record["prompt_audit"]["attempts"].append(attempt_record)
            stage_record["prompt_audit"]["latest_prompt_file"] = attempt_record["prompt_file"]
            self._save_stage_diagnostics()
            try:
                raw = self.llm_engine.call_with_fallback(
                    active_prompt,
                    stage_name=stage_name,
                    preferred_models=preferred_models or None,
                )
            except TypeError:
                raw = self.llm_engine.call_with_fallback(active_prompt, stage_name=stage_name)
            self._save_prompt_audit_text(stage_name, f"attempt_{attempt}.response.raw.txt", str(raw or ""))
            attempt_record["raw_response_file"] = self._prompt_audit_relpath(
                stage_name,
                f"attempt_{attempt}.response.raw.txt",
            )
            self._write_prompt_stage_meta(stage_name, stage_record)
            if not raw:
                last_error = f"{stage_name} received empty response"
                stage_record["errors"].append({"attempt": attempt, "kind": "empty_response", "message": last_error})
                self._write_prompt_stage_meta(stage_name, stage_record)
                self._save_stage_diagnostics()
                continue
            parsed = self.llm_engine.extract_json(raw, stage_name)
            if not isinstance(parsed, dict):
                raw_text = str(raw or "")
                tail = raw_text[-400:]
                last_error = (
                    f"{stage_name} did not return a parseable JSON object."
                    f" 原始响应字符数: {len(raw_text)}."
                    f" 响应末尾片段（用于定位 JSON 语法错误，请检查最后未闭合的数组、对象或字符串）：\n{tail}"
                )
                stage_record["errors"].append(
                    {
                        "attempt": attempt,
                        "kind": "parse_error",
                        "message": last_error[:1500],
                        "raw_excerpt": raw_text[:500],
                    }
                )
                self._write_prompt_stage_meta(stage_name, stage_record)
                self._save_stage_diagnostics()
                continue
            parsed = self._normalize_payload(stage_key, parsed)
            self._save_prompt_audit_json(stage_name, f"attempt_{attempt}.parsed.normalized.json", parsed)
            attempt_record["parsed_response_file"] = self._prompt_audit_relpath(
                stage_name,
                f"attempt_{attempt}.parsed.normalized.json",
            )
            # 强制覆盖 generated_at：防止 LLM 日期幻觉
            # LLM 经常在 JSON 输出中编造 generated_at 值，覆盖掉 pydantic 的 default_factory
            # 这里用代码实际运行时间强制覆盖，确保审计可追溯性
            if hasattr(model_cls, "model_fields") and "generated_at" in model_cls.model_fields:
                parsed["generated_at"] = datetime.now(timezone.utc)
            try:
                validated = model_cls.model_validate(parsed)
            except Exception as exc:
                last_error = str(exc)
                stage_record["errors"].append(
                    {
                        "attempt": attempt,
                        "kind": "schema_validation_error",
                        "message": last_error[:1000],
                    }
                )
                self._write_prompt_stage_meta(stage_name, stage_record)
                self._save_stage_diagnostics()
                logger.warning("%s validation failed on attempt %s: %s", stage_name, attempt, exc)
                continue
            if validator:
                validation_errors = validator(validated)
                if validation_errors:
                    last_error = "\n".join(validation_errors)
                    stage_record["errors"].append(
                        {
                            "attempt": attempt,
                            "kind": "contract_validation_error",
                            "message": last_error[:1000],
                        }
                    )
                    self._write_prompt_stage_meta(stage_name, stage_record)
                    self._save_stage_diagnostics()
                    logger.warning(
                        "%s contract validation failed on attempt %s: %s",
                        stage_name,
                        attempt,
                        last_error,
                    )
                    continue
            stage_record["status"] = "ok"
            stage_record["model"] = getattr(self.llm_engine, "successful_model", None)
            self._save_prompt_audit_json(stage_name, "output.validated.json", _model_dump(validated))
            stage_record["prompt_audit"]["validated_output_file"] = self._prompt_audit_relpath(
                stage_name,
                "output.validated.json",
            )
            self._write_prompt_stage_meta(stage_name, stage_record)
            self._save_stage_diagnostics()
            return validated
        stage_record["status"] = "failed"
        self._write_prompt_stage_meta(stage_name, stage_record)
        self._save_stage_diagnostics()
        raise RuntimeError(f"{stage_name} failed after {self.max_node_retries} attempts: {last_error}")

    def _prompt_audit_stage_dir(self, stage_name: str) -> Path:
        return self.prompt_audit_dir / self._prompt_audit_stage_label(stage_name)

    def _prompt_audit_stage_label(self, stage_name: str) -> str:
        normalized = str(stage_name or "stage").strip()
        layer_match = re.fullmatch(r"l([1-5])", normalized.lower())
        if layer_match:
            return f"L{layer_match.group(1)}"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized).strip("_") or "stage"

    def _prompt_audit_relpath(self, stage_name: str, filename: Optional[str] = None) -> str:
        path = Path("prompt_audit") / self._prompt_audit_stage_label(stage_name)
        if filename:
            path = path / filename
        return path.as_posix()

    def _actual_prompt_text(self, user_prompt: str) -> str:
        system_constraints = ""
        if hasattr(self.llm_engine, "_load_system_constraints"):
            try:
                system_constraints = self.llm_engine._load_system_constraints()
            except Exception:
                system_constraints = ""
        return (
            "## System Message\n"
            f"{system_constraints}\n\n"
            "## User Message\n"
            f"{user_prompt}"
        )

    def _capture_prompt_attempt(
        self,
        *,
        stage_key: str,
        stage_name: str,
        attempt: int,
        active_prompt: str,
        payload: Dict[str, Any],
        retry_feedback: str,
    ) -> Dict[str, Any]:
        actual_prompt = self._actual_prompt_text(active_prompt)
        prompt_hash = hashlib.sha256(actual_prompt.encode("utf-8")).hexdigest()
        prompt_filename = f"attempt_{attempt}.prompt.txt"
        payload_filename = f"attempt_{attempt}.payload.json"
        self._save_prompt_audit_text(stage_name, prompt_filename, actual_prompt)
        self._save_prompt_audit_json(
            stage_name,
            payload_filename,
            {
                "stage_key": stage_key,
                "stage_name": stage_name,
                "attempt": attempt,
                "payload": self._sanitize_prompt_payload(stage_key, payload),
                "retry_feedback": retry_feedback or "",
            },
        )
        return {
            "attempt": attempt,
            "prompt_file": self._prompt_audit_relpath(stage_name, prompt_filename),
            "payload_file": self._prompt_audit_relpath(stage_name, payload_filename),
            "prompt_sha256": prompt_hash,
            "prompt_chars": len(actual_prompt),
            "retry_feedback": bool(retry_feedback),
        }

    def _save_prompt_audit_text(self, stage_name: str, filename: str, text: str) -> None:
        stage_dir = self._prompt_audit_stage_dir(stage_name)
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / filename).write_text(text, encoding="utf-8")

    def _save_prompt_audit_json(self, stage_name: str, filename: str, payload: Any) -> None:
        stage_dir = self._prompt_audit_stage_dir(stage_name)
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _write_prompt_stage_meta(self, stage_name: str, stage_record: Dict[str, Any]) -> None:
        prompt_audit = stage_record.get("prompt_audit", {}) if isinstance(stage_record, dict) else {}
        attempts = prompt_audit.get("attempts", []) if isinstance(prompt_audit, dict) else []
        latest_attempt = attempts[-1] if attempts else {}
        meta = {
            "stage": self._prompt_audit_stage_label(stage_name),
            "stage_name": stage_name,
            "stage_key": stage_record.get("stage_key"),
            "attempt": latest_attempt.get("attempt"),
            "attempts": stage_record.get("attempts", 0),
            "model": stage_record.get("model") or getattr(self.llm_engine, "successful_model", None),
            "status": stage_record.get("status"),
            "prompt_chars": latest_attempt.get("prompt_chars") or stage_record.get("prompt_chars"),
            "prompt_tokens_estimate": None,
            "prompt_sha256": latest_attempt.get("prompt_sha256"),
            "prompt_file": latest_attempt.get("prompt_file"),
            "effective_date": self._infer_effective_date_from_prompt_audit(stage_name),
            "mode": self._infer_run_mode_from_prompt_audit(stage_name),
            "input_artifacts": self._infer_input_artifacts(stage_name),
            "output_artifact": self._infer_output_artifact(stage_name),
            "validation_errors": [
                item for item in stage_record.get("errors", [])
                if isinstance(item, dict) and item.get("kind") in {"schema_validation_error", "contract_validation_error"}
            ],
            "errors": stage_record.get("errors", []),
            "attempt_files": attempts,
            "data_boundary": self._infer_data_boundary_from_prompt_audit(stage_name),
        }
        self._save_prompt_audit_json(stage_name, "meta.json", meta)

    def _infer_effective_date_from_prompt_audit(self, stage_name: str) -> Optional[str]:
        analysis_path = self.output_dir / "analysis_packet.json"
        packet = {}
        if analysis_path.exists():
            try:
                packet = json.loads(analysis_path.read_text(encoding="utf-8"))
            except Exception:
                packet = {}
        meta = packet.get("meta", {}) if isinstance(packet, dict) else {}
        return meta.get("backtest_date") or meta.get("data_date") or meta.get("timestamp_utc")

    def _infer_run_mode_from_prompt_audit(self, stage_name: str) -> str:
        analysis_path = self.output_dir / "analysis_packet.json"
        if analysis_path.exists():
            try:
                packet = json.loads(analysis_path.read_text(encoding="utf-8"))
            except Exception:
                packet = {}
            meta = packet.get("meta", {}) if isinstance(packet, dict) else {}
            if meta.get("backtest_date"):
                return "backtest"
            if meta.get("snapshot_id") or meta.get("snapshot_mode"):
                return "snapshot"
        return "latest"

    def _infer_data_boundary_from_prompt_audit(self, stage_name: str) -> Dict[str, Any]:
        effective_date = self._infer_effective_date_from_prompt_audit(stage_name)
        return {
            "effective_date": effective_date,
            "max_input_date": None,
            "backtest_cutoff_respected": None,
        }

    def _infer_input_artifacts(self, stage_name: str) -> List[str]:
        layer_match = re.fullmatch(r"l([1-5])", str(stage_name).lower())
        if layer_match:
            layer = f"L{layer_match.group(1)}"
            return [
                f"layer_context_briefs/{layer}.json",
                f"analysis_packet.raw_data.{layer}",
            ]
        return {
            "bridge": ["context_brief.json", "layer_cards/L1-L5.json"],
            "thesis": ["synthesis_packet.json"],
            "critic": ["governance_input(thesis + synthesis + layer cards)"],
            "critic_retry": ["governance_input(thesis + synthesis + schema feedback + layer cards)"],
            "risk": ["governance_input(thesis + synthesis + layer cards)"],
            "risk_retry": ["governance_input(thesis + synthesis + schema feedback + layer cards)"],
            "reviser": ["governance_input(thesis + critique + risk + schema + layer cards)"],
            "final_adjudicator": ["governance_input(revised thesis + critique + risk + schema + layer cards)"],
        }.get(stage_name, [])

    def _infer_output_artifact(self, stage_name: str) -> str:
        layer_match = re.fullmatch(r"l([1-5])", str(stage_name).lower())
        if layer_match:
            return f"layer_cards/L{layer_match.group(1)}.json"
        return {
            "bridge": "bridge_memos/bridge_0.json",
            "thesis": "thesis_draft.json",
            "critic": "critique.json",
            "critic_retry": "critique.json",
            "risk": "risk_boundary_report.json",
            "risk_retry": "risk_boundary_report.json",
            "reviser": "analysis_revised.json",
            "final_adjudicator": "final_adjudication.json",
        }.get(stage_name, "")

    def _save_stage_diagnostics(self) -> None:
        path = self.output_dir / "llm_stage_diagnostics.json"
        path.write_text(json.dumps(self.stage_diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
        self._record_stage_artifact(path)

    def _validate_stage_evidence_refs(self, candidate: Any, allowed_refs: set[str], stage_key: str) -> List[str]:
        payload = _model_dump(candidate)
        refs_by_path: List[tuple[str, str]] = []

        def walk(value: Any, path: str = "") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    next_path = f"{path}.{key}" if path else str(key)
                    if key in {"evidence_refs", "counterevidence_refs", "counter_evidence_refs"}:
                        for ref in self._coerce_string_list(child):
                            refs_by_path.append((next_path, ref))
                    else:
                        walk(child, next_path)
                return
            if isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")

        walk(payload)
        invalid = [
            (path, ref)
            for path, ref in refs_by_path
            if ref and ref not in allowed_refs
        ]
        if not invalid:
            return []
        examples = "; ".join(f"{path} -> {ref}" for path, ref in invalid[:8])
        return [
            (
                f"evidence_ref_source_validation failed for {stage_key}: "
                f"refs must come from synthesis_packet.evidence_index. Invalid refs: {examples}"
            )
        ]

    def _validate_layer_card_v2(
        self,
        card: LayerCard,
        layer_label: str,
        expected_indicators: Dict[str, str],
    ) -> List[str]:
        """Reject thin legacy-style LayerCards before Bridge consumes them."""
        errors: List[str] = []
        expected_function_ids = set(expected_indicators)

        if not str(card.layer_synthesis or "").strip():
            errors.append(f"{layer_label}.layer_synthesis is required for LayerCard v2.")
        if not str(card.internal_conflict_analysis or "").strip():
            errors.append(f"{layer_label}.internal_conflict_analysis is required for LayerCard v2.")
        if card.quality_self_check is None:
            errors.append(f"{layer_label}.quality_self_check is required for LayerCard v2.")

        analyses_by_function: Dict[str, Any] = {}
        for analysis in card.indicator_analyses:
            if analysis.function_id:
                analyses_by_function[analysis.function_id] = analysis
            if not analysis.narrative.strip():
                errors.append(f"{layer_label}.{analysis.function_id}.narrative is required.")
            if not analysis.reasoning_process.strip():
                errors.append(f"{layer_label}.{analysis.function_id}.reasoning_process is required.")
            if not analysis.evidence_refs:
                errors.append(f"{layer_label}.{analysis.function_id}.evidence_refs must not be empty.")

        missing_analyses = sorted(expected_function_ids - set(analyses_by_function))
        for function_id in missing_analyses:
            errors.append(f"{layer_label}.indicator_analyses[{function_id}] is required.")

        for function_id, metric_name in expected_indicators.items():
            analysis = analyses_by_function.get(function_id)
            if analysis and metric_name and analysis.metric != metric_name:
                errors.append(
                    f"{layer_label}.{function_id}.metric must equal input metric_name '{metric_name}'."
                )

        if card.quality_self_check is not None:
            covered = set(card.quality_self_check.covered_function_ids)
            covered_from_analyses = expected_function_ids & set(analyses_by_function)
            effective_covered = covered | covered_from_analyses
            missing_from_self_check = sorted(expected_function_ids - effective_covered)
            if covered_from_analyses - covered:
                card.quality_self_check.covered_function_ids = sorted(effective_covered)
            if expected_function_ids and not missing_analyses and not card.quality_self_check.coverage_complete:
                card.quality_self_check.coverage_complete = True
            if missing_from_self_check:
                errors.append(
                    f"{layer_label}.quality_self_check.covered_function_ids missing: "
                    + ", ".join(missing_from_self_check)
                )

        return errors

    def _validate_bridge_memo_v2(self, bridge: BridgeMemo) -> List[str]:
        """Reject soft Bridge resonance chains that lack evidence, mechanism, or falsifiers."""
        errors: List[str] = []
        notes = set(getattr(bridge, "normalization_notes", []) or [])
        typed_conflicts_derived = "typed_conflicts_derived_from_legacy_conflicts" in notes
        for conflict in bridge.typed_conflicts:
            conflict_id = str(conflict.conflict_id or "typed_conflict")
            if not conflict.evidence_refs:
                errors.append(f"bridge.typed_conflicts[{conflict_id}].evidence_refs must not be empty.")
            if not typed_conflicts_derived and not str(conflict.mechanism or "").strip():
                errors.append(f"bridge.typed_conflicts[{conflict_id}].mechanism is required.")
            if not str(conflict.implication or "").strip():
                errors.append(f"bridge.typed_conflicts[{conflict_id}].implication is required.")
        for chain in bridge.resonance_chains:
            chain_id = str(chain.chain_id or "resonance_chain")
            if not chain.evidence_refs:
                errors.append(f"bridge.resonance_chains[{chain_id}].evidence_refs must not be empty.")
            if not chain.confirming_indicators:
                errors.append(f"bridge.resonance_chains[{chain_id}].confirming_indicators must not be empty.")
            if not str(chain.mechanism or "").strip():
                errors.append(f"bridge.resonance_chains[{chain_id}].mechanism is required.")
            if not str(chain.implication or "").strip():
                errors.append(f"bridge.resonance_chains[{chain_id}].implication is required.")
            if not chain.falsifiers:
                errors.append(f"bridge.resonance_chains[{chain_id}].falsifiers must not be empty.")
        seen_path_ids: set[str] = set()
        for path in bridge.transmission_paths:
            path_id = str(path.path_id or "transmission_path")
            if path_id in seen_path_ids:
                errors.append(f"bridge.transmission_paths[{path_id}] duplicate path_id.")
            seen_path_ids.add(path_id)
            if not path.evidence_refs:
                errors.append(f"bridge.transmission_paths[{path_id}].evidence_refs must not be empty.")
            if not str(path.implication or "").strip():
                errors.append(f"bridge.transmission_paths[{path_id}].implication is required.")
        return errors

    def _run_schema_guard(
        self,
        packet: AnalysisPacket,
        layer_cards: List[LayerCard],
        bridge_memos: List[BridgeMemo],
        thesis: ThesisDraft,
        critique: Critique,
        risk_report: RiskBoundaryReport,
    ) -> SchemaGuardReport:
        structural_issues: List[str] = []
        consistency_issues: List[str] = []
        missing_fields: List[str] = []
        suggested_fixes: List[str] = []
        soft_canon_warnings: List[str] = []
        l3_structural_warnings: List[str] = []
        semantic_warnings: List[str] = []
        valid_evidence_refs: set[str] = set()
        for layer, metrics in packet.raw_data.items():
            if not isinstance(metrics, dict):
                continue
            for function_id, raw_payload in metrics.items():
                parent_ref = f"{layer}.{function_id}"
                valid_evidence_refs.add(parent_ref)
                if isinstance(raw_payload, dict):
                    for field in self._field_authority_from_payload(raw_payload):
                        valid_evidence_refs.add(f"{parent_ref}#{field}")

        def _bad_refs(refs: List[str]) -> List[str]:
            bad: List[str] = []
            for ref in refs or []:
                ref_text = str(ref)
                if not _EVIDENCE_REF_PATTERN.fullmatch(ref_text) or ref_text not in valid_evidence_refs:
                    bad.append(ref_text)
            return bad

        def _composite_submetric_issue(conflict: Any) -> Optional[str]:
            severity = str(getattr(getattr(conflict, "severity", ""), "value", getattr(conflict, "severity", ""))).lower()
            refs = [str(ref) for ref in getattr(conflict, "evidence_refs", []) or []]
            if severity != "high" or "L2.get_cnn_fear_greed_index" not in refs:
                return None
            text = " ".join(
                str(getattr(conflict, field, "") or "")
                for field in ("conflict_id", "conflict_type", "description", "mechanism", "implication")
            ).lower()
            submetric_tokens = (
                "market momentum",
                "put/call",
                "safe haven",
                "junk bond",
                "stock price strength",
                "stock price breadth",
                "market volatility",
                "子项",
                "分项",
            )
            aggregate_tokens = (
                "total score",
                "overall",
                "aggregate",
                "headline",
                "总分",
                "综合",
                "整体",
                "总指标",
            )
            if any(token in text for token in submetric_tokens) and not any(token in text for token in aggregate_tokens):
                return (
                    "high severity conflict uses CNN Fear & Greed sub-metric without aggregate-score semantics; "
                    "treat sub-metric divergence as internal tension unless independently supported."
                )
            return None

        if len(layer_cards) != 5:
            structural_issues.append(f"Expected 5 layer cards, got {len(layer_cards)}.")

        for card in layer_cards:
            if not card.core_facts:
                structural_issues.append(f"{card.layer} has no core_facts.")
            if not card.local_conclusion:
                missing_fields.append(f"{card.layer}.local_conclusion")
            layer_label = getattr(card.layer, "value", str(card.layer))
            expected_function_ids = self._analysis_required_function_ids(packet, layer_label)
            if layer_label == "L3":
                present_priority = sorted(set(expected_function_ids) & L3_STRUCTURAL_PRIORITY_FUNCTIONS)
                missing_priority = sorted(L3_STRUCTURAL_PRIORITY_FUNCTIONS - set(expected_function_ids))
                if present_priority and missing_priority:
                    l3_structural_warnings.append(
                        "L3 structural priority coverage is partial; missing "
                        + ", ".join(missing_priority)
                    )
            covered_function_ids = {
                item.function_id
                for item in card.indicator_analyses
                if item.function_id
            }
            for function_id in expected_function_ids:
                if function_id not in covered_function_ids:
                    missing_fields.append(f"{layer_label}.indicator_analyses[{function_id}]")
            for item in card.indicator_analyses:
                if not item.narrative.strip():
                    missing_fields.append(f"{layer_label}.{item.function_id}.narrative")
                if not item.reasoning_process.strip():
                    missing_fields.append(f"{layer_label}.{item.function_id}.reasoning_process")
                try:
                    get_indicator_canon(item.function_id)
                except KeyError:
                    continue
                missing_soft_fields = [
                    field_name
                    for field_name in (
                        "permission_type",
                        "canonical_question",
                        "misread_guards",
                        "cross_validation_targets",
                        "falsifiers",
                        "core_vs_tactical_boundary",
                    )
                    if not getattr(item, field_name)
                ]
                if missing_soft_fields:
                    soft_canon_warnings.append(
                        f"{layer_label}.{item.function_id} missing soft canon fields: "
                        + ", ".join(missing_soft_fields)
                    )
            authority_overreach = self._find_indicator_authority_overreach(card.indicator_analyses)
            for issue in authority_overreach:
                semantic_warnings.append(
                    "Indicator authority overreach: "
                    f"{layer_label}.{issue['function_id']} ({issue['permission_type']}) -> {issue['rule_id']}"
                )

        if not bridge_memos:
            structural_issues.append("No bridge memo generated.")
        else:
            structural_bridge_memos = [
                memo
                for memo in bridge_memos
                if str(getattr(memo, "bridge_type", "")) != "feedback_bridge_v2"
            ]
            total_conflicts = sum(len(memo.conflicts) for memo in structural_bridge_memos)
            if total_conflicts == 0:
                consistency_issues.append("Bridge stage produced zero conflicts; this usually means tension was flattened.")
            for memo_index, memo in enumerate(structural_bridge_memos):
                seen_path_ids: set[str] = set()
                for claim_index, claim in enumerate(memo.cross_layer_claims):
                    bad_refs = _bad_refs(claim.supporting_facts)
                    if bad_refs:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].cross_layer_claims[{claim_index}].supporting_facts invalid: "
                            + ", ".join(bad_refs[:5])
                        )
                for conflict in memo.typed_conflicts:
                    conflict_id = str(conflict.conflict_id or "typed_conflict")
                    if not conflict.evidence_refs:
                        consistency_issues.append(f"BridgeMemo[{memo_index}].typed_conflicts[{conflict_id}].evidence_refs must not be empty.")
                    bad_refs = _bad_refs(conflict.evidence_refs)
                    if bad_refs:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].typed_conflicts[{conflict_id}].evidence_refs invalid: "
                            + ", ".join(bad_refs[:5])
                        )
                    composite_issue = _composite_submetric_issue(conflict)
                    if composite_issue:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].typed_conflicts[{conflict_id}] composite sub-metric over-promotion: "
                            + composite_issue
                        )
                for chain in memo.resonance_chains:
                    chain_id = str(chain.chain_id or "resonance_chain")
                    bad_refs = _bad_refs(chain.evidence_refs)
                    if bad_refs:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].resonance_chains[{chain_id}].evidence_refs invalid: "
                            + ", ".join(bad_refs[:5])
                        )
                for path in memo.transmission_paths:
                    path_id = str(path.path_id or "transmission_path")
                    if path_id in seen_path_ids:
                        consistency_issues.append(f"BridgeMemo[{memo_index}].transmission_paths[{path_id}] duplicate path_id.")
                    seen_path_ids.add(path_id)
                    if not path.evidence_refs:
                        consistency_issues.append(f"BridgeMemo[{memo_index}].transmission_paths[{path_id}].evidence_refs must not be empty.")
                    if not str(path.implication or "").strip():
                        consistency_issues.append(f"BridgeMemo[{memo_index}].transmission_paths[{path_id}].implication is required.")
                    bad_refs = _bad_refs(path.evidence_refs)
                    if bad_refs:
                        consistency_issues.append(
                            f"BridgeMemo[{memo_index}].transmission_paths[{path_id}].evidence_refs invalid: "
                            + ", ".join(bad_refs[:5])
                        )

        if not thesis.main_thesis:
            missing_fields.append("thesis.main_thesis")
        if not critique.revision_direction:
            missing_fields.append("critique.revision_direction")
        if not risk_report.must_preserve_risks:
            consistency_issues.append("RiskBoundaryReport.must_preserve_risks is empty.")

        high_conflict_types = {
            conflict.conflict_type
            for memo in bridge_memos
            for conflict in memo.conflicts
            if str(getattr(conflict.severity, "value", conflict.severity)) == "high"
        }
        retained_conflict_types = {
            conflict.conflict_type
            for conflict in thesis.retained_conflicts
        }
        dropped_high_conflicts = sorted(high_conflict_types - retained_conflict_types)
        if dropped_high_conflicts:
            consistency_issues.append(
                "High severity conflicts missing from ThesisDraft.retained_conflicts: "
                + ", ".join(dropped_high_conflicts)
            )

        if structural_issues:
            suggested_fixes.append("Re-run the failed stage and verify JSON output matches the contract.")
        if consistency_issues:
            suggested_fixes.append("Force the reviser/final stages to preserve bridge conflicts and risk boundaries explicitly.")
        if missing_fields:
            suggested_fixes.append("Patch prompts so required fields are always returned, even when the model is uncertain.")
        if soft_canon_warnings:
            suggested_fixes.append(
                "Add soft canon fields to indicator_analyses where available: "
                + "; ".join(soft_canon_warnings[:8])
            )
        if l3_structural_warnings:
            suggested_fixes.append(
                "L3 structural priority should be treated cautiously, not as a hard blocker: "
                + "; ".join(l3_structural_warnings)
            )
        if semantic_warnings:
            suggested_fixes.append(
                "Review indicator authority before publishing: "
                + "; ".join(semantic_warnings[:8])
            )

        passed = not structural_issues and not consistency_issues and not missing_fields
        quality_status = "review_required" if semantic_warnings or not passed else "passed"
        return SchemaGuardReport(
            passed=passed,
            structural_issues=structural_issues,
            consistency_issues=consistency_issues,
            missing_fields=missing_fields,
            suggested_fixes=suggested_fixes,
            quality_status=quality_status,
        )

    def _analysis_required_function_ids(self, packet: AnalysisPacket, layer: str) -> List[str]:
        layer_data = packet.raw_data.get(layer, {})
        if not isinstance(layer_data, dict):
            return []
        required = []
        for function_id, payload in layer_data.items():
            if not isinstance(payload, dict):
                continue
            if self._indicator_unavailable_for_analysis(payload):
                continue
            required.append(str(payload.get("function_id") or function_id))
        return required

    def _analysis_required_indicator_map(self, packet: AnalysisPacket, layer: str) -> Dict[str, str]:
        layer_data = packet.raw_data.get(layer, {})
        if not isinstance(layer_data, dict):
            return {}
        required: Dict[str, str] = {}
        for function_id, payload in layer_data.items():
            if not isinstance(payload, dict):
                continue
            if self._indicator_unavailable_for_analysis(payload):
                continue
            resolved_function_id = str(payload.get("function_id") or function_id)
            required[resolved_function_id] = str(
                payload.get("metric_name")
                or payload.get("name")
                or resolved_function_id
            )
        return required

    def _indicator_unavailable_for_analysis(self, payload: Dict[str, Any]) -> bool:
        return indicator_payload_unavailable_reason(payload) is not None

    def _compose_prompt(self, stage_key: str, model_cls: Type[Any], payload: Dict[str, Any]) -> str:
        prompt_payload = self._sanitize_prompt_payload(stage_key, payload)
        prompt_body = self._load_prompt(stage_key)
        if stage_key.startswith("l") and stage_key.endswith("_analyst"):
            prompt_body = self._compose_layer_prompt(stage_key, prompt_body, prompt_payload)
        elif stage_key == "bridge":
            prompt_body = self._compose_bridge_prompt(prompt_body, prompt_payload)
        elif stage_key == "thesis":
            prompt_body = self._compose_thesis_prompt(prompt_body, prompt_payload)
        fields = list(getattr(model_cls, "model_fields", {}).keys())
        schema_hint = ", ".join(fields) if fields else model_cls.__name__
        return (
            f"{prompt_body}\n\n"
            "## Runtime Input\n"
            f"{json.dumps(prompt_payload, ensure_ascii=False, indent=2, default=str)}\n\n"
            "## Response Rules\n"
            "- 只返回一个 JSON 对象。\n"
            "- 不要使用 markdown code fence。\n"
            f"- JSON 顶层字段必须匹配: {schema_hint}。\n"
            "- 不要编造新的外部数据源，只能使用输入中的信息。\n"
        )

    def _sanitize_prompt_payload(self, stage_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return the exact payload that may be serialized into an LLM prompt."""
        if stage_key == "bridge":
            return self._strip_empty_event_prompt_fields(payload)
        if stage_key == "thesis":
            return self._strip_empty_event_prompt_fields(self._slim_object_run_gate_for_prompt(payload))
        if not (stage_key.startswith("l") and stage_key.endswith("_analyst")):
            return payload
        sanitized = dict(payload)
        layer = str(sanitized.get("layer") or stage_key[:2].upper())
        raw_data = self._filter_layer_raw_data_for_prompt(
            layer,
            sanitized.get("layer_raw_data", {}),
        )
        if layer.upper() == "L4":
            raw_data = self._summarize_l4_raw_data_for_prompt(raw_data)
        sanitized["layer_raw_data"] = raw_data
        sanitized.pop("runtime_boundary_policy_id", None)
        return sanitized

    def _slim_object_run_gate_for_prompt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Keep full object gate in artifacts, but send only the decision-relevant kernel to prompts."""
        sanitized = dict(payload)
        synthesis = sanitized.get("synthesis_packet")
        if not isinstance(synthesis, dict):
            return sanitized
        packet_meta = synthesis.get("packet_meta")
        if not isinstance(packet_meta, dict):
            return sanitized
        object_gate = packet_meta.get("object_run_gate")
        if not isinstance(object_gate, dict):
            return sanitized
        slim_meta = dict(packet_meta)
        slim_meta["object_run_gate"] = {
            "schema_version": object_gate.get("schema_version", "object_run_gate_v1"),
            "primary_object": object_gate.get("primary_object", "NDX"),
            "tradable_proxy": object_gate.get("tradable_proxy", "QQQ"),
            "equal_weight_references": object_gate.get("equal_weight_references", []),
            "date_boundary": object_gate.get("date_boundary"),
            "prompt_note": "Full object boundary is stored in analysis_packet meta; use this only as object scope.",
        }
        slim_synthesis = dict(synthesis)
        slim_synthesis["packet_meta"] = slim_meta
        sanitized["synthesis_packet"] = slim_synthesis
        return sanitized

    def _strip_empty_event_prompt_fields(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            stripped: Dict[str, Any] = {}
            for key, value in payload.items():
                cleaned = self._strip_empty_event_prompt_fields(value)
                if key in {"event_refs", "event_index", "key_event_refs"} and cleaned in ({}, [], None):
                    continue
                stripped[key] = cleaned
            return stripped
        if isinstance(payload, list):
            return [self._strip_empty_event_prompt_fields(item) for item in payload]
        return payload

    def _compose_layer_prompt(self, stage_key: str, prompt_body: str, payload: Dict[str, Any]) -> str:
        layer = str(payload.get("layer") or stage_key[:2].upper())
        layer_raw_data = payload.get("layer_raw_data", {})
        layer_raw_data = self._filter_layer_raw_data_for_prompt(layer, layer_raw_data)
        expected_indicators = self._layer_indicator_manifest(layer_raw_data)
        canon_prompt = build_layer_canon_prompt(layer=layer, layer_raw_data=layer_raw_data)
        few_shot = build_layer_few_shot_prompt(layer=layer, layer_raw_data=layer_raw_data)
        v2_contract = (
            "## vNext v2 Context-Bounded Professional Layer Contract\n"
            "你在一个隔离的本层上下文中工作：角色是专业认知镜头，context boundary 是信息隔离边界。"
            "先用本层专家视角完成指标级研究，再把结果压缩为可审计、可展示、可被 Bridge 消费的结构化产物。\n\n"
            "### 静态五层本体（只用于路由，不代表当前状态）\n"
            "- L1: 宏观流动性、利率、实际利率、期限结构、货币供应、净流动性和增长预期代理。\n"
            "- L2: 风险偏好、信用利差、波动率、情绪、仓位和拥挤度。\n"
            "- L3: 指数内部结构、广度、集中度、等权/市值权重差异和领导力质量。\n"
            "- L4: 估值、盈利收益率、简式收益差距、Damodaran 美国 implied ERP 参考锚、安全边际和估值压缩风险。\n"
            "- L5: 价格趋势、动量、波动、成交量、支撑阻力和趋势失效触发。\n"
            "- Bridge: 读取各层结构化产物，验证跨层共振、冲突和传导机制。\n"
            "以上只是职责边界和接口协议，不是其他层的当前数据、状态或结论。"
            "你可以据此决定把验证问题路由给哪一层，但不得据此推断其他层现在是 bullish、bearish、expensive、healthy 或 uptrend。\n\n"
            "### 必须新增并认真填写的字段\n"
            "- indicator_analyses: 对每一个 analysis_required=true 的指标输出一条原生分析。\n"
            "- indicator_analyses[].function_id 必须等于输入 function_id。\n"
            "- indicator_analyses[].metric 必须优先等于输入 metric_name。\n"
            "- indicator_analyses[].evidence_refs 必须是字符串数组，例如 [\"L2.get_vix\"]，不得输出对象/dict。\n"
            "- 若一个 payload 的 MetricAuthority 含不同 usage，它是 mixed-field payload；引用其中任何字段时必须写成 L4.function_id#FieldName。父级 L4.function_id 只能表示混合容器，不能支撑强字段结论。\n"
            "- indicator_analyses[].narrative 是可进入最终报告的典范化解读。\n"
            "- indicator_analyses[].reasoning_process 必须展示从当前读数、分位/趋势到局部判断的因果推理。\n"
            "- indicator_analyses[].first_principles_chain 用列表写出机制链，例如 利率上升 -> 折现率上升 -> 成长股估值受压。\n"
            "- layer_synthesis 必须由 indicator_analyses 归纳，不能只重复 local_conclusion，并应适合该层独立 UI 展示。\n"
            "- internal_conflict_analysis 必须讨论本层内部指标之间的共振、背离、降噪和优先级，也应适合展开阅读。\n"
            "- quality_self_check 必须开放说明覆盖情况、弱推理点和置信度边界。\n\n"
            "### 隔离纪律\n"
            "- 允许知道其他层负责什么；禁止假设其他层当前看到了什么、判断了什么。\n"
            "- 跨层内容只能写成待 Bridge 验证的问题，不能写成已经成立的跨层结论。\n"
            "- 不得为了形成完整市场故事而提前综合其他层。\n"
            "- 不得给出最终买卖建议。\n\n"
            "### 数值单位纪律\n"
            "- 引用金额/规模数值时必须带上 payload 中的 unit 单位；payload 无单位标注时不得猜测单位，只能写明“单位未标注”。\n\n"
            "### 当前层指标清单\n"
            f"{json.dumps(expected_indicators, ensure_ascii=False, indent=2, default=str)}\n\n"
            "### 结构示例\n"
            "{\n"
            '  "indicator_analyses": [\n'
            "    {\n"
            '      "function_id": "get_10y_real_rate",\n'
            '      "metric": "10Y Real Rate",\n'
            '      "current_reading": "实际利率 1.95%，处于高位并上行",\n'
            '      "normalized_state": "restrictive",\n'
            '      "narrative": "作为成长股估值的地心引力，实际利率高位运行意味着远期现金流折现压力仍未解除。",\n'
            '      "reasoning_process": "先看水平，再看趋势和分位；若实际利率高且上行，DCF 折现率提高，NDX 高久期盈利的估值弹性下降。",\n'
            '      "first_principles_chain": ["实际利率上升", "无风险真实回报提高", "未来现金流现值下降", "成长股估值倍数承压"],\n'
            '      "evidence_refs": ["L1.get_10y_real_rate"],\n'
            '      "cross_layer_implications": ["需要 L4 验证估值是否已反映高实际利率"],\n'
            '      "risk_flags": ["valuation_compression"],\n'
            '      "confidence": "medium"\n'
            "    }\n"
            "  ],\n"
            '  "quality_self_check": {\n'
            '    "coverage_complete": true,\n'
            '    "covered_function_ids": ["get_10y_real_rate"],\n'
            '    "missing_or_weak_indicators": [],\n'
            '    "weak_reasoning_points": [],\n'
            '    "unresolved_internal_tensions": [],\n'
            '    "confidence_limitations": ["宏观变量到指数价格存在传导滞后"]\n'
            "  }\n"
            "}\n"
        )
        parts = [part for part in [canon_prompt, few_shot, v2_contract, prompt_body] if part]
        return "\n\n".join(parts)

    def _compose_bridge_prompt(self, prompt_body: str, payload: Optional[Dict[str, Any]] = None) -> str:
        has_event_input = payload is None or bool(payload.get("event_refs"))
        bridge_contract = (
            "## vNext v2 Bridge Contract\n"
            "Bridge 的职责不是重新解释单个指标，而是读取各 LayerCard 的 indicator_analyses、layer_synthesis、"
            "internal_conflict_analysis 和 cross_layer_hooks，识别跨层共振、冲突、传导机制与不确定性。\n\n"
            "必须优先使用 indicator_analyses[].reasoning_process 中已经完成的专业推理；"
            "如果要提出冲突，必须指出冲突来自哪些层、哪些指标或哪些机制。\n"
            "输出仍保持 BridgeMemo 结构，但 conflicts 和 cross_layer_claims 需要引用具体 function_id。\n"
            "cross_layer_claims[].supporting_facts 只能填写 evidence ref 字符串，格式如 "
            "\"L4.get_ndx_pe_and_earnings_yield\"；不要写中文事实句、数值解释或自然语言，"
            "这些解释应放在 claim 或 mechanism。若 LayerCard 标出 mixed-field payload，必须沿用其显式 "
            "#FieldName 子引用；不得退回函数级父 ref。"
        )
        bridge_contract += (
            "\nBridge v2 新增字段必须尽量原生填写：\n"
            "- typed_conflicts: 结构化冲突地图，包含 conflict_id、conflict_type、severity、confidence、description、mechanism、implication、involved_layers、evidence_refs、falsifiers。\n"
            "- resonance_chains: 跨层共振链，必须包含 involved_layers、evidence_refs、mechanism、confirming_indicators、falsifiers、implication；没有证据或确认指标时降低 confidence。\n"
            "- transmission_paths: 跨层传导路径，说明压力或支撑如何从 source_layer 传到 target_layer。\n"
            "- principal_contradiction: 主要矛盾地图，必须说明 contradiction_id、summary、why_principal、dominant_side、secondary_side、price_reflection、action_implication、conflict_refs、evidence_refs、transformation_signals。\n"
            "- secondary_contradictions: 次要矛盾列表，说明为什么当前不是主导项，以及它如何约束行动力度、节奏或置信度。\n"
            "- price_reflection_map: 判断关键风险/叙事是否已经进入价格，可用 not_reflected / partially_reflected / largely_reflected / over_reflected / unclear。\n"
            "- contradiction_transformation_signals: 会让主次矛盾或矛盾主导方面发生转化的可观察信号。\n"
            "- unresolved_questions: 仍需 Thesis/Critic/Risk 保留的问题。\n"
            "旧字段 conflicts 仍要填写，用于兼容；typed_conflicts 是更高优先级的 Bridge v2 产物。\n"
        )
        if has_event_input:
            bridge_contract += (
                "如果输入包含 event_refs，Bridge 可以引用 event_ref 解释触发/背景/观察，但不得把事件写成 evidence_ref，也不得说事件“证明”某个数值指标结论。\n"
            "\n## 顶层 BridgeMemo.event_refs 字段类型（强约束）\n"
            "- BridgeMemo.event_refs 类型固定为 List[str]，只放事件 ID 字符串，例如：[\"event:6479503280a4bf43\", \"event:f71e0fd17b6261c5\"]。\n"
            "- 输入里的 event_refs 是 Dict[event_id, 事件元数据]（标题、来源、时间），仅供你引用 ID；禁止把这种 dict 形态复制到输出。\n"
            "- 不要写成 {\"event:xxx\": \"...\"} 之类的 dict、对象或映射；如果没有要保留的事件，请写 []。\n"
            "- typed_conflicts/resonance_chains/transmission_paths 内部的 event_refs 同样是 List[str]。\n"
            )
        return f"{bridge_contract}\n\n{prompt_body}"

    def _compose_thesis_prompt(self, prompt_body: str, payload: Optional[Dict[str, Any]] = None) -> str:
        synthesis_payload = payload.get("synthesis_packet") if isinstance(payload, dict) else {}
        has_event_input = bool(isinstance(synthesis_payload, dict) and synthesis_payload.get("event_index"))
        thesis_contract = (
            "## vNext v2 Decision Thesis Contract\n"
            "你现在只消费 synthesis_packet。不要重新分析原始数据，不要替 L1-L5 补写单指标推理。"
            "你的职责是把 layer_summaries、bridge_summaries、high_severity_conflicts 与 evidence_index "
            "整合成主论点、支撑链、保留冲突、依赖前提，以及定价与赔率判断面。\n\n"
            "key_support_chains[].evidence_refs 应引用 synthesis_packet.evidence_index 的键或 Bridge 摘要。"
            "若 evidence_index 条目标记 mixed_field_authority=true，函数级父 ref 不能支持强结论；必须改用同一索引内显式的 #FieldName 子 ref。"
            "retained_conflicts 必须包含 synthesis_packet.high_severity_conflicts 中的所有高严重度冲突。"
        )
        thesis_contract += (
            "\n必须读取 synthesis_packet.objective_firewall_summary，检查投资对象、指标发言权、跨层验证和最强反证。"
            "如果 objective_firewall_summary 的 object_clear、authority_clear 或 cross_layer_verified 为 false，"
            "不得给出强结论，必须降低 confidence 并在 dependencies/retained_conflicts 中保留相应边界。"
        )
        if has_event_input:
            thesis_contract += (
                "如果使用 synthesis_packet.event_index，只能把 event_refs 写成催化剂、背景或观察事项；"
                "不得让 event_refs 替代 key_support_chains[].evidence_refs。"
            )
        thesis_contract += (
            "\n\nDecision Semantics 必填语义："
            "state_diagnosis 说明当前市场状态；priced_narrative 说明价格正在定价什么、哪些坏消息已/未反映；"
            "payoff_assessment 必须区分高风险高赔率、高风险低赔率、低风险低赔率等；"
            "time_horizon_views 至少覆盖数日、1-3个月、6-12个月；"
            "portfolio_actions 至少覆盖 core_position、tactical_position、waiting_cash；"
            "confirmation_cost 必须说明等待确认降低什么风险、可能错过什么；"
            "invalidation_conditions 必须是可观察条件；reader_conclusion 面向普通读者，不能写内部审批话术。"
            "principal_contradiction 必须来自 synthesis_packet.principal_contradictions 或 bridge_summaries[].principal_contradiction，并说明 why_principal、price_reflection、action_implication；"
            "secondary_contradictions 和 price_reflection_map 必须保留关键次要矛盾和定价判断。"
            "不要把“风险存在”自动等同于“赔率不利”，也不要把“估值改善”自动等同于可以买。"
        )
        return f"{thesis_contract}\n\n{prompt_body}"

    def _filter_layer_raw_data_for_prompt(self, layer: str, layer_raw_data: Any) -> Any:
        """Drop cross-layer indicators and prompt-only audit bookkeeping."""
        if not isinstance(layer_raw_data, dict):
            return layer_raw_data

        layer_value = str(layer).upper()
        filtered: Dict[str, Any] = {}
        for key, payload in layer_raw_data.items():
            function_id = str(payload.get("function_id") or key) if isinstance(payload, dict) else str(key)
            try:
                canon = get_indicator_canon(function_id)
            except KeyError:
                filtered[key] = self._strip_prompt_audit_bookkeeping_fields(payload)
                continue
            if canon.layer.value == layer_value:
                filtered[key] = self._strip_prompt_audit_bookkeeping_fields(payload)
        return filtered

    @classmethod
    def _strip_prompt_audit_bookkeeping_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._strip_prompt_audit_bookkeeping_fields(item)
                for key, item in value.items()
                if key not in PROMPT_AUDIT_BOOKKEEPING_FIELDS
            }
        if isinstance(value, list):
            return [cls._strip_prompt_audit_bookkeeping_fields(item) for item in value]
        return value

    def _summarize_l4_raw_data_for_prompt(self, layer_raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """压缩 L4 prompt 中的长序列数据。

        长序列（如 Damodaran monthly 120 条）留在 artifact，prompt 只保留
        latest/start/end/count/percentile/关键拐点，显著降低 token 成本。
        """
        summarized: Dict[str, Any] = {}
        for key, payload in layer_raw_data.items():
            if not isinstance(payload, dict):
                summarized[key] = payload
                continue
            value = payload.get("value")
            if not isinstance(value, dict):
                summarized[key] = payload
                continue
            new_value = dict(value)
            for field_name, field_value in list(value.items()):
                if isinstance(field_value, list) and len(field_value) > 10:
                    new_value[field_name] = self._summarize_long_series(field_value)
            summarized[key] = {**payload, "value": new_value}
        return summarized

    @staticmethod
    def _summarize_long_series(series: List[Dict[str, Any]], keep_recent: int = 5) -> Dict[str, Any]:
        """对长序列列表计算统计摘要，同时保留最近 N 条精简记录和趋势方向。

        recent_records 只保留 data_date 和数值字段的最新值，避免完整 dict 塞入 prompt。
        """
        if not series:
            return {"count": 0, "summary": "empty"}
        count = len(series)
        first = series[0]
        last = series[-1]

        # Single-pass: collect numeric values per column
        col_values: Dict[str, List[float]] = {}
        if isinstance(first, dict):
            for item in series:
                if not isinstance(item, dict):
                    continue
                for col, v in item.items():
                    if isinstance(v, (int, float)) and v is not None:
                        col_values.setdefault(col, []).append(v)

        numeric_stats: Dict[str, Dict[str, Any]] = {}
        numeric_cols: List[str] = []
        for col, values in col_values.items():
            numeric_cols.append(col)
            mid = len(values) // 2
            first_half_mean = sum(values[:mid]) / mid if mid > 0 else values[0]
            second_half_mean = sum(values[mid:]) / len(values[mid:]) if values[mid:] else values[-1]
            if second_half_mean > first_half_mean * 1.02:
                trend = "rising"
            elif second_half_mean < first_half_mean * 0.98:
                trend = "falling"
            else:
                trend = "stable"
            numeric_stats[col] = {
                "min": round(min(values), 6),
                "max": round(max(values), 6),
                "mean": round(sum(values) / len(values), 6),
                "latest": round(values[-1], 6),
                "trend": trend,
            }

        raw_recent = series[-keep_recent:] if count > keep_recent else series
        recent_items = []
        for item in raw_recent:
            if not isinstance(item, dict):
                continue
            compact = {}
            if "data_date" in item:
                compact["data_date"] = item["data_date"]
            for col in numeric_cols:
                if col in item and item[col] is not None:
                    compact[col] = item[col]
            recent_items.append(compact)
        return {
            "count": count,
            "period_start": first.get("data_date") if isinstance(first, dict) else None,
            "period_end": last.get("data_date") if isinstance(last, dict) else None,
            "latest_record": last if isinstance(last, dict) else None,
            "numeric_summary": numeric_stats,
            "recent_records": recent_items,
            "note": f"显示最近 {len(recent_items)}/{count} 条记录（仅 data_date + 数值）。完整序列在 chart_time_series.json artifact 中可用。",
        }

    def _layer_indicator_manifest(self, layer_raw_data: Any) -> List[Dict[str, Any]]:
        if not isinstance(layer_raw_data, dict):
            return []
        manifest: List[Dict[str, Any]] = []
        for function_id, payload in layer_raw_data.items():
            if not isinstance(payload, dict):
                continue
            manifest.append(
                {
                    "function_id": payload.get("function_id") or function_id,
                    "metric_name": payload.get("metric_name") or payload.get("name") or function_id,
                    "analysis_required": not self._indicator_unavailable_for_analysis(payload),
                    "error": payload.get("error"),
                    "source_tier": payload.get("source_tier") or (payload.get("data_quality") or {}).get("source_tier"),
                    "source_name": payload.get("source_name"),
                    "date": payload.get("date"),
                    "data_quality": self._summarize_manifest_data_quality(payload.get("data_quality")),
                    "notes": payload.get("notes"),
                    "manual_override_used": payload.get("manual_override_used", False),
                }
            )
        return manifest

    @classmethod
    def _summarize_manifest_data_quality(cls, value: Any, depth: int = 0) -> Any:
        if isinstance(value, dict):
            summarized = {
                key: cls._summarize_manifest_data_quality(item, depth + 1)
                for key, item in value.items()
                if key not in PROMPT_AUDIT_BOOKKEEPING_FIELDS
            }
            if (
                depth > 0
                and len(json.dumps(summarized, ensure_ascii=False, default=str))
                > MANIFEST_DATA_QUALITY_OBJECT_CHAR_LIMIT
            ):
                return {
                    "keys": list(summarized.keys()),
                    "summary": "large object omitted from indicator manifest; full detail remains in analysis_packet artifact",
                }
            return summarized
        if isinstance(value, list):
            if (
                len(value) > MANIFEST_DATA_QUALITY_LIST_LIMIT
                or len(json.dumps(value, ensure_ascii=False, default=str)) > MANIFEST_DATA_QUALITY_OBJECT_CHAR_LIMIT
            ):
                return {
                    "count": len(value),
                    "summary": "large list omitted from indicator manifest; full detail remains in analysis_packet artifact",
                }
            return [cls._summarize_manifest_data_quality(item, depth + 1) for item in value]
        return value

    def _run_and_save(
        self,
        *,
        stage_key: str,
        stage_name: str,
        model_cls: type,
        payload: dict,
        filename: str,
        validator: Optional[Callable[[Any], List[str]]] = None,
    ) -> Any:
        checkpoint = self._load_stage_checkpoint(
            filename,
            model_cls,
            stage_key=stage_key,
            stage_name=stage_name,
            expected_payload=payload,
        )
        if checkpoint is not None:
            return checkpoint
        result = self._run_stage(
            stage_key=stage_key,
            stage_name=stage_name,
            model_cls=model_cls,
            payload=payload,
            validator=validator,
        )
        self._save_json(filename, result)
        path = Path(filename)
        if not path.is_absolute():
            path = self.output_dir / path
        self._record_stage_artifact(path, stage_key=stage_key, stage_name=stage_name, payload=payload)
        return result

    def _load_prompt(self, stage_key: str) -> str:
        prompt_name = PROMPT_FILES.get(stage_key)
        if prompt_name:
            prompt_path = self.prompts_dir / prompt_name
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8")
        else:
            prompt_path = self.prompts_dir / f"{stage_key}.md"
        if stage_key in INLINE_PROMPTS:
            return INLINE_PROMPTS[stage_key]
        raise RuntimeError(
            f"未找到 stage `{stage_key}` 的 prompt 文件（期望路径：{prompt_path}），"
            "且 INLINE_PROMPTS 没有对应兜底条目。绝不静默返回通用占位 prompt。"
        )

    def _normalize_historical_percentile(self, value: Any) -> tuple[Optional[float], Optional[str]]:
        if value is None or isinstance(value, bool):
            return None, None
        if isinstance(value, (int, float)):
            number = float(value)
            return (number, None) if 0 <= number <= 100 else (None, str(value))
        if isinstance(value, str):
            text = value.strip()
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*%?", text)
            if match:
                number = float(match.group(1))
                return (number, None) if 0 <= number <= 100 else (None, text)
            if text:
                return None, text
        return None, str(value)

    def _save_json(self, filename: str | Path, payload: Any) -> None:
        path = Path(filename)
        if not path.is_absolute():
            path = self.output_dir / path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(_model_dump(payload), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        self._record_stage_artifact(path)

    def _load_stage_manifest(self) -> Dict[str, Any]:
        if self.stage_manifest_path.exists():
            try:
                payload = json.loads(self.stage_manifest_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    payload.setdefault("artifacts", {})
                    return payload
            except Exception:
                pass
        return {
            "schema_version": "vnext_stage_manifest_v1",
            "run_id": self.output_dir.name,
            "output_dir": str(self.output_dir),
            "resume_scope": "same output_dir and same input packet/effective_date only",
            "created_at": _utc_now().isoformat(),
            "updated_at": _utc_now().isoformat(),
            "artifacts": {},
        }

    def _artifact_relpath(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.output_dir).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _strip_volatile_hash_fields(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._strip_volatile_hash_fields(item)
                for key, item in value.items()
                if key not in {"generated_at"}
            }
        if isinstance(value, list):
            return [self._strip_volatile_hash_fields(item) for item in value]
        return value

    def _stable_json_file_sha256(self, path: Path) -> str:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return self._sha256_file(path)
        normalized = json.dumps(
            self._strip_volatile_hash_fields(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _stable_stage_payload_sha256(self, stage_key: str, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(
            self._strip_volatile_hash_fields(self._sanitize_prompt_payload(stage_key, payload)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _current_input_sha256(self) -> Optional[str]:
        analysis_packet_path = self.output_dir / "analysis_packet.json"
        if not analysis_packet_path.exists():
            return None
        return self._stable_json_file_sha256(analysis_packet_path)

    def _manifest_stage_for_path(self, relpath: str) -> str:
        if relpath == "analysis_packet.json":
            return "input"
        if relpath == "context_brief.json" or relpath.startswith("layer_context_briefs/"):
            return "context"
        layer_match = re.fullmatch(r"layer_cards/(L[1-5])\.json", relpath)
        if layer_match:
            return layer_match.group(1).lower()
        if relpath.startswith("bridge_memos/"):
            return "bridge"
        if relpath.startswith("investigation_reports/"):
            return "investigation"
        return {
            "synthesis_packet.json": "synthesis",
            "feedback_contract_manifest.json": "feedback_contract",
            "inquiry_router_output.json": "inquiry_router",
            "thesis_draft.json": "thesis",
            "critique.json": "critic",
            "risk_boundary_report.json": "risk",
            "schema_guard_report.json": "schema_guard",
            "analysis_revised.json": "reviser",
            "final_adjudication.json": "final_adjudicator",
            "run_review_report.json": "run_review",
            "outcome_review_report.json": "outcome_review",
            "post_run_reflection_library.json": "post_run_reflection",
            "llm_stage_diagnostics.json": "diagnostics",
        }.get(relpath, "artifact")

    def _write_stage_manifest(self) -> None:
        self.stage_manifest["updated_at"] = _utc_now().isoformat()
        self.stage_manifest_path.write_text(
            json.dumps(self.stage_manifest, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    def _record_stage_artifact(
        self,
        path: Path,
        *,
        stage_key: Optional[str] = None,
        stage_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if path.resolve() == self.stage_manifest_path.resolve() or not path.exists():
            return
        relpath = self._artifact_relpath(path)
        input_sha256 = self._current_input_sha256()
        item = {
            "stage": self._manifest_stage_for_path(relpath),
            "path": relpath,
            "sha256": self._sha256_file(path),
            "input_sha256": input_sha256,
            "bytes": path.stat().st_size,
            "status": "complete",
            "checkpoint_reusable": relpath.endswith(".json")
            and not relpath.startswith("prompt_audit/")
            and relpath != "run_review_report.json"
            and relpath != "outcome_review_report.json"
            and relpath != "post_run_reflection_library.json",
            "updated_at": _utc_now().isoformat(),
            "effective_date": self._infer_effective_date_from_prompt_audit(""),
        }
        if stage_key:
            item["stage_key"] = stage_key
        if stage_name:
            item["stage_name"] = stage_name
        if stage_key and payload is not None:
            item["payload_sha256"] = self._stable_stage_payload_sha256(stage_key, payload)
        self.stage_manifest.setdefault("artifacts", {})[relpath] = item
        self._write_stage_manifest()

    def _load_stage_checkpoint(
        self,
        filename: str | Path,
        model_cls: type,
        *,
        stage_key: str,
        stage_name: str,
        expected_payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not self.resume_from_existing:
            return None
        path = Path(filename)
        if not path.is_absolute():
            path = self.output_dir / path
        if not path.exists():
            return None
        relpath = self._artifact_relpath(path)
        manifest_item = self.stage_manifest.get("artifacts", {}).get(relpath, {})
        if not manifest_item or manifest_item.get("checkpoint_reusable") is False:
            return None
        if manifest_item.get("sha256") and manifest_item.get("sha256") != self._sha256_file(path):
            return None
        if manifest_item.get("stage_key") and manifest_item.get("stage_key") != stage_key:
            return None
        if manifest_item.get("stage_name") and manifest_item.get("stage_name") != stage_name:
            return None
        if expected_payload is not None:
            expected_payload_sha = self._stable_stage_payload_sha256(stage_key, expected_payload)
            if manifest_item.get("payload_sha256") != expected_payload_sha:
                return None
        current_input_sha256 = self._current_input_sha256()
        if manifest_item.get("input_sha256") and current_input_sha256:
            if manifest_item.get("input_sha256") != current_input_sha256:
                return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validated = model_cls.model_validate(payload)
        except Exception:
            return None
        self.stage_diagnostics["stages"][stage_name] = {
            "stage_key": stage_key,
            "stage_name": stage_name,
            "attempts": 0,
            "errors": [],
            "status": "resumed",
            "checkpoint": {
                "artifact": relpath,
                "sha256": manifest_item.get("sha256"),
                "resume_scope": self.stage_manifest.get("resume_scope"),
            },
            "prompt_audit": {
                "stage_dir": self._prompt_audit_relpath(stage_name),
                "attempts": [],
            },
        }
        self._save_stage_diagnostics()
        return validated

    def _normalize_payload(self, stage_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
        if stage_key.startswith("l") and stage_key.endswith("_analyst"):
            layer_label = str(normalized.get("layer") or stage_key[:2].upper()).upper()
            normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
            for text_key in ("local_conclusion", "layer_synthesis", "internal_conflict_analysis", "notes"):
                if normalized.get(text_key) is not None and not isinstance(normalized.get(text_key), str):
                    normalized[text_key] = json.dumps(normalized[text_key], ensure_ascii=False, default=str)
            if "local_conclusion" in normalized:
                normalized["local_conclusion"] = self._truncate_text(normalized.get("local_conclusion"), 500)
            raw_core_facts = normalized.get("core_facts", []) or []
            if isinstance(raw_core_facts, (str, bytes, dict)) or not isinstance(raw_core_facts, list):
                raw_core_facts = [raw_core_facts]

            normalized_core_facts = []
            for fact in raw_core_facts:
                if not isinstance(fact, dict):
                    text = str(fact)
                    normalized_core_facts.append({"metric": text[:80] or "core_fact", "value": text})
                    continue
                fact["trend"] = self._normalize_trend(fact.get("trend"))
                fact["magnitude"] = self._normalize_magnitude(fact.get("magnitude"))
                if "historical_percentile" in fact:
                    percentile, percentile_note = self._normalize_historical_percentile(fact.get("historical_percentile"))
                    fact["historical_percentile"] = percentile
                    if percentile_note:
                        raw_data = fact.get("raw_data") if isinstance(fact.get("raw_data"), dict) else {}
                        raw_data["historical_percentile_note"] = percentile_note
                        fact["raw_data"] = raw_data
                if isinstance(fact.get("value"), dict):
                    fact["value"] = json.dumps(fact["value"], ensure_ascii=False)
                normalized_core_facts.append(fact)
            normalized["core_facts"] = normalized_core_facts
            if isinstance(normalized.get("indicator_analyses"), list):
                normalized["indicator_analyses"] = [
                    self._normalize_indicator_analysis(item, layer_label=layer_label)
                    for item in normalized["indicator_analyses"]
                    if isinstance(item, dict)
                ]
            if isinstance(normalized.get("quality_self_check"), dict):
                normalized["quality_self_check"].setdefault("covered_function_ids", [])
                normalized["quality_self_check"].setdefault("missing_or_weak_indicators", [])
                normalized["quality_self_check"].setdefault("weak_reasoning_points", [])
                normalized["quality_self_check"].setdefault("unresolved_internal_tensions", [])
                normalized["quality_self_check"].setdefault("confidence_limitations", [])
            if isinstance(normalized.get("cross_layer_hooks"), list):
                normalized["cross_layer_hooks"] = [
                    self._normalize_cross_layer_hook(item)
                    for item in normalized["cross_layer_hooks"]
                ]
        if stage_key in {"bridge", "thesis", "reviser"}:
            for key in ("conflicts", "retained_conflicts", "remaining_conflicts"):
                if isinstance(normalized.get(key), list):
                    normalized[key] = [
                        conflict
                        for conflict in (self._normalize_conflict(item) for item in normalized[key])
                        if conflict
                    ]
            if stage_key == "bridge":
                normalization_notes = self._coerce_string_list(normalized.get("normalization_notes"))
                if "implication_for_ndx" in normalized:
                    normalized["implication_for_ndx"] = self._truncate_text(normalized.get("implication_for_ndx"), 500)
                if isinstance(normalized.get("typed_conflicts"), list):
                    normalized["typed_conflicts"] = [
                        self._normalize_typed_conflict(item)
                        for item in normalized["typed_conflicts"]
                        if isinstance(item, dict)
                    ]
                else:
                    normalized["typed_conflicts"] = self._derive_typed_conflicts(normalized.get("conflicts", []))
                    if normalized["typed_conflicts"]:
                        normalization_notes.append("typed_conflicts_derived_from_legacy_conflicts")
                bridge_fallback_refs = self._bridge_fallback_evidence_refs(normalized)
                if isinstance(normalized.get("cross_layer_claims"), list):
                    claims = []
                    claim_refs_normalized = False
                    for item in normalized["cross_layer_claims"]:
                        if not isinstance(item, dict):
                            continue
                        claim = self._normalize_cross_layer_claim(item, bridge_fallback_refs)
                        claims.append(claim)
                        if claim.get("_supporting_facts_normalized"):
                            claim_refs_normalized = True
                            claim.pop("_supporting_facts_normalized", None)
                    normalized["cross_layer_claims"] = claims
                    if claim_refs_normalized:
                        normalization_notes.append("cross_layer_claim_supporting_facts_normalized_to_evidence_refs")
                if isinstance(normalized.get("resonance_chains"), list):
                    normalized["resonance_chains"] = [
                        self._normalize_resonance_chain(item)
                        for item in normalized["resonance_chains"]
                        if isinstance(item, dict)
                    ]
                if isinstance(normalized.get("transmission_paths"), list):
                    transmission_paths = [
                        self._normalize_transmission_path(item)
                        for item in normalized["transmission_paths"]
                        if isinstance(item, dict)
                    ]
                    normalized["transmission_paths"] = self._dedupe_bridge_transmission_paths(transmission_paths)
                if isinstance(normalized.get("principal_contradiction"), dict):
                    normalized["principal_contradiction"] = self._normalize_principal_contradiction(
                        normalized["principal_contradiction"],
                        typed_conflicts=normalized.get("typed_conflicts", []),
                    )
                else:
                    normalized["principal_contradiction"] = self._derive_principal_contradiction(
                        normalized.get("typed_conflicts", []),
                        normalized.get("conflicts", []),
                    )
                    if normalized.get("principal_contradiction"):
                        normalization_notes.append("principal_contradiction_derived_by_code")
                if isinstance(normalized.get("secondary_contradictions"), list):
                    normalized["secondary_contradictions"] = [
                        self._normalize_secondary_contradiction(item)
                        for item in normalized["secondary_contradictions"]
                        if isinstance(item, dict)
                    ]
                else:
                    normalized["secondary_contradictions"] = self._derive_secondary_contradictions(
                        normalized.get("typed_conflicts", []),
                        normalized.get("principal_contradiction"),
                    )
                    if normalized["secondary_contradictions"]:
                        normalization_notes.append("secondary_contradictions_derived_by_code")
                if isinstance(normalized.get("price_reflection_map"), list):
                    normalized["price_reflection_map"] = [
                        self._normalize_price_reflection_assessment(item)
                        for item in normalized["price_reflection_map"]
                        if isinstance(item, dict)
                    ]
                else:
                    normalized["price_reflection_map"] = self._derive_price_reflection_map(
                        normalized.get("principal_contradiction"),
                    )
                    if normalized["price_reflection_map"]:
                        normalization_notes.append("price_reflection_map_derived_by_code")
                categories_before_completion = {
                    item.get("category")
                    for item in normalized.get("price_reflection_map", [])
                    if isinstance(item, dict)
                }
                normalized["price_reflection_map"] = self._ensure_price_reflection_categories(
                    normalized.get("price_reflection_map", []),
                    fallback_evidence_refs=(normalized.get("principal_contradiction") or {}).get("evidence_refs", []),
                    stage_key=stage_key,
                )
                categories_after_completion = {
                    item.get("category")
                    for item in normalized.get("price_reflection_map", [])
                    if isinstance(item, dict)
                }
                added_categories = sorted(categories_after_completion - categories_before_completion)
                if added_categories:
                    normalization_notes.append(
                        "price_reflection_categories_added_by_code:" + ",".join(added_categories)
                    )
                if isinstance(normalized.get("contradiction_transformation_signals"), list):
                    normalized["contradiction_transformation_signals"] = [
                        self._normalize_contradiction_transformation_signal(item)
                        for item in normalized["contradiction_transformation_signals"]
                        if isinstance(item, dict)
                    ]
                else:
                    principal = normalized.get("principal_contradiction") or {}
                    normalized["contradiction_transformation_signals"] = list(principal.get("transformation_signals", []) or [])
                if not isinstance(normalized.get("unresolved_questions"), list):
                    normalized["unresolved_questions"] = []
                normalized["event_refs"] = self._coerce_event_refs_list(normalized.get("event_refs"))
                normalized["normalization_notes"] = list(dict.fromkeys(normalization_notes))
            if stage_key in {"thesis", "reviser"}:
                thesis_payload = normalized.get("revised_thesis") if stage_key == "reviser" else normalized
                if isinstance(thesis_payload, dict):
                    if isinstance(thesis_payload.get("principal_contradiction"), dict):
                        thesis_payload["principal_contradiction"] = self._normalize_principal_contradiction(
                            thesis_payload["principal_contradiction"],
                            typed_conflicts=[],
                        )
                    if isinstance(thesis_payload.get("secondary_contradictions"), list):
                        thesis_payload["secondary_contradictions"] = [
                            self._normalize_secondary_contradiction(item)
                            for item in thesis_payload["secondary_contradictions"]
                            if isinstance(item, dict)
                        ]
                    if isinstance(thesis_payload.get("price_reflection_map"), list):
                        thesis_payload["price_reflection_map"] = [
                            self._normalize_price_reflection_assessment(item)
                            for item in thesis_payload["price_reflection_map"]
                            if isinstance(item, dict)
                        ]
                    else:
                        thesis_payload["price_reflection_map"] = []
                    thesis_payload["price_reflection_map"] = self._ensure_price_reflection_categories(
                        thesis_payload["price_reflection_map"],
                        fallback_evidence_refs=(thesis_payload.get("principal_contradiction") or {}).get("evidence_refs", []),
                        stage_key=stage_key,
                    )
                    for key in ("time_horizon_views", "portfolio_actions"):
                        if not isinstance(thesis_payload.get(key), list):
                            thesis_payload[key] = []
                    thesis_payload["time_horizon_views"] = [
                        self._normalize_time_horizon_view(item, index=index)
                        for index, item in enumerate(thesis_payload.get("time_horizon_views", []))
                    ]
                    thesis_payload["portfolio_actions"] = [
                        self._normalize_portfolio_action(item, index=index)
                        for index, item in enumerate(thesis_payload.get("portfolio_actions", []))
                    ]
                    if isinstance(thesis_payload.get("reader_conclusion"), dict):
                        thesis_payload["reader_conclusion"] = self._normalize_reader_final(thesis_payload["reader_conclusion"])
            if stage_key == "reviser":
                revised_thesis = normalized.get("revised_thesis")
                if isinstance(revised_thesis, dict) and isinstance(revised_thesis.get("retained_conflicts"), list):
                    revised_thesis["retained_conflicts"] = [
                        conflict
                        for conflict in (
                            self._normalize_conflict(item)
                            for item in revised_thesis["retained_conflicts"]
                        )
                        if conflict
                    ]
        if stage_key == "final":
            if not isinstance(normalized.get("token_usage"), dict):
                normalized["token_usage"] = None
            if isinstance(normalized.get("principal_contradiction"), dict):
                normalized["principal_contradiction"] = self._normalize_principal_contradiction(
                    normalized["principal_contradiction"],
                    typed_conflicts=[],
                )
            if isinstance(normalized.get("secondary_contradictions"), list):
                normalized["secondary_contradictions"] = [
                    self._normalize_secondary_contradiction(item)
                    for item in normalized["secondary_contradictions"]
                    if isinstance(item, dict)
                ]
            if isinstance(normalized.get("price_reflection_map"), list):
                normalized["price_reflection_map"] = [
                    self._normalize_price_reflection_assessment(item)
                    for item in normalized["price_reflection_map"]
                    if isinstance(item, dict)
                ]
            else:
                normalized["price_reflection_map"] = []
            normalized["price_reflection_map"] = self._ensure_price_reflection_categories(
                normalized["price_reflection_map"],
                fallback_evidence_refs=(normalized.get("principal_contradiction") or {}).get("evidence_refs", []),
                stage_key=stage_key,
            )
            for key in ("time_horizon_views", "portfolio_actions"):
                if not isinstance(normalized.get(key), list):
                    normalized[key] = []
            normalized["time_horizon_views"] = [
                self._normalize_time_horizon_view(item, index=index)
                for index, item in enumerate(normalized.get("time_horizon_views", []))
            ]
            normalized["portfolio_actions"] = [
                self._normalize_portfolio_action(item, index=index)
                for index, item in enumerate(normalized.get("portfolio_actions", []))
            ]
            if isinstance(normalized.get("reader_final"), dict):
                normalized["reader_final"] = self._normalize_reader_final(normalized["reader_final"])
        return normalized

    def _normalize_indicator_analysis(self, item: Dict[str, Any], *, layer_label: Optional[str] = None) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["function_id"] = str(
            normalized.get("function_id")
            or normalized.get("metric_id")
            or normalized.get("metric")
            or "unknown"
        )
        normalized["metric"] = str(
            normalized.get("metric")
            or normalized.get("metric_name")
            or normalized["function_id"]
        )
        normalized["narrative"] = str(
            normalized.get("narrative")
            or normalized.get("output_narrative")
            or normalized.get("interpretation")
            or normalized.get("current_reading")
            or ""
        )
        normalized["reasoning_process"] = str(
            normalized.get("reasoning_process")
            or normalized.get("reasoning")
            or normalized.get("rationale")
            or normalized["narrative"]
        )
        if normalized.get("current_reading") is not None and not isinstance(normalized.get("current_reading"), str):
            normalized["current_reading"] = json.dumps(normalized["current_reading"], ensure_ascii=False, default=str)
        for key in (
            "first_principles_chain",
            "evidence_refs",
            "cross_layer_implications",
            "risk_flags",
            "misread_guards",
            "cross_validation_targets",
            "falsifiers",
        ):
            value = normalized.get(key)
            normalized[key] = self._coerce_string_list(value)
        if not normalized["evidence_refs"] and layer_label and normalized["function_id"] != "unknown":
            normalized["evidence_refs"] = [f"{layer_label}.{normalized['function_id']}"]
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        self._backfill_indicator_canon_fields(normalized)
        return normalized

    def _backfill_indicator_canon_fields(self, normalized: Dict[str, Any]) -> None:
        """Populate soft canon fields when the model omits them."""
        try:
            canon = get_indicator_canon(str(normalized.get("function_id") or ""))
        except KeyError:
            return

        if not normalized.get("permission_type"):
            normalized["permission_type"] = _enum_value(canon.permission_type)
        if not normalized.get("canonical_question"):
            normalized["canonical_question"] = canon.canonical_question
        if not normalized.get("core_vs_tactical_boundary"):
            normalized["core_vs_tactical_boundary"] = canon.core_vs_tactical_boundary
        for field_name in ("misread_guards", "cross_validation_targets", "falsifiers"):
            if not normalized.get(field_name):
                normalized[field_name] = list(getattr(canon, field_name))

    def _normalize_cross_layer_hook(self, item: Any) -> Dict[str, Any]:
        if not isinstance(item, dict):
            text = str(item)
            target = self._infer_layer_from_text(text, default="L4")
            return {
                "target_layer": target,
                "question": text,
                "priority": "medium",
            }

        normalized = dict(item)
        target = normalized.get("target_layer") or normalized.get("layer") or normalized.get("target")
        if not target:
            target = self._infer_layer_from_text(json.dumps(normalized, ensure_ascii=False, default=str), default="L4")
        normalized["target_layer"] = self._normalize_layer_label(target)

        question = (
            normalized.get("question")
            or normalized.get("issue")
            or normalized.get("description")
            or normalized.get("rationale")
            or normalized.get("mechanism")
            or normalized.get("prompt")
        )
        if not question:
            question = json.dumps(normalized, ensure_ascii=False, default=str)
        normalized["question"] = str(question)

        priority = str(normalized.get("priority") or "medium").strip().lower()
        normalized["priority"] = priority if priority in {"high", "medium", "low"} else "medium"
        return normalized

    def _normalize_layer_label(self, value: Any) -> str:
        text = str(_enum_value(value) or "").strip().upper()
        match = re.search(r"L([1-5])", text)
        if match:
            return f"L{match.group(1)}"
        if text in {"1", "2", "3", "4", "5"}:
            return f"L{text}"
        return "L4"

    def _infer_layer_from_text(self, text: str, *, default: str) -> str:
        match = re.search(r"L\s*([1-5])", text, re.IGNORECASE)
        if match:
            return f"L{match.group(1)}"
        return default

    def _normalize_conflict(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(conflict, dict):
            return {}
        normalized = dict(conflict)
        if not any(str(value or "").strip() for value in normalized.values()):
            return {}
        normalized["conflict_type"] = str(
            normalized.get("conflict_type")
            or normalized.get("conflict_id")
            or normalized.get("type")
            or "normalized_conflict"
        )
        severity = str(normalized.get("severity") or "medium").lower()
        normalized["severity"] = severity if severity in {"high", "medium", "low"} else "medium"
        normalized["description"] = str(
            normalized.get("description")
            or normalized.get("summary")
            or normalized.get("claim")
            or normalized.get("conflict_type")
            or "模型输出的冲突项缺少描述，已降级为结构占位。"
        )
        normalized["implication"] = str(
            normalized.get("implication")
            or normalized.get("action_implication")
            or normalized.get("description")
            or "需继续跟踪其对最终立场的影响。"
        )
        if not normalized.get("involved_layers"):
            layers = re.findall(r"L[1-5]", normalized.get("conflict_type", "") + " " + normalized.get("description", ""))
            normalized["involved_layers"] = sorted(set(layers)) or ["L1", "L4"]
        return normalized

    def _derive_typed_conflicts(self, conflicts: Any) -> List[Dict[str, Any]]:
        if not isinstance(conflicts, list):
            return []
        return [
            self._normalize_typed_conflict(
                {
                    "conflict_id": conflict.get("conflict_type") or f"conflict_{index}",
                    "conflict_type": conflict.get("conflict_type") or "legacy_conflict",
                    "severity": conflict.get("severity", "medium"),
                    "confidence": conflict.get("confidence", "medium"),
                    "description": conflict.get("description", ""),
                    "mechanism": conflict.get("mechanism", ""),
                    "implication": conflict.get("implication", ""),
                    "involved_layers": conflict.get("involved_layers", []),
                    "evidence_refs": conflict.get("evidence_refs", []),
                    "falsifiers": conflict.get("falsifiers", []),
                }
            )
            for index, conflict in enumerate(conflicts)
            if isinstance(conflict, dict)
        ]

    def _normalize_typed_conflict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["conflict_id"] = str(
            normalized.get("conflict_id")
            or normalized.get("id")
            or normalized.get("conflict_type")
            or "typed_conflict"
        )
        normalized["conflict_type"] = str(normalized.get("conflict_type") or normalized["conflict_id"])
        normalized["severity"] = str(normalized.get("severity") or "medium").lower()
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        normalized["description"] = str(normalized.get("description") or "")
        normalized["mechanism"] = str(normalized.get("mechanism") or "")
        normalized["implication"] = str(normalized.get("implication") or normalized["description"])
        for key in ("involved_layers", "evidence_refs", "falsifiers"):
            value = normalized.get(key)
            normalized[key] = self._coerce_string_list(value)
        normalized["event_refs"] = self._coerce_event_refs_list(normalized.get("event_refs"))
        status = str(normalized.get("status") or "unresolved").lower()
        normalized["status"] = status if status in {"unresolved", "confirmed", "weakened"} else "unresolved"
        return normalized

    def _bridge_fallback_evidence_refs(self, bridge: Dict[str, Any]) -> List[str]:
        refs: List[str] = []

        def add(raw_refs: Any) -> None:
            for ref in self._coerce_string_list(raw_refs):
                if _EVIDENCE_REF_PATTERN.fullmatch(ref) and ref not in refs:
                    refs.append(ref)

        for key in (
            "typed_conflicts",
            "resonance_chains",
            "transmission_paths",
            "secondary_contradictions",
            "price_reflection_map",
        ):
            for item in bridge.get(key) or []:
                if isinstance(item, dict):
                    add(item.get("evidence_refs"))
                    add(item.get("counterevidence_refs"))
        principal = bridge.get("principal_contradiction")
        if isinstance(principal, dict):
            add(principal.get("evidence_refs"))
            for signal in principal.get("transformation_signals") or []:
                if isinstance(signal, dict):
                    add(signal.get("evidence_refs"))
        return refs

    def _normalize_cross_layer_claim(self, item: Dict[str, Any], fallback_refs: List[str]) -> Dict[str, Any]:
        normalized = dict(item)
        raw_supporting_facts = self._coerce_string_list(normalized.get("supporting_facts"))
        valid_refs = [
            ref for ref in raw_supporting_facts
            if _EVIDENCE_REF_PATTERN.fullmatch(ref)
        ]
        invalid_notes = [ref for ref in raw_supporting_facts if ref not in valid_refs]
        if invalid_notes:
            existing_notes = self._coerce_string_list(normalized.get("supporting_fact_notes"))
            normalized["supporting_fact_notes"] = list(dict.fromkeys(existing_notes + invalid_notes))
        if not valid_refs and fallback_refs:
            text = " ".join(
                [
                    str(normalized.get("claim") or ""),
                    str(normalized.get("mechanism") or ""),
                    " ".join(invalid_notes),
                ]
            )
            layers = {
                f"L{match}"
                for match in re.findall(r"L\s*([1-5])", text, flags=re.IGNORECASE)
            }
            if layers:
                valid_refs = [ref for ref in fallback_refs if ref.split(".", 1)[0] in layers]
            if not valid_refs:
                valid_refs = list(fallback_refs)
        normalized["supporting_facts"] = list(dict.fromkeys(valid_refs))
        if invalid_notes or normalized["supporting_facts"] != raw_supporting_facts:
            normalized["_supporting_facts_normalized"] = True
        return normalized

    def _normalize_resonance_chain(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["chain_id"] = str(normalized.get("chain_id") or normalized.get("id") or "resonance_chain")
        normalized["description"] = str(normalized.get("description") or normalized.get("claim") or "")
        normalized["mechanism"] = str(normalized.get("mechanism") or "")
        normalized["implication"] = str(normalized.get("implication") or "")
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        if not normalized.get("involved_layers") and normalized.get("layers"):
            normalized["involved_layers"] = normalized.get("layers")
        for key in ("involved_layers", "evidence_refs", "confirming_indicators", "falsifiers"):
            value = normalized.get(key)
            normalized[key] = self._coerce_string_list(value)
        normalized["event_refs"] = self._coerce_event_refs_list(normalized.get("event_refs"))
        return normalized

    def _normalize_transmission_path(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["path_id"] = str(normalized.get("path_id") or normalized.get("id") or "transmission_path")
        normalized["source_layer"] = self._normalize_layer_label(normalized.get("source_layer") or normalized.get("source") or "L1")
        normalized["target_layer"] = self._normalize_layer_label(normalized.get("target_layer") or normalized.get("target") or "L4")
        normalized["mechanism"] = str(normalized.get("mechanism") or normalized.get("description") or "")
        normalized["implication"] = str(
            normalized.get("implication")
            or normalized.get("action_implication")
            or normalized.get("portfolio_implication")
            or normalized.get("description")
            or normalized.get("mechanism")
            or ""
        )
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        value = normalized.get("evidence_refs")
        normalized["evidence_refs"] = self._coerce_string_list(value)
        value = normalized.get("event_refs")
        normalized["event_refs"] = self._coerce_event_refs_list(value)
        return normalized

    def _dedupe_bridge_transmission_paths(self, paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_paths: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for index, path in enumerate(paths):
            if not isinstance(path, dict):
                continue
            normalized = dict(path)
            raw_id = str(normalized.get("path_id") or "").strip()
            source = self._normalize_layer_label(normalized.get("source_layer") or "L1")
            target = self._normalize_layer_label(normalized.get("target_layer") or "L4")
            base_id = raw_id
            if not base_id or base_id == "transmission_path" or base_id in seen:
                base_id = f"{str(source).lower()}_to_{str(target).lower()}_{index + 1}"
            path_id = base_id
            suffix = 2
            while path_id in seen:
                path_id = f"{base_id}_{suffix}"
                suffix += 1
            seen.add(path_id)
            normalized["path_id"] = path_id
            normalized["source_layer"] = source
            normalized["target_layer"] = target
            if not str(normalized.get("implication") or "").strip():
                normalized["implication"] = str(normalized.get("mechanism") or normalized.get("description") or "")
            normalized_paths.append(normalized)
        return normalized_paths

    def _normalize_contradiction_transformation_signal(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["signal"] = str(normalized.get("signal") or normalized.get("condition") or normalized.get("trigger") or "")
        normalized["direction"] = str(normalized.get("direction") or normalized.get("turns_toward") or "")
        normalized["implication"] = str(normalized.get("implication") or normalized.get("action_implication") or "")
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        normalized["event_refs"] = self._coerce_event_refs_list(normalized.get("event_refs"))
        return normalized

    def _normalize_price_reflection_assessment(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["category"] = self._normalize_price_reflection_category(
            normalized.get("category")
            or normalized.get("type")
            or normalized.get("dimension")
            or normalized.get("target")
            or normalized.get("risk")
            or normalized.get("narrative")
        )
        normalized["target"] = str(
            normalized.get("target")
            or normalized.get("conflict_id")
            or normalized.get("risk")
            or normalized.get("narrative")
            or PRICE_REFLECTION_CATEGORIES.get(normalized["category"], {}).get("target")
            or "price_reflection"
        )
        reflected = str(
            normalized.get("reflected_state")
            or normalized.get("reflection_state")
            or normalized.get("price_reflection")
            or "unclear"
        ).strip().lower()
        allowed = {"not_reflected", "partially_reflected", "largely_reflected", "over_reflected", "unclear"}
        normalized["reflected_state"] = reflected if reflected in allowed else "unclear"
        normalized["rationale"] = str(normalized.get("rationale") or normalized.get("reasoning") or "")
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        normalized["counterevidence"] = self._coerce_string_list(
            normalized.get("counterevidence")
            or normalized.get("counter_evidence")
            or normalized.get("falsifiers")
            or normalized.get("contrary_evidence")
        )
        normalized["counterevidence_refs"] = self._coerce_string_list(
            normalized.get("counterevidence_refs")
            or normalized.get("counter_evidence_refs")
            or normalized.get("contrary_evidence_refs")
        )
        normalized["action_implication"] = str(
            normalized.get("action_implication")
            or normalized.get("portfolio_implication")
            or normalized.get("implication")
            or ""
        )
        normalized["missing_evidence"] = self._coerce_string_list(normalized.get("missing_evidence"))
        return normalized

    def _normalize_price_reflection_category(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = text.replace("-", "_").replace(" ", "_")
        aliases = {
            "credit": ("credit", "spread", "oas", "hyg", "信用", "利差"),
            "rates": ("rates", "rate", "yield", "real_rate", "treasury", "discount", "利率", "真实利率", "贴现"),
            "valuation": ("valuation", "erp", "earnings", "pe", "multiple", "估值", "盈利", "风险补偿"),
            "technical_panic": ("technical", "panic", "trend", "volatility", "vix", "vxn", "ta", "恐慌", "技术", "波动", "趋势"),
            "liquidity": ("liquidity", "m2", "fed", "policy", "流动性", "政策", "美联储"),
        }
        for category, tokens in aliases.items():
            if any(token in text for token in tokens):
                return category
        return text if text in PRICE_REFLECTION_CATEGORIES else "other"

    def _ensure_price_reflection_categories(
        self,
        items: List[Dict[str, Any]],
        *,
        fallback_evidence_refs: Any = None,
        stage_key: str = "",
    ) -> List[Dict[str, Any]]:
        normalized_items = [self._normalize_price_reflection_assessment(item) for item in items if isinstance(item, dict)]
        seen = {item.get("category") for item in normalized_items}
        fallback_refs = self._coerce_string_list(fallback_evidence_refs)
        for category, meta in PRICE_REFLECTION_CATEGORIES.items():
            if category in seen:
                continue
            normalized_items.append(
                self._normalize_price_reflection_assessment(
                    {
                        "category": category,
                        "target": meta["target"],
                        "reflected_state": "unclear",
                        "rationale": f"{meta['label']}价格反映未被 {stage_key or 'stage'} 原生拆出；保留为待复核项，不能当作已分析充分。",
                        "evidence_refs": fallback_refs[:2],
                        "counterevidence": ["缺少该类别的结构化反证分析"],
                        "counterevidence_refs": [],
                        "action_implication": "降低该类别对动作升级/降级的确定性；等待下游或人工复盘补足。",
                        "missing_evidence": [meta["hint"]],
                    }
                )
            )
        return normalized_items

    def _normalize_time_horizon_view(self, item: Any, *, index: int = 0) -> Dict[str, Any]:
        horizons = ["same_day_or_days", "one_to_three_months", "six_to_twelve_months"]
        if not isinstance(item, dict):
            text = str(item)
            return {
                "horizon": horizons[index] if index < len(horizons) else f"horizon_{index + 1}",
                "view": text,
                "action_implication": "模型以字符串输出；归一化层仅保留语义，证据引用仍需结构化补足。",
                "evidence_refs": [],
                "invalidation_conditions": [],
            }
        normalized = dict(item)
        default_horizon = horizons[index] if index < len(horizons) else f"horizon_{index + 1}"
        normalized["horizon"] = str(normalized.get("horizon") or default_horizon)
        normalized["view"] = str(normalized.get("view") or normalized.get("summary") or normalized.get("thesis") or "")
        normalized["action_implication"] = str(normalized.get("action_implication") or normalized.get("action") or "")
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        normalized["invalidation_conditions"] = self._coerce_string_list(normalized.get("invalidation_conditions"))
        return normalized

    def _normalize_portfolio_action(self, item: Any, *, index: int = 0) -> Dict[str, Any]:
        buckets = ["core_position", "tactical_position", "waiting_cash"]
        if not isinstance(item, dict):
            text = str(item)
            return {
                "bucket": buckets[index] if index < len(buckets) else f"bucket_{index + 1}",
                "action": text,
                "rationale": "模型以字符串输出；归一化层仅保留语义，证据引用仍需结构化补足。",
                "conditions": [],
                "evidence_refs": [],
            }
        normalized = dict(item)
        default_bucket = buckets[index] if index < len(buckets) else f"bucket_{index + 1}"
        normalized["bucket"] = str(normalized.get("bucket") or normalized.get("position_bucket") or default_bucket)
        normalized["action"] = str(normalized.get("action") or normalized.get("recommendation") or normalized.get("view") or "")
        normalized["rationale"] = str(normalized.get("rationale") or normalized.get("reasoning") or "")
        normalized["conditions"] = self._coerce_string_list(normalized.get("conditions"))
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        return normalized

    def _normalize_reader_final(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(payload)
        normalized["three_reasons"] = self._coerce_string_list(normalized.get("three_reasons"))
        normalized["invalidation_summary"] = self._coerce_string_list(normalized.get("invalidation_summary"))
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        normalized["time_horizon_summary"] = [
            self._normalize_time_horizon_view(item, index=index)
            for index, item in enumerate(self._as_list_for_normalization(normalized.get("time_horizon_summary")))
        ]
        normalized["action_summary"] = [
            self._normalize_portfolio_action(item, index=index)
            for index, item in enumerate(self._as_list_for_normalization(normalized.get("action_summary")))
        ]
        return normalized

    def _as_list_for_normalization(self, value: Any) -> List[Any]:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def _normalize_principal_contradiction(
        self,
        item: Dict[str, Any],
        *,
        typed_conflicts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["contradiction_id"] = str(
            normalized.get("contradiction_id")
            or normalized.get("conflict_id")
            or normalized.get("id")
            or "principal_contradiction"
        )
        normalized["summary"] = str(normalized.get("summary") or normalized.get("description") or "")
        normalized["why_principal"] = str(normalized.get("why_principal") or normalized.get("rationale") or "")
        normalized["dominant_side"] = str(normalized.get("dominant_side") or normalized.get("main_side") or "")
        normalized["secondary_side"] = str(normalized.get("secondary_side") or normalized.get("other_side") or "")
        normalized["price_reflection"] = str(
            normalized.get("price_reflection")
            or normalized.get("price_reflection_assessment")
            or normalized.get("pricing")
            or ""
        )
        normalized["action_implication"] = str(normalized.get("action_implication") or normalized.get("implication") or "")
        normalized["conflict_refs"] = self._coerce_string_list(normalized.get("conflict_refs"))
        if not normalized["conflict_refs"]:
            conflict_id = normalized["contradiction_id"]
            normalized["conflict_refs"] = [conflict_id] if conflict_id else []
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        if not normalized["evidence_refs"] and typed_conflicts:
            for conflict in typed_conflicts:
                if conflict.get("conflict_id") in normalized["conflict_refs"]:
                    normalized["evidence_refs"] = self._coerce_string_list(conflict.get("evidence_refs"))
                    break
        signals = normalized.get("transformation_signals")
        if isinstance(signals, list):
            normalized["transformation_signals"] = [
                self._normalize_contradiction_transformation_signal(signal)
                for signal in signals
                if isinstance(signal, dict)
            ]
        else:
            normalized["transformation_signals"] = []
        normalized["unresolved_questions"] = self._coerce_string_list(normalized.get("unresolved_questions"))
        return normalized

    def _normalize_secondary_contradiction(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(item)
        normalized["contradiction_id"] = str(
            normalized.get("contradiction_id")
            or normalized.get("conflict_id")
            or normalized.get("id")
            or "secondary_contradiction"
        )
        normalized["summary"] = str(normalized.get("summary") or normalized.get("description") or "")
        normalized["why_secondary"] = str(normalized.get("why_secondary") or normalized.get("rationale") or "")
        normalized["action_constraint"] = str(normalized.get("action_constraint") or normalized.get("implication") or "")
        normalized["evidence_refs"] = self._coerce_string_list(normalized.get("evidence_refs"))
        return normalized

    def _derive_principal_contradiction(
        self,
        typed_conflicts: List[Dict[str, Any]],
        legacy_conflicts: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        candidates = typed_conflicts if typed_conflicts else [
            self._normalize_typed_conflict(
                {
                    "conflict_id": conflict.get("conflict_type") or f"legacy_conflict_{index}",
                    "conflict_type": conflict.get("conflict_type") or "legacy_conflict",
                    "severity": conflict.get("severity", "medium"),
                    "confidence": conflict.get("confidence", "medium"),
                    "description": conflict.get("description", ""),
                    "mechanism": conflict.get("mechanism", ""),
                    "implication": conflict.get("implication", ""),
                    "involved_layers": conflict.get("involved_layers", []),
                    "evidence_refs": conflict.get("evidence_refs", []),
                    "falsifiers": conflict.get("falsifiers", []),
                }
            )
            for index, conflict in enumerate(legacy_conflicts or [])
            if isinstance(conflict, dict)
        ]
        if not candidates:
            return None

        severity_rank = {"high": 3, "medium": 2, "low": 1}
        principal = sorted(
            candidates,
            key=lambda item: severity_rank.get(str(item.get("severity", "medium")).lower(), 2),
            reverse=True,
        )[0]
        conflict_id = str(principal.get("conflict_id") or principal.get("conflict_type") or "principal_contradiction")
        return self._normalize_principal_contradiction(
            {
                "contradiction_id": conflict_id,
                "summary": principal.get("description", ""),
                "why_principal": "由当前最高严重度跨层冲突兜底推导；Thesis 必须进一步判断其是否真正主导收益风险。",
                "dominant_side": "unclear_until_thesis",
                "secondary_side": "",
                "price_reflection": "unclear",
                "action_implication": principal.get("implication", ""),
                "conflict_refs": [conflict_id],
                "evidence_refs": principal.get("evidence_refs", []),
                "transformation_signals": [
                    {"signal": falsifier, "direction": "weaken_principal_contradiction"}
                    for falsifier in self._coerce_string_list(principal.get("falsifiers"))[:3]
                ],
                "unresolved_questions": [],
            },
            typed_conflicts=candidates,
        )

    def _derive_secondary_contradictions(
        self,
        typed_conflicts: List[Dict[str, Any]],
        principal: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        principal_refs = set((principal or {}).get("conflict_refs", []) or [])
        secondary = []
        for conflict in typed_conflicts or []:
            conflict_id = str(conflict.get("conflict_id") or conflict.get("conflict_type") or "")
            if conflict_id and conflict_id in principal_refs:
                continue
            secondary.append(
                self._normalize_secondary_contradiction(
                    {
                        "contradiction_id": conflict_id,
                        "summary": conflict.get("description", ""),
                        "why_secondary": "未被 Bridge 标为当前主要矛盾，但仍约束行动力度或置信度。",
                        "action_constraint": conflict.get("implication", ""),
                        "evidence_refs": conflict.get("evidence_refs", []),
                    }
                )
            )
        return secondary[:4]

    def _derive_price_reflection_map(self, principal: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not principal:
            return []
        return [
            self._normalize_price_reflection_assessment(
                {
                    "target": principal.get("contradiction_id") or "principal_contradiction",
                    "reflected_state": principal.get("price_reflection") or "unclear",
                    "rationale": "Bridge 未原生提供 price_reflection_map；从主要矛盾价格反映字段兜底生成。",
                    "evidence_refs": principal.get("evidence_refs", []),
                    "missing_evidence": [] if principal.get("price_reflection") else ["Bridge 未说明价格反映程度"],
                }
            )
        ]

    def _coerce_event_refs_list(self, value: Any) -> List[str]:
        """BridgeMemo.event_refs must be List[str]; defend against AI mirroring the
        dict-shaped AnalysisPacket.event_refs from the prompt input."""
        if value is None:
            return []
        if isinstance(value, list):
            coerced: List[str] = []
            for item in value:
                if isinstance(item, str):
                    coerced.append(item)
                elif isinstance(item, dict):
                    ref = (
                        item.get("event_id")
                        or item.get("id")
                        or item.get("event_ref")
                        or item.get("ref")
                    )
                    if ref:
                        coerced.append(str(ref))
                elif item is not None:
                    coerced.append(str(item))
            return coerced
        if isinstance(value, dict):
            return [str(key) for key in value.keys()]
        return [str(value)]

    def _coerce_string_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        coerced: List[str] = []
        for item in items:
            if item is None:
                continue
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                layer = str(item.get("layer") or "").strip().upper()
                function_id = str(item.get("function_id") or item.get("metric_id") or "").strip()
                if layer and function_id:
                    text = f"{layer}.{function_id}"
                else:
                    text = str(
                        item.get("ref")
                        or item.get("evidence_ref")
                        or item.get("function_id")
                        or item.get("id")
                        or item.get("metric")
                        or ""
                    ).strip()
            else:
                text = str(item).strip()
            if text:
                coerced.append(text)
        return coerced

    def _truncate_text(self, value: Any, max_length: int) -> str:
        text = str(value or "")
        if len(text) <= max_length:
            return text
        if max_length <= 3:
            return text[:max_length]
        return text[: max_length - 3].rstrip() + "..."

    def _normalize_confidence(self, confidence: Any) -> str:
        if not isinstance(confidence, str):
            return "medium"
        lowered = confidence.strip().lower()
        mapping = {
            "高": "high",
            "高置信度": "high",
            "中": "medium",
            "中等": "medium",
            "中等置信度": "medium",
            "低": "low",
            "低置信度": "low",
        }
        if lowered in {"high", "medium", "low"}:
            return lowered
        return mapping.get(confidence.strip(), "medium")

    def _normalize_trend(self, trend: Any) -> Any:
        if not isinstance(trend, str):
            return trend
        mapping = {
            "flat": "stable",
            "neutral": "stable",
            "normal": "stable",
            "sideways": "stable",
            "below": "falling",
            "below_ma": "falling",
            "near_lower": "falling",
            "bearish": "falling",
            "fear": "falling",
            "above": "rising",
            "above_ma": "rising",
            "near_upper": "rising",
            "bullish": "rising",
            "greed": "rising",
            "accumulation": "rising",
            "distribution": "falling",
        }
        lowered = trend.strip().lower()
        return mapping.get(lowered, trend if lowered in {"rising", "falling", "stable", "volatile"} else None)

    def _normalize_magnitude(self, magnitude: Any) -> Any:
        if not isinstance(magnitude, str):
            return magnitude
        lowered = magnitude.strip().lower()
        mapping = {
            "moderate": "elevated",
            "medium": "elevated",
            "unknown": None,
            "na": None,
        }
        if lowered in {"extreme", "high", "elevated", "normal", "low"}:
            return lowered
        return mapping.get(lowered)


def run_vnext_analysis(
    packet: AnalysisPacket | Dict[str, Any],
    *,
    available_models: List[str],
    output_dir: str,
    resume_from_existing: bool = False,
) -> Dict[str, Any]:
    orchestrator = VNextOrchestrator(
        available_models=available_models,
        output_dir=output_dir,
        resume_from_existing=resume_from_existing,
    )
    return orchestrator.run(packet)
