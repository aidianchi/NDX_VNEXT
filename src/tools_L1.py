# tools_L1.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第1层数据获取函数
"""

from copy import deepcopy

try:
    from .tools_common import *
    from .tools_common import _fetch_fred_series, _fetch_yf_history
    from .data_evidence import build_data_quality
except ImportError:
    from tools_common import *
    from tools_common import _fetch_fred_series, _fetch_yf_history
    from data_evidence import build_data_quality

# =====================================================
# 第1层函数
# =====================================================


AMOUNT_UNIT_BILLION_USD = "billion_usd"


def _recompute_value_series_input(
    series: pd.DataFrame, *, value_column: str = "value", history_years: int = 10
) -> Dict[str, Any]:
    """Serialize dated observations for the independent recomputation belt.

    The collector moves this audit-only payload to top-level `recompute_inputs`,
    so long series never enter L1-L5 runtime context.
    """
    if series is None or series.empty or value_column not in series.columns:
        return {}
    frame = series.copy()
    if "date" not in frame.columns:
        frame = frame.reset_index()
        date_column = "date" if "date" in frame.columns else frame.columns[0]
        frame = frame.rename(columns={date_column: "date"})
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
    frame = frame.dropna(subset=["date", value_column]).sort_values("date")
    if frame.empty:
        return {}
    anchor = frame["date"].iloc[-1]
    frame = frame[frame["date"] >= anchor - pd.DateOffset(years=history_years)]
    return {
        "schema_version": "dated_value_series_v1",
        "point_in_time_cutoff": anchor.strftime("%Y-%m-%d"),
        "purpose": "independent_recompute_only",
        "raw_series": [
            {"date": row["date"].strftime("%Y-%m-%d"), "value": float(row[value_column])}
            for _, row in frame.iterrows()
        ],
    }


def _attach_recompute_value_series(
    payload: Dict[str, Any], series: pd.DataFrame, *, value_column: str = "value"
) -> Dict[str, Any]:
    value = payload.get("value") if isinstance(payload.get("value"), dict) else {}
    relativity = value.get("relativity") if isinstance(value.get("relativity"), dict) else {}
    legacy_momentum_relativity = "history_years" in relativity
    audit_input = _recompute_value_series_input(
        series,
        value_column=value_column,
        history_years=15 if legacy_momentum_relativity else 10,
    )
    if audit_input:
        audit_input["percentile_contract"] = (
            {
                "scale": "0_100",
                "comparison": "strict_less",
                "one_year_window": "calendar_year",
                "ten_year_window": "all_attached_history_if_at_least_9_5_years",
            }
            if legacy_momentum_relativity
            else {
                "scale": "0_1",
                "comparison": "less_than_or_equal",
                "windows": "calendar_year",
            }
        )
        payload["recompute_input"] = audit_input
    return payload


def _fred_unavailable_payload(
    *,
    name: str,
    series_id: str,
    unit: str,
    minimum_points: int,
    series: Optional[pd.DataFrame] = None,
    calculation: Optional[str] = None,
) -> Dict[str, Any]:
    quality = dict(getattr(series, "attrs", {}).get("data_quality") or get_fred_series_diagnostics(series_id) or {})
    failure_type = quality.get("failure_type") or "insufficient_observations"
    failure_reason = quality.get("failure_reason") or f"FRED returned fewer than {minimum_points} usable observations."
    quality.update(
        {
            "availability": "unavailable",
            "failure_type": failure_type,
            "failure_reason": failure_reason,
            "observations_available": 0 if series is None else len(series),
            "minimum_observations_required": minimum_points,
        }
    )
    if calculation:
        quality["calculation"] = calculation
    return {
        "name": name,
        "series_id": series_id,
        "value": None,
        "unit": unit,
        "source_name": "FRED",
        "notes": f"FRED data unavailable or insufficient: {failure_type} ({failure_reason})",
        "data_quality": quality,
    }


def _read_cached_series_until(series_id: str, end_date: str) -> pd.DataFrame:
    """Read local TimeSeriesManager cache for historical mode without current-day refresh."""
    try:
        effective_date = pd.to_datetime(end_date)
        path = ts_manager._series_path(series_id)
        frame = ts_manager._read_local(path, date_col="date")
        frame = ts_manager._normalize_df(frame)
        if frame.empty or "value" not in frame.columns:
            return pd.DataFrame(columns=["date", "value"])
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame = frame[(frame["date"] <= effective_date)].dropna(subset=["date", "value"])
        return frame.sort_values("date")[["date", "value"]]
    except Exception as exc:
        logging.warning("读取 %s 历史缓存失败: %s", series_id, exc)
        return pd.DataFrame(columns=["date", "value"])


def _get_series_for_effective_date(series_id: str, update_func, end_date: Optional[str]) -> pd.DataFrame:
    """Use historical cache in backtests; only fetch through the requested effective date if cache is missing."""
    if end_date:
        effective_date = pd.to_datetime(end_date)
        cached = _read_cached_series_until(series_id, end_date)
        if not cached.empty:
            latest_date = cached["date"].max()
            if not pd.isna(latest_date) and latest_date >= effective_date - timedelta(days=7):
                return cached
        try:
            return update_func(start_date=None, end_date=end_date)
        except TypeError as exc:
            logging.warning("%s historical fetch does not support end_date safely: %s", series_id, exc)
            return pd.DataFrame(columns=["date", "value"])
    return ts_manager.get_or_update_series(series_id, update_func)


FED_FUNDS_FUTURES_MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
FED_FUNDS_PATH_MONTHS = 13
FED_FUNDS_PATH_MINIMUM_CURVE_MONTHS = 4
FED_FUNDS_PATH_FLAT_BAND_PP = 0.125
FED_FUNDS_PATH_LIQUIDITY_THRESHOLDS = {
    "negligible_below_avg_volume_10d": 5.0,
    "thin_below_avg_volume_10d": 100.0,
}


def _fed_funds_contract_for_month(year: int, month: int) -> str:
    return f"ZQ{FED_FUNDS_FUTURES_MONTH_CODES[month]}{year % 100:02d}.CBT"


def _fed_funds_month_at_offset(anchor: datetime, months_ahead: int) -> tuple:
    absolute_month = anchor.year * 12 + (anchor.month - 1) + months_ahead
    return absolute_month // 12, absolute_month % 12 + 1


def _fed_funds_path_state(slope_pp: Optional[float]) -> str:
    """Classify the implied-rate curve with the canon's ±12.5bp buffer."""
    if slope_pp is None:
        return "unavailable"
    if slope_pp <= -FED_FUNDS_PATH_FLAT_BAND_PP:
        return "easing_priced"
    if slope_pp >= FED_FUNDS_PATH_FLAT_BAND_PP:
        return "tightening_priced"
    return "flat_path"


