# tools_L5.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第5层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

# =====================================================
# 第5层函数
# =====================================================

def calculate_technical_indicators_yf(df: pd.DataFrame) -> dict:
    """计算技术指标（V5.2修复版：解决数据格式问题）"""
    indicators = {}
    if df.empty:
        return indicators

    try:
        # 清理数据（使用通用函数）
        df = clean_yfinance_dataframe(df)

        # 再次检查处理后的数据
        if df.empty or 'close' not in df.columns:
            raise Exception("数据清理后无有效OHLC数据")

        current_price = df["close"].iloc[-1]
        indicators["current_price"] = round(current_price, 2)

        # 1. 移动平均线（SMA - 简单移动平均）
        # 注：统一使用SMA以保持与多尺度MA分析的一致性，符合长期投资视角
        if len(df) >= 50:
            indicators["sma_50"] = round(df["close"].rolling(window=50).mean().iloc[-1], 2)
        if len(df) >= 200:
            indicators["sma_200"] = round(df["close"].rolling(window=200).mean().iloc[-1], 2)
            indicators["sma_position"] = "above_200" if current_price > indicators["sma_200"] else "below_200"

        # 2. RSI(14)
        if len(df) >= 15:
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, 1e-9)  # 避免除零
            indicators["rsi_14"] = round(100 - (100 / (1 + rs)).iloc[-1], 2)
            indicators["rsi_status"] = "overbought" if indicators["rsi_14"] > 70 else "oversold" if indicators["rsi_14"] < 30 else "neutral"

        # 3. 布林带（20日SMA）
        if len(df) >= 20:
            sma_20 = df["close"].rolling(window=20).mean()
            std_20 = df["close"].rolling(window=20).std()
            indicators["bb_upper"] = round((sma_20 + 2 * std_20).iloc[-1], 2)
            indicators["bb_lower"] = round((sma_20 - 2 * std_20).iloc[-1], 2)
            indicators["bb_middle"] = round(sma_20.iloc[-1], 2)
            indicators["bb_width"] = round(indicators["bb_upper"] - indicators["bb_lower"], 2)

        # 4. ATR(14)
        if 'high' in df.columns and 'low' in df.columns and len(df) >= 15:
            tr = pd.concat([
                df['high'] - df['low'],
                abs(df['high'] - df['close'].shift()),
                abs(df['low'] - df['close'].shift())
            ], axis=1).max(axis=1)
            indicators["atr_14"] = round(tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1], 2)

            # 布林带压缩率（V5新增）
            if "bb_middle" in indicators and indicators["bb_middle"] > 0:
                indicators["bb_compression_ratio"] = round(indicators["bb_width"] / indicators["bb_middle"], 4)
                indicators["bb_compression_status"] = "high_compression" if indicators["bb_compression_ratio"] < 0.05 else "normal"

            # 2.5倍ATR止损位
            if "atr_14" in indicators:
                indicators["atr_stop_loss_2_5x"] = round(current_price - (2.5 * indicators["atr_14"]), 2)

        # 5. MACD (12, 26, 9) - 动量确认的黄金标准
        if len(df) >= 35:
            ema_12 = df["close"].ewm(span=12, adjust=False).mean()
            ema_26 = df["close"].ewm(span=26, adjust=False).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            macd_histogram = macd_line - signal_line
            
            indicators["macd_line"] = round(macd_line.iloc[-1], 2)
            indicators["macd_signal"] = round(signal_line.iloc[-1], 2)
            indicators["macd_histogram"] = round(macd_histogram.iloc[-1], 2)
            indicators["macd_status"] = "bullish" if macd_histogram.iloc[-1] > 0 else "bearish"
            
            # MACD交叉信号（检测最近的交叉）
            if len(macd_histogram) >= 2:
                if macd_histogram.iloc[-2] < 0 and macd_histogram.iloc[-1] > 0:
                    indicators["macd_cross"] = "golden_cross"  # 金叉
                elif macd_histogram.iloc[-2] > 0 and macd_histogram.iloc[-1] < 0:
                    indicators["macd_cross"] = "death_cross"  # 死叉
                else:
                    indicators["macd_cross"] = "no_cross"

        # 6. OBV (On-Balance Volume) - 能量潮指标
        if 'volume' in df.columns and len(df) >= 2:
            # 计算OBV：价格上涨日累加成交量，下跌日减去成交量
            obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
            indicators["obv"] = int(obv.iloc[-1])
            
            # OBV 20日变化率（衡量资金流向趋势）
            if len(df) >= 20:
                obv_20d_ago = obv.iloc[-20]
                if abs(obv_20d_ago) > 0:
                    indicators["obv_20d_change_pct"] = round((obv.iloc[-1] - obv_20d_ago) / abs(obv_20d_ago) * 100, 2)
                else:
                    indicators["obv_20d_change_pct"] = 0.0
                
                # OBV趋势判断
                indicators["obv_trend"] = "accumulation" if indicators["obv_20d_change_pct"] > 5 else "distribution" if indicators["obv_20d_change_pct"] < -5 else "neutral"

        # 7. Volume MA Ratio - 成交量相对强度
        if 'volume' in df.columns and len(df) >= 20:
            volume_ma_20 = df['volume'].rolling(window=20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            
            if volume_ma_20 > 0:
                indicators["volume_ma_ratio"] = round(current_volume / volume_ma_20, 2)
                
                # 成交量状态判断
                if indicators["volume_ma_ratio"] > 1.5:
                    indicators["volume_status"] = "high"  # 异常放量
                elif indicators["volume_ma_ratio"] < 0.5:
                    indicators["volume_status"] = "low"  # 缩量
                else:
                    indicators["volume_status"] = "normal"
                
                # 量价关系分析（核心）
                if len(df) >= 2:
                    price_change = df['close'].iloc[-1] - df['close'].iloc[-2]
                    if indicators["volume_ma_ratio"] > 1.5 and price_change > 0:
                        indicators["volume_price_relationship"] = "bullish_confirmation"  # 放量上涨
                    elif indicators["volume_ma_ratio"] > 1.5 and price_change < 0:
                        indicators["volume_price_relationship"] = "bearish_confirmation"  # 放量下跌
                    elif indicators["volume_ma_ratio"] < 0.7 and abs(price_change) > current_price * 0.01:
                        indicators["volume_price_relationship"] = "divergence_warning"  # 缩量大幅波动（警告）
                    else:
                        indicators["volume_price_relationship"] = "normal"

        # 8. Donchian Channels (20日) - 突破识别
        if 'high' in df.columns and 'low' in df.columns and len(df) >= 20:
            indicators["donchian_upper"] = round(df['high'].rolling(window=20).max().iloc[-1], 2)
            indicators["donchian_lower"] = round(df['low'].rolling(window=20).min().iloc[-1], 2)
            indicators["donchian_middle"] = round((indicators["donchian_upper"] + indicators["donchian_lower"]) / 2, 2)
            
            # 通道宽度（波动率代理）
            indicators["donchian_width"] = round(indicators["donchian_upper"] - indicators["donchian_lower"], 2)
            
            # 价格在通道中的位置（0-100%）
            channel_range = indicators["donchian_upper"] - indicators["donchian_lower"]
            if channel_range > 0:
                price_position = (current_price - indicators["donchian_lower"]) / channel_range * 100
                indicators["donchian_position_pct"] = round(price_position, 1)
                
                # 突破信号
                if current_price >= indicators["donchian_upper"]:
                    indicators["donchian_signal"] = "upper_breakout"  # 向上突破
                elif current_price <= indicators["donchian_lower"]:
                    indicators["donchian_signal"] = "lower_breakdown"  # 向下突破
                elif price_position > 80:
                    indicators["donchian_signal"] = "near_upper"  # 接近上轨
                elif price_position < 20:
                    indicators["donchian_signal"] = "near_lower"  # 接近下轨
                else:
                    indicators["donchian_signal"] = "mid_channel"  # 通道中部

    except Exception as e:
        print(f"计算技术指标失败：{str(e)[:100]}")

    return indicators


def get_qqq_technical_indicators(end_date: str = None) -> Dict[str, Any]:
    """获取QQQ技术指标（V5.2修复版）"""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    start_date = effective_date - timedelta(days=365)

    # 优先使用yfinance（1年日频数据）
    if YF_AVAILABLE:
        try:
            # 使用yfinance获取数据
            df = cached_yf_download('QQQ', start=start_date, end=effective_date, interval="1d", progress=False, auto_adjust=False)

            # 清理数据
            df = clean_yfinance_dataframe(df)

            if df.empty or len(df) < 200:  # 至少需要200个数据点计算EMA200
                raise Exception(f"数据不足：仅{len(df)}个交易日")

            indicators = calculate_technical_indicators_yf(df)
            if not indicators:
                raise Exception("未计算出有效技术指标")

            return {
                "name": "QQQ Technical Indicators",
                "series_id": "QQQ",
                "value": indicators,
                "unit": "mixed (price/ratio)",
                "date": df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], 'strftime') else effective_date.strftime("%Y-%m-%d"),
                "source_name": "yfinance",
                "notes": "V7.0完整版：含SMA、RSI、布林带、ATR、MACD(EMA)、OBV、成交量分析、唐奇安通道。注：统一使用SMA（除MACD外）以保持一致性"
            }
        except Exception as e:
            print(f"yfinance获取QQQ技术指标失败：{str(e)[:100]}")

    # 降级到Alpha Vantage（备用）
    alphavantage_api_key = get_alphavantage_api_key()
    if not alphavantage_api_key:
        return {
            "name": "QQQ Technical Indicators",
            "value": None,
            "notes": "yfinance不可用且无Alpha Vantage API Key"
        }

    try:
        # 获取Alpha Vantage日频数据
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": "QQQ",
            "apikey": alphavantage_api_key,
            "outputsize": "full"  # 完整数据（20+年）
        }
        data = safe_request(get_alphavantage_base_url(), params)
        if not data or "Time Series (Daily)" not in data:
            raise Exception("Alpha Vantage无有效数据")

        # 转换为DataFrame并筛选到指定日期
        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df[df.index <= effective_date] # 筛选到指定日期
        # 移除 tail(252) 限制，保留全部历史数据用于百分位计算（与yfinance路径一致）

        # 重命名列以兼容技术指标计算函数
        df = df.rename(columns={
            '1. open': 'open',
            '2. high': 'high',
            '3. low': 'low',
            '4. close': 'close',
            '5. volume': 'volume'
        })

        # 确保数据为数值类型
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        if len(df) < 200:
            raise Exception(f"Alpha Vantage数据不足：仅{len(df)}个交易日")

        # 计算技术指标
        indicators = calculate_technical_indicators_yf(df)
        if not indicators:
            raise Exception("Alpha Vantage数据计算指标失败")

        return {
            "name": "QQQ Technical Indicators",
            "series_id": "QQQ",
            "value": indicators,
            "unit": "mixed (price/ratio)",
            "date": df.index[-1].strftime("%Y-%m-%d"),
            "source_name": "Alpha Vantage (fallback)",
            "notes": "yfinance不可用，使用Alpha Vantage备用数据"
        }
    except Exception as e:
        return {
            "name": "QQQ Technical Indicators",
            "value": None,
            "notes": f"Alpha Vantage备用方案失败：{str(e)[:100]}"
        }


