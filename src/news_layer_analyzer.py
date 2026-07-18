from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: str | Path, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    with file_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


TITLE_REPLACEMENTS = {
    "Federal Reserve": "美联储",
    "Press Release": "新闻稿",
    "FOMC": "联邦公开市场委员会",
    "monetary policy": "货币政策",
    "inflation": "通胀",
    "employment": "就业",
    "payroll": "非农就业",
    "GDP": "国内生产总值",
    "CPI": "消费者价格指数",
    "PPI": "生产者价格指数",
    "earnings": "盈利",
    "guidance": "业绩指引",
    "10-Q": "10-Q 季报",
    "10-K": "10-K 年报",
    "8-K": "8-K 临时公告",
}


def _localized_title(title: str) -> str:
    localized = _clean_text(title)
    for source, target in TITLE_REPLACEMENTS.items():
        localized = localized.replace(source, target)
        localized = localized.replace(source.title(), target)
    return localized or "未命名官方事件"


def _event_family(event: Dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "")
    source_id = str(event.get("source_id") or "")
    source_tier = str(event.get("source_tier") or "")
    title = str(event.get("title") or "").lower()
    tags = {str(tag) for tag in _as_list(event.get("relevance_tags"))}
    if ("sec" in source_id or source_tier in {"official_filing", "company_disclosure"}) and any(
        token in title for token in ["10-q", "10-k", "8-k", "earnings", "guidance", "filing"]
    ):
        return "mega_cap_filing"
    if any(token in title for token in ["cpi", "ppi", "inflation", "prices", "consumer price", "producer price"]):
        return "inflation"
    if any(token in title for token in ["employment", "payroll", "jobs", "unemployment", "real earnings"]):
        return "labor"
    if any(token in title for token in ["gdp", "gross domestic product", "income", "spending"]):
        return "growth"
    if "policy" in event_type or "fomc" in title or "federal reserve" in title or "monetary" in title or "topic:macro_rates" in tags:
        return "policy"
    if any(token in title for token in ["earnings", "guidance"]) or "topic:valuation_earnings" in tags:
        return "mega_cap_earnings_news"
    if "topic:index_structure" in tags:
        return "index_structure"
    if "topic:credit_vol" in tags:
        return "credit_volatility"
    if "topic:trend_execution" in tags:
        return "trend_execution"
    return "official_event"


def _base_channels(event: Dict[str, Any]) -> List[str]:
    family = _event_family(event)
    if family == "policy":
        return ["利率预期", "折现率", "风险偏好"]
    if family == "inflation":
        return ["通胀压力", "利率预期", "利润率"]
    if family == "labor":
        return ["增长韧性", "工资通胀", "降息预期"]
    if family == "growth":
        return ["盈利预期", "经济周期", "风险偏好"]
    if family in {"mega_cap_filing", "mega_cap_earnings_news"}:
        return ["龙头盈利", "业绩指引", "指数集中度"]
    return ["信息背景", "风险偏好"]


def _observation_channels(link: Dict[str, Any]) -> List[str]:
    channels: List[str] = []
    for observation in _as_list(link.get("observations")):
        if not isinstance(observation, dict):
            continue
        series = str(observation.get("series_key") or "")
        direction = str(observation.get("direction") or "")
        if series in {"US10Y", "US10Y_REAL"} and direction == "up":
            channels.append("利率上行压力")
        elif series in {"US10Y", "US10Y_REAL"} and direction == "down":
            channels.append("利率压力缓和")
        elif series in {"VIX", "VXN", "HY_OAS"} and direction == "up":
            channels.append("风险溢价上升")
        elif series in {"VIX", "VXN", "HY_OAS"} and direction == "down":
            channels.append("风险溢价回落")
        elif series in {"QQQ_OHLCV", "HYG"} and direction == "down":
            channels.append("风险资产承压")
        elif series in {"QQQ_OHLCV", "HYG"} and direction == "up":
            channels.append("风险资产修复")
        elif series == "DAMODARAN_ERP_MONTHLY" and direction == "up":
            channels.append("股权风险补偿要求上升")
    return list(dict.fromkeys(channels))


