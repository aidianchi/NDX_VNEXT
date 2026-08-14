#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baseline_metrics.py — Layer2 事件链五项质量指标基线（任务 2）

只读操作：对指定 run 目录计算五项指标，输出确定性 JSON 到 stdout。

用法:
  .venv/bin/python scripts/layer2_baseline/baseline_metrics.py --run <run_dir>
  # 反向验证：--run 指向不存在或残缺目录必须报错并非零退出

五项指标（口径见 investigation_reports/20260811_layer2_research/02_第二层形态探讨稿.md Q5）：
  1. 全文率：raw_text_available=false 的材料占比
  2. 来源等级分布：按 source_type 统计条数与占比
  3. 主张对账通过率：固定种子抽 5 张事件卡，断言对回原文（脚本输出机械层映射证据，语义判定在报告）
  4. 渠道真空覆盖率：注册源中本次运行有明确"有/无新事件"记录的比例
  5. IA 引用可用率：IA 输入（integrated_synthesis_report.json）事件卡关键字段完整占比

确定性保证：stdout 不含时间戳/随机量，连跑两次逐字节一致。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "src" / "news_event_ledger.py"

REQUIRED_FILES = [
    "event_source_raw.jsonl",
    "event_interpretation_cards.json",
    "final_adjudication.json",
    "synthesis_packet.json",
    "integrated_synthesis_report.json",
]