def get_rsi_qqq(end_date: str = None) -> Dict[str, Any]:
    """单独获取QQQ的RSI(14)指标（复用技术指标函数）"""
    tech_data = get_qqq_technical_indicators(end_date=end_date)
    if tech_data.get("value") and "rsi_14" in tech_data["value"]:
        return {
            "name": "QQQ RSI(14)",
            "value": {
                "level": tech_data["value"]["rsi_14"],
                "status": tech_data["value"]["rsi_status"],
                "date": tech_data.get("date")
            },
            "unit": "ratio (0-100)",
            "source_name": tech_data.get("source_name"),
            "notes": "RSI(14)：>70超买，<30超卖"
        }
    return {
        "name": "QQQ RSI(14)",
        "value": None,
        "notes": "无法从技术指标数据中提取RSI"
    }


def get_atr_qqq(end_date: str = None) -> Dict[str, Any]:
    """单独获取QQQ的ATR(14)指标（复用技术指标函数）"""
    tech_data = get_qqq_technical_indicators(end_date=end_date)
    if tech_data.get("value") and "atr_14" in tech_data["value"]:
        return {
            "name": "QQQ ATR(14)",
            "value": {
                "level": tech_data["value"]["atr_14"],
                "stop_loss_2_5x": tech_data["value"].get("atr_stop_loss_2_5x"),
                "date": tech_data.get("date")
            },
            "unit": "price points",
            "source_name": tech_data.get("source_name"),
            "notes": "ATR(14)：反映波动率，2.5倍ATR为建议止损位"
        }
    return {
        "name": "QQQ ATR(14)",
        "value": None,
        "notes": "无法从技术指标数据中提取ATR"
    }


