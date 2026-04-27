from __future__ import annotations

import json
import logging
import re
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
        LayerCard,
        ObjectiveFirewallSummary,
        SynthesisPacket,
        LayerSynthesisItem,
        BridgeSynthesisItem,
        RiskBoundaryReport,
        SchemaGuardReport,
        ThesisDraft,
    )
    from .deep_research_canon import L3_STRUCTURAL_PRIORITY_FUNCTIONS, build_layer_canon_prompt, get_indicator_canon
    from .few_shot import build_layer_few_shot_prompt
    from .llm_engine import LLMEngine
except ImportError:
    from contracts import (
        AnalysisPacket,
        AnalysisRevised,
        BridgeMemo,
        ContextBrief,
        Critique,
        FinalAdjudication,
        LayerCard,
        ObjectiveFirewallSummary,
        SynthesisPacket,
        LayerSynthesisItem,
        BridgeSynthesisItem,
        RiskBoundaryReport,
        SchemaGuardReport,
        ThesisDraft,
    )
    from deep_research_canon import L3_STRUCTURAL_PRIORITY_FUNCTIONS, build_layer_canon_prompt, get_indicator_canon
    from few_shot import build_layer_few_shot_prompt
    from llm_engine import LLMEngine

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
    "thesis": "你负责基于 LayerCards 与 BridgeMemo 构建主论点，并保留未解决冲突。只返回合法 JSON。",
    "critic": "你负责攻击 ThesisDraft 的逻辑弱点与证据跳跃。只返回合法 JSON。",
    "risk": "你负责保留风险边界、失效条件与必须保留的风险提示。只返回合法 JSON。",
    "reviser": "你负责吸收 critique/risk/schema 反馈后修订 thesis，但不能抹平冲突。只返回合法 JSON。",
    "final": "你负责独立裁决是否放行本次分析，并明确最终立场与必须保留的风险。只返回合法 JSON。",
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
    ) -> None:
        if not llm_engine and not available_models:
            raise ValueError("At least one available model is required.")
        self.available_models = available_models
        self.output_dir = Path(output_dir)
        self.prompts_dir = Path(prompts_dir) if prompts_dir else Path(__file__).with_name("prompts")
        self.llm_engine = llm_engine or LLMEngine(available_models=available_models)
        self.max_node_retries = max_node_retries
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.layer_cards_dir = self.output_dir / "layer_cards"
        self.layer_context_dir = self.output_dir / "layer_context_briefs"
        self.bridge_dir = self.output_dir / "bridge_memos"
        self.layer_cards_dir.mkdir(exist_ok=True)
        self.layer_context_dir.mkdir(exist_ok=True)
        self.bridge_dir.mkdir(exist_ok=True)

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
        critique = self._run_stage(
            stage_key="critic",
            stage_name="critic",
            model_cls=Critique,
            payload={
                "context_brief": _model_dump(context_brief),
                "synthesis_packet": _model_dump(synthesis_packet),
                "thesis_draft": _model_dump(thesis),
                "layer_cards": [_model_dump(card) for card in layer_cards],
                "bridge_memos": [_model_dump(memo) for memo in bridge_memos],
            },
        )
        self._save_json("critique.json", critique)

        risk_report = self._run_stage(
            stage_key="risk",
            stage_name="risk",
            model_cls=RiskBoundaryReport,
            payload={
                "context_brief": _model_dump(context_brief),
                "synthesis_packet": _model_dump(synthesis_packet),
                "thesis_draft": _model_dump(thesis),
                "layer_cards": [_model_dump(card) for card in layer_cards],
                "bridge_memos": [_model_dump(memo) for memo in bridge_memos],
            },
        )
        self._save_json("risk_boundary_report.json", risk_report)

        schema_report = self._run_schema_guard(packet_model, layer_cards, bridge_memos, thesis, critique, risk_report)
        self._save_json("schema_guard_report.json", schema_report)

        analysis_revised = self._run_stage(
            stage_key="reviser",
            stage_name="reviser",
            model_cls=AnalysisRevised,
            payload={
                "context_brief": _model_dump(context_brief),
                "synthesis_packet": _model_dump(synthesis_packet),
                "thesis_draft": _model_dump(thesis),
                "critique": _model_dump(critique),
                "risk_boundary_report": _model_dump(risk_report),
                "schema_guard_report": _model_dump(schema_report),
                "bridge_memos": [_model_dump(memo) for memo in bridge_memos],
            },
        )
        self._save_json("analysis_revised.json", analysis_revised)

        final_adjudication = self._run_stage(
            stage_key="final",
            stage_name="final_adjudicator",
            model_cls=FinalAdjudication,
            payload={
                "context_brief": _model_dump(context_brief),
                "synthesis_packet": _model_dump(synthesis_packet),
                "analysis_revised": _model_dump(analysis_revised),
                "bridge_memos": [_model_dump(memo) for memo in bridge_memos],
                "critique": _model_dump(critique),
                "risk_boundary_report": _model_dump(risk_report),
                "schema_guard_report": _model_dump(schema_report),
                "layer_cards": [_model_dump(card) for card in layer_cards],
            },
        )
        token_report = self.llm_engine.get_token_report() if hasattr(self.llm_engine, "get_token_report") else {}
        final_adjudication.token_usage = token_report
        self._save_json("final_adjudication.json", final_adjudication)

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
            "output_dir": str(self.output_dir),
        }

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
            },
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
            high_conflicts.extend(
                conflict
                for conflict in memo.conflicts
                if str(_enum_value(conflict.severity)) == "high"
            )
            high_typed_conflicts.extend(
                conflict
                for conflict in memo.typed_conflicts
                if str(_enum_value(conflict.severity)) == "high"
            )
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
                    unresolved_questions=memo.unresolved_questions,
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
            objective_firewall_summary=objective_firewall,
            evidence_index=evidence_index,
            synthesis_guidance=[
                "必须消费 objective_firewall_summary：若 object_clear、authority_clear、cross_layer_verified 任一为 false，主结论必须降置信度并保留警示。",
                "Thesis 只能整合 synthesis_packet，不得重新分析原始指标。",
                "必须保留 high_severity_conflicts，不能为了叙事流畅而抹平张力。",
                "所有 key_support_chains 的 evidence_refs 必须来自 evidence_index 或 bridge_summaries。",
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
        cross_layer_verified = bool(typed_conflicts or legacy_conflicts)
        if not cross_layer_verified:
            warnings.append("No bridge conflict or typed conflict verifies cross-layer logic.")

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
            object_clear=True,
            authority_clear=authority_clear if known_items else False,
            timing_clear=timing_clear,
            cross_layer_verified=cross_layer_verified,
            strongest_falsifier=falsifiers[0] if falsifiers else "",
            unresolved_tensions=unresolved_tensions,
            warnings=warnings,
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
        for attempt in range(1, self.max_node_retries + 1):
            active_prompt = prompt
            if last_error:
                active_prompt = (
                    f"{prompt}\n\n上一次返回未通过结构校验，错误如下：\n{last_error}\n"
                    "请仅输出修正后的 JSON 对象，不要附加任何解释。"
                )
            raw = self.llm_engine.call_with_fallback(active_prompt, stage_name=stage_name)
            if not raw:
                last_error = f"{stage_name} received empty response"
                continue
            parsed = self.llm_engine.extract_json(raw, stage_name)
            if not isinstance(parsed, dict):
                last_error = f"{stage_name} did not return a parseable JSON object"
                continue
            parsed = self._normalize_payload(stage_key, parsed)
            try:
                validated = model_cls.model_validate(parsed)
            except Exception as exc:
                last_error = str(exc)
                logger.warning("%s validation failed on attempt %s: %s", stage_name, attempt, exc)
                continue
            if validator:
                validation_errors = validator(validated)
                if validation_errors:
                    last_error = "\n".join(validation_errors)
                    logger.warning(
                        "%s contract validation failed on attempt %s: %s",
                        stage_name,
                        attempt,
                        last_error,
                    )
                    continue
            return validated
        raise RuntimeError(f"{stage_name} failed after {self.max_node_retries} attempts: {last_error}")

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
            missing_from_self_check = sorted(expected_function_ids - covered)
            if expected_function_ids and not card.quality_self_check.coverage_complete:
                errors.append(f"{layer_label}.quality_self_check.coverage_complete must be true.")
            if missing_from_self_check:
                errors.append(
                    f"{layer_label}.quality_self_check.covered_function_ids missing: "
                    + ", ".join(missing_from_self_check)
                )

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
            if payload.get("error"):
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
            if payload.get("error"):
                continue
            resolved_function_id = str(payload.get("function_id") or function_id)
            required[resolved_function_id] = str(
                payload.get("metric_name")
                or payload.get("name")
                or resolved_function_id
            )
        return required

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
        sanitized["layer_raw_data"] = self._filter_layer_raw_data_for_prompt(
            layer,
            sanitized.get("layer_raw_data", {}),
        )
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
            "- L4: 估值、盈利收益率、ERP、风险补偿、安全边际和估值压缩风险。\n"
            "- L5: 价格趋势、动量、波动、成交量、支撑阻力和趋势失效触发。\n"
            "- Bridge: 读取各层结构化产物，验证跨层共振、冲突和传导机制。\n"
            "以上只是职责边界和接口协议，不是其他层的当前数据、状态或结论。"
            "你可以据此决定把验证问题路由给哪一层，但不得据此推断其他层现在是 bullish、bearish、expensive、healthy 或 uptrend。\n\n"
            "### 必须新增并认真填写的字段\n"
            "- indicator_analyses: 对每一个 analysis_required=true 的指标输出一条原生分析。\n"
            "- indicator_analyses[].function_id 必须等于输入 function_id。\n"
            "- indicator_analyses[].metric 必须优先等于输入 metric_name。\n"
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
            "- typed_conflicts: 结构化冲突地图，包含 conflict_id、conflict_type、severity、confidence、description、mechanism、implication、involved_layers、evidence_refs、falsifiers。\n"
            "- resonance_chains: 跨层共振链，说明哪些层在同一方向互相确认。\n"
            "- transmission_paths: 跨层传导路径，说明压力或支撑如何从 source_layer 传到 target_layer。\n"
            "- unresolved_questions: 仍需 Thesis/Critic/Risk 保留的问题。\n"
            "旧字段 conflicts 仍要填写，用于兼容；typed_conflicts 是更高优先级的 Bridge v2 产物。\n"
        )
        return f"{bridge_contract}\n\n{prompt_body}"

    def _compose_thesis_prompt(self, prompt_body: str) -> str:
        thesis_contract = (
            "## vNext v2 Thesis Contract\n"
            "你现在只消费 synthesis_packet。不要重新分析原始数据，不要替 L1-L5 补写单指标推理。"
            "你的职责是把 layer_summaries、bridge_summaries、high_severity_conflicts 与 evidence_index "
            "整合成主论点、支撑链、保留冲突和依赖前提。\n\n"
            "key_support_chains[].evidence_refs 应引用 synthesis_packet.evidence_index 的键或 Bridge 摘要。"
            "retained_conflicts 必须包含 synthesis_packet.high_severity_conflicts 中的所有高严重度冲突。"
        )
        thesis_contract += (
            "\n必须读取 synthesis_packet.objective_firewall_summary，检查投资对象、指标发言权、跨层验证和最强反证。"
            "如果 objective_firewall_summary 的 object_clear、authority_clear 或 cross_layer_verified 为 false，"
            "不得给出强结论，必须降低 confidence 并在 dependencies/retained_conflicts 中保留相应边界。"
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
                    "analysis_required": not bool(payload.get("error")),
                    "error": payload.get("error"),
                    "value": payload.get("value"),
                    "manual_override_used": payload.get("manual_override_used", False),
                }
            )
        return manifest

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
            normalized["confidence"] = self._normalize_confidence(normalized.get("confidence"))
            for text_key in ("local_conclusion", "layer_synthesis", "internal_conflict_analysis", "notes"):
                if normalized.get(text_key) is not None and not isinstance(normalized.get(text_key), str):
                    normalized[text_key] = json.dumps(normalized[text_key], ensure_ascii=False, default=str)
            normalized_core_facts = []
            for fact in normalized.get("core_facts", []) or []:
                if not isinstance(fact, dict):
                    text = str(fact)
                    normalized_core_facts.append({"metric": text[:80] or "core_fact", "value": text})
                    continue
                fact["trend"] = self._normalize_trend(fact.get("trend"))
                fact["magnitude"] = self._normalize_magnitude(fact.get("magnitude"))
                if isinstance(fact.get("value"), dict):
                    fact["value"] = json.dumps(fact["value"], ensure_ascii=False)
                normalized_core_facts.append(fact)
            normalized["core_facts"] = normalized_core_facts
            if isinstance(normalized.get("indicator_analyses"), list):
                normalized["indicator_analyses"] = [
                    self._normalize_indicator_analysis(item)
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
                if not isinstance(normalized.get("unresolved_questions"), list):
                    normalized["unresolved_questions"] = []
            if stage_key == "reviser":
                revised_thesis = normalized.get("revised_thesis")
                if isinstance(revised_thesis, dict) and isinstance(revised_thesis.get("retained_conflicts"), list):
                    revised_thesis["retained_conflicts"] = [
                        self._normalize_conflict(item) for item in revised_thesis["retained_conflicts"]
                    ]
        if stage_key == "final" and not isinstance(normalized.get("token_usage"), dict):
            normalized["token_usage"] = None
        return normalized

    def _normalize_indicator_analysis(self, item: Dict[str, Any]) -> Dict[str, Any]:
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
            if value is None:
                normalized[key] = []
            elif not isinstance(value, list):
                normalized[key] = [str(value)]
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
            if value is None:
                normalized[key] = []
            elif not isinstance(value, list):
                normalized[key] = [str(value)]
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
        for key in ("involved_layers", "evidence_refs"):
            value = normalized.get(key)
            if value is None:
                normalized[key] = []
            elif not isinstance(value, list):
                normalized[key] = [str(value)]
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
        if value is None:
            normalized["evidence_refs"] = []
        elif not isinstance(value, list):
            normalized["evidence_refs"] = [str(value)]
        return normalized

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
