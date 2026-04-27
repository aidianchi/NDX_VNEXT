# tools.py
# -*- coding: utf-8 -*-
"""
NDX Agent 数据工具统一入口。

设计原则：
1. `TOOLS_REGISTRY` 保持为原版实现的标准注册表，兼容现有调用方。
2. `OPTIMIZED_TOOLS_REGISTRY` 仅对“已验证为等价且能带来缓存收益”的函数做受控覆盖。
3. collector 只能通过 registry 取函数，不能在编排层硬编码 API 调用。
"""

try:
    from .tools_common import *
    from .tools_L1 import *
    from .tools_L2 import *
    from .tools_L3 import *
    from .tools_L4 import *
    from .tools_L5 import *
    from .tools_finnhub import (
        get_stock_quote,
        get_stock_candles,
        get_company_profile,
        get_basic_financials,
        get_financials_reported,
        get_analyst_recommendations,
        get_price_target,
        get_earnings_estimates,
        get_news_sentiment,
        get_insider_transactions,
        get_stock_full_analysis,
        get_m7_finnhub_analysis,
    )
    from .tools_simfin import (
        get_company_info,
        get_financial_statements,
        get_all_financials,
        get_derived_signals,
        get_key_metrics,
        get_current_valuation,
        get_share_prices,
        get_m7_simfin_analysis,
        get_m7_fundamentals_simfin,
    )
except ImportError:
    from tools_common import *
    from tools_L1 import *
    from tools_L2 import *
    from tools_L3 import *
    from tools_L4 import *
    from tools_L5 import *
    from tools_finnhub import (
        get_stock_quote,
        get_stock_candles,
        get_company_profile,
        get_basic_financials,
        get_financials_reported,
        get_analyst_recommendations,
        get_price_target,
        get_earnings_estimates,
        get_news_sentiment,
        get_insider_transactions,
        get_stock_full_analysis,
        get_m7_finnhub_analysis,
    )
    from tools_simfin import (
        get_company_info,
        get_financial_statements,
        get_all_financials,
        get_derived_signals,
        get_key_metrics,
        get_current_valuation,
        get_share_prices,
        get_m7_simfin_analysis,
        get_m7_fundamentals_simfin,
    )


TOOLS_REGISTRY = {
    # 核心数据
    "get_ndx100_components": get_ndx100_components,

    # Layer 1
    "get_vix": get_vix,
    "get_vxn": get_vxn,
    "get_vxn_vix_ratio": get_vxn_vix_ratio,
    "get_10y2y_spread_bp": get_10y2y_spread_bp,
    "get_hy_oas_bp": get_hy_oas_bp,
    "get_ig_oas_bp": get_ig_oas_bp,
    "get_10y_real_rate": get_10y_real_rate,
    "get_10y_treasury": get_10y_treasury,
    "get_10y_breakeven": get_10y_breakeven,
    "get_fed_funds_rate": get_fed_funds_rate,
    "get_m2_yoy": get_m2_yoy,
    "get_hyg_momentum": get_hyg_momentum,
    "get_net_liquidity_momentum": get_net_liquidity_momentum,
    "get_qqq_net_liquidity_ratio": get_qqq_net_liquidity_ratio,
    "get_xly_xlp_ratio": get_xly_xlp_ratio,
    "get_copper_gold_ratio": get_copper_gold_ratio,

    # Layer 2
    "get_qqq_qqew_ratio": get_qqq_qqew_ratio,
    "get_advance_decline_line": get_advance_decline_line,
    "get_percent_above_ma": get_percent_above_ma,
    "get_new_highs_lows": get_new_highs_lows,
    "get_mcclellan_oscillator_nasdaq_or_nyse": get_mcclellan_oscillator_nasdaq_or_nyse,
    "get_cnn_fear_greed_index": get_cnn_fear_greed_index,

    # Layer 3
    "get_m7_fundamentals": get_m7_fundamentals,

    # Layer 4
    "get_ndx_pe_and_earnings_yield": get_ndx_pe_and_earnings_yield,
    "get_equity_risk_premium": get_equity_risk_premium,
    "get_crowdedness_dashboard": get_crowdedness_dashboard,

    # Layer 5
    "get_qqq_technical_indicators": get_qqq_technical_indicators,
    "get_rsi_qqq": get_rsi_qqq,
    "get_atr_qqq": get_atr_qqq,
    "get_adx_qqq": get_adx_qqq,
    "get_macd_qqq": get_macd_qqq,
    "get_obv_qqq": get_obv_qqq,
    "get_volume_analysis_qqq": get_volume_analysis_qqq,
    "get_donchian_channels_qqq": get_donchian_channels_qqq,
    "get_multi_scale_ma_position": get_multi_scale_ma_position,

    # Finnhub 数据（L4 个股深度分析）
    "get_stock_quote": get_stock_quote,
    "get_stock_candles": get_stock_candles,
    "get_company_profile": get_company_profile,
    "get_basic_financials": get_basic_financials,
    "get_financials_reported": get_financials_reported,
    "get_analyst_recommendations": get_analyst_recommendations,
    "get_price_target": get_price_target,
    "get_earnings_estimates": get_earnings_estimates,
    "get_news_sentiment": get_news_sentiment,
    "get_insider_transactions": get_insider_transactions,
    "get_stock_full_analysis": get_stock_full_analysis,
    "get_m7_finnhub_analysis": get_m7_finnhub_analysis,

    # Simfin 数据（L4 财务基本面）
    "get_company_info": get_company_info,
    "get_financial_statements": get_financial_statements,
    "get_all_financials": get_all_financials,
    "get_derived_signals": get_derived_signals,
    "get_key_metrics": get_key_metrics,
    "get_current_valuation": get_current_valuation,
    "get_share_prices": get_share_prices,
    "get_m7_simfin_analysis": get_m7_simfin_analysis,
    "get_m7_fundamentals_simfin": get_m7_fundamentals_simfin,

    # 概念键
    "masters_perspective": None,
}


# 只覆盖已经有独立 optimized 实现，且验证目标明确是“共享缓存 + 输出保持一致”的函数。
# optimized collector 浠嶇劧閫氳繃 registry 璋冨害锛屼絾涓嶅啀鍒囨崲鍒板彟涓€濂楀疄鐜般€?
OPTIMIZED_TOOLS_REGISTRY = dict(TOOLS_REGISTRY)


if __name__ == "__main__":
    print("NDX Agent Tools - Central Registry")
    print("=" * 70)
    print("\nConfiguration Status:")
    print(f"  FRED_API_KEY: {'OK' if get_fred_api_key() else 'MISSING'}")
    print(f"  ALPHAVANTAGE_API_KEY: {'OK' if get_alphavantage_api_key() else 'MISSING'}")
    print(f"  yfinance: {'OK' if YF_AVAILABLE else 'MISSING'}")
    print(f"  pandas_ta: {'OK' if PANDAS_TA_AVAILABLE else 'MISSING'}")
    print(f"\n  Total functions: {len([k for k, v in TOOLS_REGISTRY.items() if v is not None])}")
    print(f"  Optimized overrides: {len([k for k in OPTIMIZED_TOOLS_REGISTRY if OPTIMIZED_TOOLS_REGISTRY[k] is not TOOLS_REGISTRY.get(k)])}")
