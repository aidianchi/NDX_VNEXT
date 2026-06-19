import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.vnext_reporter import (
    VNextReportGenerator,
    _label,
    _slug,
)
from agent_analysis.prompt_inspector import PromptInspectorGenerator


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_vnext_reporter_news_section_shows_event_data_links():
    reporter = VNextReportGenerator()

    html = reporter._news_section(
        {
            "news_event_ledger": {
                "events": [
                    {
                        "event_id": "event:fomc",
                        "title": "Federal Reserve issues FOMC statement",
                        "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                        "source_tier": "official_macro",
                        "layers": ["L1", "L4"],
                        "symbols": [],
                        "notes": "Official RSS item; treat as catalyst/background only.",
                    }
                ],
                "source_errors": [],
            },
            "news_event_data_links": {
                "links": [
                    {
                        "event_id": "event:fomc",
                        "observations": [
                            {
                                "series_key": "QQQ_OHLCV",
                                "series_label": "QQQ",
                                "statement": "QQQ 在事件日前后 +/-5 天窗口内从 450 变为 468。",
                                "needs_bridge_review": True,
                            }
                        ],
                    }
                ]
            },
            "news_layer_analysis": {
                "aggregate_analysis": {
                    "market_state_zh": "综合看来，新闻背景更偏向利率和政策预期敏感。",
                    "equity_fragility_zh": "若新闻同时对应利率上行和波动率上升，股市脆弱性会增加。",
                    "rate_pressure_zh": "涉及美联储的数据会改变降息/加息预期。",
                    "oil_pressure_zh": "本次新闻连接器尚未接入油价序列。",
                    "dominant_pressure_channels": ["利率预期", "风险溢价上升"],
                },
                "event_summaries": [
                    {
                        "event_id": "event:fomc",
                        "summary_zh": "这是一条来自美联储的政策事件。",
                        "possible_equity_impact_zh": "可能通过利率预期影响股市。",
                        "pressure_channels": ["利率预期"],
                    }
                ],
                "source_boundary": "本新闻层只基于官方事件标题和市场序列观察生成。",
            },
        }
    )

    assert "新闻中文概要、股市影响与市场连接观察" in html
    assert "新闻层总分析" in html
    assert "可能对股市的影响" in html
    assert "附近市场序列观察" in html
    assert "QQQ 在事件日前后" in html
    assert "不是因果证明，也不是 evidence_ref" in html


