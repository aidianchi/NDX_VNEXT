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
        AnalysisPacket,
        AnalysisRevised,
        BridgeMemo,
        ContextBrief,
        Critique,
        FinalAdjudication,
        GovernanceInputPacket,
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
    )
    from .deep_research_canon import L3_STRUCTURAL_PRIORITY_FUNCTIONS, build_layer_canon_prompt, get_indicator_canon
    from .few_shot import build_layer_few_shot_prompt
    from .llm_engine import LLMEngine
    from .packet_builder import indicator_payload_unavailable_reason
    from .run_review import build_run_review_report
    from .outcome_review import build_outcome_review_report
except ImportError:
    from contracts import (
        AnalysisPacket,
        AnalysisRevised,
        BridgeMemo,
        ContextBrief,
        Critique,
        FinalAdjudication,
        GovernanceInputPacket,
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
    )
    from deep_research_canon import L3_STRUCTURAL_PRIORITY_FUNCTIONS, build_layer_canon_prompt, get_indicator_canon
    from few_shot import build_layer_few_shot_prompt
    from llm_engine import LLMEngine
    from packet_builder import indicator_payload_unavailable_reason
    from run_review import build_run_review_report
    from outcome_review import build_outcome_review_report

logger = logging.getLogger(__name__)

PROMPT_FILES = {
    "l1_analyst": "l1_analyst.md",
    "l2_analyst": "l2_analyst.md",
    "l3_analyst": "l3_analyst.md",
    "l4_analyst": "l4_analyst.md",
    "l5_analyst": "l5_analyst.md",
    "bridge": "cross_layer_bridge.md",
    "thesis": "thesis_builder.md",
    "critic": "critic.md",
    "risk": "risk_sentinel.md",
    "reviser": "reviser.md",
    "final": "final_adjudicator.md",
}

