# tools_L1.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第1层数据获取函数
"""

try:
    from .tools_common import *
    from .tools_common import _fetch_fred_series, _fetch_yf_history
except ImportError:
    from tools_common import *
    from tools_common import _fetch_fred_series, _fetch_yf_history

# =====================================================
# 第1层函数
# =====================================================

def _get_yf_series_with_analysis(ticker: str, name: str, end_date: Optional[str] = None, use_ma20_trend: bool = False) -> Dict[str, Any]:
    """
    (内部函数) 使用yfinance获取时间序列数据。use_ma20_trend=True 时（如 VIX/VXN）
    输出 spot_over_ma20_ratio 替代日度动量，用于分层降噪。
    """
    if not YF_AVAILABLE:
        return {"name": name, "value": None, "notes": "yfinance library not available."}

    try:
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            effective_date = datetime.now()

        request_end_date = effective_date + timedelta(days=1)
        # 获取至少10年的历史数据，用于计算10年百分位
        request_start_date = effective_date - timedelta(days=365 * 11)

        df = yf.download(
            ticker,
            start=request_start_date.strftime("%Y-%m-%d"),
            end=request_end_date.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False
        )
        
        if df.empty:
             raise ValueError(f"yfinance returned an empty DataFrame for {ticker}.")
        
        df = clean_yfinance_dataframe(df)
        df.index = pd.to_datetime(df.index)
        df = df[df.index.date <= effective_date.date()]
        
        if df.empty:
            raise ValueError(f"No data available on or before {effective_date.date()}")

        # 移除 tail(365) 限制，保留全部历史数据用于百分位计算 
        if len(df) < 3:
             raise ValueError(f"Insufficient data points ({len(df)}) for analysis.")
        
        series_for_analysis = df.rename(columns={'close': 'value'})

        if use_ma20_trend and len(df) >= 20:
            level = float(df["close"].iloc[-1])
            ma20 = float(df["close"].rolling(20, min_periods=20).mean().iloc[-1])
            
            # 【修复】：正确处理 reset_index() 后的列名
            stats_df = series_for_analysis.reset_index()
            if "index" in stats_df.columns:
                stats_df = stats_df.rename(columns={"index": "date"})
            elif "Date" in stats_df.columns:
                stats_df = stats_df.rename(columns={"Date": "date"})
            # 确保有 date 列
            if "date" not in stats_df.columns:
                stats_df["date"] = stats_df.index
            
            stats = calculate_long_term_stats(stats_df[["date", "value"]], level)
            analysis = {
                "level": round(level, 4),
                "date": df.index[-1].strftime("%Y-%m-%d"),
                "spot_over_ma20_ratio": round(level / ma20, 4) if ma20 > 0 else None,
                "ma20": round(ma20, 4),
                "historical_stats": stats,
            }
        else:
            analysis = analyze_series_momentum_relativity(series_for_analysis)
        if not analysis or analysis.get("level") is None:
            raise ValueError("Analysis function returned empty results.")

        return {
            "name": name, "series_id": ticker, "value": analysis,
            "unit": "level", "source_name": "yfinance",
            "notes": f"Successfully fetched data as of {analysis['date']}." + (" 分层降噪：Spot/MA20。" if use_ma20_trend else "")
        }
    except Exception as e:
        error_note = f"Failed to get {ticker} data: {str(e)}"
        logging.warning(f"  - {name}: {error_note}")
        return {
            "name": name, "series_id": ticker, "value": None,
            "notes": error_note
        }


def get_vix(end_date: str = None) -> Dict[str, Any]:
    """获取VIX恐慌指数，使用持久化缓存并返回历史统计。V5.8修复版：增强错误处理和Alpha Vantage备用。"""
    if not YF_AVAILABLE:
        logging.warning("yfinance 不可用，尝试 Alpha Vantage 备用方案")
        return _get_vix_from_alphavantage(end_date=end_date)

    # 尝试使用 TimeSeriesManager 获取数据
    try:
        vix_df = ts_manager.get_or_update_series("VIX", _fetch_vix_history)
        if not vix_df.empty:
            if end_date:
                effective_date = datetime.strptime(end_date, "%Y-%m-%d")
                vix_df = vix_df[vix_df["date"] <= effective_date]
            if not vix_df.empty:
                latest_row = vix_df.iloc[-1]
                latest_level = float(latest_row["value"])
                latest_date_str = latest_row["date"].strftime("%Y-%m-%d")
                historical_stats = calculate_long_term_stats(vix_df[["date", "value"]], latest_level)
                value_out = {"level": round(latest_level, 4), "historical_stats": historical_stats, "date": latest_date_str}
                if len(vix_df) >= 20:
                    vix_s = vix_df.set_index("date")["value"].sort_index()
                    ma20 = float(vix_s.rolling(20, min_periods=20).mean().iloc[-1])
                    value_out["spot_over_ma20_ratio"] = round(latest_level / ma20, 4) if ma20 > 0 else None
                    value_out["ma20"] = round(ma20, 4)
                logging.info(f"成功从缓存获取 VIX 数据: {latest_level} (日期: {latest_date_str})")
                return {
                    "name": "VIX Index",
                    "series_id": "^VIX",
                    "value": value_out,
                    "unit": "index level",
                    "source_name": "yfinance (cached)",
                    "notes": "VIX 恐慌指数；分层降噪：现值 + 趋势比(Spot/MA20)。"
                }
    except Exception as e:
        logging.warning(f"TimeSeriesManager 获取 VIX 数据失败: {e}，尝试直接获取")

    # 回退到直接使用 yfinance 获取数据（分层降噪：Spot/MA20）
    result = _get_yf_series_with_analysis(ticker="^VIX", name="VIX Index", end_date=end_date, use_ma20_trend=True)
    
    # 如果yfinance也失败，尝试Alpha Vantage
    if result.get("value") is None:
        logging.warning("yfinance 直接获取 VIX 失败，尝试 Alpha Vantage 备用方案")
        return _get_vix_from_alphavantage(end_date=end_date)
    
    return result


def _get_vix_from_alphavantage(end_date: str = None) -> Dict[str, Any]:
    """Alpha Vantage备用方案获取VIX数据"""
    alphavantage_api_key = get_alphavantage_api_key()
    if not alphavantage_api_key:
        return {
            "name": "VIX Index",
            "value": None,
            "notes": "yfinance 和 Alpha Vantage 均不可用"
        }
    
    try:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": "VIX",
            "apikey": alphavantage_api_key,
            "outputsize": "full"
        }
        data = safe_request(get_alphavantage_base_url(), params)
        if not data or "Time Series (Daily)" not in data:
            raise Exception("Alpha Vantage 无有效 VIX 数据")
        
        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df[df.index <= effective_date]
        df = df.rename(columns={"4. close": "value"})
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])
        
        if len(df) < 3:
            raise Exception("Alpha Vantage VIX 数据不足")
        
        latest_level = float(df["value"].iloc[-1])
        latest_date_str = df.index[-1].strftime("%Y-%m-%d")
        df_for_stats = df.reset_index().rename(columns={"index": "date"})[["date", "value"]]
        historical_stats = calculate_long_term_stats(df_for_stats, latest_level)
        
        value_out = {"level": round(latest_level, 4), "historical_stats": historical_stats, "date": latest_date_str}
        if len(df) >= 20:
            ma20 = float(df["value"].rolling(20, min_periods=20).mean().iloc[-1])
            value_out["spot_over_ma20_ratio"] = round(latest_level / ma20, 4) if ma20 > 0 else None
            value_out["ma20"] = round(ma20, 4)
        
        logging.info(f"成功从 Alpha Vantage 获取 VIX 数据: {latest_level}")
        return {
            "name": "VIX Index",
            "series_id": "VIX",
            "value": value_out,
            "unit": "index level",
            "source_name": "Alpha Vantage (fallback)",
            "notes": "VIX 恐慌指数（Alpha Vantage备用）；分层降噪：现值 + 趋势比(Spot/MA20)。"
        }
    except Exception as e:
        logging.error(f"Alpha Vantage 获取 VIX 失败: {str(e)}")
        return {
            "name": "VIX Index",
            "value": None,
            "notes": f"所有数据源均失败: {str(e)[:100]}"
        }



def get_vxn(end_date: str = None) -> Dict[str, Any]:
    """获取VXN纳指恐慌指数。分层降噪：现值 + 趋势比(Spot/MA20)。V5.8修复版：增强错误处理。"""
    result = _get_yf_series_with_analysis(ticker="^VXN", name="VXN Index", end_date=end_date, use_ma20_trend=True)
    
    # 如果yfinance失败，记录详细错误
    if result.get("value") is None:
        logging.error(f"VXN 获取失败: {result.get('notes', 'Unknown error')}")
    
    return result



def get_vxn_vix_ratio(end_date: str = None) -> Dict[str, Any]:
    """计算VXN/VIX比率 (仅水平)"""
    vxn_data = get_vxn(end_date=end_date)
    vix_data = get_vix(end_date=end_date)
    ratio, date = None, None
    vxn_level = vxn_data.get("value", {}).get("level")
    vix_level = vix_data.get("value", {}).get("level")

    if vxn_level and vix_level:
        ratio = round(vxn_level / vix_level, 4)
        date = max(vxn_data["value"]["date"], vix_data["value"]["date"])

    return {
        "name": "VXN/VIX Ratio", "value": {"level": ratio, "date": date}, "unit": "ratio",
        "notes": f"Calculated from latest levels: VXN={vxn_level}, VIX={vix_level}"
    }


def get_10y2y_spread_bp(end_date: str = None) -> Dict[str, Any]:
    """获取10年-2年期美债利差。分层降噪：用 MA20 乖离率替代日度动量。"""
    series = get_fred_series("T10Y2Y", end_date=end_date)
    if series is None or len(series) < 20:
        return {
            "name": "10Y-2Y Treasury Spread", "series_id": "T10Y2Y", "value": None,
            "unit": "basis points", "source_name": "FRED",
            "notes": "数据不足，无法计算 MA20 乖离率。"
        }
    series = series.copy()
    series['value'] = series['value'] * 100  # Convert to BPS
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "10Y-2Y Treasury Spread", "series_id": "T10Y2Y", "value": analysis,
        "unit": "basis points", "source_name": "FRED",
        "notes": "10Y-2Y 利差；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }


def get_hy_oas_bp(end_date: str = None) -> Dict[str, Any]:
    """获取高收益企业债OAS。分层降噪：用 MA5 vs MA20 趋势替代日度动量。"""
    series = get_fred_series("BAMLH0A0HYM2", end_date=end_date)
    if series is None or len(series) < 20:
        return {
            "name": "High Yield OAS", "series_id": "BAMLH0A0HYM2", "value": None,
            "unit": "basis points", "source_name": "FRED",
            "notes": "数据不足，无法计算 MA5/MA20 趋势。"
        }
    analysis = analyze_series_ma_trend(series, short_period=5, long_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "High Yield OAS", "series_id": "BAMLH0A0HYM2", "value": analysis,
        "unit": "basis points", "source_name": "FRED",
        "notes": "ICE BofA US High Yield OAS；分层降噪：MA5 vs MA20 趋势方向。"
    }


def get_ig_oas_bp(end_date: str = None) -> Dict[str, Any]:
    """获取投资级企业债OAS。分层降噪：用 MA5 vs MA20 趋势替代日度动量。"""
    series = get_fred_series("BAMLC0A0CM", end_date=end_date)
    if series is None or len(series) < 20:
        return {
            "name": "Investment Grade OAS", "series_id": "BAMLC0A0CM", "value": None,
            "unit": "basis points", "source_name": "FRED",
            "notes": "数据不足，无法计算 MA5/MA20 趋势。"
        }
    analysis = analyze_series_ma_trend(series, short_period=5, long_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "Investment Grade OAS", "series_id": "BAMLC0A0CM", "value": analysis,
        "unit": "basis points", "source_name": "FRED",
        "notes": "ICE BofA US Corporate OAS；分层降噪：MA5 vs MA20 趋势方向。"
    }


def get_10y_real_rate(end_date: str = None) -> Dict[str, Any]:
    """获取10年期实际利率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("DFII10", end_date=end_date)
    if series is None or len(series) < 20:
        return {
            "name": "10Y Real Rate", "series_id": "DFII10", "value": None,
            "unit": "percent", "source_name": "FRED",
            "notes": "数据不足，无法计算 MA20 乖离率。"
        }
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "10Y Real Rate", "series_id": "DFII10", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期实际利率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }


def get_10y_treasury(end_date: str = None) -> Dict[str, Any]:
    """获取10年期美债名义收益率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("DGS10", end_date=end_date)
    if series is None or len(series) < 20:
        return {
            "name": "10Y Treasury Yield", "series_id": "DGS10", "value": None,
            "unit": "percent", "source_name": "FRED",
            "notes": "数据不足，无法计算 MA20 乖离率。"
        }
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "10Y Treasury Yield", "series_id": "DGS10", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期美债收益率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }


def get_10y_breakeven(end_date: str = None) -> Dict[str, Any]:
    """获取10年期盈亏平衡通胀率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("T10YIE", end_date=end_date)
    if series is None or len(series) < 20:
        return {
            "name": "10Y Breakeven Inflation", "series_id": "T10YIE", "value": None,
            "unit": "percent", "source_name": "FRED",
            "notes": "数据不足，无法计算 MA20 乖离率。"
        }
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "10Y Breakeven Inflation", "series_id": "T10YIE", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期盈亏平衡通胀率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }


def get_fed_funds_rate(end_date: str = None) -> Dict[str, Any]:
    """获取联邦基金利率 (V5.1升级)"""
    series = get_fred_series("FEDFUNDS", end_date=end_date)
    analysis = analyze_series_momentum_relativity(series)
    return {
        "name": "Fed Funds Rate", "series_id": "FEDFUNDS", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "Effective Federal Funds Rate with momentum and relativity."
    }


