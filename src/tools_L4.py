# tools_L4.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第4层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

try:
    from .tools_L1 import get_10y_treasury
except ImportError:
    try:
        from tools_L1 import get_10y_treasury
    except ImportError:
        get_10y_treasury = None

try:
    from .tools_L3 import get_ndx100_components
except ImportError:
    from tools_L3 import get_ndx100_components

from io import BytesIO, StringIO
import re
from typing import Iterable
from zipfile import ZipFile
from xml.etree import ElementTree as ET

# =====================================================
# 第4层函数
# =====================================================

SOURCE_TIER_LICENSED_MANUAL = "licensed_manual/Wind"
SOURCE_TIER_OFFICIAL = "official"
SOURCE_TIER_COMPONENT_MODEL = "component_model"
SOURCE_TIER_THIRD_PARTY = "third_party_estimate"
SOURCE_TIER_PROXY = "proxy"
SOURCE_TIER_UNAVAILABLE = "unavailable"

VALUATION_FALLBACK_CHAIN = [
    SOURCE_TIER_LICENSED_MANUAL,
    SOURCE_TIER_OFFICIAL,
    SOURCE_TIER_COMPONENT_MODEL,
    SOURCE_TIER_THIRD_PARTY,
    SOURCE_TIER_PROXY,
    SOURCE_TIER_UNAVAILABLE,
]


def _utc_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str):
        value = value.strip().replace("%", "")
        if "," in value and "." not in value and re.search(r"\d,\d{1,2}$", value):
            value = value.replace(",", ".")
        else:
            value = value.replace(",", "")
        if not value:
            return None
    try:
        return float(value)
    except Exception:
        return None