def _summary_zh(event: Dict[str, Any]) -> str:
    source = _clean_text(event.get("source_name")) or "官方来源"
    title = _localized_title(str(event.get("title") or ""))
    family = _event_family(event)
    if event.get("collection_status") == "scheduled_future":
        event_date = _clean_text(event.get("event_date")) or "待定日期"
        return f"{source} 日历显示“{title}”计划于 {event_date} 发生；这是未来日程，不是已经发生的事件。"
    if family in {"mega_cap_filing", "mega_cap_earnings_news"}:
        symbols = ", ".join(str(item) for item in _as_list(event.get("symbols")) if item)
        if family == "mega_cap_filing":
            entity_text = symbols or "未标明公司"
            return f"这是一条来自 {source} 的公司披露事件，涉及 {entity_text}；核心信息是“{title}”。它更适合作为龙头盈利和业绩预期的背景线索。"
        entity_text = f"涉及 {symbols}" if symbols else "未确认与 M7 实体直接相关"
        if event.get("source_tier") == "aggregator_report":
            return f"这是一条由 {source} 聚合平台转述的公司公告或业绩线索，{entity_text}；核心信息是“{title}”。它不是公司原文，只能作为待复核的背景线索。"
        return f"这是一条来自 {source} 的盈利相关媒体报道或聚合线索，{entity_text}；核心信息是“{title}”。它不是公司原文，只能作为待复核的背景线索。"
    if family == "policy":
        return f"这是一条来自 {source} 的政策或金融条件事件，核心信息是“{title}”。它主要影响市场对利率路径、流动性和风险偏好的判断。"
    if family == "inflation":
        return f"这是一条来自 {source} 的通胀相关事件，核心信息是“{title}”。它会影响市场对通胀粘性、降息空间和企业利润率压力的判断。"
    if family == "labor":
        return f"这是一条来自 {source} 的就业相关事件，核心信息是“{title}”。它会同时影响增长韧性、工资通胀和政策转向预期。"
    if family == "growth":
        return f"这是一条来自 {source} 的增长或收入支出相关事件，核心信息是“{title}”。它主要影响盈利周期和风险偏好。"
    return f"这是一条来自 {source} 的官方事件，核心信息是“{title}”。它只作为背景线索，需要和价格、利率、信用等数据一起复核。"


def _impact_zh(event: Dict[str, Any], link: Dict[str, Any]) -> str:
    channels = _base_channels(event) + _observation_channels(link)
    channels = list(dict.fromkeys(channels))
    channel_text = "、".join(channels[:5]) or "风险偏好"
    observations = [item for item in _as_list(link.get("observations")) if isinstance(item, dict)]
    review_count = sum(1 for item in observations if item.get("needs_bridge_review"))
    if review_count:
        return f"可能通过{channel_text}影响股市；附近市场序列已有 {review_count} 条达到复核阈值，应作为 Bridge 的背景线索复查，但不能当作因果证明。"
    return f"可能通过{channel_text}影响股市；目前只看到时间邻近观察，不能据此推出单独利好或利空结论。"


def _confidence(event: Dict[str, Any], link: Dict[str, Any]) -> str:
    observations = [item for item in _as_list(link.get("observations")) if isinstance(item, dict)]
    if any(item.get("needs_bridge_review") for item in observations):
        return "medium"
    if observations:
        return "low_to_medium"
    return "low"


def _boundary_note(event: Dict[str, Any]) -> str:
    source_tier = str(event.get("source_tier") or "")
    if source_tier in {"official", "official_macro", "official_filing", "company_disclosure"}:
        nature = "官方事件"
    elif source_tier == "aggregator_report":
        nature = "聚合平台材料"
    elif source_tier == "third_party_calendar":
        nature = "第三方日历材料"
    elif source_tier in {"reliable_mainstream_report", "market_narrative", "unverified_signal"}:
        nature = "媒体材料"
    else:
        nature = "候选事件材料"
    return f"这是{nature}的中文解读和股市影响假设，不是证据引用，也不进入 L1-L5。"