def get_m2_yoy(end_date: str = None) -> Dict[str, Any]:
    """获取M2货币供应量年同比增速 (保留月度动量特性)"""
    yoy, date = calculate_yoy_change("M2SL", lookback_days=800, end_date=end_date)
    return {
        "name": "M2 YoY Growth", "series_id": "M2SL",
        "value": {"level": yoy, "date": date, "momentum": "monthly", "relativity": None},
        "unit": "percent", "source_name": "FRED",
        "notes": "M2 Money Supply Year-over-Year Growth (monthly momentum)."
    }


def _fetch_walcl_history(start_date: Optional[Any] = None) -> pd.DataFrame:
    """
    原子化获取 WALCL 历史，单位归一到十亿美元。
    注意：FRED API返回的WALCL单位是百万美元，必须除以1000转换为十亿美元。
    """
    df = _fetch_fred_series("WALCL", start_date=start_date)
    if df.empty:
        return df
    # WALCL在FRED中单位是百万美元，必须除以1000转换为十亿美元
    # 典型值范围：7,000,000-9,000,000百万美元 -> 7,000-9,000十亿美元
    df["value"] = df["value"] / 1000.0
    return df



def _fetch_tga_history(start_date: Optional[Any] = None) -> pd.DataFrame:
    """
    原子化获取财政部现金账户 WTREGEN，单位十亿美元。
    注意：FRED API返回的WTREGEN单位已经是十亿美元，不需要转换。
    """
    df = _fetch_fred_series("WTREGEN", start_date=start_date)
    if df.empty:
        return df
    # WTREGEN在FRED中单位已经是十亿美元，不需要转换
    # 典型值范围：几百到几千十亿美元，不应该>10,000
    return df



def _fetch_rrp_history(start_date: Optional[Any] = None) -> pd.DataFrame:
    """
    原子化获取隔夜逆回购 RRPONTSYD，单位十亿美元。
    注意：FRED API返回的RRPONTSYD单位已经是十亿美元，不需要转换。
    """
    df = _fetch_fred_series("RRPONTSYD", start_date=start_date)
    if df.empty:
        return df
    # RRPONTSYD在FRED中单位已经是十亿美元，不需要转换
    # 典型值范围：几百到几千十亿美元，不应该>10,000
    return df



