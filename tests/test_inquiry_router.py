import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import InquiryMessage, InquiryMessageType
from agent_analysis.inquiry_router import InquiryRouter


def _message(message_id: str, message_type: InquiryMessageType) -> InquiryMessage:
    return InquiryMessage(
        message_id=message_id,
        message_type=message_type,
        sender_stage="bridge",
        target_stage="L2",
        trigger=f"{message_type.value} trigger",
        question="需要补查什么证据能支持或反驳当前缺口？",
        allowed_context_refs=["bridge_memos/bridge_0.json"],
        forbidden_context_refs=["thesis_draft.json", "final_adjudication.json"],
        effective_date="2026-07-06",
    )


def test_inquiry_router_generates_controlled_agent_specs_for_all_message_types():
    router = InquiryRouter(max_agent_specs=4)
    output = router.route(
        _message(f"inq_{index}", message_type)
        for index, message_type in enumerate(InquiryMessageType, start=1)
    )

    assert output.schema_version == "inquiry_router_output_v1"
    assert [message.message_id for message in output.input_messages] == ["inq_1", "inq_2", "inq_3", "inq_4"]
    assert len(output.agent_specs) == 4
    assert not output.rejected_messages
    for spec in output.agent_specs:
        assert spec.allowed_context_refs == ["bridge_memos/bridge_0.json"]
        assert "thesis_draft.json" in spec.forbidden_context_refs
        assert spec.budget.max_tool_calls == 0
        assert "required_output_fields_completed" in spec.stop_conditions
        assert spec.required_output["contract"] == "InvestigationReport"
        assert "source_authority" in spec.required_output["required_fields"]


def test_inquiry_router_rejects_unauditable_or_over_budget_messages():
    router = InquiryRouter(max_agent_specs=1)
    valid = _message("inq_valid", InquiryMessageType.ADJUDICATION_GAP)
    missing_context = InquiryMessage(
        message_id="inq_missing_context",
        message_type=InquiryMessageType.OBSERVATION_INQUIRY,
        sender_stage="L1",
        target_stage="L2",
        trigger="L1 发现数据异常。",
        question="是否存在历史类似背景？",
        allowed_context_refs=[],
        forbidden_context_refs=["thesis_draft.json"],
        effective_date="2026-07-06",
    )
    over_budget = _message("inq_over_budget", InquiryMessageType.EVENT_CHALLENGE)

    output = router.route([valid, missing_context, over_budget])

    assert len(output.agent_specs) == 1
    reasons = {item.message_id: item.rejection_reason for item in output.rejected_messages}
    assert reasons["inq_missing_context"] == "missing_allowed_context_refs"
    assert reasons["inq_over_budget"] == "router_budget_exhausted"
    assert all(item.trigger for item in output.rejected_messages)
