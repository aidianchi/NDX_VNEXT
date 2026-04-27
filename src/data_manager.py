import os
from datetime import datetime, timedelta
from typing import Callable, Optional, Union

import numpy as np
import pandas as pd
from scipy import stats
try:
    from .config import path_config
except ImportError:
    from config import path_config

DateLike = Union[str, datetime]


class TimeSeriesManager:
    """
    时间序列管理器，负责本地 CSV 缓存的读取与增量更新。
    所有日期列统一转换为 pandas datetime64[ns]。
    """

    def __init__(self, cache_dir: str = path_config.cache_dir) -> None:
        self.cache_dir = cache_dir
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)

    def _series_path(self, series_id: str) -> str:
        return os.path.join(self.cache_dir, f"{series_id}.csv")

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None:
            return pd.DataFrame()
        # 复制以避免修改上游数据
        df = df.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        else:
            # 若缺少 date 列，创建空日期列以保持接口一致性
            df["date"] = pd.NaT
        return df

    def get_or_update_series(
        self,
        series_id: str,
        update_func: Callable[[Optional[DateLike]], pd.DataFrame],
        *,
        date_col: str = "date",
    ) -> pd.DataFrame:
        """
        获取或增量更新指定时间序列。
        - update_func 必须接受 start_date 参数（str 或 datetime），返回包含 date 列的 DataFrame。
        """
        path = self._series_path(series_id)
        local_df = self._read_local(path, date_col=date_col)
        local_df = self._normalize_df(local_df)

        # 冷启动：无本地文件或为空
        if local_df.empty:
            try:
                new_df = update_func(start_date=None)
            except Exception as exc:  # noqa: BLE001
                print(f"[TimeSeriesManager] 初始化拉取失败: {exc}")
                return local_df
        else:
            last_date = local_df[date_col].max()
            if pd.isna(last_date):
                start_date = None
            else:
                start_date = (last_date + timedelta(days=1)).date()
            try:
                new_df = update_func(start_date=start_date)
            except Exception as exc:  # noqa: BLE001
                print(f"[TimeSeriesManager] 增量更新失败，返回本地缓存: {exc}")
                return local_df

        new_df = self._normalize_df(new_df)
        merged = self._merge_and_clean(local_df, new_df, date_col=date_col)
        self._write_local(path, merged)
        return merged

    @staticmethod
    def _merge_and_clean(
        old_df: pd.DataFrame, new_df: pd.DataFrame, *, date_col: str
    ) -> pd.DataFrame:
        if old_df is None:
            old_df = pd.DataFrame()
        if new_df is None:
            new_df = pd.DataFrame()

        combined = pd.concat([old_df, new_df], ignore_index=True)
        if combined.empty:
            return combined

        # 去重并按日期排序
        combined = combined.drop_duplicates(subset=[date_col])
        combined = combined.sort_values(by=date_col)
        combined.reset_index(drop=True, inplace=True)
        return combined

    def _read_local(self, path: str, *, date_col: str) -> pd.DataFrame:
        if not os.path.exists(path):
            return pd.DataFrame()
        try:
            df = pd.read_csv(path)
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col])
            return df
        except Exception as exc:  # noqa: BLE001
            print(f"[TimeSeriesManager] 读取本地文件失败: {exc}")
            return pd.DataFrame()

    def _write_local(self, path: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        try:
            df.to_csv(path, index=False)
        except Exception as exc:  # noqa: BLE001
            print(f"[TimeSeriesManager] 写入本地文件失败: {exc}")


def calculate_long_term_stats(df: pd.DataFrame, current_value: float) -> dict:
    """
    计算长期分位与 Z 分数。
    - 输入 DataFrame 需包含 date 列与 value 列。
    - current_value 为当前最新值，用于相对定位。
    """
    if df is None or df.empty or current_value is None or np.isnan(current_value):
        return {
            "percentile_5y": np.nan,
            "percentile_10y": np.nan,
            "z_score_10y": np.nan,
        }

    df = df.copy()
    if "date" not in df.columns or "value" not in df.columns:
        raise ValueError("DataFrame 必须包含 'date' 和 'value' 列。")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    now = pd.Timestamp(datetime.now().date())
    window_5y = now - pd.DateOffset(years=5)
    window_10y = now - pd.DateOffset(years=10)

    df_5y = df[df["date"] >= window_5y]
    df_10y = df[df["date"] >= window_10y]

    def _percentile(series: pd.Series, value: float) -> float:
        clean = series.dropna()
        if clean.empty:
            return np.nan
        return float(np.sum(clean <= value) / len(clean))

    percentile_5y = _percentile(df_5y["value"], current_value)
    percentile_10y = _percentile(df_10y["value"], current_value)

    z_score_10y = np.nan
    clean_10y = df_10y["value"].dropna()
    if clean_10y.shape[0] >= 2:
        z = stats.zscore(clean_10y.to_numpy(), nan_policy="omit")
        # 将当前值按同样均值方差计算
        mean_10y = clean_10y.mean()
        std_10y = clean_10y.std(ddof=0)
        if std_10y > 0:
            z_score_10y = float((current_value - mean_10y) / std_10y)
        else:
            z_score_10y = 0.0 if not np.isnan(current_value) else np.nan

    return {
        "percentile_5y": percentile_5y,
        "percentile_10y": percentile_10y,
        "z_score_10y": z_score_10y,
    }


def align_and_calculate_ratio(
    numerator_series: pd.DataFrame,
    denominator_series: pd.DataFrame,
    *,
    date_col: str = "date",
    value_col: str = "value",
) -> pd.DataFrame:
    """
    频率对齐后计算比率，防止前视偏差。
    - 分子通常为日频，分母可能为周/月频。
    - 采用 merge_asof(direction='backward') 或前向填充，禁止使用未来值。
    返回包含 date、numerator、denominator、ratio 四列的 DataFrame。
    """
    num = numerator_series.copy() if numerator_series is not None else pd.DataFrame()
    denom = (
        denominator_series.copy() if denominator_series is not None else pd.DataFrame()
    )

    if num.empty or denom.empty:
        return pd.DataFrame(columns=[date_col, "numerator", "denominator", "ratio"])

    for df in (num, denom):
        if date_col not in df.columns or value_col not in df.columns:
            raise ValueError("输入 DataFrame 必须包含 date 与 value 列。")
        df[date_col] = pd.to_datetime(df[date_col])
        df.sort_values(date_col, inplace=True)

    aligned = pd.merge_asof(
        num[[date_col, value_col]],
        denom[[date_col, value_col]].rename(columns={value_col: "denominator"}),
        on=date_col,
        direction="backward",  # 避免前视偏差
    )
    aligned.rename(columns={value_col: "numerator"}, inplace=True)

    # 若分母存在缺口，使用历史值前向填充，仍避免使用未来信息
    aligned["denominator"] = aligned["denominator"].ffill()

    aligned["ratio"] = aligned["numerator"] / aligned["denominator"]
    aligned = aligned[[date_col, "numerator", "denominator", "ratio"]]
    aligned.replace([np.inf, -np.inf], np.nan, inplace=True)
    aligned.dropna(subset=["numerator", "denominator"], inplace=True)
    aligned.reset_index(drop=True, inplace=True)
    return aligned