def _round_or_none(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(value, digits) if value is not None and np.isfinite(value) else None


def _quality_block(
    *,
    source_tier: str,
    data_date: str,
    update_frequency: str,
    formula: str,
    coverage: Any = None,
    anomalies: Optional[List[Any]] = None,
    fallback_chain: Optional[List[str]] = None,
    source_disagreement: Any = None,
) -> Dict[str, Any]:
    return {
        "source_tier": source_tier,
        "data_date": data_date,
        "collected_at_utc": _utc_timestamp(),
        "update_frequency": update_frequency,
        "formula": formula,
        "coverage": coverage or {},
        "anomalies": anomalies or [],
        "fallback_chain": fallback_chain or [],
        "source_disagreement": source_disagreement or {},
    }


def _valuation_source_result(
    *,
    source_id: str,
    source_name: str,
    source_url: str,
    source_tier: str,
    metric: str,
    value: Optional[float],
    unit: str = "ratio",
    percentile_10y: Optional[float] = None,
    data_date: Optional[str] = None,
    methodology: str = "",
    availability: Optional[str] = None,
    unavailable_reason: Optional[str] = None,
    coverage: Any = None,
    formula: str = "",
    fallback_chain: Optional[List[str]] = None,
    source_disagreement: Any = None,
) -> Dict[str, Any]:
    """Normalize one L4 valuation source without inventing missing percentiles."""
    historical_percentile = _round_or_none(percentile_10y) if percentile_10y is not None else None
    normalized_availability = availability or ("available" if value is not None else "unavailable")
    result = {
        "source_id": source_id,
        "source": source_id,
        "source_name": source_name,
        "url": source_url,
        "source_url": source_url,
        "source_tier": source_tier,
        "metric": metric,
        "value": _round_or_none(value) if value is not None else None,
        "unit": unit,
        "percentile_10y": historical_percentile,
        "historical_percentile": historical_percentile,
        "data_date": data_date,
        "collected_at_utc": _utc_timestamp(),
        "methodology": methodology,
        "availability": normalized_availability,
        "unavailable_reason": unavailable_reason,
        "coverage": coverage or {},
        "formula": formula,
        "fallback_chain": fallback_chain or VALUATION_FALLBACK_CHAIN,
        "source_disagreement": source_disagreement or {},
    }
    return result


def _unavailable_valuation_source(
    *,
    source_id: str,
    source_name: str,
    source_url: str,
    metric: str,
    reason: str,
    methodology: str = "",
) -> Dict[str, Any]:
    return _valuation_source_result(
        source_id=source_id,
        source_name=source_name,
        source_url=source_url,
        source_tier=SOURCE_TIER_UNAVAILABLE,
        metric=metric,
        value=None,
        methodology=methodology,
        availability="unavailable",
        unavailable_reason=reason,
    )


def _html_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", "\n", html)


def _first_number(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text, flags=re.I | re.S)
    return _safe_float(match.group(1)) if match else None


def _first_date(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, flags=re.I | re.S)
    return match.group(1).strip() if match else None


def _percent_or_none(value: Any, digits: int = 2) -> Optional[float]:
    number = _safe_float(value)
    if number is None:
        return None
    if abs(number) <= 1:
        number *= 100
    return _round_or_none(number, digits)


def _excel_serial_to_date(value: Any, *, date1904: bool = False) -> Optional[str]:
    number = _safe_float(value)
    if number is None or number < 20000:
        return None
    try:
        if date1904:
            number += 1462
        return (datetime(1899, 12, 30) + timedelta(days=int(number))).strftime("%Y-%m-%d")
    except Exception:
        return None


def _normalize_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _xlsx_cell_text(cell: ET.Element, shared_strings: List[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//{*}t")).strip()

    raw_value = cell.findtext("{*}v")
    if raw_value is None:
        return ""
    raw_value = raw_value.strip()
    if cell_type == "s":
        idx = int(_safe_float(raw_value) or 0)
        return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
    if cell_type == "str":
        return raw_value
    number = _safe_float(raw_value)
    return number if number is not None else raw_value


def _xlsx_col_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", str(cell_ref or "A1").upper())
    letters = match.group(1) if match else "A"
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


def _parse_xlsx_tables(content: bytes) -> List[pd.DataFrame]:
    """Parse simple XLSX sheets with stdlib so official Damodaran files do not require openpyxl."""
    with ZipFile(BytesIO(content)) as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for item in root.findall(".//{*}si"):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//{*}t")).strip())

        rels: Dict[str, str] = {}
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rels_root.findall("{*}Relationship"):
            target = rel.attrib.get("Target", "")
            if target.startswith("/"):
                path = target.lstrip("/")
            else:
                path = f"xl/{target}"
            rels[rel.attrib.get("Id", "")] = path.replace("\\", "/")

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        workbook_pr = workbook.find("{*}workbookPr")
        date1904 = bool(workbook_pr is not None and str(workbook_pr.attrib.get("date1904", "")).lower() in {"1", "true"})
        tables: List[pd.DataFrame] = []
        for sheet in workbook.findall(".//{*}sheet"):
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            sheet_path = rels.get(rel_id or "")
            if not sheet_path or sheet_path not in zf.namelist():
                continue
            sheet_root = ET.fromstring(zf.read(sheet_path))
            rows: List[List[Any]] = []
            for row in sheet_root.findall(".//{*}sheetData/{*}row"):
                values: List[Any] = []
                for cell in row.findall("{*}c"):
                    idx = _xlsx_col_index(cell.attrib.get("r", ""))
                    while len(values) <= idx:
                        values.append("")
                    values[idx] = _xlsx_cell_text(cell, shared_strings)
                rows.append(values)
            if not rows:
                continue
            width = max(len(row) for row in rows)
            normalized_rows = [row + [""] * (width - len(row)) for row in rows]
            header_idx = next((i for i, row in enumerate(normalized_rows) if any(str(item).strip() for item in row)), 0)
            headers = [str(item).strip() or f"column_{idx}" for idx, item in enumerate(normalized_rows[header_idx])]
            data_rows = normalized_rows[header_idx + 1 :]
            frame = pd.DataFrame(data_rows, columns=headers)
            frame.attrs["date1904"] = date1904
            tables.append(frame)
        return tables


def _read_excel_tables(content: bytes) -> List[pd.DataFrame]:
    try:
        sheets = pd.read_excel(BytesIO(content), sheet_name=None)
        return list(sheets.values())
    except Exception:
        return _parse_xlsx_tables(content)


def _find_column(columns: Iterable[Any], *needles: str, any_needles: Iterable[str] = ()) -> Optional[Any]:
    any_needles_l = tuple(item.lower() for item in any_needles)
    for col in columns:
        label = _normalize_label(col)
        if all(needle.lower() in label for needle in needles) and (
            not any_needles_l or any(needle in label for needle in any_needles_l)
        ):
            return col
    return None


def _latest_row_by_date(table: pd.DataFrame, date_col: Any) -> Optional[pd.Series]:
    working = table.copy()
    date1904 = bool(table.attrs.get("date1904"))

    def sort_key(value: Any) -> str:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        serial_date = _excel_serial_to_date(value, date1904=date1904)
        if serial_date:
            return serial_date
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return ""
        return parsed.strftime("%Y-%m-%d")

    working["_date_key"] = working[date_col].map(sort_key)
    working = working[working["_date_key"].astype(bool)].sort_values("_date_key")
    if working.empty:
        return None
    return working.iloc[-1]


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
    """计算NDX成分股聚合估值，避免把PE做简单平均。"""
    if df.empty:
        return {}

    working = df.copy()
    if "ticker" not in working.columns:
        working["ticker"] = working.index.astype(str)
    if "market_cap" not in working.columns:
        return {}

    working["market_cap"] = working["market_cap"].map(_safe_float)
    total_constituents = len(working)
    total_market_cap = float(working["market_cap"].dropna().clip(lower=0).sum())
    if total_market_cap <= 0:
        return {}

    anomalies: List[Dict[str, Any]] = []
    coverage: Dict[str, Dict[str, Any]] = {}
    metrics: Dict[str, Any] = {"coverage": coverage, "anomalies": anomalies}

    def _metric_coverage(metric_key: str, valid: pd.DataFrame, excluded: List[Dict[str, Any]]) -> None:
        covered_market_cap = float(valid["market_cap"].sum()) if not valid.empty else 0.0
        coverage[metric_key] = {
            "constituents_used": int(len(valid)),
            "total_constituents": int(total_constituents),
            "constituent_coverage_pct": round(len(valid) / total_constituents * 100, 2) if total_constituents else 0.0,
            "market_cap_coverage_pct": round(covered_market_cap / total_market_cap * 100, 2) if total_market_cap else 0.0,
            "excluded": excluded[:20],
        }

    def _valid_pe_frame(column: str, metric_key: str) -> pd.DataFrame:
        excluded: List[Dict[str, Any]] = []
        pe_values = working[column].map(_safe_float) if column in working.columns else pd.Series([None] * len(working))
        frame = working.assign(_pe=pe_values)
        valid = frame[(frame["market_cap"] > 0) & (frame["_pe"] > 0)].copy()
        for _, row in frame.loc[~frame.index.isin(valid.index)].iterrows():
            reason = "missing_or_nonpositive_market_cap" if not row.get("market_cap") or row.get("market_cap") <= 0 else f"invalid_{column}"
            item = {"ticker": row.get("ticker"), "metric": metric_key, "reason": reason}
            excluded.append(item)
            anomalies.append(item)
        _metric_coverage(metric_key, valid, excluded)
        return valid

    trailing = _valid_pe_frame("trailing_pe", "trailing_pe")
    if not trailing.empty:
        earnings = trailing["market_cap"] / trailing["_pe"]
        covered_cap = float(trailing["market_cap"].sum())
        total_earnings = float(earnings.sum())
        if total_earnings > 0:
            metrics["weighted_trailing_pe"] = round(covered_cap / total_earnings, 2)
            metrics["weighted_earnings_yield"] = round(total_earnings / covered_cap * 100, 2)

    forward = _valid_pe_frame("forward_pe", "forward_pe")
    if not forward.empty:
        forward_earnings = forward["market_cap"] / forward["_pe"]
        covered_cap = float(forward["market_cap"].sum())
        total_forward_earnings = float(forward_earnings.sum())
        if total_forward_earnings > 0:
            metrics["weighted_forward_pe"] = round(covered_cap / total_forward_earnings, 2)
            metrics["weighted_forward_earnings_yield"] = round(total_forward_earnings / covered_cap * 100, 2)

    fcf_values = working["fcf"].map(_safe_float) if "fcf" in working.columns else pd.Series([None] * len(working))
    if fcf_values.isna().all() and "fcf_yield" in working.columns:
        fcf_yield_values = working["fcf_yield"].map(_safe_float)
        fcf_values = working["market_cap"] * fcf_yield_values / 100.0
    fcf_frame = working.assign(_fcf=fcf_values)
    valid_fcf = fcf_frame[(fcf_frame["market_cap"] > 0) & fcf_frame["_fcf"].notna()].copy()
    fcf_excluded: List[Dict[str, Any]] = []
    for _, row in fcf_frame.loc[~fcf_frame.index.isin(valid_fcf.index)].iterrows():
        reason = "missing_or_nonpositive_market_cap" if not row.get("market_cap") or row.get("market_cap") <= 0 else "missing_fcf"
        item = {"ticker": row.get("ticker"), "metric": "fcf_yield", "reason": reason}
        fcf_excluded.append(item)
        anomalies.append(item)
    _metric_coverage("fcf_yield", valid_fcf, fcf_excluded)
    if not valid_fcf.empty:
        covered_cap = float(valid_fcf["market_cap"].sum())
        total_fcf = float(valid_fcf["_fcf"].sum())
        if covered_cap > 0:
            metrics["weighted_fcf_yield"] = round(total_fcf / covered_cap * 100, 2)

    if "price_to_book" in working.columns:
        pb_values = working["price_to_book"].map(_safe_float)
        pb_frame = working.assign(_pb=pb_values)
        valid_pb = pb_frame[(pb_frame["market_cap"] > 0) & (pb_frame["_pb"] > 0)].copy()
        pb_excluded = [
            {"ticker": row.get("ticker"), "metric": "price_to_book", "reason": "invalid_price_to_book"}
            for _, row in pb_frame.loc[~pb_frame.index.isin(valid_pb.index)].iterrows()
        ]
        _metric_coverage("price_to_book", valid_pb, pb_excluded)
        if not valid_pb.empty:
            weights = valid_pb["market_cap"] / valid_pb["market_cap"].sum()
            metrics["weighted_price_to_book"] = round(float(np.average(valid_pb["_pb"], weights=weights)), 2)

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
                "TrailingPE": pe,
                "ForwardPE": forward_pe,
                "EarningsYield": round(earnings_yield, 2) if earnings_yield else None,
                "FCFYield": None,  # Alpha Vantage无QQQ FCF数据
                "Coverage": {"note": "QQQ代理NDX，非完整成分股计算"}
            },
            "unit": "ratio/percent",
            "date": effective_date.strftime("%Y-%m-%d"),
            "source_tier": SOURCE_TIER_PROXY,
            "source_name": "Alpha Vantage (QQQ Proxy)",
            "data_quality": _quality_block(
                source_tier=SOURCE_TIER_PROXY,
                data_date=effective_date.strftime("%Y-%m-%d"),
                update_frequency="latest QQQ overview when Alpha Vantage updates",
                formula="QQQ proxy PE/ForwardPE; earnings yield = 1 / ForwardPE",
                coverage={"note": "QQQ proxy, not component-level NDX coverage"},
                anomalies=["FCF yield unavailable from Alpha Vantage QQQ overview"],
                fallback_chain=VALUATION_FALLBACK_CHAIN,
            ),
            "notes": "因yfinance不可用，使用QQQ数据代理NDX基本面"
        }
    except Exception as e:
        return {
            "name": "NDX P/E and Earnings Yield",
            "value": None,
            "notes": f"Alpha Vantage fallback failed: {str(e)[:50]}"
        }


def _fetch_text(url: str, timeout: int = 8) -> Tuple[Optional[str], Optional[str]]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ndx-vnext/1.0)"},
            timeout=timeout,
            proxies=get_requests_proxies(),
        )
        response.raise_for_status()
        return response.text, None
    except Exception as exc:
        return None, str(exc)[:120]


