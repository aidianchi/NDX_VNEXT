# -*- coding: utf-8 -*-
"""
NDX Agent · Simfin 数据获取模块

Simfin API 功能：
- 标准化财务报表（年报/季报）
- 派生指标和信号（自动计算的财务比率）
- 股价数据（日度/周度/月度）
- 公司基本信息
- 批量数据下载（支持日期过滤）

使用场景：
- L4 估值分析：获取标准化基本面数据
- M7 深度分析：对比科技巨头财务表现
- 历史分析：10年+财务历史数据

API限制：免费版 2请求/秒，需要控制调用频率
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from functools import wraps

try:
    from .tools_common import (
        get_api_key, get_base_url, get_requests_proxies, is_service_enabled,
        ts_manager, YF_AVAILABLE, PANDAS_TA_AVAILABLE
    )
except ImportError:
    from tools_common import (
        get_api_key, get_base_url, get_requests_proxies, is_service_enabled,
        ts_manager, YF_AVAILABLE, PANDAS_TA_AVAILABLE
    )

import requests
import pandas as pd

logger = logging.getLogger(__name__)

# =====================================================
# 配置与常量
# =====================================================

SIMFIN_BASE_URL = "https://backend.simfin.com/api/v3"
RATE_LIMIT_DELAY = 0.5  # 免费版 2 req/sec，设置0.5秒间隔

_last_request_time = 0


def _rate_limited_request():
    """控制请求频率，避免触发限制。"""
    global _last_request_time
    current_time = time.time()
    elapsed = current_time - _last_request_time
    if elapsed < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - elapsed)
    _last_request_time = time.time()


def get_simfin_config() -> Tuple[str, str]:
    """获取Simfin API配置。"""
    if not is_service_enabled("simfin"):
        return "", ""
    api_key = get_api_key("simfin")
    base_url = get_base_url("simfin") or SIMFIN_BASE_URL
    return api_key, base_url


def simfin_request(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """
    发送Simfin API请求（带频率控制）。

    参数:
        endpoint: API端点路径
        params: 额外参数

    返回:
        JSON响应或None（失败时）
    """
    api_key, base_url = get_simfin_config()
    if not api_key:
        logger.debug("Simfin API key not configured or service disabled")
        return None

    # 频率控制
    _rate_limited_request()

    url = f"{base_url}/{endpoint}"
    request_params = params or {}
    request_params["api-key"] = api_key

    try:
        response = requests.get(
            url,
            params=request_params,
            proxies=get_requests_proxies(),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Simfin API request failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Simfin API unexpected error: {e}")
        return None


# =====================================================
# 公司搜索与信息
# =====================================================

def search_company(query: str) -> Dict[str, Any]:
    """
    搜索公司。

    **投资含义**：
    通过公司名称或代码找到对应的Simfin ID，用于后续数据查询。
    """
    data = simfin_request("companies/search", {"query": query})
    if not data:
        return {"error": f"Failed to search for '{query}'", "query": query}

    return {
        "query": query,
        "results": data if isinstance(data, list) else [],
        "source": "simfin",
    }


def get_company_info(ticker: str) -> Dict[str, Any]:
    """
    获取公司基本信息。

    **投资含义**：
    了解公司的行业分类、上市交易所、员工数等基本信息，
    帮助构建公司的"身份画像"。
    """
    # 先搜索获取company ID
    search_result = search_company(ticker)
    if "error" in search_result or not search_result.get("results"):
        return {"error": f"Company not found: {ticker}", "ticker": ticker}

    company = search_result["results"][0]
    company_id = company.get("id")

    if not company_id:
        return {"error": f"No company ID for {ticker}", "ticker": ticker}

    return {
        "ticker": ticker,
        "simfin_id": company_id,
        "name": company.get("name"),
        "sector": company.get("sector"),
        "industry": company.get("industry"),
        "exchange": company.get("exchange"),
        "employees": company.get("employees"),
        "website": company.get("website"),
        "source": "simfin",
    }


# =====================================================
# 财务报表
# =====================================================

def get_financial_statements(
    ticker: str,
    statement_type: str = "pl",  # pl: 利润表, bs: 资产负债表, cf: 现金流量表
    variant: str = "annual",  # annual 或 quarterly
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    获取财务报表（标准化格式）。

    参数:
        statement_type: 'pl'(利润表), 'bs'(资产负债表), 'cf'(现金流量表)
        variant: 'annual'(年报) 或 'quarterly'(季报)
        start_date: 开始日期 'YYYY-MM-DD'
        end_date: 结束日期 'YYYY-MM-DD'

    **投资含义**（第一性原理）：
    财务报表是企业经营的真实记录，三个报表构成完整画面：

    - 利润表(PL): 展示"赚不赚钱"（收入、成本、利润的时间切片）
    - 资产负债表(BS): 展示"家底厚不厚"（资产=负债+权益的时点快照）
    - 现金流量表(CF): 展示"真金白银"（经营/投资/筹资的现金流动）

    关键分析维度：
    1. 成长性：营收增长率、利润增长率
    2. 盈利能力：毛利率、净利率、ROE、ROA
    3. 财务健康：负债率、流动比率、自由现金流
    4. 营运效率：资产周转率、存货周转率
    """
    # 映射statement type
    type_mapping = {
        "pl": "profit-loss",
        "bs": "balance-sheet",
        "cf": "cash-flow",
        "profit-loss": "profit-loss",
        "balance-sheet": "balance-sheet",
        "cash-flow": "cash-flow",
    }

    simfin_type = type_mapping.get(statement_type.lower())
    if not simfin_type:
        return {
            "error": f"Invalid statement type: {statement_type}",
            "valid_types": list(type_mapping.keys()),
        }

    # 构建请求参数
    params = {"type": variant}
    if start_date:
        params["start"] = start_date
    if end_date:
        params["end"] = end_date

    data = simfin_request(f"companies/ticker/{ticker}/statements/standardised", params)

    if not data:
        return {
            "error": f"Failed to get {statement_type} for {ticker}",
            "ticker": ticker,
            "statement_type": statement_type,
        }

    # 提取指定报表类型
    statements = data.get("statements", {}).get(simfin_type, {})

    statement_names = {
        "profit-loss": "利润表",
        "balance-sheet": "资产负债表",
        "cash-flow": "现金流量表",
    }

    return {
        "ticker": ticker,
        "company_name": data.get("name"),
        "statement_type": simfin_type,
        "statement_name": statement_names.get(simfin_type, simfin_type),
        "variant": variant,
        "currency": data.get("currency"),
        "data": statements,
        "source": "simfin",
    }