# 第 2 项：source_tier 枚举全集 —— 直接 AST 解析代码 governance.source_tiers（以代码为准）
def source_tier_universe() -> list[str]:
    tree = ast.parse(LEDGER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key_node, val_node in zip(node.keys, node.values):
                if isinstance(key_node, ast.Constant) and key_node.value == "source_tiers" and isinstance(val_node, ast.List):
                    return [elt.value for elt in val_node.elts if isinstance(elt, ast.Constant)]
    return []

# 第 4 项：注册源全集 —— 优先读任务 1 产物 sources_audit.json，缺失时回退到硬编码清单
AUDIT_PATH = REPO_ROOT / "investigation_reports" / "20260811_layer2_research" / "baseline" / "sources_audit.json"

FALLBACK_REGISTERED_SOURCE_IDS = [
    "federal_reserve_press_all", "bls_latest", "bea_news",
    "yahoo_finance_qqq_headlines", "yahoo_finance_m7_headlines",
    "reddit_stocks_qqq_search",
    "wind_company_announcements_m7", "wind_financial_news_ndx",
    "fomc_meeting_calendar", "bls_release_calendar", "bea_release_calendar",
    "nasdaq_index_announcements",
    "m7_earnings_calendar", "sec_submissions", "alpha_vantage_news_sentiment",
]


def registered_source_ids() -> list[str]:
    if AUDIT_PATH.is_file():
        audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        ids = sorted(s["source_id"] for s in audit.get("sources", []))
        if ids:
            return ids
    return FALLBACK_REGISTERED_SOURCE_IDS

CLAIM_SAMPLE_SEED = 20260811  # 固定抽样种子，写进报告


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            die(f"{path} 第 {len(rows) + 1} 行 JSON 解析失败: {exc}")
    return rows


def metric_fulltext(records: list[dict]) -> dict:
    total = len(records)
    no_text = sum(1 for r in records if not r.get("raw_text_available"))
    return {
        "metric": "1_fulltext_rate",
        "definition": "raw_text_available=false 的材料占比",
        "total_materials": total,
        "raw_text_available_true": total - no_text,
        "raw_text_available_false": no_text,
        "fulltext_rate": round(no_text / total, 6) if total else 0.0,
    }


def metric_source_tier(records: list[dict]) -> dict:
    counter = Counter(r.get("source_type") or "" for r in records)
    total = len(records)
    universe = source_tier_universe()
    dist = []
    for tier in universe:
        n = counter.get(tier, 0)
        dist.append({
            "source_type": tier,
            "count": n,
            "ratio": round(n / total, 6) if total else 0.0,
        })
    observed = set(counter)
    univ = set(universe)
    return {
        "metric": "2_source_tier_distribution",
        "definition": "按 source_type 统计条数与占比（枚举全集以代码 governance.source_tiers 为准）",
        "declared_tier_count": len(universe),
        "total_materials": total,
        "distribution": dist,
        "observed_types_not_in_universe": sorted(observed - univ),
        "declared_not_observed": sorted(univ - observed),
    }


def metric_claim_reconciliation(run_dir: Path, cards: list[dict], records_by_srcid: dict) -> dict:
    """固定种子抽 5 张卡；输出机械层映射证据（每张卡→原文记录字段）。
    语义判定（原文有/无/不全）由执行者逐条引用 source_id 与字段完成，见报告。"""
    seed = CLAIM_SAMPLE_SEED
    rng = random.Random(seed)
    if len(cards) < 5:
        die(f"事件卡不足 5 张（实际 {len(cards)}），无法按任务要求抽 5 张")
    sampled = rng.sample(sorted(cards, key=lambda c: c.get("event_id", "")), 5)
    rows = []
    for card in sampled:
        eid = card.get("event_id", "")
        sid = "src:" + eid.split(":", 1)[1] if eid.startswith("event:") else None
        rec = records_by_srcid.get(sid) if sid else None
        rows.append({
            "card_event_id": eid,
            "mapped_source_id": sid,
            "source_record_found": rec is not None,
            "provider": rec.get("provider") if rec else None,
            "title": rec.get("title") if rec else None,
            "raw_text_available": rec.get("raw_text_available") if rec else None,
            "raw_text_excerpt": (rec.get("raw_text_excerpt") or "")[:300] if rec else None,
            "card_fact_summary": card.get("fact_summary", ""),
            "card_interpretation": card.get("interpretation", ""),
        })
    mapped = sum(1 for r in rows if r["source_record_found"])
    return {
        "metric": "3_claim_reconciliation",
        "definition": "固定种子抽 5 张事件卡，断言对回原文。脚本输出机械层证据；语义判定（原文有/无/不全）见报告",
        "sample_seed": seed,
        "sample_size": len(rows),
        "mechanically_mapped_to_source": mapped,
        "mechanically_unmapped": len(rows) - mapped,
        "samples": rows,
    }


def metric_vacuum_coverage(run_dir: Path, ledger: dict) -> dict:
    """渠道真空覆盖率（T49 第二件：拆三态）：注册源中，本次运行有明确「有/无新事件」记录的比例。

    三态判定（优先级从高到低）：
      1. 正常有事件：event_source_raw.jsonl 有该源材料（provider 匹配）。
      2. 失败：news_event_ledger.json source_errors 有该源（error 非空），逐个列名与错误原文。
      3. 确认无事件：出现在本次轮询清单（ledger.sources 全部分组名与成员并集）中，但无材料且无错误
         —— 正常跑完、确认没有新事件。
      4. 其余 = 静默无记录（注册了但既无材料、无错误、也不在轮询清单）。
    """
    raw = load_jsonl(run_dir / "event_source_raw.jsonl")
    providers_with_material = {r.get("provider") for r in raw}
    errors = ledger.get("source_errors") or []
    providers_with_error = {e.get("source_id") for e in errors}
    error_detail = {}
    for e in errors:
        error_detail.setdefault(e.get("source_id"), []).append(e)
    # 本次轮询清单：所有分组名 + 各组全部成员打平
    polled = set()
    for group_name, members in (ledger.get("sources") or {}).items():
        polled.add(str(group_name))
        if isinstance(members, list):
            polled.update(str(m) for m in members)

    status = []
    counts = {"normal_with_events": 0, "confirmed_no_events": 0, "failed": 0, "silent": 0}
    failed_sources = []
    reg_ids = registered_source_ids()
    for sid in reg_ids:
        if sid in providers_with_material:
            status.append({"source_id": sid, "state": "normal_with_events", "answer": "正常有事件", "evidence": "event_source_raw.jsonl 有材料"})
            counts["normal_with_events"] += 1
        elif sid in providers_with_error:
            err_text = json.dumps(error_detail[sid], ensure_ascii=False)
            status.append({"source_id": sid, "state": "failed", "answer": "失败", "evidence": f"source_errors: {err_text}"})
            failed_sources.append({"source_id": sid, "errors": [e.get("error") for e in error_detail[sid]]})
            counts["failed"] += 1
        elif sid in polled:
            status.append({"source_id": sid, "state": "confirmed_no_events", "answer": "确认无事件", "evidence": "在轮询清单中，无材料且无错误"})
            counts["confirmed_no_events"] += 1
        else:
            status.append({"source_id": sid, "state": "silent", "answer": "静默无记录", "evidence": "既无材料、无错误，也不在轮询清单"})
            counts["silent"] += 1

    total = len(reg_ids)
    covered = counts["normal_with_events"] + counts["confirmed_no_events"]
    return {
        "metric": "4_vacuum_coverage",
        "definition": "注册源三态口径：正常有事件/确认无事件/失败（失败逐个列名）；覆盖率=有明确有/无新事件记录的源占比",
        "registered_count": total,
        "covered_count": covered,
        "coverage_rate": round(covered / total, 6) if total else 0.0,
        "normal_with_events": counts["normal_with_events"],
        "confirmed_no_events": counts["confirmed_no_events"],
        "failed": counts["failed"],
        "failed_sources": failed_sources,
        "silent_vacuum_sources": [s["source_id"] for s in status if s["state"] == "silent"],
        "per_source": status,
    }


def metric_ia_usability(run_dir: Path, ia_report: dict) -> dict:
    """IA 引用可用率：IA 输入（integrated_synthesis_report.json）事件卡关键字段完整占比。
    关键字段：时间(published_at/event_date)、来源(source)、等级(tier)、正文(raw_text)。"""
    cards = ia_report.get("event_interpretation_cards")
    if not isinstance(cards, list) or not cards:
        return {
            "metric": "5_ia_usable_rate",
            "measurable": False,
            "reason": "IA 输入（integrated_synthesis_report.json）中无 event_interpretation_cards 数组",
        }
    total = len(cards)
    complete = 0
    per_card = []
    for card in cards:
        p = card.get("passport") or {}
        has_time = bool(p.get("published_at") or p.get("event_date"))
        has_source = bool(p.get("source"))
        has_tier = bool(p.get("tier"))
        # 正文：IA 输入卡结构里是否有正文字段（原始 raw_text 未携带进卡，如实计 0）
        card_has_raw = any(
            key in card for key in ("raw_text", "raw_text_excerpt", "raw_text_available", "excerpt")
        )
        ok = has_time and has_source and has_tier and card_has_raw
        if ok:
            complete += 1
        per_card.append({
            "event_id": card.get("event_id"),
            "has_time": has_time,
            "has_source": has_source,
            "has_tier": has_tier,
            "has_raw_text_field": card_has_raw,
            "complete": ok,
        })
    return {
        "metric": "5_ia_usable_rate",
        "definition": "IA 输入事件卡关键字段（时间/来源/等级/正文）完整的卡占比",
        "measurable": True,
        "input_artifact": "integrated_synthesis_report.json::event_interpretation_cards",
        "total_cards": total,
        "complete_cards": complete,
        "usable_rate": round(complete / total, 6) if total else 0.0,
        "per_card": per_card,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Layer2 五项质量指标基线")
    parser.add_argument("--run", required=True, help="run 目录（output/analysis/vnext/<run_id>）")
    args = parser.parse_args()

    run_dir = Path(args.run)
    if not run_dir.is_dir():
        die(f"run 目录不存在: {run_dir}")
    missing = [f for f in REQUIRED_FILES if not (run_dir / f).is_file()]
    if missing:
        die(f"run 目录残缺，缺少文件: {missing}")

    records = load_jsonl(run_dir / "event_source_raw.jsonl")
    cards_obj = json.loads((run_dir / "event_interpretation_cards.json").read_text(encoding="utf-8"))
    cards = cards_obj.get("cards") if isinstance(cards_obj, dict) else cards_obj
    if not isinstance(cards, list):
        die("event_interpretation_cards.json 无 cards 数组")
    ledger = json.loads((run_dir / "news_event_ledger.json").read_text(encoding="utf-8"))
    ia_report = json.loads((run_dir / "integrated_synthesis_report.json").read_text(encoding="utf-8"))

    records_by_srcid = {r.get("source_id"): r for r in records}

    result = {
        "schema_version": "layer2_baseline_v1",
        "run_dir": str(run_dir.resolve()),
        "metrics": [
            metric_fulltext(records),
            metric_source_tier(records),
            metric_claim_reconciliation(run_dir, cards, records_by_srcid),
            metric_vacuum_coverage(run_dir, ledger),
            metric_ia_usability(run_dir, ia_report),
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