def test_vnext_reporter_generates_native_ui(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "final_adjudication.json",
        {
            "approval_status": "approved_with_reservations",
            "final_stance": "中性偏谨慎",
            "confidence": "medium",
            "key_support_chains": [
                {
                    "chain_description": "高实际利率压制估值",
                    "evidence_refs": ["L1.get_10y_real_rate", "L4.get_equity_risk_premium"],
                    "weight": 0.4,
                }
            ],
            "must_preserve_risks": ["估值压缩风险"],
            "adjudicator_notes": "保留核心冲突。",
            "evidence_refs": ["Risk report"],
            "state_diagnosis": "高风险但赔率可能改善。",
            "priced_narrative": "价格已反映部分坏消息。",
            "payoff_assessment": "高风险高赔率候选。",
            "time_horizon_views": [
                {
                    "horizon": "one_to_three_months",
                    "view": "赔率改善但趋势未确认。",
                    "action_implication": "战术仓分批。",
                    "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
                }
            ],
            "portfolio_actions": [
                {
                    "bucket": "tactical_position",
                    "action": "分批试探。",
                    "rationale": "等待确认有机会成本。",
                    "evidence_refs": ["L5.get_ta_indicators"],
                }
            ],
            "confirmation_cost": "等待全部确认可能错过主要反弹段。",
            "invalidation_conditions": ["信用继续恶化"],
            "reader_final": {
                "one_liner": "这不是低风险环境，但可能是高风险高赔率候选。",
                "three_reasons": [
                    "风险仍在。",
                    "估值已有压缩。",
                    "等待确认有机会成本。",
                ],
                "invalidation_summary": ["信用继续恶化"],
                "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
            },
            "token_usage": {
                "l1": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "bridge": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            },
        },
    )
    _write_json(
        run_dir / "context_brief.json",
        {
            "data_summary": "global brief",
            "layer_highlights": {
                "L1": ["global L1"],
                "L2": ["global L2"],
                "L3": ["global L3"],
                "L4": ["global L4"],
                "L5": ["global L5"],
            },
            "apparent_cross_layer_signals": ["global cross-layer signal"],
            "task_description": "global task",
        },
    )
    for layer in ["L1", "L2", "L3", "L4", "L5"]:
        _write_json(
            run_dir / "layer_context_briefs" / f"{layer}.json",
            {
                "data_summary": f"{layer} local brief",
                "layer_highlights": {layer: [f"{layer} local highlight"]},
                "apparent_cross_layer_signals": [],
                "task_description": f"{layer} local task",
            },
        )
    prompt_text = "## System Message\n系统约束\n\n## User Message\nObjectCanon\nIndicatorCanon\nPermissionType\nResponse Rules\nL1 runtime prompt"
    prompt_dir = run_dir / "prompt_audit" / "L1"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "attempt_1.prompt.txt").write_text(prompt_text, encoding="utf-8")
    _write_json(prompt_dir / "attempt_1.payload.json", {"payload": {"layer": "L1"}})
    (prompt_dir / "attempt_1.response.raw.txt").write_text('{"layer":"L1"}', encoding="utf-8")
    _write_json(prompt_dir / "output.validated.json", {"layer": "L1", "local_conclusion": "干净"})
    _write_json(
        prompt_dir / "meta.json",
        {
            "stage": "L1",
            "stage_name": "l1",
            "status": "ok",
            "prompt_chars": len(prompt_text),
            "prompt_sha256": __import__("hashlib").sha256(prompt_text.encode("utf-8")).hexdigest(),
            "prompt_file": "prompt_audit/L1/attempt_1.prompt.txt",
            "output_artifact": "layer_cards/L1.json",
            "attempts": 1,
        },
    )
    _write_json(
        run_dir / "run_summary.json",
        {"prompt_inspector": str(tmp_path / "reports" / "vnext_prompt_inspector_run.html")},
    )
    _write_json(
        run_dir / "llm_stage_diagnostics.json",
        {
            "stages": {
                "l1": {
                    "status": "ok",
                    "attempts": 1,
                    "prompt_chars": len(prompt_text),
                    "prompt_audit": {"stage_dir": "prompt_audit/L1"},
                }
            }
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {
            "packet_meta": {
                "data_date": "2026-04-23",
                "backtest_date": "2025-04-09",
                "indicator_total": 34,
                "indicator_successful": 34,
                "backtest_data_boundaries": [
                    {
                        "function_id": "get_ndx_forward_earnings_quality",
                        "reason": "latest-only source",
                        "future_upgrade": "historical source required",
                    }
                ],
                "strict_backtest_invariants": {
                    "hard_enforced": [
                        {
                            "invariant_id": "observation_dates_lte_effective_date",
                            "status": "enforced_by_data_integrity_gate",
                            "description": "dates are gated",
                        }
                    ],
                    "declared_limitations": [
                        {
                            "invariant_id": "alfred_first_vintage_not_enforced",
                            "status": "declared_limitation",
                            "future_upgrade": "ALFRED vintage required",
                        }
                    ],
                },
            },
            "objective_firewall_summary": {
                "object_clear": True,
                "authority_clear": True,
                "timing_clear": True,
                "cross_layer_verified": True,
                "strongest_falsifier": "盈利上修足以抵消折现率压力。",
                "unresolved_tensions": ["real_rate_vs_valuation: 高真实利率与高估值并存。"],
                "warnings": [],
            },
        },
    )
    _write_json(
        run_dir / "layer_cards" / "L1.json",
        {
            "layer": "L1",
            "local_conclusion": "宏观偏紧。",
            "confidence": "medium",
            "risk_flags": ["valuation_compression"],
            "layer_synthesis": "实际利率仍是主约束。",
            "internal_conflict_analysis": "净流动性改善与高实际利率冲突。",
            "cross_layer_hooks": [{"target_layer": "L4", "question": "估值是否已反映折现率压力？"}],
            "indicator_analyses": [
                {
                    "function_id": "get_10y_real_rate",
                    "metric": "10Y Real Rate",
                    "current_reading": "1.92%",
                    "normalized_state": "restrictive",
                    "narrative": "实际利率压制成长股估值。",
                    "reasoning_process": "实际利率上升 -> 折现率上升 -> 估值承压。",
                    "first_principles_chain": ["实际利率上升", "折现率上升", "估值承压"],
                    "cross_layer_implications": ["需要 L4 验证估值"],
                    "risk_flags": ["valuation_compression"],
                    "permission_type": "fact",
                    "canonical_question": "真实贴现率是否正在给 NDX 估值施压？",
                    "misread_guards": ["不是单纯的政策变量。"],
                    "cross_validation_targets": ["get_ndx_pe_and_earnings_yield"],
                    "falsifiers": ["盈利上修足以抵消折现率压力。"],
                    "core_vs_tactical_boundary": "核心框架指标。",
                }
            ],
        },
    )
    for layer in ["L2", "L3", "L4", "L5"]:
        _write_json(
            run_dir / "layer_cards" / f"{layer}.json",
            {
                "layer": layer,
                "local_conclusion": f"{layer} placeholder",
                "confidence": "medium",
                "layer_synthesis": f"{layer} synthesis",
                "internal_conflict_analysis": f"{layer} conflict",
                "indicator_analyses": [],
            },
        )
    _write_json(
        run_dir / "layer_cards" / "L4.json",
        {
            "layer": "L4",
            "local_conclusion": "估值偏高。",
            "confidence": "medium",
            "layer_synthesis": "估值需要盈利和利率共同验证。",
            "internal_conflict_analysis": "PE 与简式收益差距均提示安全边际偏薄。",
            "indicator_analyses": [
                {
                    "function_id": "get_ndx_pe_and_earnings_yield",
                    "metric": "NDX Valuation",
                    "current_reading": "PE 34.0",
                    "normalized_state": "expensive",
                    "narrative": "Trendonify 有历史分位，WorldPERatio 只做 PE 交叉校验。",
                    "reasoning_process": "真实历史分位优先；WorldPERatio rolling range 不当作分位。",
                    "first_principles_chain": ["PE", "historical percentile", "source disagreement"],
                    "cross_layer_implications": ["需要 L1 验证利率"],
                    "risk_flags": ["valuation_compression"],
                    "permission_type": "fact",
                    "canonical_question": "估值是否给未来回报留下安全边际？",
                },
                {
                    "function_id": "get_equity_risk_premium",
                    "metric": "NDX Simple Yield Gap",
                    "current_reading": "-0.75%",
                    "normalized_state": "thin_margin",
                    "narrative": "这是收益率与 10 年期美债的简式差距，不是 Damodaran 式 implied ERP。",
                    "reasoning_process": "FCF yield 3.5% - 10Y 4.25% = -0.75%。",
                    "first_principles_chain": ["FCF yield", "10Y Treasury", "simple gap"],
                    "cross_layer_implications": ["需要 L1 验证利率"],
                    "risk_flags": ["thin_margin"],
                    "permission_type": "composite",
                },
                {
                    "function_id": "get_damodaran_us_implied_erp",
                    "metric": "Damodaran US Implied ERP",
                    "current_reading": "4.33%",
                    "normalized_state": "background_anchor",
                    "narrative": "这是美国市场 implied ERP 背景锚，不替代 NDX 自身估值。",
                    "reasoning_process": "Damodaran 官方数据只解释美国市场风险补偿背景。",
                    "first_principles_chain": ["US market ERP", "background anchor"],
                    "cross_layer_implications": ["不能替代 NDX PE 分位"],
                    "risk_flags": [],
                    "permission_type": "context",
                }
            ],
        },
    )
    _write_json(
        run_dir / "analysis_packet.json",
        {
            "raw_data": {
                "L4": {
                    "get_ndx_pe_and_earnings_yield": {
                        "function_id": "get_ndx_pe_and_earnings_yield",
                        "metric_name": "NDX Valuation",
                        "value": {
                            "PE": 34.0,
                            "ThirdPartyChecks": [
                                {
                                    "source_name": "Trendonify",
                                    "source_tier": "third_party_estimate",
                                    "metric": "ndx_trailing_pe",
                                    "value": 34.1,
                                    "percentile_10y": 86.0,
                                    "historical_percentile": 86.0,
                                    "data_date": "May 01, 2026",
                                    "availability": "available",
                                },
                                {
                                    "source_name": "WorldPERatio",
                                    "source_tier": "third_party_estimate",
                                    "metric": "ndx_trailing_pe",
                                    "value": 32.27,
                                    "percentile_10y": None,
                                    "historical_percentile": None,
                                    "data_date": "01 May 2026",
                                    "availability": "available",
                                    "unavailable_reason": "historical percentile unavailable: source does not provide explicit percentile/rank",
                                    "relative_position": {
                                        "position_type": "std_dev_context_not_percentile",
                                        "valuation_windows": {
                                            "5y": {
                                                "average_pe": 31.2,
                                                "std_dev": 5.1,
                                                "range_low": 26.1,
                                                "range_high": 36.3,
                                                "deviation_vs_mean_sigma": 0.21,
                                                "valuation_label": "Fair",
                                            },
                                            "10y": {
                                                "average_pe": 27.4,
                                                "std_dev": 4.0,
                                                "range_low": 23.4,
                                                "range_high": 31.4,
                                                "deviation_vs_mean_sigma": 1.22,
                                                "valuation_label": "Overvalued",
                                            },
                                            "20y": {
                                                "average_pe": 25.8,
                                                "std_dev": 4.2,
                                                "range_low": 21.6,
                                                "range_high": 30.0,
                                                "deviation_vs_mean_sigma": 1.54,
                                                "valuation_label": "Overvalued",
                                            },
                                        },
                                        "trend_context": {
                                            "sma50_margin_pct": 8.7,
                                            "sma200_margin_pct": 12.4,
                                        },
                                    },
                                },
                                {
                                    "source_name": "Trendonify",
                                    "source_tier": "unavailable",
                                    "metric": "ndx_forward_pe",
                                    "value": None,
                                    "availability": "unavailable",
                                    "unavailable_reason": "403 Forbidden",
                                },
                            ],
                        },
                        "data_quality": {
                            "source_tier": "component_model",
                            "data_date": "2026-04-30",
                            "collected_at_utc": "2026-05-01T00:00:00Z",
                            "update_frequency": "daily when sources update",
                            "formula": "component model current value; third-party checks for PE/percentile",
                            "coverage": {"market_cap_coverage_pct": 92.5},
                            "anomalies": [],
                            "fallback_chain": ["licensed_manual/Wind", "official", "component_model", "third_party_estimate", "proxy"],
                            "source_disagreement": {"WorldPERatio PE": 32.27, "Trendonify PE": 34.1},
                        },
                    },
                    "get_damodaran_us_implied_erp": {
                        "function_id": "get_damodaran_us_implied_erp",
                        "metric_name": "Damodaran US Implied ERP Reference",
                        "value": {
                            "erp_t12m_adjusted_payout": 4.24,
                            "erp_t12m_cash_yield": 4.36,
                            "erp_avg_cf_yield_10y": 6.36,
                            "erp_net_cash_yield": 4.15,
                            "erp_normalized_earnings_payout": 3.73,
                            "implied_erp_fcfe": 4.24,
                            "tbond_rate": 4.40,
                            "adjusted_riskfree_rate": 4.14,
                            "default_spread": 0.26,
                            "expected_return": 8.55,
                            "scope": "US equity market reference, not NDX-specific",
                            "source_file": "ERPbymonth.xlsx",
                            "current_calculator_source_file": "ERPMay26.xlsx",
                            "monthly_series": [
                                {"data_date": "2026-01-01", "erp_t12m_adjusted_payout": 4.10, "us_10y_treasury_rate": 4.05, "expected_return": 8.15},
                                {"data_date": "2026-02-01", "erp_t12m_adjusted_payout": 4.18, "us_10y_treasury_rate": 4.18, "expected_return": 8.36},
                                {"data_date": "2026-03-01", "erp_t12m_adjusted_payout": 4.31, "us_10y_treasury_rate": 4.31, "expected_return": 8.62},
                                {"data_date": "2026-04-01", "erp_t12m_adjusted_payout": 4.29, "us_10y_treasury_rate": 4.25, "expected_return": 8.54},
                                {"data_date": "2026-05-01", "erp_t12m_adjusted_payout": 4.24, "us_10y_treasury_rate": 4.40, "expected_return": 8.55},
                            ],
                        },
                        "data_quality": {
                            "source_tier": "official",
                            "data_date": "2026-05-01",
                            "collected_at_utc": "2026-05-01T00:00:00Z",
                            "update_frequency": "monthly current ERP when ERPbymonth.xlsx is available",
                            "formula": "Damodaran US implied ERP model; monthly current ERP preferred",
                            "coverage": {"scope": "US market/S&P 500 reference"},
                            "anomalies": [],
                            "fallback_chain": ["official", "unavailable"],
                            "source_disagreement": {},
                        },
                    },
                    "get_equity_risk_premium": {
                        "function_id": "get_equity_risk_premium",
                        "metric_name": "NDX Simple Yield Gap",
                        "data_quality": {
                            "source_tier": "component_model",
                            "data_date": "2026-04-30",
                            "collected_at_utc": "2026-05-01T00:00:00Z",
                            "update_frequency": "daily when sources update",
                            "formula": "NDX FCF yield - 10Y Treasury yield",
                            "coverage": {"market_cap_coverage_pct": 92.5},
                            "anomalies": ["2 constituents excluded from FCF coverage"],
                            "fallback_chain": ["licensed_manual/Wind", "component_model", "proxy"],
                            "source_disagreement": {"WorldPERatio PE": 32.27, "Trendonify PE": 34.51},
                        },
                    }
                }
            }
        },
    )
    _write_json(
        run_dir / "bridge_memos" / "bridge_0.json",
        {
            "bridge_type": "macro_valuation",
            "cross_layer_claims": [],
            "conflicts": [
                {
                    "conflict_type": "L1_vs_L4",
                    "severity": "high",
                    "description": "高利率与高估值冲突。",
                    "implication": "估值压缩。",
                }
            ],
            "typed_conflicts": [
                {
                    "conflict_id": "real_rate_vs_valuation",
                    "conflict_type": "valuation_discount_rate",
                    "severity": "high",
                    "confidence": "medium",
                    "description": "高真实利率与高估值并存。",
                    "mechanism": "真实利率提高折现率。",
                    "implication": "估值压力必须保留。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": ["L1.get_10y_real_rate"],
                    "falsifiers": ["盈利上修足以抵消折现率压力。"],
                }
            ],
            "resonance_chains": [
                {
                    "chain_id": "risk_off_resonance",
                    "layers": ["L1", "L2", "L5"],
                    "description": "宏观约束、信用脆弱和技术节奏同时偏谨慎。",
                    "evidence_refs": ["L1.get_10y_real_rate"],
                    "confirming_indicators": ["get_10y_real_rate", "get_vix"],
                    "mechanism": "利率和风险偏好共同压低估值容忍度。",
                    "implication": "反弹需要更强确认。",
                    "falsifiers": ["风险偏好改善且利率回落。"],
                    "confidence": "medium",
                }
            ],
            "transmission_paths": [
                {
                    "path_id": "rates_to_valuation",
                    "source_layer": "L1",
                    "target_layer": "L4",
                    "mechanism": "真实利率通过折现率传导到估值倍数。",
                    "evidence_refs": ["L1.get_10y_real_rate"],
                    "implication": "估值安全边际变薄。",
                    "confidence": "medium",
                }
            ],
            "implication_for_ndx": "谨慎。",
        },
    )
    _write_json(run_dir / "critique.json", {"overall_assessment": "可用", "cross_layer_issues": []})
    _write_json(
        run_dir / "risk_boundary_report.json",
        {
            "failure_conditions": [],
            "must_preserve_risks": ["valuation_compression"],
            "boundary_status": {
                "liquidity_shock": "safe",
                "valuation_compression": "warning",
            },
        },
    )
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})
    _write_json(run_dir / "data_integrity_report.json", {"publish_status": "publishable", "blocking_reasons": []})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    # Structural assertions (present in every template)
    assert "NDX 投资判断书" in html
    assert "主论点证据链" in html
    assert "主判断" in html
    assert "风险与反证" in html
    assert "冲突与共振" in html
    assert "L1-L5 底稿" in html
    assert "数据与审计" in html
    assert "新闻源" not in html
    assert "新闻侧边材料" in html
    assert "五层底稿" in html
    assert "evidence-L1-get_10y_real_rate" in html
    assert "L1_vs_L4" in html
    assert "证据发言权" in html
    assert "主要冲突" in html
    assert "压力传导" in html
    assert "real_rate_vs_valuation" in html
    assert "rates_to_valuation" in html
    assert "risk_off_resonance" in html
    assert "来源等级" in html
    assert "component_model" in html
    assert "估值来源对照" in html
    assert "Trendonify" in html
    assert "WorldPERatio" in html
    assert "34.1" in html
    assert "86.0" in html
    assert '"data_quality"' in html
    assert "data-contract-ref" in html
    assert "403 Forbidden" in html
    assert "US equity market reference, not NDX-specific" in html
    assert "覆盖率" in html
    assert "NDX Simple Yield Gap" in html
    assert "确认指标" in html
    assert "本页读法" in html
    assert "优先复核" in html
    assert "分批试探" in html
    assert "这不是低风险环境，但可能是高风险高赔率候选。" in html
    assert "价格已反映部分坏消息。" in html
    assert "高风险高赔率候选。" in html
    assert "战术仓" in html
    assert "分批试探。" in html
    assert "优先复核" in html
    assert "回测数据边界" in html
    assert "get_ndx_forward_earnings_quality" in html
    assert "historical source required" in html
    assert "严格回测 invariant" in html
    assert "observation_dates_lte_effective_date" in html
    assert "alfred_first_vintage_not_enforced" in html
    assert "可发布" in html
    assert "可控" in html
    assert "需关注" in html
    assert "<b>safe</b>" not in html
    assert "<b>warning</b>" not in html
    assert "2 个阶段；输入 30，输出 15，合计 45" in html
    assert "{&#x27;prompt_tokens&#x27;:" not in html
    assert "数据日期" in html
    assert "输入跨度" in html
    assert "采集时间" in html
    assert "生成时间" in html
    assert "Yahoo 数据诊断" in html
    assert "Agent 运行健康" in html
    assert "Agent 原文检查器" in html
    assert "已保存 1 个阶段" in html
    assert "Agent IO Audit" not in html
    assert "L1-L5 输入边界卡" not in html
    assert "other layer runtime highlights absent" not in html
    assert "llm_stage_diagnostics.json" in html
    assert "审计索引" in html
    assert "页面使用的原生 JSON" not in html
    assert 'data-typed-conflict="real_rate_vs_valuation"' in html
    assert 'data-transmission-path="rates_to_valuation"' in html
    assert 'data-resonance-chain="risk_off_resonance"' in html
    assert "市场图谱" not in html
    assert "Damodaran ERP monthly lens" in html
    assert "Valuation cross-check + WorldPERatio" in html
    assert "ERPbymonth.xlsx" in html
    assert "ERPMay26.xlsx" in html
    assert "data-visual-type=\"damodaran-current\"" in html
    assert "data-indicator-visual=\"L4.get_damodaran_us_implied_erp\"" in html
    assert "std-dev, not percentile" in html
    assert "Overvalued" in html
    assert "function handleEvidenceHash" in html
    assert "window.addEventListener('hashchange', handleEvidenceHash)" in html
    assert "location.hash" in html

    # Redesign assertions — accordion, Slate Editorial, vocabulary translation
    assert "aria-expanded" in html
    assert "data-layer-panel" not in html
    assert 'class="layer-tab"' not in html
    assert "showLayer" not in html
    assert "有保留通过" in html
    assert "toggleLayerCard" in html
    assert "layer-card" in html
    assert "layer-card__head" in html
    assert "layer-card__body" in html
    assert "layer-summary-tile" in html
    assert "grid-template-rows" in html
    assert "prefers-reduced-motion" in html
    assert ":focus-visible" in html
    assert "skip-link" in html
    assert "Source Serif Pro" in html
    assert "JetBrains Mono" in html
    assert "Inter" in html
    payload_match = re.search(r'<script type="application/json" id="vnext-data">(.*?)</script>', html, re.S)
    assert payload_match
    assert "&quot;" not in payload_match.group(1)
    payload = json.loads(payload_match.group(1))
    assert "analysis_packet" not in payload
    assert "chart_time_series" not in payload
    assert payload["layers"]["L1"]["indicator_analyses"][0]["function_id"] == "get_10y_real_rate"
    audit_index = Path(report_path).with_name(f"{Path(report_path).stem}_audit_index.json")
    assert audit_index.exists()
    audit_payload = json.loads(audit_index.read_text(encoding="utf-8"))
    assert audit_payload["kind"] == "vnext_brief_audit_index"
    assert any(item["relative_path"] == "analysis_packet.json" for item in audit_payload["artifact_files"])

    atlas_path = reporter.run(run_dir, template="atlas")
    atlas_html = Path(atlas_path).read_text(encoding="utf-8")
    assert "template-atlas" in atlas_html

    legacy_path = reporter.run(run_dir, template="brief", include_legacy_agent_io_audit=True)
    legacy_html = Path(legacy_path).read_text(encoding="utf-8")
    assert "Agent IO Audit" in legacy_html
    assert "L1-L5 输入边界卡" in legacy_html


