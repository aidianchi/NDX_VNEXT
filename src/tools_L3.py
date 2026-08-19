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
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


# =====================================================
# 第3层函数：指数内部健康度（NDX100 成分股广度，自 tools_L2 迁入）
# =====================================================

_NDX100_PRICE_PANEL_RUN_CACHE: Dict[str, Tuple[List[str], pd.DataFrame]] = {}
NDX100_ARCHIVE_DOWNLOAD_BATCH_SIZE = 20
NDX100_BREADTH_MIN_DAILY_COVERAGE = 0.80
NDX100_ARCHIVE_ROLLING_ROWS = 260


def _attach_recompute_value_series(payload: Dict[str, Any], frame: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """Attach dated audit input for the collector to move outside L1-L5 raw_data."""
    if frame is None or frame.empty or not {"date", "value"}.issubset(frame.columns):
        return payload
    working = frame[["date", "value"]].copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working["value"] = pd.to_numeric(working["value"], errors="coerce")
    working = working.dropna().sort_values("date").tail(3660)
    payload["recompute_input"] = {
        "schema": "dated_value_series_v1",
        "purpose": "audit_only_independent_recomputation",
        "percentile_contract": {
            "scale": "0_1",
            "comparison": "less_than_or_equal",
            "windows": "calendar_year",
        },
        "raw_series": [
            {"date": row.date.strftime("%Y-%m-%d"), "value": float(row.value)}
            for row in working.itertuples(index=False)
        ],
    }
    return payload


def reset_ndx100_price_panel_run_cache() -> None:
    """Clear the shared component panel at the start of each formal collector run."""
    _NDX100_PRICE_PANEL_RUN_CACHE.clear()


def _yf_daily_end_inclusive(effective_date: datetime) -> datetime:
    """yfinance daily end is exclusive; request T+1 then filter back to T."""
    return effective_date + timedelta(days=1)


def _filter_daily_frame_to_effective_date(df: pd.DataFrame, effective_date: datetime) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    filtered = df.copy()
    if not isinstance(filtered.index, pd.DatetimeIndex):
        filtered.index = pd.to_datetime(filtered.index)
    filtered.index = filtered.index.tz_localize(None)
    effective = pd.Timestamp(effective_date).tz_localize(None)
    return filtered[filtered.index <= effective]


def _ndx100_price_archive_dir() -> str:
    path = os.path.join(path_config.cache_dir, "market_archive", "ndx100_component_prices")
    os.makedirs(path, exist_ok=True)
    return path


def _archive_ticker_slug(ticker: str) -> str:
    return str(ticker).upper().replace("/", "_").replace("\\", "_").replace(".", "-")


def _archive_target_date(effective_date: datetime, historical_date: Optional[str]) -> pd.Timestamp:
    requested = pd.Timestamp(effective_date).tz_localize(None).normalize()
    if historical_date:
        return requested
    try:
        completed = _latest_completed_us_daily_date().tz_localize(None).normalize()
        return min(requested, completed)
    except Exception:
        return requested


def _read_ndx100_component_price_archive(
    tickers: Iterable[str],
    start_date: datetime,
    effective_date: datetime,
) -> pd.DataFrame:
    frames: Dict[str, pd.Series] = {}
    start = pd.Timestamp(start_date).tz_localize(None).normalize()
    end = pd.Timestamp(effective_date).tz_localize(None).normalize()
    for ticker in tickers:
        path = os.path.join(_ndx100_price_archive_dir(), f"{_archive_ticker_slug(ticker)}.csv")
        if not os.path.exists(path):
            continue
        try:
            frame = pd.read_csv(path, parse_dates=["date"])
            if frame.empty or "close" not in frame.columns:
                continue
            frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
            frame = frame.dropna(subset=["date", "close"])
            frame = frame[(frame["date"] >= start) & (frame["date"] <= end)]
            if frame.empty:
                continue
            frames[str(ticker).upper()] = frame.set_index("date")["close"].sort_index()
        except Exception as exc:
            logging.warning("Failed reading NDX100 price archive for %s: %s", ticker, exc)
    if not frames:
        return pd.DataFrame()
    close = pd.DataFrame(frames).sort_index()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def _write_ndx100_component_price_archive(frame: pd.DataFrame) -> None:
    close = _extract_component_close_prices(frame)
    if close.empty:
        return
    close = close.copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    for ticker in close.columns:
        series = pd.to_numeric(close[ticker], errors="coerce").dropna()
        if series.empty:
            continue
        path = os.path.join(_ndx100_price_archive_dir(), f"{_archive_ticker_slug(ticker)}.csv")
        new_rows = pd.DataFrame({"date": series.index, "close": series.values})
        try:
            if os.path.exists(path):
                old_rows = pd.read_csv(path, parse_dates=["date"])
                rows = pd.concat([old_rows, new_rows], ignore_index=True)
            else:
                rows = new_rows
            rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
            rows["close"] = pd.to_numeric(rows["close"], errors="coerce")
            rows = rows.dropna(subset=["date", "close"])
            rows = rows.sort_values("date").drop_duplicates("date", keep="last")
            rows.to_csv(path, index=False)
        except Exception as exc:
            logging.warning("Failed writing NDX100 price archive for %s: %s", ticker, exc)


def _archive_close_to_yf_panel(close: pd.DataFrame, repair_meta: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    if close.empty:
        return pd.DataFrame()
    panel = pd.concat({"Close": close.sort_index()}, axis=1)
    panel.attrs["source_name"] = "local NDX100 component price archive"
    panel.attrs["market_data_source"] = "ndx100_component_price_archive"
    panel.attrs["archive_repair"] = dict(repair_meta or {})
    return panel


def _component_archive_coverage_diagnostics(
    close: pd.DataFrame,
    tickers: List[str],
    start_date: datetime,
    target_date: pd.Timestamp,
) -> Dict[str, Any]:
    """Find stale endpoints, sparse dates and ticker holes in the active window."""
    ticker_keys = [str(ticker).upper() for ticker in tickers]
    if close.empty:
        return {
            "repair_tickers": list(tickers),
            "latest_observed_date": None,
            "latest_date_coverage_pct": 0.0,
            "rolling_min_daily_coverage_pct": 0.0,
            "rolling_min_ticker_coverage_pct": 0.0,
            "sparse_dates": [],
        }

    start = pd.Timestamp(start_date).tz_localize(None).normalize()
    target = pd.Timestamp(target_date).tz_localize(None).normalize()
    aligned = close.copy()
    aligned.index = pd.to_datetime(aligned.index).tz_localize(None).normalize()
    aligned.columns = [str(column).upper() for column in aligned.columns]
    aligned = aligned.loc[(aligned.index >= start) & (aligned.index <= target)]
    aligned = aligned.reindex(columns=ticker_keys)
    window = aligned.tail(NDX100_ARCHIVE_ROLLING_ROWS)
    if window.empty:
        return {
            "repair_tickers": list(tickers),
            "latest_observed_date": None,
            "latest_date_coverage_pct": 0.0,
            "rolling_min_daily_coverage_pct": 0.0,
            "rolling_min_ticker_coverage_pct": 0.0,
            "sparse_dates": [],
        }

    repair_keys = {
        str(ticker).upper()
        for ticker in _component_archive_missing_tickers_by_endpoints(aligned, tickers, start, target)
    }
    daily_coverage = window.notna().sum(axis=1) / max(len(ticker_keys), 1)
    latest_date = window.index[-1]
    latest_missing = window.columns[window.loc[latest_date].isna()]
    repair_keys.update(str(ticker).upper() for ticker in latest_missing)

    sparse_rows = daily_coverage[daily_coverage < NDX100_BREADTH_MIN_DAILY_COVERAGE]
    for row_date in sparse_rows.index:
        repair_keys.update(str(ticker).upper() for ticker in window.columns[window.loc[row_date].isna()])

    ticker_coverage = window.notna().sum(axis=0) / max(len(window), 1)
    for ticker in ticker_keys:
        series = window[ticker]
        first = series.first_valid_index()
        last = series.last_valid_index()
        if first is None or last is None:
            repair_keys.add(ticker)
            continue
        bounded = series.loc[first:last]
        if bounded.isna().any():
            repair_keys.add(ticker)

    original_by_upper = {str(ticker).upper(): ticker for ticker in tickers}
    return {
        "repair_tickers": [original_by_upper[key] for key in ticker_keys if key in repair_keys],
        "latest_observed_date": latest_date.strftime("%Y-%m-%d"),
        "latest_date_coverage_pct": round(float(daily_coverage.iloc[-1]) * 100, 2),
        "rolling_min_daily_coverage_pct": round(float(daily_coverage.min()) * 100, 2),
        "rolling_min_ticker_coverage_pct": round(float(ticker_coverage.min()) * 100, 2),
        "sparse_dates": [item.strftime("%Y-%m-%d") for item in sparse_rows.index[-10:]],
    }


def _component_archive_missing_tickers_by_endpoints(
    close: pd.DataFrame,
    tickers: List[str],
    start_date: datetime,
    target_date: pd.Timestamp,
) -> List[str]:
    """Legacy endpoint checks retained as one part of the repair plan."""
    if close.empty:
        return list(tickers)
    start = pd.Timestamp(start_date).tz_localize(None).normalize()
    missing: List[str] = []
    for ticker in tickers:
        key = str(ticker).upper()
        if key not in close.columns:
            missing.append(ticker)
            continue
        series = close[key].dropna()
        if series.empty:
            missing.append(ticker)
            continue
        if series.index.min().normalize() > start + pd.Timedelta(days=10):
            missing.append(ticker)
            continue
        if series.index.max().normalize() < target_date - pd.Timedelta(days=5):
            missing.append(ticker)
    return missing


def _component_archive_missing_tickers(
    close: pd.DataFrame,
    tickers: List[str],
    start_date: datetime,
    target_date: pd.Timestamp,
) -> List[str]:
    return _component_archive_coverage_diagnostics(close, tickers, start_date, target_date)["repair_tickers"]


def _component_price_source_name(frame: pd.DataFrame) -> str:
    source = ""
    if isinstance(frame, pd.DataFrame):
        source = str(frame.attrs.get("source_name") or frame.attrs.get("market_data_source") or "").strip()
    return source or "yfinance"


def _ensure_component_ticker_columns(frame: pd.DataFrame, tickers: List[str]) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty or isinstance(frame.columns, pd.MultiIndex):
        return frame
    if len(tickers) != 1:
        return frame
    ticker = str(tickers[0]).upper()
    return pd.concat({ticker: frame}, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=1)


def _download_ndx100_missing_price_archive(
    tickers: List[str],
    start_date: datetime,
    end_date: datetime,
) -> None:
    if not YF_AVAILABLE or not tickers:
        return
    for offset in range(0, len(tickers), NDX100_ARCHIVE_DOWNLOAD_BATCH_SIZE):
        batch = tickers[offset : offset + NDX100_ARCHIVE_DOWNLOAD_BATCH_SIZE]
        try:
            frame = cached_yf_download(
                batch if len(batch) > 1 else batch[0],
                start=start_date,
                end=end_date,
                interval="1d",
                progress=False,
                auto_adjust=False,
            )
            frame = _ensure_component_ticker_columns(frame, batch)
            frame = _filter_daily_frame_to_effective_date(frame, end_date - timedelta(days=1))
            if not _extract_component_close_prices(frame).empty:
                _write_ndx100_component_price_archive(frame)
        except Exception as exc:
            logging.warning("NDX100 archive batch download failed for %s: %s", ",".join(batch), str(exc)[:160])
            if len(batch) == 1:
                continue
            for ticker in batch:
                try:
                    frame = cached_yf_download(
                        ticker,
                        start=start_date,
                        end=end_date,
                        interval="1d",
                        progress=False,
                        auto_adjust=False,
                    )
                    frame = _ensure_component_ticker_columns(frame, [ticker])
                    frame = _filter_daily_frame_to_effective_date(frame, end_date - timedelta(days=1))
                    if not _extract_component_close_prices(frame).empty:
                        _write_ndx100_component_price_archive(frame)
                except Exception as ticker_exc:
                    logging.warning("NDX100 archive ticker download failed for %s: %s", ticker, str(ticker_exc)[:160])


def _get_ndx100_common_price_data(
    effective_date: datetime,
    lookback_days: int = 300,
    historical_date: Optional[str] = None,
) -> Tuple[List[str], pd.DataFrame]:
    """
    鍏变韩 NDX100 鎴愬垎鑲℃壒閲忚鎯呫€?
    鐩爣鏄 L2 鐨?breadth 鎸囨爣鍏变韩涓€娆′笅杞斤紝
    浣嗗悇鑷殑璁＄畻绐楀彛浠嶇劧鎸夊師鐗堥€昏緫鍒囩墖锛屼笉鏀瑰彉杈撳嚭鍙ｅ緞銆?
    """
    ndx100_components, universe_provenance = get_ndx100_components_with_provenance(end_date=historical_date)
    common_start = effective_date - timedelta(days=lookback_days)
    target_date = _archive_target_date(effective_date, historical_date)
    cache_key = ":".join(
        [
            target_date.strftime("%Y-%m-%d"),
            str(lookback_days),
            historical_date or "live",
            ",".join(sorted(str(ticker).upper() for ticker in ndx100_components)),
        ]
    )
    if cache_key in _NDX100_PRICE_PANEL_RUN_CACHE:
        cached_components, cached_data = _NDX100_PRICE_PANEL_RUN_CACHE[cache_key]
        return list(cached_components), cached_data.copy()

    archived_close = _read_ndx100_component_price_archive(ndx100_components, common_start, target_date)
    before_repair = _component_archive_coverage_diagnostics(
        archived_close, ndx100_components, common_start, target_date
    )
    missing_tickers = before_repair["repair_tickers"]

    if missing_tickers:
        _download_ndx100_missing_price_archive(
            missing_tickers,
            common_start,
            _yf_daily_end_inclusive(effective_date),
        )
        archived_close = _read_ndx100_component_price_archive(ndx100_components, common_start, target_date)

    after_repair = _component_archive_coverage_diagnostics(
        archived_close, ndx100_components, common_start, target_date
    )
    repair_meta = {
        **after_repair,
        "triggered": bool(missing_tickers),
        "requested_tickers": [str(ticker).upper() for ticker in missing_tickers],
        "remaining_tickers": [str(ticker).upper() for ticker in after_repair["repair_tickers"]],
        "status": (
            "not_needed"
            if not missing_tickers
            else "completed"
            if not after_repair["repair_tickers"]
            else "incomplete"
        ),
        "before_latest_date_coverage_pct": before_repair["latest_date_coverage_pct"],
    }

    if not archived_close.empty:
        result = _archive_close_to_yf_panel(archived_close, repair_meta)
    else:
        result = pd.DataFrame()
    result = _filter_daily_frame_to_effective_date(result, effective_date)
    result.attrs["universe_provenance"] = dict(universe_provenance)
    _NDX100_PRICE_PANEL_RUN_CACHE[cache_key] = (list(ndx100_components), result.copy())
    return ndx100_components, result


def _cap_weight_equal_weight_ratio_from_yfinance(
    *,
    end_date: Optional[str],
    numerator_ticker: str,
    denominator_ticker: str,
    numerator_label: str,
    denominator_label: str,
    metric_name: str,
    series_id: str,
) -> Dict[str, Any]:
    """Calculate cap-weighted vs equal-weight relative strength from daily closes."""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    if not YF_AVAILABLE:
        return {
            "name": metric_name,
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "notes": "yfinance unavailable",
        }

    try:
        start_date = effective_date - timedelta(days=365 * 11)

        numerator = cached_yf_download(
            numerator_ticker,
            start=start_date,
            end=_yf_daily_end_inclusive(effective_date),
            progress=False,
            auto_adjust=False,
        )
        denominator = cached_yf_download(
            denominator_ticker,
            start=start_date,
            end=_yf_daily_end_inclusive(effective_date),
            progress=False,
            auto_adjust=False,
        )

        numerator = _filter_daily_frame_to_effective_date(clean_yfinance_dataframe(numerator), effective_date)
        denominator = _filter_daily_frame_to_effective_date(clean_yfinance_dataframe(denominator), effective_date)

        if numerator.empty or denominator.empty or "close" not in numerator.columns or "close" not in denominator.columns:
            return {"name": metric_name, "value": None, "notes": f"{numerator_label}/{denominator_label} close series unavailable"}

        df = pd.concat(
            [numerator["close"].rename("numerator"), denominator["close"].rename("denominator")],
            axis=1,
        ).dropna()
        df = df[(df["numerator"] > 0) & (df["denominator"] > 0)]
        if len(df) < 3:
            return {"name": metric_name, "value": None, "notes": f"Insufficient common {numerator_label}/{denominator_label} history"}

        ratio_series = df["numerator"] / df["denominator"]
        latest_ratio = float(ratio_series.iloc[-1])
        latest_numerator = float(df["numerator"].iloc[-1])
        latest_denominator = float(df["denominator"].iloc[-1])
        ratio_df = pd.DataFrame({"date": ratio_series.index, "value": ratio_series.values})
        latest_date_val = ratio_series.index[-1].strftime("%Y-%m-%d")
        value_out = {
            "level": round(latest_ratio, 4),
            "date": latest_date_val,
            "relativity": calculate_long_term_stats(ratio_df, latest_ratio, as_of_date=latest_date_val),
            "numerator": numerator_label,
            "denominator": denominator_label,
            "numerator_close": round(latest_numerator, 2),
            "denominator_close": round(latest_denominator, 2),
        }
        if len(ratio_series) >= 20:
            ratio_ma20 = float(ratio_series.rolling(20, min_periods=20).mean().iloc[-1])
            value_out["ratio_trend_vs_ma20"] = "above" if latest_ratio > ratio_ma20 else "below"
            value_out["ratio_ma20"] = round(ratio_ma20, 4)
        if len(df) >= 60:
            numerator_ma60 = float(df["numerator"].rolling(60, min_periods=60).mean().iloc[-1])
            value_out["cap_weight_price_vs_ma60"] = "above" if latest_numerator > numerator_ma60 else "below"
            value_out["cap_weight_ma60"] = round(numerator_ma60, 2)

        payload = {
            "name": metric_name,
            "series_id": series_id,
            "value": value_out,
            "unit": "ratio",
            "source_name": "yfinance/Yahoo daily close",
            "source_tier": "market_data_provider",
            "data_quality": {
                "source_tier": "market_data_provider",
                "data_date": latest_date_val,
                "formula": f"{numerator_ticker} close / {denominator_ticker} close",
                "coverage": {
                    "common_observations": int(len(ratio_series)),
                    "first_common_date": ratio_series.index[0].strftime("%Y-%m-%d"),
                    "latest_common_date": latest_date_val,
                },
                "fallback_chain": ["yfinance/Yahoo", "unavailable"],
                "anomalies": [],
            },
            "notes": (
                f"{numerator_label}/{denominator_label}；分层降噪：比值趋势(MA20)+市值加权指数价格趋势(MA60)。"
                f"{numerator_label}={latest_numerator:.2f}, {denominator_label}={latest_denominator:.2f}。"
                "该比值只说明市值加权相对等权的结构强弱，不能证明估值便宜或宏观宽松。"
            ),
        }
        return _attach_recompute_value_series(payload, ratio_df)
    except Exception as e:
        return {"name": metric_name, "value": None, "notes": f"Error: {str(e)}"}


def get_ndx_ndxe_ratio(end_date: str = None) -> Dict[str, Any]:
    """获取 NDX/NDXE 比率及历史分位，用于观察市值加权相对等权 Nasdaq-100 的集中度。"""
    return _cap_weight_equal_weight_ratio_from_yfinance(
        end_date=end_date,
        numerator_ticker="^NDX",
        denominator_ticker="^NDXE",
        numerator_label="NDX",
        denominator_label="NDXE",
        metric_name="NDX/NDXE Ratio",
        series_id="NDX_NDXE_RATIO",
    )


def get_qqq_qqew_ratio(end_date: str = None) -> Dict[str, Any]:
    """Deprecated compatibility alias: the main L3 ratio now uses NDX/NDXE."""
    result = get_ndx_ndxe_ratio(end_date=end_date)
    if isinstance(result, dict):
        result["legacy_function_id"] = "get_qqq_qqew_ratio"
        result["replacement_function_id"] = "get_ndx_ndxe_ratio"
    return result


def _extract_component_close_prices(data: pd.DataFrame) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        for field in ("Close", "close"):
            if field in data.columns.get_level_values(0):
                close = data[field]
                return close.dropna(axis=1, how="all")
    for field in ("Close", "close"):
        if field in data.columns:
            close = data[field]
            if isinstance(close, pd.Series):
                return close.to_frame()
            return close.dropna(axis=1, how="all")
    return pd.DataFrame()


def _component_coverage_anomalies(components: List[str], used_columns: Iterable[Any]) -> List[str]:
    used = {str(column).upper() for column in used_columns}
    excluded = [str(component).upper() for component in components if str(component).upper() not in used]
    if not excluded:
        return []
    preview = ", ".join(excluded[:10])
    suffix = "" if len(excluded) <= 10 else f", +{len(excluded) - 10} more"
    return [f"excluded_constituents_due_to_missing_or_incomplete_price_data: {preview}{suffix}"]


def _rolling_by_observation(close: pd.DataFrame, window: int, operation: str) -> pd.DataFrame:
    """Roll over each ticker's available observations instead of requiring a hole-free panel."""
    result = pd.DataFrame(index=close.index, columns=close.columns, dtype=float)
    for ticker in close.columns:
        series = pd.to_numeric(close[ticker], errors="coerce").dropna()
        if operation == "mean":
            rolled = series.rolling(window=window, min_periods=window).mean()
        elif operation == "max":
            rolled = series.rolling(window=window, min_periods=window).max()
        elif operation == "min":
            rolled = series.rolling(window=window, min_periods=window).min()
        else:
            raise ValueError(f"Unsupported rolling operation: {operation}")
        result.loc[rolled.index, ticker] = rolled
    return result


def _archive_repair_metadata(frame: pd.DataFrame) -> Dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        return {}
    metadata = frame.attrs.get("archive_repair")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _ndx100_universe_provenance(frame: pd.DataFrame) -> Dict[str, Any]:
    """Read the get_ndx100_components_with_provenance() result stashed on the
    price panel by _get_ndx100_common_price_data, if present."""
    if not isinstance(frame, pd.DataFrame):
        return {}
    metadata = frame.attrs.get("universe_provenance")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _breadth_sparse_anomalies(
    data: pd.DataFrame,
    close_prices: pd.DataFrame,
    qualified: pd.Series,
    latest_qualified_index: pd.Timestamp,
) -> List[str]:
    anomalies: List[str] = []
    excluded = [index for index in close_prices.index if not bool(qualified.get(index, False))]
    if excluded:
        anomalies.append(
            f"excluded_sparse_or_insufficient_history_dates: count={len(excluded)}, latest={excluded[-1].strftime('%Y-%m-%d')}"
        )
    if len(close_prices.index) and close_prices.index[-1] != latest_qualified_index:
        anomalies.append(
            f"latest_raw_row_excluded_for_sparse_coverage: {close_prices.index[-1].strftime('%Y-%m-%d')}"
        )
    repair = _archive_repair_metadata(data)
    if repair.get("triggered"):
        anomalies.append(
            "archive_repair_triggered: "
            f"status={repair.get('status')}, requested={len(repair.get('requested_tickers') or [])}, "
            f"remaining={len(repair.get('remaining_tickers') or [])}"
        )
    return anomalies


def _breadth_coverage_extra(
    data: pd.DataFrame,
    *,
    latest_daily_coverage_pct: float,
    excluded_dates_count: int,
) -> Dict[str, Any]:
    repair = _archive_repair_metadata(data)
    return {
        "latest_daily_coverage_pct": round(float(latest_daily_coverage_pct), 2),
        "minimum_daily_coverage_pct": round(NDX100_BREADTH_MIN_DAILY_COVERAGE * 100, 2),
        "excluded_sparse_or_insufficient_history_dates": int(excluded_dates_count),
        "archive_repair_triggered": bool(repair.get("triggered")),
        "archive_repair_status": repair.get("status") or "not_reported",
        "archive_repair_requested_tickers": len(repair.get("requested_tickers") or []),
        "archive_repair_remaining_tickers": len(repair.get("remaining_tickers") or []),
    }


def _breadth_quality(
    *,
    data_date: str,
    formula: str,
    constituents_used: int,
    total_constituents: int,
    anomalies: Optional[List[str]] = None,
    coverage_extra: Optional[Dict[str, Any]] = None,
    universe_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    coverage = {
        "constituents_used": constituents_used,
        "total_constituents": total_constituents,
        "constituent_coverage_pct": round(constituents_used / total_constituents * 100, 2) if total_constituents else 0.0,
    }
    coverage.update(coverage_extra or {})
    quality = {
        "source_tier": "component_model",
        "data_date": data_date,
        "collected_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "update_frequency": "daily market close",
        "formula": formula,
        "coverage": coverage,
        "anomalies": anomalies or [],
        "fallback_chain": ["component_model", "proxy", "unavailable"],
        "source_disagreement": {},
    }
    if universe_provenance:
        quality["universe_provenance"] = dict(universe_provenance)
    return quality


def _breadth_historical_universe_unavailable_payload(
    name: str, exc: HistoricalUniverseUnavailable
) -> Dict[str, Any]:
    """Honest unavailable payload for backtest requests where the historical
    NDX100 universe could not be resolved. Must never be paired with a value
    computed against the current constituent list."""
    return {
        "name": name,
        "value": {"level": None, "date": None, "momentum": None, "relativity": None},
        "source_tier": "unavailable",
        "availability": "unavailable",
        "unavailable_reason": "historical_universe_unavailable",
        "data_quality": {
            "fallback_reason": "historical_universe_unavailable",
            "anomalies": ["historical_universe_unavailable", "current_universe_not_used"],
        },
        "notes": (
            f"Historical NDX100 universe unavailable for {exc.end_date}: {exc.reason}. "
            "Current-universe sources (Nasdaq API/Wikipedia/GitHub live/static fallback) "
            "were deliberately not used to avoid injecting survivorship bias into this backtest."
        ),
    }


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
        ndx100_components, data = _get_ndx100_common_price_data(effective_date, historical_date=end_date)

        # 下载126天+20天缓冲的数据（确保有足够交易日）
        lookback_days = 126
        start_date = effective_date - timedelta(days=lookback_days + 40)


        if data.empty or len(data) < 2:
            raise ValueError("Insufficient data returned from yfinance.")

        # 提取收盘价数据
        close_prices = _extract_component_close_prices(data)
        close_prices = close_prices[close_prices.index >= start_date]

        # 确保至少有2天数据
        if len(close_prices) < 2:
            raise ValueError(f"Insufficient trading days: {len(close_prices)}")

        # A/D 只能在同一股票连续两个交易日都有价格时计算。外连接数据的
        # 最新一行常只有少数股票更新；把 NaN 当作“不涨不跌”会制造假广度。
        minimum_daily_coverage = 0.80
        changes = close_prices.diff()
        valid_pairs = close_prices.notna() & close_prices.shift(1).notna()
        valid_counts = valid_pairs.sum(axis=1)
        # Columns that are entirely empty were already removed and are reported
        # separately as universe coverage loss. The daily floor is measured
        # against the actually observable panel, so one permanently missing
        # constituent does not invalidate every day.
        observable_constituents = max(len(close_prices.columns), 1)
        daily_coverage = valid_counts / observable_constituents
        qualified = daily_coverage >= minimum_daily_coverage
        daily_net = ((changes > 0) & valid_pairs).sum(axis=1) - ((changes < 0) & valid_pairs).sum(axis=1)
        daily_net = daily_net[qualified]
        if daily_net.empty:
            raise ValueError("No A/D observations meet the 80% valid-pair coverage floor.")
        daily_ad_values = daily_net.astype(int).tolist()

        # 累积求和形成腾落线
        cumulative_ad_line = np.cumsum(daily_ad_values)

        # 获取最新值
        current_level = int(cumulative_ad_line[-1])
        latest_qualified_index = daily_net.index[-1]
        latest_date_val = latest_qualified_index.strftime("%Y-%m-%d")

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
        latest_change = changes.loc[latest_qualified_index]
        latest_valid = valid_pairs.loc[latest_qualified_index]
        latest_advances = int(((latest_change > 0) & latest_valid).sum())
        latest_declines = int(((latest_change < 0) & latest_valid).sum())
        latest_valid_count = int(valid_counts.loc[latest_qualified_index])
        latest_coverage_pct = round(float(daily_coverage.loc[latest_qualified_index]) * 100, 2)

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
            "source_tier": "component_model",
            "source_name": _component_price_source_name(data),
            "availability": "available",
            "data_quality": _breadth_quality(
                data_date=latest_date_val,
                formula="daily advancing constituents - declining constituents among valid consecutive-price pairs; days below 80% coverage are excluded, cumulatively summed",
                constituents_used=latest_valid_count,
                total_constituents=len(ndx100_components),
                anomalies=(
                    _component_coverage_anomalies(ndx100_components, close_prices.columns)
                    + _breadth_sparse_anomalies(data, close_prices, qualified, latest_qualified_index)
                ),
                coverage_extra=_breadth_coverage_extra(
                    data,
                    latest_daily_coverage_pct=latest_coverage_pct,
                    excluded_dates_count=int((~qualified).sum()),
                ),
                universe_provenance=_ndx100_universe_provenance(data),
            ),
            "notes": (
                f"基于{len(ndx100_components)}只成分股、仅保留有效价格对覆盖率至少80%的{len(daily_ad_values)}个交易日。"
                f"最新合格日{latest_date_val}覆盖{latest_valid_count}只({latest_coverage_pct}%)：上涨{latest_advances}只，下跌{latest_declines}只。"
            )
        }
    except HistoricalUniverseUnavailable as e:
        return _breadth_historical_universe_unavailable_payload("Advance/Decline Line (NDX100)", e)
    except Exception as e:
        return {
            "name": "Advance/Decline Line (NDX100)",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "availability": "unavailable",
            "unavailable_reason": "insufficient_valid_pair_coverage",
            "notes": f"Failed to calculate: {str(e)}"
        }


def get_percent_above_ma(end_date: str = None) -> Dict[str, Any]:
    """计算NDX100成分股中价格高于50日和200日均线的股票百分比"""
    if not YF_AVAILABLE:
        return {
            "name": "% Stocks Above MA (NDX100)",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "source_tier": "unavailable",
            "availability": "unavailable",
            "unavailable_reason": "yfinance_not_available",
            "notes": "yfinance not available, cannot fetch component data."
        }

    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    try:
        # **修改点**: 调用新的动态函数获取成分股
        ndx100_components, data = _get_ndx100_common_price_data(effective_date, historical_date=end_date)

        start_date = effective_date - timedelta(days=300) # 确保有足够数据计算200日均线

        # 批量下载过去约一年的日频数据
        if data.empty:
            raise ValueError("No data returned from yfinance.")

        close_prices = _extract_component_close_prices(data).sort_index()
        if close_prices.empty:
            raise ValueError("No observable component close columns.")

        ma50_panel = _rolling_by_observation(close_prices, 50, "mean")
        ma200_panel = _rolling_by_observation(close_prices, 200, "mean")
        eligible = close_prices.notna() & ma50_panel.notna() & ma200_panel.notna()
        valid_counts = eligible.sum(axis=1)
        observable_constituents = max(len(close_prices.columns), 1)
        daily_coverage = valid_counts / observable_constituents
        qualified = daily_coverage >= NDX100_BREADTH_MIN_DAILY_COVERAGE
        if not qualified.any():
            raise ValueError("No MA observation meets the 80% daily coverage and 200-observation floor.")

        latest_qualified_index = qualified[qualified].index[-1]
        latest_eligible = eligible.loc[latest_qualified_index]
        latest_prices = close_prices.loc[latest_qualified_index, latest_eligible]
        ma50 = ma50_panel.loc[latest_qualified_index, latest_eligible]
        ma200 = ma200_panel.loc[latest_qualified_index, latest_eligible]
        above_50d = int((latest_prices > ma50).sum())
        above_200d = int((latest_prices > ma200).sum())
        total_stocks = int(latest_eligible.sum())
        percent_above_50d = round((above_50d / total_stocks) * 100, 2)
        percent_above_200d = round((above_200d / total_stocks) * 100, 2)

        # 获取最新日期
        latest_date_val = latest_qualified_index.strftime("%Y-%m-%d")
        latest_coverage_pct = float(daily_coverage.loc[latest_qualified_index]) * 100
        repair = _archive_repair_metadata(data)
        anomalies = (
            _component_coverage_anomalies(ndx100_components, close_prices.columns)
            + _breadth_sparse_anomalies(data, close_prices, qualified, latest_qualified_index)
        )

        return {
            "name": "% Stocks Above MA (NDX100)",
            "value": {
                "level": {
                    "percent_above_50d": percent_above_50d,
                    "percent_above_200d": percent_above_200d
                },
                "date": latest_date_val,
                "coverage": {
                    "constituents_used": total_stocks,
                    "total_constituents": len(ndx100_components),
                    "constituent_coverage_pct": round(total_stocks / len(ndx100_components) * 100, 2) if ndx100_components else 0.0,
                },
            },
            "unit": "percent",
            "source_tier": "component_model",
            "source_name": _component_price_source_name(data),
            "availability": "available",
            "data_quality": _breadth_quality(
                data_date=latest_date_val,
                formula="latest qualified component close above 50- and 200-observation moving averages; dates below 80% eligible coverage are excluded",
                constituents_used=total_stocks,
                total_constituents=len(ndx100_components),
                anomalies=anomalies,
                coverage_extra=_breadth_coverage_extra(
                    data,
                    latest_daily_coverage_pct=latest_coverage_pct,
                    excluded_dates_count=int((~qualified).sum()),
                ),
                universe_provenance=_ndx100_universe_provenance(data),
            ),
            "notes": (
                f"最新合格日{latest_date_val}使用{total_stocks}/{len(ndx100_components)}只成分股，"
                f"当日可计算覆盖率{latest_coverage_pct:.2f}%；单日缺失不会删除整只股票。"
                f" archive repair={repair.get('status') or 'not_reported'}。"
            )
        }
    except HistoricalUniverseUnavailable as e:
        return _breadth_historical_universe_unavailable_payload("% Stocks Above MA (NDX100)", e)
    except Exception as e:
        return {
            "name": "% Stocks Above MA (NDX100)",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "source_tier": "unavailable",
            "availability": "unavailable",
            "unavailable_reason": "insufficient_component_price_coverage_or_history",
            "notes": f"Failed to calculate: {str(e)}"
        }


def get_new_highs_lows(end_date: str = None) -> Dict[str, Any]:
    """计算NDX100成分股52周新高/新低家数。"""
    if not YF_AVAILABLE:
        return {
            "name": "New Highs-Lows Index",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "source_tier": "unavailable",
            "availability": "unavailable",
            "unavailable_reason": "yfinance_not_available",
            "notes": "yfinance not available, cannot fetch component data."
        }

    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    try:
        try:
            components, data = _get_ndx100_common_price_data(effective_date, lookback_days=420, historical_date=end_date)
        except TypeError:
            components, data = _get_ndx100_common_price_data(effective_date, historical_date=end_date)
        close_prices = _extract_component_close_prices(data).sort_index()
        if close_prices.empty:
            raise ValueError("No observable component close columns.")
        rolling_high = _rolling_by_observation(close_prices, 252, "max")
        rolling_low = _rolling_by_observation(close_prices, 252, "min")
        eligible = close_prices.notna() & rolling_high.notna() & rolling_low.notna()
        valid_counts = eligible.sum(axis=1)
        observable_constituents = max(len(close_prices.columns), 1)
        daily_coverage = valid_counts / observable_constituents
        qualified = daily_coverage >= NDX100_BREADTH_MIN_DAILY_COVERAGE
        if not qualified.any():
            raise ValueError(
                f"Insufficient data for 52-week high/low calculation (max_eligible={int(valid_counts.max())})."
            )

        latest_qualified_index = qualified[qualified].index[-1]
        latest_eligible = eligible.loc[latest_qualified_index]
        latest = close_prices.loc[latest_qualified_index, latest_eligible]
        highs = rolling_high.loc[latest_qualified_index, latest_eligible]
        lows = rolling_low.loc[latest_qualified_index, latest_eligible]
        new_highs = int((latest >= highs).sum())
        new_lows = int((latest <= lows).sum())
        total_used = int(latest_eligible.sum())
        latest_date_val = latest_qualified_index.strftime("%Y-%m-%d")
        latest_coverage_pct = float(daily_coverage.loc[latest_qualified_index]) * 100
        repair = _archive_repair_metadata(data)
        level = {
            "new_highs_52w": new_highs,
            "new_lows_52w": new_lows,
            "net_new_highs": new_highs - new_lows,
            "percent_new_highs": round(new_highs / total_used * 100, 2) if total_used else 0.0,
            "percent_new_lows": round(new_lows / total_used * 100, 2) if total_used else 0.0,
        }
        coverage = {
            "constituents_used": total_used,
            "total_constituents": len(components),
            "constituent_coverage_pct": round(total_used / len(components) * 100, 2) if components else 0.0,
        }
        return {
            "name": "New Highs-Lows Index",
            "series_id": "NDX_COMPONENT_NEW_HIGHS_LOWS",
            "value": {
                "level": level,
                "date": latest_date_val,
                "coverage": coverage,
                "momentum": "positive" if new_highs > new_lows else "negative" if new_lows > new_highs else "neutral",
                "relativity": None,
            },
            "unit": "count/percent",
            "source_tier": "component_model",
            "source_name": _component_price_source_name(data),
            "availability": "available",
            "data_quality": _breadth_quality(
                data_date=latest_date_val,
                formula="component latest qualified close equals its trailing 252 available-observation high or low; dates below 80% eligible coverage are excluded",
                constituents_used=total_used,
                total_constituents=len(components),
                anomalies=(
                    _component_coverage_anomalies(components, close_prices.columns)
                    + _breadth_sparse_anomalies(data, close_prices, qualified, latest_qualified_index)
                ),
                coverage_extra=_breadth_coverage_extra(
                    data,
                    latest_daily_coverage_pct=latest_coverage_pct,
                    excluded_dates_count=int((~qualified).sum()),
                ),
                universe_provenance=_ndx100_universe_provenance(data),
            ),
            "notes": (
                f"52周新高{new_highs}只，新低{new_lows}只；最新合格日{latest_date_val}"
                f"覆盖{total_used}/{len(components)}只({latest_coverage_pct:.2f}%)。"
                f" archive repair={repair.get('status') or 'not_reported'}。"
            )
        }
    except HistoricalUniverseUnavailable as e:
        return _breadth_historical_universe_unavailable_payload("New Highs-Lows Index", e)
    except Exception as e:
        return {
            "name": "New Highs-Lows Index",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "source_tier": "unavailable",
            "availability": "unavailable",
            "unavailable_reason": "insufficient_component_price_coverage_or_history",
            "notes": f"Failed to calculate: {str(e)}"
        }


def get_mcclellan_oscillator_nasdaq_or_nyse(end_date: str = None) -> Dict[str, Any]:
    """用NDX100成分股涨跌家数序列计算McClellan Oscillator。"""
    if not YF_AVAILABLE:
        return {
            "name": "McClellan Oscillator",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "source_tier": "unavailable",
            "availability": "unavailable",
            "unavailable_reason": "yfinance_not_available",
            "notes": "yfinance not available, cannot fetch component data."
        }

    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    try:
        components, data = _get_ndx100_common_price_data(effective_date, historical_date=end_date)
        close_prices = _extract_component_close_prices(data).sort_index()
        if close_prices.empty or len(close_prices) < 40:
            raise ValueError(f"Insufficient data for McClellan calculation (days={len(close_prices)}).")

        price_changes = close_prices.diff()
        valid_pairs = close_prices.notna() & close_prices.shift(1).notna()
        valid_counts = valid_pairs.sum(axis=1)
        observable_constituents = max(len(close_prices.columns), 1)
        daily_coverage = valid_counts / observable_constituents
        qualified = daily_coverage >= NDX100_BREADTH_MIN_DAILY_COVERAGE
        net_advances = (
            ((price_changes > 0) & valid_pairs).sum(axis=1)
            - ((price_changes < 0) & valid_pairs).sum(axis=1)
        )
        net_advances = net_advances[qualified]
        if len(net_advances) < 39:
            raise ValueError(
                f"Insufficient qualified daily breadth observations for McClellan (days={len(net_advances)})."
            )
        ema19 = net_advances.ewm(span=19, adjust=False).mean()
        ema39 = net_advances.ewm(span=39, adjust=False).mean()
        oscillator = ema19 - ema39
        latest_value = float(oscillator.iloc[-1])
        latest_qualified_index = oscillator.index[-1]
        latest_date_val = latest_qualified_index.strftime("%Y-%m-%d")
        total_used = int(valid_counts.loc[latest_qualified_index])
        latest_coverage_pct = float(daily_coverage.loc[latest_qualified_index]) * 100
        repair = _archive_repair_metadata(data)
        return {
            "name": "McClellan Oscillator",
            "series_id": "NDX_COMPONENT_MCCLELLAN",
            "value": {
                "level": round(latest_value, 2),
                "date": latest_date_val,
                "momentum": "positive" if latest_value > 0 else "negative" if latest_value < 0 else "neutral",
                "relativity": None,
                "coverage": {
                    "constituents_used": total_used,
                    "total_constituents": len(components),
                    "constituent_coverage_pct": round(total_used / len(components) * 100, 2) if components else 0.0,
                },
            },
            "unit": "net_advancers_ema_spread",
            "source_tier": "component_model",
            "source_name": _component_price_source_name(data),
            "availability": "available",
            "data_quality": _breadth_quality(
                data_date=latest_date_val,
                formula="19-day EMA(net advances) - 39-day EMA(net advances) using only valid consecutive-price pairs and dates with at least 80% coverage",
                constituents_used=total_used,
                total_constituents=len(components),
                anomalies=(
                    _component_coverage_anomalies(components, close_prices.columns)
                    + _breadth_sparse_anomalies(data, close_prices, qualified, latest_qualified_index)
                ),
                coverage_extra=_breadth_coverage_extra(
                    data,
                    latest_daily_coverage_pct=latest_coverage_pct,
                    excluded_dates_count=int((~qualified).sum()),
                ),
                universe_provenance=_ndx100_universe_provenance(data),
            ),
            "notes": (
                f"基于NDX100成分股每日涨跌家数序列；最新合格日{latest_date_val}"
                f"覆盖{total_used}/{len(components)}只({latest_coverage_pct:.2f}%)。"
                f" archive repair={repair.get('status') or 'not_reported'}。"
            )
        }
    except HistoricalUniverseUnavailable as e:
        return _breadth_historical_universe_unavailable_payload("McClellan Oscillator", e)
    except Exception as e:
        return {
            "name": "McClellan Oscillator",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "source_tier": "unavailable",
            "availability": "unavailable",
            "unavailable_reason": "insufficient_valid_pair_coverage_or_history",
            "notes": f"Failed to calculate: {str(e)}"
        }


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
    # C1 修复：官方总数与"实际解析到的持仓数"必须分名分账，不许两个裸数字并存。
    holdings_parsed = len(holdings)
    provider_total = payload.get("totalNumberOfHoldings")
    total_holdings = int(provider_total) if provider_total is not None else holdings_parsed
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
    holdings_lag_days = max((effective_date.date() - concentration_date.date()).days, 0)

    changes = [
        item
        for item in [
            _concentration_weight_change_proxy(top10, concentration_date, 21),
            _concentration_weight_change_proxy(top10, concentration_date, 63),
        ]
        if item is not None
    ]
    holdings_lag_note = (
        f"持仓锚截至 {effective}，晚于运行时点 {holdings_lag_days} 天；"
        "Invesco 官方持仓按发布节奏更新，这段时差内不得把它当成当日持仓。"
    )
    value = {
        "effective_date": effective,
        "holdings_as_of": effective,
        "holdings_lag_days": holdings_lag_days,
        "holdings_lag_note": holdings_lag_note,
        "total_holdings": total_holdings,
        "holdings_parsed": holdings_parsed,
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
            "coverage": {
                "holdings_reported": holdings_parsed,
                "total_holdings": total_holdings,
                "holdings_as_of": effective,
                "holdings_lag_days": holdings_lag_days,
            },
            "anomalies": (
                (["invesco_live_unavailable_used_cached_snapshot"] if used_cached_snapshot else [])
                + ([] if len(top10) == 10 else ["fewer_than_10_holdings_parsed"])
                + (
                    [f"provider_total_holdings({total_holdings}) != parsed_holdings({holdings_parsed})，以 provider 总数为分母、解析数只作覆盖率"]
                    if total_holdings != holdings_parsed else []
                )
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