INLINE_PROMPTS = {
    "bridge": "你负责显式识别跨层支撑关系、冲突关系与关键不确定性。只返回合法 JSON。",
    "thesis": "你负责把 synthesis_packet 整合成状态、价格、赔率、动作和失效条件，并保留未解决冲突。只返回合法 JSON。",
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


_SEVERITY_HIGH_MEDIUM = frozenset({"high", "medium"})

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
        if indicator_payload:
            return True
    return False


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
    ) -> None:
        if not llm_engine and not available_models:
            raise ValueError("At least one available model is required.")
        self.available_models = available_models
        self.output_dir = Path(output_dir).resolve()
        self.prompts_dir = Path(prompts_dir) if prompts_dir else Path(__file__).with_name("prompts")
        self.llm_engine = llm_engine or LLMEngine(available_models=available_models)
        self.max_node_retries = max_node_retries
        self.schema_guard_retry = schema_guard_retry
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.layer_cards_dir = self.output_dir / "layer_cards"
        self.layer_context_dir = self.output_dir / "layer_context_briefs"
        self.bridge_dir = self.output_dir / "bridge_memos"
        self.prompt_audit_dir = self.output_dir / "prompt_audit"
        self.layer_cards_dir.mkdir(exist_ok=True)
        self.layer_context_dir.mkdir(exist_ok=True)
        self.bridge_dir.mkdir(exist_ok=True)
        self.prompt_audit_dir.mkdir(exist_ok=True)
        self.stage_diagnostics: Dict[str, Any] = {"schema_version": "vnext_llm_stage_diagnostics_v1", "stages": {}}

    def run(self, packet: AnalysisPacket | Dict[str, Any]) -> Dict[str, Any]:
        packet_model = packet if isinstance(packet, AnalysisPacket) else AnalysisPacket.model_validate(packet)
        self._save_json("analysis_packet.json", packet_model)

        context_brief = self._build_context_brief(packet_model)
        self._save_json("context_brief.json", context_brief)

        layer_cards = self._run_layer_cards(packet_model, context_brief)
        bridge_memos = [self._run_bridge(packet_model, context_brief, layer_cards)]
        synthesis_packet = self._build_synthesis_packet(packet_model, context_brief, layer_cards, bridge_memos)
        self._save_json("synthesis_packet.json", synthesis_packet)
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
        final_adjudication = self._run_stage(
            stage_key="final",
            stage_name="final_adjudicator",
            model_cls=FinalAdjudication,
            payload={
                "governance_input": _model_dump(gov_input_final),
            },
        )
        token_report = self.llm_engine.get_token_report() if hasattr(self.llm_engine, "get_token_report") else {}
        final_adjudication.token_usage = token_report
        self._save_json("final_adjudication.json", final_adjudication)
        run_review_report = self._build_run_review_report(
            packet_model=packet_model,
            bridge_memos=bridge_memos,
            synthesis_packet=synthesis_packet,
            thesis=thesis,
            risk_report=risk_report,
            final_adjudication=final_adjudication,
        )
        self._save_json("run_review_report.json", run_review_report)
        outcome_review_report = self._build_outcome_review_report(
            packet_model=packet_model,
            final_adjudication=final_adjudication,
        )
        self._save_json("outcome_review_report.json", outcome_review_report)

        return {
            "context_brief": context_brief,
            "layer_cards": layer_cards,
            "bridge_memos": bridge_memos,
            "synthesis_packet": synthesis_packet,
            "thesis_draft": thesis,
            "critique": critique,
            "risk_boundary_report": risk_report,
            "schema_guard_report": schema_report,
            "analysis_revised": analysis_revised,
            "final_adjudication": final_adjudication,
            "run_review_report": run_review_report,
            "outcome_review_report": outcome_review_report,
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
        final_adjudication: FinalAdjudication,
    ) -> RunReviewReport:
        data_integrity = {}
        data_integrity_path = self.output_dir / "data_integrity_report.json"
        if data_integrity_path.exists():
            try:
                data_integrity = json.loads(data_integrity_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data_integrity = {}
        return build_run_review_report(
            run_dir=str(self.output_dir),
            analysis_packet=_model_dump(packet_model),
            bridges=[_model_dump(memo) for memo in bridge_memos],
            synthesis_packet=_model_dump(synthesis_packet),
            thesis_draft=_model_dump(thesis),
            risk_boundary_report=_model_dump(risk_report),
            final_adjudication=_model_dump(final_adjudication),
            data_integrity_report=data_integrity,
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

    def _run_layer_cards(self, packet: AnalysisPacket, context_brief: ContextBrief) -> List[LayerCard]:
        cards: List[LayerCard] = []
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            layer_context_brief = self._build_layer_context_brief(packet, context_brief, layer)
            self._save_json(self.layer_context_dir / f"{layer}.json", layer_context_brief)
            card = self._run_stage(
                stage_key=f"{layer.lower()}_analyst",
                stage_name=layer.lower(),
                model_cls=LayerCard,
                payload={
                    "context_brief": _model_dump(layer_context_brief),
                    "layer": layer,
                    "layer_facts": _model_dump(packet.facts_by_layer.get(layer)),
                    "layer_raw_data": packet.raw_data.get(layer, {}),
                    "manual_overrides": self._build_layer_manual_overrides(packet, layer),
                },
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
        return cards

    def _run_bridge(
        self,
        packet: AnalysisPacket,
        context_brief: ContextBrief,
        layer_cards: List[LayerCard],
    ) -> BridgeMemo:
        bridge = self._run_stage(
            stage_key="bridge",
            stage_name="bridge",
            model_cls=BridgeMemo,
            payload={
                "context_brief": _model_dump(context_brief),
                "candidate_cross_layer_links": [_model_dump(link) for link in packet.candidate_cross_layer_links],
                "layer_cards": [_model_dump(card) for card in layer_cards],
                "event_refs": packet.event_refs,
            },
            validator=self._validate_bridge_memo_v2,
        )
        self._save_json(self.bridge_dir / "bridge_0.json", bridge)
        return bridge

    def _run_thesis(self, synthesis_packet: SynthesisPacket) -> ThesisDraft:
        thesis = self._run_stage(
            stage_key="thesis",
            stage_name="thesis",
            model_cls=ThesisDraft,
            payload={
                "synthesis_packet": _model_dump(synthesis_packet),
            },
        )
        self._save_json("thesis_draft.json", thesis)
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
                evidence_index[ref] = {
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
            # H3: Include both high and medium severity conflicts so Thesis is aware
            # of all meaningful cross-layer tensions, not just the highest severity ones.
            high_conflicts.extend(
                conflict for conflict in memo.conflicts if _severity_is_high_or_medium(conflict)
            )
            high_typed_conflicts.extend(
                conflict for conflict in memo.typed_conflicts if _severity_is_high_or_medium(conflict)
            )
            if getattr(memo, "principal_contradiction", None) is not None:
                principal_contradictions.append(memo.principal_contradiction)
            bridge_summaries.append(
                BridgeSynthesisItem(
                    bridge_type=memo.bridge_type,
                    layers_connected=memo.layers_connected,
                    key_claims=[claim.claim for claim in memo.cross_layer_claims],
                    key_conflicts=[
                        f"{conflict.conflict_type}: {conflict.description}"
                        for conflict in memo.conflicts
                    ],
                    typed_conflicts=[_model_dump(conflict) for conflict in memo.typed_conflicts],
                    resonance_chains=[_model_dump(chain) for chain in memo.resonance_chains],
                    transmission_paths=[_model_dump(path) for path in memo.transmission_paths],
                    principal_contradiction=_model_dump(memo.principal_contradiction) if getattr(memo, "principal_contradiction", None) is not None else None,
                    secondary_contradictions=[_model_dump(item) for item in memo.secondary_contradictions],
                    price_reflection_map=[_model_dump(item) for item in memo.price_reflection_map],
                    contradiction_transformation_signals=[_model_dump(item) for item in memo.contradiction_transformation_signals],
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
        for item in known_items:
            falsifiers.extend(item.falsifiers)

        typed_conflicts = [
            conflict
            for memo in bridge_memos
            for conflict in memo.typed_conflicts
        ]
        legacy_conflicts = [
            conflict
            for memo in bridge_memos
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
        last_error = ""
        stage_record: Dict[str, Any] = {
            "stage_key": stage_key,
            "stage_name": stage_name,
            "attempts": 0,
            "errors": [],
            "prompt_chars": len(prompt),
            "status": "running",
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
            "bridge": ["context_brief.json", "layer_cards/L1-L5.json", "analysis_packet.event_refs"],
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
        valid_evidence_refs = {
            f"{layer}.{function_id}"
            for layer, metrics in packet.raw_data.items()
            if isinstance(metrics, dict)
            for function_id in metrics.keys()
        }

        def _bad_refs(refs: List[str]) -> List[str]:
            bad: List[str] = []
            for ref in refs or []:
                ref_text = str(ref)
                if not re.fullmatch(r"L[1-5]\.[A-Za-z_][A-Za-z0-9_]*", ref_text) or ref_text not in valid_evidence_refs:
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

        if not bridge_memos:
            structural_issues.append("No bridge memo generated.")
        else:
            total_conflicts = sum(len(memo.conflicts) for memo in bridge_memos)
            if total_conflicts == 0:
                consistency_issues.append("Bridge stage produced zero conflicts; this usually means tension was flattened.")
            for memo_index, memo in enumerate(bridge_memos):
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

        return SchemaGuardReport(
            passed=not structural_issues and not consistency_issues and not missing_fields,
            structural_issues=structural_issues,
            consistency_issues=consistency_issues,
            missing_fields=missing_fields,
            suggested_fixes=suggested_fixes,
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
            prompt_body = self._compose_bridge_prompt(prompt_body)
        elif stage_key == "thesis":
            prompt_body = self._compose_thesis_prompt(prompt_body)
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
        return sanitized

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

    def _compose_bridge_prompt(self, prompt_body: str) -> str:
        bridge_contract = (
            "## vNext v2 Bridge Contract\n"
            "Bridge 的职责不是重新解释单个指标，而是读取各 LayerCard 的 indicator_analyses、layer_synthesis、"
            "internal_conflict_analysis 和 cross_layer_hooks，识别跨层共振、冲突、传导机制与不确定性。\n\n"
            "必须优先使用 indicator_analyses[].reasoning_process 中已经完成的专业推理；"
            "如果要提出冲突，必须指出冲突来自哪些层、哪些指标或哪些机制。\n"
            "输出仍保持 BridgeMemo 结构，但 conflicts 和 cross_layer_claims 需要尽量引用具体 function_id。"
        )
        bridge_contract += (
            "\nBridge v2 新增字段必须尽量原生填写：\n"
            "- typed_conflicts: 结构化冲突地图，包含 conflict_id、conflict_type、severity、confidence、description、mechanism、implication、involved_layers、evidence_refs、event_refs、falsifiers。\n"
            "- resonance_chains: 跨层共振链，必须包含 involved_layers、evidence_refs、event_refs、mechanism、confirming_indicators、falsifiers、implication；没有证据或确认指标时降低 confidence。\n"
            "- transmission_paths: 跨层传导路径，说明压力或支撑如何从 source_layer 传到 target_layer，可选 event_refs 只能表示催化剂或背景。\n"
            "- principal_contradiction: 主要矛盾地图，必须说明 contradiction_id、summary、why_principal、dominant_side、secondary_side、price_reflection、action_implication、conflict_refs、evidence_refs、transformation_signals。\n"
            "- secondary_contradictions: 次要矛盾列表，说明为什么当前不是主导项，以及它如何约束行动力度、节奏或置信度。\n"
            "- price_reflection_map: 判断关键风险/叙事是否已经进入价格，可用 not_reflected / partially_reflected / largely_reflected / over_reflected / unclear。\n"
            "- contradiction_transformation_signals: 会让主次矛盾或矛盾主导方面发生转化的可观察信号。\n"
            "- unresolved_questions: 仍需 Thesis/Critic/Risk 保留的问题。\n"
            "旧字段 conflicts 仍要填写，用于兼容；typed_conflicts 是更高优先级的 Bridge v2 产物。\n"
            "如果输入包含 event_refs，Bridge 可以引用 event_ref 解释触发/背景/观察，但不得把事件写成 evidence_ref，也不得说事件“证明”某个数值指标结论。\n"
            "\n## 顶层 BridgeMemo.event_refs 字段类型（强约束）\n"
            "- BridgeMemo.event_refs 类型固定为 List[str]，只放事件 ID 字符串，例如：[\"event:6479503280a4bf43\", \"event:f71e0fd17b6261c5\"]。\n"
            "- 输入里的 event_refs 是 Dict[event_id, 事件元数据]（标题、来源、时间），仅供你引用 ID；禁止把这种 dict 形态复制到输出。\n"
            "- 不要写成 {\"event:xxx\": \"...\"} 之类的 dict、对象或映射；如果没有要保留的事件，请写 []。\n"
            "- typed_conflicts/resonance_chains/transmission_paths 内部的 event_refs 同样是 List[str]。\n"
        )
        return f"{bridge_contract}\n\n{prompt_body}"

    def _compose_thesis_prompt(self, prompt_body: str) -> str:
        thesis_contract = (
            "## vNext v2 Decision Thesis Contract\n"
            "你现在只消费 synthesis_packet。不要重新分析原始数据，不要替 L1-L5 补写单指标推理。"
            "你的职责是把 layer_summaries、bridge_summaries、high_severity_conflicts 与 evidence_index "
            "整合成主论点、支撑链、保留冲突、依赖前提，以及定价与赔率判断面。\n\n"
            "key_support_chains[].evidence_refs 应引用 synthesis_packet.evidence_index 的键或 Bridge 摘要。"
            "retained_conflicts 必须包含 synthesis_packet.high_severity_conflicts 中的所有高严重度冲突。"
        )
        thesis_contract += (
            "\n必须读取 synthesis_packet.objective_firewall_summary，检查投资对象、指标发言权、跨层验证和最强反证。"
            "如果 objective_firewall_summary 的 object_clear、authority_clear 或 cross_layer_verified 为 false，"
            "不得给出强结论，必须降低 confidence 并在 dependencies/retained_conflicts 中保留相应边界。"
            "如果使用 synthesis_packet.event_index，只能把 event_refs 写成催化剂、背景或观察事项；"
            "不得让 event_refs 替代 key_support_chains[].evidence_refs。"
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
        """Drop known indicators whose canon belongs to another layer."""
        if not isinstance(layer_raw_data, dict):
            return layer_raw_data

        layer_value = str(layer).upper()
        filtered: Dict[str, Any] = {}
        for key, payload in layer_raw_data.items():
            function_id = str(payload.get("function_id") or key) if isinstance(payload, dict) else str(key)
            try:
                canon = get_indicator_canon(function_id)
            except KeyError:
                filtered[key] = payload
                continue
            if canon.layer.value == layer_value:
                filtered[key] = payload
        return filtered

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
                    "value": payload.get("value"),
                    "source_tier": payload.get("source_tier") or (payload.get("data_quality") or {}).get("source_tier"),
                    "source_name": payload.get("source_name"),
                    "date": payload.get("date"),
                    "data_quality": payload.get("data_quality"),
                    "notes": payload.get("notes"),
                    "manual_override_used": payload.get("manual_override_used", False),
                }
            )
        return manifest

    def _run_and_save(self, *, stage_key: str, stage_name: str, model_cls: type, payload: dict, filename: str) -> Any:
        result = self._run_stage(stage_key=stage_key, stage_name=stage_name, model_cls=model_cls, payload=payload)
        self._save_json(filename, result)
        return result

    def _load_prompt(self, stage_key: str) -> str:
        prompt_name = PROMPT_FILES.get(stage_key)
        if prompt_name:
            prompt_path = self.prompts_dir / prompt_name
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8")
            nested_prompt_path = self.prompts_dir / "prompts" / prompt_name
            if nested_prompt_path.exists():
                return nested_prompt_path.read_text(encoding="utf-8")
        return INLINE_PROMPTS.get(stage_key, "请基于输入返回严格合法的 JSON。")

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

    def _normalize_payload(self, stage_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
        if stage_key.startswith("l") and stage_key.endswith("_analyst"):
            layer_label = str(normalized.get("layer") or stage_key[:2].upper()).upper()
            normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
            for text_key in ("local_conclusion", "layer_synthesis", "internal_conflict_analysis", "notes"):
                if normalized.get(text_key) is not None and not isinstance(normalized.get(text_key), str):
                    normalized[text_key] = json.dumps(normalized[text_key], ensure_ascii=False, default=str)
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
                    normalized[key] = [self._normalize_conflict(item) for item in normalized[key]]
            if stage_key == "bridge":
                if isinstance(normalized.get("typed_conflicts"), list):
                    normalized["typed_conflicts"] = [
                        self._normalize_typed_conflict(item)
                        for item in normalized["typed_conflicts"]
                        if isinstance(item, dict)
                    ]
                else:
                    normalized["typed_conflicts"] = self._derive_typed_conflicts(normalized.get("conflicts", []))
                if isinstance(normalized.get("resonance_chains"), list):
                    normalized["resonance_chains"] = [
                        self._normalize_resonance_chain(item)
                        for item in normalized["resonance_chains"]
                        if isinstance(item, dict)
                    ]
                if isinstance(normalized.get("transmission_paths"), list):
                    normalized["transmission_paths"] = [
                        self._normalize_transmission_path(item)
                        for item in normalized["transmission_paths"]
                        if isinstance(item, dict)
                    ]
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
                normalized["price_reflection_map"] = self._ensure_price_reflection_categories(
                    normalized.get("price_reflection_map", []),
                    fallback_evidence_refs=(normalized.get("principal_contradiction") or {}).get("evidence_refs", []),
                    stage_key=stage_key,
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
                        self._normalize_conflict(item) for item in revised_thesis["retained_conflicts"]
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
        normalized.setdefault("description", "")
        normalized.setdefault("implication", normalized.get("description") or "需继续跟踪其对最终立场的影响。")
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
        normalized["mechanism"] = str(normalized.get("mechanism") or "")
        normalized["implication"] = str(normalized.get("implication") or "")
        normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
        value = normalized.get("evidence_refs")
        normalized["evidence_refs"] = self._coerce_string_list(value)
        value = normalized.get("event_refs")
        normalized["event_refs"] = self._coerce_event_refs_list(value)
        return normalized

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


def run_vnext_analysis(packet: AnalysisPacket | Dict[str, Any], *, available_models: List[str], output_dir: str) -> Dict[str, Any]:
    orchestrator = VNextOrchestrator(available_models=available_models, output_dir=output_dir)
    return orchestrator.run(packet)
