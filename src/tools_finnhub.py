# -*- coding: utf-8 -*-
"""
NDX Agent · Finnhub 数据获取模块

Finnhub API 功能：
- 实时股价数据（免费版 60请求/分钟）
- 历史K线数据（1年+历史）
- 基本面数据（PE、ROE、利润率等）
- 财务报表（年报/季报）
- 分析师预测和目标价
- 内部交易数据
- 新闻情绪分析

使用场景：
- L4 估值分析：获取个股基本面数据
- M7 深度分析：获取科技巨头财务数据
- 市场情绪：分析师预测和新闻情绪
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

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def get_finnhub_config() -> Tuple[str, str]:
    """获取Finnhub API配置。"""
    if not is_service_enabled("finnhub"):
        return "", ""
    api_key = get_api_key("finnhub")
    base_url = get_base_url("finnhub") or FINNHUB_BASE_URL
    return api_key, base_url


def finnhub_request(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """
    发送Finnhub API请求。

    参数:
        endpoint: API端点路径（如 'quote', 'stock/metric'）
        params: 额外参数

    返回:
        JSON响应或None（失败时）
    """
    api_key, base_url = get_finnhub_config()
    if not api_key:
        logger.debug("Finnhub API key not configured or service disabled")
        return None

    url = f"{base_url}/{endpoint}"
    request_params = params or {}
    request_params["token"] = api_key

    try:
        response = requests.get(
            url,
            params=request_params,
            proxies=get_requests_proxies(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Finnhub API request failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Finnhub API unexpected error: {e}")
        return None


# =====================================================
# 股价数据
# =====================================================

def get_stock_quote(symbol: str) -> Dict[str, Any]:
    """
    获取实时股票报价。

    **投资含义**：
    - c: 当前价格 - 最新成交价
    - d: 价格变动 - 日内涨跌额
    - dp: 变动百分比 - 日内涨跌幅
    - h/l: 日内最高/最低价
    - o: 开盘价
    - pc: 前收盘价

    返回示例:
    {
        "c": 150.25,      # 当前价格
        "d": 2.5,         # 涨跌额
        "dp": 1.69,       # 涨跌幅%
        "h": 151.0,       # 日内最高
        "l": 148.5,       # 日内最低
        "o": 149.0,       # 开盘价
        "pc": 147.75,     # 前收盘价
        "t": 1699999999   # 时间戳
    }
    """
    data = finnhub_request("quote", {"symbol": symbol})
    if not data:
        return {"error": f"Failed to get quote for {symbol}", "symbol": symbol}

    return {
        "symbol": symbol,
        "current_price": data.get("c"),
        "change": data.get("d"),
        "change_percent": data.get("dp"),
        "high": data.get("h"),
        "low": data.get("l"),
        "open": data.get("o"),
        "previous_close": data.get("pc"),
        "timestamp": data.get("t"),
        "source": "finnhub",
    }


def get_stock_candles(
    symbol: str,
    resolution: str = "D",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    获取历史K线数据（OHLCV）。

    参数:
        symbol: 股票代码（如 'AAPL'）
        resolution: 时间周期 ('1', '5', '15', '30', '60', 'D', 'W', 'M')
        from_date: 开始日期 'YYYY-MM-DD'（默认30天前）
        to_date: 结束日期 'YYYY-MM-DD'（默认今天）

    **投资含义**：
    K线数据是技术分析的基础，用于计算各种指标（RSI、MACD、移动平均线等）。
    Finnhub免费版提供1年+的历史数据。
    """
    # 处理日期
    if to_date:
        to_ts = int(datetime.strptime(to_date, "%Y-%m-%d").timestamp())
    else:
        to_ts = int(datetime.now().timestamp())

    if from_date:
        from_ts = int(datetime.strptime(from_date, "%Y-%m-%d").timestamp())
    else:
        from_ts = int((datetime.now() - timedelta(days=30)).timestamp())

    data = finnhub_request(
        "stock/candle",
        {"symbol": symbol, "resolution": resolution, "from": from_ts, "to": to_ts},
    )

    if not data or data.get("s") != "ok":
        return {"error": f"Failed to get candles for {symbol}", "symbol": symbol}

    # 转换为DataFrame格式
    df = pd.DataFrame({
        "timestamp": data.get("t", []),
        "open": data.get("o", []),
        "high": data.get("h", []),
        "low": data.get("l", []),
        "close": data.get("c", []),
        "volume": data.get("v", []),
    })

    if not df.empty:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")

    return {
        "symbol": symbol,
        "resolution": resolution,
        "data": df.to_dict("records") if not df.empty else [],
        "source": "finnhub",
    }