def _fetch_bytes(url: str, timeout: int = 12) -> Tuple[Optional[bytes], Optional[str]]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ndx-vnext/1.0)"},
            timeout=timeout,
            proxies=get_requests_proxies(),
        )
        response.raise_for_status()
        return response.content, None
    except Exception as exc:
        return None, str(exc)[:120]


def _parse_worldperatio_ndx_pe(html: str) -> Dict[str, Any]:
    text = _html_text(html)
    value = _first_number(r"P/E Ratio\s*\n\s*([0-9]+(?:\.[0-9]+)?)", text)
    data_date = _first_date(r"([0-9]{2}\s+[A-Za-z]+\s+[0-9]{4})(?:\s*\n|\s+)", text)
    percentile = _first_number(
        r"(?:Historical\s+)?(?:Percentile(?:\s+Rank)?|Rank)\s*\n\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        text,
    )
    lower_text = text.lower()
    methodology_bits = ["QQQ ETF proxy"]
    if "rolling average" in lower_text:
        methodology_bits.append("rolling average")
    if "outlier" in lower_text:
        methodology_bits.append("outlier normalization")
    if len(methodology_bits) == 1:
        methodology_bits.append("published WorldPERatio methodology text")
    unavailable_reason = None if percentile is not None else "historical percentile unavailable: source does not provide explicit percentile/rank"
    result = _valuation_source_result(
        source_id="worldperatio_pe",
        source_name="WorldPERatio",
        source_url="https://worldperatio.com/index/nasdaq-100/",
        source_tier=SOURCE_TIER_THIRD_PARTY,
        metric="ndx_trailing_pe",
        value=value,
        percentile_10y=percentile,
        data_date=data_date,
        methodology="; ".join(methodology_bits),
        unavailable_reason=unavailable_reason,
        formula="Published Nasdaq 100 PE; no historical percentile unless explicit percentile/rank is published",
    )
    relative_position = _parse_worldperatio_relative_position(text, percentile_is_explicit=percentile is not None)
    if relative_position:
        result["relative_position"] = relative_position
        result["methodology"] = f"{result['methodology']}; std-dev / z-score relative context is not percentile"
    return result


