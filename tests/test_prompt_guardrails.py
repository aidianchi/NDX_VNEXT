from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"


def test_governance_prompts_do_not_teach_unsupported_historical_probabilities():
    prompt_files = [
        "cross_layer_bridge.md",
        "thesis_builder.md",
        "critic.md",
        "risk_sentinel.md",
        "final_adjudicator.md",
    ]
    banned_phrases = [
        "历史上类似",
        "负收益概率",
        "回调概率",
        "样本：",
        "样本:",
        "平均收益 -",
        ">70%",
        "> 70%",
    ]

    offenders = []
    for name in prompt_files:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        for phrase in banned_phrases:
            if phrase in text:
                offenders.append(f"{name}: {phrase}")

    assert not offenders


def test_risk_and_final_prompts_explicitly_ban_fabricated_backtest_statistics():
    for name in ["risk_sentinel.md", "final_adjudicator.md"]:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        assert "不得编造历史胜率、回测收益、样本区间或概率数字" in text
        assert "除非输入 evidence_refs 明确提供这类统计" in text
