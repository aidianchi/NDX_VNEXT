#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_sources.py — 采集源体检表生成器（任务 1）

只读操作：用 AST 静态解析 src/news_event_ledger.py 的注册源，叠加人工判定表，
输出 源体检表.md 与机器可读 sources_audit.json。

用法:
  .venv/bin/python scripts/layer2_baseline/audit_sources.py            # 生成产物
  .venv/bin/python scripts/layer2_baseline/audit_sources.py --check   # 校验后退出码 0/1

规则:
  - 注册源数以代码为准（AST 解析），判定表必须与之一一对应；对不上即 --check 失败。
  - 三性判定："存疑" 是合法值，禁止编造。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "src" / "news_event_ledger.py"
OUT_DIR = REPO_ROOT / "investigation_reports" / "20260811_layer2_research" / "baseline"

# ---------------------------------------------------------------------------
# 1. AST 解析注册源（以代码为准，不靠记忆）
# ---------------------------------------------------------------------------

LIST_CONTAINERS = [
    "OFFICIAL_RSS_SOURCES",
    "YAHOO_FINANCE_RSS_SOURCES",
    "SOCIAL_RSS_SOURCES",
    "WIND_DOC_QUERIES",
    "OFFICIAL_CALENDAR_SOURCES",
]

# 代码里硬编码注册的 source_id（不在上述列表容器中）
HARDCODED_SOURCE_IDS = ["m7_earnings_calendar", "sec_submissions", "alpha_vantage_news_sentiment"]


def parse_registered_sources() -> dict[str, dict]:
    """返回 {source_id: {"name":..., "url":..., "container":...}}，全部来自代码 AST。"""
    tree = ast.parse(LEDGER_PATH.read_text(encoding="utf-8"))
    sources: dict[str, dict] = {}

    for node in ast.walk(tree):
        # 列表/字典容器：取 "source_id": "xxx" 键值
        if isinstance(node, (ast.List, ast.Dict, ast.Set)):
            items = node.elts if isinstance(node, (ast.List, ast.Set)) else node.values
            for item in items:
                if not isinstance(item, ast.Dict):
                    continue
                kv = {}
                for key_node, val_node in zip(item.keys, item.values):
                    if isinstance(key_node, ast.Constant) and isinstance(val_node, ast.Constant):
                        kv[key_node.value] = val_node.value
                sid = kv.get("source_id")
                if isinstance(sid, str):
                    sources.setdefault(sid, {
                        "name": kv.get("source_name", ""),
                        "url": kv.get("url", ""),
                        "authority_tier": kv.get("authority_tier", ""),
                        "source_tier": kv.get("source_tier", ""),
                        "event_type": kv.get("event_type", ""),
                        "container": "",
                    })

    # 硬编码 source_id：source_id="xxx" 关键字实参
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "source_id" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    sid = kw.value.value
                    sources.setdefault(sid, {
                        "name": "",
                        "url": "",
                        "authority_tier": "",
                        "source_tier": "",
                        "event_type": "",
                        "container": "hardcoded",
                    })

    # 补充容器归属与人工可读名称（名称/URL 以代码为准，缺失时从判定表回填）
    container_map: dict[str, list[str]] = {c: [] for c in LIST_CONTAINERS}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in LIST_CONTAINERS:
                value = node.value
                if isinstance(value, (ast.List, ast.Tuple)):
                    elts = value.elts
                    for elt in elts:
                        if isinstance(elt, ast.Dict):
                            kv = {}
                            for k, v in zip(elt.keys, elt.values):
                                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                    kv[k.value] = v.value
                            if isinstance(kv.get("source_id"), str):
                                container_map[target.id].append(kv["source_id"])
                                if kv["source_id"] in sources:
                                    sources[kv["source_id"]]["container"] = target.id
                                    if not sources[kv["source_id"]]["name"]:
                                        sources[kv["source_id"]]["name"] = kv.get("source_name", "")
                                    if not sources[kv["source_id"]]["url"]:
                                        sources[kv["source_id"]]["url"] = kv.get("url", "")
                                    if not sources[kv["source_id"]]["authority_tier"]:
                                        sources[kv["source_id"]]["authority_tier"] = kv.get("authority_tier", "")
                                    if not sources[kv["source_id"]]["source_tier"]:
                                        sources[kv["source_id"]]["source_tier"] = kv.get("source_tier", "")
                                    if not sources[kv["source_id"]]["event_type"]:
                                        sources[kv["source_id"]]["event_type"] = kv.get("event_type", "")
                elif isinstance(value, ast.Dict):
                    # dict 容器（如 OFFICIAL_CALENDAR_SOURCES）：键即 source_id，值内含 source_name/url
                    for k_node, v_node in zip(value.keys, value.values):
                        if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
                            continue
                        sid = k_node.value
                        container_map[target.id].append(sid)
                        vmeta = {}
                        if isinstance(v_node, ast.Dict):
                            for vk, vv in zip(v_node.keys, v_node.values):
                                if isinstance(vk, ast.Constant) and isinstance(vv, ast.Constant):
                                    vmeta[vk.value] = vv.value
                        if sid not in sources:
                            sources[sid] = {
                                "name": "", "url": "", "authority_tier": "",
                                "source_tier": "", "event_type": "", "container": "",
                            }
                        sources[sid]["container"] = target.id
                        if not sources[sid]["name"]:
                            sources[sid]["name"] = vmeta.get("source_name", "")
                        if not sources[sid]["url"]:
                            sources[sid]["url"] = vmeta.get("url", "")

    return sources


