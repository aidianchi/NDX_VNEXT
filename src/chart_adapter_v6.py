# chart_adapter_v6.py
# -*- coding: utf-8 -*-
"""
NDX Agent · V6.0 图表适配器
为V6.0新增的技术指标提供实时数据计算

支持的指标：
- MACD (Moving Average Convergence Divergence)
- OBV (On-Balance Volume)
- Volume Analysis (成交量分析)
- Donchian Channels (唐奇安通道)

版本：1.0.0
日期：2026-02-18
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Optional

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logging.warning("yfinance 未安装，V6.0图表功能不可用")


def get_qqq_price_data(lookback_days: int = 365) -> Optional[pd.DataFrame]:
    """
    获取QQQ价格数据（用于计算技术指标）
    
    参数:
        lookback_days: 回溯天数
        
    返回:
        包含 ['date', 'open', 'high', 'low', 'close', 'volume'] 的DataFrame
    """
    if not YFINANCE_AVAILABLE:
        return None
    
    try:
        ticker = yf.Ticker("QQQ")
        
        # 计算起始日期
        end_date = pd.Timestamp.now()
        start_date = end_date - pd.Timedelta(days=lookback_days + 100)  # 多取一些数据用于计算均线
        
        # 获取历史数据
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty:
            logging.warning("QQQ数据为空")
            return None
        
        # 重置索引，将日期作为列
        df = df.reset_index()
        df = df.rename(columns={'Date': 'date', 'Open': 'open', 'High': 'high', 
                                'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
        
        # 只保留需要的列
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
        
        # 确保日期格式正确，并移除时区信息
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        
        # 只取最近的数据
        cutoff_date = pd.Timestamp.now().tz_localize(None) - pd.Timedelta(days=lookback_days)
        df = df[df['date'] >= cutoff_date]
        
        logging.info(f"成功获取QQQ数据: {len(df)} 条记录")
        return df
        
    except Exception as e:
        logging.error(f"获取QQQ数据失败: {str(e)}")
        return None


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    计算MACD指标
    
    参数:
        df: 包含 'close' 列的DataFrame
        fast: 快线周期（默认12）
        slow: 慢线周期（默认26）
        signal: 信号线周期（默认9）
        
    返回:
        包含 ['date', 'macd', 'signal', 'histogram'] 的DataFrame
    """
    if df is None or df.empty or 'close' not in df.columns:
        return pd.DataFrame()
    
    try:
        # 计算EMA
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        
        # MACD线 = 快线 - 慢线
        macd_line = ema_fast - ema_slow
        
        # 信号线 = MACD的9日EMA
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        
        # 柱状图 = MACD - 信号线
        histogram = macd_line - signal_line
        
        result = pd.DataFrame({
            'date': df['date'],
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        })
        
        # 去除NaN值
        result = result.dropna()
        
        return result
        
    except Exception as e:
        logging.error(f"计算MACD失败: {str(e)}")
        return pd.DataFrame()


