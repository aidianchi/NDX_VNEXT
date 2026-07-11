# tools_L2.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第2层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

from datetime import timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from .tools_L3 import get_ndx100_components
except ImportError:
    from tools_L3 import get_ndx100_components

_NDX100_PRICE_PANEL_RUN_CACHE: Dict[str, Tuple[List[str], pd.DataFrame]] = {}
NDX100_ARCHIVE_DOWNLOAD_BATCH_SIZE = 20
NDX100_BREADTH_MIN_DAILY_COVERAGE = 0.80
NDX100_ARCHIVE_ROLLING_ROWS = 260


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


# =====================================================
# 第2层函数
# =====================================================

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
    ndx100_components = get_ndx100_components(end_date=historical_date)
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

        return {
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


def get_hy_quality_spread_bp(end_date: str = None) -> Dict[str, Any]:
    """低质高收益债相对高质高收益债的信用压力差。"""
    ccc_series = get_fred_series("BAMLH0A3HYC", end_date=end_date)
    bb_series = get_fred_series("BAMLH0A1HYBB", end_date=end_date)
    if ccc_series is None or bb_series is None or len(ccc_series) < 20 or len(bb_series) < 20:
        return {
            "name": "HY CCC & Lower minus BB OAS",
            "series_id": "BAMLH0A3HYC-BAMLH0A1HYBB",
            "value": None,
            "unit": "basis points",
            "source_name": "FRED / ICE BofA",
            "source_tier": "official_provider",
            "notes": "数据不足，无法计算低质高收益债相对 BB 的信用分层压力。",
        }

    ccc = ccc_series[["date", "value"]].rename(columns={"value": "ccc_oas"})
    bb = bb_series[["date", "value"]].rename(columns={"value": "bb_oas"})
    aligned = pd.merge(ccc, bb, on="date", how="inner").dropna()
    if len(aligned) < 20:
        return {
            "name": "HY CCC & Lower minus BB OAS",
            "series_id": "BAMLH0A3HYC-BAMLH0A1HYBB",
            "value": None,
            "unit": "basis points",
            "source_name": "FRED / ICE BofA",
            "source_tier": "official_provider",
            "notes": "CCC & Lower 和 BB OAS 共同日期不足，无法计算分层利差。",
        }

    spread_series = aligned.copy()
    spread_series["value"] = spread_series["ccc_oas"] - spread_series["bb_oas"]
    analysis = analyze_series_ma_trend(spread_series[["date", "value"]], short_period=5, long_period=20)
    stats = calculate_long_term_stats(spread_series[["date", "value"]], analysis["level"])
    latest = aligned.iloc[-1]
    analysis.update(
        {
            "ccc_oas": round(float(latest["ccc_oas"]), 2),
            "bb_oas": round(float(latest["bb_oas"]), 2),
            "relativity": stats,
        }
    )
    return {
        "name": "HY CCC & Lower minus BB OAS",
        "series_id": "BAMLH0A3HYC-BAMLH0A1HYBB",
        "value": analysis,
        "unit": "basis points",
        "source_name": "FRED / ICE BofA",
        "source_tier": "official_provider",
        "data_quality": {
            "source_tier": "official_provider",
            "data_date": analysis.get("date"),
            "collected_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "update_frequency": "daily market close",
            "formula": "ICE BofA CCC & Lower US High Yield OAS minus ICE BofA BB US High Yield OAS",
            "coverage": {
                "series": ["BAMLH0A3HYC", "BAMLH0A1HYBB"],
                "common_observations": int(len(spread_series)),
            },
            "anomalies": [],
            "fallback_chain": ["FRED / ICE BofA", "unavailable"],
            "source_disagreement": {},
        },
        "notes": (
            "低质高收益债相对 BB 的分层压力。FRED 可得口径是 CCC & Lower，"
            "不是精确 CCC+；应与 HY OAS、IG OAS 和 VIX 联合阅读。"
        ),
    }


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
) -> Dict[str, Any]:
    coverage = {
        "constituents_used": constituents_used,
        "total_constituents": total_constituents,
        "constituent_coverage_pct": round(constituents_used / total_constituents * 100, 2) if total_constituents else 0.0,
    }
    coverage.update(coverage_extra or {})
    return {
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
            ),
            "notes": (
                f"基于{len(ndx100_components)}只成分股、仅保留有效价格对覆盖率至少80%的{len(daily_ad_values)}个交易日。"
                f"最新合格日{latest_date_val}覆盖{latest_valid_count}只({latest_coverage_pct}%)：上涨{latest_advances}只，下跌{latest_declines}只。"
            )
        }
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
            ),
            "notes": (
                f"最新合格日{latest_date_val}使用{total_stocks}/{len(ndx100_components)}只成分股，"
                f"当日可计算覆盖率{latest_coverage_pct:.2f}%；单日缺失不会删除整只股票。"
                f" archive repair={repair.get('status') or 'not_reported'}。"
            )
        }
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
            ),
            "notes": (
                f"52周新高{new_highs}只，新低{new_lows}只；最新合格日{latest_date_val}"
                f"覆盖{total_used}/{len(components)}只({latest_coverage_pct:.2f}%)。"
                f" archive repair={repair.get('status') or 'not_reported'}。"
            )
        }
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
            ),
            "notes": (
                f"基于NDX100成分股每日涨跌家数序列；最新合格日{latest_date_val}"
                f"覆盖{total_used}/{len(components)}只({latest_coverage_pct:.2f}%)。"
                f" archive repair={repair.get('status') or 'not_reported'}。"
            )
        }
    except Exception as e:
        return {
            "name": "McClellan Oscillator",
            "value": {"level": None, "date": None, "momentum": None, "relativity": None},
            "source_tier": "unavailable",
            "availability": "unavailable",
            "unavailable_reason": "insufficient_valid_pair_coverage_or_history",
            "notes": f"Failed to calculate: {str(e)}"
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


def _cnn_safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cnn_fgi_timestamp_to_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        return pd.to_datetime(value, utc=True, errors="coerce").strftime("%Y-%m-%d")
    except Exception:
        return None


def _select_cnn_fgi_historical_point(data: Dict[str, Any], end_date: str) -> Optional[Dict[str, Any]]:
    historical = data.get("fear_and_greed_historical")
    rows = historical.get("data") if isinstance(historical, dict) else None
    if not isinstance(rows, list):
        return None
    effective = pd.to_datetime(end_date, utc=True, errors="coerce")
    if pd.isna(effective):
        return None
    selected: Optional[Dict[str, Any]] = None
    selected_date = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_date_text = row.get("date") or row.get("x") or row.get("timestamp")
        row_date = pd.to_datetime(
            _cnn_fgi_timestamp_to_date(row_date_text) or row_date_text,
            utc=True,
            errors="coerce",
        )
        if pd.isna(row_date) or row_date > effective:
            continue
        if selected_date is None or row_date > selected_date:
            selected = row
            selected_date = row_date
    if selected is not None and selected_date is not None:
        selected = dict(selected)
        selected["_selected_date"] = selected_date.strftime("%Y-%m-%d")
    return selected


def get_cnn_fear_greed_index(end_date: str = None) -> Dict[str, Any]:
    """
    获取CNN恐贪指数 (Fear & Greed Index)

    数据源：CNN Business官方API
    URL：https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{date}

    核心价值：
    - 综合性市场情绪指标，整合7个子指标
    - 极端值是反向情绪观察（<25极度恐惧、>75极度贪婪），必须结合价格、波动率和信用确认
    - 提供历史对比数据（前一日/周/月/年）

    返回结构：
    - score: 恐贪指数得分 (0-100)
    - rating: 情绪评级 (extreme fear/fear/neutral/greed/extreme greed)
    - previous_close/week/month/year: 历史对比
    - sub_metrics: 7个子指标详情

    投资逻辑（第一性原理）：
    - 极端恐惧（<25）：市场过度悲观的候选观察，不能单独推出价格低于内在价值或买入结论
    - 极端贪婪（>75）：市场过度乐观的候选观察，不能单独推出卖出结论
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

        historical_point = _select_cnn_fgi_historical_point(data, end_date) if end_date else None
        if end_date and not historical_point:
            return {
                "name": "CNN Fear & Greed Index",
                "value": None,
                "source_tier": "unavailable",
                "source_name": "CNN Business",
                "notes": "Historical CNN Fear & Greed data unavailable for effective_date; live field was not used in backtest mode.",
                "data_quality": {
                    "data_date": end_date,
                    "anomalies": ["historical_point_missing"],
                    "fallback_chain": ["CNN fear_and_greed_historical.data", "unavailable"],
                },
            }

        fear_greed = historical_point or data.get('fear_and_greed', {})
        if not fear_greed:
            return {
                "name": "CNN Fear & Greed Index",
                "value": None,
                "notes": "No fear and greed data in response"
            }

        score = fear_greed.get('score')
        if score is None:
            score = fear_greed.get("y")
        if score is None:
            score = fear_greed.get("value")
        score = _cnn_safe_float(score)
        rating = fear_greed.get('rating')

        result = {
            "name": "CNN Fear & Greed Index",
            "series_id": "CNN_FGI",
            "value": {
                "score": round(score, 2) if score is not None else None,
                "rating": rating,
                "timestamp": fear_greed.get('timestamp') or fear_greed.get("x"),
                "data_date": fear_greed.get("_selected_date") or _cnn_fgi_timestamp_to_date(fear_greed.get('timestamp') or fear_greed.get("x")),
                "previous_close": fear_greed.get('previous_close'),
                "previous_1_week": fear_greed.get('previous_1_week'),
                "previous_1_month": fear_greed.get('previous_1_month'),
                "previous_1_year": fear_greed.get('previous_1_year'),
            },
            "unit": "index (0-100)",
            "source_name": "CNN Business",
            "notes": "Score range: 0-100. <25=Extreme Fear, >75=Extreme Greed. This is sentiment evidence only and requires confirmation from volatility, credit, price, and valuation."
        }
        if end_date:
            result["data_quality"] = {
                "data_date": result["value"].get("data_date") or end_date,
                "effective_date": end_date,
                "source_path": "fear_and_greed_historical.data",
                "anomalies": [],
            }
        else:
            result["data_quality"] = {
                "data_date": result["value"].get("data_date"),
                "source_path": "fear_and_greed",
                "anomalies": ["live_current_field"],
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

        logging.info(f"CNN FGI: {score:.2f} ({rating})" if score is not None else f"CNN FGI: unavailable ({rating})")
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