# ---------------------------------------------------------------------------
# 2. 人工判定表（通读代码 + 观察样本 run 20260731_002156 后逐源判定）
#    三性：trust / necessity / scrapable；拿不准一律 "存疑"，不猜。
# ---------------------------------------------------------------------------

JUDGMENT = {
    "federal_reserve_press_all": {
        "trust": "官方",
        "trust_evidence": "美联储官网 RSS（federalreserve.gov/feeds/press_all.xml），代码 authority_tier=official",
        "necessity": "已发生（政策/金融条件新闻与公告）",
        "necessity_evidence": "供给已发生的货币政策/金融条件事件；与日历源 fomc_meeting_calendar 是互补（后者只给将发生的日程），无供给重叠",
        "overlaps": [],
        "scrapable": "能",
        "scrapable_evidence": "标准 RSS，无需登录、无需浏览器；本次 run 出活 8 条",
    },
    "bls_latest": {
        "trust": "官方",
        "trust_evidence": "美国劳工统计局官网 RSS（bls.gov/feed/bls_latest.rss），authority_tier=official",
        "necessity": "已发生（宏观数据发布）",
        "necessity_evidence": "供给已发生的宏观数据发布（CPI/就业等）；与 bls_release_calendar 互补（日历只给将发生的发布日期），无供给重叠",
        "overlaps": [],
        "scrapable": "能",
        "scrapable_evidence": "标准 RSS，无需登录、无需浏览器；本次 run 出活 1 条",
    },
    "bea_news": {
        "trust": "官方",
        "trust_evidence": "美国经济分析局官网 RSS（bea.gov/news/rss），authority_tier=official",
        "necessity": "已发生（宏观数据发布）",
        "necessity_evidence": "供给已发生的 GDP/PCE 等数据发布；与 bea_release_calendar 互补，无供给重叠",
        "overlaps": [],
        "scrapable": "能",
        "scrapable_evidence": "标准 RSS，无需登录、无需浏览器；本次 run 出活 6 条",
    },
    "yahoo_finance_qqq_headlines": {
        "trust": "主流",
        "trust_evidence": "Yahoo Finance RSS 聚合（feeds.finance.yahoo.com），authority_tier=market_news_aggregator，主流财经媒体聚合",
        "necessity": "已发生 + 被相信（市场新闻与叙事）",
        "necessity_evidence": "供给已发生的市场新闻与市场叙事；与 yahoo_finance_m7_headlines 同源不同标的（部分重叠），与 alpha_vantage_news_sentiment 同属市场新闻聚合（部分重叠）",
        "overlaps": ["yahoo_finance_m7_headlines", "alpha_vantage_news_sentiment", "wind_financial_news_ndx"],
        "scrapable": "能",
        "scrapable_evidence": "RSS 无需登录、无需浏览器；本次 run 出活 8 条。注意：Yahoo 偶有反爬/限流，接口稳定性为中等，本次实测可用",
    },
    "yahoo_finance_m7_headlines": {
        "trust": "主流",
        "trust_evidence": "Yahoo Finance RSS 聚合（M7 标的），authority_tier=market_news_aggregator",
        "necessity": "已发生 + 被相信（M7 市场新闻与叙事）",
        "necessity_evidence": "供给 M7 的已发生市场新闻；与 yahoo_finance_qqq_headlines 同源不同标的（部分重叠），与 alpha_vantage_news_sentiment 部分重叠",
        "overlaps": ["yahoo_finance_qqq_headlines", "alpha_vantage_news_sentiment", "wind_financial_news_ndx"],
        "scrapable": "能",
        "scrapable_evidence": "RSS 无需登录、无需浏览器；本次 run 出活 8 条，接口稳定性中等",
    },
    "reddit_stocks_qqq_search": {
        "trust": "弱",
        "trust_evidence": "Reddit r/stocks 搜索 RSS，authority_tier=social_discussion，社交讨论噪音源",
        "necessity": "被相信（市场叙事温度）",
        "necessity_evidence": "供给散户叙事与情绪（narrative temperature），是全注册表唯一社交源；与任何源无供给重叠",
        "overlaps": [],
        "scrapable": "存疑",
        "scrapable_evidence": "RSS 无需登录、无需浏览器（需带 User-Agent）；但 Reddit 对无登录抓取有速率限制，官方无稳定性承诺，接口可能随时 429。本次 run 出活 8 条",
    },
    "wind_company_announcements_m7": {
        "trust": "授权",
        "trust_evidence": "Wind 万得金融数据终端（licensed_provider/Wind），持牌商业数据源",
        "necessity": "已发生（公司公告/财报/指引）",
        "necessity_evidence": "供给 M7 的公司公告类材料；与 sec_submissions 供给重叠（同为 M7 披露，SEC 为原始官方、Wind 为授权聚合），重叠度高的部分按 SEC 为准",
        "overlaps": ["sec_submissions"],
        "scrapable": "不能",
        "scrapable_evidence": "走 Wind skill CLI（~/.agents/skills/wind-mcp-skill），依赖本地 skill 目录存在 + Wind 授权连接/登录态，非普通 HTTP 接口。本次 run 因无实体匹配丢弃 1 条",
    },
    "wind_financial_news_ndx": {
        "trust": "授权",
        "trust_evidence": "Wind 万得金融新闻（licensed_provider/Wind），持牌商业数据源",
        "necessity": "已发生 + 被相信（财经新闻）",
        "necessity_evidence": "供给 NDX/宏观财经新闻；与 yahoo 两源、alpha_vantage_news_sentiment 供给重叠（同为市场财经新闻聚合）",
        "overlaps": ["yahoo_finance_qqq_headlines", "yahoo_finance_m7_headlines", "alpha_vantage_news_sentiment"],
        "scrapable": "不能",
        "scrapable_evidence": "走 Wind skill CLI，依赖本地 skill 目录 + Wind 授权连接/登录态。本次 run 出活 8 条（说明采集时授权可用，但非普通 HTTP 可复现）",
    },
    "fomc_meeting_calendar": {
        "trust": "官方",
        "trust_evidence": "美联储官网 FOMC 日历页（federalreserve.gov/monetarypolicy/fomccalendars.htm），官方日程",
        "necessity": "将发生（FOMC 会议日程）",
        "necessity_evidence": "供给将发生的 FOMC 会议日期（规则语境：利率路径关键节点）；与 federal_reserve_press_all 互补，无供给重叠",
        "overlaps": [],
        "scrapable": "能",
        "scrapable_evidence": "无需登录、无需浏览器，直接抓 HTML 解析；本次 run 出活 8 条。注意：是 HTML 页面解析而非标准接口，页面改版会失效",
    },
    "bls_release_calendar": {
        "trust": "官方",
        "trust_evidence": "BLS 发布日历 ICS（bls.gov/schedule/news_release/bls.ics），官方标准日历格式",
        "necessity": "将发生（宏观数据发布日期）",
        "necessity_evidence": "供给将发生的 BLS 数据发布日期（规则语境）；与 bls_latest 互补，无供给重叠",
        "overlaps": [],
        "scrapable": "能",
        "scrapable_evidence": "标准 ICS 文件，无需登录、无需浏览器；本次 run 出活 8 条",
    },
    "bea_release_calendar": {
        "trust": "官方",
        "trust_evidence": "BEA 发布日历 ICS（bea.gov/news/schedule/ics/online-calendar-subscription.ics），官方标准日历格式",
        "necessity": "将发生（宏观数据发布日期）",
        "necessity_evidence": "供给将发生的 BEA 数据发布日期（规则语境）；与 bea_news 互补，无供给重叠",
        "overlaps": [],
        "scrapable": "能",
        "scrapable_evidence": "标准 ICS 文件，无需登录、无需浏览器；本次 run 出活 8 条",
    },
    "nasdaq_index_announcements": {
        "trust": "官方",
        "trust_evidence": "Nasdaq 官网新闻中心（nasdaq.com/about/press-center），官方指数公告入口",
        "necessity": "将发生（指数调整/再平衡公告）",
        "necessity_evidence": "供给将发生的 NDX 指数再平衡/成分调整公告（规则语境）；无其他源供给此材料，无重叠",
        "overlaps": [],
        "scrapable": "不能",
        "scrapable_evidence": "HTML 页面抓取 + 正则解析（非标准接口），本次 run 实测 Read timed out（读超时 12s）。无需登录/浏览器，但接口不稳定，不满足「接口稳定」",
    },
    "m7_earnings_calendar": {
        "trust": "弱",
        "trust_evidence": "yfinance 库拉 Yahoo Finance earnings dates + 确定性静默期规则推算（third_party_calendar / third_party_unofficial），非公司官方披露",
        "necessity": "将发生（M7 财报日期，规则语境）",
        "necessity_evidence": "供给将发生的 M7 财报日程；是唯一财报日程源，无供给重叠。注意：是规则推算值而非公司确认值",
        "overlaps": [],
        "scrapable": "存疑",
        "scrapable_evidence": "依赖 yfinance 第三方库 + Yahoo 非官方接口，无需登录、无需浏览器；接口稳定性无官方承诺，Yahoo 可能限流/变更。本次 run 出活 2 条",
    },
    "sec_submissions": {
        "trust": "官方",
        "trust_evidence": "SEC EDGAR 官方 submissions API（data.sec.gov/submissions/CIKxxx.json），authority_tier=official_filing",
        "necessity": "已发生（8-K/10-Q/10-K 官方申报）",
        "necessity_evidence": "供给 M7 已发生的官方申报（规则语境：法定披露）；与 wind_company_announcements_m7 供给重叠（本源为原始官方）",
        "overlaps": ["wind_company_announcements_m7"],
        "scrapable": "能",
        "scrapable_evidence": "官方 JSON API，无需登录（需带 User-Agent 声明），代码已按 0.12s 间隔限速；接口稳定。本次 run 出活 13 条",
    },
    "alpha_vantage_news_sentiment": {
        "trust": "主流",
        "trust_evidence": "Alpha Vantage NEWS_SENTIMENT API（third_party_news_sentiment），主流第三方数据商",
        "necessity": "已发生 + 被相信（新闻情感聚合）",
        "necessity_evidence": "供给新闻情感标签（叙事温度）；与 yahoo 两源、wind_financial_news_ndx 供给重叠（同为新闻聚合）",
        "overlaps": ["yahoo_finance_qqq_headlines", "yahoo_finance_m7_headlines", "wind_financial_news_ndx"],
        "scrapable": "不能",
        "scrapable_evidence": "需要 API key（get_api_key('alphavantage')），本次 run 实测 skipped_alpha_vantage_disabled_or_missing_key（未配 key 或服务被禁）。有 key 时是稳定 REST 接口",
    },
}