# =====================================================
# 基本面数据
# =====================================================

def get_company_profile(symbol: str) -> Dict[str, Any]:
    """
    获取公司基本资料。

    **投资含义**：
    了解公司的行业、规模、上市地点等基本信息，
    帮助定位公司在市场中的地位。
    """
    data = finnhub_request("stock/profile2", {"symbol": symbol})
    if not data:
        return {"error": f"Failed to get profile for {symbol}", "symbol": symbol}

    return {
        "symbol": symbol,
        "name": data.get("name"),
        "country": data.get("country"),
        "currency": data.get("currency"),
        "exchange": data.get("exchange"),
        "industry": data.get("finnhubIndustry"),
        "sector": data.get("sector"),
        "market_cap": data.get("marketCapitalization"),  # 百万美元
        "shares_outstanding": data.get("shareOutstanding"),
        "website": data.get("weburl"),
        "ipo_date": data.get("ipo"),
        "logo": data.get("logo"),
        "source": "finnhub",
    }


def get_basic_financials(symbol: str, metric_type: str = "all") -> Dict[str, Any]:
    """
    获取基础财务指标。

    参数:
        metric_type: 'all', 'margin', 'growth', 'valuation', 'financialStrength'

    **投资含义**（第一性原理）：
    这些指标反映公司的盈利能力、成长性和估值水平：

    - 估值指标（PE, PB, PEG）: 衡量股价相对基本面的便宜程度
    - 盈利能力（ROE, ROA, 净利润率）: 衡量公司赚钱效率
    - 成长性（营收增长率, 利润增长率）: 衡量公司扩张速度
    - 财务健康（负债率, 流动比率）: 衡量偿债能力和抗风险能力

    返回示例:
    {
        "pe_ratio": 25.3,           # 市盈率（股价/每股收益）
        "pb_ratio": 8.1,            # 市净率（股价/每股净资产）
        "roe": 0.25,                # 净资产收益率（净利润/净资产）
        "roa": 0.15,                # 总资产收益率（净利润/总资产）
        "net_margin": 0.20,         # 净利润率（净利润/营收）
        "revenue_growth": 0.15,     # 营收增长率
        "eps_growth": 0.12,         # 每股收益增长率
        "debt_equity": 0.5,         # 负债权益比
    }
    """
    data = finnhub_request("stock/metric", {"symbol": symbol, "metric": metric_type})
    if not data:
        return {"error": f"Failed to get metrics for {symbol}", "symbol": symbol}

    metrics = data.get("metric", {})

    # 提取关键指标
    key_metrics = {
        # 估值指标
        "pe_ratio": metrics.get("peBasicExclExtraTTM"),
        "pe_trailing": metrics.get("peTTM"),
        "pe_forward": metrics.get("peExclExtraAnnual"),
        "pb_ratio": metrics.get("pbQuarterly"),
        "ps_ratio": metrics.get("psTTM"),
        "peg_ratio": metrics.get("pegRatio"),
        "ev_ebitda": metrics.get("enterpriseValueOverEBITDATTM"),

        # 盈利能力
        "roe": metrics.get("roeTTM"),
        "roa": metrics.get("roaTTM"),
        "roi": metrics.get("roiTTM"),
        "gross_margin": metrics.get("grossMarginTTM"),
        "operating_margin": metrics.get("operatingMarginTTM"),
        "net_margin": metrics.get("netProfitMarginTTM"),
        "ebitda_margin": metrics.get("ebitdaMarginTTM"),

        # 成长性
        "revenue_growth_3y": metrics.get("revenueGrowth3Y"),
        "revenue_growth_5y": metrics.get("revenueGrowth5Y"),
        "eps_growth_3y": metrics.get("epsGrowth3Y"),
        "eps_growth_5y": metrics.get("epsGrowth5Y"),
        "dividend_growth": metrics.get("dividendGrowth5Y"),

        # 财务健康
        "debt_equity": metrics.get("totalDebt/totalEquityQuarterly"),
        "current_ratio": metrics.get("currentRatioQuarterly"),
        "quick_ratio": metrics.get("quickRatioQuarterly"),
        "interest_coverage": metrics.get("interestCoverageTTM"),

        # 股东回报
        "dividend_yield": metrics.get("dividendYieldIndicatedAnnual"),
        "payout_ratio": metrics.get("payoutRatioTTM"),

        # 效率
        "asset_turnover": metrics.get("assetTurnoverTTM"),
        "inventory_turnover": metrics.get("inventoryTurnoverTTM"),
    }

    return {
        "symbol": symbol,
        "metric_type": metric_type,
        "metrics": {k: v for k, v in key_metrics.items() if v is not None},
        "all_metrics": metrics,  # 保留原始数据供深入分析
        "series": data.get("series", {}),
        "source": "finnhub",
    }


