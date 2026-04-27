# tools_L3.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第3层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

# =====================================================
# 第3层函数
# =====================================================

def get_ndx100_components(end_date: Optional[str] = None) -> List[str]:
    """
    多源混合策略获取纳斯达克100成分股列表 (V6.1 历史回测优化版)
    
    优先级顺序：
    - 回测模式（有end_date）：
        1. nasdaq-100-ticker-history（历史数据库，最优先）
        2. 纳斯达克官网API（备用）
        3. Wikipedia（备用）
        4. 静态后备列表（兜底）
    
    - 实时模式（无end_date）：
        1. 纳斯达克官网API（最权威、最准确）
        2. Wikipedia实时爬取（实时更新）
        3. nasdaq-100-ticker-history（备用）
        4. 静态后备列表（兜底）
    
    参数:
        end_date: 指定日期（YYYY-MM-DD），用于历史回测
    
    返回:
        成分股代码列表
    """
    
    # ========================================
    # 回测模式：优先使用历史数据库
    # ========================================
    if end_date:
        logging.info(f"回测模式：正在获取 {end_date} 的历史成分股...")
        
        # 策略1: nasdaq-100-ticker-history（历史数据库，最优先）
        try:
            from nasdaq_100_ticker_history import tickers_as_of
            
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
            req_year, req_month, req_day = effective_date.year, effective_date.month, effective_date.day
            
            try:
                components = tickers_as_of(year=req_year, month=req_month, day=req_day)
                tickers = [str(ticker).upper() for ticker in components]
                logging.info(f"✅ 成功从历史数据库获取 {len(tickers)} 只成分股（{end_date}）")
                return tickers
            except Exception as e:
                # 当请求年份尚未有数据时，尝试回退到最近可用年份
                err_str = str(e).lower()
                if "cant find resource" in err_str or "n100-ticker-changes" in err_str:
                    logging.warning(f"历史数据库无 {end_date} 数据，尝试回退到最近可用年份...")
                    for fallback_year in range(effective_date.year - 1, effective_date.year - 6, -1):
                        if fallback_year < 2000:
                            break
                        try:
                            components = tickers_as_of(year=fallback_year, month=12, day=31)
                            if components:
                                tickers = [str(ticker).upper() for ticker in components]
                                logging.warning(f"使用 {fallback_year} 年末成分股（{len(tickers)} 只）作为近似")
                                return tickers
                        except Exception:
                            continue
                raise
                
        except ImportError:
            logging.warning("nasdaq_100_ticker_history 未安装，回测模式降级到实时数据源")
        except Exception as e:
            logging.warning(f"从历史数据库获取失败: {str(e)[:100]}，尝试备用方案")
        
        # 回测模式下，如果历史数据库失败，继续尝试其他方案
        logging.warning(f"⚠️ 历史数据不可用，使用最新成分股（可能存在幸存者偏差）")
    
    # ========================================
    # 策略1: 纳斯达克官网API（最优先）
    # ========================================
    try:
        logging.info("正在从纳斯达克官网API获取成分股...")
        url = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        if 'data' in data and 'data' in data['data'] and 'rows' in data['data']['data']:
            rows = data['data']['data']['rows']
            tickers = [row['symbol'].upper() for row in rows if 'symbol' in row]
            
            if len(tickers) >= 90:  # 合理性检查
                logging.info(f"✅ 成功从纳斯达克官网API获取 {len(tickers)} 只成分股")
                return tickers
            else:
                logging.warning(f"纳斯达克API返回数量异常: {len(tickers)} 只（预期≥90）")
        else:
            logging.warning("纳斯达克API响应格式不符合预期")
            
    except Exception as e:
        logging.warning(f"纳斯达克官网API获取失败: {str(e)[:100]}")
    
    # ========================================
    # 策略2: Wikipedia爬取（次优先）
    # ========================================
    try:
        logging.info("正在从Wikipedia爬取成分股...")
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # 尝试导入BeautifulSoup
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logging.warning("BeautifulSoup未安装，跳过Wikipedia爬取")
            raise
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 查找包含成分股的表格
        tables = soup.find_all('table', {'class': 'wikitable'})
        
        for table in tables:
            headers_row = [th.get_text(strip=True) for th in table.find_all('th')]
            
            # 查找Ticker或Symbol列
            ticker_index = -1
            for idx, header in enumerate(headers_row):
                if header in ['Ticker', 'Symbol', 'ticker', 'symbol']:
                    ticker_index = idx
                    break
            
            if ticker_index == -1:
                continue
            
            # 提取ticker
            tickers = []
            for row in table.find_all('tr')[1:]:  # 跳过表头
                cells = row.find_all('td')
                if len(cells) > ticker_index:
                    ticker = cells[ticker_index].get_text(strip=True)
                    ticker = ticker.replace('\n', '').replace('\xa0', '').strip()
                    if ticker and (ticker.replace('.', '').replace('-', '').isalpha() or ticker.isalnum()):
                        tickers.append(ticker.upper())
            
            if len(tickers) >= 90:
                logging.info(f"✅ 成功从Wikipedia获取 {len(tickers)} 只成分股")
                return tickers
        
        logging.warning("Wikipedia未找到有效的成分股表格")
        
    except Exception as e:
        logging.warning(f"从Wikipedia获取失败: {str(e)[:100]}")
    
    # ========================================
    # 策略3: GitHub项目 nasdaq-100-ticker-history
    # ========================================
    try:
        from nasdaq_100_ticker_history import tickers_as_of
        
        logging.info("正在从GitHub项目获取成分股...")
        
        # 尝试获取当前年份数据
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            effective_date = datetime.now()
        
        req_year, req_month, req_day = effective_date.year, effective_date.month, effective_date.day
        
        try:
            components = tickers_as_of(year=req_year, month=req_month, day=req_day)
            tickers = [str(ticker).upper() for ticker in components]
            logging.info(f"✅ 成功从GitHub项目获取 {len(tickers)} 只成分股（数据日期：{req_year}-{req_month:02d}-{req_day:02d}）")
            return tickers
        except Exception as e:
            # 当请求年份尚未有数据时，尝试回退到最近可用年份
            err_str = str(e).lower()
            if "cant find resource" in err_str or "n100-ticker-changes" in err_str:
                for fallback_year in range(effective_date.year - 1, effective_date.year - 6, -1):
                    if fallback_year < 2000:
                        break
                    try:
                        components = tickers_as_of(year=fallback_year, month=12, day=31)
                        if components:
                            tickers = [str(ticker).upper() for ticker in components]
                            logging.warning(f"GitHub项目无 {effective_date.year} 年数据，使用 {fallback_year} 年末成分股（{len(tickers)} 只）")
                            return tickers
                    except Exception:
                        continue
            raise
            
    except ImportError:
        logging.warning("nasdaq_100_ticker_history 未安装，跳过GitHub项目方法")
    except Exception as e:
        logging.warning(f"从GitHub项目获取失败: {str(e)[:100]}")
    
    # ========================================
    # 策略4: 静态后备列表（兜底）
    # ========================================
    logging.warning("⚠️ 所有动态获取方式失败，使用静态后备列表（基于纳斯达克官网API 2026-02-06）")
    logging.info(f"静态后备列表包含 {len(NDX100_COMPONENTS_FALLBACK)} 只成分股")
    return NDX100_COMPONENTS_FALLBACK

