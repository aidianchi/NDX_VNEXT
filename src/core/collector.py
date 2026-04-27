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
from datetime import datetime
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
            2: ["get_vix", "get_vxn", "get_hy_oas_bp", "get_ig_oas_bp", "get_hyg_momentum", "get_xly_xlp_ratio", "get_crowdedness_dashboard", "get_vxn_vix_ratio", "get_cnn_fear_greed_index"],
            
            # 第三层：指数内部健康度 (Index Internal Health)
            # 核心问题：趋势是由广泛参与驱动还是由少数领导者支撑？
            3: ["get_advance_decline_line", "get_percent_above_ma", "get_qqq_qqew_ratio", "get_m7_fundamentals", "get_new_highs_lows", "get_mcclellan_oscillator_nasdaq_or_nyse"],
            
            # 第四层：指数基本面估值 (Index Fundamental Valuation)
            # 核心问题：当前价格相对于其内在价值和无风险资产，是否具有吸引力？
            4: ["get_ndx_pe_and_earnings_yield", "get_equity_risk_premium"],
            
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
                "get_donchian_channels_qqq",     # V6.0新增：唐奇安通道突破识别
                "get_multi_scale_ma_position"    # V7.0新增：多尺度MA分析
            ]
        }

    # 回测时不支持历史数据的函数列表
    BACKTEST_UNSUPPORTED_FUNCTIONS = [
        "get_m7_fundamentals",  # yfinance.info只返回最新财报，不支持历史查询
    ]

    def _collect_single_indicator(self, func_name: str, end_date: Optional[str] = None) -> dict:
        """安全地调用单个数据函数并处理异常。"""
        try:
            if func_name not in TOOLS_REGISTRY:
                raise ValueError(f"函数 {func_name} 未在 tools.py 中定义。")
            
            # 回测模式下，跳过不支持历史数据的函数
            if end_date and func_name in self.BACKTEST_UNSUPPORTED_FUNCTIONS:
                logging.warning(f"  - 跳过 {func_name}... ⊘ (回测模式下不支持历史数据，避免前瞻偏差)")
                return {
                    "name": func_name.replace('_', ' ').title(),
                    "value": None,
                    "error": None,
                    "backtest_skipped": True,
                    "skip_reason": "该指标仅支持实时数据，回测模式下自动跳过以避免前瞻偏差"
                }
            
            result = TOOLS_REGISTRY[func_name](end_date=end_date)
            
            if result.get('value') is None:
                logging.warning(f"  - 调用 {func_name}... ✗ (数据缺失)")
                result['error'] = "Upstream data source returned None."
            else:
                logging.info(f"  - 调用 {func_name}... ✔")
            return result
            
        except Exception as e:
            error_msg = str(e)[:150]
            logging.error(f"  - 调用 {func_name}... ✗ (异常: {error_msg})")
            return {"name": func_name.replace('_', ' ').title(), "value": None, "error": error_msg}

    def run(self, backtest_date: Optional[str] = None, enable_news: bool = False) -> Dict[str, Any]:
        """
        执行所有数据收集任务，优先使用manual_data.py中的数据进行覆盖。
        
        Args:
            backtest_date: 回测日期（可选）
            enable_news: 是否启用新闻采集（默认False，非侵入性）
        """
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
                if manual_data_available and MANUAL_DATA.get("active") and has_meaningful_manual_override(manual_metric):
                    logging.info(f"  - 璋冪敤 {func_name}... 鉁?(manual override used)")
                    logging.info(f"  - 调用 {func_name}... ✔ (使用 'manual_data.py' 中的人工数据)")
                    indicator = {
                        "layer": layer_num,
                        "metric_name": manual_metric.get("name", func_name.replace("_", " ").title()),
                        "function_id": func_name,
                        "raw_data": manual_metric, # 将整块手动数据存入raw_data
                        "error": None,
                        "collection_timestamp_utc": datetime.utcnow().isoformat()
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
                    "collection_timestamp_utc": datetime.utcnow().isoformat()
                }
                indicators.append(indicator)

        data_json = {
            "timestamp_utc": datetime.utcnow().isoformat(),
            "backtest_date": backtest_date,
            "indicators": indicators
        }
        
        # --- 【新增】联网新闻采集（可选，非侵入性）---
        if enable_news:
            try:
                logging.info("\n" + "=" * 60)
                logging.info("[可选功能] 联网新闻采集已启用")
                logging.info("=" * 60)
                
                try:
                    from ..news_collector import NewsManager
                    from ..news_manager import NewsCacheManager, NewsIntegrator
                except ImportError:
                    from news_collector import NewsManager
                    from news_manager import NewsCacheManager, NewsIntegrator
                
                # 检查缓存
                cache_mgr = NewsCacheManager(cache_hours=6)
                
                if cache_mgr.is_cache_valid():
                    # 使用缓存
                    news_data = cache_mgr.load_cache()
                    logging.info("✓ 使用缓存的新闻数据")
                else:
                    # 重新采集
                    # 注意：use_nlp=False 使用简单关键词（默认）
                    # 若要启用FinBERT，需先安装: pip install transformers torch
                    news_mgr = NewsManager(use_nlp=False)
                    grouped_news = news_mgr.collect_all()
                    
                    # 转换为可序列化格式
                    news_data = {}
                    for layer, items in grouped_news.items():
                        news_data[layer] = [item.to_dict() for item in items]
                    
                    # 保存缓存
                    cache_mgr.save_cache(news_data)
                
                # 整合新闻到数据JSON
                integrator = NewsIntegrator()
                data_json = integrator.integrate_with_data(data_json, news_data)
                
                logging.info("✓ 新闻数据已成功整合到分析框架")
                
            except Exception as e:
                logging.warning(f"新闻采集失败（不影响核心流程）: {e}")
                logging.warning("将继续使用纯数值数据进行分析")
        # --- 【新增结束】---
        
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