def _parse_worldperatio_relative_position(text: str, *, percentile_is_explicit: bool) -> Dict[str, Any]:
    windows: Dict[str, Dict[str, Any]] = {}
    for years in (1, 5, 10, 20):
        window_key = f"{years}y"
        block_match = re.search(
            rf"{years}\s+Year.*?(?=\n\s*(?:1|5|10|20)\s+Year|\n\s*(?:50|200)\s+Day|$)",
            text,
            flags=re.I | re.S,
        )
        if not block_match:
            continue
        block = block_match.group(0)
        average_pe = _first_number(r"Average\s+PE\s*:?\s*\n?\s*([0-9]+(?:\.[0-9]+)?)", block)
        std_dev = _first_number(r"(?:Standard\s+Deviation|Std\.?\s*Dev\.?)\s*:?\s*\n?\s*([0-9]+(?:\.[0-9]+)?)", block)
        range_match = re.search(
            r"(?:Fair\s+Value\s+Range|Range)\s*:?\s*\n?\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)",
            block,
            flags=re.I,
        )
        deviation = _first_number(r"Deviation\s+from\s+mean\s*:?\s*\n?\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*(?:sigma|σ)?", block)
        label = _first_date(r"Valuation\s*:?\s*\n?\s*([A-Za-z][A-Za-z\s-]+?)(?:\n|$)", block)
        if not any(value is not None for value in (average_pe, std_dev, deviation)) and not range_match and not label:
            continue
        windows[window_key] = {
            "average_pe": _round_or_none(average_pe),
            "std_dev": _round_or_none(std_dev),
            "range_low": _round_or_none(_safe_float(range_match.group(1)) if range_match else None),
            "range_high": _round_or_none(_safe_float(range_match.group(2)) if range_match else None),
            "deviation_vs_mean_sigma": _round_or_none(deviation),
            "valuation_label": label.strip() if label else None,
        }

    trend_context = {
        "sma50_margin_pct": _round_or_none(_first_number(r"50\s+Day\s+SMA\s+margin\s*:?\s*\n?\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*%?", text)),
        "sma200_margin_pct": _round_or_none(_first_number(r"200\s+Day\s+SMA\s+margin\s*:?\s*\n?\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*%?", text)),
    }
    trend_context = {key: value for key, value in trend_context.items() if value is not None}

    if not windows and not trend_context:
        return {}
    return {
        "position_type": "std_dev_context_not_percentile",
        "percentile_is_explicit": percentile_is_explicit,
        "valuation_windows": windows,
        "trend_context": trend_context,
        "interpretation_boundary": "WorldPERatio rolling averages/std-dev labels describe relative position but are not historical percentile/rank.",
    }


def _parse_trendonify_ndx_pe(html: str, *, forward: bool = False) -> Dict[str, Any]:
    text = _html_text(html)
    title = "Nasdaq 100 Forward PE Ratio" if forward else "Nasdaq 100 PE Ratio"
    metric = "ndx_forward_pe" if forward else "ndx_trailing_pe"
    value = _first_number(rf"{re.escape(title)}\s*\n\s*([0-9]+(?:\.[0-9]+)?)", text)
    data_date = _first_date(r"Last Updated:\s*([A-Za-z]+\s+[0-9]{2},\s+[0-9]{4})", text)
    percentile = _first_number(r"Valuation Percentile Rank\s*\n\s*([0-9]+(?:\.[0-9]+)?)\s*%?", text)
    url = (
        "https://trendonify.com/united-states/stock-market/nasdaq-100/forward-pe-ratio"
        if forward
        else "https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio"
    )
    return _valuation_source_result(
        source_id="trendonify_forward_pe" if forward else "trendonify_pe",
        source_name="Trendonify",
        source_url=url,
        source_tier=SOURCE_TIER_THIRD_PARTY,
        metric=metric,
        value=value,
        percentile_10y=percentile,
        data_date=data_date,
        methodology="QQQ-derived third-party estimate with explicit valuation percentile rank when available",
        formula=f"Published {title}; percentile only from explicit Valuation Percentile Rank",
    )


def get_ndx_valuation_third_party_checks() -> List[Dict[str, Any]]:
    """读取第三方NDX估值页面，作为校验源，不作为主估值源。"""
    checks: List[Dict[str, Any]] = []
    sources = [
        ("worldperatio_pe", "https://worldperatio.com/index/nasdaq-100/", _parse_worldperatio_ndx_pe),
        (
            "trendonify_pe",
            "https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio",
            lambda html: _parse_trendonify_ndx_pe(html, forward=False),
        ),
        (
            "trendonify_forward_pe",
            "https://trendonify.com/united-states/stock-market/nasdaq-100/forward-pe-ratio",
            lambda html: _parse_trendonify_ndx_pe(html, forward=True),
        ),
    ]
    for source_id, url, parser in sources:
        html, error = _fetch_text(url)
        if error or not html:
            checks.append(
                _unavailable_valuation_source(
                    source_id=source_id,
                    source_name="Trendonify" if source_id.startswith("trendonify") else "WorldPERatio",
                    source_url=url,
                    metric="ndx_forward_pe" if source_id.endswith("forward_pe") else "ndx_trailing_pe",
                    reason=error or "empty_response",
                )
            )
            continue
        try:
            parsed = parser(html)
            checks.append(parsed)
        except Exception as exc:
            checks.append(
                _unavailable_valuation_source(
                    source_id=source_id,
                    source_name="Trendonify" if source_id.startswith("trendonify") else "WorldPERatio",
                    source_url=url,
                    metric="ndx_forward_pe" if source_id.endswith("forward_pe") else "ndx_trailing_pe",
                    reason=str(exc)[:120],
                )
            )
    return checks


