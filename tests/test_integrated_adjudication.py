"""WO-R8: 第三层真裁决（integrated adjudication）的合约、builder 与渲染测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from integrated_synthesis_report import IntegratedSynthesisReportBuilder  # noqa: E402
from agent_analysis.contracts import IntegratedAdjudication, IntegratedConflictRow  # noqa: E402
from agent_analysis.vnext_reporter import VNextReportGenerator  # noqa: E402


FINAL_STANCE = "实际利率历史极高压制高估值，防守等待。"


def _final_adjudication() -> dict:
    return {
        "generated_at": "2026-07-18T00:00:00Z",
        "final_stance": FINAL_STANCE,
        "approval_status": "approved_with_reservations",
        "confidence": "medium",
        "reasoned_verdict": "核心矛盾是高利率对高估值 [L1.get_10y_real_rate]。",
        "principal_contradiction": {"summary": "估值压缩", "evidence_refs": ["L4.get_damodaran_us_implied_erp"]},
        "must_preserve_risks": ["估值压缩风险"],
        "invalidation_conditions": ["实际利率回落至 2.0% 以下"],
    }


def _cards() -> dict:
    return {"effective_date": "2026-07-18", "cards": [{
        "event_id": "event_abc12345",
        "fact_summary": "报道称某巨头资本开支加速。",
        "interpretation": "可能支持盈利叙事。",
        "mechanism_hypothesis": {"financial_link": "earnings_path", "hypothesis": "可能通过盈利路径影响估值。"},
        "supports_hypotheses": [], "refutes_hypotheses": [],
        "needs_data_confirmation": ["盈利修正数据"], "limitations": [],
        "passport": {"source": "x", "tier": "reliable_report", "effective_date": "2026-07-18"},
    }]}


def _questions() -> dict:
    return {"questions": [
        {"question_id": "q1", "question": "AI 新闻是否有数据同步确认？"},
        {"question_id": "q2", "question": "利率叙事是否有信用利差支持？"},
    ]}


def _valid_response(**overrides) -> str:
    body = {
        "stance_echo": FINAL_STANCE,
        "integrated_verdict": ("综合判决正文。" * 80)[:520] + "[L1.get_10y_real_rate][card:event_abc12345]",
        "current_phenomena": ["实际利率 99 分位 [L1.get_10y_real_rate]"],
        "possible_mechanisms": ["资本开支可能通过盈利路径缓解估值压力"],
        "principal_contradiction": "高利率 vs 高估值",
        "principal_aspect": "利率压制占主导",
        "data_support": ["L1.get_10y_real_rate"],
        "event_support": ["event_abc12345"],
        "integrated_explanations": [],
        "reasonable_assumptions": [],
        "weak_leads": [],
        "unexplained": ["盈利能否消化估值"],
        "strongest_counterevidence": "资本开支加速",
        "question_answers": [{
            "question_id": "q1", "question": "AI 新闻是否有数据同步确认？",
            "answer_status": "partially_answered", "answer": "资本开支已确认，盈利修正缺失。",
            "data_refs": ["L1.get_10y_real_rate"], "investigation_refs": [], "missing_evidence": ["盈利修正"],
        }],
        "conflict_matrix": [{
            "card_id": "event_abc12345", "event_side": "资本开支加速支持盈利叙事",
            "relation": "not_yet_testable", "data_side_refs": [], "note": "缺盈利修正数据",
        }],
        "falsifiers": ["利率回落且盈利上修"],
        "watch_next": ["盈利修正（数据）"],
        "notes": [],
    }
    body.update(overrides)
    return json.dumps(body, ensure_ascii=False)


def _build(llm_response, **kwargs):
    calls = []

    def caller(prompt, stage_name=""):
        calls.append(prompt)
        if callable(llm_response):
            return llm_response(len(calls))
        return llm_response

    builder = IntegratedSynthesisReportBuilder()
    investigation_reports = kwargs.pop("investigation_reports", [])
    payload = builder.build(
        pure_data_report={"principal_contradictions": []},
        analysis_packet={"meta": {"data_date": "2026-07-18"}},
        data_integrity_report={"publish_status": "publishable"},
        event_narrative_ledger={"events": [{"claims": []}]},
        event_interpretation_cards=_cards(),
        final_adjudication=_final_adjudication(),
        cross_layer_questions=_questions(),
        investigation_reports=investigation_reports,
        llm_caller=caller,
        **kwargs,
    )
    return payload, calls


def test_successful_adjudication_and_unanswered_question_note():
    payload, calls = _build(_valid_response())
    adj = payload["integrated_adjudication"]
    assert adj and adj["llm_adjudicated"] is True
    assert adj["stance_echo"] == FINAL_STANCE
    assert payload["policy"]["llm_note"] == "adjudicated"
    assert any(note.startswith("question_unanswered:q2") for note in adj["notes"])
    assert len(calls) == 1


def test_stance_deviation_is_rejected():
    payload, calls = _build(_valid_response(stance_echo="其实应该看多"))
    assert payload["integrated_adjudication"] is None
    assert "llm_adjudication_failed" in payload["policy"]["llm_note"]
    assert len(calls) == 2  # 重试一次后放弃


def test_empty_response_falls_back_without_blocking():
    payload, _ = _build(None)
    assert payload["integrated_adjudication"] is None
    assert "empty_response" in payload["policy"]["llm_note"]
    assert payload["integrated_judgments"]  # 旧确定性拼装不受影响


def test_placeholder_data_side_ref_is_rejected_by_contract():
    with pytest.raises(Exception, match="concrete evidence refs"):
        IntegratedConflictRow(
            card_id="event_abc12345", event_side="x",
            relation="confirmed_by_data", data_side_refs=["pure_data_report"], note="",
        )


def test_unknown_question_and_card_are_dropped_with_notes():
    response = _valid_response()
    data = json.loads(response)
    data["question_answers"].append({
        "question_id": "q_ghost", "question": "幽灵问题", "answer_status": "answered_by_data",
        "answer": "无中生有", "data_refs": [], "investigation_refs": [], "missing_evidence": [],
    })
    data["conflict_matrix"].append({
        "card_id": "event_ghost", "event_side": "幽灵卡",
        "relation": "confirmed_by_data", "data_side_refs": ["L1.get_10y_real_rate"], "note": "",
    })
    payload, _ = _build(json.dumps(data, ensure_ascii=False))
    adj = payload["integrated_adjudication"]
    assert all(a["question_id"] != "q_ghost" for a in adj["question_answers"])
    assert all(r["card_id"] != "event_ghost" for r in adj["conflict_matrix"])
    assert any("dropped_unknown_question:q_ghost" in n for n in adj["notes"])
    assert any("dropped_unknown_card:event_ghost" in n for n in adj["notes"])


def test_env_disable_skips_llm(monkeypatch):
    monkeypatch.setenv("INTEGRATED_ADJUDICATION_LLM_ENABLED", "0")
    payload, calls = _build(_valid_response())
    assert payload["integrated_adjudication"] is None
    assert payload["policy"]["llm_note"] == "disabled_by_env"
    assert not calls


def test_verdict_length_band():
    with pytest.raises(Exception, match="integrated_verdict"):
        IntegratedAdjudication(stance_echo="x", integrated_verdict="太短")


def test_facade_holds_layer1_verdict_and_block_renders_integrated_body():
    """红队 C1 裁决：门脸保持第一层正文；第三层正文在自己的章节完整呈现。"""
    generator = VNextReportGenerator(reports_dir="/tmp/r8_test_reports")
    artifacts = {
        "final_adjudication": _final_adjudication(),
        "synthesis_packet": {"packet_meta": {}},
        "analysis_packet": {"meta": {}},
        "hypothesis_competition": {"hypotheses": []},
        "data_integrity_report": {"publish_status": "publishable"},
        "integrated_synthesis_report": {
            "integrated_adjudication": IntegratedAdjudication.model_validate(
                json.loads(_valid_response())
            ).model_dump(mode="json"),
            "recollection_requests": {
                "requests": [{
                    "source_type": "question",
                    "source_id": "q1",
                    "missing": "缺盈利修正数据",
                    "candidate_function_ids": ["L4.get_forward_earnings"],
                    "trigger_reason": "partially_answered",
                }],
            },
        },
    }
    html = generator._brief_facade_section(Path("/tmp"), artifacts)
    assert "综合判决正文" not in html  # 第三层正文不进门脸（C1 hold）
    assert "核心矛盾是高利率对高估值" in html  # 第一层 reasoned_verdict 保持

    block = generator._integrated_adjudication_block(artifacts)
    assert "新闻事件出的题，数据的回答" in block
    assert "当前不可检验" in block
    assert "综合判决正文" in block  # 第三层正文在此呈现
    assert 'href="#world"' in block  # 红队 M2：card chip 锚点指向真实存在的 #world
    assert "下轮建议补采清单" in block
    assert "缺盈利修正数据" in block


def test_recollection_requests_copy_only_whitelisted_gap_fields():
    data = json.loads(_valid_response())
    data["integrated_verdict"] = ("VERDICT_SENTINEL " * 40) + "[L1.get_10y_real_rate]"
    data["question_answers"][0].update({
        "answer_status": "cannot_answer_yet",
        "answer": "ANSWER_SENTINEL",
        "missing_evidence": ["逐字缺口 L4.get_forward_earnings"],
    })
    data["conflict_matrix"][0]["note"] = "逐字冲突缺口"
    payload, _ = _build(
        json.dumps(data, ensure_ascii=False),
        evidence_registry={
            "passports": {
                "L1.get_10y_real_rate": {},
                "L4.get_forward_earnings#revision": {},
            },
        },
        investigation_reports=[{
            "investigation_id": "inv_gap",
            "effective_date": "2026-07-18",
            "finding": "FINDING_SENTINEL",
            "cannot_establish": ["CANNOT_ESTABLISH_SENTINEL"],
            "limits": ["LIMITS_SENTINEL"],
            "missing_data": ["逐字调查缺口"],
        }],
    )

    requests = payload["recollection_requests"]["requests"]
    assert [request["missing"] for request in requests] == [
        "逐字缺口 L4.get_forward_earnings",
        "逐字冲突缺口",
        "逐字调查缺口",
    ]
    assert requests[0]["candidate_function_ids"] == ["L4.get_forward_earnings"]
    serialized = json.dumps(payload["recollection_requests"], ensure_ascii=False)
    for sentinel in (
        "VERDICT_SENTINEL",
        "ANSWER_SENTINEL",
        "FINDING_SENTINEL",
        "CANNOT_ESTABLISH_SENTINEL",
        "LIMITS_SENTINEL",
    ):
        assert sentinel not in serialized
    assert payload["recollection_requests"]["policy"]["no_stance_rule"] == (
        "requests carry only missing-data descriptions; verdict text must never be copied here"
    )


def test_unknown_candidate_is_not_guessed_and_list_renders_without_adjudication():
    recollection = IntegratedSynthesisReportBuilder()._build_recollection_requests(
        question_answers=[{
            "question_id": "q_unknown",
            "answer_status": "cannot_answer_yet",
            "missing_evidence": ["需要 L5.get_unknown_metric <script>alert(1)</script>"],
        }],
        conflict_rows=[],
        investigation_reports=[],
        evidence_registry={"passports": {}},
    )
    assert recollection["requests"][0]["candidate_function_ids"] == []

    html = VNextReportGenerator(reports_dir="/tmp/w2_recollection")._integrated_adjudication_block({
        "integrated_synthesis_report": {
            "integrated_adjudication": None,
            "recollection_requests": recollection,
        },
    })
    assert "下轮建议补采清单" in html
    assert "L5.get_unknown_metric" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_fake_refs_are_hard_rejected_everywhere():
    """红队 C3：白名单外的 ref/调查 id 一律剔除留痕，不得以 note 放行。"""
    data = json.loads(_valid_response())
    data["data_support"] = ["L9.fake", "L1.get_10y_real_rate"]
    data["question_answers"][0]["data_refs"] = ["L9.fake"]
    data["question_answers"][0]["investigation_refs"] = ["inv_ghost"]
    data["question_answers"][0]["answer_status"] = "answered_by_data"
    data["conflict_matrix"][0] = {
        "card_id": "event_abc12345", "event_side": "x",
        "relation": "confirmed_by_data", "data_side_refs": ["L9.fake"], "note": "",
    }
    payload, _ = _build(json.dumps(data, ensure_ascii=False))
    adj = payload["integrated_adjudication"]
    assert adj["data_support"] == ["L1.get_10y_real_rate"]
    answer = adj["question_answers"][0]
    assert answer["data_refs"] == [] and answer["investigation_refs"] == []
    assert answer["answer_status"] == "cannot_answer_yet"  # 无证据自动降级
    row = adj["conflict_matrix"][0]
    assert row["relation"] == "not_yet_testable" and row["data_side_refs"] == []
    assert any("rejected_unknown_ref" in n for n in adj["notes"])
    assert any("relation_downgraded_no_refs" in n for n in adj["notes"])


def test_publish_gate_merges_claim_gate_and_final_approval():
    """红队 C4：claim gate blocked 或 Final rejected 时第三层降为 audit_only 且不调用 LLM。"""
    builder = IntegratedSynthesisReportBuilder()
    gate = builder._publish_gate(
        {"publish_status": "publishable"}, {"events": [{}]},
        final_claim_ledger={"publish_gate": {"status": "blocked"}},
    )
    assert gate["status"] == "audit_only"
    assert gate["formal_investment_conclusion_allowed"] is False

    gate2 = builder._publish_gate(
        {"publish_status": "publishable"}, {"events": [{}]},
        final_adjudication={"approval_status": "rejected"},
    )
    assert gate2["status"] == "audit_only"


def test_caller_exception_degrades_instead_of_crashing():
    """红队 I4：llm_caller 抛异常必须转为降级，不许炸管线。"""
    def boom(prompt, stage_name=""):
        raise RuntimeError("api down")

    builder = IntegratedSynthesisReportBuilder()
    payload = builder.build(
        pure_data_report={"principal_contradictions": []},
        analysis_packet={"meta": {"data_date": "2026-07-18"}},
        data_integrity_report={"publish_status": "publishable"},
        event_narrative_ledger={"events": [{"claims": []}]},
        event_interpretation_cards=_cards(),
        final_adjudication=_final_adjudication(),
        cross_layer_questions=_questions(),
        llm_caller=boom,
    )
    assert payload["integrated_adjudication"] is None
    assert "caller_exception" in payload["policy"]["llm_note"]
    assert payload["integrated_judgments"]


def test_audit_only_ref_is_demoted_from_data_support():
    """红队 C2：audit-only ref 不得进入数据支持档，自动降入弱线索并留痕。"""
    calls = []

    def caller(prompt, stage_name=""):
        calls.append(prompt)
        data = json.loads(_valid_response())
        data["data_support"] = ["L1.get_10y_real_rate"]
        return json.dumps(data, ensure_ascii=False)

    builder = IntegratedSynthesisReportBuilder()
    payload = builder.build(
        pure_data_report={"principal_contradictions": []},
        analysis_packet={"meta": {"data_date": "2026-07-18"}},
        data_integrity_report={"publish_status": "publishable"},
        event_narrative_ledger={"events": [{"claims": []}]},
        event_interpretation_cards=_cards(),
        final_adjudication=_final_adjudication(),
        cross_layer_questions=_questions(),
        evidence_registry={"passports": {"L1.get_10y_real_rate": {"authority_model": {"field_usage": "audit_only"}}}},
        llm_caller=caller,
    )
    adj = payload["integrated_adjudication"]
    assert adj["data_support"] == []
    assert "L1.get_10y_real_rate" in adj["weak_leads"]
    assert any("audit_only_ref_demoted" in n for n in adj["notes"])
    assert "ref_authority" in calls[0]  # 权限映射确实进了 prompt


def test_env_disable_accepts_common_false_values(monkeypatch):
    """红队 M3：false/off/no 也应关闭 LLM 调用。"""
    for value in ("false", "OFF", "No"):
        monkeypatch.setenv("INTEGRATED_ADJUDICATION_LLM_ENABLED", value)
        payload, calls = _build(_valid_response())
        assert payload["integrated_adjudication"] is None, value
        assert not calls


def test_superseded_markers_on_legacy_fields():
    """红队 I5 裁决：旧结构保留但必须标明已被新裁决取代。"""
    payload, _ = _build(_valid_response())
    assert payload["integrated_judgments"][0]["superseded_by_adjudication"] is True
