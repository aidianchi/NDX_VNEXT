import os
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L1 as l1
from data_evidence import REQUIRED_DATA_QUALITY_FIELDS


END_DATE = "2026-07-10"


def _contract_map(end_date=END_DATE):
    anchor = datetime.strptime(end_date, "%Y-%m-%d")
    result = {}
    for months_ahead in range(13):
        year, month = l1._fed_funds_month_at_offset(anchor, months_ahead)
        result[months_ahead] = l1._fed_funds_contract_for_month(year, month)
    return result


def _daily_frame(close, volume, end_date=END_DATE, future_close=None):
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = [end - timedelta(days=offset) for offset in range(9, -1, -1)]
    closes = [close] * 10
    volumes = [volume] * 10
    if future_close is not None:
        dates.append(end + timedelta(days=1))
        closes.append(future_close)
        volumes.append(volume)
    return pd.DataFrame({"Close": closes, "Volume": volumes}, index=pd.DatetimeIndex(dates, name="Date"))


def _install_mocks(
    monkeypatch,
    *,
    close_by_offset=None,
    volume_by_offset=None,
    present_offsets=None,
    effr=4.0,
    future_close_by_offset=None,
    end_date=END_DATE,
):
    contracts = _contract_map(end_date)
    close_by_offset = close_by_offset or {offset: 96.0 - offset * 0.01 for offset in range(13)}
    volume_by_offset = volume_by_offset or {offset: 1000.0 for offset in range(13)}
    present_offsets = set(range(13)) if present_offsets is None else set(present_offsets)
    future_close_by_offset = future_close_by_offset or {}
    frames = {
        contract: _daily_frame(
            close_by_offset[offset],
            volume_by_offset[offset],
            end_date=end_date,
            future_close=future_close_by_offset.get(offset),
        )
        for offset, contract in contracts.items()
        if offset in present_offsets
    }

    def fake_download(ticker, **_kwargs):
        frame = frames.get(ticker)
        return frame.copy() if frame is not None else pd.DataFrame()

    def fake_fred(series_id, days=60, end_date=None):
        if effr is None:
            return None
        assert series_id == "EFFR"
        return pd.DataFrame({"date": [pd.Timestamp(end_date or END_DATE)], "value": [effr]})

    monkeypatch.setattr(l1, "cached_yf_download", fake_download)
    monkeypatch.setattr(l1, "get_fred_series", fake_fred)
    return contracts


def test_state_classification_buffer_boundaries_are_explicit():
    assert l1._fed_funds_path_state(-0.125) == "easing_priced"
    assert l1._fed_funds_path_state(-0.1249) == "flat_path"
    assert l1._fed_funds_path_state(0.1249) == "flat_path"
    assert l1._fed_funds_path_state(0.125) == "tightening_priced"


def test_negligible_far_month_is_excluded_and_horizon_is_truthful(monkeypatch):
    closes = {offset: 96.0 + offset * 0.05 for offset in range(13)}
    volumes = {offset: 1000.0 for offset in range(13)}
    volumes[12] = 1.0
    contracts = _install_mocks(monkeypatch, close_by_offset=closes, volume_by_offset=volumes)

    result = l1.get_fed_funds_rate_path(END_DATE)
    value = result["value"]

    assert value["status"] == "available"
    assert contracts[12] not in {item["contract"] for item in value["path"]}
    assert value["horizon_used"]["actual_months_ahead"] == 11
    assert value["horizon_used"]["fallback_used"] is True
    assert value["slope_12m"] == -0.55
    assert value["cuts_priced_bps"] == 55
    raw_far = next(item for item in value["raw_series"] if item["months_ahead"] == 12)
    assert raw_far["liquidity_tier"] == "negligible"
    assert raw_far["included_in_path"] is False


def test_negligible_front_month_reports_actual_curve_span(monkeypatch):
    volumes = {offset: 1000.0 for offset in range(13)}
    volumes[0] = 1.0
    _install_mocks(monkeypatch, volume_by_offset=volumes)

    result = l1.get_fed_funds_rate_path(END_DATE)
    horizon = result["value"]["horizon_used"]

    assert result["value"]["front_month"]["months_ahead"] == 1
    assert horizon["front_months_ahead"] == 1
    assert horizon["far_months_ahead"] == 12
    assert horizon["actual_months_ahead"] == 11
    assert horizon["fallback_used"] is True


def test_point_in_time_cutoff_never_uses_rows_after_end_date(monkeypatch):
    contracts = _install_mocks(monkeypatch, future_close_by_offset={0: 90.0})

    result = l1.get_fed_funds_rate_path(END_DATE)
    front = result["value"]["front_month"]
    raw_front = next(item for item in result["value"]["raw_series"] if item["contract"] == contracts[0])

    assert front["close"] == 96.0
    assert front["implied_rate"] == 4.0
    assert all(row["data_date"] <= END_DATE for row in raw_front["observations"])
    assert all(row["close"] != 90.0 for row in raw_front["observations"])


def test_large_contract_gap_degrades_to_insufficient_curve_without_crashing(monkeypatch):
    _install_mocks(monkeypatch, present_offsets={0, 1, 2})

    result = l1.get_fed_funds_rate_path(END_DATE)
    value = result["value"]

    assert result["availability"] == "available"
    assert result["data_quality"]["availability"] == "available"
    assert value["status"] == "insufficient_curve"
    assert len(value["path"]) == 3
    assert value["slope_12m"] is None
    assert value["cuts_priced_bps"] is None
    assert value["state"] is None
    assert result["data_quality"]["fallback_reason"] == "fewer_than_four_non_negligible_contract_months"


def test_effr_anchor_gap_over_threshold_is_anomaly_not_blocker(monkeypatch):
    closes = {offset: 95.0 for offset in range(13)}
    _install_mocks(monkeypatch, close_by_offset=closes, effr=4.0)

    result = l1.get_fed_funds_rate_path(END_DATE)
    value = result["value"]

    assert value["effr_anchor"]["front_month_minus_anchor_pp"] == 1.0
    assert any("gap_gt_0.35pp" in anomaly for anomaly in result["data_quality"]["anomalies"])
    assert result["availability"] == "available"
    assert value["status"] == "available"


def test_malformed_fred_anchor_never_blocks_valid_futures_curve(monkeypatch):
    _install_mocks(monkeypatch)
    monkeypatch.setattr(l1, "get_fred_series", lambda *_args, **_kwargs: pd.DataFrame({"bad": [1]}))

    result = l1.get_fed_funds_rate_path(END_DATE)

    assert result["availability"] == "available"
    assert result["value"]["status"] == "available"
    assert result["value"]["effr_anchor"] is None
    assert "effr_anchor_unavailable_non_blocking" in result["data_quality"]["anomalies"]


def test_end_to_end_evidence_contract_and_metric_authority(monkeypatch):
    _install_mocks(monkeypatch)

    result = l1.get_fed_funds_rate_path(END_DATE)
    quality = result["data_quality"]

    assert result["source_tier"] == "third_party_unofficial"
    assert REQUIRED_DATA_QUALITY_FIELDS.issubset(quality)
    assert quality["availability"] == "available"
    assert quality["point_in_time_note"]
    assert set(quality["metric_authority"]) >= {
        "path_0_6m",
        "path_7_12m",
        "state",
        "slope_12m_and_cuts_priced_bps",
        "effr_anchor",
    }
    assert quality["metric_authority"]["path_7_12m"]["authority"] == "low_liquidity_far_month"
    assert quality["metric_authority"]["state"]["usage"] == "supporting_only"
