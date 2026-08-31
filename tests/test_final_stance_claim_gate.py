"""E1 P0: final_stance claim gate — missing/unavailable evidence must only be
mapped to reduced confidence and data-boundary notes, never to a direction
(bullish or bearish). This is a reasoning defect, not a data gap, and it does
not go away once the missing data shows up later.

Real accident sentence (output/analysis/vnext/20260719_130534/run_summary.json
final_stance): "盈利证据缺失放大下行风险" — "missing evidence" is used, in the
same sentence, as the reason risk is "amplified".

2026-08-31 T69 P1-6（闸门宪法 v2）：运行时拦截降级为留痕不拦。句法共现
（"缺失"与"放大…风险"同从句）是语义判断，超出闸门职权；且 raise 会连带
checkpoint 复验把旧产物整份作废。现命中只往 quality_gate.notes 记
"final_stance_claim_gate suspect"留痕，不再 raise、不再触发重试、不再拦截
checkpoint 复用；提示词侧原则条款（"缺失证据不得定方向"）保留，检测函数
_missing_evidence_as_direction_claim 保留作事后审计探测器。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_analysis.contracts import (  # noqa: E402
    ApprovalStatus,
    Confidence,
    FinalAdjudication,
    _missing_evidence_as_direction_claim,
)

_REAL_ACCIDENT_ARCHIVE = (
    Path(__file__).resolve().parents[1]
    / "output" / "analysis" / "vnext" / "20260719_130534" / "final_adjudication.json"
)

_REAL_ACCIDENT_SENTENCE = (
    "赔率不利：高实际利率与高估值形成估值压缩主矛盾，"
    "盈利证据缺失放大下行风险，信用尾部压力未充分定价，风险收益比偏向防守。"
)


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


def _claim_gate_notes(final) -> str:
    return final.quality_gate.notes if final.quality_gate is not None else ""


def test_real_accident_sentence_is_traced_not_rejected():
    """T69 P1-6 反向锁定：20260719_130534 run 的真实事故原句不再被拒——
    构造成功、字段原样保留，命中记进 quality_gate.notes 留痕。"""
    final = _final(final_stance=_REAL_ACCIDENT_SENTENCE)
    assert final.final_stance == _REAL_ACCIDENT_SENTENCE
    assert "final_stance_claim_gate" in _claim_gate_notes(final)


def test_real_accident_archive_replays_with_trace_not_rejection():
    """The archived run that produced the real accident sentence replays through
    the same contract it was originally saved under — T69 P1-6 后 claim gate
    不再 raise，checkpoint/resume 对旧产物重新 model_validate 不再因此作废，
    但留痕必须出现（事后审计的入口）。"""
    if not _REAL_ACCIDENT_ARCHIVE.exists():
        pytest.skip("archived run not present in this checkout")
    data = json.loads(_REAL_ACCIDENT_ARCHIVE.read_text(encoding="utf-8"))
    assert data.get("final_stance") == _REAL_ACCIDENT_SENTENCE
    final = FinalAdjudication.model_validate(data)
    assert final.final_stance == _REAL_ACCIDENT_SENTENCE
    assert "final_stance_claim_gate" in _claim_gate_notes(final)


def test_separated_clause_variant_is_traced_not_rejected():
    """隔从句写法（"盈利证据缺失，同时高估值放大下行风险"）仍然命中探测器，
    但只留痕不拦。"""
    final = _final(final_stance="盈利证据缺失，同时高估值放大下行风险。")
    assert "final_stance_claim_gate" in _claim_gate_notes(final)


@pytest.mark.parametrize(
    "text",
    [
        "缺乏数据支持的情况下，估值压力依然放大了上行风险。",
        "没有数据确认盈利拐点，信用利差扩大加剧下行风险。",
    ],
)
def test_other_missing_evidence_and_amplify_risk_phrasings_are_traced_not_rejected(text):
    final = _final(final_stance=text)
    assert final.final_stance == text
    assert "final_stance_claim_gate" in _claim_gate_notes(final)


def test_counterfactual_sentence_is_not_flagged():
    """"若/如果/一旦…缺口补齐后风险仍会放大" describes a hypothetical, not a
    claim that today's missing evidence itself sets the direction — must not
    be misfired on (探测器不命中，自然也无留痕)."""
    final = _final(final_stance="若盈利证据缺失后续补齐，下行风险仍可能放大，需要持续验证。")
    assert final.final_stance.startswith("若盈利证据缺失")
    assert "final_stance_claim_gate" not in _claim_gate_notes(final)


def test_semicolon_separated_unrelated_points_are_not_flagged():
    """A long sentence can legitimately discuss several independent risk
    points separated by Chinese semicolons; a missing-evidence phrase in one
    clause and an unrelated amplify/risk phrase in a different
    semicolon-separated clause must not be treated as one causal claim."""
    final = _final(
        payoff_assessment=(
            "赔率偏下行：风险补偿不足，估值和利率环境不支持核心仓进攻；"
            "战术仓虽有边际改善但缺乏安全边际和确认信号，且广度、趋势强度均弱；"
            "信用尾部压力若扩散将急剧恶化赔率。"
        )
    )
    assert "缺乏" in final.payoff_assessment
    assert "final_stance_claim_gate" not in _claim_gate_notes(final)


def test_benign_sentence_without_trigger_words_passes():
    final = _final(final_stance="赔率中性，静待信号明朗后再决定仓位方向。")
    assert final.final_stance
    assert "final_stance_claim_gate" not in _claim_gate_notes(final)


def test_prompt_states_missing_evidence_must_not_set_direction():
    prompt = (
        Path(__file__).resolve().parents[1]
        / "src" / "agent_analysis" / "prompts" / "final_adjudicator.md"
    ).read_text(encoding="utf-8")
    assert "缺失证据不得定方向" in prompt
    assert "永远不能写成看多或看空的理由" in prompt


def test_missing_evidence_direction_claim_helper_returns_offending_sentence():
    """Direct unit coverage of the detector so failures are debuggable without
    constructing a full FinalAdjudication."""
    hit = _missing_evidence_as_direction_claim(_REAL_ACCIDENT_SENTENCE)
    assert hit is not None
    assert "缺失" in hit and "放大" in hit

    assert _missing_evidence_as_direction_claim("若数据补齐后风险仍放大。") is None
    assert _missing_evidence_as_direction_claim("赔率中性，静待信号明朗。") is None