class NewsLayerAnalyzer:
    """Build a Chinese news interpretation sidecar without polluting L1-L5 context."""

    def build(
        self,
        *,
        event_ledger: Dict[str, Any],
        news_event_data_links: Optional[Dict[str, Any]] = None,
        output_path: Optional[str | Path] = None,
        source_paths: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        links = {
            str(item.get("event_id") or item.get("event_ref")): item
            for item in _as_list((news_event_data_links or {}).get("links"))
            if isinstance(item, dict)
        }
        events = [item for item in _as_list(event_ledger.get("events")) if isinstance(item, dict)]
        separate_scheduled = [
            item for item in _as_list(event_ledger.get("scheduled_future_events")) if isinstance(item, dict)
        ]
        realized_events = [event for event in events if event.get("collection_status") != "scheduled_future"]
        scheduled_future_events = [
            event for event in events if event.get("collection_status") == "scheduled_future"
        ] + separate_scheduled
        summaries = [self._event_summary(event, links.get(str(event.get("event_id")), {})) for event in realized_events[:20]]
        payload = {
            "schema_version": "news_layer_analysis_v1",
            "generated_at_utc": _utc_now_iso(),
            "policy": {
                "runtime_context_rule": "This sidecar is not injected into L1-L5 layer-local prompts.",
                "causality_rule": "Chinese summaries and equity impact notes are hypotheses/background, not causal proof.",
                "evidence_rule": "News layer output is never evidence_ref.",
            },
            "source_artifacts": source_paths or {},
            "aggregate_analysis": self._aggregate_analysis(summaries),
            "event_summaries": summaries,
            "scheduled_future_events": [
                self._event_summary(event, links.get(str(event.get("event_id")), {}))
                for event in scheduled_future_events[:20]
            ],
            "source_boundary": "本新闻层只基于官方事件标题、来源元数据和事件日前后市场序列观察生成；它不能替代正式指标证据，也不证明新闻导致了市场变化。",
        }
        if output_path:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def _event_summary(self, event: Dict[str, Any], link: Dict[str, Any]) -> Dict[str, Any]:
        channels = list(dict.fromkeys(_base_channels(event) + _observation_channels(link)))
        return {
            "event_ref": event.get("event_id"),
            "event_id": event.get("event_id"),
            "published_at": event.get("published_at"),
            "event_date": event.get("event_date"),
            "collection_status": event.get("collection_status"),
            "source_name": event.get("source_name"),
            "source_tier": event.get("source_tier"),
            "event_type": event.get("event_type"),
            "symbols": _as_list(event.get("symbols")),
            "title_original": event.get("title"),
            "title_zh": _localized_title(str(event.get("title") or "")),
            "summary_zh": _summary_zh(event),
            "possible_equity_impact_zh": _impact_zh(event, link),
            "pressure_channels": channels,
            "confidence": _confidence(event, link),
            "boundary_note": _boundary_note(event),
        }

    def _aggregate_analysis(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        channel_counts: Dict[str, int] = {}
        for summary in summaries:
            for channel in _as_list(summary.get("pressure_channels")):
                channel_counts[str(channel)] = channel_counts.get(str(channel), 0) + 1
        top_channels = [item[0] for item in sorted(channel_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:6]]
        policy_heavy = any(channel in top_channels for channel in ["利率预期", "折现率", "利率上行压力", "通胀压力"])
        risk_heavy = any(channel in top_channels for channel in ["风险溢价上升", "风险资产承压", "股权风险补偿要求上升"])
        mega_cap_heavy = any(channel in top_channels for channel in ["龙头盈利", "业绩指引", "指数集中度"])
        state_parts = []
        if policy_heavy:
            state_parts.append("新闻背景更偏向利率和政策预期敏感")
        if risk_heavy:
            state_parts.append("部分市场邻近观察指向风险补偿或风险资产压力")
        if mega_cap_heavy:
            state_parts.append("大型权重公司披露仍是指数叙事的重要变量")
        market_state = "；".join(state_parts) if state_parts else "当前新闻主要提供背景信息，尚未形成单一明确方向。"
        return {
            "one_sentence_zh": market_state,
            "market_state_zh": f"综合看来，{market_state}。这些新闻更适合作为解释市场脆弱性和催化剂的背景，而不是直接交易信号。",
            "equity_fragility_zh": "若新闻同时对应利率上行、波动率上升、信用利差走阔或 QQQ/HYG 下跌，股市脆弱性会增加；若这些序列没有同步恶化，则应降低新闻冲击的权重。",
            "rate_pressure_zh": "涉及美联储、通胀、就业和增长的数据会改变降息/加息预期，并通过折现率影响高估值成长股。",
            "oil_pressure_zh": "本次新闻连接器尚未接入油价序列，因此不能自动判断“油价高企导致股价下跌”；如要分析该通道，需要把 WTI/Brent 纳入 chart_time_series 和新闻连接器。",
            "risk_relief_zh": "如果后续看到 VIX/VXN 回落、HY OAS 收窄、HYG 与 QQQ 同步修复，新闻层压力可被视为缓和而非升级。",
            "unresolved_tensions_zh": "新闻层只能提出需要复核的压力通道，最终仍要由 L1-L5 指标、Bridge 冲突图和 Final 裁决共同确认。",
            "dominant_pressure_channels": top_channels,
        }


def write_news_layer_analysis(
    run_dir: str | Path,
    *,
    event_ledger: Optional[Dict[str, Any]] = None,
    news_event_data_links: Optional[Dict[str, Any]] = None,
    event_ledger_path: Optional[str | Path] = None,
    news_event_data_links_path: Optional[str | Path] = None,
) -> str:
    run_path = Path(run_dir)
    ledger_path = Path(event_ledger_path) if event_ledger_path else run_path / "news_event_ledger.json"
    links_path = Path(news_event_data_links_path) if news_event_data_links_path else run_path / "news_event_data_links.json"
    ledger_payload = event_ledger if event_ledger is not None else _load_json(ledger_path, {})
    links_payload = news_event_data_links if news_event_data_links is not None else _load_json(links_path, {})
    output_path = run_path / "news_layer_analysis.json"
    NewsLayerAnalyzer().build(
        event_ledger=ledger_payload,
        news_event_data_links=links_payload,
        output_path=output_path,
        source_paths={
            "news_event_ledger": str(ledger_path),
            "news_event_data_links": str(links_path),
        },
    )
    return str(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Chinese news layer summaries and equity impact notes.")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    output = write_news_layer_analysis(args.run_dir)
    print(json.dumps({"news_layer_analysis": output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
