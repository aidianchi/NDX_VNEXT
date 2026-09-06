"""T71 材料侧减法第一批（体检 #7/#1）行为锁定测试。

对象 run：`output/analysis/vnext/t70_glm_check_20260902`（25 站上下文体检，
2026-09-05 老板批准按体检顺位施工）。四条病与对应修法：

  #7a 调查员材料按字符切半词 + 垫「甲」凑长度（5/5 实例，源 artifact 甲=0）
      → 切点回退行边界、禁止垫甲、note 注明按行截断（`_read_allowed_context_notes`）
  #7b 自指循环：bridge 未决问题直接派调查、材料又是同一份 memo（5 例中 4 例零信息增量）
      → 问题关键词命中层卡才派单，材料只给命中层卡（`_build_feedback_inquiry_messages`）
  #1① 一层序列摘要路由只接 L4，深嵌套长列表整车进 prompt（L2 prompt 84.6% 是十年日线）
      → 路由扩到 L1/L2/L5 + 证据索引同一把递归瘦身刀（`_sanitize_prompt_payload`）
  #1② critic/risk 的 governance 证据包没过瘦身管道（thesis/reviser/final 有，
      critic/risk 各 ~21 万字符、5 个 L4 ref 逐股全量变体 ≈24.5 万字符）
      → `_slim_governance_key_evidence_refs` 扩到 critic/risk

每条断言对着 run 实测病灶；红灯依据为体检报告与复审备忘
（investigation_reports/20260904_25站上下文体检/），测试锁定新行为防回潮。
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import (
    Confidence,
    InquiryMessageType,
    Layer,
    LayerCard,
    SynthesisPacket,
    ThesisDraft,
    TypedConflict,
)
from agent_analysis.orchestrator import VNextOrchestrator


def _orchestrator(tmp_path: Path) -> VNextOrchestrator:
    return VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )


# ── #7a：截断信封不切半词、不垫「甲」 ──


def test_investigation_material_truncates_at_line_boundary_without_pad(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    ref = "bridge_memos/bridge_0.json"
    (tmp_path / "bridge_memos").mkdir(parents=True, exist_ok=True)
    payload = {"unresolved_questions": [f"问题{i}：" + "x" * 40 for i in range(120)]}
    (tmp_path / ref).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    notes = orch._read_allowed_context_notes([ref], 1, question="未决问题", assembled_refs=[])

    text = notes[0]
    assert "甲" not in text, "截断信封不得用「甲」填充（run 实测 5/5 实例被垫甲）"
    body = text[text.index("{"): text.rindex("}") + 1]
    envelope = json.loads(body)
    assert envelope["_material_truncated"] is True
    assert "已截断" in envelope["note"]
    preview = envelope["preview"]
    excerpt = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    assert excerpt.startswith(preview), "preview 必须是原文前缀"
    assert preview.endswith("\n"), "切点必须落在原文行边界，不得切在词/值中间"
    assert len(preview) < len(excerpt), "本用例必须真的触发截断"


def test_investigation_material_under_budget_stays_intact(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    ref = "bridge_memos/bridge_0.json"
    (tmp_path / "bridge_memos").mkdir(parents=True, exist_ok=True)
    payload = {"note": "短材料不截断"}
    (tmp_path / ref).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    notes = orch._read_allowed_context_notes([ref], 1, question="未决问题", assembled_refs=[])
    assert "_material_truncated" not in notes[0]
    assert "短材料不截断" in notes[0]


# ── #7b：bridge 未决问题只在命中层卡数据面时派单 ──


def _card(layer: Layer, conclusion: str) -> LayerCard:
    # 用真实枚举（live run 20260905_171025 教训：str(枚举) == "Layer.L1"，
    # 字符串夹具抓不到这个 bug 类——refs 曾被拼成 layer_cards/LAYER.L1.json）
    return LayerCard.model_construct(
        layer=layer,
        generated_at="2026-09-02T00:00:00",
        core_facts=[],
        local_conclusion=conclusion,
        confidence="medium",
    )


def test_bridge_unresolved_questions_dispatch_only_with_layer_card_match(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    cards = [
        _card(Layer.L2, "高收益利差走阔至极值，尾部信用收缩"),
        _card(Layer.L1, "实际利率处于十年高位，期货定价偏紧"),
    ]
    bridge = SimpleNamespace(
        unresolved_questions=[
            "高收益利差走阔是特质性再融资还是系统性收缩——用信用数据裁决",
            "本条纯为 memo 内部表述张力，不含任何层卡数据词指向",
        ]
    )

    messages = orch._build_feedback_inquiry_messages(
        packet=SimpleNamespace(meta={}), layer_cards=cards, bridge_v1=bridge
    )

    gap = [
        m
        for m in messages
        if m.message_type == InquiryMessageType.ADJUDICATION_GAP and m.trigger.startswith("Bridge V1 unresolved_questions")
    ]
    assert len(gap) == 1, "零数据指向的问题不再派单（旧实现 5 例中 4 例自指零增量）"
    assert gap[0].allowed_context_refs == ["layer_cards/L2.json"], "材料只给命中的层卡，不给 memo 自己"
    assert gap[0].question.startswith("高收益利差走阔")


def test_bridge_unresolved_question_with_no_data_match_not_dispatched(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    cards = [_card(Layer.L1, "实际利率处于十年高位")]
    bridge = SimpleNamespace(unresolved_questions=["本条纯为 memo 内部表述张力，无数据指向"])

    messages = orch._build_feedback_inquiry_messages(
        packet=SimpleNamespace(meta={}), layer_cards=cards, bridge_v1=bridge
    )
    gap = [
        m
        for m in messages
        if m.message_type == InquiryMessageType.ADJUDICATION_GAP and m.trigger.startswith("Bridge V1 unresolved_questions")
    ]
    assert gap == []


# ── #1①：层 payload 的深嵌套长列表走递归瘦身，短列表与聚合字段不动 ──


def test_layer_payload_deep_series_slimmed_short_lists_kept(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    rows = [
        {"data_date": f"20{16 + i // 12}-{i % 12 + 1:02d}-01", "vix": 13.0 + i}
        for i in range(24)
    ]
    payload = {
        "layer": "L2",
        "layer_raw_data": {
            "get_vix_term_structure": {
                "value": {"percentile_5y": 61.2, "nested": {"raw_series": rows}}
            }
        },
    }

    out = orch._sanitize_prompt_payload("l2_analyst", payload)
    slim = out["layer_raw_data"]["get_vix_term_structure"]["value"]["nested"]["raw_series"]
    assert isinstance(slim, dict) and slim.get("_prompt_summary") is True
    assert slim["count"] == 24
    assert "chart_time_series" in slim["note"], "截断注记要指回可回查的 artifact"
    assert out["layer_raw_data"]["get_vix_term_structure"]["value"]["percentile_5y"] == 61.2

    payload2 = {"layer": "L2", "layer_raw_data": {"get_x": {"value": {"quarterly": [1, 2, 3, 4]}}}}
    out2 = orch._sanitize_prompt_payload("l2_analyst", payload2)
    assert out2["layer_raw_data"]["get_x"]["value"]["quarterly"] == [1, 2, 3, 4], "短列表是叙事信号，不得误伤"


def test_l4_direct_series_still_gets_numeric_summary(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    rows = [
        {"data_date": f"20{16 + i // 12}-{i % 12 + 1:02d}-01", "value": 100.0 + i}
        for i in range(24)
    ]
    payload = {
        "layer": "L4",
        "layer_raw_data": {"get_damodaran_monthly": {"value": {"monthly": rows}}},
    }

    out = orch._sanitize_prompt_payload("l4_analyst", payload)
    monthly = out["layer_raw_data"]["get_damodaran_monthly"]["value"]["monthly"]
    assert isinstance(monthly, dict) and monthly.get("count") == 24
    assert "numeric_summary" in monthly, "L4 现成统计摘要机制不得回退"


# ── #1②：governance 证据瘦身扩到 critic/risk ──


def _fat_synthesis() -> SynthesisPacket:
    fat_rows = [{"ticker": f"T{i:03d}", "spread_bp": 300 + i} for i in range(24)]
    return SynthesisPacket(
        evidence_index={
            "L2.get_hy_credit_spread#detail": {
                "metric_name": "hy_credit_spread",
                "field_value": fat_rows,
            }
        },
        high_severity_typed_conflicts=[
            TypedConflict(
                conflict_id="credit_tail_vs_equity",
                conflict_type="credit_transmission",
                severity="high",
                confidence="medium",
                description="尾部信用走阔与股指平稳冲突。",
                mechanism="融资成本上行侵蚀安全垫。",
                implication="保留信用约束。",
                involved_layers=["L2"],
                evidence_refs=["L2.get_hy_credit_spread#detail"],
                falsifiers=["利差回落至均值"],
            )
        ],
    )


def _minimal_thesis() -> ThesisDraft:
    return ThesisDraft(
        main_thesis="中性。",
        environment_assessment="宏观中性。",
        valuation_assessment="估值中性。",
        timing_assessment="趋势中性。",
        overall_confidence=Confidence.MEDIUM,
        dependencies=[],
    )


def test_governance_key_evidence_refs_slimmed_for_critic_and_risk(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    synthesis = _fat_synthesis()
    thesis = _minimal_thesis()
    ref = "L2.get_hy_credit_spread#detail"

    gov_critic = orch._build_governance_input_packet(
        synthesis_packet=synthesis, thesis=thesis, consumer="critic"
    )
    fv = gov_critic.key_evidence_refs[ref]["field_value"]
    assert isinstance(fv, dict) and fv.get("_prompt_summary") is True and fv["count"] == 24

    gov_risk = orch._build_governance_input_packet(
        synthesis_packet=synthesis, thesis=thesis, consumer="risk"
    )
    assert ref in gov_risk.key_evidence_refs, "论证盲分料仍要给冲突面证据，只是瘦身"
    rv = gov_risk.key_evidence_refs[ref]["field_value"]
    assert isinstance(rv, dict) and rv.get("_prompt_summary") is True


def test_governance_key_evidence_refs_slimming_keeps_ref_keys(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    gov = orch._build_governance_input_packet(
        synthesis_packet=_fat_synthesis(), thesis=_minimal_thesis(), consumer="critic"
    )
    assert "L2.get_hy_credit_spread#detail" in gov.key_evidence_refs, "ref key 集合不动，引用合法性不受影响"


def test_layer_match_ignores_stage_name_tokens(tmp_path: Path):
    """纯英文站名 token（thesis/critic/risk）不得当题词——每张卡的 JSON 里都有，会五层全中。"""
    orch = _orchestrator(tmp_path)
    cards = [
        _card(Layer.L1, "实际利率处于十年高位，期货定价偏紧"),
        _card(Layer.L2, "高收益利差走阔至极值，尾部信用收缩"),
    ]
    bridge = SimpleNamespace(unresolved_questions=["纯程序事项：需要 Thesis/Critic/Risk 界定复核窗口"])
    messages = orch._build_feedback_inquiry_messages(
        packet=SimpleNamespace(meta={}), layer_cards=cards, bridge_v1=bridge
    )
    gap = [
        m
        for m in messages
        if m.message_type == InquiryMessageType.ADJUDICATION_GAP and m.trigger.startswith("Bridge V1 unresolved_questions")
    ]
    assert gap == [], "站名 token 与语法碎片不得触发派单"


def test_matched_refs_use_plain_layer_labels(tmp_path: Path):
    """枚举层名必须取值（L2）而非 repr（Layer.L2）——live 实测的文件路径 bug。"""
    orch = _orchestrator(tmp_path)
    cards = [_card(Layer.L2, "高收益利差走阔至极值，尾部信用收缩")]
    bridge = SimpleNamespace(unresolved_questions=["高收益利差走阔是特质性再融资还是系统性收缩——用信用数据裁决"])
    messages = orch._build_feedback_inquiry_messages(
        packet=SimpleNamespace(meta={}), layer_cards=cards, bridge_v1=bridge
    )
    refs = [r for m in messages for r in (m.allowed_context_refs or [])]
    assert refs, "应命中 L2 卡并派单"
    assert all(not r.startswith("layer_cards/Layer.") for r in refs), "refs 不得含枚举 repr 前缀"
    assert "layer_cards/L2.json" in refs
