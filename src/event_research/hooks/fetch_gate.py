# -*- coding: utf-8 -*-
"""搜索腿白名单闸（PreToolUse，matcher=web_fetch）。

分档白名单（config/event_source_whitelist.json，老板 2026-08-24 拍板分档）：
- 四档（official/mainstream_finance/sell_side/social）都可抓取；
- 弱档（sell_side/social）只进线索不进正文——这条由对账器机器执行降级，
  本闸只管"白名单外一律 deny"和"仅 https"。
"""

from __future__ import annotations

import sys

from common import domain_tier, emit_deny, is_https, load_whitelist, read_hook_payload


def main() -> None:
    payload = read_hook_payload()
    if payload.get("hook_event_name") != "PreToolUse":
        return
    tool_input = payload.get("tool_input") or {}
    url = str(tool_input.get("url") or "")
    if not url:
        emit_deny("web_fetch 缺少 url 参数")
    if not is_https(url):
        emit_deny(f"仅允许 https：{url}")
    if domain_tier(url, load_whitelist()) is None:
        emit_deny(f"域名不在事件层搜索腿白名单：{url}")


if __name__ == "__main__":
    main()
    sys.exit(0)