def get_all_financials(
    ticker: str,
    variant: str = "annual",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    获取全部三张财务报表。

    **使用场景**：深度财务分析，需要三张表勾稽关系验证
    """
    return {
        "ticker": ticker,
        "income_statement": get_financial_statements(ticker, "pl", variant, start_date, end_date),
        "balance_sheet": get_financial_statements(ticker, "bs", variant, start_date, end_date),
        "cash_flow": get_financial_statements(ticker, "cf", variant, start_date, end_date),
        "source": "simfin",
        "timestamp": datetime.now().isoformat(),
    }


# =====================================================
# 派生指标和信号
# =====================================================

def get_derived_signals(
    ticker: str,
    variant: str = "annual",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    获取派生财务指标（自动计算的比率和信号）。

    **投资含义**：
    Simfin预计算的财务比率，避免手动计算错误：

    - 估值比率：P/E, P/B, P/S, EV/EBITDA
    - 盈利能力：ROE, ROA, 毛利率, 营业利润率
    - 成长性：营收增长率, EPS增长率
    - 财务健康：负债率, 流动比率, 利息保障倍数
    - 效率指标：资产周转率, 存货周转率

    **注意**：这些是基于财务报表的历史数据计算，不是实时估值。
    """
    params = {"type": variant}
    if start_date:
        params["start"] = start_date
    if end_date:
        params["end"] = end_date

    data = simfin_request(f"companies/ticker/{ticker}/derived/signals", params)

    if not data:
        return {
            "error": f"Failed to get derived signals for {ticker}",
            "ticker": ticker,
        }

    return {
        "ticker": ticker,
        "company_name": data.get("name"),
        "variant": variant,
        "currency": data.get("currency"),
        "signals": data.get("signals", {}),
        "source": "simfin",
    }


def get_key_metrics(ticker: str, variant: str = "annual") -> Dict[str, Any]:
    """
    获取关键财务指标（最新一期）。

    **使用场景**：快速了解公司财务健康状况
    """
    signals_data = get_derived_signals(ticker, variant)

    if "error" in signals_data:
        return signals_data

    signals = signals_data.get("signals", {})

    # 提取最近一期的指标
    # Simfin返回的是时间序列格式
    key_metrics = {
        "ticker": ticker,
        "variant": variant,
        "metrics": {},
        "source": "simfin",
    }

    if signals:
        # 获取最新的指标值
        for metric_name, values in signals.items():
            if isinstance(values, dict) and values:
                # 取最新的日期
                latest_date = max(values.keys())
                key_metrics["metrics"][metric_name] = {
                    "value": values[latest_date],
                    "date": latest_date,
                }

    return key_metrics


# =====================================================
# 股价数据
# =====================================================

def get_share_prices(
    ticker: str,
    variant: str = "daily",  # daily, weekly, monthly
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    获取历史股价数据。

    **投资含义**：
    股价数据是技术分析的基础，也是计算收益率的前提。

    Simfin股价数据特点：
    - 包含调整后的价格（考虑分红、拆股）
    - 包含成交量
    - 数据标准化，便于跨公司比较
    """
    params = {"type": variant}
    if start_date:
        params["start"] = start_date
    if end_date:
        params["end"] = end_date

    data = simfin_request(f"companies/ticker/{ticker}/shares/prices", params)

    if not data:
        return {
            "error": f"Failed to get share prices for {ticker}",
            "ticker": ticker,
        }

    prices = data.get("prices", {})

    # 转换为列表格式
    price_list = []
    for date, values in prices.items():
        if isinstance(values, dict):
            price_list.append({
                "date": date,
                "open": values.get("open"),
                "high": values.get("high"),
                "low": values.get("low"),
                "close": values.get("close"),
                "adj_close": values.get("adjClose"),
                "volume": values.get("volume"),
            })

    # 按日期排序
    price_list.sort(key=lambda x: x["date"])

    return {
        "ticker": ticker,
        "company_name": data.get("name"),
        "variant": variant,
        "currency": data.get("currency"),
        "price_count": len(price_list),
        "date_range": {
            "start": price_list[0]["date"] if price_list else None,
            "end": price_list[-1]["date"] if price_list else None,
        },
        "prices": price_list,
        "source": "simfin",
    }


def get_current_valuation(ticker: str) -> Dict[str, Any]:
    """
    获取当前估值指标。

    **投资含义**（价值投资核心）：
    估值指标帮助判断"贵不贵"：
    - P/E < 行业平均: 可能被低估
    - P/E > 行业平均: 可能被高估（或增长预期更高）
    - PEG < 1: 性价比较高（增长相对于估值便宜）

    **注意**：估值只是参考，不是买卖信号。高估值可能合理（护城河、增长），
    低估值可能陷阱（价值陷阱）。
    """
    # 获取最新派生指标
    signals = get_derived_signals(ticker, variant="annual")

    if "error" in signals:
        return signals

    signals_data = signals.get("signals", {})

    # 提取估值相关指标
    valuation_metrics = [
        "P/E", "P/B", "P/S", "EV/EBITDA", "EV/Sales",
        "Dividend Yield", "P/FCF", "PEG Ratio"
    ]

    latest_valuation = {}
    for metric in valuation_metrics:
        if metric in signals_data:
            values = signals_data[metric]
            if isinstance(values, dict) and values:
                latest_date = max(values.keys())
                latest_valuation[metric] = {
                    "value": values[latest_date],
                    "date": latest_date,
                }

    return {
        "ticker": ticker,
        "valuation_metrics": latest_valuation,
        "interpretation": {
            "P/E": "市盈率：股价/每股收益，越低通常越便宜",
            "P/B": "市净率：股价/每股净资产，<1可能低估",
            "P/S": "市销率：股价/每股营收，适用于亏损公司",
            "EV/EBITDA": "企业价值倍数：考虑债务的估值指标",
            "Dividend Yield": "股息率：现金分红/股价，收益型指标",
        },
        "source": "simfin",
    }


# =====================================================
# 批量数据获取
# =====================================================

def get_companies_list(market: str = "us") -> Dict[str, Any]:
    """
    获取Simfin覆盖的公司列表。

    **用途**：了解数据覆盖范围，批量分析准备
    """
    data = simfin_request("companies/list", {"market": market})

    if not data:
        return {"error": f"Failed to get companies list for market: {market}"}

    companies = data if isinstance(data, list) else []

    return {
        "market": market,
        "company_count": len(companies),
        "companies": companies[:50],  # 返回前50个
        "source": "simfin",
    }


# =====================================================
# NDX 专用函数
# =====================================================

M7_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

def get_m7_simfin_analysis() -> Dict[str, Any]:
    """
    获取Magnificent 7的Simfin综合分析。

    **投资含义**：
    对比M7的财务指标，识别：
    1. 估值分化：哪些相对便宜/贵
    2. 盈利质量：ROE、ROA对比
    3. 财务健康：负债水平对比
    4. 成长性：营收/利润增长趋势
    """
    results = {}

    for ticker in M7_TICKERS:
        try:
            results[ticker] = {
                "info": get_company_info(ticker),
                "valuation": get_current_valuation(ticker),
                "key_metrics": get_key_metrics(ticker),
            }
            time.sleep(RATE_LIMIT_DELAY)  # 频率控制
        except Exception as e:
            logger.warning(f"Failed to get Simfin data for {ticker}: {e}")
            results[ticker] = {"error": str(e)}

    # 构建对比分析
    comparison = {
        "pe_comparison": [],
        "pb_comparison": [],
        "roe_comparison": [],
        "revenue_growth_comparison": [],
    }

    for ticker, data in results.items():
        if "error" in data:
            continue

        valuation = data.get("valuation", {}).get("valuation_metrics", {})
        metrics = data.get("key_metrics", {}).get("metrics", {})

        # P/E 对比
        pe_data = valuation.get("P/E", {})
        if pe_data and pe_data.get("value"):
            comparison["pe_comparison"].append({
                "ticker": ticker,
                "pe": pe_data["value"],
            })

        # P/B 对比
        pb_data = valuation.get("P/B", {})
        if pb_data and pb_data.get("value"):
            comparison["pb_comparison"].append({
                "ticker": ticker,
                "pb": pb_data["value"],
            })

        # ROE 对比
        roe_data = metrics.get("Return on Equity", {})
        if roe_data and roe_data.get("value"):
            comparison["roe_comparison"].append({
                "ticker": ticker,
                "roe": roe_data["value"],
            })

    # 排序
    for key in comparison:
        comparison[key].sort(key=lambda x: list(x.values())[1] if list(x.values())[1] else 0)

    return {
        "companies": results,
        "comparison": comparison,
        "source": "simfin",
        "timestamp": datetime.now().isoformat(),
    }


def get_m7_fundamentals_simfin() -> Dict[str, Any]:
    """
    获取M7的完整基本面数据（三张表+派生指标）。

    **使用场景**：M7深度财务分析
    **注意**：此函数会发起多次API调用，耗时较长
    """
    results = {}

    for ticker in M7_TICKERS:
        try:
            results[ticker] = get_all_financials(ticker, variant="annual")
            time.sleep(RATE_LIMIT_DELAY)
        except Exception as e:
            logger.warning(f"Failed to get fundamentals for {ticker}: {e}")
            results[ticker] = {"error": str(e)}

    return {
        "companies": results,
        "source": "simfin",
        "timestamp": datetime.now().isoformat(),
    }


# =====================================================
# 导出函数
# =====================================================

__all__ = [
    # 公司信息
    "search_company",
    "get_company_info",
    "get_companies_list",
    # 财务报表
    "get_financial_statements",
    "get_all_financials",
    # 派生指标
    "get_derived_signals",
    "get_key_metrics",
    "get_current_valuation",
    # 股价数据
    "get_share_prices",
    # M7专用
    "get_m7_simfin_analysis",
    "get_m7_fundamentals_simfin",
]