def test_prompt_inspector_renders_complete_prompt_and_hash(tmp_path: Path):
    run_dir = tmp_path / "run"
    prompt_text = "## System Message\n系统约束\n\n## User Message\nObjectCanon\nIndicatorCanon\nPermissionType\nResponse Rules\n完整原文_SENTINEL"
    prompt_dir = run_dir / "prompt_audit" / "L1"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "attempt_1.prompt.txt").write_text(prompt_text, encoding="utf-8")
    _write_json(prompt_dir / "attempt_1.payload.json", {"payload": {"layer": "L1", "value": 5.25}})
    (prompt_dir / "attempt_1.response.raw.txt").write_text('{"layer":"L1"}', encoding="utf-8")
    _write_json(prompt_dir / "output.validated.json", {"layer": "L1", "local_conclusion": "ok"})
    prompt_hash = __import__("hashlib").sha256(prompt_text.encode("utf-8")).hexdigest()
    _write_json(
        prompt_dir / "meta.json",
        {
            "stage": "L1",
            "stage_name": "l1",
            "status": "ok",
            "prompt_sha256": prompt_hash,
            "prompt_file": "prompt_audit/L1/attempt_1.prompt.txt",
            "output_artifact": "layer_cards/L1.json",
            "attempts": 1,
        },
    )
    _write_json(
        run_dir / "llm_stage_diagnostics.json",
        {"stages": {"l1": {"status": "ok", "attempts": 1, "prompt_audit": {"stage_dir": "prompt_audit/L1"}}}},
    )

    path = PromptInspectorGenerator(reports_dir=str(tmp_path / "reports")).run(run_dir)
    html = Path(path).read_text(encoding="utf-8")

    assert "Agent 原文检查器" in html
    assert "完整原文_SENTINEL" in html
    assert prompt_hash in html
    assert "总览" in html
    assert "完整原文" in html
    assert "输入数据" in html
    assert "规则定位" in html
    assert "输出结果" in html
    assert "下游流向" in html