def _damodaran_table_candidates(table: pd.DataFrame) -> List[pd.DataFrame]:
    candidates = [table]
    for idx, row in table.iterrows():
        values = [str(value).strip().lower() for value in row.tolist()]
        if "year" not in values:
            continue
        promoted = table.iloc[idx + 1 :].copy()
        promoted.columns = [str(value).strip() for value in row.tolist()]
        candidates.append(promoted)
        break
    return candidates


def _parse_damodaran_implied_erp_tables(tables: List[pd.DataFrame]) -> Dict[str, Any]:
    for raw_table in tables:
        for table in _damodaran_table_candidates(raw_table):
            parsed = _parse_damodaran_implied_erp_table(table)
            if parsed:
                return parsed
    raise ValueError("No Damodaran implied ERP table found")


def _parse_damodaran_implied_erp_table(table: pd.DataFrame) -> Optional[Dict[str, Any]]:
    normalized_columns = [str(col).strip() for col in table.columns]
    lower_columns = [col.lower() for col in normalized_columns]
    year_col = next((col for col, lower in zip(normalized_columns, lower_columns) if lower == "year"), None)
    fcfe_col = next(
        (
            col
            for col, lower in zip(normalized_columns, lower_columns)
            if "implied" in lower and "fcfe" in lower
        ),
        None,
    )
    ddm_col = next(
        (
            col
            for col, lower in zip(normalized_columns, lower_columns)
            if "implied" in lower and "ddm" in lower
        ),
        None,
    )
    bond_col = next((col for col, lower in zip(normalized_columns, lower_columns) if "t.bond" in lower), None)
    if not year_col or not (fcfe_col or ddm_col):
        return None
    table = table.copy()
    table["_year"] = table[year_col].map(_safe_float)
    table = table.dropna(subset=["_year"]).sort_values("_year")
    if table.empty:
        return None
    latest = table.iloc[-1]

    def percent_value(column: Optional[str]) -> Optional[float]:
        if not column:
            return None
        value = _safe_float(latest.get(column))
        if value is not None and abs(value) <= 1:
            value *= 100
        return _round_or_none(value)

    result = {
        "year": int(latest["_year"]),
        "implied_premium_fcfe": percent_value(fcfe_col),
        "implied_premium_ddm": percent_value(ddm_col),
        "t_bond_rate": percent_value(bond_col),
    }
    result["implied_erp_fcfe"] = result["implied_premium_fcfe"]
    result["implied_erp_ddm"] = result["implied_premium_ddm"]
    result["tbond_rate"] = result["t_bond_rate"]
    if result["implied_premium_fcfe"] is not None or result["implied_premium_ddm"] is not None:
        return result
    return None


def _parse_damodaran_implied_erp_html(html: str) -> Dict[str, Any]:
    tables = pd.read_html(StringIO(html))
    return _parse_damodaran_implied_erp_tables(tables)


def _format_damodaran_date(value: Any, *, date1904: bool = False) -> Optional[str]:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    serial_date = _excel_serial_to_date(value, date1904=date1904)
    if serial_date:
        return serial_date
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def _parse_damodaran_monthly_erp_excel(content: bytes) -> Dict[str, Any]:
    """Parse Damodaran ERPbymonth.xlsx for the latest monthly current ERP row."""
    tables = _read_excel_tables(content)
    for table in tables:
        if table.empty:
            continue
        date_col = _find_column(table.columns, "date")
        if not date_col:
            date_col = _find_column(table.columns, "start", any_needles=("month",))
        if not date_col:
            continue
        latest = _latest_row_by_date(table, date_col)
        if latest is None:
            continue

        columns = list(table.columns)
        sp500_col = _find_column(columns, "s&p")
        tbond_col = _find_column(columns, "t.bond")
        if not tbond_col:
            tbond_col = _find_column(columns, "treasury")
        riskfree_col = _find_column(columns, "riskfree")
        sustainable_col = _find_column(columns, "erp", any_needles=("sustainable", "adjusted payout"))
        cash_yield_col = next(
            (
                col
                for col in columns
                if "erp" in _normalize_label(col)
                and "t12" in _normalize_label(col).replace(" ", "")
                and "sustainable" not in _normalize_label(col)
                and "net" not in _normalize_label(col)
            ),
            None,
        )
        smoothed_col = _find_column(columns, "erp", any_needles=("smoothed", "average cf", "average"))
        normalized_col = _find_column(columns, "erp", any_needles=("normalized",))
        net_cash_col = _find_column(columns, "erp", any_needles=("net cash",))
        expected_return_col = _find_column(columns, "expected", "return")

        result = {
            "data_date": latest.get("_date_key") or _format_damodaran_date(latest.get(date_col), date1904=bool(table.attrs.get("date1904"))),
            "sp500_level": _round_or_none(_safe_float(latest.get(sp500_col))) if sp500_col else None,
            "us_10y_treasury_rate": _percent_or_none(latest.get(tbond_col)) if tbond_col else None,
            "adjusted_riskfree_rate": _percent_or_none(latest.get(riskfree_col)) if riskfree_col else None,
            "erp_t12m_adjusted_payout": _percent_or_none(latest.get(sustainable_col)) if sustainable_col else None,
            "erp_t12m_cash_yield": _percent_or_none(latest.get(cash_yield_col)) if cash_yield_col else None,
            "erp_avg_cf_yield_10y": _percent_or_none(latest.get(smoothed_col)) if smoothed_col else None,
            "erp_normalized_earnings_payout": _percent_or_none(latest.get(normalized_col)) if normalized_col else None,
            "erp_net_cash_yield": _percent_or_none(latest.get(net_cash_col)) if net_cash_col else None,
            "expected_return": _percent_or_none(latest.get(expected_return_col)) if expected_return_col else None,
            "source_file": "ERPbymonth.xlsx",
        }
        series_frame = table.copy()
        if "_date_key" not in series_frame.columns:
            series_frame["_date_key"] = series_frame[date_col].apply(
                lambda value: _format_damodaran_date(value, date1904=bool(table.attrs.get("date1904")))
            )
        series_frame = series_frame.dropna(subset=["_date_key"]).tail(120)
        monthly_series = []
        for _, row in series_frame.iterrows():
            monthly_series.append(
                {
                    "data_date": str(row.get("_date_key")),
                    "sp500_level": _round_or_none(_safe_float(row.get(sp500_col))) if sp500_col else None,
                    "us_10y_treasury_rate": _percent_or_none(row.get(tbond_col)) if tbond_col else None,
                    "adjusted_riskfree_rate": _percent_or_none(row.get(riskfree_col)) if riskfree_col else None,
                    "erp_t12m_adjusted_payout": _percent_or_none(row.get(sustainable_col)) if sustainable_col else None,
                    "erp_t12m_cash_yield": _percent_or_none(row.get(cash_yield_col)) if cash_yield_col else None,
                    "erp_avg_cf_yield_10y": _percent_or_none(row.get(smoothed_col)) if smoothed_col else None,
                    "erp_normalized_earnings_payout": _percent_or_none(row.get(normalized_col)) if normalized_col else None,
                    "erp_net_cash_yield": _percent_or_none(row.get(net_cash_col)) if net_cash_col else None,
                    "expected_return": _percent_or_none(row.get(expected_return_col)) if expected_return_col else None,
                }
            )
        result["monthly_series"] = monthly_series
        if result["us_10y_treasury_rate"] is not None and result["adjusted_riskfree_rate"] is not None:
            result["default_spread"] = _round_or_none(result["us_10y_treasury_rate"] - result["adjusted_riskfree_rate"])
        else:
            result["default_spread"] = None
        if result["data_date"] and any(value is not None for key, value in result.items() if key.startswith("erp_")):
            return result
    raise ValueError("No monthly Damodaran ERP row found")


