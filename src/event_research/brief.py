# -*- coding: utf-8 -*-
"""巡逻简报：给老板看的金字塔形态（2026-08-24 老板裁定的阅读形态）。

病根（老板指出）：按"系统有哪些零件"排版的产出是零件清单不是判断书。
本模块按阅读顺序组织：第一屏三行（变没变/本期判断/认错条件）→ 为什么 →
机器质检（默认收尾，是质量证明不是内容）。全部内容由代码从落盘产物装配，
不经模型手写。
"""

from __future__ import annotations

from typing import Any, Dict, List

_TIER_LABEL = {
    "official": "官方",
    "primary_news": "主流财经/逐字稿",
    "aggregator_news": "卖方",
    "weak_social": "社媒",
}

_RECONCILE_LABEL = {
    "verified": "✓ 已对回原文",
    "downgraded_pointer_missing": "✗ 出生证缺失",
    "downgraded_quote_not_found": "✗ 引文对不上",
    "downgraded_weak_tier": "✗ 弱来源进了正文",
    "downgraded_source_unverified": "✗ 来源无法定档",
}


def render_brief(run_summary: Dict[str, Any], cards: List[Dict[str, Any]]) -> str:
    """从 run_summary + 材料卡装配 markdown 简报。"""
    narrative = run_summary.get("narrative_state") or {}
    lines: List[str] = [
        f"# 事件层巡逻简报 · {run_summary.get('agenda_id')} · {run_summary.get('run_dir', '')[-15:]}",
        "",
        "> 事件层（第二层）判断。不进数据主链；每条事实可点回原文。",
        "",
        "## 第一屏",
        "",
        f"- **变没变**：{narrative.get('previous_position_delta', '（首期无上期）')}",
        f"- **本期判断**：{narrative.get('conclusion', '（缺失）')}",
        f"- **认错条件**：{narrative.get('falsification', '（缺失）')}",
        "",
        "## 为什么（想看理由再展开）",
        "",
        f"- 多方最硬一句：{narrative.get('bull_strongest', '—')}",
        f"- 空方最硬一句：{narrative.get('bear_strongest', '—')}",
        f"- 框架坐标：{narrative.get('framework_position', '—')}",
    ]
    absence = narrative.get("absence_signals")
    if absence:
        lines.append("- 该发生没发生：")
        for item in absence:
            lines.append(f"  - {item}")

    lines += ["", "### 证据卡", ""]
    for card in cards:
        reco = card.get("reconciliation") or {}
        reco_label = _RECONCILE_LABEL.get(reco.get("status", ""), reco.get("status", "未对账"))
        tier_label = _TIER_LABEL.get(str(card.get("source_tier")), str(card.get("source_tier")))
        lines.append(f"- [{card.get('card_id')}] {card.get('fact_summary')}")
        lines.append(f"  - 解读（假设）：{card.get('interpretation')}")
        if card.get("validation_errors"):
            lines.append(f"  - 镣铐标注：{'、'.join(card['validation_errors'])}")
        if card.get("falsification"):
            lines.append(f"  - 改判条件：{card['falsification']}")
        if card.get("counter_one_liner"):
            lines.append(f"  - 最强反方：{card['counter_one_liner']}")
        lines.append(f"  - 来源：{card.get('source_url')}（{tier_label}；{reco_label}；采集于 {card.get('collected_at_utc')}）")
        lines.append(f"  - 待数据确认：{'；'.join(card.get('needs_data_confirmation') or [])}")

    check = run_summary.get("narrative_number_check") or {}
    ungrounded = check.get("ungrounded") or []
    lines += [
        "",
        "## 机器质检（质量证明，不是内容）",
        "",
        f"- 对账通过率：{run_summary.get('cards_verified')}/{run_summary.get('cards_total')}"
        f"（降级 {run_summary.get('cards_downgraded', 0)} 张；镣铐标注 {run_summary.get('cards_with_shackle_labels', 0)} 张，标注随卡走不连坐）",
        f"- 一手率：{run_summary.get('tier_distribution', {}).get('first_hand_rate')}",
        f"- 判断数字核对：查了 {check.get('checked', 0)} 个，无据 {len(ungrounded)} 个"
        + ("" if not ungrounded else "：" + "、".join(f"{u['field']} 的「{u['text']}」" for u in ungrounded)),
        f"- 判断挂锚：{'已挂 ' + '/'.join(check.get('card_refs') or []) if check.get('anchored') else '✗ 未挂任何证据卡'}",
        f"- 经费：已花 {(run_summary.get('budget') or {}).get('spent')} / 卡面 {(run_summary.get('budget') or {}).get('budget_cap')}"
        + ("（耗尽，本期为半成品）" if run_summary.get("budget_exhausted") else ""),
    ]
    if run_summary.get("charter_feedback"):
        lines += ["", f"## 宪章反馈（AI 自述，未经核实）", "", str(run_summary["charter_feedback"])]
    return "\n".join(lines) + "\n"