def _fetch_qqq_history(start_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 QQQ 历史收盘价，返回 ['date', 'value']。"""
    return _fetch_yf_history("QQQ", start_date=start_date)



def _fetch_vix_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 VIX 日频历史。"""
    return _fetch_yf_history("^VIX", start_date=start_date, end_date=end_date)



def _fetch_xly_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 XLY 日频历史。"""
    return _fetch_yf_history("XLY", start_date=start_date, end_date=end_date)



def _fetch_xlp_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 XLP 日频历史。"""
    return _fetch_yf_history("XLP", start_date=start_date, end_date=end_date)



def _fetch_copper_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取铜期货 HG=F 日频历史。"""
    return _fetch_yf_history("HG=F", start_date=start_date, end_date=end_date)



def _fetch_gold_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取黄金期货 GC=F 日频历史。"""
    return _fetch_yf_history("GC=F", start_date=start_date, end_date=end_date)



def _build_net_liquidity_series() -> Tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """
    构建净流动性日频序列与组件。
    V5.8 修复版：增加数值合理性检查，确保单位一致性。
    """
    walcl_df = ts_manager.get_or_update_series("WALCL", _fetch_walcl_history)
    tga_df = ts_manager.get_or_update_series("WTREGEN", _fetch_tga_history)
    rrp_df = ts_manager.get_or_update_series("RRPONTSYD", _fetch_rrp_history)

    def _normalize_billions(series: pd.Series, series_id: str) -> pd.Series:
        """
        兜底归一到十亿美元，根据序列ID采用不同的转换策略。
        V5.8 增强：增加详细的数值合理性检查和自动修正。
        
        参数:
            series: 待归一化的序列
            series_id: 序列标识符（"WALCL", "WTREGEN", "RRPONTSYD"）
        
        返回:
            归一化到十亿美元单位的序列
        """
        if series.empty:
            return series
        
        max_val = series.max()
        min_val = series.min()
        
        if series_id == "WALCL":
            # WALCL在FRED中单位是百万美元
            # 正常范围：7,000,000-9,000,000百万美元（未转换）或 7,000-9,000十亿美元（已转换）
            if max_val > 100_000:
                # 检测到可能是百万美元单位（>100,000说明未转换）
                logging.warning(f"检测到WALCL数据可能为百万美元单位（最大值={max_val:.2f}），自动转换为十亿美元")
                return series / 1000.0
            elif max_val > 10_000:
                # 异常大值，可能是数据错误
                logging.error(f"WALCL数据异常：最大值={max_val:.2f}，超出合理范围（应在7,000-9,000十亿美元）")
                # 尝试修正：假设是百万美元未转换
                return series / 1000.0
            elif max_val < 1000:
                # 异常小值，可能是重复转换
                logging.error(f"WALCL数据异常：最大值={max_val:.2f}，远低于合理范围（应在7,000-9,000十亿美元）")
                # 可能是千美元单位，需要乘以1000
                return series * 1000.0
            else:
                # 数值在合理范围内（1000-10000），认为已正确转换
                logging.info(f"WALCL数据范围正常：{min_val:.2f} - {max_val:.2f} 十亿美元")
                return series
        
        elif series_id in ["WTREGEN", "RRPONTSYD"]:
            # WTREGEN和RRPONTSYD在FRED中单位已经是十亿美元
            # 正常范围：几百到几千十亿美元
            if max_val > 10_000:
                # 异常大值
                logging.error(f"{series_id}数据异常：最大值={max_val:.2f}，超出合理范围（应<10,000十亿美元）")
                # 可能是百万美元误标，需要除以1000
                return series / 1000.0
            elif max_val < 10:
                # 异常小值
                logging.error(f"{series_id}数据异常：最大值={max_val:.2f}，远低于合理范围（应在几百到几千十亿美元）")
                # 可能是万亿美元单位，需要乘以1000
                return series * 1000.0
            else:
                # 数值在合理范围内
                logging.info(f"{series_id}数据范围正常：{min_val:.2f} - {max_val:.2f} 十亿美元")
                return series
        
        return series

    if walcl_df.empty or tga_df.empty or rrp_df.empty:
        logging.error("净流动性组件数据缺失，无法构建序列")
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)

    walcl_s = walcl_df.set_index("date")["value"].resample("D").ffill()
    tga_s = tga_df.set_index("date")["value"].resample("D").ffill()
    rrp_s = rrp_df.set_index("date")["value"].resample("D").ffill()

    # 再次保证单位一致：全部校正到十亿美元（兜底机制）
    walcl_s = _normalize_billions(walcl_s, "WALCL")
    tga_s = _normalize_billions(tga_s, "WTREGEN")
    rrp_s = _normalize_billions(rrp_s, "RRPONTSYD")

    common_index = walcl_s.index.union(tga_s.index).union(rrp_s.index)
    walcl_s = walcl_s.reindex(common_index).ffill()
    tga_s = tga_s.reindex(common_index).ffill()
    rrp_s = rrp_s.reindex(common_index).ffill()

    net_liquidity = walcl_s - tga_s - rrp_s
    
    # 最终合理性检查
    net_liq_latest = net_liquidity.iloc[-1]
    if abs(net_liq_latest) > 20_000:
        logging.error(f"净流动性最终值异常：{net_liq_latest:.2f}，超出合理范围（应在-10,000到+10,000十亿美元）")
    else:
        logging.info(f"净流动性计算完成：最新值 {net_liq_latest:.2f} 十亿美元（Fed={walcl_s.iloc[-1]:.2f}, TGA={tga_s.iloc[-1]:.2f}, RRP={rrp_s.iloc[-1]:.2f}）")
    
    net_liq_df = net_liquidity.reset_index().rename(columns={"index": "date"})
    net_liq_df = net_liq_df.rename(columns={net_liq_df.columns[1]: "value"})
    return net_liq_df, walcl_s, tga_s, rrp_s



def get_net_liquidity_momentum(end_date: str = None) -> Dict[str, Any]:
    """
    计算“美元净流动性”及历史统计：
    Net Liquidity = WALCL(Fed Assets) - WTREGEN(TGA) - RRPONTSYD(Overnight RRP)
    - 使用 TimeSeriesManager 进行增量持久化。
    - 返回值包含 historical_stats。
    """
    if not get_fred_api_key():
        return {
            "name": "Net Liquidity (Fed - TGA - RRP)",
            "value": None,
            "notes": "FRED_API_KEY 不可用，无法计算净流动性。"
        }

    net_liq_df, walcl_s, tga_s, rrp_s = _build_net_liquidity_series()

    if net_liq_df.empty:
        return {
            "name": "Net Liquidity (Fed - TGA - RRP)",
            "value": None,
            "notes": "无法获取完整的 WALCL/WTREGEN/RRPONTSYD 序列。"
        }

    latest_date = net_liq_df["date"].iloc[-1]
    latest_level = float(net_liq_df["value"].iloc[-1])

    # 历史统计
    historical_stats = calculate_long_term_stats(net_liq_df, latest_level)

    # 4周动量（保持向后兼容）
    net_liquidity_series = net_liq_df.set_index("date")["value"]
    net_liq_ma20 = net_liquidity_series.rolling(window=20, min_periods=5).mean()
    momentum_4w = None
    if len(net_liq_ma20.dropna()) >= 25:
        try:
            current_ma = net_liq_ma20.iloc[-1]
            past_ma = net_liq_ma20.iloc[-21]
            momentum_4w = float(current_ma - past_ma)
        except Exception:
            momentum_4w = None

    components = {
        "fed_assets": float(walcl_s.iloc[-1]),
        "tga": float(tga_s.iloc[-1]),
        "rrp": float(rrp_s.iloc[-1]),
    }

    return {
        "name": "Net Liquidity (Fed - TGA - RRP)",
        "series_id": "WALCL-WTREGEN-RRPONTSYD",
        "value": {
            "level": round(latest_level, 2),
            "momentum_4w": round(momentum_4w, 2) if momentum_4w is not None else None,
            "components": {k: round(v, 2) for k, v in components.items()},
            "historical_stats": historical_stats,
            "date": latest_date.strftime("%Y-%m-%d"),
        },
        "unit": "USD Billions",
        "source_name": "FRED",
        "notes": "净流动性；分层降噪：4周滚动动量（月度/周度趋势），替代日度动量。"
    }