def get_financials_reported(
    symbol: str, statement: str = "bs", freq: str = "annual"
) -> Dict[str, Any]:
    """
    获取财务报表（原始报告格式）。

    参数:
        statement: 'bs'(资产负债表), 'ic'(利润表), 'cf'(现金流量表)
        freq: 'annual'(年报) 或 'quarterly'(季报)

    **投资含义**：
    - 资产负债表(BS): 公司某一时点的财务状况（资产=负债+权益）
    - 利润表(IC): 一段时间内的经营成果（收入-成本=利润）
    - 现金流量表(CF): 现金的流入流出（经营活动、投资活动、筹资活动）
    """
    data = finnhub_request(
        "stock/financials-reported",
        {"symbol": symbol, "statement": statement, "freq": freq},
    )

    if not data:
        return {
            "error": f"Failed to get financials for {symbol}",
            "symbol": symbol,
            "statement": statement,
        }

    statement_names = {"bs": "资产负债表", "ic": "利润表", "cf": "现金流量表"}

    return {
        "symbol": symbol,
        "statement_type": statement,
        "statement_name": statement_names.get(statement, statement),
        "frequency": freq,
        "data": data.get("data", []),
        "source": "finnhub",
    }


# =====================================================
# 分析师数据
# =====================================================

def get_analyst_recommendations(symbol: str) -> Dict[str, Any]:
    """
    获取分析师评级趋势。

    **投资含义**（行为金融学视角）：
    分析师评级反映了专业机构对公司的看法：
    - strongBuy/buy: 看涨，认为股价将上涨
    - hold: 中性，认为股价将横盘
    - sell/strongSell: 看跌，认为股价将下跌

    注意：分析师评级存在乐观偏差（conflict of interest），
    且往往是滞后指标，更适合作为反向指标使用。

    返回示例:
    {
        "period": "2024-01",
        "strong_buy": 10,
        "buy": 15,
        "hold": 8,
        "sell": 2,
        "strong_sell": 0,
        "consensus": "buy"  # 综合评级
    }
    """
    data = finnhub_request("stock/recommendation", {"symbol": symbol})
    if not data or not isinstance(data, list):
        return {
            "error": f"Failed to get recommendations for {symbol}",
            "symbol": symbol,
        }

    # 获取最新的评级
    latest = data[0] if data else {}

    # 计算综合评级
    buy_count = latest.get("strongBuy", 0) + latest.get("buy", 0)
    hold_count = latest.get("hold", 0)
    sell_count = latest.get("sell", 0) + latest.get("strongSell", 0)
    total = buy_count + hold_count + sell_count

    if total > 0:
        buy_pct = buy_count / total
        sell_pct = sell_count / total

        if buy_pct >= 0.6:
            consensus = "强烈买入"
        elif buy_pct >= 0.4:
            consensus = "买入"
        elif sell_pct >= 0.4:
            consensus = "卖出"
        elif sell_pct >= 0.6:
            consensus = "强烈卖出"
        else:
            consensus = "持有"
    else:
        consensus = "无评级"

    return {
        "symbol": symbol,
        "period": latest.get("period"),
        "strong_buy": latest.get("strongBuy"),
        "buy": latest.get("buy"),
        "hold": latest.get("hold"),
        "sell": latest.get("sell"),
        "strong_sell": latest.get("strongSell"),
        "total_analysts": total,
        "consensus": consensus,
        "buy_percentage": round(buy_count / total * 100, 1) if total > 0 else 0,
        "history": data[:12],  # 最近12个月的历史
        "source": "finnhub",
    }


def get_price_target(symbol: str) -> Dict[str, Any]:
    """
    获取分析师目标价。

    **投资含义**：
    分析师目标价反映专业机构对股票合理估值的预期：
    - targetHigh: 最高目标价（最乐观预期）
    - targetLow: 最低目标价（最悲观预期）
    - targetMean: 平均目标价（共识预期）
    - targetMedian: 中位数目标价（排除极端值影响）

    当前价格相对目标价的位置可以判断市场预期：
    - 当前价 > 目标价: 可能高估，或分析师过于保守
    - 当前价 < 目标价: 可能低估，或分析师过于乐观
    """
    data = finnhub_request("stock/price-target", {"symbol": symbol})
    if not data:
        return {
            "error": f"Failed to get price target for {symbol}",
            "symbol": symbol,
        }

    current = data.get("lastUpdated")
    target_mean = data.get("targetMean")

    # 计算潜在涨跌幅
    if current and target_mean:
        upside = round((target_mean - current) / current * 100, 2)
    else:
        upside = None

    return {
        "symbol": symbol,
        "current_price": current,
        "target_high": data.get("targetHigh"),
        "target_low": data.get("targetLow"),
        "target_mean": target_mean,
        "target_median": data.get("targetMedian"),
        "number_of_analysts": data.get("numberOfAnalysts"),
        "upside_potential": upside,  # 上涨空间百分比
        "source": "finnhub",
    }