def calculate_obv(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算OBV (On-Balance Volume) 指标
    
    参数:
        df: 包含 ['close', 'volume'] 的DataFrame
        
    返回:
        包含 ['date', 'obv'] 的DataFrame
    """
    if df is None or df.empty or 'close' not in df.columns or 'volume' not in df.columns:
        return pd.DataFrame()
    
    try:
        # 计算价格变化方向
        price_change = df['close'].diff()
        
        # OBV计算规则：
        # 价格上涨：OBV += 成交量
        # 价格下跌：OBV -= 成交量
        # 价格不变：OBV不变
        obv = pd.Series(index=df.index, dtype=float)
        obv.iloc[0] = df['volume'].iloc[0]
        
        for i in range(1, len(df)):
            if price_change.iloc[i] > 0:
                obv.iloc[i] = obv.iloc[i-1] + df['volume'].iloc[i]
            elif price_change.iloc[i] < 0:
                obv.iloc[i] = obv.iloc[i-1] - df['volume'].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
        result = pd.DataFrame({
            'date': df['date'],
            'obv': obv,
            'value': obv  # 添加value列以兼容标准图表函数
        })
        
        return result
        
    except Exception as e:
        logging.error(f"计算OBV失败: {str(e)}")
        return pd.DataFrame()


def calculate_volume_analysis(df: pd.DataFrame, ma_period: int = 20) -> pd.DataFrame:
    """
    计算成交量分析指标
    
    参数:
        df: 包含 'volume' 的DataFrame
        ma_period: 均量周期（默认20）
        
    返回:
        包含 ['date', 'volume', 'volume_ma20'] 的DataFrame
    """
    if df is None or df.empty or 'volume' not in df.columns:
        return pd.DataFrame()
    
    try:
        # 计算均量线
        volume_ma = df['volume'].rolling(window=ma_period, min_periods=ma_period).mean()
        
        result = pd.DataFrame({
            'date': df['date'],
            'volume': df['volume'],
            'volume_ma20': volume_ma
        })
        
        # 去除NaN值
        result = result.dropna()
        
        return result
        
    except Exception as e:
        logging.error(f"计算成交量分析失败: {str(e)}")
        return pd.DataFrame()


def calculate_donchian_channels(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    计算唐奇安通道指标
    
    参数:
        df: 包含 ['high', 'low', 'close'] 的DataFrame
        period: 通道周期（默认20）
        
    返回:
        包含 ['date', 'close', 'upper_band', 'lower_band'] 的DataFrame
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    if 'high' not in df.columns or 'low' not in df.columns or 'close' not in df.columns:
        return pd.DataFrame()
    
    try:
        # 上轨 = N日最高价
        upper_band = df['high'].rolling(window=period, min_periods=period).max()
        
        # 下轨 = N日最低价
        lower_band = df['low'].rolling(window=period, min_periods=period).min()
        
        result = pd.DataFrame({
            'date': df['date'],
            'close': df['close'],
            'upper_band': upper_band,
            'lower_band': lower_band
        })
        
        # 去除NaN值
        result = result.dropna()
        
        return result
        
    except Exception as e:
        logging.error(f"计算唐奇安通道失败: {str(e)}")
        return pd.DataFrame()


def get_chart_data_for_v6_indicator(function_id: str, lookback_days: int = 365) -> Optional[pd.DataFrame]:
    """
    为V6.0指标获取图表数据（统一接口）
    
    参数:
        function_id: 指标ID（如 "get_macd_qqq"）
        lookback_days: 回溯天数
        
    返回:
        适配后的DataFrame，格式取决于指标类型
    """
    # 首先获取QQQ原始数据
    price_df = get_qqq_price_data(lookback_days)
    
    if price_df is None or price_df.empty:
        return None
    
    # 根据function_id调用对应的计算函数
    if function_id == "get_macd_qqq":
        return calculate_macd(price_df)
    
    elif function_id == "get_obv_qqq":
        return calculate_obv(price_df)
    
    elif function_id == "get_volume_analysis_qqq":
        return calculate_volume_analysis(price_df)
    
    elif function_id == "get_donchian_channels_qqq":
        return calculate_donchian_channels(price_df)
    
    else:
        logging.warning(f"未知的V6.0指标: {function_id}")
        return None


# =====================================================
# 测试入口
# =====================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    print("=" * 70)
    print("V6.0 图表适配器测试")
    print("=" * 70)
    
    if not YFINANCE_AVAILABLE:
        print("[FAIL] yfinance 未安装")
        exit(1)
    
    print("[OK] yfinance 已安装")
    
    # 测试1: 获取QQQ数据
    print("\n[测试1] 获取QQQ价格数据...")
    df = get_qqq_price_data(lookback_days=365)
    
    if df is not None and not df.empty:
        print(f"[OK] 成功获取 {len(df)} 条记录")
        print(f"日期范围: {df['date'].min()} ~ {df['date'].max()}")
    else:
        print("[FAIL] 获取数据失败")
        exit(1)
    
    # 测试2: 计算MACD
    print("\n[测试2] 计算MACD...")
    macd_df = calculate_macd(df)
    if not macd_df.empty:
        print(f"[OK] MACD计算成功: {len(macd_df)} 条记录")
        print(f"最新MACD: {macd_df['macd'].iloc[-1]:.3f}")
    else:
        print("[FAIL] MACD计算失败")
    
    # 测试3: 计算OBV
    print("\n[测试3] 计算OBV...")
    obv_df = calculate_obv(df)
    if not obv_df.empty:
        print(f"[OK] OBV计算成功: {len(obv_df)} 条记录")
        print(f"最新OBV: {obv_df['obv'].iloc[-1]:,.0f}")
    else:
        print("[FAIL] OBV计算失败")
    
    # 测试4: 计算成交量分析
    print("\n[测试4] 计算成交量分析...")
    vol_df = calculate_volume_analysis(df)
    if not vol_df.empty:
        print(f"[OK] 成交量分析成功: {len(vol_df)} 条记录")
        print(f"最新成交量: {vol_df['volume'].iloc[-1]:,.0f}")
    else:
        print("[FAIL] 成交量分析失败")
    
    # 测试5: 计算唐奇安通道
    print("\n[测试5] 计算唐奇安通道...")
    don_df = calculate_donchian_channels(df)
    if not don_df.empty:
        print(f"[OK] 唐奇安通道计算成功: {len(don_df)} 条记录")
        print(f"最新价格: ${don_df['close'].iloc[-1]:.2f}")
        print(f"上轨: ${don_df['upper_band'].iloc[-1]:.2f}")
        print(f"下轨: ${don_df['lower_band'].iloc[-1]:.2f}")
    else:
        print("[FAIL] 唐奇安通道计算失败")
    
    print("\n" + "=" * 70)
    print("测试完成！")

