#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_relay.py — T49 第二件·任务 4：离线重装配演示（正文上链）

在不 live 重跑流水线（不花 API 钱）的前提下，模拟"注入后 IA 本应看到的卡"：

- 读旧 run 的 `event_source_raw.jsonl`（源材料）与 `event_interpretation_cards.json`（旧卡，无正文）；
- 以 `news_event_ledger.json` 为桥（event_id → raw_text_hash → source raw 行），把每张卡对回源材料；
- 按新代码口径注入 `evidence_excerpt` / `raw_text_available`（逐字来自源材料 `raw_text_excerpt`）；
- 逐字校验：每张卡的 `evidence_excerpt` 必须等于对应源材料的 `raw_text_excerpt`（或为其前缀截断）；
- 按新口径重算 IA 引用可用率（有全文的卡应 > 0%）。

用法:
  正常模式（注入+校验+可用率）:
    .venv/bin/python scripts/layer2_baseline/demo_relay.py \
        --run output/analysis/vnext/20260731_002156

  反向验证（把注入后卡文件里某张卡的 evidence_excerpt 改一个字再跑，必须报错并非零退出）:
    .venv/bin/python scripts/layer2_baseline/demo_relay.py \
        --run output/analysis/vnext/20260731_002156 --check <injected_cards.json>

只读操作：不改 output/ 任何文件；注入后卡输出到 investigation_reports/20260811_layer2_research/demo/。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN = REPO_ROOT / "output" / "analysis" / "vnext" / "20260731_002156"
DEFAULT_OUT = (
    REPO_ROOT
    / "investigation_reports"
    / "20260811_layer2_research"
    / "demo"
    / "relayed_cards.json"
)
IA_EXCERPT_LIMIT = 500


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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_material_index(run_dir: Path) -> dict[str, dict]:
    """source raw 行按 raw_text_hash 索引；同时保留 source_id → 行列表用于诊断。"""
    rows = load_jsonl(run_dir / "event_source_raw.jsonl")
    by_hash = {}
    by_source_id: dict[str, list[dict]] = {}
    for row in rows:
        h = row.get("raw_text_hash")
        if h:
            by_hash[h] = row
        by_source_id.setdefault(str(row.get("source_id") or ""), []).append(row)
    return {"by_hash": by_hash, "by_source_id": by_source_id, "total_materials": len(rows)}


def build_event_bridge(run_dir: Path) -> dict[str, dict]:
    """news_event_ledger.json 的 events：event_id → 事件（含 raw_text_hash / source_id）。"""
    ledger = load_json(run_dir / "news_event_ledger.json")
    events = ledger.get("events") or []
    return {str(e.get("event_id") or ""): e for e in events if isinstance(e, dict)}


def inject_and_check(
    run_dir: Path,
    cards: list[dict],
    *,
    reuse_excerpt: bool = False,
) -> tuple[list[dict], list[dict]]:
    """注入 evidence_excerpt / raw_text_available 并逐字校验。

    - reuse_excerpt=False（正常模式）：从源材料注入 evidence_excerpt，再校验注入值逐字等于源材料。
    - reuse_excerpt=True（反向验证）：保留卡文件里已有的 evidence_excerpt 原值，直接与源材料逐字比对——
      被篡改的值必然不相等（或非前缀），从而报错。

    返回 (relayed_cards, failures)；failures 非空时调用方必须报错并非零退出。
    校验规则：evidence_excerpt 必须等于对应源材料 raw_text_excerpt，或者是其前缀截断。
    """
    material_index = build_material_index(run_dir)
    bridge = build_event_bridge(run_dir)
    by_hash = material_index["by_hash"]

    relayed = []
    failures = []
    for card in cards:
        event_id = str(card.get("event_id") or "")
        event = bridge.get(event_id, {})
        raw_hash = event.get("raw_text_hash")
        material = by_hash.get(raw_hash) if raw_hash else None
        card_failures = []
        if material is None:
            card_failures.append("无法对回源材料（event_id 不在 ledger 或 raw_text_hash 不在 source raw）")
        else:
            available = bool(material.get("raw_text_available"))
            source_excerpt = str(material.get("raw_text_excerpt") or "") if available else ""
            if reuse_excerpt:
                # 校验文件里已有的原值（不得覆盖，否则篡改检测失效）
                evidence_excerpt = str(card.get("evidence_excerpt") or "")
            else:
                evidence_excerpt = source_excerpt
            evidence_excerpt_ia = evidence_excerpt[:IA_EXCERPT_LIMIT]

            # 逐字校验：evidence_excerpt 必须等于源材料 raw_text_excerpt 或其前缀截断
            if evidence_excerpt != source_excerpt:
                card_failures.append(
                    "evidence_excerpt 不等于源材料 raw_text_excerpt"
                    f"（excerpt_len={len(evidence_excerpt)} vs source_len={len(source_excerpt)}）"
                )
            if not source_excerpt.startswith(evidence_excerpt):
                card_failures.append(
                    "evidence_excerpt 不是源材料 raw_text_excerpt 的前缀（疑似被改写）"
                    f"（excerpt_head={evidence_excerpt[:40]!r} vs source_head={source_excerpt[:40]!r}）"
                )

        if card_failures:
            failures.append({"event_id": event_id, "errors": card_failures})
        relayed.append(
            {
                "event_id": event_id,
                "fact_summary": str(card.get("fact_summary") or ""),
                "interpretation": str(card.get("interpretation") or "")[:300],
                "passport_tier": ((card.get("passport") or {}).get("tier") if isinstance(card.get("passport"), dict) else None),
                "mapped_source_id": str(material.get("source_id") or "") if material else "",
                "raw_text_available": bool(material.get("raw_text_available")) if material else False,
                "evidence_excerpt": evidence_excerpt,
                "evidence_excerpt_ia": evidence_excerpt_ia,
                "verbatim_check": "failed" if card_failures else "ok",
            }
        )
    return relayed, failures


