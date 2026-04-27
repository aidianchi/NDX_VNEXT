# tools_L2.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第2层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

# =====================================================
# 第2层函数
# =====================================================

def _get_ndx100_common_price_data(effective_date: datetime) -> Tuple[List[str], pd.DataFrame]:
    """
    鍏变韩 NDX100 鎴愬垎鑲℃壒閲忚鎯呫€?
    鐩爣鏄 L2 鐨?breadth 鎸囨爣鍏变韩涓€娆′笅杞斤紝
    浣嗗悇鑷殑璁＄畻绐楀彛浠嶇劧鎸夊師鐗堥€昏緫鍒囩墖锛屼笉鏀瑰彉杈撳嚭鍙ｅ緞銆?
    """
    ndx100_components = get_ndx100_components(end_date=effective_date.strftime("%Y-%m-%d"))
    common_start = effective_date - timedelta(days=300)
    data = cached_yf_download(
        ndx100_components,
        start=common_start,
        end=effective_date,
        interval="1d",
        progress=False,
        auto_adjust=False,
    )
    return ndx100_components, data


def get_qqq_qqew_ratio(end_date: str = None) -> Dict[str, Any]:
    """获取QQQ/QQEW比率及其动量与相对性 - 优先yfinance，失败时用Alpha Vantage（修复版）"""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    # 优先尝试yfinance
    if YF_AVAILABLE:
        try:
            # 拉长历史长度用于10年百分位评估
            start_date = effective_date - timedelta(days=365 * 11)

            qqq = cached_yf_download('QQQ', start=start_date, end=effective_date, progress=False, auto_adjust=False)
            qqew = cached_yf_download('QQEW', start=start_date, end=effective_date, progress=False, auto_adjust=False)

            qqq = clean_yfinance_dataframe(qqq)
            qqew = clean_yfinance_dataframe(qqew)

            if not qqq.empty and not qqew.empty and 'close' in qqq.columns and 'close' in qqew.columns:
                df = pd.concat(
                    [qqq['close'].rename('qqq'), qqew['close'].rename('qqew')],
                    axis=1
                ).dropna()
                if len(df) >= 3:
                    ratio_series = df['qqq'] / df['qqew']
                    latest_ratio = float(ratio_series.iloc[-1])
                    latest_qqq = float(df['qqq'].iloc[-1])
                    latest_qqew = float(df['qqew'].iloc[-1])
                    ratio_df = pd.DataFrame({"date": ratio_series.index, "value": ratio_series.values})
                    value_out = {
                        "level": round(latest_ratio, 4),
                        "date": ratio_series.index[-1].strftime("%Y-%m-%d"),
                        "relativity": calculate_long_term_stats(ratio_df, latest_ratio),
                    }
                    if len(ratio_series) >= 20:
                        ratio_ma20 = float(ratio_series.rolling(20, min_periods=20).mean().iloc[-1])
                        value_out["ratio_trend_vs_ma20"] = "above" if latest_ratio > ratio_ma20 else "below"
                        value_out["ratio_ma20"] = round(ratio_ma20, 4)
                    if len(df) >= 60:
                        qqq_ma60 = float(df['qqq'].rolling(60, min_periods=60).mean().iloc[-1])
                        value_out["qqq_price_vs_ma60"] = "above" if latest_qqq > qqq_ma60 else "below"
                        value_out["qqq_ma60"] = round(qqq_ma60, 2)
                    return {
                        "name": "QQQ/QQEW Ratio",
                        "series_id": "CALCULATED",
                        "value": value_out,
                        "unit": "ratio",
                        "source_name": "yfinance",
                        "notes": f"QQQ/QQEW；分层降噪：比值趋势(MA20)+价格趋势(MA60)。QQQ={latest_qqq:.2f}, QQEW={latest_qqew:.2f}"
                    }
        except Exception as e:
            print(f"yfinance failed for QQQ/QQEW: {str(e)[:50]}")

    # 降级到Alpha Vantage
    alphavantage_api_key = get_alphavantage_api_key()
    if not alphavantage_api_key:
        return {
            "name": "QQQ/QQEW Ratio",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "notes": "Both yfinance and Alpha Vantage unavailable"
        }

    try:
        params_qqq = {"function": "TIME_SERIES_DAILY", "symbol": "QQQ", "apikey": alphavantage_api_key}
        qqq_data = safe_request(get_alphavantage_base_url(), params_qqq)
        if not qqq_data or "Note" in qqq_data:
            return {"name": "QQQ/QQEW Ratio", "value": None, "notes": "API limit reached"}

        time.sleep(13)
        params_qqew = {"function": "TIME_SERIES_DAILY", "symbol": "QQEW", "apikey": alphavantage_api_key}
        qqew_data = safe_request(get_alphavantage_base_url(), params_qqew)
        if not qqew_data:
            return {"name": "QQQ/QQEW Ratio", "value": None, "notes": "Failed to fetch QQEW"}

        qqq_ts = qqq_data.get("Time Series (Daily)", {})
        qqew_ts = qqew_data.get("Time Series (Daily)", {})
        
        # 过滤日期
        qqq_ts_filtered = {k: v for k, v in qqq_ts.items() if datetime.strptime(k, "%Y-%m-%d") <= effective_date}
        qqew_ts_filtered = {k: v for k, v in qqew_ts.items() if datetime.strptime(k, "%Y-%m-%d") <= effective_date}

        common_dates = sorted(set(qqq_ts_filtered.keys()) & set(qqew_ts_filtered.keys()))
        if len(common_dates) < 3:
            return {"name": "QQQ/QQEW Ratio", "value": None, "notes": "No sufficient common dates"}

        records = []
        for d in common_dates:
            try:
                qqq_close = float(qqq_ts_filtered[d]["4. close"])
                qqew_close = float(qqew_ts_filtered[d]["4. close"])
                if qqew_close > 0:
                    records.append({"date": pd.to_datetime(d), "value": qqq_close / qqew_close})
            except Exception:
                continue

        if len(records) < 3:
            return {"name": "QQQ/QQEW Ratio", "value": None, "notes": "Insufficient valid ratio observations"}

        df = pd.DataFrame(records).sort_values("date")
        latest_ratio = float(df.iloc[-1]["value"])
        latest_date_val = df.iloc[-1]["date"].strftime("%Y-%m-%d")
        ratio_s = df.set_index("date")["value"]
        value_out = {
            "level": round(latest_ratio, 4),
            "date": latest_date_val,
            "relativity": calculate_long_term_stats(df, latest_ratio),
        }
        if len(ratio_s) >= 20:
            ratio_ma20 = float(ratio_s.rolling(20, min_periods=20).mean().iloc[-1])
            value_out["ratio_trend_vs_ma20"] = "above" if latest_ratio > ratio_ma20 else "below"
            value_out["ratio_ma20"] = round(ratio_ma20, 4)
        analysis = value_out

        return {
            "name": "QQQ/QQEW Ratio",
            "series_id": "CALCULATED",
            "value": analysis,
            "unit": "ratio",
            "source_name": "Alpha Vantage (fallback)",
            "notes": f"Calculated from Alpha Vantage daily closes; latest date {latest_date_val}."
        }
    except Exception as e:
        return {"name": "QQQ/QQEW Ratio", "value": None, "notes": f"Error: {str(e)}"}


