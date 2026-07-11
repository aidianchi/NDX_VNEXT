#!/usr/bin/env python3
"""U1 P5: data_p4 + L2 credit/sentiment turned benign-normal (not euphoric).

Removes the last remaining bearish axes: CCC-BB quality spread (was 99.87%ile
widening), elevated VXN/VXN-VIX ratio, defensive put/call. Target world:
zero extreme bearish signals, and no extreme-greed contrarian signal either.
"""
import copy
import json
import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_p4.json")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_p5.json")


def main():
    with open(BASE, "r", encoding="utf-8") as f:
        data = json.load(f)
    d = copy.deepcopy(data)
    inds = {i["function_id"]: i for i in d["indicators"]}
    changes = {}

    q = inds["get_hy_quality_spread_bp"]["raw_data"]["value"]
    changes["hy_quality_spread"] = (
        {"level": q["level"], "trend": q["trend"], "pct10y": q["relativity"]["percentile_10y"]},
        {"level": 4.0, "trend": "short_below_long", "pct10y": 0.30})
    q["level"] = 4.0
    q["short_ma"] = 4.05
    q["long_ma"] = 4.20
    q["trend"] = "short_below_long"
    q["ccc_oas"] = 5.0
    q["bb_oas"] = 1.0
    q["relativity"]["percentile_5y"] = 0.30
    q["relativity"]["percentile_10y"] = 0.30
    q["relativity"]["z_score_10y"] = -0.4

    vxn = inds["get_vxn"]["raw_data"]["value"]
    changes["vxn"] = (vxn["level"], 20.0)
    vxn["level"] = 20.0
    vxn["ma20"] = 21.0
    vxn["spot_over_ma20_ratio"] = round(20.0 / 21.0, 4)
    vxn["historical_stats"]["percentile_5y"] = 0.38
    vxn["historical_stats"]["percentile_10y"] = 0.40
    vxn["historical_stats"]["z_score_10y"] = -0.2

    ratio = inds["get_vxn_vix_ratio"]["raw_data"]["value"]
    changes["vxn_vix_ratio"] = (ratio["level"], 1.30)
    ratio["level"] = 1.30

    crowd = inds["get_crowdedness_dashboard"]["raw_data"]["value"]
    if isinstance(crowd.get("skew_index"), dict):
        changes["skew"] = (crowd["skew_index"]["value"], 130.0)
        crowd["skew_index"]["value"] = 130.0
    if isinstance(crowd.get("qqq_put_call_ratio_oi"), dict):
        changes["put_call"] = (crowd["qqq_put_call_ratio_oi"]["value"], 1.0)
        crowd["qqq_put_call_ratio_oi"]["value"] = 1.0

    fg = inds["get_cnn_fear_greed_index"]["raw_data"]["value"]
    changes["fear_greed"] = (fg["score"], 60.0)
    fg["score"] = 60.0
    fg["rating"] = "greed"

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    with open(os.path.join(os.path.dirname(OUT), "change_log_p5.json"), "w", encoding="utf-8") as f:
        json.dump(changes, f, ensure_ascii=False, indent=2, default=str)
    print("wrote", OUT)
    print(json.dumps(changes, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