def get_qqq_net_liquidity_ratio(end_date: str = None) -> Dict[str, Any]:
    """
    新指标：QQQ / Net Liquidity 比率（防前视偏差）。
    - 分子：QQQ 日频收盘价（yfinance）
    - 分母：净流动性（WALCL - WTREGEN - RRP），日频前向填充
    - 使用 TimeSeriesManager 对齐并持久化缓存。
    """
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    qqq_df = ts_manager.get_or_update_series("QQQ", _fetch_qqq_history)
    net_liq_df, _, _, _ = _build_net_liquidity_series()

    if qqq_df.empty or net_liq_df.empty:
        return {
            "name": "QQQ / Net Liquidity Ratio",
            "value": None,
            "notes": "分子或分母数据缺失，无法计算比率。"
        }

    # 过滤到指定日期之前，防止未来值
    qqq_df = qqq_df[qqq_df["date"] <= effective_date]
    net_liq_df = net_liq_df[net_liq_df["date"] <= effective_date]

    ratio_df = align_and_calculate_ratio(
        numerator_series=qqq_df[["date", "value"]],
        denominator_series=net_liq_df[["date", "value"]],
        date_col="date",
        value_col="value",
    )

    if ratio_df.empty:
        return {
            "name": "QQQ / Net Liquidity Ratio",
            "value": None,
            "notes": "对齐后序列为空，可能是日期缺口导致。"
        }

    latest_row = ratio_df.iloc[-1]
    latest_ratio = float(latest_row["ratio"])
    latest_date_str = latest_row["date"].strftime("%Y-%m-%d")

    stats_df = ratio_df.rename(columns={"ratio": "value"})
    historical_stats = calculate_long_term_stats(stats_df[["date", "value"]], latest_ratio)

    return {
        "name": "QQQ / Net Liquidity Ratio",
        "series_id": "QQQ_NET_LIQ_RATIO",
        "value": {
            "level": round(latest_ratio, 4),
            "historical_stats": historical_stats,
            "date": latest_date_str,
        },
        "unit": "ratio",
        "source_name": "yfinance + FRED (cached)",
        "notes": "分母采用向后对齐（backward）避免前视偏差。"
    }


def get_hyg_momentum(end_date: str = None) -> Dict[str, Any]:
    """获取高收益公司债ETF(HYG)的价格动量，作为信用利差的实时代理"""
    return _get_yf_series_with_analysis(ticker="HYG", name="High Yield Corp Bond (HYG) Momentum", end_date=end_date)

# =====================================================
# 第二层：市场内部结构
# =====================================================


