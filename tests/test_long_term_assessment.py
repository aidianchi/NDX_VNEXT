"""W3: long-term asset assessment stays separate from cyclical posture."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_analysis.contracts import (  # noqa: E402
    ApprovalStatus,
    Confidence,
    FinalAdjudication,
)
from agent_analysis.vnext_reporter import VNextReportGenerator  # noqa: E402


def _final(**overrides):
    payload = {
        "approval_status": ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        "final_stance": "测试姿态",
        "confidence": Confidence.MEDIUM,
        "must_preserve_risks": ["测试风险"],
        "adjudicator_notes": "测试说明",
    }
    payload.update(overrides)
    return FinalAdjudication(**payload)


def test_numeric_percent_implied_return_requires_evidence_refs():
    with pytest.raises(Exception, match="numeric percent requires evidence_refs"):
        _final(long_term_assessment={
            "object_quality": "结构质量待观察",
            "valuation_implied_return": "长期年化回报可能为 8%",
            "evidence_refs": [" "],
        })

    accepted = _final(long_term_assessment={
        "object_quality": "结构质量待观察",
        "valuation_implied_return": "长期年化回报可能为 8%",
        "evidence_refs": ["L4.get_example"],
    })
    assert accepted.long_term_assessment is not None


def test_all_empty_long_term_fields_normalize_to_none():
    final = _final(long_term_assessment={
        "object_quality": " ",
        "earnings_compounding": "",
        "valuation_implied_return": "",
        "permanent_loss_hypotheses": [],
        "evidence_refs": ["L4.get_example"],
        "uncertainty_notes": ["只有说明，不构成评估"],
    })
    assert final.long_term_assessment is None


def test_prompt_contains_fable_long_term_block_verbatim():
    prompt = (
        Path(__file__).resolve().parents[1]
        / "src" / "agent_analysis" / "prompts" / "final_adjudicator.md"
    ).read_text(encoding="utf-8")
    expected = '''## 长期资产评估（3-5 年以上，独立于周期姿态）

- `long_term_assessment` 与 `time_horizon_views` 回答不同的问题：后者是周期判断（最长 6-12 个月），前者回答"这笔资产本身值不值得长期持有"。二者不得互相推导：周期姿态谨慎不自动等于长期不值得持有，反之亦然。
- `object_quality`：判断对象的结构性质（集中度、成分质量、盈利能力），只用输入 refs。
- `earnings_compounding`：盈利与自由现金流的复利证据（资本开支转化、回购执行、盈利预期方向），只用输入 refs。
- `valuation_implied_return`：当前估值分位隐含的长期回报边界；只许引用输入的估值分位与收益率差 refs，禁止给出具体年化收益数字，除非输入 refs 明确提供。
- `permanent_loss_hypotheses`：会造成永久性资本损失（而非波动）的假说清单，每条注明当前证据状态（有支持／无证据／被反驳）。
- 核心仓（core_position）的任何加减动作建议，必须注明"须经个人投资政策书与再平衡带确认"；系统不得代替政策书给出具体金额或比例。
- 不确定就写不确定；输入证据不足以支撑某字段时写明缺什么，不许硬编。'''
    assert expected in prompt


def test_reporter_renders_long_term_section_and_core_policy_guard(tmp_path: Path):
    generator = VNextReportGenerator(reports_dir="/tmp/w3_long_term")
    final = _final(
        long_term_assessment={
            "object_quality": "成分质量高但集中度需要持续审视。",
            "earnings_compounding": "盈利与现金流转化仍需后续证据。",
            "valuation_implied_return": "当前分位约束长期回报上界。",
            "permanent_loss_hypotheses": ["集中度失效：无证据"],
            "evidence_refs": ["L4.get_example"],
            "uncertainty_notes": ["缺少完整周期样本"],
        },
        portfolio_actions=[{
            "bucket": "core_position",
            "action": "维持",
            "rationale": "长期框架未变",
            "conditions": ["等待再平衡窗口"],
        }],
    ).model_dump(mode="json")

    html = generator._decision_section({"final_adjudication": final, "thesis_draft": {}})
    actions_html = generator._actions_section({"final_adjudication": final, "risk_boundary_report": {}})
    assert "长期资产评估（3-5 年以上）" in html
    assert "成分质量高但集中度需要持续审视" in html
    assert "集中度失效：无证据" in html
    assert "核心仓动作须经个人投资政策书与再平衡带确认" in html
    assert "核心仓动作须经个人投资政策书与再平衡带确认" in actions_html

    artifacts = {"final_adjudication": final, "thesis_draft": {}}
    brief_html = generator._main_sections("brief", tmp_path, artifacts, final, "{}")
    assert "长期资产评估（3-5 年以上）" in brief_html
    assert "成分质量高但集中度需要持续审视" in brief_html


def test_reporter_omits_long_term_section_when_absent(tmp_path: Path):
    generator = VNextReportGenerator(reports_dir="/tmp/w3_long_term_missing")
    final = _final().model_dump(mode="json")
    html = generator._decision_section({"final_adjudication": final, "thesis_draft": {}})
    assert "长期资产评估（3-5 年以上）" not in html
    brief_html = generator._main_sections(
        "brief", tmp_path, {"final_adjudication": final, "thesis_draft": {}}, final, "{}"
    )
    assert "长期资产评估（3-5 年以上）" not in brief_html