def test_prompt_inspector_empty_cross_layer_signals_are_clean(tmp_path: Path):
    run_dir = tmp_path / "run"
    prompt_text = '## System Message\n系统约束\n\n## User Message\n{"context_brief":{"apparent_cross_layer_signals":[]}}'
    prompt_dir = run_dir / "prompt_audit" / "L1"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "attempt_1.prompt.txt").write_text(prompt_text, encoding="utf-8")
    _write_json(
        prompt_dir / "attempt_1.payload.json",
        {
            "payload": {
                "layer": "L1",
                "context_brief": {"apparent_cross_layer_signals": [], "layer_highlights": {"L1": ["ok"]}},
                "layer_raw_data": {},
                "layer_facts": {},
            }
        },
    )
    (prompt_dir / "attempt_1.response.raw.txt").write_text('{"layer":"L1"}', encoding="utf-8")
    _write_json(prompt_dir / "output.validated.json", {"layer": "L1"})
    _write_json(prompt_dir / "meta.json", {"stage": "L1", "stage_name": "l1", "status": "ok", "attempts": 1})
    _write_json(run_dir / "llm_stage_diagnostics.json", {"stages": {}})

    payload = PromptInspectorGenerator(reports_dir=str(tmp_path / "reports"))._load_payload(run_dir)

    assert payload["stages"][0]["boundary"]["status"] == "干净"