def get_adx_qqq(end_date: str = None) -> Dict[str, Any]:
    """获取QQQ的ADX(14)指标，包括+DI和-DI（增强版）"""
    if not YF_AVAILABLE or not PANDAS_TA_AVAILABLE:
        return {
            "name": "QQQ ADX(14)",
            "value": None,
            "notes": "Required libraries (yfinance or pandas_ta) are not available."
        }
    
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()
    
    start_date = effective_date - timedelta(days=365)

    try:
        # 1. 下载yfinance数据并进行严格检查
        try:
            df = cached_yf_download('QQQ', start=start_date, end=effective_date, interval="1d", progress=False, auto_adjust=False)
            df = clean_yfinance_dataframe(df) # 标准化列名等
        except Exception as e:
            return {"name": "ADX QQQ", "value": None, "error": f"yfinance data download failed: {e}"}

        # 检查DataFrame是否有效
        required_cols = ['high', 'low', 'close']
        if df.empty or len(df) < 30 or not all(col in df.columns for col in required_cols):
            return {
                "name": "ADX QQQ", 
                "value": None, 
                "error": "Insufficient or invalid data from yfinance"
            }

        # 2. 计算ADX指标并检查结果
        try:
            df.ta.adx(append=True)
            
            # 提取最新的ADX, +DI (DMP), -DI (DMN)值
            latest_indicators = df.iloc[-1]
            adx_value = latest_indicators.get('ADX_14')
            pdi_value = latest_indicators.get('DMP_14') # Positive Directional Indicator
            mdi_value = latest_indicators.get('DMN_14') # Negative Directional Indicator

            # 检查计算结果是否为NaN
            if pd.isna(adx_value) or pd.isna(pdi_value) or pd.isna(mdi_value):
                return {
                    "name": "ADX QQQ", 
                    "value": None, 
                    "error": "ADX calculation resulted in NaN values."
                }
        except Exception as e:
            return {"name": "ADX QQQ", "value": None, "error": f"pandas_ta calculation failed: {e}"}

        # 3. 如果所有检查都通过，则返回成功结果
        latest_date_val = df.index[-1].strftime("%Y-%m-%d")
        return {
            "name": "QQQ ADX(14)",
            "series_id": "QQQ_ADX",
            "value": {
                "level": {
                    "adx": round(adx_value, 2),
                    "pdi": round(pdi_value, 2),
                    "mdi": round(mdi_value, 2)
                },
                "date": latest_date_val,
            },
            "unit": "index level",
            "source_name": "yfinance & pandas_ta",
            "notes": "ADX > 25 indicates trend strength. pdi > mdi suggests uptrend, vice versa."
        }
        
    except Exception as e:
        # 捕获任何意外的顶层错误
        return {
            "name": "QQQ ADX(14)",
            "value": None,
            "notes": f"An unexpected error occurred in get_adx_qqq: {str(e)}"
        }

