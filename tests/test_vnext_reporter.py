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


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {
            "packet_meta": {
                "data_date": "2026-04-23",
                "indicator_total": 34,
                "indicator_successful": 34,
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
    _write_json(run_dir / "risk_boundary_report.json", {"failure_conditions": [], "must_preserve_risks": []})
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    # Structural assertions (present in every template)
    assert "NDX vNext Native Artifact UI" in html
    assert "brief · 投研长文" in html
    assert "主论点证据链" in html
    assert "Layer Workbench" in html
    assert "evidence-L1-get_10y_real_rate" in html
    assert "L1_vs_L4" in html
    assert "Objective Firewall" in html
    assert "Permission Type" in html
    assert "Typed Conflicts" in html
    assert "Transmission Paths" in html
    assert "real_rate_vs_valuation" in html
    assert "rates_to_valuation" in html
    assert "risk_off_resonance" in html
    assert "Source Tier" in html
    assert "component_model" in html
    assert "Valuation Sources" in html
    assert "Trendonify" in html
    assert "WorldPERatio" in html
    assert "34.1" in html
    assert "86.0" in html
    assert "No Historical Percentile" in html
    assert "403 Forbidden" in html
    assert "US equity market reference, not NDX-specific" in html
    assert "Coverage" in html
    assert "NDX Simple Yield Gap" in html
    assert "Confirming Indicators" in html
    assert 'data-typed-conflict="real_rate_vs_valuation"' in html
    assert 'data-transmission-path="rates_to_valuation"' in html
    assert 'data-resonance-chain="risk_off_resonance"' in html
    assert "市场图谱" in html
    assert "L4 估值相对位置尺" in html
    assert "Damodaran ERP 月度路径" in html
    assert "WorldPERatio 窗口标签" in html
    assert "L1-L4 利率估值压力图" in html
    assert "ERPbymonth.xlsx" in html
    assert "ERPMay26.xlsx" in html
    assert "data-chart-id=\"damodaran-erp-series\"" in html
    assert "data-ref=\"L4.get_damodaran_us_implied_erp\"" in html
    assert "std-dev context, not percentile" in html
    assert "Overvalued" in html

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
    json.loads(payload_match.group(1))

    atlas_path = reporter.run(run_dir, template="atlas")
    atlas_html = Path(atlas_path).read_text(encoding="utf-8")
    assert "atlas · 证据地图" in atlas_html
    assert "template-atlas" in atlas_html


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

    # Should NOT contain data quality headers when data_quality is absent
    assert "来源等级" not in html
    # CSS always contains the class definition; assert no rendered element
    assert '<div class="data-quality-box">' not in html
    # But layer cards should still render
    assert "layer-card" in html
    assert "evidence-L1-get_10y_real_rate" in html


def test_vnext_reporter_label_mapping():
    assert _label("approved_with_reservations", "approval") == "有保留通过"
    assert _label("medium", "confidence") == "中"
    assert _label("high", "severity") == "高"
    assert _label("valuation_compression", "risk_flag") == "估值压缩"
    assert _label("unknown_key", "approval") == "unknown_key"
