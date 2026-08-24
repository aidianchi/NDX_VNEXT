# -*- coding: utf-8 -*-
"""来源分级打标器（PostToolUse，matcher=web_fetch）。

每次抓取完成后给模型贴标签：该 URL 属哪一档、能不能进正文。
机器执行（弱档降级）在对账器，这里只做语义提示，帮助模型写卡时定 source_tier。
"""

from __future__ import annotations

import sys

from common import domain_tier, emit_additional_context, load_whitelist, read_hook_payload

_TIER_LABEL = {
    "official": "official（官方，可进正文，source_tier=official）",
    "official_disclosure": "official_disclosure（公司官方披露/IR，可进正文，source_tier=official）",
    "transcript": "transcript（业绩会逐字稿托管，内容是管理层官方发言，可进正文，source_tier=primary_news；注意转录误差可能）",
    "mainstream_finance": "mainstream_finance（主流财经，可进正文，source_tier=primary_news）",
    "sell_side": "sell_side（卖方，只进线索不进正文，source_tier=aggregator_news）",
    "social": "social（社媒，只进线索不进正文，source_tier=weak_social）",
}


def main() -> None:
    payload = read_hook_payload()
    if payload.get("hook_event_name") != "PostToolUse":
        return
    tool_input = payload.get("tool_input") or {}
    url = str(tool_input.get("url") or "")
    if not url:
        return
    tier = domain_tier(url, load_whitelist())
    label = _TIER_LABEL.get(tier or "", "未分级")
    emit_additional_context(f"[事件层来源分级] 刚抓取的 {url} 属 {label}。")


if __name__ == "__main__":
    main()
    sys.exit(0)