def get_xly_xlp_ratio(end_date: str = None) -> Dict[str, Any]:
    """获取非必需消费品ETF(XLY)与必需消费品ETF(XLP)的比率及其动量与相对性。"""
    if not YF_AVAILABLE:
        return {
            "name": "XLY/XLP Ratio",
            "value": None,
            "notes": "yfinance library is not available."
        }

    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    # 尝试使用 TimeSeriesManager 获取数据
    try:
        xly_df = ts_manager.get_or_update_series("XLY", _fetch_xly_history)
        xlp_df = ts_manager.get_or_update_series("XLP", _fetch_xlp_history)

        if not xly_df.empty and not xlp_df.empty:
            xly_df = xly_df[xly_df["date"] <= effective_date]
            xlp_df = xlp_df[xlp_df["date"] <= effective_date]

            if not xly_df.empty and not xlp_df.empty:
                ratio_df = align_and_calculate_ratio(
                    numerator_series=xly_df[["date", "value"]],
                    denominator_series=xlp_df[["date", "value"]],
                    date_col="date",
                    value_col="value",
                )

                if not ratio_df.empty:
                    ratio_for_ma = ratio_df[["date", "ratio"]].rename(columns={"ratio": "value"})
                    latest_ratio = float(ratio_df.iloc[-1]["ratio"])
                    latest_date_str = ratio_df.iloc[-1]["date"].strftime("%Y-%m-%d")
                    historical_stats = calculate_long_term_stats(ratio_for_ma, latest_ratio)
                    ma_analysis = analyze_series_ratio_vs_ma(ratio_for_ma, ma_period=20) if len(ratio_df) >= 20 else {}
                    value_out = {
                        "level": round(latest_ratio, 4),
                        "historical_stats": historical_stats,
                        "date": latest_date_str,
                    }
                    if ma_analysis:
                        value_out["position_vs_ma20"] = ma_analysis.get("position_vs_ma")
                        value_out["ma20"] = ma_analysis.get("ma")
                    return {
                        "name": "XLY/XLP Ratio",
                        "value": value_out,
                        "unit": "ratio",
                        "source_name": "yfinance (cached)",
                        "notes": "XLY/XLP 风险偏好；分层降噪：比值相对 MA20 位置。"
                    }
    except Exception as e:
        logging.warning(f"TimeSeriesManager 获取 XLY/XLP 数据失败: {e}")

    # 回退到直接使用 yfinance 获取数据
    # 使用分单标的下载避免 MultiIndex 结构问题及 clean_yfinance_dataframe 破坏 ticker 信息
    try:
        start_date = effective_date - timedelta(days=365 * 11)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (effective_date + timedelta(days=1)).strftime("%Y-%m-%d")
        xly_df = yf.download("XLY", start=start_str, end=end_str, progress=False, auto_adjust=False)
        xlp_df = yf.download("XLP", start=start_str, end=end_str, progress=False, auto_adjust=False)
        xly_df = clean_yfinance_dataframe(xly_df)
        xlp_df = clean_yfinance_dataframe(xlp_df)
        if xly_df.empty or "close" not in xly_df.columns:
            raise ValueError("No data returned from yfinance for XLY.")
        if xlp_df.empty or "close" not in xlp_df.columns:
            raise ValueError("No data returned from yfinance for XLP.")
        xly_close = xly_df["close"].rename("xly")
        xlp_close = xlp_df["close"].rename("xlp")
        aligned_df = pd.concat([xly_close, xlp_close], axis=1).dropna()
        aligned_df.columns = ['xly', 'xlp']
        aligned_df['ratio'] = aligned_df['xly'] / aligned_df['xlp']
        
        if len(aligned_df) < 3:
            raise ValueError("Not enough valid data points for XLY/XLP ratio calculation.")
        
        # 转换为标准格式用于分析
        ratio_series = aligned_df[['ratio']].rename(columns={'ratio': 'value'})
        ratio_series.index = pd.to_datetime(ratio_series.index)
        ratio_series = ratio_series[ratio_series.index.date <= effective_date.date()]
        
        if ratio_series.empty:
            raise ValueError("No data available on or before the specified date.")
        
        # 分层降噪：比值相对 MA20 位置，替代日度动量
        ratio_for_analysis = ratio_series.reset_index()
        ratio_for_analysis.columns = ['date', 'value']
        analysis = analyze_series_ratio_vs_ma(ratio_for_analysis, ma_period=20) if len(ratio_for_analysis) >= 20 else {}
        latest_ratio = float(ratio_series.iloc[-1]['value'])
        latest_date_val = ratio_series.index[-1].strftime("%Y-%m-%d")
        stats = calculate_long_term_stats(ratio_for_analysis, latest_ratio)
        value_out = {"level": round(latest_ratio, 4), "date": latest_date_val, "historical_stats": stats}
        if analysis:
            value_out["position_vs_ma20"] = analysis.get("position_vs_ma")
            value_out["ma20"] = analysis.get("ma")

        return {
            "name": "XLY/XLP Ratio",
            "value": value_out,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": f"XLY/XLP 风险偏好；分层降噪：比值相对 MA20 位置。Raw: XLY={aligned_df['xly'].iloc[-1]:.2f}, XLP={aligned_df['xlp'].iloc[-1]:.2f}"
        }
    except Exception as e:
        return {
            "name": "XLY/XLP Ratio",
            "value": None,
            "notes": f"Failed to calculate: {str(e)}"
        }