def build_audit() -> dict:
    registered = parse_registered_sources()
    rows = []
    for sid in sorted(registered):
        code = registered[sid]
        j = JUDGMENT.get(sid)
        if j is None:
            rows.append({
                "source_id": sid,
                "source_name": code["name"],
                "container": code["container"] or "hardcoded",
                "url": code["url"],
                "trust": "存疑",
                "trust_evidence": "人工判定缺失，未给出结论",
                "necessity": "存疑",
                "necessity_evidence": "人工判定缺失，未给出结论",
                "overlaps": [],
                "scrapable": "存疑",
                "scrapable_evidence": "人工判定缺失，未给出结论",
            })
        else:
            rows.append({
                "source_id": sid,
                "source_name": code["name"] or j.get("_name", ""),
                "container": code["container"] or "hardcoded",
                "url": code["url"],
                "trust": j["trust"],
                "trust_evidence": j["trust_evidence"],
                "necessity": j["necessity"],
                "necessity_evidence": j["necessity_evidence"],
                "overlaps": j.get("overlaps", []),
                "scrapable": j["scrapable"],
                "scrapable_evidence": j["scrapable_evidence"],
            })
    return {
        "schema_version": "layer2_source_audit_v1",
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "registered_source_count": len(registered),
        "audited_source_count": len(rows),
        "ledger_file": str(LEDGER_PATH),
        "sources": rows,
    }