def get_advance_decline_line(end_date: str = None) -> Dict[str, Any]:
    """
    计算NDX100的累积腾落线 (Cumulative Advance/Decline Line)
    
    核心价值：
    - 识别趋势内部健康度
    - 与指数价格进行背离分析
    - 预警顶部/底部反转
    
    实现方法：
    - 获取过去126个交易日（约6个月）的成分股数据
    - 每日计算：上涨股票数 - 下跌股票数
    - 累积求和形成趋势线
    - 计算MA20判断趋势方向
    """
    if not YF_AVAILABLE:
        return {
            "name": "Advance/Decline Line (NDX100)",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "notes": "yfinance not available, cannot fetch component data."
        }
    
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    try:
        # 获取成分股列表
        ndx100_components, data = _get_ndx100_common_price_data(effective_date)

        # 下载126天+20天缓冲的数据（确保有足够交易日）
        lookback_days = 126
        start_date = effective_date - timedelta(days=lookback_days + 40)
        
        
        if data.empty or len(data) < 2:
            raise ValueError("Insufficient data returned from yfinance.")

        # 提取收盘价数据
        close_prices = data['Close']
        close_prices = close_prices[close_prices.index >= start_date]
        
        # 确保至少有2天数据
        if len(close_prices) < 2:
            raise ValueError(f"Insufficient trading days: {len(close_prices)}")

        # 计算每日涨跌家数净值
        daily_ad_values = []
        for i in range(1, len(close_prices)):
            price_change = close_prices.iloc[i] - close_prices.iloc[i-1]
            advances = (price_change > 0).sum()
            declines = (price_change < 0).sum()
            net_advances = advances - declines
            daily_ad_values.append(net_advances)

        # 累积求和形成腾落线
        cumulative_ad_line = np.cumsum(daily_ad_values)
        
        # 获取最新值
        current_level = int(cumulative_ad_line[-1])
        latest_date_val = close_prices.index[-1].strftime("%Y-%m-%d")
        
        # 计算MA20判断趋势
        if len(cumulative_ad_line) >= 20:
            ma20 = np.mean(cumulative_ad_line[-20:])
            distance_from_ma20_pct = ((current_level - ma20) / abs(ma20) * 100) if ma20 != 0 else 0
            
            # 判断趋势方向
            if distance_from_ma20_pct > 2:
                trend = "rising"
            elif distance_from_ma20_pct < -2:
                trend = "declining"
            else:
                trend = "sideways"
        else:
            ma20 = None
            distance_from_ma20_pct = None
            trend = "insufficient_data"

        # 计算最近的涨跌家数（用于notes）
        latest_price_change = close_prices.iloc[-1] - close_prices.iloc[-2]
        latest_advances = (latest_price_change > 0).sum()
        latest_declines = (latest_price_change < 0).sum()

        return {
            "name": "Advance/Decline Line (NDX100)",
            "value": {
                "level": current_level,
                "date": latest_date_val,
                "trend": trend,
                "ma20": int(ma20) if ma20 is not None else None,
                "distance_from_ma20_pct": round(distance_from_ma20_pct, 2) if distance_from_ma20_pct is not None else None,
                "momentum": None,  # 保持兼容性
                "relativity": None  # 保持兼容性
            },
            "unit": "cumulative_count",
            "source_name": "yfinance",
            "notes": f"基于{len(ndx100_components)}只成分股的{len(daily_ad_values)}天累积数据。最新：上涨{latest_advances}只，下跌{latest_declines}只。"
        }
    except Exception as e:
        return {
            "name": "Advance/Decline Line (NDX100)",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "notes": f"Failed to calculate: {str(e)}"
        }