# =====================================================
# V5.1 高级辅助函数
# =====================================================


def calculate_quantitative_moat_score(info: dict) -> Tuple[float, str]:
    """根据公开财务数据计算代理护城河分数 (0-10分制)"""
    score = 0
    notes = []

    # 1. 资本回报率 (ROE) - 满分4分
    roe = info.get("returnOnEquity")
    if roe is not None:
        if roe > 0.25:
            score += 4
        elif roe > 0.15:
            score += 3
        elif roe > 0.05:
            score += 1.5
        notes.append(f"ROE({roe:.1%})")

    # 2. 毛利率 - 满分3分
    gross_margin = info.get("grossMargins")
    if gross_margin is not None:
        if gross_margin > 0.60:
            score += 3
        elif gross_margin > 0.40:
            score += 2
        elif gross_margin > 0.20:
            score += 1
        notes.append(f"GM({gross_margin:.1%})")

    # 3. 营业利润率 - 满分3分
    op_margin = info.get("operatingMargins")
    if op_margin is not None:
        if op_margin > 0.25:
            score += 3
        elif op_margin > 0.15:
            score += 2
        elif op_margin > 0.05:
            score += 1
        notes.append(f"OM({op_margin:.1%})")

    return round(score, 1), ", ".join(notes)


def get_m7_fundamentals(end_date: str = None) -> Dict[str, Any]:
    """
    获取M7公司基本面 - 优先yfinance，失败时用Alpha Vantage（修复版）
    注意：此函数获取的是最新的基本面数据，end_date参数仅用于保持签名一致性，
    因为yfinance的.info和AlphaVantage的OVERVIEW不直接支持历史时点查询。
    """
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    m7_data = {}
    data_source = "mixed"

    if YF_AVAILABLE:
        for ticker in M7_TICKERS:
            try:
                info = get_yf_ticker_info_with_retry(ticker, attempts=3, pause_seconds=1.0)

                # 验证是否获取到有效数据
                if not info or 'marketCap' not in info:
                    raise Exception("Invalid info data")

                # 计算量化护城河分数
                moat_score, moat_notes = calculate_quantitative_moat_score(info)

                m7_data[ticker] = {
                    "PE": info.get("trailingPE"),
                    "ForwardPE": info.get("forwardPE"),
                    "PEG": info.get("pegRatio"),
                    "ROE": info.get("returnOnEquity") * 100 if info.get("returnOnEquity") else None,
                    "EPS": info.get("trailingEps"),
                    "MarketCap": info.get("marketCap"),
                    "ProfitMargin": info.get("profitMargins") * 100 if info.get("profitMargins") else None,
                    "GrossMargin": info.get("grossMargins") * 100 if info.get("grossMargins") else None,
                    "OperatingMargin": info.get("operatingMargins") * 100 if info.get("operatingMargins") else None,
                    "Price": info.get("currentPrice") or info.get("regularMarketPrice"),
                    "52WeekHigh": info.get("fiftyTwoWeekHigh"),
                    "52WeekLow": info.get("fiftyTwoWeekLow"),
                    "quantitative_moat_score": moat_score,
                    "quantitative_moat_notes": moat_notes,
                    "source": "yfinance"
                }
            except Exception as e:
                print(f"yfinance failed for {ticker}: {str(e)[:30]}")
                m7_data[ticker] = {"error": "yfinance failed", "source": "failed"}

    # 处理yfinance获取失败的标的，尝试Alpha Vantage降级
    failed_tickers = [t for t in M7_TICKERS if t not in m7_data or m7_data[t].get("error")]
    alphavantage_api_key = get_alphavantage_api_key()
    if failed_tickers and alphavantage_api_key:
        for ticker in failed_tickers:
            try:
                # Alpha Vantage获取基本面数据（简化版，仅核心指标）
                params = {
                    "function": "OVERVIEW",
                    "symbol": ticker,
                    "apikey": alphavantage_api_key
                }
                data = safe_request(get_alphavantage_base_url(), params)
                if not data or "Symbol" not in data:
                    raise Exception("No data from Alpha Vantage")

                # 计算简化版护城河分数（基于可用字段）
                roe = float(data.get("ReturnOnEquity", 0)) / 100 if data.get("ReturnOnEquity") else None
                gross_margin = float(data.get("GrossMargin", 0)) / 100 if data.get("GrossMargin") else None
                op_margin = float(data.get("OperatingMargin", 0)) / 100 if data.get("OperatingMargin") else None

                score = 0
                notes = []
                if roe:
                    score += 4 if roe > 0.25 else 3 if roe > 0.15 else 1.5 if roe > 0.05 else 0
                    notes.append(f"ROE({roe:.1%})")
                if gross_margin:
                    score += 3 if gross_margin > 0.6 else 2 if gross_margin > 0.4 else 1 if gross_margin > 0.2 else 0
                    notes.append(f"GM({gross_margin:.1%})")
                if op_margin:
                    score += 3 if op_margin > 0.25 else 2 if op_margin > 0.15 else 1 if op_margin > 0.05 else 0
                    notes.append(f"OM({op_margin:.1%})")

                # 获取价格数据（日频）
                time.sleep(13)  # 避免API限流
                price_params = {
                    "function": "TIME_SERIES_DAILY",
                    "symbol": ticker,
                    "apikey": alphavantage_api_key,
                    "outputsize": "compact"
                }
                price_data = safe_request(get_alphavantage_base_url(), price_params)
                latest_date_val = max(price_data["Time Series (Daily)"].keys()) if price_data.get("Time Series (Daily)") else None
                latest_price = float(price_data["Time Series (Daily)"][latest_date_val]["4. close"]) if latest_date_val else None

                m7_data[ticker] = {
                    "PE": float(data.get("PERatio")) if data.get("PERatio") else None,
                    "ForwardPE": float(data.get("ForwardPE")) if data.get("ForwardPE") else None,
                    "PEG": float(data.get("PEGRatio")) if data.get("PEGRatio") else None,
                    "ROE": float(data.get("ReturnOnEquity")) if data.get("ReturnOnEquity") else None,
                    "EPS": float(data.get("EPS")) if data.get("EPS") else None,
                    "MarketCap": int(data.get("MarketCapitalization")) if data.get("MarketCapitalization") else None,
                    "ProfitMargin": float(data.get("ProfitMargin")) if data.get("ProfitMargin") else None,
                    "GrossMargin": float(data.get("GrossMargin")) if data.get("GrossMargin") else None,
                    "OperatingMargin": float(data.get("OperatingMargin")) if data.get("OperatingMargin") else None,
                    "Price": latest_price,
                    "52WeekHigh": float(data.get("52WeekHigh")) if data.get("52WeekHigh") else None,
                    "52WeekLow": float(data.get("52WeekLow")) if data.get("52WeekLow") else None,
                    "quantitative_moat_score": round(score, 1),
                    "quantitative_moat_notes": ", ".join(notes) if notes else "Insufficient data",
                    "source": "Alpha Vantage"
                }
            except Exception as e:
                m7_data[ticker] = {"error": str(e)[:50], "source": "failed"}
    elif not failed_tickers:
        data_source = "yfinance"

    # 计算汇总统计
    valid_pe = [v.get("PE", 0) for v in m7_data.values() if isinstance(v, dict) and v.get("PE") and not v.get("error")]
    valid_roe = [v.get("ROE", 0) for v in m7_data.values() if isinstance(v, dict) and v.get("ROE") and not v.get("error")]
    total_market_cap = sum(v.get("MarketCap", 0) for v in m7_data.values() if isinstance(v, dict) and v.get("MarketCap") and not v.get("error"))
    weighted_moat_score = 0

    if total_market_cap > 0:
        for v in m7_data.values():
            if isinstance(v, dict) and v.get("MarketCap") and v.get("quantitative_moat_score") is not None and not v.get("error"):
                weight = v["MarketCap"] / total_market_cap
                weighted_moat_score += v["quantitative_moat_score"] * weight

    summary = {
        "avg_PE": round(np.mean(valid_pe), 2) if valid_pe else None,
        "avg_ROE": round(np.mean(valid_roe), 2) if valid_roe else None,
        "weighted_quantitative_moat": round(weighted_moat_score, 2),
        "count": len([v for v in m7_data.values() if isinstance(v, dict) and not v.get("error")])
    }

    return {
        "name": "M7 Fundamentals",
        "series_id": "M7_COMPOSITE",
        "value": m7_data,
        "unit": "mixed",
        "date": effective_date.strftime("%Y-%m-%d"),
        "source_name": data_source,
        "source_url": "Mixed: yfinance + Alpha Vantage",
        "notes": f"Successfully fetched {summary['count']}/7 companies. Note: Fetches latest data available.",
        "summary": summary
    }

# =====================================================
# 第四层：指数基本面与拥挤度（修复版）
# =====================================================

