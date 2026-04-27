# tools_L4.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第4层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

# =====================================================
# 第4层函数
# =====================================================

def get_crowdedness_dashboard(end_date: str = None) -> Dict[str, Any]:
    """
    获取拥挤度仪表盘 - V3精简版（专注仓位拥挤度）
    
    核心指标（移除VIX/VXN重复，专注仓位拥挤度）：
    1. SKEW指数：尾部风险溢价（黑天鹅担忧程度）
    2. QQQ Put/Call比率：期权市场的看空/看多情绪对比
    3. QQQ空仓率：做空仓位的拥挤程度
    
    数据源策略：
    - SKEW: yfinance (^SKEW) - 可靠
    - Put/Call: yfinance期权链（主） + AKShare（备用）
    - 空仓率: yfinance info - 通常为None（ETF不提供）
    
    架构说明：
    - VIX和VXN/VIX已在第二层独立存在，此处不再重复
    - 遵循"单一事实来源"原则（PROJECT_ARCHITECTURE.md 原则2）
    """
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    crowdedness_data = {}
    print("  - 获取拥挤度仪表盘...", end="", flush=True)

    # 1. SKEW Index (尾部风险指标) - 使用yfinance获取^SKEW
    skew_val = None
    skew_date = None
    if YF_AVAILABLE:
        try:
            skew_hist = get_yf_ticker_history_with_retry("^SKEW", period="5d", attempts=3, pause_seconds=1.0)
            if not skew_hist.empty:
                skew_val = round(skew_hist['Close'].iloc[-1], 2)
                skew_date = skew_hist.index[-1].strftime("%Y-%m-%d")
        except Exception as e:
            logging.warning(f"SKEW from yfinance failed: {e}")
    
    crowdedness_data["skew_index"] = {
        "value": skew_val,
        "date": skew_date,
        "source": "yfinance (^SKEW)" if skew_val else "unavailable",
        "interpretation": ">150: 尾部风险溢价高 (市场担忧黑天鹅); <120: 尾部风险溢价低"
    }

    # 2. QQQ Put/Call Ratio (基于期权持仓量) - yfinance主源 + AKShare备用
    pc_ratio = None
    pc_source = "unavailable"
    pc_notes = ""
    
    if YF_AVAILABLE:
        try:
            opt_date, opt_chain = get_yf_option_chain_with_retry("QQQ", attempts=3, pause_seconds=1.0)

            # 取最近到期的期权合约

            put_oi = opt_chain.puts['openInterest'].sum()
            call_oi = opt_chain.calls['openInterest'].sum()
            
            if call_oi > 0 and put_oi > 0:
                pc_ratio = round(put_oi / call_oi, 2)
                pc_source = "yfinance"
                pc_notes = f"基于到期日: {opt_date} 的期权持仓量"
            else:
                raise Exception("OpenInterest data is zero")
        except Exception as e:
            logging.warning(f"yfinance Put/Call failed: {e}, trying AKShare fallback...")
            # 尝试AKShare备用源
            try:
                try:
                    from .tools_akshare import get_qqq_put_call_akshare
                except ImportError:
                    from tools_akshare import get_qqq_put_call_akshare
                akshare_result = get_qqq_put_call_akshare(end_date=end_date)
                if akshare_result and akshare_result.get("value"):
                    pc_ratio = akshare_result["value"]
                    pc_source = "akshare (fallback)"
                    pc_notes = akshare_result.get("notes", "")
            except Exception as ak_error:
                logging.warning(f"AKShare Put/Call fallback also failed: {ak_error}")
                pc_notes = f"yfinance和AKShare均失败: {str(e)[:30]}"

    crowdedness_data["qqq_put_call_ratio_oi"] = {
        "value": pc_ratio,
        "date": effective_date.strftime("%Y-%m-%d"),
        "source": pc_source,
        "notes": pc_notes if pc_notes else "期权数据获取失败",
        "interpretation": ">1.2: 看空情绪主导; <0.8: 看多情绪主导"
    }

    # 3. QQQ空仓率 (Short Interest)
    if YF_AVAILABLE:
        try:
            qqq_info = get_yf_ticker_info_with_retry("QQQ", attempts=3, pause_seconds=1.0)
            short_percent = qqq_info.get("shortPercentOfFloat")
            crowdedness_data["qqq_short_interest_percent"] = {
                "value": round(short_percent * 100, 2) if short_percent else None,
                "date": effective_date.strftime("%Y-%m-%d"),
                "source": "yfinance",
                "interpretation": ">2%: 空仓拥挤 (看空情绪浓); <1%: 空仓稀少 (看空情绪弱)",
                "notes": "ETF通常不提供空仓数据，此字段可能为空"
            }
        except Exception as e:
            crowdedness_data["qqq_short_interest_percent"] = {
                "value": None,
                "error": f"Failed to fetch: {str(e)[:30]}",
                "source": "failed",
                "notes": "ETF通常不提供空仓数据"
            }
    else:
        crowdedness_data["qqq_short_interest_percent"] = {
            "value": None,
            "source": "unavailable",
            "notes": "yfinance未安装"
        }

    print(" [OK]")
    return {
        "name": "Crowdedness Dashboard",
        "value": crowdedness_data,
        "date": effective_date.strftime("%Y-%m-%d"),
        "source_name": "Mixed (yfinance)",
        "notes": "拥挤度核心指标：SKEW(尾部风险)、VIX(恐慌程度)、VXN/VIX(科技股相对压力)、Put/Call比率、空仓率"
    }