# =====================================================
# 第五层：新增独立函数（V6.0 - 量价关系与图表形态）
# =====================================================


def get_macd_qqq(end_date: str = None) -> Dict[str, Any]:
    """单独获取QQQ的MACD指标（复用技术指标函数）"""
    tech_data = get_qqq_technical_indicators(end_date=end_date)
    if tech_data.get("value") and "macd_line" in tech_data["value"]:
        return {
            "name": "QQQ MACD(12,26,9)",
            "value": {
                "macd_line": tech_data["value"]["macd_line"],
                "signal_line": tech_data["value"]["macd_signal"],
                "histogram": tech_data["value"]["macd_histogram"],
                "status": tech_data["value"]["macd_status"],
                "cross_signal": tech_data["value"].get("macd_cross", "no_cross"),
                "date": tech_data.get("date")
            },
            "unit": "price points",
            "source_name": tech_data.get("source_name"),
            "notes": "MACD：动量确认的黄金标准。Histogram>0看涨，<0看跌。金叉/死叉为关键信号。"
        }
    return {
        "name": "QQQ MACD(12,26,9)",
        "value": None,
        "notes": "无法从技术指标数据中提取MACD"
    }


def get_obv_qqq(end_date: str = None) -> Dict[str, Any]:
    """单独获取QQQ的OBV指标（复用技术指标函数）"""
    tech_data = get_qqq_technical_indicators(end_date=end_date)
    if tech_data.get("value") and "obv" in tech_data["value"]:
        return {
            "name": "QQQ OBV (On-Balance Volume)",
            "value": {
                "level": tech_data["value"]["obv"],
                "change_20d_pct": tech_data["value"].get("obv_20d_change_pct"),
                "trend": tech_data["value"].get("obv_trend", "neutral"),
                "date": tech_data.get("date")
            },
            "unit": "cumulative volume",
            "source_name": tech_data.get("source_name"),
            "notes": "OBV：能量潮指标。上升趋势表示资金流入(accumulation)，下降表示流出(distribution)。"
        }
    return {
        "name": "QQQ OBV (On-Balance Volume)",
        "value": None,
        "notes": "无法从技术指标数据中提取OBV"
    }


