from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts"


def _prompt_markdown_files():
    return sorted(path for path in PROMPT_DIR.rglob("*.md") if path.is_file())


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


def test_risk_and_final_prompts_do_not_teach_unsupported_numeric_impact_ranges():
    banned_fragments = [
        "下跌 20%+",
        "20%+",
        "5-10%",
        "3-5%",
        "25 倍以下",
        "增速 <10%",
        "增速降至 10% 以下",
    ]

    offenders = []
    for name in ["risk_sentinel.md", "final_adjudicator.md"]:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        for fragment in banned_fragments:
            if fragment in text:
                offenders.append(f"{name}: {fragment}")

    assert not offenders


def test_risk_and_final_prompts_explicitly_ban_unsupported_numeric_impacts():
    required = "不得编造点位、跌幅、估值倍数、盈利增速阈值或其他定量影响幅度"
    for name in ["risk_sentinel.md", "final_adjudicator.md"]:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        assert required in text


def test_decision_prompts_do_not_teach_reusable_stance_templates():
    banned_fragments = [
        "中性偏谨慎",
        "高风险高赔率候选",
        "这不是低风险环境，但可能是高风险高赔率候选",
        "核心仓守纪律，战术仓分批",
        "建议等待更好的入场时机",
        "等待估值回调或广度改善",
    ]

    offenders = []
    for path in _prompt_markdown_files():
        text = path.read_text(encoding="utf-8")
        for fragment in banned_fragments:
            if fragment in text:
                offenders.append(f"{path.relative_to(PROMPT_DIR)}: {fragment}")

    assert not offenders


def test_decision_prompts_require_symmetric_payoff_burden():
    # 2026-07-12 起废除单向"高赔率"合取门（它与永久性盈利数据缺口合谋，使建设性
    # 结论在结构上不可能出现）；改锁双向对称举证 + 姿态中立不变量。
    for name in ["thesis_builder.md", "final_adjudicator.md"]:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        assert "不得照抄" in text
        assert "两个方向都不允许一票定论" in text
        assert "不允许默认落到" in text
        assert "当默认安全答案" in text
        assert "并列出仍然反对的类别" in text
        assert "并列出仍然相反的类别" in text


def test_l4_prompt_requires_data_authority_metadata_for_valuation():
    text = (PROMPT_DIR / "l4_analyst.md").read_text(encoding="utf-8")
    required_fragments = [
        "source_tier",
        "data_date",
        "collected_at_utc",
        "update_frequency",
        "coverage",
        "fallback_chain",
        "source_disagreement",
        "Wind 是可选高信任输入",
    ]

    for fragment in required_fragments:
        assert fragment in text


def test_l4_prompt_distinguishes_current_monthly_erp_stddev_context_and_true_percentile():
    text = (PROMPT_DIR / "l4_analyst.md").read_text(encoding="utf-8")
    required_fragments = [
        "monthly current ERP",
        "annual history fallback",
        "std-dev / z-score relative context",
        "不能把 WorldPERatio 的标准差区间、估值标签或回归提示写成 historical percentile",
        "不能把 histimpl.xls 年度历史表写成最新月度 ERP",
        "ERPbymonth.xlsx",
        "Damodaran US implied ERP historical percentile",
        "NDX PE/PB/Forward PE historical percentile",
        "damodaran_erp_percentile_5y",
        "damodaran_erp_percentile_10y",
        "damodaran_erp_historical_percentiles.windows",
        "insufficient_history",
        "unavailable",
    ]

    for fragment in required_fragments:
        assert fragment in text


def test_l4_prompt_does_not_interpret_unverified_wind_risk_premium_absolute_value():
    text = (PROMPT_DIR / "l4_analyst.md").read_text(encoding="utf-8")

    assert "绝对值无论高低都不能解释为补偿厚薄" in text
    assert "只能复述 provider label" in text
    assert "不得与 Damodaran ERP 或简式收益差距直接比较" in text
    assert "数据日、新鲜度、窗口、样本量和 0-100 尺度检查" in text
    assert "定义未核验的 provider label 不适用这条经济含义推断" in text
    assert "Wind NDX 风险溢价低或分位低" not in text
    assert "Wind NDX 风险溢价高或分位高" not in text


def test_mixed_field_payload_prompts_require_explicit_field_evidence_refs():
    prompt_requirements = {
        "l4_analyst.md": ["mixed-field payload", "L4.function_id#FieldName"],
        "cross_layer_bridge.md": ["mixed-field payload", "L4.function_id#FieldName"],
        "thesis_builder.md": ["mixed_field_authority=true", "L4.function_id#FieldName"],
        "final_adjudicator.md": ["mixed-field payload", "L4.function_id#FieldName"],
    }

    for name, fragments in prompt_requirements.items():
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        for fragment in fragments:
            assert fragment in text


def test_prompts_do_not_call_ndx_simple_yield_gap_low_erp():
    prompt_files = [
        "l1_analyst.md",
        "l2_analyst.md",
        "l3_analyst.md",
        "l4_analyst.md",
        "l5_analyst.md",
        "cross_layer_bridge.md",
        "thesis_builder.md",
        "critic.md",
        "risk_sentinel.md",
        "reviser.md",
        "final_adjudicator.md",
    ]
    banned_fragments = [
        "低 ERP",
        "NDX ERP",
        "ERP 为负",
        "负ERP",
        "负 ERP",
    ]

    offenders = []
    for name in prompt_files:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        for fragment in banned_fragments:
            if fragment in text:
                offenders.append(f"{name}: {fragment}")

    assert not offenders