def get_earnings_estimates(symbol: str, freq: str = "quarterly") -> Dict[str, Any]:
    """
    获取盈利预测（EPS预测）。

    **投资含义**：
    EPS（每股收益）预测反映市场对公司未来盈利的预期。
    实际EPS vs 预期EPS是股价短期波动的关键驱动因素：
    - 实际 > 预期（ beat ）: 通常股价上涨
    - 实际 < 预期（ miss ）: 通常股价下跌
    """
    data = finnhub_request("stock/eps-estimate", {"symbol": symbol, "freq": freq})
    if not data:
        return {
            "error": f"Failed to get EPS estimates for {symbol}",
            "symbol": symbol,
        }

    return {
        "symbol": symbol,
        "frequency": freq,
        "estimates": data.get("data", []),
        "source": "finnhub",
    }


# =====================================================
# 另类数据
# =====================================================

def get_news_sentiment(symbol: str) -> Dict[str, Any]:
    """
    获取新闻情绪分析。

    **投资含义**（行为金融学）：
    新闻情绪反映市场参与者的情绪状态：
    - buzz: 新闻热度（文章数量vs历史平均）
    - sentiment: 情绪分数（-1到1，负为看空，正为看多）
    - 行业/公司情绪对比: 相对表现

    情绪极端值往往是反向指标：过度乐观可能预示顶部，过度悲观可能预示底部。
    """
    data = finnhub_request("news-sentiment", {"symbol": symbol})
    if not data:
        return {
            "error": f"Failed to get sentiment for {symbol}",
            "symbol": symbol,
        }

    buzz = data.get("buzz", {})
    sentiment = data.get("sentiment", {})
    scores = data.get("sentimentScores", {})

    return {
        "symbol": symbol,
        "buzz_score": buzz.get("buzz"),  # 新闻热度
        "buzz_change": buzz.get("buzzChange"),  # 热度变化
        "articles_in_last_week": buzz.get("articlesInLastWeek"),
        "sentiment_score": sentiment.get("bearishPercent"),  # 看空比例
        "sector_sentiment": data.get("sectorAverageBullishPercent"),
        "company_vs_sector": data.get("companyNewsScore"),
        # 详细分数
        "bearish_percent": scores.get("bearishPercent"),
        "bullish_percent": scores.get("bullishPercent"),
        "neutral_percent": scores.get("neutralPercent"),
        "source": "finnhub",
    }


def get_insider_transactions(symbol: str, from_date: Optional[str] = None, to_date: Optional[str] = None) -> Dict[str, Any]:
    """
    获取内部交易数据。

    **投资含义**（信息不对称理论）：
    内部人士（高管、董事、大股东）拥有普通投资者无法获得的信息，
    其交易行为往往预示公司前景：
    - 大量买入: 内部人士看好公司前景（积极信号）
    - 大量卖出: 可能是财务自由需求，也可能是看淡前景（需结合语境）

    注意：需区分计划交易（10b5-1计划）和自主交易。
    """
    params = {"symbol": symbol}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    data = finnhub_request("stock/insider-transactions", params)
    if not data:
        return {
            "error": f"Failed to get insider transactions for {symbol}",
            "symbol": symbol,
        }

    transactions = data.get("data", [])

    # 统计买卖方向
    buy_count = sum(1 for t in transactions if t.get("change") > 0)
    sell_count = sum(1 for t in transactions if t.get("change") < 0)

    # 统计交易金额（近似）
    total_buy_value = sum(
        t.get("change", 0) * t.get("transactionPrice", 0)
        for t in transactions
        if t.get("change", 0) > 0
    )
    total_sell_value = sum(
        abs(t.get("change", 0)) * t.get("transactionPrice", 0)
        for t in transactions
        if t.get("change", 0) < 0
    )

    return {
        "symbol": symbol,
        "total_transactions": len(transactions),
        "buy_transactions": buy_count,
        "sell_transactions": sell_count,
        "buy_value": round(total_buy_value, 2) if total_buy_value else 0,
        "sell_value": round(total_sell_value, 2) if total_sell_value else 0,
        "net_value": round(total_buy_value - total_sell_value, 2),
        "transactions": transactions[:20],  # 最近20笔
        "source": "finnhub",
    }


