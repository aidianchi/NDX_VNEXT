# -*- coding: utf-8 -*-
"""
core.collector

数据收集器

负责从 tools.py 收集、缓存和格式化所有市场数据。
支持实时数据和历史回测数据收集。
"""

import os
import json
import logging
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# 导入工具注册表
try:
    from ..tools import TOOLS_REGISTRY
except ImportError:
    from tools import TOOLS_REGISTRY

# 导入配置
try:
    from ..config import path_config
except ImportError:
    from config import path_config

try:
    from ..tools_common import classify_yfinance_failure, get_yfinance_runtime_diagnostics, reset_yfinance_runtime_diagnostics
except ImportError:
    from tools_common import classify_yfinance_failure, get_yfinance_runtime_diagnostics, reset_yfinance_runtime_diagnostics

class DataCollector:
    """负责从tools.py收集、缓存和格式化所有市场数据。"""
    def __init__(self):
        # 定义每个分析层级所需的数据函数
        self.LAYER_FUNCTIONS = {
            # 第一层：宏观经济状况 (Macro-Economic Conditions)
            # 核心问题：经济增长、通胀和货币政策的客观背景是什么？
            1: [
                "get_10y2y_spread_bp",
                "get_fed_funds_rate",
                "get_m2_yoy",                 # 传统货币存量（M2 YoY）
                "get_net_liquidity_momentum", # 美元净流动性动量（WALCL - TGA - RRP）
                "get_copper_gold_ratio",
                "get_10y_treasury",
                "get_10y_real_rate",
                "get_10y_breakeven",
            ],
            
            # 第二层：市场风险偏好 (Market Risk Appetite)
            # 核心问题：市场参与者的主观情绪是倾向风险还是规避风险？
            2: ["get_vix", "get_vxn", "get_hy_oas_bp", "get_ig_oas_bp", "get_hy_quality_spread_bp", "get_hyg_momentum", "get_xly_xlp_ratio", "get_crowdedness_dashboard", "get_vxn_vix_ratio", "get_cnn_fear_greed_index"],
            
            # 第三层：指数内部健康度 (Index Internal Health)
            # 核心问题：趋势是由广泛参与驱动还是由少数领导者支撑？
            3: ["get_advance_decline_line", "get_percent_above_ma", "get_qqq_qqew_ratio", "get_qqq_top10_concentration", "get_m7_fundamentals", "get_new_highs_lows", "get_mcclellan_oscillator_nasdaq_or_nyse"],
            
            # 第四层：指数基本面估值 (Index Fundamental Valuation)
            # 核心问题：当前价格相对于其内在价值和无风险资产，是否具有吸引力？
            4: ["get_ndx_pe_and_earnings_yield", "get_ndx_forward_earnings_quality", "get_equity_risk_premium", "get_damodaran_us_implied_erp"],
            
            # 第五层：价格趋势与波动率 (Price Trend & Volatility) - V6.0完整版
            # 核心问题：价格的路径、动能和波动状态如何？
            # V6.0新增：MACD（动量确认）、OBV（资金流向）、Volume Analysis（量价关系）、Donchian Channels（突破识别）
            # V7.0新增：Multi-Scale MA Position（多尺度移动平均线分析）
            5: [
                "get_qqq_technical_indicators",  # 综合技术指标（包含所有V6.0新增指标）
                "get_rsi_qqq",                   # RSI超买超卖
                "get_atr_qqq",                   # ATR波动率与止损
                "get_adx_qqq",                   # ADX趋势强度
                "get_macd_qqq",                  # V6.0新增：MACD动量确认
                "get_obv_qqq",                   # V6.0新增：OBV能量潮
                "get_volume_analysis_qqq",       # V6.0新增：成交量分析与量价关系
                "get_price_volume_quality_qqq",  # V7.1新增：VWAP/MFI/CMF量价质量验证
                "get_donchian_channels_qqq",     # V6.0新增：唐奇安通道突破识别
                "get_multi_scale_ma_position"    # V7.0新增：多尺度MA分析
            ]
        }

    def _merge_manual_ndx_valuation_checks(self, manual_metric: Dict[str, Any], backtest_date: Optional[str] = None) -> Dict[str, Any]:
        result = deepcopy(manual_metric)
        if backtest_date:
            value = result.get("value") if isinstance(result.get("value"), dict) else {}
            result["value"] = {**value, "ThirdPartyChecks": []}
            data_quality = result.get("data_quality") if isinstance(result.get("data_quality"), dict) else {}
            data_quality["source_disagreement"] = dict(data_quality.get("source_disagreement") or {})
            result["data_quality"] = data_quality
            result["manual_override_note"] = (
                "Manual valuation values remain primary; live third-party checks are skipped in backtest "
                "to avoid current web data entering historical evidence."
            )
            return result

        try:
            try:
                from ..tools_L4 import get_ndx_valuation_third_party_checks
            except ImportError:
                from tools_L4 import get_ndx_valuation_third_party_checks
            third_party_checks = get_ndx_valuation_third_party_checks()
        except Exception as exc:
            third_party_checks = []
            result["third_party_checks_error"] = str(exc)[:150]

        value = result.get("value") if isinstance(result.get("value"), dict) else {}
        result["value"] = {**value, "ThirdPartyChecks": third_party_checks}

        data_quality = result.get("data_quality") if isinstance(result.get("data_quality"), dict) else {}
        source_disagreement = dict(data_quality.get("source_disagreement") or {})
        for item in third_party_checks:
            if not isinstance(item, dict):
                continue
            source_disagreement[item.get("source_id") or item.get("source") or item.get("source_name")] = {
                "metric": item.get("metric"),
                "value": item.get("value"),
                "data_date": item.get("data_date"),
                "percentile_10y": item.get("percentile_10y"),
                "historical_percentile": item.get("historical_percentile"),
                "source_tier": item.get("source_tier"),
                "availability": item.get("availability"),
                "unavailable_reason": item.get("unavailable_reason") or item.get("error"),
                "browser_sidecar": item.get("browser_sidecar"),
            }
        data_quality["source_disagreement"] = source_disagreement
        result["data_quality"] = data_quality
        result["manual_override_note"] = (
            "Manual valuation values remain primary; live third-party checks are attached for audit/cross-check only."
        )
        return result

    # 回测时不支持历史数据的函数：宁缺勿错，跳过并写入可审计记录。
    BACKTEST_UNSUPPORTED_FUNCTIONS = {
        "get_m7_fundamentals": {
            "reason": "yfinance.info 只返回最新财报，不能证明是回测日可见数据",
            "anomalies": ["latest_only_yfinance_fundamentals_not_used_in_backtest"],
        },
        "get_qqq_top10_concentration": {
            "reason": "当前路径的 Invesco holdings 只暴露最新持仓，不能证明是回测日成分/权重",
            "anomalies": ["latest_only_holdings_endpoint_not_used_in_backtest"],
        },
        "get_ndx_pe_and_earnings_yield": {
            "reason": "自动路径依赖 yfinance 成分股基本面批量代理；回测时覆盖率和历史可见性不可接受，若有人工/Wind 数据可用人工覆盖",
            "anomalies": ["batch_yfinance_component_fundamentals_not_used_in_backtest"],
        },
        "get_ndx_forward_earnings_quality": {
            "reason": "自动路径依赖 yfinance 最新 forward fundamentals / EPS trend，回测时自动跳过",
            "anomalies": ["latest_only_yfinance_forward_fundamentals_not_used_in_backtest"],
        },
        "get_equity_risk_premium": {
            "reason": "该简式收益差距依赖 NDX 成分股估值收益率；回测自动路径不可用时不再间接触发批量 yfinance",
            "anomalies": ["dependent_on_skipped_ndx_component_valuation"],
        },
    }

    def _build_strict_backtest_invariants(self, backtest_date: Optional[str]) -> Dict[str, Any]:
        if not backtest_date:
            return {}
        return {
            "schema_version": "strict_backtest_invariants_v1",
            "effective_date": backtest_date,
            "hard_enforced": [
                {
                    "invariant_id": "observation_dates_lte_effective_date",
                    "status": "enforced_by_data_integrity_gate",
                    "description": "进入 packet / prompt / report 的观察日期不得晚于回测日；递归日期扫描发现越界会阻断发布。",
                },
                {
                    "invariant_id": "latest_only_component_fundamentals_skipped",
                    "status": "enforced_by_collector_visibility_gate",
                    "description": "不能证明回测日可见的 yfinance 成分股基本面、最新持仓和相关派生估值自动路径会跳过并写入 backtest_data_boundaries。",
                },
                {
                    "invariant_id": "inactive_manual_values_hidden",
                    "status": "enforced_by_packet_builder",
                    "description": "inactive manual metrics 只保留审计计数，不把具体数值送入 agent 上下文。",
                },
            ],
            "declared_limitations": [
                {
                    "invariant_id": "alfred_first_vintage_not_enforced",
                    "status": "declared_limitation",
                    "publish_impact": "publishable_with_disclosure",
                    "description": "FRED 类宏观序列当前按 observation date 裁剪；尚未强制使用 ALFRED first-vintage 还原首次发布版本。",
                    "future_upgrade": "为可修订宏观序列接入 ALFRED vintage_date / realtime_start 约束。",
                },
                {
                    "invariant_id": "financials_first_reported_not_enforced",
                    "status": "declared_limitation",
                    "publish_impact": "publishable_with_disclosure_or_skip_latest_only",
                    "description": "财报、盈利预期和成分股 fundamentals 尚未系统校验 first-reported / filing availability；不能证明历史可见的自动路径默认跳过。",
                    "future_upgrade": "接入带 filing_date / accepted_date / report_date 的历史财报与预期数据源。",
                },
                {
                    "invariant_id": "point_in_time_universe_not_enforced",
                    "status": "declared_limitation",
                    "publish_impact": "publishable_with_disclosure_or_proxy_only",
                    "description": "当前没有完整 point-in-time NDX universe；历史成分、权重和集中度只能用可见来源或明确 proxy，不能冒充正式历史成分事实。",
                    "future_upgrade": "建立 NDX constituent / weight history，或接入能证明发布时间的官方/供应商快照。",
                },
                {
                    "invariant_id": "llm_training_prior_not_eliminated",
                    "status": "declared_limitation",
                    "publish_impact": "publishable_with_disclosure",
                    "description": "LLM 可能带有回测日之后的世界知识；系统只允许它基于 evidence refs 下结论，不声称完全复原当时认知环境。",
                    "future_upgrade": "在 prompt / governance 中继续限制无证据历史胜率、点位和事后叙事，并用审计样本复盘。",
                },
            ],
            "research_candidate_policy": {
                "status": "manual_review_required",
                "description": "联网研究、浏览器 sidecar 或当前网页发现的历史线索必须先标记 research_candidate / manual_review_required，未升级为正式数据源前不得成为 L1-L5 evidence_ref。",
            },
        }

    def _collect_single_indicator(self, func_name: str, end_date: Optional[str] = None) -> dict:
        """安全地调用单个数据函数并处理异常。"""
        started = time.monotonic()
        try:
            if func_name not in TOOLS_REGISTRY:
                raise ValueError(f"函数 {func_name} 未在 tools.py 中定义。")
            
            # 回测模式下，跳过不支持历史数据的函数
            if end_date and func_name in self.BACKTEST_UNSUPPORTED_FUNCTIONS:
                skip_meta = self.BACKTEST_UNSUPPORTED_FUNCTIONS[func_name]
                logging.warning(f"  - 跳过 {func_name}... ⊘ (回测模式下不支持历史数据，避免前瞻偏差)")
                result = {
                    "name": func_name.replace('_', ' ').title(),
                    "value": None,
                    "error": "backtest_skipped_unsupported_function",
                    "backtest_skipped": True,
                    "skip_reason": skip_meta["reason"],
                    "data_quality": {
                        "effective_date": end_date,
                        "availability": "backtest_skipped",
                        "anomalies": skip_meta.get("anomalies", ["latest_only_source_not_used_in_backtest"]),
                    },
                }
                return self._finalize_indicator_result(result, started)
            
            result = TOOLS_REGISTRY[func_name](end_date=end_date)
            
            if result.get('value') is None:
                logging.warning(f"  - 调用 {func_name}... ✗ (数据缺失)")
                result['error'] = "Upstream data source returned None."
            else:
                logging.info(f"  - 调用 {func_name}... ✔")
            return self._finalize_indicator_result(result, started)
            
        except Exception as e:
            error_msg = str(e)[:150]
            logging.error(f"  - 调用 {func_name}... ✗ (异常: {error_msg})")
            return self._finalize_indicator_result(
                {"name": func_name.replace('_', ' ').title(), "value": None, "error": error_msg},
                started,
            )

    def _finalize_indicator_result(self, result: Dict[str, Any], started: float) -> Dict[str, Any]:
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        result["collection_duration_ms"] = duration_ms
        error = result.get("error")
        data_quality = result.get("data_quality") if isinstance(result.get("data_quality"), dict) else {}
        data_quality["collection_duration_ms"] = duration_ms
        if error and not result.get("backtest_skipped"):
            failure_type = classify_yfinance_failure(error)
            if failure_type == "provider_error":
                failure_type = "upstream_error"
            result["failure_type"] = failure_type
            result["failure_stage"] = "collection"
            data_quality["availability"] = data_quality.get("availability") or "unavailable"
            data_quality["failure_type"] = failure_type
            data_quality["failure_reason"] = str(error)[:240]
            anomalies = list(data_quality.get("anomalies") or [])
            marker = f"collection_{failure_type}"
            if marker not in anomalies:
                anomalies.append(marker)
            data_quality["anomalies"] = anomalies
        elif result.get("backtest_skipped"):
            result["failure_type"] = "backtest_skipped"
            result["failure_stage"] = "visibility_gate"
        else:
            data_quality["availability"] = data_quality.get("availability") or "available"
        result["data_quality"] = data_quality
        return result

    def run(self, backtest_date: Optional[str] = None, enable_news: bool = False) -> Dict[str, Any]:
        """
        执行所有数据收集任务，优先使用manual_data.py中的数据进行覆盖。
        
        Args:
            backtest_date: 回测日期（可选）
            enable_news: 是否启用新闻采集（默认False，非侵入性）
        """
        reset_yfinance_runtime_diagnostics()
        # --- 【新增逻辑】: 尝试导入手动数据模块 ---
        try:
            # 确保能从 src/ 目录导入 manual_data
            try:
                from ..manual_data import load_manual_data, has_meaningful_manual_override
            except ImportError:
                from manual_data import load_manual_data, has_meaningful_manual_override
            MANUAL_DATA = load_manual_data()
            manual_data_available = True
            logging.info("成功加载 'manual_data.py' 文件。")
        except ImportError as e:
            manual_data_available = False
            MANUAL_DATA = {} # 定义一个空的字典以防出错
            logging.info(f"'manual_data.py' 文件未找到，将完全使用自动化数据收集。(详情: {e})")

        if backtest_date:
            logging.info(f"\n[步骤 1/4] 数据收集阶段 (历史时点: {backtest_date})")
        else:
            logging.info("\n[步骤 1/4] 数据收集阶段 (实时)")
        logging.info("=" * 35)
        
        indicators = []
        for layer_num, functions in self.LAYER_FUNCTIONS.items():
            layer_name = {
                1: "宏观经济状况", 
                2: "市场风险偏好", 
                3: "指数内部健康度", 
                4: "指数基本面估值", 
                5: "价格趋势与波动率"
            }.get(layer_num)
            logging.info(f"\n[第{layer_num}层] 收集 {layer_name} 数据...")
            
            for func_name in functions:
                # --- 【新增逻辑】: 优先检查并使用手动输入的数据 ---
                # 检查1: manual_data.py是否存在
                # 检查2: manual_data.py是否被激活 (active: True)
                # 检查3: 当前函数名是否在手动数据的metrics字典中
                manual_metric = MANUAL_DATA.get("metrics", {}).get(func_name) if manual_data_available else None
                manual_active = bool(manual_data_available and MANUAL_DATA.get("active") and has_meaningful_manual_override(manual_metric))

                # Damodaran ERP: always call live function for monthly series, merge manual values as supplement
                if func_name == "get_damodaran_us_implied_erp":
                    result = self._collect_single_indicator(func_name, end_date=backtest_date)
                    if manual_active and isinstance(manual_metric, dict):
                        manual_value = manual_metric.get("value", {}) if isinstance(manual_metric.get("value"), dict) else {}
                        live_value = result.get("value", {}) if isinstance(result.get("value"), dict) else {}
                        merged_value = dict(live_value)
                        for key in ("manual_erp", "manual_erp_percentile_5y", "manual_erp_percentile_10y"):
                            if manual_value.get(key) is not None:
                                merged_value[key] = manual_value[key]
                        result["value"] = merged_value
                        result["manual_override_used"] = True
                        result["manual_override_note"] = "Manual ERP values merged into Damodaran monthly data; series is filtered by target_date when supplied"
                        logging.info(f"  - 调用 {func_name}... ✔ (Damodaran monthly data merged with manual ERP overrides)")
                    else:
                        logging.info(f"  - 调用 {func_name}... ✔ (Damodaran monthly data)")
                    indicator = {
                        "layer": layer_num,
                        "metric_name": result.get("name", func_name.replace("_", " ").title()),
                        "function_id": func_name,
                        "raw_data": result,
                        "error": result.get("error"),
                        "collection_timestamp_utc": datetime.now(timezone.utc).isoformat()
                    }
                    indicators.append(indicator)
                    continue

                if manual_active:
                    logging.info(f"  - 璋冪敤 {func_name}... 鉁?(manual override used)")
                    logging.info(f"  - 调用 {func_name}... ✔ (使用 'manual_data.py' 中的人工数据)")
                    raw_data = manual_metric
                    if func_name == "get_ndx_pe_and_earnings_yield" and isinstance(manual_metric, dict):
                        raw_data = self._merge_manual_ndx_valuation_checks(manual_metric, backtest_date=backtest_date)
                        if backtest_date:
                            logging.info(f"  - 调用 {func_name}... ✔ (manual valuation used; live third-party checks skipped in backtest)")
                        else:
                            logging.info(f"  - 调用 {func_name}... ✔ (manual valuation merged with live third-party checks)")
                    indicator = {
                        "layer": layer_num,
                        "metric_name": raw_data.get("name", func_name.replace("_", " ").title()),
                        "function_id": func_name,
                        "raw_data": raw_data,
                        "error": None,
                        "collection_timestamp_utc": datetime.now(timezone.utc).isoformat()
                    }
                    indicators.append(indicator)
                    # 使用 continue 结束当前函数的处理，直接进入下一个函数的循环
                    # 这确保了只有这一个函数被手动数据覆盖，其他函数不受影响
                    continue
                if manual_data_available and MANUAL_DATA.get("active") and manual_metric is not None:
                    logging.info(f"  - 璋冪敤 {func_name}... 鉁?(manual metric skipped, fallback to live source)")
                # --- 【新增逻辑结束】 ---

                # 如果上述if条件不满足，则正常执行自动化数据收集
                result = self._collect_single_indicator(func_name, end_date=backtest_date)
                indicator = {
                    "layer": layer_num,
                    "metric_name": result.get("name", func_name.replace("_", " ").title()),
                    "function_id": func_name,
                    "raw_data": result,
                    "error": result.get("error"),
                    "collection_timestamp_utc": datetime.now(timezone.utc).isoformat()
                }
                indicators.append(indicator)

        backtest_data_boundaries = []
        if backtest_date:
            for indicator in indicators:
                raw = indicator.get("raw_data") if isinstance(indicator.get("raw_data"), dict) else {}
                if raw.get("backtest_skipped"):
                    backtest_data_boundaries.append({
                        "layer": indicator.get("layer"),
                        "function_id": indicator.get("function_id"),
                        "status": "skipped",
                        "reason": raw.get("skip_reason"),
                        "effective_date": backtest_date,
                        "future_upgrade": "接入能证明回测日可见性的历史数据源后再启用",
                    })

        data_json = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "backtest_date": backtest_date,
            "indicators": indicators,
            "backtest_data_boundaries": backtest_data_boundaries,
            "strict_backtest_invariants": self._build_strict_backtest_invariants(backtest_date),
            "runtime_diagnostics": get_yfinance_runtime_diagnostics(),
        }
        
        # News/events are intentionally handled as a sidecar artifact by src/main.py.
        # They must not be mixed into the L1-L5 numeric indicator payload.
        if enable_news:
            logging.info("新闻开关已启用；事件底账将由 main.py 独立写入 news_event_ledger.json。")
        
        # 安全地生成文件名，防止路径注入
        if backtest_date:
            safe_date = backtest_date.replace('-', '')
            if not safe_date.isalnum():
                raise ValueError(f"无效的日期格式: {backtest_date}")
            output_filename = f"{path_config.data_dir}/data_collected_v9_{safe_date}.json"
        else:
            output_filename = f"{path_config.data_dir}/data_collected_v9_live.json"
        
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(data_json, f, ensure_ascii=False, indent=2)
        logging.info(f"\n=== 数据收集完成，原始数据已保存至: {output_filename} ===")
        
        return data_json

# =====================================================
# Class: AI分析器 (AIAnalyzer) - 保持不变
# =====================================================