def calculate_weighted_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """计算NDX成分股市值加权指标（含FCF收益率）"""
    if df.empty:
        return {}

    metrics = {}

    # 加权Forward PE与盈利收益率
    valid_pe = df.dropna(subset=['forward_pe', 'weight'])
    valid_pe = valid_pe[valid_pe['forward_pe'] > 0]  # 过滤异常值
    if not valid_pe.empty:
        metrics['weighted_forward_pe'] = round(np.average(valid_pe['forward_pe'], weights=valid_pe['weight']), 2)
        metrics['weighted_earnings_yield'] = round((1 / metrics['weighted_forward_pe']) * 100, 2)

    # 加权FCF收益率（V5新增）
    valid_fcf = df.dropna(subset=['fcf_yield', 'weight'])
    if not valid_fcf.empty:
        metrics['weighted_fcf_yield'] = round(np.average(valid_fcf['fcf_yield'], weights=valid_fcf['weight']), 2)

    # 加权市净率
    valid_pb = df.dropna(subset=['price_to_book', 'weight'])
    valid_pb = valid_pb[valid_pb['price_to_book'] > 0]
    if not valid_pb.empty:
        metrics['weighted_price_to_book'] = round(np.average(valid_pb['price_to_book'], weights=valid_pb['weight']), 2)

    return metrics