def _parse_damodaran_current_erp_calculator_excel(content: bytes, *, source_file: str) -> Dict[str, Any]:
    """Parse the current monthly Damodaran ERP calculator workbook for current assumptions."""
    tables = _read_excel_tables(content)
    observations: List[Tuple[str, Any]] = []
    for table in tables:
        for _, row in table.iterrows():
            cells = [cell for cell in row.tolist() if str(cell).strip()]
            if len(cells) < 2:
                continue
            for idx, cell in enumerate(cells):
                label = _normalize_label(cell)
                if not label or _safe_float(cell) is not None:
                    continue
                value = next((_safe_float(candidate) for candidate in cells[idx + 1 :] if _safe_float(candidate) is not None), None)
                if value is not None:
                    observations.append((label, value))

    def find_value(*needles: str, any_needles: Iterable[str] = ()) -> Optional[float]:
        any_needles_l = tuple(item.lower() for item in any_needles)
        for label, value in observations:
            if all(needle.lower() in label for needle in needles) and (
                not any_needles_l or any(needle in label for needle in any_needles_l)
            ):
                return value
        return None

    treasury = find_value("treasury", any_needles=("10-year", "10 year", "t.bond"))
    default_spread = find_value("default", "spread")
    adjusted_riskfree = find_value("riskfree", any_needles=("adjusted", "$"))
    expected_return = find_value("expected", "return")
    erp_tbond = find_value("implied", any_needles=("premium", "erp"))

    result = {
        "source_file": source_file,
        "us_10y_treasury_rate": _percent_or_none(treasury),
        "default_spread": _percent_or_none(default_spread),
        "adjusted_riskfree_rate": _percent_or_none(adjusted_riskfree),
        "expected_return": _percent_or_none(expected_return),
        "erp_net_cash_yield": _percent_or_none(erp_tbond),
    }
    if not any(value is not None for key, value in result.items() if key != "source_file"):
        raise ValueError("No current Damodaran ERP calculator assumptions found")
    return result


def _parse_damodaran_implied_erp_excel(content: bytes) -> Dict[str, Any]:
    """Parse Damodaran histimpl.xls bytes, falling back to HTML-table xls payloads."""
    errors: List[str] = []
    try:
        return _parse_damodaran_implied_erp_tables(_read_excel_tables(content))
    except Exception as exc:
        errors.append(str(exc)[:120])

    for encoding in ("utf-8", "latin1"):
        try:
            html = content.decode(encoding, errors="ignore")
            tables = pd.read_html(StringIO(html))
            parsed = _parse_damodaran_implied_erp_tables(tables)
            parsed["excel_parse_fallback"] = "html_table"
            return parsed
        except Exception as exc:
            errors.append(str(exc)[:120])

    raise ValueError("; ".join(error for error in errors if error) or "No Damodaran implied ERP Excel table found")