def get_volume_analysis_qqq(end_date: str = None) -> Dict[str, Any]:
    """单独获取QQQ的成交量分析（复用技术指标函数）"""
    tech_data = get_qqq_technical_indicators(end_date=end_date)
    if tech_data.get("value") and "volume_ma_ratio" in tech_data["value"]:
        return {
            "name": "QQQ Volume Analysis",
            "value": {
                "volume_ma_ratio": tech_data["value"]["volume_ma_ratio"],
                "volume_status": tech_data["value"]["volume_status"],
                "volume_price_relationship": tech_data["value"].get("volume_price_relationship", "normal"),
                "date": tech_data.get("date")
            },
            "unit": "ratio",
            "source_name": tech_data.get("source_name"),
            "notes": "成交量分析：>1.5异常放量，<0.5缩量。量价关系是趋势确认的核心。"
        }
    return {
        "name": "QQQ Volume Analysis",
        "value": None,
        "notes": "无法从技术指标数据中提取成交量分析"
    }


def get_donchian_channels_qqq(end_date: str = None) -> Dict[str, Any]:
    """单独获取QQQ的唐奇安通道（复用技术指标函数）"""
    tech_data = get_qqq_technical_indicators(end_date=end_date)
    if tech_data.get("value") and "donchian_upper" in tech_data["value"]:
        return {
            "name": "QQQ Donchian Channels(20)",
            "value": {
                "upper": tech_data["value"]["donchian_upper"],
                "middle": tech_data["value"]["donchian_middle"],
                "lower": tech_data["value"]["donchian_lower"],
                "width": tech_data["value"]["donchian_width"],
                "position_pct": tech_data["value"].get("donchian_position_pct"),
                "signal": tech_data["value"].get("donchian_signal", "mid_channel"),
                "date": tech_data.get("date")
            },
            "unit": "price points",
            "source_name": tech_data.get("source_name"),
            "notes": "唐奇安通道：海龟交易法则核心工具。突破上轨=买入信号，跌破下轨=卖出信号。"
        }
    return {
        "name": "QQQ Donchian Channels(20)",
        "value": None,
        "notes": "无法从技术指标数据中提取唐奇安通道"
        }

# =====================================================
# 新增函数：多尺度移动平均线分析 (V7.0)
# =====================================================

