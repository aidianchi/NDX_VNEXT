#!/usr/bin/env python3
"""U1 experiment: generate P1/P2/P3 perturbed copies of the live data snapshot.

Reads output/data/data_collected_v9_live.json (repo, unmodified) and writes
three perturbed JSON files into the scratchpad. Does NOT touch repo source
or the original snapshot file.
"""
import copy
import json
import os

SRC = "/Users/aidianchi/Desktop/ndx_mac/output/data/data_collected_v9_live.json"
OUT_DIR = "/private/tmp/claude-501/-Users-aidianchi-Desktop-ndx-mac/ec3f7bdb-c397-485c-951a-eddb816350b9/scratchpad/u1"


def load():
    with open(SRC, "r", encoding="utf-8") as f:
        return json.load(f)


def indicators_by_id(data):
    return {item["function_id"]: item for item in data["indicators"]}


def p1_valuation_reversal(data):
    """L4: flip PE percentile from high (81.4%ile 10y) to low (~22%ile),
    scale PE/PB/PS values down consistently ("expensive" -> "cheap")."""
    d = copy.deepcopy(data)
    inds = indicators_by_id(d)

    scale = 22.5 / 35.88  # new_PE / old_PE ~ 0.6272

    v = inds["get_ndx_wind_valuation_snapshot"]["raw_data"]["value"]
    old_pe = v["PE"]
    v["PE"] = round(old_pe * scale, 2)          # 35.88 -> 22.50
    v["PB"] = round(v["PB"] * scale, 2)          # 10.53 -> 6.60
    v["PS"] = round(v["PS"] * scale, 2)          # 7.64 -> 4.79
    v["PEHistoricalPercentile"] = 22.0           # 81.42 -> 22.0 (10y, matches window below)
    for window, pct in [("1y", 18.0), ("2y", 20.0), ("5y", 24.0), ("10y", 22.0)]:
        w = v["PEPercentileWindows"][window]
        w["percentile"] = pct
        # keep rank internally consistent-ish (lower rank among sample = cheaper)
        if isinstance(w.get("sample_count"), (int, float)) and w["sample_count"]:
            w["rank"] = int(round(w["sample_count"] * pct / 100.0))
    # RiskPremium should rise (cheaper valuation -> fatter compensation)
    old_rp = v["RiskPremium"]
    v["RiskPremium"] = round(old_rp * 1.6, 4)
    if isinstance(v.get("RiskPremiumPercentileWindows", {}).get("1y"), dict):
        v["RiskPremiumPercentileWindows"]["1y"]["percentile"] = 82.0

    v2 = inds["get_ndx_pe_and_earnings_yield"]["raw_data"]["value"]
    old_pe2 = v2["PE"]
    scale2 = 21.0 / old_pe2 if old_pe2 else 1.0
    v2["PE"] = 21.0
    v2["TrailingPE"] = 21.0
    v2["EarningsYield"] = round(v2["EarningsYield"] * (old_pe2 / 21.0), 2)
    # keep the third-party cross-check roughly aligned so DataIntegrity's
    # source-disagreement note (if ever recomputed) would not itself become
    # the story; this experiment is about LLM sensitivity, not triggering a
    # data-quality artifact.
    for check in v2.get("ThirdPartyChecks", []):
        if check.get("value") is not None:
            check["value"] = round(check["value"] * scale2, 2)

    return d, {
        "get_ndx_wind_valuation_snapshot.value.PE": (old_pe, v["PE"]),
        "get_ndx_wind_valuation_snapshot.value.PB": "scaled by same factor",
        "get_ndx_wind_valuation_snapshot.value.PS": "scaled by same factor",
        "get_ndx_wind_valuation_snapshot.value.PEHistoricalPercentile": (81.42, 22.0),
        "get_ndx_wind_valuation_snapshot.value.PEPercentileWindows": "1y/2y/5y/10y all lowered to 18-24",
        "get_ndx_wind_valuation_snapshot.value.RiskPremium": (old_rp, v["RiskPremium"]),
        "get_ndx_pe_and_earnings_yield.value.PE/TrailingPE": (old_pe2, 21.0),
        "get_ndx_pe_and_earnings_yield.value.EarningsYield": "raised inversely with PE",
        "get_ndx_pe_and_earnings_yield.value.ThirdPartyChecks[*].value": "scaled to stay consistent with new PE",
    }