def get_percent_above_ma(end_date: str = None) -> Dict[str, Any]:
    """计算NDX100成分股中价格高于50日和200日均线的股票百分比"""
    if not YF_AVAILABLE:
        return {
            "name": "% Stocks Above MA (NDX100)",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "notes": "yfinance not available, cannot fetch component data."
        }
    
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    try:
        # **修改点**: 调用新的动态函数获取成分股
        ndx100_components, data = _get_ndx100_common_price_data(effective_date)
        
        start_date = effective_date - timedelta(days=300) # 确保有足够数据计算200日均线

        # 批量下载过去约一年的日频数据
        if data.empty:
            raise ValueError("No data returned from yfinance.")

        close_prices = data['Close'].dropna(axis=1, how='any') # 删除数据不完整的列

        if close_prices.empty or len(close_prices) < 200:
             raise ValueError(f"Insufficient data for MA calculation (days={len(close_prices)}).")

        # 获取最新收盘价
        latest_prices = close_prices.iloc[-1]

        # 计算50日和200日移动平均线
        ma50 = close_prices.rolling(window=50).mean().iloc[-1]
        ma200 = close_prices.rolling(window=200).mean().iloc[-1]

        # 比较并计算高于均线的股票数量
        above_50d = (latest_prices > ma50).sum()
        above_200d = (latest_prices > ma200).sum()

        # 计算百分比
        total_stocks = len(close_prices.columns)
        percent_above_50d = round((above_50d / total_stocks) * 100, 2)
        percent_above_200d = round((above_200d / total_stocks) * 100, 2)

        # 获取最新日期
        latest_date_val = close_prices.index[-1].strftime("%Y-%m-%d")

        return {
            "name": "% Stocks Above MA (NDX100)",
            "value": {
                "level": {
                    "percent_above_50d": percent_above_50d,
                    "percent_above_200d": percent_above_200d
                },
                "date": latest_date_val,
            },
            "unit": "percent",
            "source_name": "yfinance",
            "notes": f"Based on {total_stocks} NDX100 components with complete data."
        }
    except Exception as e:
        return {
            "name": "% Stocks Above MA (NDX100)",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "notes": f"Failed to calculate: {str(e)}"
        }



def get_new_highs_lows(end_date: str = None) -> Dict[str, Any]:
    """新高新低指数 - 暂未实现（保持不变）"""
    return {
        "name": "New Highs-Lows Index",
        "value": {"level": None, "date": None, "momentum": None, "relativity": None},
        "notes": "Data source pending implementation"
    }