def render_ia_usable_rate(relayed: list[dict]) -> dict:
    total = len(relayed)
    fulltext = sum(1 for c in relayed if c["raw_text_available"] and c["evidence_excerpt"])
    return {
        "total_cards": total,
        "fulltext_cards": fulltext,
        "title_only_cards": total - fulltext,
        "ia_usable_rate_new_policy": round(fulltext / total, 6) if total else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="T49 任务 4：离线重装配演示（正文上链）")
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN, help="旧 run 目录")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="注入后卡输出路径")
    parser.add_argument("--check", type=Path, default=None, help="反向验证：对给定注入后卡文件逐字校验")
    args = parser.parse_args()

    run_dir = args.run
    if not run_dir.is_dir():
        die(f"run 目录不存在: {run_dir}")
    for name in ("event_source_raw.jsonl", "event_interpretation_cards.json", "news_event_ledger.json"):
        if not (run_dir / name).is_file():
            die(f"run 目录缺少 {name}: {run_dir / name}")

    if args.check is not None:
        # 反向验证模式：读注入后卡文件，保留文件里的 evidence_excerpt 原值逐字对回源材料校验
        injected = load_json(args.check)
        cards = injected.get("cards") if isinstance(injected, dict) else injected
        if not isinstance(cards, list):
            die(f"{args.check} 无 cards 数组")
        relayed, failures = inject_and_check(run_dir, cards, reuse_excerpt=True)
        if failures:
            print(
                json.dumps(
                    {"check": "FAILED", "failure_count": len(failures), "failures": failures},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            die(f"反向验证失败：{len(failures)} 张卡的 evidence_excerpt 与源材料不一致")
        print(json.dumps({"check": "OK", "card_count": len(relayed)}, ensure_ascii=False, indent=2))
        return 0

    # 正常模式：注入 + 逐字校验 + 新口径可用率
    cards_obj = load_json(run_dir / "event_interpretation_cards.json")
    cards = cards_obj.get("cards") if isinstance(cards_obj, dict) else cards_obj
    if not isinstance(cards, list):
        die("event_interpretation_cards.json 无 cards 数组")

    relayed, failures = inject_and_check(run_dir, cards, reuse_excerpt=False)
    if failures:
        die(f"逐字校验失败：{json.dumps(failures, ensure_ascii=False)}")

    rate = render_ia_usable_rate(relayed)
    payload = {
        "schema_version": "demo_relay_v1",
        "run_dir": str(run_dir.resolve()),
        "note": "离线重装配演示：注入后 IA 本应看到的卡（evidence_excerpt 逐字来自源材料 raw_text_excerpt）",
        "card_count": len(relayed),
        "ia_usable_rate_new_policy": rate["ia_usable_rate_new_policy"],
        "fulltext_cards": rate["fulltext_cards"],
        "title_only_cards": rate["title_only_cards"],
        "cards": relayed,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(
        {
            "run_dir": str(run_dir.resolve()),
            "card_count": rate["total_cards"],
            "fulltext_cards": rate["fulltext_cards"],
            "title_only_cards": rate["title_only_cards"],
            "ia_usable_rate_new_policy": rate["ia_usable_rate_new_policy"],
            "verbatim_check": "ALL_OK",
            "relayed_cards_written_to": str(args.out.resolve()),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
