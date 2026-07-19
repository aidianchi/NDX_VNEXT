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
    LongTermAssessment,
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


def test_direct_construction_still_rejects_numeric_percent_without_refs():
    with pytest.raises(Exception, match="numeric percent requires evidence_refs"):
        LongTermAssessment(
            object_quality="结构质量待观察",
            valuation_implied_return="长期年化回报可能为 8%",
            evidence_refs=[" "],
        )

    accepted = _final(long_term_assessment={
        "object_quality": "结构质量待观察",
        "valuation_implied_return": "长期年化回报可能为 8%",
        "evidence_refs": ["L4.get_example"],
    })
    assert accepted.long_term_assessment is not None
    assert "8%" in accepted.long_term_assessment.valuation_implied_return


def test_llm_boundary_degrades_percent_without_refs_instead_of_failing_run():
    # 真实事故回归样本：run 20260719_130534 final_adjudicator attempt 2 的原文——
    # 百分比是输入事实（PE 分位、10Y 收益率）而非编造年化，但缺 refs 曾炸掉整次 run。
    final = _final(long_term_assessment={
        "object_quality": "NDX成分股科技属性强，盈利能力和护城河深厚，但当前集中度极高（前10权重46%），头部风险突出。",
        "earnings_compounding": "M7资本开支加速指向AI基础设施投入扩大，但盈利转化路径未证实。",
        "valuation_implied_return": "当前PE 35.38（71%分位）与10Y名义4.57%的组合暗示长期回报边界受压，简式收益差距为负，安全垫不足。",
        "permanent_loss_hypotheses": ["利率持续高位导致估值永久性下移，即使盈利增长，PE收缩抵消回报。"],
    })
    assessment = final.long_term_assessment
    assert assessment is not None
    assert assessment.valuation_implied_return == ""
    assert any("原文含百分比数字但未附可追溯 evidence_refs" in note for note in assessment.uncertainty_notes)
    assert "护城河深厚" in assessment.object_quality
    assert assessment.permanent_loss_hypotheses


def test_llm_boundary_coerces_structured_hypotheses_to_sentences():
    # 真实事故回归样本：attempt 1 按提示词"注明证据状态"合法产出结构体，曾被 List[str] 拒收。
    final = _final(long_term_assessment={
        "object_quality": "结构质量待观察",
        "permanent_loss_hypotheses": [
            {
                "hypothesis": "利率长期维持高位导致NDX估值中枢结构性下移",
                "evidence_status": "有支持：实际利率处于近10年顶尖分位。",
            },
            "集中度崩塌导致指数长期表现弱于等权。",
            {"其他": "无主键结构体也不丢内容"},
        ],
        "evidence_refs": ["L4.get_example"],
    })
    hypotheses = final.long_term_assessment.permanent_loss_hypotheses
    assert hypotheses[0] == "利率长期维持高位导致NDX估值中枢结构性下移（证据状态：有支持：实际利率处于近10年顶尖分位。）"
    assert hypotheses[1] == "集中度崩塌导致指数长期表现弱于等权。"
    assert hypotheses[2] == "其他: 无主键结构体也不丢内容"


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