def test_l4_valuation_visual_uses_third_party_pb_when_component_pb_diverges(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._valuation_indicator_visual(
        "L4.get_ndx_pe_and_earnings_yield",
        {
            "PE": 33.3,
            "ForwardPE": 22.72,
            "PriceToBook": 41.18,
            "ThirdPartyChecks": [
                {"source_name": "DanjuanFunds", "value": 34.16, "pb": 10.02, "availability": "available"},
            ],
        },
    )

    assert "PB (3P)</b>10.02x" in html
    assert "Component-model PB diverged materially" in html


def test_l4_valuation_visual_explains_rejected_component_pb(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._valuation_indicator_visual(
        "L4.get_ndx_pe_and_earnings_yield",
        {
            "PE": 33.3,
            "ForwardPE": 22.72,
            "PriceToBook": None,
            "RejectedMetrics": {
                "PriceToBook": {
                    "component_value": 41.18,
                    "reference_median": 10.02,
                    "relative_diff_pct": 311.0,
                }
            },
            "ThirdPartyChecks": [
                {"source_name": "DanjuanFunds", "value": 34.16, "pb": 10.02, "availability": "available"},
            ],
        },
    )

    assert "PB (3P)</b>10.02x" in html
    assert "Component-model PB was rejected from core evidence" in html


def test_l4_valuation_visual_marks_supporting_only_component_metrics(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._valuation_indicator_visual(
        "L4.get_ndx_pe_and_earnings_yield",
        {
            "PE": 33.3,
            "ForwardPE": 22.72,
            "FCFYield": 1.4,
            "PriceToBook": 10.11,
            "MetricAuthority": {
                "FCFYield": {"usage": "supporting_only"},
                "PriceToBook": {"usage": "supporting_only"},
            },
            "ThirdPartyChecks": [
                {"source_name": "DanjuanFunds", "value": 34.16, "pb": 10.02, "availability": "available"},
            ],
        },
    )

    assert "FCF (proxy)</b>1.40%" in html
    assert "PB (3P)</b>10.02x" in html
    assert "FCF yield is supporting-only" in html
    assert "Component-model PB is supporting-only" in html


def test_vnext_reporter_slug_stable_with_colon_ref():
    assert _slug("L1.get_10y_real_rate") == _slug("L1.get_10y_real_rate: 1.94% 高分位") == "L1-get_10y_real_rate"


def test_vnext_reporter_renders_indicator_level_visuals(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "final_adjudication.json",
        {
            "approval_status": "approved_with_reservations",
            "final_stance": "中性偏谨慎",
            "confidence": "medium",
            "key_support_chains": [],
            "must_preserve_risks": [],
            "adjudicator_notes": "",
            "evidence_refs": [],
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {
            "packet_meta": {"data_date": "2026-05-01", "indicator_total": 6, "indicator_successful": 6},
            "objective_firewall_summary": {
                "object_clear": True,
                "authority_clear": True,
                "timing_clear": True,
                "cross_layer_verified": True,
                "strongest_falsifier": "",
                "unresolved_tensions": [],
                "warnings": [],
            },
        },
    )

    layer_payloads = {
        "L1": [
            {
                "function_id": "get_10y_real_rate",
                "metric": "10Y Real Rate",
                "current_reading": "1.94%, 10年分位86%",
                "normalized_state": "restrictive",
                "narrative": "实际利率处在高位。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            }
        ],
        "L2": [
            {
                "function_id": "get_cnn_fear_greed_index",
                "metric": "CNN Fear & Greed Index",
                "current_reading": "66.6, greed",
                "normalized_state": "greed",
                "narrative": "情绪偏贪婪但分项不一致。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            }
        ],
        "L3": [
            {
                "function_id": "get_percent_above_ma",
                "metric": "% Stocks Above MA",
                "current_reading": "50D 65.35%, 200D 56.44%",
                "normalized_state": "neutral",
                "narrative": "广度中性偏好。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
            {
                "function_id": "get_m7_fundamentals",
                "metric": "M7 Fundamentals",
                "current_reading": "market cap weighted PE 32.84, ROE 65.78%",
                "normalized_state": "strong",
                "narrative": "龙头质量较强但估值分散。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
        ],
        "L4": [],
        "L5": [
            {
                "function_id": "get_multi_scale_ma_position",
                "metric": "QQQ Multi-Scale MA Position",
                "current_reading": "价格674.15，均线多头排列",
                "normalized_state": "bullish_alignment",
                "narrative": "趋势结构偏强。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
            {
                "function_id": "get_donchian_channels_qqq",
                "metric": "QQQ Donchian Channels",
                "current_reading": "价格在98.1%分位",
                "normalized_state": "near_upper_band",
                "narrative": "价格贴近通道上沿。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
            {
                "function_id": "get_price_volume_quality_qqq",
                "metric": "QQQ Price Volume Quality",
                "current_reading": "VWAP above, MFI 72, CMF 0.08",
                "normalized_state": "constructive_flow",
                "narrative": "价格和资金流确认度偏正面。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
        ],
    }
    for layer, indicators in layer_payloads.items():
        _write_json(
            run_dir / "layer_cards" / f"{layer}.json",
            {
                "layer": layer,
                "local_conclusion": f"{layer} conclusion",
                "confidence": "medium",
                "risk_flags": [],
                "layer_synthesis": "",
                "internal_conflict_analysis": "",
                "indicator_analyses": indicators,
            },
        )
    _write_json(
        run_dir / "analysis_packet.json",
        {
            "raw_data": {
                "L1": {
                    "get_10y_real_rate": {
                        "value": {
                            "level": 1.94,
                            "ma": 1.931,
                            "deviation_pct": 0.47,
                            "position_vs_ma": "above",
                            "relativity": {"percentile_5y": 0.7238, "percentile_10y": 0.862, "z_score_10y": 1.22},
                        }
                    }
                },
                "L2": {
                    "get_cnn_fear_greed_index": {
                        "value": {
                            "score": 66.6,
                            "rating": "greed",
                            "sub_metrics": {
                                "Market Momentum (S&P500)": {"score": 99.8, "rating": "extreme greed"},
                                "Put/Call Options": {"score": 37.6, "rating": "fear"},
                                "Market Volatility (VIX)": {"score": 50, "rating": "neutral"},
                            },
                        }
                    }
                },
                "L3": {
                    "get_percent_above_ma": {
                        "value": {"level": {"percent_above_50d": 65.35, "percent_above_200d": 56.44}}
                    },
                    "get_m7_fundamentals": {
                        "value": {
                            "AAPL": {"PE": 33.9, "ROE": 141.5, "quantitative_moat_score": 9, "MarketCap": 4100},
                            "MSFT": {"PE": 24.7, "ROE": 34.0, "quantitative_moat_score": 10, "MarketCap": 3078},
                        }
                    },
                },
                "L5": {
                    "get_multi_scale_ma_position": {
                        "value": {
                            "current_price": 674.15,
                            "ma_positions": {
                                "ma5": {"value": 665.05, "deviation_pct": 1.37},
                                "ma20": {"value": 638.2, "deviation_pct": 5.63},
                                "ma60": {"value": 611.53, "deviation_pct": 10.24},
                                "ma200": {"value": 604.08, "deviation_pct": 11.6},
                            },
                        }
                    },
                    "get_donchian_channels_qqq": {
                        "value": {"upper": 675.97, "middle": 627.18, "lower": 578.4, "position_pct": 98.1}
                    },
                    "get_price_volume_quality_qqq": {
                        "value": {
                            "price_vs_vwap_20": "above",
                            "vwap_deviation_pct": 1.2,
                            "mfi_14": 72.0,
                            "mfi_status": "neutral",
                            "cmf_20": 0.08,
                            "cmf_status": "accumulation",
                        }
                    },
                },
            }
        },
    )
    _write_json(run_dir / "bridge_memos" / "bridge_0.json", {"bridge_type": "test", "cross_layer_claims": [], "conflicts": []})
    _write_json(run_dir / "critique.json", {"overall_assessment": "", "cross_layer_issues": []})
    _write_json(run_dir / "risk_boundary_report.json", {"failure_conditions": [], "must_preserve_risks": []})
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    assert 'data-indicator-visual="L1.get_10y_real_rate"' in html
    assert 'data-visual-type="relative-position"' in html
    assert "10Y percentile" in html
    assert 'data-indicator-visual="L2.get_cnn_fear_greed_index"' in html
    assert "Market Momentum" in html
    assert 'data-indicator-visual="L3.get_percent_above_ma"' in html
    assert "50D" in html
    assert "200D" in html
    assert 'data-indicator-visual="L3.get_m7_fundamentals"' in html
    assert "M7 fundamentals heatmap" in html
    assert 'data-indicator-visual="L5.get_multi_scale_ma_position"' in html
    assert "MA ladder" in html
    assert 'data-indicator-visual="L5.get_donchian_channels_qqq"' in html
    assert "Donchian channel" in html
    assert 'data-indicator-visual="L5.get_price_volume_quality_qqq"' in html
    assert "Price-volume quality" in html
    assert "MFI" in html


def test_vnext_reporter_handles_missing_data_quality(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "final_adjudication.json",
        {
            "approval_status": "approved_with_reservations",
            "final_stance": "中性偏谨慎",
            "confidence": "medium",
            "key_support_chains": [],
            "must_preserve_risks": [],
            "adjudicator_notes": "",
            "evidence_refs": [],
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {
            "packet_meta": {
                "data_date": "2026-04-23",
                "indicator_total": 1,
                "indicator_successful": 1,
            },
            "objective_firewall_summary": {
                "object_clear": True,
                "authority_clear": True,
                "timing_clear": True,
                "cross_layer_verified": True,
                "strongest_falsifier": "",
                "unresolved_tensions": [],
                "warnings": [],
            },
        },
    )
    _write_json(
        run_dir / "layer_cards" / "L1.json",
        {
            "layer": "L1",
            "local_conclusion": "宏观偏紧。",
            "confidence": "medium",
            "risk_flags": [],
            "layer_synthesis": "",
            "internal_conflict_analysis": "",
            "indicator_analyses": [
                {
                    "function_id": "get_10y_real_rate",
                    "metric": "10Y Real Rate",
                    "current_reading": "1.92%",
                    "normalized_state": "restrictive",
                    "narrative": "实际利率压制成长股估值。",
                    "reasoning_process": "",
                    "first_principles_chain": [],
                    "cross_layer_implications": [],
                    "risk_flags": [],
                }
            ],
        },
    )
    for layer in ["L2", "L3", "L4", "L5"]:
        _write_json(
            run_dir / "layer_cards" / f"{layer}.json",
            {
                "layer": layer,
                "local_conclusion": f"{layer} placeholder",
                "confidence": "medium",
                "layer_synthesis": "",
                "internal_conflict_analysis": "",
                "indicator_analyses": [],
            },
        )
    # No analysis_packet.raw_data → no data_quality enrichment
    _write_json(run_dir / "analysis_packet.json", {})
    _write_json(run_dir / "bridge_memos" / "bridge_0.json", {"bridge_type": "test", "cross_layer_claims": [], "conflicts": []})
    _write_json(run_dir / "critique.json", {"overall_assessment": "", "cross_layer_issues": []})
    _write_json(run_dir / "risk_boundary_report.json", {"failure_conditions": [], "must_preserve_risks": []})
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    # Should NOT render an inline data quality box when data_quality is absent.
    assert '<div class="data-quality-box">' not in html
    assert "data-contract-ref=\"L1.get_10y_real_rate\"" not in html
    # But layer cards should still render
    assert "layer-card" in html
    assert "evidence-L1-get_10y_real_rate" in html


def test_vnext_reporter_label_mapping():
    assert _label("approved_with_reservations", "approval") == "有保留通过"
    assert _label("medium", "confidence") == "中"
    assert _label("high", "severity") == "高"
    assert _label("valuation_compression", "risk_flag") == "估值压缩"
    assert _label("unknown_key", "approval") == "unknown_key"


def test_l4_manual_erp_visual_does_not_claim_damodaran_monthly(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._damodaran_indicator_visual(
        "L4.get_damodaran_us_implied_erp",
        {
            "manual_erp": 0.96,
            "manual_erp_percentile_5y": 67.3,
            "manual_erp_percentile_10y": 71.4,
            "scope": "manual/Wind ERP reference",
        },
    )

    assert "Manual/Wind ERP reference" in html
    assert "人工/Wind ERP 是外部风险补偿参考" in html
    assert "Damodaran ERP monthly lens" not in html
    assert "暂无月度序列" not in html
    assert "T12M adjusted payout" not in html


def test_l4_damodaran_visual_shows_official_percentile_windows(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._damodaran_indicator_visual(
        "L4.get_damodaran_us_implied_erp",
        {
            "data_date": "2026-05-01",
            "erp_t12m_adjusted_payout": 4.24,
            "erp_t12m_cash_yield": 4.36,
            "source_file": "ERPbymonth.xlsx",
            "retrieval_method": "monthly_excel",
            "monthly_series": [
                {"data_date": "2026-04-01", "erp_t12m_adjusted_payout": 4.1, "us_10y_treasury_rate": 4.05, "expected_return": 8.15},
                {"data_date": "2026-05-01", "erp_t12m_adjusted_payout": 4.24, "us_10y_treasury_rate": 4.4, "expected_return": 8.55},
            ],
            "damodaran_erp_historical_percentiles": {
                "data_cutoff_date": "2026-05-01",
                "windows": {
                    "5y": {"percentile": 42.7, "status": "available", "sample_count": 60, "required_min_months": 60, "window_start": "2021-06-01", "window_end": "2026-05-01"},
                    "10y": {"percentile": 37.5, "status": "available", "sample_count": 120, "required_min_months": 120, "window_start": "2016-06-01", "window_end": "2026-05-01"},
                },
            },
        },
    )

    assert "Damodaran ERP monthly lens" in html
    assert "Damodaran ERP 5Y percentile" in html
    assert "42.7%" in html
    assert "60/60 months" in html
    assert "2021-06-01 - 2026-05-01" in html
    assert "data_cutoff_date=2026-05-01" in html
    assert "not NDX PE/PB/Forward PE historical percentile" in html


def test_l4_valuation_visual_without_worldperatio_uses_neutral_title(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._valuation_indicator_visual(
        "L4.get_ndx_pe_and_earnings_yield",
        {
            "PE_TTM": 36.6,
            "PB": 10.49,
            "PE_TTM_percentile_10y": 88,
        },
    )

    assert "Valuation reference values" in html
    assert "Valuation cross-check + WorldPERatio" not in html
    assert "PE</b>36.60x" in html
    assert "PB</b>10.49x" in html
    assert "未接入 Trendonify 或 WorldPERatio" in html


def test_vnext_reporter_default_output_keeps_run_id_when_data_date_repeats(tmp_path: Path):
    run_dir = tmp_path / "20260506_061216"
    _write_json(
        run_dir / "synthesis_packet.json",
        {"packet_meta": {"data_date": "2026-05-02", "indicator_total": 0, "indicator_successful": 0}},
    )
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    output = reporter._default_output_path(run_dir, reporter._load_artifacts(run_dir), "brief", "slate_v2")

    assert output.name == "vnext_brief_20260502_0000_20260506_0612.html"


def test_enrich_indicator_data_quality_injects_collection_timestamp():
    """collection_timestamp_utc from collector is injected into every indicator's data_quality."""
    artifacts = {
        "analysis_packet": {
            "raw_data": {
                "L1": {
                    "get_fed_funds_rate": {
                        "value": 5.25,
                        "collection_timestamp_utc": "2026-05-13T19:12:34+00:00",
                    },
                    "get_vix": {
                        "value": 18.0,
                        "collection_timestamp_utc": "2026-05-13T19:12:35+00:00",
                        "manual_override_used": True,
                    },
                }
            }
        },
        "layers": {
            "L1": {
                "indicator_analyses": [
                    {
                        "function_id": "get_fed_funds_rate",
                        "metric": "Fed Funds",
                        "current_reading": "5.25%",
                    },
                    {
                        "function_id": "get_vix",
                        "metric": "VIX",
                        "current_reading": "18.0",
                    },
                ]
            }
        },
    }
    reporter = VNextReportGenerator(reports_dir="/tmp")
    reporter._enrich_indicator_data_quality(artifacts)

    l1_items = artifacts["layers"]["L1"]["indicator_analyses"]
    fed = l1_items[0]
    vix = l1_items[1]

    assert fed["data_quality"]["collected_at_utc"] == "2026-05-13T19:12:34+00:00"
    assert vix["data_quality"]["collected_at_utc"] == "2026-05-13T19:12:35+00:00"
    assert "手动输入" in vix["data_quality"]["source_tier"]


def test_enrich_indicator_data_quality_with_existing_dq():
    """When item already has data_quality (e.g. from LLM), valuation_sources
    and collected_at_utc must still be extracted / injected (U7 fix)."""
    artifacts = {
        "analysis_packet": {
            "raw_data": {
                "L4": {
                    "get_ndx_pe": {
                        "value": {
                            "ThirdPartyChecks": [
                                {"source_name": "Bloomberg", "availability": "available"},
                                {"source_name": "Wind", "availability": "available"},
                            ]
                        },
                        "collection_timestamp_utc": "2026-05-13T19:12:36+00:00",
                        "data_quality": {
                            "source_tier": "third_party_estimate",
                            "formula": "PE = price / earnings",
                        },
                    }
                }
            }
        },
        "layers": {
            "L4": {
                "indicator_analyses": [
                    {
                        "function_id": "get_ndx_pe",
                        "metric": "NDX PE",
                        "current_reading": "32.5",
                        # LLM generated a data_quality dict
                        "data_quality": {
                            "source_tier": "third_party_estimate",
                            "confidence": "medium",
                        },
                    }
                ]
            }
        },
    }
    reporter = VNextReportGenerator(reports_dir="/tmp")
    reporter._enrich_indicator_data_quality(artifacts)

    item = artifacts["layers"]["L4"]["indicator_analyses"][0]
    dq = item["data_quality"]

    # collected_at_utc must be injected even when item had existing dq
    assert dq["collected_at_utc"] == "2026-05-13T19:12:36+00:00"
    # valuation_sources must be extracted even when item had existing dq (U7)
    assert "valuation_sources" in dq
    assert len(dq["valuation_sources"]) == 2
    assert dq["valuation_sources"][0]["source_name"] == "Bloomberg"
    # Existing LLM fields must be preserved
    assert dq["confidence"] == "medium"
    # Raw data_quality fields must be merged in (U10: raw as base)
    assert dq["formula"] == "PE = price / earnings"


def test_timestamp_chip_formatting():
    """_timestamp_chip renders the data date, source, and contract drawer entry."""
    reporter = VNextReportGenerator(reports_dir="/tmp")

    chip = reporter._timestamp_chip(
        {
            "data_date": "2026-05-13",
            "provider": "FRED",
            "source_name": "FRED",
            "source_url": "",
            "collected_at_utc": "2026-05-13T19:12:34+00:00",
        },
        ref="L1.get_fed_funds_rate",
    )
    assert "数据时间：2026-05-13" in chip
    assert "来源：FRED" in chip
    assert "缺少来源链接" in chip
    assert "data-contract-ref" in chip
    assert "timestamp-chip" in chip

    chip_effective = reporter._timestamp_chip({"effective_date": "2026-05-12", "provider": "manual"})
    assert "数据时间：2026-05-12" in chip_effective

    chip_manual = reporter._timestamp_chip({
        "data_date": "2026-05-13",
        "provider": "Manual",
        "source_tier": "official · 手动输入",
    })
    assert "手动输入" in chip_manual

    # Missing timestamp
    chip_empty = reporter._timestamp_chip({})
    assert chip_empty == ""


def test_timestamp_chip_appears_in_brief_html(tmp_path: Path):
    """Timestamp chip is rendered in the final brief HTML for each indicator."""
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "final_adjudication.json",
        {
            "approval_status": "approved_with_reservations",
            "final_stance": "中性偏谨慎",
            "confidence": "medium",
            "must_preserve_risks": ["估值压缩风险"],
            "adjudicator_notes": "保留核心冲突。",
            "evidence_refs": [],
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {"packet_meta": {"data_date": "2026-05-13", "indicator_total": 1, "indicator_successful": 1}},
    )
    _write_json(
        run_dir / "layer_cards" / "L1.json",
        {
            "layer": "L1",
            "local_conclusion": "宏观偏紧。",
            "confidence": "medium",
            "indicator_analyses": [
                {
                    "function_id": "get_fed_funds_rate",
                    "metric": "Fed Funds",
                    "current_reading": "5.25%",
                    "normalized_state": "restrictive",
                    "narrative": "实际利率压制成长股估值。",
                    "reasoning_process": "实际利率上升 -> 折现率上升 -> 估值承压。",
                }
            ],
        },
    )
    for layer in ["L2", "L3", "L4", "L5"]:
        _write_json(
            run_dir / "layer_cards" / f"{layer}.json",
            {
                "layer": layer,
                "local_conclusion": f"{layer} placeholder",
                "confidence": "medium",
                "indicator_analyses": [],
            },
        )
    _write_json(
        run_dir / "analysis_packet.json",
        {
            "raw_data": {
                "L1": {
                    "get_fed_funds_rate": {
                        "value": 5.25,
                        "collection_timestamp_utc": "2026-05-13T19:12:34+00:00",
                    }
                }
            }
        },
    )
    _write_json(run_dir / "bridge_memos" / "bridge_0.json", {"bridge_type": "test", "cross_layer_claims": [], "conflicts": []})
    _write_json(run_dir / "critique.json", {"overall_assessment": "", "cross_layer_issues": []})
    _write_json(run_dir / "risk_boundary_report.json", {"failure_conditions": [], "must_preserve_risks": []})
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    # Evidence status should appear in the HTML with data time, not run collection time.
    assert "timestamp-chip" in html
    assert "数据时间：未记录" in html
    assert "来源：未记录" in html
    assert "证据合约" in html