def p2_breadth_reversal(data):
    """L3: flip breadth from the live baseline (broadly healthy: ADL rising,
    >55%/>62% above 50d/200d MA, net new highs positive, McClellan +0.48,
    NDX/NDXE concentration extreme) to broadly weak (ADL falling, minority
    above MAs, net new lows, McClellan deeply negative, concentration eased)."""
    d = copy.deepcopy(data)
    inds = indicators_by_id(d)

    adl = inds["get_advance_decline_line"]["raw_data"]["value"]
    adl["trend"] = "falling"
    adl["distance_from_ma20_pct"] = -10.59
    adl["level"] = int(round(adl["ma20"] * (1 - 0.1059)))

    pam = inds["get_percent_above_ma"]["raw_data"]["value"]
    pam["level"]["percent_above_50d"] = 24.0
    pam["level"]["percent_above_200d"] = 29.0

    nhl = inds["get_new_highs_lows"]["raw_data"]["value"]
    nhl["level"]["new_highs_52w"] = 0
    nhl["level"]["new_lows_52w"] = 38
    nhl["level"]["net_new_highs"] = -38
    nhl["level"]["percent_new_highs"] = 0.0
    nhl["level"]["percent_new_lows"] = 37.6
    nhl["momentum"] = "negative"

    mccl = inds["get_mcclellan_oscillator_nasdaq_or_nyse"]["raw_data"]["value"]
    mccl["level"] = -38.5
    mccl["momentum"] = "negative"

    ratio = inds["get_ndx_ndxe_ratio"]["raw_data"]["value"]
    # baseline: extreme cap-weighted-vs-equal-weighted concentration
    # (percentile_10y 96.5%, near record narrow leadership); reverse to
    # unconcentrated / broadening leadership.
    ratio["relativity"]["percentile_5y"] = 0.08
    ratio["relativity"]["percentile_10y"] = 0.10
    ratio["relativity"]["z_score_10y"] = -1.55
    ratio["ratio_trend_vs_ma20"] = "above"
    old_level = ratio["level"]
    ratio["level"] = round(old_level * 0.90, 4)
    ratio["ratio_ma20"] = round(ratio["ratio_ma20"] * 0.88, 4)

    return d, {
        "get_advance_decline_line.value.trend": ("rising", "falling"),
        "get_advance_decline_line.value.distance_from_ma20_pct": (10.59, -10.59),
        "get_percent_above_ma.value.percent_above_50d": (55.45, 24.0),
        "get_percent_above_ma.value.percent_above_200d": (62.38, 29.0),
        "get_new_highs_lows.value": ("4 new highs / 0 new lows", "0 new highs / 38 new lows"),
        "get_mcclellan_oscillator_nasdaq_or_nyse.value.level": (0.48, -38.5),
        "get_ndx_ndxe_ratio.value.relativity.percentile_10y": (0.9654, 0.10),
    }


def p3_liquidity_reversal(data):
    """L1: flip macro stance from tight/restrictive (contracting net
    liquidity momentum, high real/nominal rates near multi-year highs) to
    loose/accommodative (expanding net liquidity, much lower rates)."""
    d = copy.deepcopy(data)
    inds = indicators_by_id(d)

    nl = inds["get_net_liquidity_momentum"]["raw_data"]["value"]
    nl["momentum_4w"] = 19.93
    nl["level"] = 6200.0
    nl["historical_stats"]["percentile_5y"] = 0.75
    nl["historical_stats"]["percentile_10y"] = 0.80
    nl["historical_stats"]["z_score_10y"] = 1.1

    ffr = inds["get_fed_funds_rate"]["raw_data"]["value"]
    ffr["level"] = 1.5
    ffr["momentum"]["direction"] = "falling"
    ffr["momentum"]["velocity_1d"] = -0.02
    ffr["relativity"]["percentile_1y"] = 15.0
    ffr["relativity"]["percentile_10y"] = 15.0

    t10 = inds["get_10y_treasury"]["raw_data"]["value"]
    t10["level"] = 2.8
    t10["ma"] = 2.95
    t10["deviation_pct"] = round((2.8 - 2.95) / 2.95 * 100, 2)
    t10["position_vs_ma"] = "below"
    t10["relativity"]["percentile_5y"] = 0.18
    t10["relativity"]["percentile_10y"] = 0.20
    t10["relativity"]["z_score_10y"] = -1.2

    rr = inds["get_10y_real_rate"]["raw_data"]["value"]
    rr["level"] = 0.3
    rr["ma"] = 0.45
    rr["deviation_pct"] = round((0.3 - 0.45) / 0.45 * 100, 2)
    rr["position_vs_ma"] = "below"
    rr["relativity"]["percentile_5y"] = 0.08
    rr["relativity"]["percentile_10y"] = 0.10
    rr["relativity"]["z_score_10y"] = -1.4

    be = inds["get_10y_breakeven"]["raw_data"]["value"]
    be["level"] = 2.5  # keeps 10y_treasury(2.8) - breakeven(2.5) = real_rate(0.3) internally consistent

    spread = inds["get_10y2y_spread_bp"]["raw_data"]["value"]
    spread["level"] = 150.0
    spread["ma"] = 130.0
    spread["deviation_pct"] = round((150.0 - 130.0) / 130.0 * 100, 2)
    spread["position_vs_ma"] = "above"
    spread["relativity"]["percentile_5y"] = 0.85
    spread["relativity"]["percentile_10y"] = 0.80

    m2 = inds["get_m2_yoy"]["raw_data"]["value"]
    m2["level"] = 9.5
    m2["relativity"]["percentile_1y"] = 85.0
    m2["relativity"]["percentile_10y"] = 85.0

    return d, {
        "get_net_liquidity_momentum.value.momentum_4w": (-19.93, 19.93),
        "get_net_liquidity_momentum.value.level": (5955.78, 6200.0),
        "get_fed_funds_rate.value.level": (3.63, 1.5),
        "get_10y_treasury.value.level": (4.56, 2.8),
        "get_10y_real_rate.value.level": (2.31, 0.3),
        "get_10y_breakeven.value.level": (2.23, 2.5),
        "get_10y2y_spread_bp.value.level": (38.0, 150.0),
        "get_m2_yoy.value.level": (5.58, 9.5),
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    data = load()

    change_log = {}
    for name, fn in [
        ("p1_valuation_reversal", p1_valuation_reversal),
        ("p2_breadth_reversal", p2_breadth_reversal),
        ("p3_liquidity_reversal", p3_liquidity_reversal),
    ]:
        perturbed, changes = fn(data)
        out_path = os.path.join(OUT_DIR, f"data_{name.split('_')[0]}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(perturbed, f, ensure_ascii=False, indent=2)
        change_log[name] = {"output": out_path, "changes": changes}
        print(f"wrote {out_path}")

    with open(os.path.join(OUT_DIR, "change_log.json"), "w", encoding="utf-8") as f:
        json.dump(change_log, f, ensure_ascii=False, indent=2, default=str)
    print("wrote change_log.json")


if __name__ == "__main__":
    main()
