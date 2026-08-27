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
    # T58/O16：stance_echo 已改代码装配，模型答卷不再包含该字段（填了也会被摘除覆盖）。
    body = {
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
        # T67/W5：裁决批评者独立成站——mock 里 critic 返回空清单（无问题），
        # 使既有"单次草稿、无重试"语义保持可测（draft=1 次 + critic=1 次）。
        if stage_name == "integrated_adjudicator_critic":
            return json.dumps({"critiques": []})
        if callable(llm_response):
            return llm_response(len(calls))
        return llm_response

    builder = IntegratedSynthesisReportBuilder()
    investigation_reports = kwargs.pop("investigation_reports", [])
    cross_layer_questions = kwargs.pop("cross_layer_questions", None)
    payload = builder.build(
        pure_data_report={"principal_contradictions": []},
        analysis_packet={"meta": {"data_date": "2026-07-18"}},
        data_integrity_report={"publish_status": "publishable"},
        event_narrative_ledger={"events": [{"claims": []}]},
        event_interpretation_cards=_cards(),
        final_adjudication=_final_adjudication(),
        cross_layer_questions=cross_layer_questions if cross_layer_questions is not None else _questions(),
        investigation_reports=investigation_reports,
        llm_caller=caller,
        **kwargs,
    )
    return payload, calls


def _sent_payload(calls):
    prompt = calls[0]
    start = prompt.index("```json\n") + len("```json\n")
    end = prompt.rindex("\n```")
    return json.loads(prompt[start:end])


def test_competing_hypotheses_are_compacted_into_payload():
    payload, calls = _build(
        _valid_response(),
        competing_hypotheses=[
            {
                "hypothesis_id": "hyp_a",
                "hypothesis_text": "甲" * 310,
                "status": "leading",
                "source": "bridge_v2",
                "support_evidence_refs": ["L1.get_10y_real_rate"],
            },
            {"hypothesis_id": "hyp_b", "hypothesis_text": "乙", "status": "candidate", "source": "counter_thesis"},
        ],
    )
    assert payload["integrated_adjudication"] is not None
    sent = _sent_payload(calls)
    compacted = sent["competing_hypotheses"]
    assert len(compacted) == 2
    assert compacted[0]["hypothesis_id"] == "hyp_a"
    assert compacted[0]["hypothesis_text"] == "甲" * 300
    assert compacted[0]["status"] == "leading"
    assert compacted[0]["source"] == "bridge_v2"
    assert set(compacted[0]) == {"hypothesis_id", "hypothesis_text", "status", "source"}


def test_event_layer_summary_is_compacted_into_payload():
    payload, calls = _build(
        _valid_response(),
        event_layer_summary={
            "most_important_events": [{"event_cluster_id": "event_cluster:1", "minimum_fact": "美联储发布声明。"}],
            "most_important_claims": [{"claim_text": "某公司财测上修。"}],
            "strongest_counterevidence": ["时间邻近不等于因果证明。"],
        },
    )
    assert payload["integrated_adjudication"] is not None
    sent = _sent_payload(calls)
    summary = sent["event_layer_summary"]
    assert "美联储发布声明" in summary["summary"]
    assert "某公司财测上修" in summary["summary"]
    assert "时间邻近不等于因果证明" in summary["summary"]
    assert summary["cards_available"] is True

    payload_empty, calls_empty = _build(_valid_response())
    sent_empty = _sent_payload(calls_empty)
    assert sent_empty["event_layer_summary"] == {"summary": "", "cards_available": False}


def test_event_research_patrols_carried_into_payload():
    """同步巡逻成果（事件层二档候选材料）进 IA prompt；缺省为空且如实标注。"""
    patrols = {
        "schema_version": "event_research_patrols_v1",
        "patrols": [
            {
                "agenda_id": "EV-20260825-abc123",
                "question": "实际利率是否继续压制估值",
                "narrative_state": {"conclusion": "层内结论文本"},
                "verified_cards": [{"fact_summary": "对账通过的事实", "source_tier": "official"}],
                "downgraded_cards": [{"fact_summary": "降级卡事实", "reconciliation_status": "downgraded_quote_not_found"}],
                "cards_downgraded": 1,
            }
        ],
    }
    payload, calls = _build(_valid_response(), event_research_patrols=patrols)
    assert payload["integrated_adjudication"] is not None
    assert "event_research_patrols" in payload["policy"]["inputs"]
    sent = _sent_payload(calls)
    assert sent["event_research_patrols_empty"] is False
    assert sent["event_research_patrols"][0]["agenda_id"] == "EV-20260825-abc123"
    assert sent["event_research_patrols"][0]["verified_cards"][0]["fact_summary"] == "对账通过的事实"
    assert sent["event_research_patrols"][0]["downgraded_cards"][0]["reconciliation_status"] == "downgraded_quote_not_found"

    payload_empty, calls_empty = _build(_valid_response())
    sent_empty = _sent_payload(calls_empty)
    assert sent_empty["event_research_patrols"] == []
    assert sent_empty["event_research_patrols_empty"] is True


def test_event_research_patrols_respect_effective_date():
    """时点纪律：研究架跨 run 累积，回测/历史 run 只能看到当时已巡逻的成果。"""
    patrols = {
        "patrols": [
            {"agenda_id": "EV-old", "question": "旧成果", "researched_at_utc": "2026-07-10T01:00:00+00:00",
             "verified_cards": [], "narrative_state": {}},
            {"agenda_id": "EV-new", "question": "未来成果", "researched_at_utc": "2026-08-26T01:00:00+00:00",
             "verified_cards": [], "narrative_state": {}},
        ],
    }
    # _build 的 analysis_packet data_date = 2026-07-18：只有 7-10 的进得去
    payload, calls = _build(_valid_response(), event_research_patrols=patrols)
    sent = _sent_payload(calls)
    assert [p["agenda_id"] for p in sent["event_research_patrols"]] == ["EV-old"]


def test_question_event_refs_are_carried_and_sanitized():
    questions = _questions()
    questions["questions"][0]["event_refs"] = ["event:abc12345", "event:from_question"]

    data = json.loads(_valid_response())
    data["question_answers"][0].update({
        "answer_status": "answered_by_data",
        "answer": "数据同步确认。",
        "data_refs": ["L1.get_10y_real_rate"],
        "investigation_refs": [],
        "event_refs": ["event:abc12345", "event_ghost", "event_abc12345"],
        "missing_evidence": [],
    })
    payload, calls = _build(json.dumps(data, ensure_ascii=False), cross_layer_questions=questions)
    assert payload["integrated_adjudication"] is not None
    sent = _sent_payload(calls)
    assert sent["cross_layer_questions"][0]["event_refs"] == ["event:abc12345", "event:from_question"]

    adj = payload["integrated_adjudication"]
    answer = adj["question_answers"][0]
    assert answer["answer_status"] == "answered_by_data"
    assert answer["event_refs"] == ["event:abc12345", "event_abc12345"]
    assert any("rejected_unknown_event_ref:q1:event_ghost" in note for note in adj["notes"])


def test_answered_by_data_with_only_event_refs_still_downgraded():
    questions = _questions()
    questions["questions"][0]["event_refs"] = ["event:abc12345"]

    data = json.loads(_valid_response())
    data["question_answers"][0].update({
        "answer_status": "answered_by_data",
        "answer": "只有事件侧来源。",
        "data_refs": [],
        "investigation_refs": [],
        "event_refs": ["event:abc12345"],
        "missing_evidence": [],
    })
    payload, _ = _build(json.dumps(data, ensure_ascii=False), cross_layer_questions=questions)
    answer = payload["integrated_adjudication"]["question_answers"][0]
    assert answer["answer_status"] == "cannot_answer_yet"
    assert answer["event_refs"] == ["event:abc12345"]
    assert answer["missing_evidence"] == ["缺口未由模型明示，需人工补记"]


def test_investigation_gaps_split_stub_reports():
    reports = [
        {"investigation_id": "inv_good1", "is_deterministic_stub": False, "finding": "有效发现一", "effective_date": "2026-07-18"},
        {"investigation_id": "inv_good2", "is_deterministic_stub": False, "finding": "有效发现二", "effective_date": "2026-07-18"},
        {"investigation_id": "inv_stub", "is_deterministic_stub": True, "finding": "本轮未执行真实调查", "effective_date": "2026-07-18"},
    ]
    payload, calls = _build(_valid_response(), investigation_reports=reports)
    assert payload["integrated_adjudication"] is not None
    sent = _sent_payload(calls)
    assert [r["investigation_id"] for r in sent["investigation_reports"]] == ["inv_good1", "inv_good2"]
    assert sent["allowed_investigation_ids"] == ["inv_good1", "inv_good2"]
    gaps = sent["investigation_gaps"]
    assert len(gaps) == 1
    assert gaps[0]["investigation_id"] == "inv_stub"
    assert gaps[0]["status"] == "deterministic_stub"
    assert gaps[0]["note"] == "本调查未返回有效报告"


def test_successful_adjudication_and_unanswered_question_note():
    payload, calls = _build(_valid_response())
    adj = payload["integrated_adjudication"]
    assert adj and adj["llm_adjudicated"] is True
    assert adj["stance_echo"] == FINAL_STANCE
    assert payload["policy"]["llm_note"] == "adjudicated"
    assert any(note.startswith("question_unanswered:q2") for note in adj["notes"])
    q2 = next(answer for answer in adj["question_answers"] if answer["question_id"] == "q2")
    assert q2["answer_status"] == "cannot_answer_yet"
    assert q2["missing_evidence"] == ["缺口未由模型明示，需人工补记"]
    assert any(request["source_id"] == "q2" for request in payload["recollection_requests"]["requests"])
    assert len(calls) == 2  # draft 1 次 + critic（无问题）1 次，无定稿重跑


def test_stance_echo_assembled_by_code_not_model():
    """T58/O16：stance_echo 改代码装配——模型即使自报偏离的姿态（旧机制的"改判
    意图信号"，实测从未真实触发），也不再触发整包打回；产物里的 stance_echo
    恒等于输入 payload 的 final_stance。异议意图由 conflict_matrix/unexplained
    通道表达（原看守灯 PC-27 已退役，外部材料异议归 PC-28 承接）。"""
    payload, calls = _build(_valid_response(stance_echo="其实应该看多"))
    adj = payload["integrated_adjudication"]
    assert adj is not None
    assert adj["stance_echo"] == FINAL_STANCE
    assert payload["policy"]["llm_note"] == "adjudicated"
    assert len(calls) == 2  # draft 1 次 + critic 1 次；不再因姿态抄写偏差重试


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


def test_data_verdict_objection_material_requires_contradicted_data():
    """T67/W4：material 异议必须点名被挑战的数据点；tangential 可空。"""
    from agent_analysis.contracts import DataVerdictObjection
    with pytest.raises(Exception, match="material objections must name"):
        DataVerdictObjection(
            source_ref="https://example.com/fact", claim="外部事实与数据姿态相反",
            contradicted_data=[], materiality="material",
        )
    ok = DataVerdictObjection(
        source_ref="https://example.com/fact", claim="外部事实与数据姿态相反",
        contradicted_data=["L1.get_10y_real_rate"], materiality="material",
    )
    assert ok.materiality == "material"
    tangential = DataVerdictObjection(
        source_ref="event:abc", claim="擦边", materiality="tangential",
    )
    assert tangential.contradicted_data == []


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
        "缺口未由模型明示，需人工补记",
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


def test_low_quality_placeholder_is_marked_and_counted():
    """Q6: 模型没给具体缺口时，代码侧回填的占位文案必须标记 low_quality_placeholder
    并计入 low_quality_count，不得悄悄混进"已核实缺口清单"误导下一轮补采。"""
    data = json.loads(_valid_response())
    data["question_answers"][0]["missing_evidence"] = []  # 触发 missing_evidence 代码侧占位回填
    data["conflict_matrix"][0] = {
        "card_id": "event_abc12345", "event_side": "资本开支加速支持盈利叙事",
        "relation": "confirmed_by_data", "data_side_refs": [], "note": "",  # 触发 note 代码侧占位回填
    }
    payload, _ = _build(json.dumps(data, ensure_ascii=False))
    requests = payload["recollection_requests"]["requests"]
    assert len(requests) == 3
    assert {r["missing"] for r in requests} == {
        "缺口未由模型明示，需人工补记",
        "原判定缺乏白名单内数据引用，已降级为不可检验",
    }
    assert all(r["quality"] == "low_quality_placeholder" for r in requests)
    assert payload["recollection_requests"]["low_quality_count"] == 3


def test_model_specified_missing_evidence_is_marked_specified():
    """当模型确实写明具体缺口时，quality 必须是 specified，且不计入 low_quality_count。"""
    payload, _ = _build(_valid_response())
    requests = payload["recollection_requests"]["requests"]
    assert requests
    q1 = next(r for r in requests if r["source_id"] == "q1")
    q2 = next(r for r in requests if r["source_id"] == "q2")
    assert q1["quality"] == "specified"
    assert q2["quality"] == "low_quality_placeholder"
    assert payload["recollection_requests"]["low_quality_count"] == 1


def test_downgraded_answer_backfills_missing_evidence_instead_of_vanishing():
    """codex P1 修复：answered_by_data 因无证据被自动降级为 cannot_answer_yet 时，
    若模型没写 missing_evidence，此前会静默从补采清单里消失（既不提醒也不计数）。
    现在必须回填占位并计入 low_quality_count，保证"降级"不等于"这道题被系统遗忘"。"""
    data = json.loads(_valid_response())
    data["question_answers"][0].update({
        "answer_status": "answered_by_data",
        "data_refs": [], "investigation_refs": [], "missing_evidence": [],
    })
    payload, _ = _build(json.dumps(data, ensure_ascii=False))
    answers = payload["integrated_adjudication"]["question_answers"]
    assert answers[0]["answer_status"] == "cannot_answer_yet"
    assert answers[0]["missing_evidence"] == ["缺口未由模型明示，需人工补记"]
    requests = payload["recollection_requests"]["requests"]
    assert any(r["source_id"] == "q1" and r["quality"] == "low_quality_placeholder" for r in requests)


def test_vague_missing_evidence_phrases_are_flagged_low_quality():
    """codex P1 修复：模型自己写"需要更多数据""待补充"这类空话，此前只做精确字符串匹配、
    会被误标成 specified；现在这些常见空话短语也要落 low_quality_placeholder。"""
    from integrated_synthesis_report import _is_low_quality_missing_text

    assert _is_low_quality_missing_text("需要更多数据")
    assert _is_low_quality_missing_text("待补充")
    assert _is_low_quality_missing_text("待确认")
    assert _is_low_quality_missing_text("需要更多数据支持")
    assert _is_low_quality_missing_text("待补充数据")
    assert _is_low_quality_missing_text("需更多数据")
    assert _is_low_quality_missing_text("需更多数据支持")
    assert _is_low_quality_missing_text("还需更多数据支持")
    assert not _is_low_quality_missing_text("需 NVDA 2026Q2 财报公布后的营收同比修订值")  # 具体缺口不得误伤
    assert not _is_low_quality_missing_text("缺 NDX Forward PE 与分析师盈利修正数据")
    assert not _is_low_quality_missing_text("盈利修正")  # 合法的短而具体的缺口，不得被长度规则误伤
    assert not _is_low_quality_missing_text("需要更多数据：NVDA 2026Q2 财报公布后的营收同比修订值")
    assert not _is_low_quality_missing_text("需更多数据：NVDA 2026Q2 财报公布后的营收同比修订值")

    data = json.loads(_valid_response())
    data["question_answers"][0]["missing_evidence"] = ["需要更多数据"]
    payload, _ = _build(json.dumps(data, ensure_ascii=False))
    requests = payload["recollection_requests"]["requests"]
    assert requests[0]["quality"] == "low_quality_placeholder"
    assert payload["recollection_requests"]["low_quality_count"] == 2


def test_empty_or_explicitly_unanswered_questions_are_reconciled_into_recollection():
    data = json.loads(_valid_response())
    data["question_answers"] = []
    payload, _ = _build(json.dumps(data, ensure_ascii=False))
    answers = payload["integrated_adjudication"]["question_answers"]
    assert {answer["question_id"] for answer in answers} == {"q1", "q2"}
    assert all(answer["answer_status"] == "cannot_answer_yet" for answer in answers)
    requests = payload["recollection_requests"]["requests"]
    assert {request["source_id"] for request in requests if request["source_type"] == "question"} == {"q1", "q2"}

    data = json.loads(_valid_response())
    data["question_answers"][0]["answer"] = "未作答"
    data["question_answers"][0]["missing_evidence"] = []
    payload, _ = _build(json.dumps(data, ensure_ascii=False))
    q1 = next(answer for answer in payload["integrated_adjudication"]["question_answers"] if answer["question_id"] == "q1")
    assert q1["answer_status"] == "cannot_answer_yet"
    assert q1["missing_evidence"] == ["缺口未由模型明示，需人工补记"]


def test_question_reconciliation_preserves_canonical_order_specific_gaps_and_first_duplicate():
    data = json.loads(_valid_response())
    q2 = {
        "question_id": "q2", "question": "利率叙事是否有信用利差支持？",
        "answer_status": "cannot_answer_yet", "answer": "未作答",
        "data_refs": [], "investigation_refs": [],
        "missing_evidence": ["缺 2026-07-18 当日 HY OAS level 字段"],
    }
    duplicate_q2 = dict(q2, answer="重复回答", missing_evidence=["不应覆盖首条"])
    data["question_answers"] = [q2, duplicate_q2]
    payload, _ = _build(json.dumps(data, ensure_ascii=False))
    answers = payload["integrated_adjudication"]["question_answers"]
    assert [answer["question_id"] for answer in answers] == ["q1", "q2"]
    assert answers[1]["missing_evidence"] == ["缺 2026-07-18 当日 HY OAS level 字段"]
    assert any(note == "dropped_duplicate_question:q2" for note in payload["integrated_adjudication"]["notes"])


def test_recollection_request_keeps_backward_compatible_keys():
    """消费方 vnext_reporter._recollection_fold 只读这五个键；新增 quality 必须是纯增量。"""
    payload, _ = _build(_valid_response())
    for request in payload["recollection_requests"]["requests"]:
        for key in ("missing", "source_type", "source_id", "candidate_function_ids", "trigger_reason"):
            assert key in request
        assert request["quality"] in {"specified", "low_quality_placeholder"}


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


def test_prompt_requires_specific_missing_evidence_content():
    """Q6：提示词必须要求缺口写明具体字段/窗口，禁止留空或笼统套话。"""
    prompt = (
        Path(__file__).resolve().parents[1]
        / "src" / "agent_analysis" / "prompts" / "integrated_adjudicator.md"
    ).read_text(encoding="utf-8")
    assert "具体缺什么数据、什么字段、什么时间窗口" in prompt
    assert "具体缺哪条数据、哪个字段、哪个时间窗口" in prompt
    assert "禁止留空" in prompt


def test_superseded_markers_on_legacy_fields():
    """红队 I5 裁决：旧结构保留但必须标明已被新裁决取代。"""
    payload, _ = _build(_valid_response())
    assert payload["integrated_judgments"][0]["superseded_by_adjudication"] is True


def test_allowed_refs_are_subset_of_payload_content():
    """T42①-A：许可 ⊆ 实发不变量。allowed_data_refs 必须从 payload 实际发送的内容
    里导出，不能独立扫描完整 final_adjudication——否则会把只出现在
    time_horizon_views/portfolio_actions/claim_ledger 等未被复制进 payload 的字段里的
    ref 也算进许可集合，模型看不到这些 ref 的任何上下文却被告知"可以引用"。"""
    calls = []

    def caller(prompt, stage_name=""):
        calls.append(prompt)
        return _valid_response()

    fa = _final_adjudication()
    # 这个 ref 只出现在 time_horizon_views 里，不会被复制进 payload 的任何叙事字段。
    fa["time_horizon_views"] = [{"evidence_refs": ["L3.get_never_sent_ref"], "invalidation_conditions": []}]

    builder = IntegratedSynthesisReportBuilder()
    builder.build(
        pure_data_report={"principal_contradictions": []},
        analysis_packet={"meta": {"data_date": "2026-07-18"}},
        data_integrity_report={"publish_status": "publishable"},
        event_narrative_ledger={"events": [{"claims": []}]},
        event_interpretation_cards=_cards(),
        final_adjudication=fa,
        cross_layer_questions=_questions(),
        llm_caller=caller,
    )
    assert calls, "LLM caller 应被调用"
    prompt = calls[0]
    start = prompt.index("```json\n") + len("```json\n")
    end = prompt.rindex("\n```")
    sent_payload = json.loads(prompt[start:end])
    allowed = set(sent_payload.get("allowed_data_refs") or [])
    assert "L3.get_never_sent_ref" not in allowed, (
        "只出现在 time_horizon_views 里的 ref 未被复制进 payload 正文，"
        "不应出现在许可集合里（许可 ⊆ 实发不变量）"
    )
    payload_body_text = json.dumps(
        {k: v for k, v in sent_payload.items() if k not in ("allowed_data_refs", "ref_authority")},
        ensure_ascii=False,
    )
    for ref in allowed:
        assert ref in payload_body_text, f"{ref} 进了许可集合但没出现在实际发送内容里"


def test_ref_authority_carries_current_reading_from_evidence_index():
    """T42①-B：ref_authority 必须捎带 synthesis_packet.evidence_index 里的
    canonical_question / current_reading，否则模型明明被许可引用某 ref 却拿不到
    对应的结构化数值，只能回答"本轮输入未提供该数值"。"""
    calls = []

    def caller(prompt, stage_name=""):
        calls.append(prompt)
        return _valid_response()

    fa = _final_adjudication()  # reasoned_verdict 里带 [L1.get_10y_real_rate]，天然会进许可集合
    evidence_index = {
        "L1.get_10y_real_rate": {
            "canonical_question": "实际利率是否处于历史极端位置？",
            "current_reading": "2.41%，99.4分位",
        },
    }
    builder = IntegratedSynthesisReportBuilder()
    builder.build(
        pure_data_report={"principal_contradictions": []},
        analysis_packet={"meta": {"data_date": "2026-07-18"}},
        data_integrity_report={"publish_status": "publishable"},
        event_narrative_ledger={"events": [{"claims": []}]},
        event_interpretation_cards=_cards(),
        final_adjudication=fa,
        cross_layer_questions=_questions(),
        llm_caller=caller,
        evidence_index=evidence_index,
    )
    assert calls, "LLM caller 应被调用"
    prompt = calls[0]
    assert "2.41%，99.4分位" in prompt, (
        "evidence_index 里的 current_reading 数值必须捎带进发给模型的 payload"
    )


def test_ref_authority_registered_parent_refs_never_unknown():
    """A5 修复：已注册但未登记字段级权限的父引用保守默认 supporting_only；
    mixed-field 父引用同保守降级；只有查无护照的引用才标 unknown。"""
    builder = IntegratedSynthesisReportBuilder()
    authority = builder._ref_authority_map(
        allowed_refs=[
            "L1.get_10y_real_rate",
            "L4.get_mixed#parent",
            "L9.not_registered",
        ],
        evidence_registry={
            "passports": {
                "L1.get_10y_real_rate": {
                    "permission_type": "fact",
                    "authority_model": {"field_usage": "", "field_usages": []},
                },
                "L4.get_mixed#parent": {
                    "permission_type": "composite",
                    "authority_model": {
                        "field_usage": "",
                        "field_usages": ["core_allowed", "supporting_only"],
                    },
                },
            }
        },
        evidence_index={
            "L1.get_10y_real_rate": {"canonical_question": "Q1", "current_reading": "R1"},
        },
    )
    assert authority["L1.get_10y_real_rate"]["usage"] == "supporting_only"
    assert authority["L1.get_10y_real_rate"]["usage_source"] == "registered_parent_conservative_default"
    assert authority["L4.get_mixed#parent"]["usage"] == "supporting_only"
    assert authority["L4.get_mixed#parent"]["usage_source"] == "mixed_field_parent_conservative_default"
    assert authority["L4.get_mixed#parent"]["field_usages"] == ["core_allowed", "supporting_only"]
    assert authority["L9.not_registered"]["usage"] == "unknown"
    assert authority["L9.not_registered"]["usage_source"] == "unregistered_ref"


def test_mechanical_literals_are_code_assembled():
    # T54 批 1：schema_version / judgment_object 是固定字面量——模型填错也由代码装配覆盖。
    payload, _ = _build(
        _valid_response(schema_version="ia_v99_llm_invented", judgment_object="QQQ")
    )
    ia = payload["integrated_adjudication"]
    assert ia is not None
    assert ia["schema_version"] == "integrated_adjudication_v1"
    assert ia["judgment_object"] == "NDX"


def _build_critic_flow(critic_response: str, final_response=None, **kwargs):
    """T67/W5：按 stage 返回不同响应的 builder，供裁决批评者路径测试。"""
    calls = []
    stages = []

    def caller(prompt, stage_name=""):
        calls.append(prompt)
        stages.append(stage_name)
        if stage_name == "integrated_adjudicator_critic":
            return critic_response
        if stage_name == "integrated_adjudicator_final":
            return final_response
        return _valid_response()

    builder = IntegratedSynthesisReportBuilder()
    payload = builder.build(
        pure_data_report={"principal_contradictions": []},
        analysis_packet={"meta": {"data_date": "2026-07-18"}},
        data_integrity_report={"publish_status": "publishable"},
        event_narrative_ledger={"events": [{"claims": []}]},
        event_interpretation_cards=_cards(),
        final_adjudication=_final_adjudication(),
        cross_layer_questions=_questions(),
        llm_caller=caller,
        **kwargs,
    )
    return payload, stages


def test_critic_finds_issues_triggers_finalize_and_records_critique():
    """批评者挑出真问题 → 触发定稿调用 → 产物带 critic_applied 标注 + 批评落盘。"""
    critic = json.dumps({"critiques": [{
        "category": "logical_leap", "severity": "high", "target": "integrated_verdict",
        "issue": "把可能写成已经", "suggested_fix": "改为条件句",
    }]})
    payload, stages = _build_critic_flow(critic, final_response=_valid_response())
    assert "integrated_adjudicator_final" in stages
    adj = payload["integrated_adjudication"]
    assert any(note.startswith("critic_applied:1") for note in adj["notes"])
    assert len(payload["integrated_adjudication_critique"]) == 1


def test_critic_failure_degrades_to_draft_without_blocking():
    """批评者两次失败（返回非 JSON）→ 退回草稿 + critic_degraded，不阻断 run。"""
    payload, stages = _build_critic_flow("not-a-json")
    assert "integrated_adjudicator_final" not in stages
    adj = payload["integrated_adjudication"]
    assert adj is not None  # 草稿仍在
    assert any("critic_degraded" in n for n in adj["notes"])
    assert payload["integrated_adjudication_critique"] == []


def test_critic_disabled_by_env(monkeypatch):
    monkeypatch.setenv("INTEGRATED_ADJUDICATION_CRITIC_ENABLED", "0")
    payload, stages = _build_critic_flow("ignored")
    assert "integrated_adjudicator_critic" not in stages
    assert any("critic_disabled_by_env" in n for n in payload["integrated_adjudication"]["notes"])