def get_copper_gold_ratio(end_date: str = None) -> Dict[str, Any]:
    """获取铜期货(HG=F)与黄金期货(GC=F)的价格比率及其动量与相对性。"""
    if not YF_AVAILABLE:
        return {
            "name": "Copper/Gold Ratio",
            "value": None,
            "notes": "yfinance library is not available."
        }

    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    # 尝试使用 TimeSeriesManager 获取数据
    try:
        copper_df = ts_manager.get_or_update_series("HG=F", _fetch_copper_history)
        gold_df = ts_manager.get_or_update_series("GC=F", _fetch_gold_history)

        if not copper_df.empty and not gold_df.empty:
            copper_df = copper_df[copper_df["date"] <= effective_date]
            gold_df = gold_df[gold_df["date"] <= effective_date]

            if not copper_df.empty and not gold_df.empty:
                ratio_df = align_and_calculate_ratio(
                    numerator_series=copper_df[["date", "value"]],
                    denominator_series=gold_df[["date", "value"]],
                    date_col="date",
                    value_col="value",
                )

                if not ratio_df.empty:
                    ratio_for_ma = ratio_df[["date", "ratio"]].rename(columns={"ratio": "value"})
                    latest_ratio = float(ratio_df.iloc[-1]["ratio"])
                    latest_date_str = ratio_df.iloc[-1]["date"].strftime("%Y-%m-%d")
                    historical_stats = calculate_long_term_stats(ratio_for_ma, latest_ratio)
                    ma_analysis = analyze_series_ratio_vs_ma(ratio_for_ma, ma_period=50) if len(ratio_df) >= 50 else {}
                    value_out = {
                        "level": round(latest_ratio, 4),
                        "historical_stats": historical_stats,
                        "date": latest_date_str,
                    }
                    if ma_analysis:
                        value_out["position_vs_ma50"] = ma_analysis.get("position_vs_ma")
                        value_out["ma50"] = ma_analysis.get("ma")
                    return {
                        "name": "Copper/Gold Ratio",
                        "value": value_out,
                        "unit": "ratio",
                        "source_name": "yfinance (cached)",
                        "notes": "铜/金比率；分层降噪：比值相对 MA50 位置，替代日度动量。"
                    }
    except Exception as e:
        logging.warning(f"TimeSeriesManager 获取铜/金数据失败: {e}")

    # 回退到直接使用 yfinance 获取数据
    # 使用分单标的下载避免 MultiIndex 结构问题及 clean_yfinance_dataframe 破坏 ticker 信息
    try:
        start_date = effective_date - timedelta(days=365 * 11)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (effective_date + timedelta(days=1)).strftime("%Y-%m-%d")
        copper_df = yf.download("HG=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
        gold_df = yf.download("GC=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
        copper_df = clean_yfinance_dataframe(copper_df)
        gold_df = clean_yfinance_dataframe(gold_df)
        if copper_df.empty or "close" not in copper_df.columns:
            raise ValueError("No data returned from yfinance for HG=F (copper).")
        if gold_df.empty or "close" not in gold_df.columns:
            raise ValueError("No data returned from yfinance for GC=F (gold).")
        copper_close = copper_df["close"].rename("copper")
        gold_close = gold_df["close"].rename("gold")
        aligned_df = pd.concat([copper_close, gold_close], axis=1).dropna()
        aligned_df.columns = ['copper', 'gold']
        aligned_df['ratio'] = aligned_df['copper'] / aligned_df['gold']
        
        if len(aligned_df) < 3:
            raise ValueError("Not enough valid data points for Copper/Gold ratio calculation.")
        
        # 转换为标准格式用于分析
        ratio_series = aligned_df[['ratio']].rename(columns={'ratio': 'value'})
        ratio_series.index = pd.to_datetime(ratio_series.index)
        ratio_series = ratio_series[ratio_series.index.date <= effective_date.date()]
        
        if ratio_series.empty:
            raise ValueError("No data available on or before the specified date.")
        
        # 分层降噪：比值相对 MA50 位置，替代日度动量
        ratio_for_analysis = ratio_series.reset_index()
        ratio_for_analysis.columns = ['date', 'value']
        analysis = analyze_series_ratio_vs_ma(ratio_for_analysis, ma_period=50) if len(ratio_for_analysis) >= 50 else {}
        latest_ratio = float(ratio_series.iloc[-1]['value'])
        latest_date_val = ratio_series.index[-1].strftime("%Y-%m-%d")
        stats = calculate_long_term_stats(ratio_for_analysis, latest_ratio)
        value_out = {"level": round(latest_ratio, 4), "date": latest_date_val, "historical_stats": stats}
        if analysis:
            value_out["position_vs_ma50"] = analysis.get("position_vs_ma")
            value_out["ma50"] = analysis.get("ma")

        return {
            "name": "Copper/Gold Ratio",
            "value": value_out,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": f"铜/金比率；分层降噪：比值相对 MA50 位置。Raw: Copper={aligned_df['copper'].iloc[-1]:.2f}, Gold={aligned_df['gold'].iloc[-1]:.2f}"
        }
    except Exception as e:
        return {
            "name": "Copper/Gold Ratio",
            "value": None,
            "notes": f"Failed to calculate: {str(e)}"
        }


# =====================================================
# 新增指标 (任务2.2): DXY, SOFR, WTI, Gold/WTI Ratio
# =====================================================

def get_dxy_index(end_date: str = None) -> Dict[str, Any]:
    """
    获取美元指数 (DXY) - V6.0新增

    第一性原理:
    - 美元是全球储备货币，DXY衡量美元对一篮子主要货币(欧元、日元、英镑等)的强弱
    - 强美元(>100)通常压制新兴市场和美国出口企业盈利，利好进口和美国消费者
    - 弱美元(<90)利好美国出口商、大宗商品，通常伴随风险偏好上升

    数据来源: FRED (DTWEXBGS)
    分层降噪: MA20乖离率

    Args:
        end_date: 分析截止日期 (YYYY-MM-DD)

    Returns:
        DXY数据字典，包含水平值、历史百分位、趋势
    """
    series = get_fred_series("DTWEXBGS", end_date=end_date)
    if series is None or len(series) < 20:
        return {
            "name": "DXY Dollar Index",
            "series_id": "DTWEXBGS",
            "value": None,
            "unit": "index level",
            "source_name": "FRED",
            "notes": "数据不足，无法计算MA20乖离率。"
        }

    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats

    return {
        "name": "DXY Dollar Index",
        "series_id": "DTWEXBGS",
        "value": analysis,
        "unit": "index level",
        "source_name": "FRED",
        "notes": "美元指数；分层降噪：MA20乖离率。>100强势，<90弱势。强美元压制出口和新兴市场。"
    }


def get_sofr_rate(end_date: str = None) -> Dict[str, Any]:
    """
    获取SOFR担保隔夜融资利率 - V6.0新增

    第一性原理:
    - SOFR (Secured Overnight Financing Rate) 是LIBOR的替代基准利率
    - 基于真实交易（美国国债回购市场），比LIBOR更难操纵，更可靠
    - 反映银行间无担保借贷成本，是衡量美元流动性的关键指标
    - SOFR飙升 = 流动性紧张（如2019年9月回购危机）

    数据来源: FRED (SOFR)
    分层降噪: MA20乖离率

    Args:
        end_date: 分析截止日期 (YYYY-MM-DD)

    Returns:
        SOFR数据字典
    """
    series = get_fred_series("SOFR", end_date=end_date)
    if series is None or len(series) < 20:
        return {
            "name": "SOFR Rate",
            "series_id": "SOFR",
            "value": None,
            "unit": "percent",
            "source_name": "FRED",
            "notes": "数据不足，无法计算MA20乖离率。"
        }

    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats

    return {
        "name": "SOFR Rate",
        "series_id": "SOFR",
        "value": analysis,
        "unit": "percent",
        "source_name": "FRED",
        "notes": "SOFR担保隔夜融资利率；分层降噪：MA20乖离率。LIBOR的可靠替代品。SOFR飙升=流动性紧张。"
    }


def get_wti_oil(end_date: str = None) -> Dict[str, Any]:
    """
    获取WTI原油价格 - V6.0新增

    第一性原理:
    - WTI (West Texas Intermediate) 是美国基准原油，反映能源成本和通胀预期
    - 油价上升 → 通胀压力 → 美联储鹰派 → 股市承压（尤其消费股）
    - 油价下降 → 通缩风险 → 经济衰退担忧（尤其能源股）
    - 对纳斯达克而言，油价波动影响主要通过通胀预期传导

    数据来源: yfinance (CL=F)
    分层降噪: MA20乖离率 + 历史百分位

    Args:
        end_date: 分析截止日期 (YYYY-MM-DD)

    Returns:
        WTI数据字典
    """
    if not YF_AVAILABLE:
        return {
            "name": "WTI Crude Oil",
            "value": None,
            "unit": "USD/barrel",
            "source_name": "yfinance",
            "notes": "yfinance not available."
        }

    try:
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            effective_date = datetime.now()

        # 获取11年历史用于10年百分位
        start_date = effective_date - timedelta(days=365 * 11)

        df = yf.download(
            "CL=F",
            start=start_date.strftime("%Y-%m-%d"),
            end=(effective_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False
        )

        if df.empty:
            raise ValueError("yfinance returned empty dataframe for CL=F")

        df = clean_yfinance_dataframe(df)
        df.index = pd.to_datetime(df.index)
        df = df[df.index.date <= effective_date.date()]

        if len(df) < 20:
            raise ValueError(f"Insufficient data points: {len(df)}")

        current_price = float(df["close"].iloc[-1])
        latest_date = df.index[-1].strftime("%Y-%m-%d")

        # 计算MA20
        ma20 = float(df["close"].rolling(20, min_periods=20).mean().iloc[-1])

        # 计算历史统计
        series_for_stats = df[["close"]].reset_index()
        series_for_stats.columns = ["date", "value"]
        stats = calculate_long_term_stats(series_for_stats, current_price)

        analysis = {
            "level": round(current_price, 2),
            "date": latest_date,
            "ma20": round(ma20, 2),
            "deviation_pct": round((current_price - ma20) / ma20 * 100, 2) if ma20 > 0 else None,
            "position_vs_ma": "above" if current_price > ma20 else "below",
            "relativity": stats
        }

        return {
            "name": "WTI Crude Oil",
            "series_id": "CL=F",
            "value": analysis,
            "unit": "USD/barrel",
            "source_name": "yfinance",
            "notes": f"WTI原油价格；分层降噪：MA20乖离率。影响通胀预期。当前: ${current_price:.2f}"
        }

    except Exception as e:
        return {
            "name": "WTI Crude Oil",
            "value": None,
            "unit": "USD/barrel",
            "source_name": "yfinance",
            "notes": f"Failed to fetch WTI: {str(e)[:100]}"
        }


def get_gold_wti_ratio(end_date: str = None) -> Dict[str, Any]:
    """
    获取黄金/WTI原油比率 - V6.0新增

    第一性原理:
    - 黄金 = 避险资产 + 通胀对冲
    - WTI = 周期资产 + 通胀代理
    - Gold/WTI比率上升 → 避险需求 > 周期需求 → 衰退预期
    - Gold/WTI比率下降 → 周期需求 > 避险需求 → 复苏预期
    - 这是铜金比的替代/补充指标，尤其在铜数据不可靠时

    数据来源: yfinance (GC=F / CL=F)
    分层降噪: MA50相对位置

    Args:
        end_date: 分析截止日期 (YYYY-MM-DD)

    Returns:
        Gold/WTI比率数据字典
    """
    if not YF_AVAILABLE:
        return {
            "name": "Gold/WTI Ratio",
            "value": None,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": "yfinance not available."
        }

    try:
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            effective_date = datetime.now()

        start_date = effective_date - timedelta(days=365 * 11)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (effective_date + timedelta(days=1)).strftime("%Y-%m-%d")

        # 下载黄金和WTI数据
        gold_df = yf.download("GC=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
        wti_df = yf.download("CL=F", start=start_str, end=end_str, progress=False, auto_adjust=False)

        gold_df = clean_yfinance_dataframe(gold_df)
        wti_df = clean_yfinance_dataframe(wti_df)

        if gold_df.empty or "close" not in gold_df.columns:
            raise ValueError("No data for Gold (GC=F)")
        if wti_df.empty or "close" not in wti_df.columns:
            raise ValueError("No data for WTI (CL=F)")

        # 对齐数据
        gold_close = gold_df["close"].rename("gold")
        wti_close = wti_df["close"].rename("wti")
        aligned = pd.concat([gold_close, wti_close], axis=1).dropna()

        if len(aligned) < 50:
            raise ValueError(f"Insufficient aligned data: {len(aligned)} days")

        # 计算比率
        aligned["ratio"] = aligned["gold"] / aligned["wti"]

        # 获取最新值
        latest_ratio = float(aligned["ratio"].iloc[-1])
        latest_gold = float(aligned["gold"].iloc[-1])
        latest_wti = float(aligned["wti"].iloc[-1])
        latest_date = aligned.index[-1].strftime("%Y-%m-%d")

        # 计算MA50和统计
        ma50 = float(aligned["ratio"].rolling(50, min_periods=50).mean().iloc[-1])

        series_for_stats = aligned[["ratio"]].reset_index()
        series_for_stats.columns = ["date", "value"]
        stats = calculate_long_term_stats(series_for_stats, latest_ratio)

        value_out = {
            "level": round(latest_ratio, 4),
            "date": latest_date,
            "ma50": round(ma50, 4),
            "position_vs_ma50": "above" if latest_ratio > ma50 else "below",
            "relativity": stats
        }

        return {
            "name": "Gold/WTI Ratio",
            "series_id": "GC_F_CL_F_RATIO",
            "value": value_out,
            "unit": "ratio (oz/barrel)",
            "source_name": "yfinance",
            "notes": f"黄金/WTI比率；分层降噪：MA50相对位置。衰退/周期代理。Gold=${latest_gold:.2f}, WTI=${latest_wti:.2f}"
        }

    except Exception as e:
        return {
            "name": "Gold/WTI Ratio",
            "value": None,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": f"Failed to calculate: {str(e)[:100]}"
        }


# =====================================================
# 工具注册表（整合所有层级函数）
# =====================================================