def _fed_funds_liquidity_tier(avg_volume_10d: Optional[float]) -> str:
    if avg_volume_10d is None or avg_volume_10d < FED_FUNDS_PATH_LIQUIDITY_THRESHOLDS["negligible_below_avg_volume_10d"]:
        return "negligible"
    if avg_volume_10d < FED_FUNDS_PATH_LIQUIDITY_THRESHOLDS["thin_below_avg_volume_10d"]:
        return "thin"
    return "adequate"


def get_fed_funds_rate_path(end_date: str = None) -> Dict[str, Any]:
    """Return a compact Fed funds futures implied-rate path for L1.

    This is the deliberately reduced implementation from
    investigation_reports/20260711_first_principles/WORK_ORDERS.md item 4
    (fed funds 缩水版): 13 monthly ZQ contracts, an implied average-rate
    slope/state, and an EFFR/DFF reference anchor. It does not attempt CME
    FedWatch meeting probabilities or stitched historical percentiles.

    Point-in-time contract: the contract set is generated from the month of
    ``end_date`` and every contract's history is explicitly truncated to
    observations on or before ``end_date``. Futures settlement closes are
    non-revisable market facts and therefore backtest-eligible, but Yahoo's
    relay is marked ``third_party_unofficial`` because it is not verified
    against the official CME settlement file.
    """
    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    effective_date_str = effective_date.strftime("%Y-%m-%d")
    request_start = effective_date - timedelta(days=35)
    request_end = effective_date + timedelta(days=1)
    source_name = "yfinance (Yahoo Finance ZQ monthly futures) + FRED (EFFR/DFF anchor)"
    source_url = "https://finance.yahoo.com/quote/ZQ%3DF/"

    state_thresholds = {
        "easing_priced_at_or_below_slope_pp": -FED_FUNDS_PATH_FLAT_BAND_PP,
        "tightening_priced_at_or_above_slope_pp": FED_FUNDS_PATH_FLAT_BAND_PP,
        "flat_path_abs_slope_below_pp": FED_FUNDS_PATH_FLAT_BAND_PP,
        "note": "斜率绝对值小于0.125个百分点（12.5bp）视为 flat；边界值归入 easing/tightening。",
    }
    liquidity_thresholds = {
        **FED_FUNDS_PATH_LIQUIDITY_THRESHOLDS,
        "negligible_action": "exclude_from_formal_path_and_curve_calculation",
        "thin_action": "retain_with_field_authority_downgrade",
        "far_month_rule": "months_ahead > 6 is always low_liquidity_far_month",
    }

    def _metric_authority() -> Dict[str, Any]:
        # T36：登记表键名对齐 value 的真实顶层字段名（不是概念分组名），否则模型
        # 照实抄真实字段名反而被 evidence_index 白名单判违规（见
        # investigation_reports/20260728_single_source_audit/FINDINGS.md）。
        # path_0_6m/path_7_12m 曾经是两个分组名，但两者描述的是同一个真实顶层数组
        # 字段 "path"（近端 0-6 月 vs 远端 7-12 月只是同一数组内部的置信度差异，
        # 每个元素自带 field_authority 标注），合并成一条登记；
        # slope_12m_and_cuts_priced_bps 曾经是一个分组名覆盖两个真实顶层标量字段
        # slope_12m 和 cuts_priced_bps，拆成两条，usage/reason 原样沿用。
        return {
            "path": {
                "source": "third_party_unofficial",
                "usage": "supporting_only",
                "authority": "mixed_near_and_far_month_liquidity_tiers",
                "reason": (
                    "近端（0-6月）月度结算价可支持市场定价观察；thin 月按单项 field_authority 继续降级，"
                    "不能视为 Fed 承诺。7-12月合约（months_ahead>6）无论当日成交量如何均属远月低置信观察"
                    "（field_authority=low_liquidity_far_month），不能单独支撑方向结论；数组每个元素自带"
                    "field_authority 标注可用于区分近端/远端置信度。"
                ),
                "reference_sources": [],
            },
            "state": {
                "source": "third_party_unofficial",
                "usage": "supporting_only",
                "authority": "supporting",
                "reason": (
                    "easing_priced 不是流动性利多，须与 HY OAS 和增长数据交叉验证；"
                    "tightening_priced 只作贴现率逆风风险确认。"
                ),
                "reference_sources": ["get_hy_oas_bp"],
            },
            "slope_12m": {
                "source": "third_party_unofficial",
                "usage": "supporting_only",
                "authority": "derived_curve_summary",
                "reason": "由首个合格月和最远合格月推导；horizon_used 若短于12月必须按实际期限解释。",
                "reference_sources": [],
            },
            "cuts_priced_bps": {
                "source": "third_party_unofficial",
                "usage": "supporting_only",
                "authority": "derived_curve_summary",
                "reason": "由首个合格月和最远合格月推导；horizon_used 若短于12月必须按实际期限解释。",
                "reference_sources": [],
            },
            "effr_anchor": {
                "source": "official_fred_reference_when_available",
                "usage": "cross_check_only",
                "authority": "non_blocking_anchor",
                "reason": "EFFR/DFF 是时点实施利率，而期货合约隐含整月平均利率；偏差只标注 anomaly，不阻断曲线判读。",
                "reference_sources": ["FRED EFFR", "FRED DFF"],
            },
        }

    def _unavailable(reason: str, raw_series: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        quality = build_data_quality(
            provider="yfinance",
            source_name=source_name,
            source_url=source_url,
            source_tier="third_party_unofficial",
            data_date="not_available",
            as_of_date=effective_date_str,
            effective_date=effective_date_str,
            vintage_date="not_available",
            availability="unavailable",
            fallback_reason=reason,
            fallback_chain=["third_party_unofficial", "unavailable"],
            license_note="public_endpoint_review_required",
            coverage={"contracts_requested": FED_FUNDS_PATH_MONTHS, "contracts_observed": 0},
            methodology="implied_rate = 100 - ZQ monthly futures close; curve requires at least four non-negligible months",
            formula="implied_rate = 100 - close",
            anomalies=[reason],
        )
        quality["metric_authority"] = _metric_authority()
        return {
            "name": "Fed Funds Futures Implied Rate Path",
            "series_id": "ZQ_MONTHLY_PATH",
            "value": None,
            "unit": "percent",
            "date": effective_date_str,
            "source_tier": "third_party_unofficial",
            "source_name": source_name,
            "source_url": source_url,
            "availability": "unavailable",
            "unavailable_reason": reason,
            "data_quality": quality,
            "notes": f"Fed funds futures rate path unavailable: {reason}",
        }

    raw_series: List[Dict[str, Any]] = []
    path: List[Dict[str, Any]] = []
    try:
        for months_ahead in range(FED_FUNDS_PATH_MONTHS):
            contract_year, contract_month = _fed_funds_month_at_offset(effective_date, months_ahead)
            contract = _fed_funds_contract_for_month(contract_year, contract_month)
            observations: List[Dict[str, Any]] = []
            try:
                frame = cached_yf_download(
                    contract,
                    start=request_start.strftime("%Y-%m-%d"),
                    end=request_end.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=False,
                )
                frame = clean_yfinance_dataframe(frame)
                if frame is not None and not frame.empty and "close" in frame.columns:
                    frame = frame.copy()
                    frame.index = pd.to_datetime(frame.index)
                    if getattr(frame.index, "tz", None) is not None:
                        frame.index = frame.index.tz_localize(None)
                    frame = frame[frame.index <= pd.Timestamp(effective_date)].sort_index().tail(10)
                    for data_date, row in frame.iterrows():
                        close_value = row.get("close")
                        volume_value = row.get("volume")
                        if pd.isna(close_value):
                            continue
                        observations.append({
                            "data_date": pd.Timestamp(data_date).strftime("%Y-%m-%d"),
                            "close": round(float(close_value), 4),
                            "volume": None if pd.isna(volume_value) else round(float(volume_value), 2),
                        })
            except Exception as contract_exc:
                logging.warning("Fed funds contract %s unavailable: %s", contract, contract_exc)

            volumes = [item["volume"] for item in observations if isinstance(item.get("volume"), (int, float))]
            avg_volume = (sum(volumes) / len(volumes)) if volumes else None
            liquidity_tier = _fed_funds_liquidity_tier(avg_volume)
            raw_entry = {
                "months_ahead": months_ahead,
                "contract": contract,
                "contract_year": contract_year,
                "contract_month": contract_month,
                "observations": observations,
                "avg_volume_10d": None if avg_volume is None else round(avg_volume, 2),
                "liquidity_tier": liquidity_tier if observations else "unavailable",
                "included_in_path": bool(observations and liquidity_tier != "negligible"),
            }
            raw_series.append(raw_entry)
            if not observations or liquidity_tier == "negligible":
                continue

            latest = observations[-1]
            item_authority = (
                "low_liquidity_far_month" if months_ahead > 6
                else "supporting_thin_liquidity" if liquidity_tier == "thin"
                else "supporting"
            )
            path.append({
                "months_ahead": months_ahead,
                "contract": contract,
                "implied_rate": round(100.0 - float(latest["close"]), 4),
                "close": latest["close"],
                "last_trade_date": latest["data_date"],
                "avg_volume_10d": round(float(avg_volume), 2),
                "liquidity_tier": liquidity_tier,
                "field_authority": item_authority,
            })

        observed_contracts = sum(1 for entry in raw_series if entry["observations"])
        if observed_contracts == 0:
            return _unavailable("no_zq_contract_observations_on_or_before_effective_date", raw_series)

        curve_status = "available" if len(path) >= FED_FUNDS_PATH_MINIMUM_CURVE_MONTHS else "insufficient_curve"
        front_month = deepcopy(path[0]) if path else None
        far_month = deepcopy(path[-1]) if path else None
        slope_12m: Optional[float] = None
        cuts_priced_bps: Optional[int] = None
        state: Optional[str] = None
        horizon_used: Optional[Dict[str, Any]] = None
        if front_month and far_month:
            actual_curve_months = far_month["months_ahead"] - front_month["months_ahead"]
            horizon_used = {
                "requested_months_ahead": 12,
                "front_months_ahead": front_month["months_ahead"],
                "far_months_ahead": far_month["months_ahead"],
                "actual_months_ahead": actual_curve_months,
                "contract": far_month["contract"],
                "fallback_used": actual_curve_months != 12,
                "reason": (
                    "front_or_requested_12m_contract_excluded_or_unavailable_used_actual_qualified_span"
                    if actual_curve_months != 12 else "requested_12m_curve_span_qualified"
                ),
            }
        if curve_status == "available" and front_month and far_month:
            slope_raw = float(far_month["implied_rate"]) - float(front_month["implied_rate"])
            slope_12m = round(slope_raw, 4)
            cuts_priced_bps = round(-slope_raw * 100)
            state = _fed_funds_path_state(slope_raw)

        anomalies: List[str] = []
        effr_anchor: Optional[Dict[str, Any]] = None
        for anchor_series_id in ("EFFR", "DFF"):
            try:
                anchor_series = get_fred_series(anchor_series_id, days=60, end_date=end_date)
                if anchor_series is None or anchor_series.empty or not {"date", "value"}.issubset(anchor_series.columns):
                    continue
                anchor_frame = anchor_series.copy()
                anchor_frame["date"] = pd.to_datetime(anchor_frame["date"], errors="coerce")
                anchor_frame["value"] = pd.to_numeric(anchor_frame["value"], errors="coerce")
                anchor_frame = anchor_frame[
                    anchor_frame["date"].notna()
                    & (anchor_frame["date"] <= pd.Timestamp(effective_date))
                ].dropna(subset=["value"])
                if anchor_frame.empty:
                    continue
                anchor_row = anchor_frame.sort_values("date").iloc[-1]
                anchor_rate = float(anchor_row["value"])
                front_gap = None if front_month is None else round(float(front_month["implied_rate"]) - anchor_rate, 4)
                effr_anchor = {
                    "series_id": anchor_series_id,
                    "rate": round(anchor_rate, 4),
                    "data_date": anchor_row["date"].strftime("%Y-%m-%d"),
                    "front_month_minus_anchor_pp": front_gap,
                    "availability": "available",
                    "usage": "non_blocking_cross_check",
                }
                if front_gap is not None and abs(front_gap) > 0.35:
                    anomalies.append(f"front_month_vs_{anchor_series_id.lower()}_gap_gt_0.35pp:{front_gap:+.4f}pp")
                break
            except Exception as anchor_exc:
                logging.warning("Optional FRED anchor %s ignored: %s", anchor_series_id, anchor_exc)
                continue
        if effr_anchor is None:
            anomalies.append("effr_anchor_unavailable_non_blocking")

        data_dates = [entry["observations"][-1]["data_date"] for entry in raw_series if entry["observations"]]
        latest_data_date = max(data_dates) if data_dates else effective_date_str
        value = {
            "effective_date": effective_date_str,
            "status": curve_status,
            "front_month": front_month,
            "path": path,
            "slope_12m": slope_12m,
            "horizon_used": horizon_used,
            "cuts_priced_bps": cuts_priced_bps,
            "state": state,
            "state_thresholds": state_thresholds,
            "liquidity_thresholds": liquidity_thresholds,
            "effr_anchor": effr_anchor,
            "raw_series": raw_series,
            "state_usage_boundary": {
                "easing_priced": {
                    "usage": "supporting_only",
                    "reason": "深度降息定价可能反映衰退恐惧；必须与 HY OAS 和增长数据交叉验证后才能讨论方向，禁止单独作为流动性利多。",
                },
                "tightening_priced": {
                    "usage": "supporting_only",
                    "reason": "只可作为贴现率逆风的风险确认，不能单独推出 NDX 方向。",
                },
                "flat_path": {
                    "usage": "supporting_only",
                    "reason": "缓冲带内没有足够曲线斜率信号，不携带方向性结论。",
                },
            },
            "source_boundary": (
                "ZQ 结算价反映市场对合约月份平均联邦基金利率的定价，不是 Fed 承诺；Yahoo 为未经 CME 官方核验的第三方转发。"
                "本缩水版不拼接历史合约、不计算历史分位，也不输出会议概率；升级路径是在官方 CME/FedWatch 可达后核验结算价并增加会议级概率与严格 PIT 合约档案。"
            ),
        }
        quality = build_data_quality(
            provider="yfinance",
            source_name=source_name,
            source_url=source_url,
            source_tier="third_party_unofficial",
            data_date=latest_data_date,
            as_of_date=latest_data_date,
            effective_date=effective_date_str,
            vintage_date=latest_data_date,
            availability="available",
            fallback_reason=("none" if curve_status == "available" else "fewer_than_four_non_negligible_contract_months"),
            fallback_chain=["third_party_unofficial", "unavailable"],
            license_note="public_endpoint_review_required",
            coverage={
                "contracts_requested": FED_FUNDS_PATH_MONTHS,
                "contracts_observed": observed_contracts,
                "contracts_in_formal_path": len(path),
                "negligible_contracts_excluded": sum(1 for entry in raw_series if entry["liquidity_tier"] == "negligible"),
                "curve_status": curve_status,
                "minimum_curve_months_required": FED_FUNDS_PATH_MINIMUM_CURVE_MONTHS,
                "horizon_used": horizon_used,
            },
            methodology=(
                "For each of 13 monthly ZQ contracts from the effective-date month: select the latest close on/before effective_date, "
                "implied_rate=100-close, average the available last 10 daily volumes, exclude avg_volume<5, retain 5<=volume<100 as thin, "
                "then slope=farthest qualified implied rate-front qualified implied rate."
            ),
            formula="implied_rate = 100 - close; slope_12m = farthest_qualified_rate - front_qualified_rate; cuts_priced_bps = round(-slope_12m * 100)",
            anomalies=anomalies,
            point_in_time_note="Contract set and every observation are truncated to effective_date; settlement closes are non-revisable market facts.",
        )
        quality["metric_authority"] = _metric_authority()
        return {
            "name": "Fed Funds Futures Implied Rate Path",
            "series_id": "ZQ_MONTHLY_PATH",
            "value": value,
            "unit": "percent",
            "date": latest_data_date,
            "source_tier": "third_party_unofficial",
            "source_name": source_name,
            "source_url": source_url,
            "availability": "available",
            "data_quality": quality,
            "notes": (
                "ZQ 月合约隐含的是整月平均利率，而 EFFR/DFF 锚是最近时点实施利率；二者超过0.35个百分点只记异常、不阻断。"
                + (" 合格月份不足4个，曲线结论已诚实降级。" if curve_status == "insufficient_curve" else "")
            ),
        }
    except Exception as exc:
        return _unavailable(f"fed_funds_rate_path_exception:{str(exc)[:150]}", raw_series)


def get_10y2y_spread_bp(end_date: str = None) -> Dict[str, Any]:
    """获取10年-2年期美债利差。分层降噪：用 MA20 乖离率替代日度动量。"""
    series = get_fred_series("T10Y2Y", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="10Y-2Y Treasury Spread",
            series_id="T10Y2Y",
            unit="basis points",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )
    series = series.copy()
    series['value'] = series['value'] * 100  # Convert to BPS
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return _attach_recompute_value_series({
        "name": "10Y-2Y Treasury Spread", "series_id": "T10Y2Y", "value": analysis,
        "unit": "basis points", "source_name": "FRED",
        "notes": "10Y-2Y 利差；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }, series[["date", "value"]])


def get_10y_real_rate(end_date: str = None) -> Dict[str, Any]:
    """获取10年期实际利率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("DFII10", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="10Y Real Rate",
            series_id="DFII10",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return _attach_recompute_value_series({
        "name": "10Y Real Rate", "series_id": "DFII10", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期实际利率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }, series[["date", "value"]])


def get_10y_treasury(end_date: str = None) -> Dict[str, Any]:
    """获取10年期美债名义收益率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("DGS10", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="10Y Treasury Yield",
            series_id="DGS10",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return _attach_recompute_value_series({
        "name": "10Y Treasury Yield", "series_id": "DGS10", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期美债收益率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }, series[["date", "value"]])


def get_10y_breakeven(end_date: str = None) -> Dict[str, Any]:
    """获取10年期盈亏平衡通胀率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("T10YIE", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="10Y Breakeven Inflation",
            series_id="T10YIE",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return _attach_recompute_value_series({
        "name": "10Y Breakeven Inflation", "series_id": "T10YIE", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期盈亏平衡通胀率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }, series[["date", "value"]])


def get_fed_funds_rate(end_date: str = None) -> Dict[str, Any]:
    """获取联邦基金利率 (V5.1升级)"""
    series = get_fred_series("FEDFUNDS", end_date=end_date)
    if series is None or len(series) < 3:
        return _fred_unavailable_payload(
            name="Fed Funds Rate",
            series_id="FEDFUNDS",
            unit="percent",
            minimum_points=3,
            series=series,
            calculation="momentum_relativity",
        )
    analysis = analyze_series_momentum_relativity(series)
    if not analysis or analysis.get("level") is None:
        return _fred_unavailable_payload(
            name="Fed Funds Rate",
            series_id="FEDFUNDS",
            unit="percent",
            minimum_points=3,
            series=series,
            calculation="momentum_relativity",
        )
    return _attach_recompute_value_series({
        "name": "Fed Funds Rate", "series_id": "FEDFUNDS", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "Effective Federal Funds Rate with momentum and relativity."
    }, series[["date", "value"]])


def get_m2_yoy(end_date: str = None) -> Dict[str, Any]:
    """获取M2货币供应量年同比增速 (保留月度动量特性)"""
    yoy, date = calculate_yoy_change("M2SL", lookback_days=800, end_date=end_date)
    yoy_history = calculate_yoy_series("M2SL", lookback_days=5475, end_date=end_date)
    relativity = None
    if yoy_history is not None and not yoy_history.empty:
        analysis = analyze_series_momentum_relativity(yoy_history)
        relativity = analysis.get("relativity")
    if yoy is None or not date:
        return {
            "name": "M2 YoY Growth",
            "series_id": "M2SL",
            "value": None,
            "unit": "percent",
            "source_name": "FRED",
            "availability": "unavailable",
            "unavailable_reason": "m2_yoy_level_or_observation_date_missing",
            "notes": "M2 YoY cannot be used because the level or observation date is missing.",
        }
    return _attach_recompute_value_series({
        "name": "M2 YoY Growth", "series_id": "M2SL",
        "value": {"level": yoy, "date": date, "momentum": "monthly", "relativity": relativity},
        "unit": "percent", "source_name": "FRED",
        "notes": "M2 Money Supply Year-over-Year Growth (monthly momentum); relativity is calculated on the YoY series itself."
    }, yoy_history[["date", "value"]] if yoy_history is not None else None)


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
    注意：FRED WTREGEN 原始值是百万美元，需除以1000转换为十亿美元。
    """
    df = _fetch_fred_series("WTREGEN", start_date=start_date)
    if df.empty:
        return df
    df["value"] = pd.to_numeric(df["value"], errors="coerce") / 1000.0
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

    def _repair_wtregen_early_mixed_cache(series: pd.Series) -> pd.Series:
        if series.empty:
            return series
        index = pd.to_datetime(series.index, errors="coerce")
        early_mask = (index < pd.Timestamp("2008-10-22")) & (series > 1000)
        if not early_mask.any():
            return series
        repaired = series.copy()
        repaired.loc[early_mask] = repaired.loc[early_mask] / 1000.0
        logging.warning(
            "WTREGEN early-history mixed-cache anomaly repaired for %s rows before 2008-10-22; "
            "cached historical TGA values appear to mix raw million-dollar and normalized billion-dollar units.",
            int(early_mask.sum()),
        )
        return repaired

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
            # WTREGEN 原始口径可能是百万美元；RRPONTSYD 通常已经是十亿美元。
            if max_val > 10_000:
                logging.warning(f"{series_id}检测到百万美元口径或混合缓存（最大值={max_val:.2f}），逐点转换为十亿美元")
                normalized = series.where(series <= 10_000, series / 1000.0)
            elif max_val < 10:
                # 异常小值
                logging.error(f"{series_id}数据异常：最大值={max_val:.2f}，远低于合理范围（应在几百到几千十亿美元）")
                # 可能是万亿美元单位，需要乘以1000
                normalized = series * 1000.0
            else:
                # 数值在合理范围内
                logging.info(f"{series_id}数据范围正常：{min_val:.2f} - {max_val:.2f} 十亿美元")
                normalized = series
            if series_id == "WTREGEN":
                normalized = _repair_wtregen_early_mixed_cache(normalized)
            return normalized
        
        return series

    if walcl_df.empty or tga_df.empty or rrp_df.empty:
        logging.error("净流动性组件数据缺失，无法构建序列")
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)

    for frame in (walcl_df, tga_df, rrp_df):
        frame["date"] = pd.to_datetime(frame["date"])
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame.dropna(subset=["date", "value"], inplace=True)

    walcl_s = walcl_df.set_index("date")["value"].astype(float).resample("D").ffill()
    tga_s = tga_df.set_index("date")["value"].astype(float).resample("D").ffill()
    rrp_s = rrp_df.set_index("date")["value"].astype(float).resample("D").ffill()

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

    effective_date = pd.to_datetime(end_date, errors="coerce") if end_date else None
    net_liq_df, walcl_s, tga_s, rrp_s = _build_net_liquidity_series()

    if net_liq_df.empty:
        return {
            "name": "Net Liquidity (Fed - TGA - RRP)",
            "value": None,
            "notes": "无法获取完整的 WALCL/WTREGEN/RRPONTSYD 序列。"
        }
    if effective_date is not None and not pd.isna(effective_date):
        net_liq_df = net_liq_df[net_liq_df["date"] <= effective_date]
        walcl_s = walcl_s[walcl_s.index <= effective_date]
        tga_s = tga_s[tga_s.index <= effective_date]
        rrp_s = rrp_s[rrp_s.index <= effective_date]

    if net_liq_df.empty or walcl_s.empty or tga_s.empty or rrp_s.empty:
        return {
            "name": "Net Liquidity (Fed - TGA - RRP)",
            "value": None,
            "notes": f"净流动性在 {end_date} 之前没有完整可见数据。"
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

    return _attach_recompute_value_series({
        "name": "Net Liquidity (Fed - TGA - RRP)",
        "series_id": "WALCL-WTREGEN-RRPONTSYD",
        "value": {
            "level": round(latest_level, 2),
            "level_unit": AMOUNT_UNIT_BILLION_USD,
            "momentum_4w": round(momentum_4w, 2) if momentum_4w is not None else None,
            "momentum_4w_unit": AMOUNT_UNIT_BILLION_USD,
            "components": {k: round(v, 2) for k, v in components.items()},
            "components_unit": AMOUNT_UNIT_BILLION_USD,
            "component_units": {k: AMOUNT_UNIT_BILLION_USD for k in components},
            "historical_stats": historical_stats,
            "date": latest_date.strftime("%Y-%m-%d"),
        },
        "unit": "USD Billions",
        "source_name": "FRED",
        "notes": "净流动性；分层降噪：4周滚动动量（月度/周度趋势），替代日度动量。"
    }, net_liq_df[["date", "value"]])


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
        copper_df = _get_series_for_effective_date("HG=F", _fetch_copper_history, end_date)
        gold_df = _get_series_for_effective_date("GC=F", _fetch_gold_history, end_date)

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
                    return _attach_recompute_value_series({
                        "name": "Copper/Gold Ratio",
                        "value": value_out,
                        "unit": "ratio",
                        "source_name": "yfinance (cached)",
                        "notes": "铜/金比率；分层降噪：比值相对 MA50 位置，替代日度动量。"
                    }, ratio_for_ma)
    except Exception as e:
        logging.warning(f"TimeSeriesManager 获取铜/金数据失败: {e}")

    # 回退到直接使用 yfinance 获取数据
    # 使用分单标的下载避免 MultiIndex 结构问题及 clean_yfinance_dataframe 破坏 ticker 信息
    try:
        start_date = effective_date - timedelta(days=365 * 11)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (effective_date + timedelta(days=1)).strftime("%Y-%m-%d")
        copper_df = cached_yf_download("HG=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
        gold_df = cached_yf_download("GC=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
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

        return _attach_recompute_value_series({
            "name": "Copper/Gold Ratio",
            "value": value_out,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": f"铜/金比率；分层降噪：比值相对 MA50 位置。Raw: Copper={aligned_df['copper'].iloc[-1]:.2f}, Gold={aligned_df['gold'].iloc[-1]:.2f}"
        }, ratio_for_analysis)
    except Exception as e:
        return {
            "name": "Copper/Gold Ratio",
            "value": None,
            "notes": f"Failed to calculate: {str(e)}"
        }


# =====================================================
# 已废弃孤儿指标 (原任务2.2): DXY, SOFR, WTI, Gold/WTI Ratio
# 四个函数从未接入运行时（不在 LAYER_FUNCTIONS / TOOLS_REGISTRY），仅供考古。
# =====================================================

def get_dxy_index(end_date: str = None) -> Dict[str, Any]:
    """
    **已废弃（deprecated）**：从未接入运行时，保留仅供考古，新代码勿用。

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
        return _fred_unavailable_payload(
            name="DXY Dollar Index",
            series_id="DTWEXBGS",
            unit="index level",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )

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
    **已废弃（deprecated）**：从未接入运行时，保留仅供考古，新代码勿用。

    获取SOFR担保隔夜融资利率 - V6.0新增

    第一性原理:
    - SOFR (Secured Overnight Financing Rate) 是LIBOR的替代基准利率
    - 基于真实交易（美国国债回购市场），比LIBOR更难操纵，更可靠
    - 反映以美国国债为抵押的隔夜回购融资成本，是衡量美元融资和抵押品流动性的关键指标
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
        return _fred_unavailable_payload(
            name="SOFR Rate",
            series_id="SOFR",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )

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
    **已废弃（deprecated）**：从未接入运行时，保留仅供考古，新代码勿用。

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

        df = cached_yf_download(
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
    **已废弃（deprecated）**：从未接入运行时，保留仅供考古，新代码勿用。

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
        gold_df = cached_yf_download("GC=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
        wti_df = cached_yf_download("CL=F", start=start_str, end=end_str, progress=False, auto_adjust=False)

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

