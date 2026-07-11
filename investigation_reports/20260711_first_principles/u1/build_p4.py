#!/usr/bin/env python3
"""U1 stage 2: build data_p4.json — textbook-bullish world, internally consistent.

Composition: p1 (valuation cheap) -> p3 (liquidity easy) -> breadth healthy +
stage-1 consistency fixes (Danjuan percentile, simple yield gap positive,
Damodaran ERP ample, concentration normalized).
"""
import copy
import json
import os
import sys

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, OUT_DIR)
from perturb_snapshot import load, indicators_by_id, p1_valuation_reversal, p3_liquidity_reversal  # noqa: E402


def apply_p4_extras(data):
    d = copy.deepcopy(data)
    inds = indicators_by_id(d)
    changes = {}

    # --- fix stage-1 miss: Danjuan third-party percentile must agree with "cheap" ---
    tpc = inds["get_ndx_pe_and_earnings_yield"]["raw_data"]["value"].get("ThirdPartyChecks", [])
    for check in tpc:
        if check.get("historical_percentile") is not None:
            changes[f"ThirdPartyChecks[{check.get('source')}].historical_percentile"] = (
                check["historical_percentile"], 21.0)
            check["historical_percentile"] = 21.0

    # --- simple yield gap turns positive, consistent with Wind PE 22.5 and 10Y 2.8 ---
    erp = inds["get_equity_risk_premium"]["raw_data"]["value"]
    changes["get_equity_risk_premium.level"] = (erp.get("level"), 1.64)
    erp["level"] = 1.64
    comps = erp.get("components")
    if isinstance(comps, dict):
        for key in list(comps.keys()):
            if "earnings_yield" in key or "Earnings" in key:
                comps[key] = "4.4444%"
            if "10Y" in key or "Risk-Free" in key:
                comps[key] = "2.8%"

    # --- Damodaran implied ERP ample (75th-ish percentile territory) ---
    dam = inds["get_damodaran_us_implied_erp"]["raw_data"]["value"]
    changes["damodaran.erp_t12m_adjusted_payout"] = (dam.get("erp_t12m_adjusted_payout"), 6.0)
    dam["erp_t12m_adjusted_payout"] = 6.0
    dam["erp_t12m_cash_yield"] = 5.8
    dam["us_10y_treasury_rate"] = 2.8
    dam["adjusted_riskfree_rate"] = 2.7
    dam["expected_return"] = 8.7
    series = dam.get("monthly_series") or []
    if series and isinstance(series[-1], dict):
        series[-1]["erp_t12m_adjusted_payout"] = 6.0
        series[-1]["erp_t12m_cash_yield"] = 5.8
        series[-1]["us_10y_treasury_rate"] = 2.8

    # --- breadth uniformly healthy ---
    pam = inds["get_percent_above_ma"]["raw_data"]["value"]
    changes["percent_above_50d/200d"] = (
        (pam["level"]["percent_above_50d"], pam["level"]["percent_above_200d"]), (70.0, 75.0))
    pam["level"]["percent_above_50d"] = 70.0
    pam["level"]["percent_above_200d"] = 75.0

    nhl = inds["get_new_highs_lows"]["raw_data"]["value"]
    changes["new_highs/new_lows"] = (
        (nhl["level"].get("new_highs_52w"), nhl["level"].get("new_lows_52w")), (30, 0))
    nhl["level"]["new_highs_52w"] = 30
    nhl["level"]["new_lows_52w"] = 0
    nhl["level"]["net_new_highs"] = 30
    nhl["level"]["percent_new_highs"] = 29.7
    nhl["level"]["percent_new_lows"] = 0.0
    nhl["momentum"] = "positive"

    mccl = inds["get_mcclellan_oscillator_nasdaq_or_nyse"]["raw_data"]["value"]
    changes["mcclellan.level"] = (mccl.get("level"), 25.0)
    mccl["level"] = 25.0
    mccl["momentum"] = "positive"

    # A/D already rising in baseline; keep as-is (healthy).

    # --- concentration normalized ---
    ratio = inds["get_ndx_ndxe_ratio"]["raw_data"]["value"]
    changes["ndx_ndxe.percentile_10y"] = (ratio["relativity"].get("percentile_10y"), 0.45)
    ratio["relativity"]["percentile_5y"] = 0.40
    ratio["relativity"]["percentile_10y"] = 0.45
    ratio["relativity"]["z_score_10y"] = 0.1
    ratio["level"] = round(ratio["level"] * 0.93, 4)
    ratio["ratio_ma20"] = round(ratio["ratio_ma20"] * 0.925, 4)

    top10 = inds.get("get_qqq_top10_concentration", {}).get("raw_data", {}).get("value")
    if isinstance(top10, dict):
        for key in ("top10_weight_pct", "level", "top10_weight"):
            if isinstance(top10.get(key), (int, float)):
                changes[f"top10.{key}"] = (top10[key], 38.0)
                top10[key] = 38.0
                break

    return d, changes


def main():
    data = load()
    d1, log1 = p1_valuation_reversal(data)
    d13, log3 = p3_liquidity_reversal(d1)
    d4, log4 = apply_p4_extras(d13)

    out_path = os.path.join(OUT_DIR, "data_p4.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(d4, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "change_log_p4.json"), "w", encoding="utf-8") as f:
        json.dump({"p1_reused": log1, "p3_reused": log3, "p4_extras": log4},
                  f, ensure_ascii=False, indent=2, default=str)
    print(f"wrote {out_path}")
    print(json.dumps(log4, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