def get_ndx_components_data_yf_v5(end_date: str = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    V5.6版：用yfinance获取NDX100成分股数据（增强容错）
    注意：此函数获取最新的基本面数据，end_date参数仅用于获取对应日期的成分股列表，
    因为yfinance的.info不直接支持历史时点基本面查询。
    """
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    # **修改点**: 调用新的动态函数获取成分股
    ndx100_components = get_ndx100_components(end_date=effective_date.strftime("%Y-%m-%d"))
    
    if not YF_AVAILABLE:
        return pd.DataFrame(), {"error": "yfinance not available", "successful": 0, "total_tickers": len(ndx100_components)}

    data_list = []
    failed_tickers = []
    print(f"开始获取 {len(ndx100_components)} 支NDX100成分股数据 (V5.6)...")

    for i, ticker in enumerate(ndx100_components):
        # 跳过已知问题股票
        if ticker in TICKER_REPLACEMENTS and TICKER_REPLACEMENTS[ticker] is None:
            continue

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # 如果获取失败，尝试替换股票
            if not info or 'marketCap' not in info or info.get('marketCap', 0) <= 0:
                if ticker in TICKER_REPLACEMENTS and TICKER_REPLACEMENTS[ticker]:
                    ticker = TICKER_REPLACEMENTS[ticker]
                    stock = yf.Ticker(ticker)
                    info = stock.info
                else:
                    failed_tickers.append(ticker)
                    continue

            # 过滤无市值的标的
            market_cap = info.get('marketCap', 0)
            if not market_cap or market_cap <= 0:
                failed_tickers.append(ticker)
                continue

            # 提取核心财务指标
            data_list.append({
                'ticker': ticker,
                'market_cap': market_cap,
                'forward_pe': info.get('forwardPE'),
                'trailing_pe': info.get('trailingPE'),
                'price_to_book': info.get('priceToBook'),
                # 自由现金流与FCF收益率（V5新增）
                'fcf': info.get('freeCashflow'),
                'fcf_yield': (info.get('freeCashflow') / market_cap) * 100 if info.get('freeCashflow') else None,
                'weight': None  # 后续计算市值权重
            })

            # 进度提示
            if (i + 1) % 20 == 0:
                print(f"  已处理 {i + 1}/{len(ndx100_components)} 个NDX成分股")
            time.sleep(0.05)  # 避免请求过于频繁

        except Exception as e:
            if ticker not in failed_tickers:
                failed_tickers.append(ticker)
            continue

    # 转换为DataFrame并计算权重
    df = pd.DataFrame(data_list)
    total_market_cap = df['market_cap'].sum()
    if total_market_cap > 0:
        df['weight'] = df['market_cap'] / total_market_cap

    # 统计信息
    stats = {
        'successful': len(df),
        'total_tickers': len(ndx100_components),
        'failed': len(failed_tickers),
        'coverage': round(len(df) / len(ndx100_components), 3) if len(ndx100_components) > 0 else 0,
        'failed_tickers': failed_tickers
    }
    print(f"NDX成分股数据获取完成：成功{len(df)}/{len(ndx100_components)}，失败{len(failed_tickers)}/{len(ndx100_components)}")
    return df, stats


def get_ndx_pe_and_earnings_yield_av(end_date: str = None) -> Dict[str, Any]:
    """
    备用方案：用Alpha Vantage的QQQ数据代理NDX基本面（简化版）
    注意：此函数获取最新的基本面数据，end_date参数仅用于保持签名一致性。
    """
    alphavantage_api_key = get_alphavantage_api_key()
    if not alphavantage_api_key:
        return {
            "name": "NDX P/E and Earnings Yield",
            "value": None,
            "notes": "Alpha Vantage API Key not available"
        }

    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    try:
        # 获取QQQ基本面数据（代理NDX）
        params = {
            "function": "OVERVIEW",
            "symbol": "QQQ",
            "apikey": alphavantage_api_key
        }
        data = safe_request(get_alphavantage_base_url(), params)
        if not data or "PERatio" not in data:
            raise Exception("No QQQ data from Alpha Vantage")

        # 提取核心指标
        pe = float(data.get("PERatio")) if data.get("PERatio") else None
        forward_pe = float(data.get("ForwardPE")) if data.get("ForwardPE") else None
        earnings_yield = (1 / forward_pe) * 100 if forward_pe and forward_pe > 0 else None

        return {
            "name": "NDX P/E and Earnings Yield (QQQ Proxy)",
            "series_id": "NDX_PROXY_QQQ",
            "value": {
                "PE": pe,
                "ForwardPE": forward_pe,
                "EarningsYield": round(earnings_yield, 2) if earnings_yield else None,
                "FCFYield": None,  # Alpha Vantage无QQQ FCF数据
                "Coverage": {"note": "QQQ代理NDX，非完整成分股计算"}
            },
            "unit": "ratio/percent",
            "date": effective_date.strftime("%Y-%m-%d"),
            "source_name": "Alpha Vantage (QQQ Proxy)",
            "notes": "因yfinance不可用，使用QQQ数据代理NDX基本面"
        }
    except Exception as e:
        return {
            "name": "NDX P/E and Earnings Yield",
            "value": None,
            "notes": f"Alpha Vantage fallback failed: {str(e)[:50]}"
        }


def get_ndx_pe_and_earnings_yield(end_date: str = None) -> Dict[str, Any]:
    """获取NDX100的P/E、盈利收益率与FCF收益率（V5.6修复版）"""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    # 优先使用yfinance完整成分股计算
    if YF_AVAILABLE:
        try:
            df, stats = get_ndx_components_data_yf_v5(end_date=effective_date.strftime("%Y-%m-%d"))
            if df.empty:
                raise Exception(f"无有效NDX成分股数据：{stats.get('error', 'Unknown')}")

            # 计算加权指标
            metrics = calculate_weighted_metrics(df)
            if not metrics:
                raise Exception("无法计算加权指标（数据不足）")

            coverage_pct = stats['coverage'] * 100
            return {
                "name": "NDX P/E and Earnings Yield",
                "series_id": "NDX_WEIGHTED",
                "value": {
                    "PE": metrics.get('weighted_forward_pe'),
                    "EarningsYield": metrics.get('weighted_earnings_yield'),
                    "FCFYield": metrics.get('weighted_fcf_yield'),  # V5新增FCF收益率
                    "PriceToBook": metrics.get('weighted_price_to_book'),
                    "Coverage": {
                        "stocks_analyzed": stats['successful'],
                        "total_stocks": stats['total_tickers'],
                        "market_cap_coverage": f"{coverage_pct:.1f}%",
                        "failed_tickers": stats['failed_tickers'][:5] + ["..."] if len(stats['failed_tickers']) > 5 else stats['failed_tickers']
                    }
                },
                "unit": "ratio/percent",
                "date": effective_date.strftime("%Y-%m-%d"),
                "source_name": "yfinance (NDX100 Components)",
                "notes": f"市值加权计算，覆盖{coverage_pct:.1f}%的NDX成分股"
            }
        except Exception as e:
            print(f"yfinance计算NDX基本面失败：{str(e)[:50]}，尝试Alpha Vantage备用方案")
            return get_ndx_pe_and_earnings_yield_av(end_date=effective_date.strftime("%Y-%m-%d"))
    else:
        # yfinance不可用时直接降级到Alpha Vantage
        return get_ndx_pe_and_earnings_yield_av(end_date=effective_date.strftime("%Y-%m-%d"))


def get_equity_risk_premium(end_date: str = None) -> Dict[str, Any]:
    """计算股权风险溢价（V5升级：优先使用FCF收益率）"""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()
    
    date_str = effective_date.strftime("%Y-%m-%d")

    # 获取NDX收益率数据
    ndx_data = get_ndx_pe_and_earnings_yield(end_date=date_str)
    if not ndx_data.get("value"):
        return {
            "name": "FCF Yield Premium over 10Y Treasury",
            "value": None,
            "notes": "无法获取NDX收益率数据，计算失败"
        }

    # 优先使用FCF收益率，其次用盈利收益率
    yield_to_use = None
    yield_type = None
    ndx_value = ndx_data["value"]

    if ndx_value.get("FCFYield") is not None:
        yield_to_use = ndx_value["FCFYield"]
        yield_type = "FCF Yield"
    elif ndx_value.get("EarningsYield") is not None:
        yield_to_use = ndx_value["EarningsYield"]
        yield_type = "Earnings Yield"
    else:
        return {
            "name": "FCF Yield Premium over 10Y Treasury",
            "value": None,
            "notes": "NDX无有效收益率数据（FCF/盈利）"
        }

    # 获取10年期美债收益率（无风险利率）
    treasury_data = get_10y_treasury(end_date=date_str)
    treasury_yield = treasury_data.get("value", {}).get("level")
    if treasury_yield is None:
        return {
            "name": "FCF Yield Premium over 10Y Treasury",
            "value": None,
            "notes": "无法获取10年期美债收益率（无风险利率）"
        }

    # 计算股权风险溢价（ERP = 股票收益率 - 无风险利率）
    erp = round(yield_to_use - treasury_yield, 2)
    return {
        "name": "FCF Yield Premium over 10Y Treasury",
        "series_id": "ERP_CALCULATED",
        "value": {
            "level": erp,
            "date": date_str,
            "components": {
                f"NDX {yield_type}": f"{yield_to_use}%",
                "10Y Treasury Yield (Risk-Free)": f"{treasury_yield}%"
            }
        },
        "unit": "percent",
        "source_name": "Calculated (yfinance/Alpha Vantage + FRED)",
        "notes": "该指标衡量指数当前的自由现金流收益率超出无风险利率的幅度，未考虑未来增长，可视为一个保守的、基于当前现金生成能力的相对吸引力指标。"
    }

# =====================================================
# 第五层：技术指标（*本轮修改部分*）
# =====================================================