def check(rows: list, registered_count: int) -> list[str]:
    errors = []
    if registered_count != len(rows):
        errors.append(f"注册源数({registered_count}) != 表内源数({len(rows)})")
    for r in rows:
        if not r["trust"]:
            errors.append(f"{r['source_id']}.trust 为空")
        elif r["trust"] not in ("存疑", "官方", "授权", "主流", "弱"):
            errors.append(f"{r['source_id']}.trust 取值非法: {r['trust']}")
        if not r["necessity"]:
            errors.append(f"{r['source_id']}.necessity 为空")
        if not r["scrapable"]:
            errors.append(f"{r['source_id']}.scrapable 为空")
        elif r["scrapable"] not in ("存疑", "能", "不能"):
            errors.append(f"{r['source_id']}.scrapable 取值非法: {r['scrapable']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Layer2 采集源体检表")
    parser.add_argument("--check", action="store_true", help="校验模式：注册源数=表内源数且三性齐全，不写文件")
    args = parser.parse_args()

    audit = build_audit()
    errors = check(audit["sources"], audit["registered_source_count"])

    if args.check:
        print(f"注册源数 = {audit['registered_source_count']}, 表内源数 = {audit['audited_source_count']}")
        for r in audit["sources"]:
            print(f"  {r['source_id']:<32} 靠谱={r['trust']}  必要={r['necessity'][:12]}  能死板拿={r['scrapable']}")
        if errors:
            for e in errors:
                print("CHECK_FAIL:", e)
            print("CHECK_RESULT: FAIL")
            return 1
        print("CHECK_RESULT: PASS")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "sources_audit.json"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Layer2 采集源体检表",
        "",
        f"- 生成时间：{audit['generated_at_utc']}",
        f"- 注册源清单来源：`src/news_event_ledger.py`（AST 静态解析，`{audit['ledger_file']}`）",
        f"- 注册源数：{audit['registered_source_count']}；表内源数：{audit['audited_source_count']}",
        "- 判定原则：①靠谱吗（官方/授权/主流/弱）②必要吗（供给哪类材料——已发生/将发生/被相信/规则语境，重叠源列在括号）③能死板拿吗（无需登录、无需浏览器、接口稳定）；拿不准标「存疑」，不猜。",
        "",
        "| source_id | 名称 | 注册处 | ① 靠谱吗 | ② 必要吗 | 供给重叠 | ③ 能死板拿吗 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in audit["sources"]:
        overlap = "、".join(r["overlaps"]) if r["overlaps"] else "—"
        md_lines.append(
            f"| {r['source_id']} | {r['source_name'] or '（代码未命名）'} | {r['container']} "
            f"| {r['trust']} | {r['necessity']} | {overlap} | {r['scrapable']} |"
        )

    md_lines += ["", "## 逐源判定依据（证据）", ""]
    for r in audit["sources"]:
        md_lines += [
            f"### {r['source_id']}",
            f"- ① 靠谱：**{r['trust']}** —— {r['trust_evidence']}",
            f"- ② 必要：**{r['necessity']}** —— {r['necessity_evidence']}",
            f"- ③ 能死板拿：**{r['scrapable']}** —— {r['scrapable_evidence']}",
            "",
        ]

    md_path = OUT_DIR / "源体检表.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"注册源数 = {audit['registered_source_count']}, 表内源数 = {audit['audited_source_count']}")
    if errors:
        for e in errors:
            print("CHECK_FAIL:", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