# =====================================================
# 市场数据
# =====================================================

def get_market_news(category: str = "general", min_id: int = 0) -> Dict[str, Any]:
    """
    获取市场新闻。

    参数:
        category: 'general', 'forex', 'crypto', 'merger'
    """
    data = finnhub_request("news", {"category": category, "minId": min_id})
    if not data:
        return {"error": "Failed to get market news"}

    return {
        "category": category,
        "article_count": len(data),
        "articles": data[:10],  # 最近10条
        "source": "finnhub",
    }


def get_company_news(symbol: str, from_date: Optional[str] = None, to_date: Optional[str] = None) -> Dict[str, Any]:
    """
    获取公司相关新闻。
    """
    params = {"symbol": symbol}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    data = finnhub_request("company-news", params)
    if not data:
        return {"error": f"Failed to get news for {symbol}", "symbol": symbol}

    return {
        "symbol": symbol,
        "article_count": len(data),
        "articles": data[:10],
        "source": "finnhub",
    }


# =====================================================
# 综合数据获取函数
# =====================================================

def get_stock_full_analysis(symbol: str) -> Dict[str, Any]:
    """
    获取股票的综合分析数据（整合多个端点）。

    **使用场景**：L4层个股深度分析

    返回包含：
    - 实时报价
    - 公司资料
    - 基本面指标
    - 分析师评级
    - 目标价
    - 新闻情绪
    """
    return {
        "symbol": symbol,
        "quote": get_stock_quote(symbol),
        "profile": get_company_profile(symbol),
        "financials": get_basic_financials(symbol),
        "recommendations": get_analyst_recommendations(symbol),
        "price_target": get_price_target(symbol),
        "sentiment": get_news_sentiment(symbol),
        "source": "finnhub",
        "timestamp": datetime.now().isoformat(),
    }


# =====================================================
# NDX 专用函数
# =====================================================

M7_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

def get_m7_finnhub_analysis() -> Dict[str, Any]:
    """
    获取Magnificent 7的综合分析。

    **投资含义**（集中度风险）：
    M7占纳斯达克100权重的50%左右，其表现直接决定指数走势。
    通过对比M7的基本面，可以判断：
    1. 是否有成员估值过高（泡沫风险）
    2. 是否有成员基本面恶化（领头羊风险）
    3. 整体盈利增长趋势（指数盈利支撑）
    """
    results = {}

    for symbol in M7_SYMBOLS:
        try:
            results[symbol] = {
                "quote": get_stock_quote(symbol),
                "financials": get_basic_financials(symbol),
                "recommendations": get_analyst_recommendations(symbol),
                "price_target": get_price_target(symbol),
            }
            time.sleep(0.1)  # 避免触发频率限制
        except Exception as e:
            logger.warning(f"Failed to get data for {symbol}: {e}")
            results[symbol] = {"error": str(e)}

    # 汇总分析
    pe_ratios = []
    for symbol, data in results.items():
        if "financials" in data and "metrics" in data["financials"]:
            pe = data["financials"]["metrics"].get("pe_ratio")
            if pe:
                pe_ratios.append({"symbol": symbol, "pe": pe})

    pe_ratios.sort(key=lambda x: x["pe"])

    return {
        "companies": results,
        "summary": {
            "pe_ranking": pe_ratios,  # 按PE排序（便宜到贵）
            "highest_pe": pe_ratios[-1] if pe_ratios else None,
            "lowest_pe": pe_ratios[0] if pe_ratios else None,
            "average_pe": round(sum(r["pe"] for r in pe_ratios) / len(pe_ratios), 2) if pe_ratios else None,
        },
        "source": "finnhub",
        "timestamp": datetime.now().isoformat(),
    }


# =====================================================
# 导出函数供其他模块使用
# =====================================================

__all__ = [
    # 股价数据
    "get_stock_quote",
    "get_stock_candles",
    # 基本面数据
    "get_company_profile",
    "get_basic_financials",
    "get_financials_reported",
    # 分析师数据
    "get_analyst_recommendations",
    "get_price_target",
    "get_earnings_estimates",
    # 另类数据
    "get_news_sentiment",
    "get_insider_transactions",
    # 市场数据
    "get_market_news",
    "get_company_news",
    # 综合
    "get_stock_full_analysis",
    "get_m7_finnhub_analysis",
]