def get_multi_scale_ma_position(end_date: str = None) -> Dict[str, Any]:
    """
    获取QQQ价格相对于多尺度移动平均线的位置（纯客观数据）
    
    实现精简版4尺度框架：
    - MA5 (1周): 超短期趋势
    - MA20 (1月): 短期趋势
    - MA60 (1季度): 中期趋势
    - MA200 (1年): 长期趋势
    
    返回纯客观数值，不包含任何解释性标签（如"强势"/"弱势"）
    
    Args:
        end_date: 分析截止日期（格式：YYYY-MM-DD），None表示当前日期
        
    Returns:
        {
            'name': 'QQQ Multi-Scale MA Position',
            'value': {
                'current_price': 450.23,
                'date': '2026-02-22',
                'ma_positions': {
                    'ma5': {'value': 445.12, 'deviation_pct': 1.15},
                    'ma20': {'value': 448.50, 'deviation_pct': 0.39},
                    'ma60': {'value': 455.80, 'deviation_pct': -1.22},
                    'ma200': {'value': 420.30, 'deviation_pct': 7.12},
                },
                'ma_order': ['ma200', 'ma5', 'ma20', 'current_price', 'ma60'],
                'cross_scale_divergence': {
                    'short_vs_long': 5.97,  # |ma5_dev - ma200_dev|
                    'short_vs_mid': 2.37,   # |ma5_dev - ma60_dev|
                }
            },
            'unit': 'price & percentage',
            'source_name': 'yfinance',
        }
    """
    if not YF_AVAILABLE:
        return {
            "name": "QQQ Multi-Scale MA Position",
            "value": None,
            "notes": "yfinance未安装，无法计算多尺度MA位置"
        }
    
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()
    
    # 需要至少250个交易日来计算MA200
    start_date = effective_date - timedelta(days=400)
    
    try:
        # 下载数据
        df = cached_yf_download('QQQ', start=start_date, end=effective_date, interval="1d", progress=False, auto_adjust=False)
        df = clean_yfinance_dataframe(df)
        
        if df.empty or len(df) < 200:
            raise Exception(f"数据不足：仅{len(df)}个交易日，需要至少200天")
        
        # 计算各周期简单移动平均线（SMA）
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma60'] = df['close'].rolling(window=60).mean()
        df['ma200'] = df['close'].rolling(window=200).mean()
        
        # 获取最新数据
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # 计算偏离度（百分比）
        ma_positions = {}
        for period in [5, 20, 60, 200]:
            ma_key = f'ma{period}'
            ma_value = latest[ma_key]
            
            if pd.notna(ma_value) and ma_value > 0:
                deviation_pct = ((current_price - ma_value) / ma_value) * 100
                ma_positions[ma_key] = {
                    'value': round(float(ma_value), 2),
                    'deviation_pct': round(float(deviation_pct), 2)
                }
            else:
                ma_positions[ma_key] = {
                    'value': None,
                    'deviation_pct': None
                }
        
        # 计算MA排序（从低到高）
        ma_values = {
            'ma5': ma_positions['ma5']['value'],
            'ma20': ma_positions['ma20']['value'],
            'ma60': ma_positions['ma60']['value'],
            'ma200': ma_positions['ma200']['value'],
            'current_price': float(current_price)
        }
        # 过滤掉None值并排序
        valid_mas = {k: v for k, v in ma_values.items() if v is not None}
        ma_order = sorted(valid_mas.keys(), key=lambda k: valid_mas[k])
        
        # 计算跨尺度背离度
        cross_scale_divergence = {}
        if all(ma_positions[k]['deviation_pct'] is not None for k in ['ma5', 'ma20', 'ma60', 'ma200']):
            cross_scale_divergence = {
                'short_vs_long': round(abs(ma_positions['ma5']['deviation_pct'] - ma_positions['ma200']['deviation_pct']), 2),
                'short_vs_mid': round(abs(ma_positions['ma5']['deviation_pct'] - ma_positions['ma60']['deviation_pct']), 2),
                'mid_vs_long': round(abs(ma_positions['ma60']['deviation_pct'] - ma_positions['ma200']['deviation_pct']), 2),
            }
        
        return {
            "name": "QQQ Multi-Scale MA Position",
            "series_id": "QQQ_MULTI_SCALE_MA",
            "value": {
                "current_price": round(float(current_price), 2),
                "date": df.index[-1].strftime("%Y-%m-%d"),
                "ma_positions": ma_positions,
                "ma_order": ma_order,
                "cross_scale_divergence": cross_scale_divergence
            },
            "unit": "price & percentage",
            "source_name": "yfinance",
            "notes": "4尺度MA分析：MA5(1周)/MA20(1月)/MA60(1季)/MA200(1年)。偏离度=(价格-MA)/MA*100"
        }
        
    except Exception as e:
        return {
            "name": "QQQ Multi-Scale MA Position",
            "value": None,
            "notes": f"计算多尺度MA位置失败：{str(e)[:150]}"
        }


# =====================================================
# 新增函数 (任务一)
# =====================================================

