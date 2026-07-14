# tools_L3.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第3层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

from datetime import timezone
from typing import Any, Dict, List, Optional, Tuple

# =====================================================
# 第3层函数
# =====================================================

def get_ndx100_components_with_provenance(end_date: Optional[str] = None) -> Tuple[List[str], Dict[str, Any]]:
    """
    多源混合策略获取纳斯达克100成分股列表，并返回来源溯源信息 (V7.0 幸存者偏差硬防线版)

    优先级顺序：
    - 回测模式（有end_date）：
        只信任 nasdaq-100-ticker-history（历史数据库）。一旦该数据库不可用
        （未安装 / 查询失败 / 返回空），立即抛出 HistoricalUniverseUnavailable，
        绝不落回任何"当前"成分股来源——落回会把幸存者偏差静默注入回测。

    - 实时模式（无end_date）：
        1. 纳斯达克官网API（最权威、最准确）
        2. Wikipedia实时爬取（实时更新）
        3. nasdaq-100-ticker-history（备用，取当前日期）
        4. 静态后备列表（兜底）

    参数:
        end_date: 指定日期（YYYY-MM-DD），用于历史回测

    返回:
        (成分股代码列表, provenance字典)
        provenance 至少包含 universe_source / as_of / retrieved_at / count

    异常:
        HistoricalUniverseUnavailable: 回测模式下历史数据库不可用时抛出
    """
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # ========================================
    # 回测模式：只信任历史数据库，失败即硬失败（不落回当前名单）
    # ========================================
    if end_date:
        logging.info(f"回测模式：正在获取 {end_date} 的历史成分股...")

        try:
            from nasdaq_100_ticker_history import tickers_as_of
        except ImportError:
            raise HistoricalUniverseUnavailable("nasdaq_100_ticker_history_not_installed", end_date) from None

        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
        req_year, req_month, req_day = effective_date.year, effective_date.month, effective_date.day

        def _historical_provenance(tickers: List[str]) -> Dict[str, Any]:
            return {
                "universe_source": "historical_library",
                "as_of": end_date,
                "retrieved_at": retrieved_at,
                "count": len(tickers),
            }

        try:
            components = tickers_as_of(year=req_year, month=req_month, day=req_day)
            tickers = [str(ticker).upper() for ticker in components]
            if not tickers:
                raise HistoricalUniverseUnavailable("historical_library_empty_result", end_date)
            logging.info(f"✅ 成功从历史数据库获取 {len(tickers)} 只成分股（{end_date}）")
            return tickers, _historical_provenance(tickers)
        except HistoricalUniverseUnavailable:
            raise
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
                            provenance = _historical_provenance(tickers)
                            # 近似分支必须如实声明实际名单日期，不得冒充请求日期的历史名单
                            provenance["as_of"] = f"{fallback_year}-12-31"
                            provenance["approximation_of"] = end_date
                            provenance["approximation_note"] = (
                                f"历史库无 {end_date} 数据，使用 {fallback_year} 年末名单作为近似（早于请求日期，无未来信息泄漏）"
                            )
                            return tickers, provenance
                    except Exception:
                        continue
            raise HistoricalUniverseUnavailable(f"historical_library_query_failed: {str(e)[:160]}", end_date) from e

    # ========================================
    # 实时模式 策略1: 纳斯达克官网API（最优先）
    # ========================================
    live_as_of = datetime.now().strftime("%Y-%m-%d")
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
                return tickers, {
                    "universe_source": "nasdaq_api",
                    "as_of": live_as_of,
                    "retrieved_at": retrieved_at,
                    "count": len(tickers),
                }
            else:
                logging.warning(f"纳斯达克API返回数量异常: {len(tickers)} 只（预期≥90）")
        else:
            logging.warning("纳斯达克API响应格式不符合预期")

    except Exception as e:
        logging.warning(f"纳斯达克官网API获取失败: {str(e)[:100]}")

    # ========================================
    # 实时模式 策略2: Wikipedia爬取（次优先）
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
                return tickers, {
                    "universe_source": "wikipedia",
                    "as_of": live_as_of,
                    "retrieved_at": retrieved_at,
                    "count": len(tickers),
                }

        logging.warning("Wikipedia未找到有效的成分股表格")

    except Exception as e:
        logging.warning(f"从Wikipedia获取失败: {str(e)[:100]}")

    # ========================================
    # 实时模式 策略3: GitHub项目 nasdaq-100-ticker-history
    # ========================================
    try:
        from nasdaq_100_ticker_history import tickers_as_of

        logging.info("正在从GitHub项目获取成分股...")

        effective_date = datetime.now()
        req_year, req_month, req_day = effective_date.year, effective_date.month, effective_date.day

        try:
            components = tickers_as_of(year=req_year, month=req_month, day=req_day)
            tickers = [str(ticker).upper() for ticker in components]
            logging.info(f"✅ 成功从GitHub项目获取 {len(tickers)} 只成分股（数据日期：{req_year}-{req_month:02d}-{req_day:02d}）")
            return tickers, {
                "universe_source": "github_library",
                "as_of": live_as_of,
                "retrieved_at": retrieved_at,
                "count": len(tickers),
            }
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
                            return tickers, {
                                "universe_source": "github_library",
                                "as_of": live_as_of,
                                "retrieved_at": retrieved_at,
                                "count": len(tickers),
                            }
                    except Exception:
                        continue
            raise

    except ImportError:
        logging.warning("nasdaq_100_ticker_history 未安装，跳过GitHub项目方法")
    except Exception as e:
        logging.warning(f"从GitHub项目获取失败: {str(e)[:100]}")

    # ========================================
    # 实时模式 策略4: 静态后备列表（兜底）
    # ========================================
    logging.warning("⚠️ 所有动态获取方式失败，使用静态后备列表（基于纳斯达克官网API 2026-02-06）")
    logging.info(f"静态后备列表包含 {len(NDX100_COMPONENTS_FALLBACK)} 只成分股")
    return NDX100_COMPONENTS_FALLBACK, {
        "universe_source": "static_fallback",
        "as_of": live_as_of,
        "retrieved_at": retrieved_at,
        "count": len(NDX100_COMPONENTS_FALLBACK),
    }