def get_damodaran_us_implied_erp(end_date: str = None) -> Dict[str, Any]:
    """Damodaran US implied ERP reference anchor; not an NDX-specific valuation metric."""
    date_str = end_date or datetime.now().strftime("%Y-%m-%d")
    html_url = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/implpr.html"
    annual_download_url = "http://www.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls"
    monthly_url = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"
    try:
        current_dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        current_dt = datetime.now()
    current_source_file = f"ERP{current_dt.strftime('%B')}{current_dt.strftime('%y')}.xlsx"
    current_url = f"https://pages.stern.nyu.edu/~adamodar/pc/implprem/{current_source_file}"
    parsed: Optional[Dict[str, Any]] = None
    retrieval_method = ""
    errors: List[str] = []

    content, monthly_error = _fetch_bytes(monthly_url)
    if content:
        try:
            parsed = _parse_damodaran_monthly_erp_excel(content)
            retrieval_method = "monthly_excel"
            current_content, current_error = _fetch_bytes(current_url)
            if current_content:
                try:
                    current_parsed = _parse_damodaran_current_erp_calculator_excel(
                        current_content,
                        source_file=current_source_file,
                    )
                    parsed["current_calculator_source_file"] = current_source_file
                    parsed["current_calculator_url"] = current_url
                    for key in ("default_spread", "expected_return"):
                        if current_parsed.get(key) is not None:
                            parsed[key] = current_parsed[key]
                except Exception as exc:
                    parsed["current_calculator_error"] = str(exc)[:120]
            elif current_error:
                parsed["current_calculator_error"] = current_error
        except Exception as exc:
            errors.append(f"monthly_excel_parse_failed: {str(exc)[:120]}")
    else:
        errors.append(f"monthly_excel_fetch_failed: {monthly_error or 'empty_response'}")

    if parsed is None:
        annual_content, annual_excel_error = _fetch_bytes(annual_download_url)
    else:
        annual_content, annual_excel_error = None, None

    if parsed is None and annual_content:
        try:
            parsed = _parse_damodaran_implied_erp_excel(annual_content)
            parsed["source_file"] = "histimpl.xls"
            retrieval_method = "annual_excel_fallback"
        except Exception as exc:
            errors.append(f"annual_excel_parse_failed: {str(exc)[:120]}")
    elif parsed is None:
        errors.append(f"annual_excel_fetch_failed: {annual_excel_error or 'empty_response'}")

    if parsed is None:
        html, html_error = _fetch_text(html_url)
        if html:
            try:
                parsed = _parse_damodaran_implied_erp_html(html)
                parsed["source_file"] = "implpr.html"
                retrieval_method = "annual_html_fallback"
            except Exception as exc:
                errors.append(f"html_parse_failed: {str(exc)[:120]}")
        else:
            errors.append(f"html_fetch_failed: {html_error or 'empty_response'}")

    if parsed is None:
        unavailable_reason = "; ".join(errors)
        return {
            "name": "Damodaran US Implied ERP Reference",
            "series_id": "DAMODARAN_US_IMPLIED_ERP",
            "value": None,
            "unit": "percent",
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "source_name": "Damodaran",
            "source_url": monthly_url,
            "download_url": monthly_url,
            "availability": "unavailable",
            "unavailable_reason": unavailable_reason,
            "error": unavailable_reason,
            "data_quality": _quality_block(
                source_tier=SOURCE_TIER_UNAVAILABLE,
                data_date=date_str,
                update_frequency="Damodaran dataset/page update cadence",
                formula="Damodaran implied ERP model for US market; unavailable this run",
                fallback_chain=[SOURCE_TIER_OFFICIAL, SOURCE_TIER_UNAVAILABLE],
            ),
        }

    value = {
        **parsed,
        "scope": "US equity market reference, not NDX-specific",
        "download_url": monthly_url if retrieval_method == "monthly_excel" else annual_download_url,
        "retrieval_method": retrieval_method,
    }
    data_date_out = str(parsed.get("data_date") or parsed.get("year") or date_str)
    return {
        "name": "Damodaran US Implied ERP Reference",
        "series_id": "DAMODARAN_US_IMPLIED_ERP",
        "value": value,
        "unit": "percent",
        "date": data_date_out,
        "source_tier": SOURCE_TIER_OFFICIAL,
        "source_name": "Damodaran",
        "source_url": monthly_url if retrieval_method == "monthly_excel" else (annual_download_url if retrieval_method == "annual_excel_fallback" else html_url),
        "download_url": monthly_url if retrieval_method == "monthly_excel" else annual_download_url,
        "availability": "available",
        "notes": "美国市场 implied ERP 参考锚，不替代 NDX 自身估值或简式收益差距。",
        "data_quality": _quality_block(
            source_tier=SOURCE_TIER_OFFICIAL,
            data_date=data_date_out,
            update_frequency="monthly current ERP when ERPbymonth.xlsx is available; annual history fallback otherwise",
            formula="Damodaran US implied ERP model; monthly current ERP preferred, histimpl.xls annual history only as fallback",
            coverage={"scope": "US market/S&P 500 reference"},
            fallback_chain=[SOURCE_TIER_OFFICIAL, SOURCE_TIER_UNAVAILABLE],
        ),
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
            third_party_checks = get_ndx_valuation_third_party_checks()
            source_disagreement = {
                "component_model": {
                    "metric": "ndx_component_model_current_values",
                    "PE": metrics.get("weighted_trailing_pe"),
                    "ForwardPE": metrics.get("weighted_forward_pe"),
                    "FCFYield": metrics.get("weighted_fcf_yield"),
                    "source_tier": SOURCE_TIER_COMPONENT_MODEL,
                    "historical_percentile": None,
                    "note": "current component aggregate only; not a historical valuation percentile anchor",
                },
                **{
                item.get("source_id") or item.get("source"): {
                    "metric": item.get("metric"),
                    "value": item.get("value"),
                    "data_date": item.get("data_date"),
                    "percentile_10y": item.get("percentile_10y"),
                    "historical_percentile": item.get("historical_percentile"),
                    "source_tier": item.get("source_tier"),
                    "availability": item.get("availability"),
                    "unavailable_reason": item.get("unavailable_reason") or item.get("error"),
                }
                for item in third_party_checks
                }
            }
            data_quality = _quality_block(
                source_tier=SOURCE_TIER_COMPONENT_MODEL,
                data_date=effective_date.strftime("%Y-%m-%d"),
                update_frequency="latest component fundamentals; refreshed on collection",
                formula=(
                    "Trailing PE = covered market cap / covered trailing earnings; "
                    "Forward PE = covered market cap / covered forward earnings; "
                    "FCF yield = covered FCF / covered market cap"
                ),
                coverage=metrics.get("coverage", {}),
                anomalies=metrics.get("anomalies", []),
                fallback_chain=VALUATION_FALLBACK_CHAIN,
                source_disagreement=source_disagreement,
            )
            return {
                "name": "NDX P/E and Earnings Yield",
                "series_id": "NDX_WEIGHTED",
                "value": {
                    "PE": metrics.get('weighted_trailing_pe'),
                    "TrailingPE": metrics.get('weighted_trailing_pe'),
                    "ForwardPE": metrics.get('weighted_forward_pe'),
                    "EarningsYield": metrics.get('weighted_earnings_yield'),
                    "ForwardEarningsYield": metrics.get('weighted_forward_earnings_yield'),
                    "FCFYield": metrics.get('weighted_fcf_yield'),
                    "PriceToBook": metrics.get('weighted_price_to_book'),
                    "Coverage": {
                        "stocks_analyzed": stats['successful'],
                        "total_stocks": stats['total_tickers'],
                        "market_cap_coverage": f"{coverage_pct:.1f}%",
                        "metric_coverage": metrics.get("coverage", {}),
                        "failed_tickers": stats['failed_tickers'][:5] + ["..."] if len(stats['failed_tickers']) > 5 else stats['failed_tickers'],
                    },
                    "Anomalies": metrics.get("anomalies", []),
                    "ThirdPartyChecks": third_party_checks,
                },
                "unit": "ratio/percent",
                "date": effective_date.strftime("%Y-%m-%d"),
                "source_tier": SOURCE_TIER_COMPONENT_MODEL,
                "source_name": "yfinance (NDX100 Components)",
                "data_quality": data_quality,
                "notes": f"市值加权计算，覆盖{coverage_pct:.1f}%的NDX成分股"
            }
        except Exception as e:
            print(f"yfinance计算NDX基本面失败：{str(e)[:50]}，尝试Alpha Vantage备用方案")
            return get_ndx_pe_and_earnings_yield_av(end_date=effective_date.strftime("%Y-%m-%d"))
    else:
        # yfinance不可用时直接降级到Alpha Vantage
        return get_ndx_pe_and_earnings_yield_av(end_date=effective_date.strftime("%Y-%m-%d"))


def get_equity_risk_premium(end_date: str = None) -> Dict[str, Any]:
    """计算NDX简式收益差距：收益率 - 10Y，美股implied ERP另列参考。"""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    date_str = effective_date.strftime("%Y-%m-%d")

    # 获取NDX收益率数据
    ndx_data = get_ndx_pe_and_earnings_yield(end_date=date_str)
    if not ndx_data.get("value"):
        return {
            "name": "NDX Simple Yield Gap",
            "value": None,
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "notes": "无法获取NDX收益率数据，计算失败"
        }

    # 优先使用FCF收益率，其次用盈利收益率
    yield_to_use = None
    yield_type = None
    ndx_value = ndx_data["value"]

    if ndx_value.get("FCFYield") is not None:
        yield_to_use = ndx_value["FCFYield"]
        yield_type = "fcf_yield"
    elif ndx_value.get("EarningsYield") is not None:
        yield_to_use = ndx_value["EarningsYield"]
        yield_type = "earnings_yield"
    else:
        return {
            "name": "NDX Simple Yield Gap",
            "value": None,
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "notes": "NDX无有效收益率数据（FCF/盈利）"
        }

    # 获取10年期美债收益率（无风险利率）
    if get_10y_treasury is None:
        treasury_data = {"value": None}
    else:
        treasury_data = get_10y_treasury(end_date=date_str)
    treasury_yield = treasury_data.get("value", {}).get("level")
    if treasury_yield is None:
        return {
            "name": "NDX Simple Yield Gap",
            "value": None,
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "notes": "无法获取10年期美债收益率（无风险利率）"
        }

    gap = round(yield_to_use - treasury_yield, 2)
    method = f"{yield_type}_minus_10y"
    formula = "NDX FCF yield - 10Y Treasury yield" if yield_type == "fcf_yield" else "NDX earnings yield - 10Y Treasury yield"
    source_tier = ndx_data.get("source_tier") or ndx_data.get("data_quality", {}).get("source_tier") or SOURCE_TIER_COMPONENT_MODEL
    data_quality = _quality_block(
        source_tier=source_tier,
        data_date=date_str,
        update_frequency="daily when NDX valuation and Treasury sources update",
        formula=formula,
        coverage=ndx_data.get("data_quality", {}).get("coverage", ndx_value.get("Coverage", {})),
        anomalies=ndx_data.get("data_quality", {}).get("anomalies", []),
        fallback_chain=[source_tier, SOURCE_TIER_OFFICIAL, SOURCE_TIER_UNAVAILABLE],
        source_disagreement=ndx_data.get("data_quality", {}).get("source_disagreement", {}),
    )
    return {
        "name": "NDX Simple Yield Gap",
        "series_id": "SIMPLE_YIELD_GAP",
        "value": {
            "level": gap,
            "date": date_str,
            "method": method,
            "yield_type": yield_type,
            "components": {
                f"NDX {yield_type}": f"{yield_to_use}%",
                "10Y Treasury Yield (Risk-Free)": f"{treasury_yield}%"
            },
            "not_implied_erp_warning": "This is a simple yield gap, not Damodaran-style implied ERP.",
            "damodaran_reference": {
                "function_id": "get_damodaran_us_implied_erp",
                "scope": "US equity market reference, not NDX-specific",
            },
        },
        "unit": "percent",
        "source_tier": SOURCE_TIER_COMPONENT_MODEL,
        "source_name": "Calculated simple yield gap (NDX valuation + 10Y Treasury)",
        "data_quality": data_quality,
        "notes": "该指标只衡量当前盈利/现金流收益率相对10年期美债的简式差距，未包含未来增长、回购、现金流路径或终值假设，不能当作 Damodaran 式 implied ERP。"
    }

# =====================================================
# 第五层：技术指标（*本轮修改部分*）
# =====================================================