def get_mcclellan_oscillator_nasdaq_or_nyse(end_date: str = None) -> Dict[str, Any]:
    """McClellan Oscillator - 暂未实现（保持不变）"""
    return {
        "name": "McClellan Oscillator",
        "value": {"level": None, "date": None, "momentum": None, "relativity": None},
        "notes": "Data source pending implementation"
    }


CNN_FGI_BASE_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def _get_cnn_headers() -> Dict[str, str]:
    """构建CNN API请求头，模拟浏览器访问"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://edition.cnn.com/',
        'Accept-Language': 'en-US,en;q=0.9',
    }


def get_cnn_fear_greed_index(end_date: str = None) -> Dict[str, Any]:
    """
    获取CNN恐贪指数 (Fear & Greed Index)
    
    数据源：CNN Business官方API
    URL：https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{date}
    
    核心价值：
    - 综合性市场情绪指标，整合7个子指标
    - 极端值是有效的反向指标（<25极度恐惧=买入机会，>75极度贪婪=风险警示）
    - 提供历史对比数据（前一日/周/月/年）
    
    返回结构：
    - score: 恐贪指数得分 (0-100)
    - rating: 情绪评级 (extreme fear/fear/neutral/greed/extreme greed)
    - previous_close/week/month/year: 历史对比
    - sub_metrics: 7个子指标详情
    
    投资逻辑（第一性原理）：
    - 极端恐惧（<25）：市场过度悲观，价格低于内在价值 → 买入机会
    - 极端贪婪（>75）：市场过度乐观，价格高于内在价值 → 风险警示
    """
    headers = _get_cnn_headers()
    
    if end_date:
        start_date = end_date
    else:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    url = f"{CNN_FGI_BASE_URL}/{start_date}"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        fear_greed = data.get('fear_and_greed', {})
        if not fear_greed:
            return {
                "name": "CNN Fear & Greed Index",
                "value": None,
                "notes": "No fear and greed data in response"
            }
        
        score = fear_greed.get('score')
        rating = fear_greed.get('rating')
        
        result = {
            "name": "CNN Fear & Greed Index",
            "series_id": "CNN_FGI",
            "value": {
                "score": round(score, 2) if score else None,
                "rating": rating,
                "timestamp": fear_greed.get('timestamp'),
                "previous_close": fear_greed.get('previous_close'),
                "previous_1_week": fear_greed.get('previous_1_week'),
                "previous_1_month": fear_greed.get('previous_1_month'),
                "previous_1_year": fear_greed.get('previous_1_year'),
            },
            "unit": "index (0-100)",
            "source_name": "CNN Business",
            "notes": "Score range: 0-100. <25=Extreme Fear (buy signal), >75=Extreme Greed (risk warning)"
        }
        
        sub_metrics = {}
        sub_metric_names = {
            "market_momentum_sp500": "Market Momentum (S&P500)",
            "stock_price_strength": "Stock Price Strength",
            "stock_price_breadth": "Stock Price Breadth",
            "put_call_options": "Put/Call Options",
            "market_volatility_vix": "Market Volatility (VIX)",
            "junk_bond_demand": "Junk Bond Demand",
            "safe_haven_demand": "Safe Haven Demand"
        }
        
        for key, display_name in sub_metric_names.items():
            if key in data:
                metric_data = data[key]
                sub_metrics[display_name] = {
                    "score": metric_data.get('score'),
                    "rating": metric_data.get('rating')
                }
        
        if sub_metrics:
            result["value"]["sub_metrics"] = sub_metrics
        
        trend = "neutral"
        if score is not None:
            if score < 25:
                trend = "extreme_fear"
            elif score < 45:
                trend = "fear"
            elif score < 55:
                trend = "neutral"
            elif score < 75:
                trend = "greed"
            else:
                trend = "extreme_greed"
        result["value"]["trend"] = trend
        
        logging.info(f"CNN FGI: {score:.2f} ({rating})")
        return result
        
    except requests.exceptions.HTTPError as e:
        logging.warning(f"CNN FGI HTTP error: {e}")
        return {
            "name": "CNN Fear & Greed Index",
            "value": None,
            "notes": f"HTTP error: {str(e)[:50]}"
        }
    except requests.exceptions.RequestException as e:
        logging.warning(f"CNN FGI request error: {e}")
        return {
            "name": "CNN Fear & Greed Index",
            "value": None,
            "notes": f"Request error: {str(e)[:50]}"
        }
    except Exception as e:
        logging.warning(f"CNN FGI unexpected error: {e}")
        return {
            "name": "CNN Fear & Greed Index",
            "value": None,
            "notes": f"Error: {str(e)[:50]}"
        }

# =====================================================
# 第三层：核心公司健康度（修复版）
# =====================================================