def get_ndx100_components(end_date: Optional[str] = None) -> List[str]:
    """
    多源混合策略获取纳斯达克100成分股列表 (薄封装，见 get_ndx100_components_with_provenance)。

    保持既有签名与返回类型不变；调用方若需要来源溯源信息，请改用
    get_ndx100_components_with_provenance。

    参数:
        end_date: 指定日期（YYYY-MM-DD），用于历史回测

    返回:
        成分股代码列表

    异常:
        HistoricalUniverseUnavailable: 回测模式下历史数据库不可用时抛出
    """
    tickers, _provenance = get_ndx100_components_with_provenance(end_date=end_date)
    return tickers


INVESCO_QQQ_HOLDINGS_URL = (
    "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/"
    "holdings/fund?idType=ticker&interval=monthly&productType=ETF"
)
INVESCO_QQQ_HOLDINGS_PAGE = "https://www.invesco.com/qqq-etf/en/about.html#top-10-holdings"


def _qqq_holdings_archive_dir() -> str:
    path = os.path.join(path_config.cache_dir, "market_archive", "qqq_holdings")
    os.makedirs(path, exist_ok=True)
    return path


def _qqq_holdings_effective_date(payload: Dict[str, Any]) -> str:
    raw = payload.get("effectiveBusinessDate") or payload.get("effectiveDate")
    if raw:
        try:
            return pd.to_datetime(raw).strftime("%Y-%m-%d")
        except Exception:
            return str(raw)[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _write_qqq_holdings_snapshot(payload: Dict[str, Any]) -> None:
    holdings = payload.get("holdings") if isinstance(payload, dict) else None
    if not isinstance(holdings, list) or len(holdings) < 10:
        return
    effective = _qqq_holdings_effective_date(payload)
    archive_payload = {
        "cached_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "effective_date": effective,
        "source_url": INVESCO_QQQ_HOLDINGS_URL,
        "payload": payload,
    }
    try:
        dated_path = os.path.join(_qqq_holdings_archive_dir(), f"{effective}.json")
        latest_path = os.path.join(_qqq_holdings_archive_dir(), "latest.json")
        for path in [dated_path, latest_path]:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(archive_payload, handle, ensure_ascii=False, default=str)
                handle.write("\n")
    except Exception as exc:
        logging.warning("Failed writing QQQ holdings snapshot: %s", exc)


def _read_latest_qqq_holdings_snapshot() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    path = os.path.join(_qqq_holdings_archive_dir(), "latest.json")
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            archive_payload = json.load(handle)
        payload = archive_payload.get("payload")
        holdings = payload.get("holdings") if isinstance(payload, dict) else None
        if isinstance(holdings, list) and len(holdings) >= 10:
            return payload, archive_payload
    except Exception as exc:
        logging.warning("Failed reading QQQ holdings snapshot: %s", exc)
    return None, None


def _fetch_invesco_qqq_holdings() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        response = requests.get(
            INVESCO_QQQ_HOLDINGS_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.invesco.com",
                "Referer": "https://www.invesco.com/qqq-etf/en/about.html",
            },
            timeout=12,
            proxies=get_requests_proxies(),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("holdings"), list):
            return None, "Invesco holdings response missing holdings list"
        _write_qqq_holdings_snapshot(data)
        return data, None
    except Exception as exc:
        return None, str(exc)[:160]


