"""E1 P0: final_stance claim gate — missing/unavailable evidence must only be
mapped to reduced confidence and data-boundary notes, never to a direction
(bullish or bearish). This is a reasoning defect, not a data gap, and it does
not go away once the missing data shows up later.

Real accident sentence (output/analysis/vnext/20260719_130534/run_summary.json
final_stance): "盈利证据缺失放大下行风险" — "missing evidence" is used, in the
same sentence, as the reason risk is "amplified". That must be intercepted
even when the missing-evidence phrase and the amplify/risk phrase sit in
separated clauses ("盈利证据缺失，同时高估值放大下行风险"), while genuine
counterfactual/conditional sentences ("若数据补齐后风险仍放大") must not be
flagged.
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


def test_real_accident_sentence_is_rejected():
    """The exact final_stance text from the 20260719_130534 run must be
    intercepted, not just a paraphrase of it."""
    with pytest.raises(Exception) as excinfo:
        _final(final_stance=_REAL_ACCIDENT_SENTENCE)
    assert "final_stance_claim_gate" in str(excinfo.value)


def test_real_accident_archive_no_longer_replays_cleanly():
    """The archived run that produced the real accident sentence must now
    fail replay through the same contract it was originally saved under —
    the claim gate applies retroactively to any FinalAdjudication.model_validate
    call, including checkpoint/resume reloads of a stale artifact."""
    if not _REAL_ACCIDENT_ARCHIVE.exists():
        pytest.skip("archived run not present in this checkout")
    data = json.loads(_REAL_ACCIDENT_ARCHIVE.read_text(encoding="utf-8"))
    assert data.get("final_stance") == _REAL_ACCIDENT_SENTENCE
    with pytest.raises(Exception) as excinfo:
        FinalAdjudication.model_validate(data)
    assert "final_stance_claim_gate" in str(excinfo.value)


def test_separated_clause_variant_is_rejected():
    """Must not be adjacent-word matching only: the missing-evidence phrase
    and the amplify/risk phrase can sit in different comma-separated clauses
    of the same sentence and still must be caught."""
    with pytest.raises(Exception) as excinfo:
        _final(final_stance="盈利证据缺失，同时高估值放大下行风险。")
    assert "final_stance_claim_gate" in str(excinfo.value)


@pytest.mark.parametrize(
    "text",
    [
        "缺乏数据支持的情况下，估值压力依然放大了上行风险。",
        "没有数据确认盈利拐点，信用利差扩大加剧下行风险。",
    ],
)
def test_other_missing_evidence_and_amplify_risk_phrasings_are_rejected(text):
    with pytest.raises(Exception) as excinfo:
        _final(final_stance=text)
    assert "final_stance_claim_gate" in str(excinfo.value)


def test_counterfactual_sentence_is_not_flagged():
    """"若/如果/一旦…缺口补齐后风险仍会放大" describes a hypothetical, not a
    claim that today's missing evidence itself sets the direction — must not
    be misfired on."""
    final = _final(final_stance="若盈利证据缺失后续补齐，下行风险仍可能放大，需要持续验证。")
    assert final.final_stance.startswith("若盈利证据缺失")


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


def test_benign_sentence_without_trigger_words_passes():
    final = _final(final_stance="赔率中性，静待信号明朗后再决定仓位方向。")
    assert final.final_stance


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
