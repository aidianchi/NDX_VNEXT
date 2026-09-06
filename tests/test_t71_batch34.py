"""T71 第三、四批合并（体检 #5/#6/#8/#9/#10/#2）行为锁定测试。

每条对着体检实测病灶：
  #5  校验重试整套重发 29.2 万字符只补 1K 反馈；续跑覆盖失败留档（留痕丢失）
  #9  仅标题事件被 mainline 送进主链（91736ca4 零正文）
  #10 投影截断器把数字劈开（22.92→.92、155.18→5.18）
  #8  few-shot 示例字段与真实 payload 脱节（50ma/percentile_1y/trend/机制假设/死容器）
  #6  revision_claimed_fields 指令要求自报、代码却整体覆盖（死指令）
  #2  四站 payload 8-16 个恒空占位键（每站 ~2K schema 噪音）
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.context_spread import _numeric_span_at, _project_value
from agent_analysis.orchestrator import (
    VNextOrchestrator,
    _response_is_json_object,
)


def _orchestrator(tmp_path: Path) -> VNextOrchestrator:
    return VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
        max_node_retries=2,
    )


class _Tiny(BaseModel):
    a: int = 0


# ── #5 增量重试 ──


def _fake_engine(prompts, responses):
    class FakeEng:
        def call_with_fallback(self, prompt, **kwargs):
            prompts.append(prompt)
            return responses[len(prompts) - 1]

        def extract_json(self, text, stage):
            try:
                return json.loads(text)
            except Exception:
                return None

    return FakeEng()


def test_validation_retry_sends_incremental_prompt_for_json_object(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    prompts = []
    orch.llm_engine = _fake_engine(prompts, ['{"a": 1}', '{"a": 1}'])
    calls = {"n": 0}

    def validator(_obj):
        calls["n"] += 1
        return [] if calls["n"] > 1 else ["形状不对：b 应为列表"]

    orch._run_stage(
        stage_key="critic",
        stage_name="critic",
        model_cls=_Tiny,
        payload={"governance_input": {"payload_marker": "ORIGINAL_CONTEXT"}},
        validator=validator,
    )

    assert len(prompts) == 2
    assert "上一次输出原文" in prompts[1], "形状类校验失败：重试只发上次输出+错误"
    assert "ORIGINAL_CONTEXT" not in prompts[1], "全量材料不得随重试再发"
    assert "ORIGINAL_CONTEXT" in prompts[0]


def test_parse_failure_retry_still_sends_full_prompt(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    prompts = []
    orch.llm_engine = _fake_engine(prompts, ["完全不是 JSON 的垃圾", '{"a": 1}'])
    calls = {"n": 0}

    def validator(_obj):
        return []

    orch._run_stage(
        stage_key="critic",
        stage_name="critic",
        model_cls=_Tiny,
        payload={"governance_input": {"payload_marker": "ORIGINAL_CONTEXT"}},
        validator=validator,
    )

    assert len(prompts) == 2
    assert "上一次输出原文" not in prompts[1], "解析失败（没有可用 JSON）必须走全量重发"
    assert "ORIGINAL_CONTEXT" in prompts[1]


def test_missing_field_error_keeps_full_prompt(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    prompts = []
    orch.llm_engine = _fake_engine(prompts, ['{"a": 1}', '{"a": 1}'])
    calls = {"n": 0}

    def validator(_obj):
        calls["n"] += 1
        return [] if calls["n"] > 1 else ["missing required field: b"]

    orch._run_stage(
        stage_key="critic",
        stage_name="critic",
        model_cls=_Tiny,
        payload={"governance_input": {"payload_marker": "ORIGINAL_CONTEXT"}},
        validator=validator,
    )

    assert len(prompts) == 2
    assert "上一次输出原文" not in prompts[1], "缺字段需要重读材料补内容，必须走全量重发"


def test_response_is_json_object_helper():
    assert _response_is_json_object('{"a": 1}')
    assert _response_is_json_object('```json\n{"a": 1}\n```')
    assert not _response_is_json_object("前置说明 {\"a\": 1}")
    assert not _response_is_json_object('{"a": 1}{"b": 2}')
    assert not _response_is_json_object("")
    assert not _response_is_json_object("null")


# ── #5 留痕：审计文件写前归档 ──


def test_prompt_audit_archives_existing_attempt_files(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    stage_dir = orch._prompt_audit_stage_dir("critic")
    stage_dir.mkdir(parents=True, exist_ok=True)
    old_file = stage_dir / "attempt_1.response.raw.txt"
    old_file.write_text("上一轮失败的原始响应", encoding="utf-8")

    orch._save_prompt_audit_text("critic", "attempt_1.response.raw.txt", "本轮新响应")

    assert (stage_dir / "attempt_1.response.raw.txt").read_text(encoding="utf-8") == "本轮新响应"
    archived = list((stage_dir / "archived").glob("*_attempt_1.response.raw.txt"))
    assert len(archived) == 1
    assert "上一轮失败的原始响应" in archived[0].read_text(encoding="utf-8"), "被覆盖的失败留档必须可回查"


# ── #9 仅标题事件不给 mainline 席位 ──


def test_title_only_event_rejected_from_mainline(tmp_path: Path):
    orch = _orchestrator(tmp_path)
    (tmp_path / "event_mechanism_report.json").write_text(
        json.dumps(
            {
                "mainlines": [
                    {"mainline_id": "m_healthy", "news_card_ids": ["event:e1"]},
                    {"mainline_id": "m_titleonly", "news_card_ids": ["event:e2"]},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "news_event_ledger.json").write_text(
        json.dumps(
            {
                "events": [
                    {"event_id": "event:e1", "raw_text_available": True},
                    {"event_id": "event:e2", "raw_text_available": False},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    selected = orch._select_event_card_candidates(effective_date="2026-09-05", feedback_messages=[])

    by_id = {e.get("event_id"): e for e in selected}
    assert "event:e1" in by_id and "mainline" in by_id["event:e1"]["trigger_reasons"]
    assert "event:e2" not in by_id, "零正文（仅标题）事件不得经 mainline 进主链"


# ── #10 投影截断器数字边界 ──


def test_project_value_never_splits_numbers():
    # 头窗切点（120）落在 22.92 中间；尾窗切点（len-60）落在 155.18 中间
    text = "前" * 119 + "22.92" + "中" * 100 + "155.18" + "后" * 57
    out = _project_value(text)
    assert "22.92" in out, "头窗切点不得劈开数字（22.92 残留 .92 是实测病灶）"
    assert "155.18" in out, "尾窗切点不得劈开数字（155.18 残留 5.18 是实测病灶）"


def test_numeric_span_at_finds_number_span():
    text = "读数为 22.92，后续"
    span = _numeric_span_at(text, 7)  # 切在 22.92 中间
    assert span == (4, 9), "切点落在数字中间必须返回完整数字跨度"
    assert _numeric_span_at(text, 2) is None, "切点不在数字上返回 None"


# ── #8 / #6 提示词与示例的内容契约 ──

PROMPT_DIR = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"
EXAMPLES = Path(__file__).resolve().parents[1] / "src" / "prompt_examples.py"


def test_examples_match_real_payload_schema():
    ex = EXAMPLES.read_text(encoding="utf-8")
    assert "percent_above_50ma" not in ex, "真实契约是 percent_above_50d/200d（tools_L3）"
    assert "percent_above_50d" in ex
    assert '"level": 8.4, "trend": "rising", "percentile_1y": 78.0' not in ex, "ATR 示例教了运行时不存在字段"
    assert "stop_loss_2_5x" in ex, "ATR 示例必须对齐真实形状（level/stop_loss_2_5x/date）"


def test_l4_dead_container_instruction_removed():
    l4 = (PROMPT_DIR / "l4_analyst.md").read_text(encoding="utf-8")
    assert "RejectedMetrics" not in l4, "容器在本 run 数据端从未产出（0 次），条件指令是死指令"


def test_section_summary_card_fields_match_reality():
    ss = (PROMPT_DIR / "event_section_summary.md").read_text(encoding="utf-8")
    assert "机制假设" not in ss, "小结输入卡 12 字段里没有机制假设（实测）"
    assert "局限说明" in ss


def test_reviser_claimed_fields_instruction_removed():
    rev = (PROMPT_DIR / "reviser.md").read_text(encoding="utf-8")
    assert "同时填写 `revision_claimed_fields`" not in rev, "模型自报会被代码 diff 整体覆盖（实测 23 项覆盖 17 项）"
    assert "不用你填" in rev and "revision_claimed_fields" in rev, "保留「代码装配」的说明"


# ── #2 治理站空字段剪枝 ──


def test_sanitize_prunes_empty_governance_keys_for_governance_stages():
    orch = _orchestrator(tmp_path=Path(os.environ.get("TMPDIR", "/tmp")) / "t71_unused_prune")
    payload = {
        "governance_input": {
            "fact_card": [],
            "must_preserve_risks": ["风险一"],
            "schema_passed": True,
            "evidence_registry_summary": {},
            "note": "",
        }
    }
    out = orch._sanitize_prompt_payload("critic", payload)
    gi = out["governance_input"]
    assert "fact_card" not in gi and "evidence_registry_summary" not in gi and "note" not in gi
    assert gi["must_preserve_risks"] == ["风险一"], "非空键一律不动"
    assert gi["schema_passed"] is True, "布尔 False/True 不算空"


def test_sanitize_keeps_non_governance_payloads_untouched():
    orch = _orchestrator(tmp_path=Path(os.environ.get("TMPDIR", "/tmp")) / "t71_unused_prune2")
    payload = {"layer": "L2", "layer_raw_data": {}, "other": {"empty_list": []}}
    out = orch._sanitize_prompt_payload("l2_analyst", payload)
    assert out["other"] == {"empty_list": []}, "剪枝只作用于 governance_input，别处不越界"


def test_reasoned_verdict_renders_markdown_bold():
    """09-06 老板实测：终审叙事的 **理由一…** 星号原样上页面。渲染层必须转 <strong>。"""
    from agent_analysis.vnext_reporter import _inline_emphasis_html
    html = _inline_emphasis_html('<p>**理由一：钱贵。** 实际利率处十年 99 分位。</p>')
    assert "<strong>理由一：钱贵。</strong>" in html
    assert "**" not in html
