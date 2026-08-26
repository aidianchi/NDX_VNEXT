#!/usr/bin/env python3
"""T67/W3 · 第二层成熟度五项度量基线测量器。

只读现有落盘产物，零 AI 调用。五项度量定义见系统说明书 2.10 末段：
  ① 全文率          ② 来源等级分布      ③ 主张-原文对账通过率
  ④ 渠道真空核查覆盖率  ⑤ IA 引用可用率

产物：
  investigation_reports/20260826_第三层治理施工工单/baseline_measurements.json
  investigation_reports/20260826_第三层治理施工工单/baseline_measurements.md

诚实原则：某项在现有产物里缺原料，如实标"暂不可量 + 缺什么原料"，不造数。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "investigation_reports" / "20260826_第三层治理施工工单"

# 结构性无正文的事件类型：信息就在标题/日期里，本来就不该有正文。
# （SEC 文件号、官方日程/宏观数发布日程。）剔除它们后，才是"想抓没抓到"的真缺口。
STRUCTURAL_NO_BODY_TYPES = {"issuer_filing", "official_calendar"}


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def metric_1_fulltext_rate(main_runs: list[Path]) -> dict:
    """全文率：raw 口径 + adjusted 口径（剔除结构性无正文）。"""
    rows = []
    for run_dir in main_runs:
        ledger = _load(run_dir / "news_event_ledger.json")
        if not ledger:
            continue
        events = [e for e in ledger.get("events", []) if isinstance(e, dict)]
        if not events:
            continue
        total = len(events)
        raw_ok = sum(1 for e in events if e.get("raw_text_available"))
        structural = sum(1 for e in events if e.get("event_type") in STRUCTURAL_NO_BODY_TYPES)
        adjustable = total - structural
        adjusted_ok = sum(
            1
            for e in events
            if e.get("event_type") not in STRUCTURAL_NO_BODY_TYPES and e.get("raw_text_available")
        )
        rows.append(
            {
                "run": run_dir.name,
                "total": total,
                "raw_text": raw_ok,
                "raw_rate": round(raw_ok / total, 4),
                "structural_no_body": structural,
                "adjusted_denom": adjustable,
                "adjusted_rate": round(adjusted_ok / adjustable, 4) if adjustable else None,
            }
        )
    return {"rows": rows}


def metric_2_source_tier(main_runs: list[Path]) -> dict:
    """来源等级分布：聚合最近 main run 的 source_tier 计数。"""
    tiers: Counter = Counter()
    total = 0
    for run_dir in main_runs:
        ledger = _load(run_dir / "news_event_ledger.json")
        if not ledger:
            continue
        for e in ledger.get("events", []):
            if isinstance(e, dict) and e.get("source_tier"):
                tiers[str(e["source_tier"])] += 1
                total += 1
    return {"total": total, "distribution": dict(tiers.most_common())}


def metric_3_reconcile(dsh_runs: list[Path]) -> dict:
    """主张-原文对账通过率 + 一手率（来源等级分布的巡逻侧落地）。"""
    rows = []
    for run_dir in dsh_runs:
        s = _load(run_dir / "run_summary.json")
        if not s:
            continue
        rows.append(
            {
                "run": run_dir.name,
                "tracking_key": s.get("tracking_key"),
                "cards_total": s.get("cards_total"),
                "cards_verified": s.get("cards_verified"),
                "reconcile_pass_rate": s.get("reconcile_pass_rate"),
                "first_hand_rate": (s.get("tier_distribution") or {}).get("first_hand_rate"),
                "publishable": s.get("publishable"),
            }
        )
    total_cards = sum(r["cards_total"] or 0 for r in rows)
    verified = sum(r["cards_verified"] or 0 for r in rows)
    return {
        "rows": rows,
        "aggregate": {
            "cards_total": total_cards,
            "cards_verified": verified,
            "overall_reconcile_rate": round(verified / total_cards, 4) if total_cards else None,
        },
    }


def metric_4_channel_vacuum(main_runs: list[Path], dsh_runs: list[Path]) -> dict:
    """渠道真空核查覆盖率：现有产物里没有结构化落点，如实标暂不可量。"""
    # 探测可能的落点字段，确认是否真的没有。
    candidates = []
    for run_dir in dsh_runs:
        s = _load(run_dir / "run_summary.json")
        if s and s.get("leads"):
            candidates.append(run_dir.name)
    return {
        "measurable": False,
        "note": "渠道真空核查覆盖率没有结构化落点：无渠道清单、无抽查记录字段。"
        "run_summary 的 leads 是线索不是渠道真空覆盖。需先定义渠道清单 + 落盘抽查记录。",
        "closest_field_probe": {"leads_runs_with_content": candidates[:5]},
    }


def metric_5_ia_citation(main_runs: list[Path]) -> dict:
    """IA 引用可用率：研究架事实进 IA 的数量 + 事件卡进 IA 的数量。"""
    rows = []
    for run_dir in main_runs:
        report = _load(run_dir / "integrated_synthesis_report.json")
        if not report:
            continue
        patrols = (report.get("event_research_patrols") or {}).get("patrols") or []
        cards = report.get("event_interpretation_cards") or []
        rows.append(
            {
                "run": run_dir.name,
                "patrol_facts_into_ia": len([p for p in patrols if isinstance(p, dict)]),
                "event_cards_into_ia": len([c for c in cards if isinstance(c, dict)]),
            }
        )
    patrol_total = sum(r["patrol_facts_into_ia"] for r in rows)
    return {
        "rows": rows,
        "measurable": patrol_total > 0,
        "note": "IA 引用可用率 = 进 IA 的巡逻事实里被 IA 实际引用（带卡 id）的占比。"
        "现有全部 main run 的巡逻事实进 IA 数 = 0（研究架未建成、圈题 no_selection），故暂不可量。"
        "事件卡进 IA 数可量（见 rows.event_cards_into_ia），但'引用可用'需 IA 输出带卡 id 的引用锚，尚未仪器化。",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="量第二层成熟度五项基线（零 AI 调用）")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    main_runs = sorted(
        Path(ROOT, "output", "analysis", "vnext").glob("*/"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:6]
    dsh_runs = sorted(
        Path(ROOT, "output", "event_research", "runs").glob("EV-*/"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    result = {
        "generated_note": "T67/W3 基线测量器，零 AI 调用。渠道真空与 IA 引用两项暂不可量，缺原料见各 metric.note。",
        "metric_1_fulltext_rate": metric_1_fulltext_rate(main_runs),
        "metric_2_source_tier": metric_2_source_tier(main_runs),
        "metric_3_reconcile": metric_3_reconcile(dsh_runs),
        "metric_4_channel_vacuum": metric_4_channel_vacuum(main_runs, dsh_runs),
        "metric_5_ia_citation": metric_5_ia_citation(main_runs),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "baseline_measurements.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {json_path}")

    # 打印摘要供人读
    m1 = result["metric_1_fulltext_rate"]["rows"]
    if m1:
        latest = m1[0]
        print(f"[①全文率] 最近 run {latest['run']}: raw={latest['raw_rate']:.0%} adjusted={latest['adjusted_rate']:.0%}（结构性无正文 {latest['structural_no_body']}/{latest['total']}）")
    m2 = result["metric_2_source_tier"]["distribution"]
    print(f"[②来源等级] {m2}")
    m3 = result["metric_3_reconcile"]
    print(f"[③对账通过率] 聚合 {m3['aggregate']['cards_verified']}/{m3['aggregate']['cards_total']} = {m3['aggregate']['overall_reconcile_rate']}")
    print(f"[④渠道真空] measurable={result['metric_4_channel_vacuum']['measurable']}")
    print(f"[⑤IA引用] measurable={result['metric_5_ia_citation']['measurable']}")


if __name__ == "__main__":
    main()
