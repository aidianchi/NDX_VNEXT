from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List

try:
    from .contracts import (
        AgentBudget,
        AgentSpec,
        InquiryMessage,
        InquiryMessageType,
        InquiryRouterDecision,
        InquiryRouterOutput,
    )
except ImportError:
    from contracts import (
        AgentBudget,
        AgentSpec,
        InquiryMessage,
        InquiryMessageType,
        InquiryRouterDecision,
        InquiryRouterOutput,
    )


DEFAULT_FORBIDDEN_CONTEXT_REFS = [
    "layer_cards.other_layers_runtime_data",
    "bridge_memos.current_judgment",
    "synthesis_packet.current_judgment",
    "thesis_draft.current_judgment",
    "final_adjudication.current_judgment",
    "post_run_reflection_library.current_run",
]

REQUIRED_INVESTIGATION_OUTPUT_FIELDS = [
    "investigation_id",
    "originating_agent_id",
    "is_deterministic_stub",
    "finding",
    "evidence_refs",
    "counter_evidence_refs",
    "claims_supported",
    "claims_challenged",
    "cannot_establish",
    "confidence",
    "limits",
    "source_authority",
    "effective_date",
]

MESSAGE_TOOL_POLICY = {
    InquiryMessageType.OBSERVATION_INQUIRY: ["read_allowed_artifacts", "deterministic_data_check"],
    InquiryMessageType.EVENT_CHALLENGE: ["read_allowed_artifacts", "scenario_stress_check"],
    InquiryMessageType.ADJUDICATION_GAP: ["read_allowed_artifacts", "targeted_artifact_review"],
    InquiryMessageType.EVIDENCE_UPGRADE_REQUEST: ["read_allowed_artifacts", "source_authority_review"],
}


class InquiryRouter:
    """
    Thin stage-1 router for controlled feedback tasks.

    It deliberately does not run research. It only turns valid InquiryMessage objects into
    bounded AgentSpec task sheets, or records a rejection reason that can be audited later.
    """

    def __init__(
        self,
        *,
        max_agent_specs: int = 3,
        default_budget: AgentBudget | None = None,
        forbidden_context_refs: Iterable[str] | None = None,
    ) -> None:
        self.max_agent_specs = max_agent_specs
        self.default_budget = default_budget or AgentBudget(max_tool_calls=0, max_minutes=0, max_source_refs=0)
        self.default_forbidden_context_refs = list(forbidden_context_refs or DEFAULT_FORBIDDEN_CONTEXT_REFS)

    def route(self, messages: Iterable[InquiryMessage | Dict[str, Any]]) -> InquiryRouterOutput:
        input_messages: List[InquiryMessage] = []
        decisions: List[InquiryRouterDecision] = []
        agent_specs: List[AgentSpec] = []
        rejected_messages: List[InquiryRouterDecision] = []

        for raw_message in messages:
            message = raw_message if isinstance(raw_message, InquiryMessage) else InquiryMessage.model_validate(raw_message)
            input_messages.append(message)
            rejection_reason = self._rejection_reason(message)
            if rejection_reason:
                decision = self._reject(message, rejection_reason)
            elif len(agent_specs) >= self.max_agent_specs:
                decision = self._reject(message, "router_budget_exhausted")
            else:
                decision = self._route_one(message)
            decisions.append(decision)
            if decision.status == "accepted" and decision.agent_spec is not None:
                agent_specs.append(decision.agent_spec)
            elif decision.status == "rejected":
                rejected_messages.append(decision)

        return InquiryRouterOutput(
            input_messages=input_messages,
            decisions=decisions,
            agent_specs=agent_specs,
            rejected_messages=rejected_messages,
            router_policy=self.policy_manifest(),
        )

    def policy_manifest(self) -> Dict[str, Any]:
        return {
            "schema_version": "inquiry_router_policy_v1",
            "max_agent_specs": self.max_agent_specs,
            "stage_1_execution": "contract_only_no_dynamic_agent_execution",
            "default_budget": self.default_budget.model_dump(mode="json"),
            "default_forbidden_context_refs": self.default_forbidden_context_refs,
            "message_types": [item.value for item in InquiryMessageType],
            "required_investigation_output_fields": REQUIRED_INVESTIGATION_OUTPUT_FIELDS,
            "no_backflow_rule": (
                "InvestigationReport may be read by Bridge V2 or integrated synthesis in later stages, "
                "but must not rewrite or be injected into L1-L5 layer cards."
            ),
        }

    def _route_one(self, message: InquiryMessage) -> InquiryRouterDecision:
        rejection_reason = self._rejection_reason(message)
        if rejection_reason:
            return self._reject(message, rejection_reason)

        forbidden_refs = list(dict.fromkeys(message.forbidden_context_refs + self.default_forbidden_context_refs))
        agent_id = f"agent_{hashlib.sha1(message.message_id.encode('utf-8')).hexdigest()[:12]}"
        agent_spec = AgentSpec(
            agent_id=agent_id,
            originating_message_id=message.message_id,
            research_question=message.question,
            allowed_context_refs=message.allowed_context_refs,
            forbidden_context_refs=forbidden_refs,
            allowed_tools=MESSAGE_TOOL_POLICY[message.message_type],
            budget=self.default_budget,
            stop_conditions=[
                "budget_exhausted",
                "required_output_fields_completed",
                "forbidden_context_would_be_required",
            ],
            success_criteria=[
                "finding states what can and cannot be established",
                "supporting and counter evidence refs are separated",
                "source_authority records source tier and limits",
                "effective_date is preserved",
            ],
            required_output={
                "contract": "InvestigationReport",
                "required_fields": REQUIRED_INVESTIGATION_OUTPUT_FIELDS,
                "no_backflow": True,
            },
        )
        return InquiryRouterDecision(
            message_id=message.message_id,
            message_type=message.message_type,
            status="accepted",
            agent_spec=agent_spec,
            trigger=message.trigger,
        )

    def _rejection_reason(self, message: InquiryMessage) -> str:
        if not message.allowed_context_refs:
            return "missing_allowed_context_refs"
        if not message.forbidden_context_refs:
            return "missing_forbidden_context_refs"
        overlap = set(message.allowed_context_refs) & set(message.forbidden_context_refs)
        if overlap:
            return "allowed_context_intersects_forbidden_context: " + ", ".join(sorted(overlap))
        return ""

    def _reject(self, message: InquiryMessage, reason: str) -> InquiryRouterDecision:
        return InquiryRouterDecision(
            message_id=message.message_id,
            message_type=message.message_type,
            status="rejected",
            rejection_reason=reason,
            trigger=message.trigger,
        )