def _normalize_qqq_holding(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ticker = str(row.get("ticker") or "").strip().upper()
    weight = row.get("percentageOfTotalNetAssets")
    try:
        weight_pct = float(weight)
    except Exception:
        return None
    if not ticker or weight_pct <= 0:
        return None
    return {
        "ticker": ticker,
        "issuer_name": row.get("issuerName"),
        "weight_pct": round(weight_pct, 4),
        "units": row.get("units"),
        "security_type": row.get("securityTypeName"),
    }


def _concentration_weight_change_proxy(
    holdings: List[Dict[str, Any]],
    effective_date: datetime,
    lookback_days: int,
) -> Optional[Dict[str, Any]]:
    if not YF_AVAILABLE or not holdings:
        return None
    tickers = [item["ticker"] for item in holdings[:10] if item.get("ticker")]
    if not tickers:
        return None
    start_date = effective_date - timedelta(days=lookback_days + 14)
    try:
        prices = cached_yf_download(
            tickers,
            start=start_date,
            end=effective_date + timedelta(days=1),
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if isinstance(prices.columns, pd.MultiIndex):
            close = prices["Close"] if "Close" in prices.columns.get_level_values(0) else prices["Adj Close"]
        else:
            close_col = "Close" if "Close" in prices.columns else "Adj Close"
            close = prices[[close_col]].rename(columns={close_col: tickers[0]})
        close = close.dropna(how="all")
        if len(close) < 3:
            return None
        latest = close.iloc[-1]
        prior = close.iloc[0]
        current_weights = {item["ticker"]: float(item["weight_pct"]) for item in holdings[:10]}
        prior_weights = {}
        for ticker, current_weight in current_weights.items():
            latest_price = latest.get(ticker)
            prior_price = prior.get(ticker)
            if latest_price and prior_price and latest_price > 0 and prior_price > 0:
                prior_weights[ticker] = current_weight / (float(latest_price) / float(prior_price))
        if not prior_weights:
            return None
        current_top10 = sum(current_weights.values())
        prior_top10 = sum(prior_weights.values())
        scale = 100.0 / (prior_top10 + (100.0 - current_top10)) if prior_top10 > 0 else None
        prior_top10_normalized = prior_top10 * scale if scale else None
        if prior_top10_normalized is None:
            return None
        return {
            "lookback_days": lookback_days,
            "current_top10_weight_pct": round(current_top10, 2),
            "prior_top10_weight_proxy_pct": round(prior_top10_normalized, 2),
            "change_pct_points": round(current_top10 - prior_top10_normalized, 2),
            "methodology": "Proxy: reverse current top-10 QQQ weights by constituent price returns; not official historical weights.",
        }
    except Exception:
        return None


def _ndx_equal_weight_performance_spread(effective_date: datetime) -> Dict[str, Any]:
    if not YF_AVAILABLE:
        return {"availability": "unavailable", "reason": "yfinance unavailable"}
    start_date = effective_date - timedelta(days=220)
    try:
        ndx = clean_yfinance_dataframe(
            cached_yf_download("^NDX", start=start_date, end=effective_date + timedelta(days=1), progress=False, auto_adjust=True)
        )
        ndxe = clean_yfinance_dataframe(
            cached_yf_download("^NDXE", start=start_date, end=effective_date + timedelta(days=1), progress=False, auto_adjust=True)
        )
        if ndx.empty or ndxe.empty or "close" not in ndx.columns or "close" not in ndxe.columns:
            return {"availability": "unavailable", "reason": "NDX/NDXE close series unavailable"}
        df = pd.concat([ndx["close"].rename("ndx"), ndxe["close"].rename("ndxe")], axis=1).dropna()
        if len(df) < 22:
            return {"availability": "unavailable", "reason": "insufficient common NDX/NDXE history"}
        out: Dict[str, Any] = {"availability": "available", "source_name": "yfinance daily close", "windows": {}}
        for label, rows in [("1m", 21), ("3m", 63), ("6m", 126)]:
            if len(df) <= rows:
                continue
            latest = df.iloc[-1]
            prior = df.iloc[-rows - 1]
            ndx_return = float(latest["ndx"] / prior["ndx"] - 1) * 100
            ndxe_return = float(latest["ndxe"] / prior["ndxe"] - 1) * 100
            out["windows"][label] = {
                "ndx_return_pct": round(ndx_return, 2),
                "ndxe_return_pct": round(ndxe_return, 2),
                "market_cap_minus_equal_weight_pct": round(ndx_return - ndxe_return, 2),
                "ratio_change_pct": round(float((latest["ndx"] / latest["ndxe"]) / (prior["ndx"] / prior["ndxe"]) - 1) * 100, 2),
            }
        return out
    except Exception as exc:
        return {"availability": "unavailable", "reason": str(exc)[:120]}


def _qqq_equal_weight_performance_spread(effective_date: datetime) -> Dict[str, Any]:
    """Backward-compatible alias for tests and older call sites.

    The implementation uses NDX vs NDXE because QQQ is the tradable proxy while
    the research comparison should stay anchored to the underlying index pair.
    """
    return _ndx_equal_weight_performance_spread(effective_date)


def get_qqq_top10_concentration(end_date: str = None) -> Dict[str, Any]:
    """QQQ official holdings anchor for Top10 concentration and cap-weighted vs equal-weight spread."""
    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    if end_date:
        return {
            "name": "QQQ Top10 Concentration",
            "series_id": "INVESCO_QQQ_HOLDINGS",
            "value": None,
            "unit": "percent",
            "date": end_date,
            "source_name": "Invesco QQQ official holdings API",
            "source_url": INVESCO_QQQ_HOLDINGS_PAGE,
            "source_tier": "unavailable",
            "notes": "Backtest/snapshot mode skipped: current Invesco holdings must not be used as historical QQQ top-10 concentration evidence.",
            "data_quality": {
                "effective_date": end_date,
                "fallback_reason": "no_official_historical_qqq_holdings_snapshot",
                "coverage": {"holdings_reported": 0, "total_holdings": None},
                "anomalies": ["historical_holdings_unavailable", "live_current_holdings_not_used"],
                "fallback_chain": ["official_historical_holdings", "unavailable"],
            },
        }
    payload, error = _fetch_invesco_qqq_holdings()
    snapshot_meta: Optional[Dict[str, Any]] = None
    used_cached_snapshot = False
    if payload is None:
        payload, snapshot_meta = _read_latest_qqq_holdings_snapshot()
        used_cached_snapshot = payload is not None
    if payload is None:
        return {
            "name": "QQQ Top10 Concentration",
            "series_id": "INVESCO_QQQ_HOLDINGS",
            "value": None,
            "unit": "percent",
            "source_name": "Invesco QQQ official holdings API",
            "source_url": INVESCO_QQQ_HOLDINGS_PAGE,
            "source_tier": "official_provider",
            "notes": f"Invesco holdings unavailable: {error}",
        }

    holdings = [
        normalized
        for normalized in (_normalize_qqq_holding(row) for row in payload.get("holdings", []))
        if normalized is not None
    ]
    holdings.sort(key=lambda item: item["weight_pct"], reverse=True)
    top10 = holdings[:10]
    total_holdings = int(payload.get("totalNumberOfHoldings") or len(holdings))
    top10_weight = sum(item["weight_pct"] for item in top10)
    top5_weight = sum(item["weight_pct"] for item in holdings[:5])
    top3_weight = sum(item["weight_pct"] for item in holdings[:3])
    alphabet_adjusted_m7 = set(M7_TICKERS) | {"GOOG"}
    m7_weight = sum(item["weight_pct"] for item in holdings if item["ticker"] in alphabet_adjusted_m7)
    equal_weight_top10 = (10 / total_holdings * 100) if total_holdings else None
    effective = payload.get("effectiveBusinessDate") or payload.get("effectiveDate") or effective_date.strftime("%Y-%m-%d")
    try:
        concentration_date = datetime.strptime(effective, "%Y-%m-%d")
    except Exception:
        concentration_date = effective_date

    changes = [
        item
        for item in [
            _concentration_weight_change_proxy(top10, concentration_date, 21),
            _concentration_weight_change_proxy(top10, concentration_date, 63),
        ]
        if item is not None
    ]
    value = {
        "effective_date": effective,
        "total_holdings": total_holdings,
        "top10_weight_pct": round(top10_weight, 2),
        "top5_weight_pct": round(top5_weight, 2),
        "top3_weight_pct": round(top3_weight, 2),
        "largest_weight_pct": top10[0]["weight_pct"] if top10 else None,
        "m7_weight_pct": round(m7_weight, 2),
        "equal_weight_top10_baseline_pct": round(equal_weight_top10, 2) if equal_weight_top10 is not None else None,
        "top10_excess_vs_equal_weight_pct_points": round(top10_weight - equal_weight_top10, 2) if equal_weight_top10 is not None else None,
        "top10_holdings": top10,
        "concentration_change_proxy": changes,
        "market_cap_vs_equal_weight": _qqq_equal_weight_performance_spread(concentration_date),
        "source_boundary": "Official current QQQ holdings from Invesco; historical concentration change is a price-return proxy, not official historical holdings.",
    }
    return {
        "name": "QQQ Top10 Concentration",
        "series_id": "INVESCO_QQQ_HOLDINGS",
        "value": value,
        "unit": "percent",
        "date": effective,
        "source_name": "Invesco QQQ official holdings API" + (" (local snapshot fallback)" if used_cached_snapshot else ""),
        "source_url": INVESCO_QQQ_HOLDINGS_PAGE,
        "source_tier": "official_provider_cached" if used_cached_snapshot else "official_provider",
        "data_quality": {
            "source_tier": "official_provider_cached" if used_cached_snapshot else "official_provider",
            "data_date": effective,
            "collected_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "update_frequency": "daily/monthly as published by Invesco endpoint",
            "formula": "Top-N concentration = sum of Invesco percentageOfTotalNetAssets; NDX vs NDXE spread from daily close total returns.",
            "coverage": {"holdings_reported": len(holdings), "total_holdings": total_holdings},
            "anomalies": (
                (["invesco_live_unavailable_used_cached_snapshot"] if used_cached_snapshot else [])
                + ([] if len(top10) == 10 else ["fewer_than_10_holdings_parsed"])
            ),
            "fallback_chain": ["official_provider/Invesco", "local_official_snapshot", "proxy/yfinance", "unavailable"],
            "snapshot_cached_at_utc": (snapshot_meta or {}).get("cached_at_utc") if used_cached_snapshot else None,
        },
        "notes": (
            "官方 QQQ 持仓用于头部权重锚；NDX/NDXE 表现差异只作为市值加权相对等权 Nasdaq-100 的价格代理。"
            + (f" 本次 Invesco live 抓取失败，使用本地官方快照兜底：{error}" if used_cached_snapshot else "")
        ),
    }

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


def _summarize_m7_fundamentals(m7_data: Dict[str, Any]) -> Dict[str, Any]:
    valid_items = {
        ticker: value
        for ticker, value in m7_data.items()
        if isinstance(value, dict) and not value.get("error") and value.get("MarketCap")
    }
    total_market_cap = sum(float(value.get("MarketCap", 0)) for value in valid_items.values())
    summary: Dict[str, Any] = {
        "count": len(valid_items),
        "total_market_cap": round(total_market_cap, 2) if total_market_cap else None,
        "top_weight_ticker": None,
        "top_weight_pct": None,
        "market_cap_weighted_PE": None,
        "market_cap_weighted_ROE": None,
        "weighted_quantitative_moat": None,
        "contribution_note": "Weighted contribution view; simple average PE is intentionally not emphasized.",
    }
    if total_market_cap <= 0:
        return summary

    weights = {
        ticker: float(value.get("MarketCap", 0)) / total_market_cap
        for ticker, value in valid_items.items()
    }
    top_ticker, top_weight = max(weights.items(), key=lambda item: item[1])
    summary["top_weight_ticker"] = top_ticker
    summary["top_weight_pct"] = round(top_weight * 100, 2)

    pe_cap = 0.0
    earnings = 0.0
    roe_weighted = 0.0
    roe_weight = 0.0
    moat_weighted = 0.0
    moat_weight = 0.0
    for ticker, value in valid_items.items():
        market_cap = float(value.get("MarketCap", 0))
        pe = value.get("PE")
        if pe and pe > 0:
            pe_cap += market_cap
            earnings += market_cap / float(pe)
        roe = value.get("ROE")
        if roe is not None:
            roe_weighted += float(roe) * market_cap
            roe_weight += market_cap
        moat = value.get("quantitative_moat_score")
        if moat is not None:
            moat_weighted += float(moat) * market_cap
            moat_weight += market_cap

    if pe_cap > 0 and earnings > 0:
        summary["market_cap_weighted_PE"] = round(pe_cap / earnings, 2)
    if roe_weight > 0:
        summary["market_cap_weighted_ROE"] = round(roe_weighted / roe_weight, 2)
    if moat_weight > 0:
        summary["weighted_quantitative_moat"] = round(moat_weighted / moat_weight, 2)
    return summary


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
                def _av_percent_ratio(field: str) -> Optional[float]:
                    raw = data.get(field)
                    if raw in (None, "", "None", "null"):
                        return None
                    value = float(str(raw).strip().rstrip("%"))
                    return value / 100 if abs(value) > 1 else value

                def _ratio_to_pct(value: Optional[float]) -> Optional[float]:
                    return round(value * 100, 2) if value is not None else None

                roe = _av_percent_ratio("ReturnOnEquity")
                gross_margin = _av_percent_ratio("GrossMargin")
                op_margin = _av_percent_ratio("OperatingMargin")
                profit_margin = _av_percent_ratio("ProfitMargin")

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
                    "ROE": _ratio_to_pct(roe),
                    "EPS": float(data.get("EPS")) if data.get("EPS") else None,
                    "MarketCap": int(data.get("MarketCapitalization")) if data.get("MarketCapitalization") else None,
                    "ProfitMargin": _ratio_to_pct(profit_margin),
                    "GrossMargin": _ratio_to_pct(gross_margin),
                    "OperatingMargin": _ratio_to_pct(op_margin),
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

    summary = _summarize_m7_fundamentals(m7_data)

    return {
        "name": "M7 Fundamentals",
        "series_id": "M7_COMPOSITE",
        "value": m7_data,
        "unit": "mixed",
        "date": effective_date.strftime("%Y-%m-%d"),
        "source_name": data_source,
        "source_url": "Mixed: yfinance + Alpha Vantage",
        "notes": f"Successfully fetched {summary['count']}/7 companies. Summary is contribution-weighted; simple average PE is not used as a headline.",
        "summary": summary
    }

# =====================================================
# 第四层：指数基本面与拥挤度（修复版）
# =====================================================
