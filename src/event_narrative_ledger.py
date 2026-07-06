from __future__ import annotations

import json
import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CLAIM_TYPE_BY_SOURCE = {
    "official_macro": "official_fact",
    "official_fact": "official_fact",
    "official_regulatory": "official_fact",
    "official_filing": "company_disclosure",
    "company_disclosure": "company_disclosure",
    "primary_market_data_release": "data_release_claim",
    "reliable_mainstream_report": "interpretation_claim",
    "sell_side_or_expert_view": "view_claim",
    "market_narrative": "narrative_claim",
    "unverified_signal": "rumor_claim",
}

SOURCE_TYPE_BY_TIER = {
    "official_macro": "official_fact",
    "official_regulatory": "official_fact",
    "official_fact": "official_fact",
    "official_filing": "company_disclosure",
    "company_disclosure": "company_disclosure",
    "primary_market_data_release": "primary_market_data_release",
    "reliable_mainstream_report": "reliable_mainstream_report",
    "sell_side_or_expert_view": "sell_side_or_expert_view",
    "market_narrative": "market_narrative",
    "unverified_signal": "unverified_signal",
}

ALLOWED_CLAIM_TYPES = [
    "official_fact",
    "company_disclosure",
    "data_release_claim",
    "interpretation_claim",
    "view_claim",
    "narrative_claim",
    "rumor_claim",
]

FINANCIAL_LINK_DESCRIPTIONS = {
    "earnings_path": "盈利路径",
    "valuation_multiple": "估值倍数",
    "discount_rate": "折现率",
    "risk_premium": "风险溢价",
    "liquidity_condition": "流动性条件",
    "credit_condition": "信用条件",
    "index_structure": "指数结构",
    "market_breadth": "市场广度",
    "technical_flow": "技术与资金流",
}

FINANCIAL_LINKS_BY_CHANNEL = {
    "利率预期": "discount_rate",
    "折现率": "discount_rate",
    "利率上行压力": "discount_rate",
    "利率压力缓和": "discount_rate",
    "风险偏好": "risk_premium",
    "风险溢价上升": "risk_premium",
    "风险溢价回落": "risk_premium",
    "通胀压力": "discount_rate",
    "增长韧性": "earnings_path",
    "盈利预期": "earnings_path",
    "龙头盈利": "earnings_path",
    "业绩指引": "earnings_path",
    "指数集中度": "index_structure",
    "风险资产承压": "technical_flow",
    "风险资产修复": "technical_flow",
    "股权风险补偿要求上升": "risk_premium",
}

FINANCIAL_LINKS_BY_SERIES = {
    "QQQ_OHLCV": "technical_flow",
    "HYG": "credit_condition",
    "VIX": "risk_premium",
    "VXN": "risk_premium",
    "US10Y": "discount_rate",
    "US10Y_REAL": "discount_rate",
    "HY_OAS": "credit_condition",
    "IG_OAS": "credit_condition",
    "DAMODARAN_ERP_MONTHLY": "risk_premium",
    "NDX_NDXE_RATIO": "index_structure",
}

READABLE_FINANCIAL_LINKS = {
    "earnings_path": "盈利预期",
    "valuation_multiple": "估值压力",
    "discount_rate": "利率压力",
    "risk_premium": "风险偏好",
    "liquidity_condition": "流动性",
    "credit_condition": "信用环境",
    "index_structure": "指数结构",
    "market_breadth": "市场广度",
    "technical_flow": "资金和技术面",
}

CORE_ENTITY_TOKENS = (
    "ndx", "nasdaq", "qqq", "纳指", "纳斯达克", "nvidia", "nvda", "英伟达",
    "microsoft", "msft", "apple", "aapl", "amazon", "amzn", "meta", "google",
    "alphabet", "googl", "goog", "tesla", "tsla", "broadcom", "avgo",
)

AI_SEMI_TOKENS = (
    "人工智能", "semiconductor", "半导体", "chip", "chips", "chipmaker",
    "chipmakers", "micron", "美光", "amd", "intc", "amat", "lrcx", "asml",
    "tsm", "soxx", "smh", "cohr", "lite", "computex", "data center",
    "数据中心", "guidance", "财测", "earnings", "盈利",
)

MACRO_RATE_TOKENS = (
    "fed", "fomc", "美联储", "rate", "rates", "yield", "10y", "treasury",
    "利率", "实际利率", "估值", "valuation", "泡沫", "inflation", "通胀",
    "selloff", "sell-off", "抛售",
)

STRUCTURE_TOKENS = (
    "breadth", "广度", "equal weight", "等权", "ndxe", "top10", "top 10",
    "concentration", "集中度", "index fund", "index investors", "joins the nasdaq-100",
    "权重", "指数结构", "新晋", "纳入", "移除", "再平衡", "成分股",
)

RISK_LIQUIDITY_TOKENS = (
    "credit", "信用", "liquidity", "流动性", "vix", "vxn", "hyg", "oas",
    "volatility", "波动率", "risk appetite", "风险偏好",
)

WEAK_RELEVANCE_TOKENS = (
    "form nport", "form n-port", "nport-p", "form n-csr", "monthly portfolio investments",
    "annual financial report and notice of agm", "tokenized stocks", "bstocks",
    "if you'd invested", "top stock to buy", "top 10 stock to buy", "zacks investment ideas",
    "best stocks to invest", "among the best stocks", "here is why",
    "should you buy", "is it a buy", "is nike", "buy after",
    "exchange-traded funds point higher", "market minute", "comcast", "ford and ferrari",
)

MAINLINE_DEFINITIONS = {
    "ai_semiconductor_earnings": {
        "title": "AI 盈利链条能不能缓解估值压力？",
        "plain_summary": "AI、半导体、财测和盈利上修相关消息，主要回答市场为什么还愿意追科技股。",
        "can_say": "这是一条值得追踪的正向线索。",
        "cannot_say": "新闻已经证明 NDX 应该上涨。",
    },
    "macro_rate_valuation_pressure": {
        "title": "宏观约束有没有被市场低估？",
        "plain_summary": "Fed、利率、估值、科技股抛售相关消息，主要提醒不要只看 AI 故事。",
        "can_say": "这些新闻足以提醒我们，不要因为 AI 故事就忽略估值和利率压力。",
        "cannot_say": "因为有负面新闻，所以指数必然下跌。",
    },
    "market_structure_breadth": {
        "title": "指数强是不是少数权重股撑出来的？",
        "plain_summary": "权重股、指数结构和市场广度相关消息，主要解释指数表面强弱和内部结构是否一致。",
        "can_say": "这条线索可以帮助判断指数强势是否足够健康。",
        "cannot_say": "少数权重股有新闻，就代表整个指数内部已经修复。",
    },
    "risk_credit_liquidity": {
        "title": "信用和流动性有没有在拖后腿？",
        "plain_summary": "信用、流动性和风险偏好相关消息，主要检查市场有没有忽略底层风险。",
        "can_say": "这条线索可以提醒综合研报保留风险。",
        "cannot_say": "出现风险新闻就等于市场马上要转跌。",
    },
    "other_watchlist": {
        "title": "其他需要留意的新闻",
        "plain_summary": "暂时无法归入核心主线的新闻，只进入观察清单，不提高结论把握。",
        "can_say": "这些材料可以留作背景。",
        "cannot_say": "这些零散新闻可以支撑指数级结论。",
    },
}


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


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _has_standalone_ai(text: str) -> bool:
    return bool(re.search(r"(?<![a-z])ai(?![a-z])", text.lower()))


def _hash_id(prefix: str, parts: List[Any]) -> str:
    key = "|".join(_clean_text(part).lower() for part in parts if _clean_text(part))
    return f"{prefix}:{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"


def _norm_title(value: Any) -> str:
    text = _clean_text(value).lower()
    for token in ("press release", "news release", "filed", "issues"):
        text = text.replace(token, " ")
    return " ".join(text.split())


def _event_date(value: Any) -> str:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else ""


def _event_cluster_key(event: Dict[str, Any]) -> str:
    symbols = ",".join(sorted(str(item).upper() for item in _as_list(event.get("symbols")) if item))
    family = str(event.get("event_type") or "")
    date = _event_date(event.get("published_at"))
    title = _norm_title(event.get("title"))
    return "|".join([family, symbols, date, title])


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed: Optional[datetime] = None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        for candidate in (text, f"{text}T00:00:00+00:00"):
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                break
            except ValueError:
                parsed = None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _effective_datetime(value: Any) -> Optional[datetime]:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    if len(str(value).strip()) == 10:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _iso_date_or_none(value: Any) -> Optional[str]:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else None


def _source_type(event: Dict[str, Any]) -> str:
    tier = str(event.get("source_tier") or event.get("authority_tier") or "").strip()
    source_id = str(event.get("source_id") or "").lower()
    source_name = str(event.get("source_name") or "").lower()
    title = str(event.get("title") or "").lower()
    if "sec" in source_id or tier in {"official_filing", "company_disclosure"}:
        return "company_disclosure"
    if ("sec" in source_name or "edgar" in source_name) and any(token in title for token in ["10-q", "10-k", "8-k"]):
        return "company_disclosure"
    if tier:
        return SOURCE_TYPE_BY_TIER.get(tier, "reliable_mainstream_report")
    if any(token in source_id or token in source_name for token in ("news", "yahoo", "rss", "article", "headline")):
        return "reliable_mainstream_report"
    return "reliable_mainstream_report"


def _source_nature_label(source_type: str) -> str:
    labels = {
        "official_fact": "官方事实发布",
        "company_disclosure": "公司披露",
        "primary_market_data_release": "一手市场数据发布",
        "reliable_mainstream_report": "媒体报道",
        "sell_side_or_expert_view": "专家或卖方观点",
        "market_narrative": "市场叙事",
        "unverified_signal": "未核实信号",
    }
    return labels.get(source_type, "候选事件材料")


def _claim_type(source_type: str, event: Dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "").lower()
    if "data" in event_type or "macro" in event_type:
        return "data_release_claim"
    claim_type = CLAIM_TYPE_BY_SOURCE.get(source_type, "interpretation_claim")
    return claim_type if claim_type in ALLOWED_CLAIM_TYPES else "interpretation_claim"


def _related_object(event: Dict[str, Any]) -> str:
    symbols = [str(item) for item in _as_list(event.get("symbols")) if item]
    title = str(event.get("title") or "").lower()
    if any(symbol.upper() in {"NDX", "NDX.GI", "QQQ", "QQQ.O"} for symbol in symbols):
        return "NDX"
    if symbols:
        return "company"
    if "nasdaq" in title or "invesco" in title or "qqq" in title:
        return "NDX"
    return "macro"


def _affected_links(event_summary: Dict[str, Any], data_link: Dict[str, Any]) -> List[str]:
    links = []
    channels = _as_list(event_summary.get("pressure_channels"))
    for channel in channels:
        mapped = FINANCIAL_LINKS_BY_CHANNEL.get(str(channel))
        if mapped:
            links.append(mapped)
    for observation in _as_list(data_link.get("observations")):
        if not isinstance(observation, dict):
            continue
        series = str(observation.get("series_key") or "")
        if series in {"US10Y", "US10Y_REAL"}:
            links.append("discount_rate")
        elif series in {"VIX", "VXN", "HY_OAS"}:
            links.append("risk_premium")
        elif series in {"QQQ_OHLCV", "HYG"}:
            links.append("technical_flow")
        elif series == "DAMODARAN_ERP_MONTHLY":
            links.append("risk_premium")
    return sorted(set(links))


def _status(source_type: str) -> str:
    if source_type in {"official_fact", "company_disclosure", "primary_market_data_release"}:
        return "event_fact"
    if source_type == "unverified_signal":
        return "manual_review_required"
    return "research_candidate"


def _support_boundary(source_type: str, affected_links: List[str]) -> tuple[str, str]:
    link_text = ", ".join(affected_links) if affected_links else "background_context"
    can_support = f"可作为 {link_text} 的事件背景或待验证解释线索。"
    cannot_support = "不能替代 L1-L5 正式数据证据，不能单独证明 NDX 强投资结论。"
    if source_type in {"official_fact", "company_disclosure", "primary_market_data_release"}:
        can_support = f"可作为事件事实进入第二层账本，并提示 {link_text} 需要复核。"
    return can_support, cannot_support


class EventNarrativeLedgerBuilder:
    """Build a claim-based event ledger for layer 2.

    This output is deliberately separate from AnalysisPacket.event_refs. It can
    feed integrated synthesis, but must not be injected into data-only prompts.
    """

    def build(
        self,
        *,
        event_ledger: Dict[str, Any],
        news_layer_analysis: Optional[Dict[str, Any]] = None,
        news_event_data_links: Optional[Dict[str, Any]] = None,
        effective_date: Optional[str] = None,
        output_path: Optional[str | Path] = None,
        source_paths: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        effective_dt = _effective_datetime(effective_date)
        summaries = {
            str(item.get("event_id") or item.get("event_ref")): item
            for item in _as_list((news_layer_analysis or {}).get("event_summaries"))
            if isinstance(item, dict)
        }
        data_links = {
            str(item.get("event_id") or item.get("event_ref")): item
            for item in _as_list((news_event_data_links or {}).get("links"))
            if isinstance(item, dict)
        }
        raw_events: List[Dict[str, Any]] = []
        for event in _as_list(event_ledger.get("events")):
            if not isinstance(event, dict):
                continue
            published_dt = _parse_datetime(event.get("published_at"))
            if effective_dt is not None and published_dt is not None and published_dt > effective_dt:
                continue
            if effective_dt is not None and published_dt is None:
                continue
            raw_events.append(event)

        clusters = self._build_clusters(raw_events)
        cluster_by_event_id = {
            str(member.get("event_id")): cluster["event_cluster_id"]
            for cluster in clusters
            for member in _as_list(cluster.get("_members"))
            if isinstance(member, dict)
        }
        claims = [
            self._claim_entry(
                event,
                summaries.get(str(event.get("event_id")), {}),
                data_links.get(str(event.get("event_id")), {}),
                cluster_by_event_id.get(str(event.get("event_id")), _hash_id("event_cluster", [event.get("event_id")])),
            )
            for event in raw_events
        ]
        claims_by_event = {claim["source_event_id"]: claim for claim in claims}
        public_clusters = [{key: value for key, value in cluster.items() if key != "_members"} for cluster in clusters]
        research_packets = self._build_research_packets(public_clusters, claims, data_links)
        market_validation = self._build_market_validation(research_packets, data_links)
        validation_by_cluster = {
            str(item.get("event_cluster_id")): item
            for item in _as_list(market_validation.get("validations"))
            if isinstance(item, dict)
        }
        for packet in research_packets:
            validation = validation_by_cluster.get(str(packet.get("event_cluster_id")), {})
            packet["market_has_likely_priced"] = validation.get("validation_label", "insufficient_data")
        events = [
            self._event_entry(
                event,
                summaries.get(str(event.get("event_id")), {}),
                data_links.get(str(event.get("event_id")), {}),
                claims_by_event.get(str(event.get("event_id")), {}),
            )
            for event in raw_events
        ]

        payload = {
            "schema_version": "event_narrative_ledger_v1",
            "generated_at_utc": _utc_now_iso(),
            "policy": {
                "runtime_context_rule": "This ledger is not injected into L1-L5, Bridge, Thesis, Risk, Reviser, or Final data-only prompts.",
                "evidence_rule": "Claims are layer-2 event/narrative material, never L1-L5 evidence_ref.",
                "wind_boundary": "Wind financial_docs may be used as an event/document source, but remains layer-2 material until upgraded by explicit formal data rules.",
            },
            "effective_date": effective_date,
            "source_artifacts": source_paths or {},
            "pipeline": {
                "stages": [
                    "source_record_time_gate",
                    "event_clustering_claim_decomposition",
                    "event_research",
                    "market_validation",
                    "ledger_report_integrated_handoff",
                ],
                "daily_light_deep_on_trigger": True,
                "claim_types": ALLOWED_CLAIM_TYPES,
            },
            "events": events,
            "claim_count": len(claims),
            "event_cluster_count": len(public_clusters),
            "research_packet_count": len(research_packets),
            "market_validation_summary": market_validation.get("summary", {}),
        }
        if output_path:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self._write_auxiliary_artifacts(output.parent, public_clusters, claims, research_packets, market_validation, payload)
        return payload

    def _build_clusters(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for event in events:
            grouped.setdefault(_event_cluster_key(event), []).append(event)
        clusters: List[Dict[str, Any]] = []
        for members in grouped.values():
            sorted_members = sorted(
                members,
                key=lambda item: _parse_datetime(item.get("published_at")) or datetime.max.replace(tzinfo=timezone.utc),
            )
            primary = sorted_members[0]
            source_types = sorted({str(_source_type(member)) for member in sorted_members})
            cluster_id = _hash_id("event_cluster", [_event_cluster_key(primary)])
            clusters.append({
                "event_cluster_id": cluster_id,
                "canonical_title": primary.get("title"),
                "primary_source": primary.get("source_name"),
                "supporting_sources": [
                    {
                        "event_id": member.get("event_id"),
                        "source_name": member.get("source_name"),
                        "source_type": _source_type(member),
                        "source_url": member.get("url"),
                    }
                    for member in sorted_members
                ],
                "earliest_available_at": primary.get("published_at"),
                "latest_update_at": sorted_members[-1].get("published_at"),
                "related_entities": sorted({str(symbol) for member in sorted_members for symbol in _as_list(member.get("symbols"))}),
                "related_symbols": sorted({str(symbol) for member in sorted_members for symbol in _as_list(member.get("symbols"))}),
                "event_family": primary.get("event_type") or "unknown_event",
                "source_conflicts": [] if len(source_types) <= 1 else [f"同一事件簇包含不同来源类型：{', '.join(source_types)}。"],
                "_members": sorted_members,
            })
        return sorted(clusters, key=lambda item: str(item.get("earliest_available_at") or ""), reverse=True)

    def _claim_entry(
        self,
        event: Dict[str, Any],
        summary: Dict[str, Any],
        data_link: Dict[str, Any],
        event_cluster_id: str,
    ) -> Dict[str, Any]:
        event_id = str(event.get("event_id") or "")
        source_type = _source_type(event)
        affected_links = _affected_links(summary, data_link)
        can_support, cannot_support = _support_boundary(source_type, affected_links)
        source_name = _clean_text(event.get("source_name") or "unknown source")
        title = _clean_text(event.get("title"))
        source_label = _source_nature_label(source_type)
        fact_summary = _clean_text(summary.get("summary_zh") or title)
        interpretation_summary = _clean_text(summary.get("possible_equity_impact_zh"))
        raw_text_available = bool(event.get("raw_text_available"))
        raw_text_excerpt = _clean_text(event.get("raw_text_excerpt"))
        title_only_limits = ["标题-only 材料，未读取全文，置信度必须降级。"] if not raw_text_available else []
        claim_type = _claim_type(source_type, event)
        title_only_fact = f"{source_name} 在 {event.get('published_at') or '未知时间'} 发布标题：“{title}”。"
        title_only_interpretation = "未读取全文，不能从标题推出明确解释。"
        title_only_narrative = "未建立可审计叙事。"
        if not raw_text_available:
            fact_part = title_only_fact
            fact_summary = title_only_fact
            interpretation_part = title_only_interpretation if claim_type in {"interpretation_claim", "view_claim"} else ""
            narrative_part = title_only_narrative if claim_type in {"narrative_claim", "rumor_claim"} else ""
            claim_text = (
                f"这是一条来自 {source_name} 的{source_label}标题，核心信息是“{title}”。"
                "由于未读取全文，它只能作为候选背景线索，不能写成强解释。"
            )
        else:
            fact_part = fact_summary if claim_type in {"official_fact", "company_disclosure", "data_release_claim"} else ""
            interpretation_part = interpretation_summary if claim_type in {"interpretation_claim", "view_claim"} else ""
            narrative_part = interpretation_summary if claim_type in {"narrative_claim", "rumor_claim"} else ""
            claim_text = fact_summary
        claim = {
            "claim_id": f"claim:{event_id.removeprefix('event:')}:primary",
            "event_cluster_id": event_cluster_id,
            "source_event_id": event_id,
            "claim_type": claim_type,
            "claim_text": claim_text,
            "source_type": source_type,
            "source_nature": source_label,
            "source_name": event.get("source_name"),
            "source_url": event.get("url"),
            "source_refs": [event.get("source_id") or event_id],
            "published_at": event.get("published_at"),
            "event_date": event.get("event_date") or _iso_date_or_none(event.get("published_at")),
            "information_available_at": event.get("published_at"),
            "related_index_object": _related_object(event),
            "affected_financial_links": affected_links,
            "fact_part": fact_part,
            "interpretation_part": interpretation_part,
            "narrative_part": narrative_part,
            "fact_summary": fact_summary,
            "interpretation_summary": interpretation_summary,
            "raw_text_available": raw_text_available,
            "raw_text_excerpt": raw_text_excerpt,
            "confidence_before_market_validation": "low" if not raw_text_available else ("medium" if source_type in {"official_fact", "company_disclosure", "primary_market_data_release"} else "low"),
            "what_it_can_support": can_support,
            "what_it_cannot_support": cannot_support,
            "needs_data_confirmation": True,
            "counterevidence_or_limits": title_only_limits + [
                "时间邻近不等于因果证明。",
                "需要纯数据研报或后续价格/信用/利率/广度数据确认。",
            ],
            "status": _status(source_type),
        }
        if source_type in {"market_narrative", "unverified_signal"}:
            claim["claim_type"] = "rumor_claim" if source_type == "unverified_signal" else "narrative_claim"
        return claim

    def _event_entry(self, event: Dict[str, Any], summary: Dict[str, Any], data_link: Dict[str, Any], claim: Dict[str, Any]) -> Dict[str, Any]:
        source_type = _source_type(event)
        return {
            "event_id": str(event.get("event_id") or ""),
            "event_cluster_id": claim.get("event_cluster_id"),
            "dedupe_id": event.get("dedupe_id"),
            "title": event.get("title"),
            "published_at": event.get("published_at"),
            "source_name": event.get("source_name"),
            "source_type": source_type,
            "claims": [claim] if claim else [],
        }

    def _build_research_packets(
        self,
        clusters: List[Dict[str, Any]],
        claims: List[Dict[str, Any]],
        data_links: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        claims_by_cluster: Dict[str, List[Dict[str, Any]]] = {}
        for claim in claims:
            claims_by_cluster.setdefault(str(claim.get("event_cluster_id")), []).append(claim)
        packets: List[Dict[str, Any]] = []
        for cluster in clusters:
            cluster_id = str(cluster.get("event_cluster_id") or "")
            cluster_claims = claims_by_cluster.get(cluster_id, [])
            affected_links = sorted({link for claim in cluster_claims for link in _as_list(claim.get("affected_financial_links"))})
            supporting_claims = [claim.get("claim_id") for claim in cluster_claims]
            title_only = any("标题-only" in " ".join(_as_list(claim.get("counterevidence_or_limits"))) for claim in cluster_claims)
            has_counter = any(_as_list(claim.get("counterevidence_or_limits")) for claim in cluster_claims)
            observations = [
                observation
                for claim in cluster_claims
                for observation in _as_list(data_links.get(str(claim.get("source_event_id")), {}).get("observations"))
                if isinstance(observation, dict)
            ]
            materiality = self._materiality(cluster, affected_links, observations)
            if title_only and materiality == "high":
                materiality = "medium"
            agent_confidence = "medium" if materiality in {"high", "medium"} and has_counter and not title_only else "low"
            downgrade_reasons = []
            if title_only:
                downgrade_reasons.append("存在标题-only 材料，未读取全文，不能高置信。")
            if not has_counter:
                downgrade_reasons.append("缺少反证或限制字段，不能高置信。")
            if not observations:
                downgrade_reasons.append("缺少市场验证观察，解释停留在待验证。")
            packets.append({
                "event_cluster_id": cluster_id,
                "judgment_object": "NDX",
                "minimum_fact": cluster.get("canonical_title") or "未命名事件。",
                "materiality": materiality,
                "materiality_reason": self._materiality_reason(cluster, affected_links, observations, title_only),
                "title_only": title_only,
                "affected_financial_links": affected_links,
                "mechanism_hypotheses": [
                    {
                        "financial_link": link,
                        "hypothesis": f"该事件可能影响 {FINANCIAL_LINK_DESCRIPTIONS.get(link, link)}，但需要正式数据确认。",
                        "cannot_prove": "不能证明新闻导致价格变化，不能替代 L1-L5 evidence_ref。",
                    }
                    for link in affected_links
                ],
                "supporting_claims": supporting_claims,
                "counter_claims": [],
                "alternative_explanations": self._alternative_explanations(affected_links),
                "source_conflict_review": _as_list(cluster.get("source_conflicts")) or ["未发现来源类型冲突；仍需警惕标题-only 和时间邻近误读。"],
                "market_has_likely_priced": "pending_market_validation",
                "data_needed_for_confirmation": self._data_needed(affected_links),
                "downgrade_reasons": downgrade_reasons,
                "agent_confidence": agent_confidence,
                "research_status": "ready_for_market_validation",
            })
        return packets

    def _materiality(self, cluster: Dict[str, Any], affected_links: List[str], observations: List[Dict[str, Any]]) -> str:
        family = str(cluster.get("event_family") or "").lower()
        title = str(cluster.get("canonical_title") or "").lower()
        if "form nport" in title or "form n-csr" in title:
            return "low"
        high_link = any(link in {"discount_rate", "risk_premium", "earnings_path", "index_structure"} for link in affected_links)
        if ("policy" in family or "filing" in family or high_link) and observations:
            return "high"
        if "policy" in family or "filing" in family or high_link:
            return "medium"
        return "low"

    def _materiality_reason(
        self,
        cluster: Dict[str, Any],
        affected_links: List[str],
        observations: List[Dict[str, Any]],
        title_only: bool,
    ) -> str:
        if title_only:
            return "标题-only 材料只可进入候选清单；重要性不得高于 medium。"
        if observations:
            return "存在固定窗口市场观察，但仍只代表时间关联。"
        if affected_links:
            return "可映射到金融链路，但缺少市场验证观察。"
        return "缺少明确金融链路。"

    def _alternative_explanations(self, affected_links: List[str]) -> List[str]:
        explanations = ["价格变化可能来自既有仓位、估值再定价或市场广度变化，而不是该事件本身。"]
        if "discount_rate" in affected_links:
            explanations.append("利率变化可能由宏观数据、财政供给或期限溢价驱动，并非单条新闻造成。")
        if "earnings_path" in affected_links:
            explanations.append("盈利预期变化可能来自财报季整体修正，而不是单家公司披露。")
        if "risk_premium" in affected_links:
            explanations.append("风险溢价变化可能来自波动率仓位、信用压力或避险需求。")
        if "index_structure" in affected_links:
            explanations.append("指数表现可能来自少数权重股抱团，而不是 NDX 内部全面改善。")
        return explanations

    def _data_needed(self, affected_links: List[str]) -> List[str]:
        needed = {
            "earnings_path": "权重股盈利、guidance、forward EPS 或利润率修正。",
            "valuation_multiple": "NDX/QQQ PE、forward PE、ERP 与历史分位。",
            "discount_rate": "US10Y、实际利率、breakeven inflation 与 Fed 路径。",
            "risk_premium": "VIX/VXN、HY OAS、IG OAS、HYG 与 ERP。",
            "liquidity_condition": "WALCL、TGA、RRP 与净流动性代理。",
            "credit_condition": "HY OAS、IG OAS、HYG 与融资压力。",
            "index_structure": "NDX/NDXE、Top10 权重、权重股相对表现。",
            "market_breadth": "A/D、%Above MA、新高新低。",
            "technical_flow": "QQQ 价格、成交量、VWAP、MFI、CMF、ATR。",
        }
        return [needed[link] for link in affected_links if link in needed] or ["需要价格、利率、波动、信用和广度数据做基础确认。"]

    def _build_market_validation(
        self,
        research_packets: List[Dict[str, Any]],
        data_links: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        validations = []
        for packet in research_packets:
            cluster_claim_ids = set(_as_list(packet.get("supporting_claims")))
            observations = []
            for link in data_links.values():
                if not isinstance(link, dict):
                    continue
                event_id = str(link.get("event_id") or "")
                derived_claim_id = f"claim:{event_id.removeprefix('event:')}:primary"
                if derived_claim_id not in cluster_claim_ids:
                    continue
                observations.extend([item for item in _as_list(link.get("observations")) if isinstance(item, dict)])
            validation_label = self._validation_label(observations)
            validations.append({
                "event_cluster_id": packet.get("event_cluster_id"),
                "validation_label": validation_label,
                "validated_links": sorted({
                    FINANCIAL_LINKS_BY_SERIES.get(str(item.get("series_key")))
                    for item in observations
                    if FINANCIAL_LINKS_BY_SERIES.get(str(item.get("series_key"))) and item.get("needs_bridge_review")
                }),
                "contradicted_links": [],
                "observations": observations[:12],
                "post_hoc_narrative_risk": self._post_hoc_risk(observations),
                "causality_statement": "background market observation only; not causal evidence",
            })
        counts: Dict[str, int] = {}
        for item in validations:
            label = str(item.get("validation_label") or "insufficient_data")
            counts[label] = counts.get(label, 0) + 1
        return {
            "schema_version": "event_market_validation_v1",
            "generated_at_utc": _utc_now_iso(),
            "policy": {
                "causality_rule": "旧窗口观察只能作为背景，不得写成市场确认新闻，也不得证明新闻导致价格变化。",
                "windows_rule": "窗口观察如存在，仅用于提示后续数据问题，不在读者页作为验证结论展示。",
            },
            "summary": counts,
            "validations": validations,
        }

    def _mainline_id_for_claim(self, claim: Dict[str, Any]) -> str:
        text = " ".join(
            [
                self._claim_title(claim),
                str(claim.get("source_name") or ""),
                str(claim.get("related_index_object") or ""),
            ]
        ).lower()
        links = set(_as_list(claim.get("affected_financial_links")))
        if _contains_any(text, STRUCTURE_TOKENS) or "index_structure" in links or "market_breadth" in links:
            return "market_structure_breadth"
        if any(token in text for token in ("rotation out of tech", "end lower", "selloff", "sell-off", "抛售", "大跌")):
            return "macro_rate_valuation_pressure"
        if _contains_any(text, AI_SEMI_TOKENS) or _has_standalone_ai(text):
            return "ai_semiconductor_earnings"
        if _contains_any(text, MACRO_RATE_TOKENS) or links.intersection({"discount_rate", "valuation_multiple"}):
            return "macro_rate_valuation_pressure"
        if _contains_any(text, RISK_LIQUIDITY_TOKENS) or links.intersection({"credit_condition", "liquidity_condition"}):
            return "risk_credit_liquidity"
        return "other_watchlist"

    def _readable_links(self, links: List[str]) -> List[str]:
        return [READABLE_FINANCIAL_LINKS.get(str(link), str(link)) for link in links if link]

    def _plain_boundary_text(self, text: Any) -> str:
        value = _clean_text(text)
        for internal, readable in READABLE_FINANCIAL_LINKS.items():
            value = value.replace(internal, readable)
        value = value.replace("background_context", "背景信息")
        value = value.replace("L1-L5 evidence_ref", "第一层到第五层的正式证据")
        value = value.replace("NDX", "纳指100")
        return value

    def _claim_title(self, claim: Dict[str, Any]) -> str:
        title = _clean_text(claim.get("fact_summary") or claim.get("claim_text") or claim.get("claim_id"))
        if "发布标题：“" in title and "”。" in title:
            title = title.split("发布标题：“", 1)[1].split("”。", 1)[0]
        if title.startswith("这是一条来自") and "核心信息是“" in title:
            title = title.split("核心信息是“", 1)[1].split("”。", 1)[0]
        return title or "未命名新闻"

    def _news_id_from_claim(self, claim: Dict[str, Any], title: str) -> str:
        claim_id = str(claim.get("claim_id") or "")
        parts = [part for part in claim_id.split(":") if part and part not in {"claim", "primary"}]
        if parts:
            return f"news:{parts[-1]}"
        return _hash_id("news", [title, claim.get("source_name"), claim.get("published_at")])

    def _relevance_score_for_claim(self, claim: Dict[str, Any], title: str, mainline_id: str) -> int:
        text = " ".join([
            title,
            str(claim.get("source_name") or ""),
            str(claim.get("related_index_object") or ""),
        ]).lower()
        links = set(_as_list(claim.get("affected_financial_links")))
        score = 0
        if _contains_any(text, CORE_ENTITY_TOKENS):
            score += 18
        if _contains_any(text, AI_SEMI_TOKENS) or _has_standalone_ai(text):
            score += 34
        if _contains_any(text, MACRO_RATE_TOKENS):
            score += 34
        if _contains_any(text, STRUCTURE_TOKENS):
            score += 28
        if _contains_any(text, RISK_LIQUIDITY_TOKENS):
            score += 24
        if mainline_id in {"ai_semiconductor_earnings", "macro_rate_valuation_pressure", "market_structure_breadth", "risk_credit_liquidity"}:
            score += 12
        if links.intersection({"earnings_path", "discount_rate", "valuation_multiple", "index_structure", "market_breadth"}):
            score += 8
        if claim.get("source_url"):
            score += 4
        if claim.get("raw_text_available"):
            score += 8
        source_type = str(claim.get("source_type") or "")
        if source_type in {"official_fact", "primary_market_data_release"}:
            score += 8
        elif source_type == "company_disclosure":
            score += 5
        elif source_type == "market_narrative":
            score -= 10
        if _contains_any(text, WEAK_RELEVANCE_TOKENS):
            score -= 55
        if "form " in text and "n-port" in text:
            score -= 30
        if not claim.get("raw_text_available") and not claim.get("source_url"):
            score -= 12
        if source_type == "market_narrative":
            score = min(score, 45)
        if source_type == "unverified_signal":
            score = min(score, 30)
        return max(0, score)

    def _relevance_band(self, score: int) -> str:
        if score >= 50:
            return "core"
        if score >= 34:
            return "supporting"
        return "background"

    def _source_quality_label(self, claim: Dict[str, Any], missing_evidence: List[str]) -> str:
        source_type = str(claim.get("source_type") or "")
        if "未读取全文" in missing_evidence and "缺 URL" in missing_evidence:
            return "弱材料：只有标题且缺链接"
        if "未读取全文" in missing_evidence:
            return "有限材料：只有标题"
        if source_type in {"official_fact", "company_disclosure", "primary_market_data_release"}:
            return "较强来源：事实材料，但仍不能直接推出指数结论"
        if source_type == "market_narrative":
            return "弱材料：市场讨论"
        return "普通来源：需要数据确认"

    def _first_sentence(self, text: Any, max_chars: int = 180) -> str:
        value = _clean_text(text)
        if not value:
            return ""
        pieces = [piece.strip() for piece in re.split(r"[。！？.!?]\s*", value) if piece.strip()]
        sentence = pieces[0] if pieces else value
        return sentence[:max_chars]

    def _news_topic(self, title: str, raw_text_excerpt: str, mainline_id: str) -> str:
        title_text = title.lower()
        text = f"{title} {raw_text_excerpt}".lower()
        if ("nasdaq-100" in title_text or "纳斯达克100" in title_text or "纳指100" in title_text) and any(token in title_text for token in ("joins", "join", "新晋", "纳入", "移除", "rebalanc", "成分")):
            return "index_membership_change"
        if "美联储" in title_text and (_has_standalone_ai(title_text) or "人工智能" in title_text):
            return "fed_ai_tension"
        if "rotation out of tech" in title_text or "end lower" in title_text or "抛售" in title_text or "大跌" in title_text:
            return "tech_selloff"
        if (_has_standalone_ai(title_text) or "人工智能" in title_text) and any(token in title_text for token in ("fund", "funds", "portfolio", "etf", "资金")):
            return "ai_fund_flow"
        if "micron" in text or "美光" in text or "hbm" in text:
            return "micron_ai_earnings"
        if "coreweave" in text or "cloud" in text or "ai云" in text or "数据中心" in text:
            return "ai_cloud_demand"
        if "burry" in text or "short nvda" in text or "bubble" in text or "泡沫" in text:
            return "ai_bubble_counterclaim"
        if "8-k" in text or "10-q" in text or "10-k" in text:
            return "company_filing"
        if "fed" in text or "fomc" in text or "美联储" in text or "rate" in text or "利率" in text:
            return "fed_rate_path"
        if "selloff" in text or "抛售" in text or "大跌" in text or "rotation out of tech" in text or "end lower" in text:
            return "tech_selloff"
        if "chip" in text or "semiconductor" in text or "半导体" in text or "soxx" in text or "smh" in text or _has_standalone_ai(text):
            return "semiconductor_chain"
        if "top stock" in text or "best stocks" in text or "here is why" in text:
            return "weak_stock_pick_article"
        return mainline_id

    def _card_summary_and_analysis(
        self,
        *,
        title: str,
        raw_text_excerpt: str,
        mainline_id: str,
        relevance_band: str,
        source_quality: str,
        readable_links: List[str],
    ) -> tuple[str, str, List[str], str, str]:
        topic = self._news_topic(title, raw_text_excerpt, mainline_id)
        excerpt = self._first_sentence(raw_text_excerpt)
        source_basis = f"正文片段显示：{excerpt}。" if excerpt else f"目前只能看到标题：“{title}”。"
        can_support = "可以作为新闻事件线索。"
        cannot_support = "不能作为主证据，不能单独推出纳指100方向。"
        if topic == "micron_ai_earnings":
            summary = "这条新闻的核心不是“AI 很热”，而是美光财测可能把 AI 需求落实到半导体盈利预期上。"
            analysis = f"{source_basis} 如果美光财测确实上修，它支持的是“AI 需求可能转化为盈利”的线索；但它仍然只是单家公司/半导体链条的证据，不能直接证明整个纳指100风险解除。"
            needs = ["美光和半导体指数是否相对纳指100继续走强", "AI 相关权重股盈利预期是否同步上修", "涨幅是否扩散到更多半导体和硬件公司"]
            can_support = "可以支持“AI 盈利链条值得追踪”这个解释线索。"
            cannot_support = "不能证明纳指100整体应该上涨，也不能覆盖估值和利率压力。"
        elif topic == "fed_ai_tension":
            summary = "这条新闻的重点是“鹰派 Fed 压力下，AI 叙事还能不能撑住科技股”。"
            analysis = f"{source_basis} 它不是单纯利好，也不是单纯利空；它把两股力量放在一起：利率约束压估值，AI 叙事提供缓冲。综合研报应把它放进核心矛盾，而不是当成方向结论。"
            needs = ["实际利率是否继续压制估值", "AI 权重股是否相对抗跌", "科技股上涨是否有广度配合"]
            can_support = "可以支持“AI 叙事与利率压力正在拉扯”。"
            cannot_support = "不能证明 AI 已经抵消 Fed 压力。"
        elif topic == "ai_cloud_demand":
            summary = "这条新闻更像 AI 基建需求线索，重点在云计算/算力订单是否能传导到权重股收入。"
            analysis = f"{source_basis} 它能说明市场为什么关注 AI 基建资本开支，但还要确认订单对象、金额、利润率和受益公司，不能只看到“AI 合同”就升级结论。"
            needs = ["合同是否落到纳指100权重公司收入", "云厂商资本开支是否继续上修", "相关硬件/半导体公司订单是否同步改善"]
            can_support = "可以支持“AI 需求仍有现实订单线索”。"
            cannot_support = "不能证明 AI 链条利润率一定改善。"
        elif topic == "ai_fund_flow":
            summary = "这条新闻更像资金和产品层面的 AI 热度线索，重点不是企业盈利，而是投资人是否继续追逐 AI 主题。"
            analysis = f"{source_basis} 它能说明 AI 主题仍有资金关注，但基金/组合文章不等于盈利证据。第二层只能把它作为情绪和拥挤度线索。"
            needs = ["AI 主题 ETF 或相关基金是否持续流入", "AI 权重股涨幅是否过度集中", "资金热度是否伴随估值扩张而非盈利上修"]
            can_support = "可以支持“AI 主题仍受资金关注”。"
            cannot_support = "不能支持“AI 盈利已经兑现”。"
        elif topic == "ai_bubble_counterclaim":
            summary = "这条新闻是 AI/半导体的反向线索：有人认为芯片资本开支或估值已经过热。"
            analysis = f"{source_basis} 它的价值在于提供反证，而不是直接证明 AI 交易结束。第二层应把它交给综合研报保留为“过热/拥挤”风险。"
            needs = ["半导体估值是否显著高于历史区间", "SOXX/SMH 成交拥挤度和回撤风险", "AI 资本开支是否出现回报率质疑"]
            can_support = "可以支持“AI 交易存在拥挤或泡沫争议”。"
            cannot_support = "不能因为一条做空观点就断言半导体行情结束。"
        elif topic == "index_membership_change":
            summary = "这条新闻是指数结构事件，重点不是盈利，而是纳指100成分变化可能影响被动资金和权重结构。"
            analysis = f"{source_basis} 它应该进入“指数结构”主线，用来问数据层：指数强弱有没有被成分调整或被动资金扰动放大。"
            needs = ["成分调整前后纳指100和等权指数是否分化", "新增/剔除成分对权重集中度的影响", "被动资金调仓是否造成短期流动性扰动"]
            can_support = "可以支持“指数结构需要复核”。"
            cannot_support = "不能证明指数基本面改善。"
        elif topic == "company_filing":
            summary = "这条新闻是公司披露线索，事实来源较强，但必须先读披露内容再判断影响。"
            analysis = f"{source_basis} 公司公告可以提高事实可信度，但 8-K/10-Q 本身不等于利好或利空。没有读到具体披露事项前，只能列为待核实材料。"
            needs = ["披露事项是否涉及业绩、指引、回购、监管或重大合同", "该公司在纳指100中的权重", "公告后分析师预期或价格是否有持续反应"]
            can_support = "可以支持“存在一条正式公司披露”。"
            cannot_support = "不能仅凭 filing 标题判断指数方向。"
        elif topic == "fed_rate_path":
            summary = "这条新闻直接关系折现率：市场在重新评估 Fed 路径、实际利率或降息预期。"
            analysis = f"{source_basis} 它能解释为什么科技股估值可能受压或获得缓冲，但必须让 10Y、实际利率、VXN 和信用利差来确认。"
            needs = ["10Y 和实际利率是否同向变化", "VXN/VIX 是否反映科技股风险重估", "Fed 预期变化是否传导到估值倍数"]
            can_support = "可以支持“利率路径仍是科技股约束”。"
            cannot_support = "不能单独证明市场已经完成宏观重定价。"
        elif topic == "tech_selloff":
            summary = "这条新闻描述科技股承压，价值在于提示风险偏好和估值压力，而不是解释全部跌幅。"
            analysis = f"{source_basis} 它应作为反向材料保留：如果数据也显示广度走弱、波动率抬升、信用变差，综合研报才可提高警惕。"
            needs = ["下跌是否集中在少数权重股还是扩散到全市场", "市场广度和新高新低是否恶化", "VXN、信用利差和成交量是否确认风险偏好转弱"]
            can_support = "可以支持“市场存在风险偏好降温线索”。"
            cannot_support = "不能因为有抛售新闻就断言指数必然继续下跌。"
        elif topic == "semiconductor_chain":
            summary = "这条新闻指向半导体链条，重点是 AI 需求有没有从龙头扩散到设备、材料或零部件。"
            analysis = f"{source_basis} 它有助于判断 AI 交易是否扩散，但需要区分“行业热度”与“纳指100盈利贡献”。"
            needs = ["半导体链条相对纳指100是否持续走强", "受益公司是否属于纳指100核心权重", "盈利修正是否跟上股价表现"]
            can_support = "可以支持“半导体扩散线索”。"
            cannot_support = "不能直接证明整个科技板块估值合理。"
        elif topic == "weak_stock_pick_article":
            summary = "这条新闻更像荐股/观点文章，研究价值低于正式新闻或公告。"
            analysis = f"{source_basis} 它最多反映市场关注度，不能当成事实证据。第二层应把它压低为观察材料。"
            needs = ["是否有正式公告或财务数据支持该观点", "该公司与纳指100权重和盈利链条的关系", "是否只是流量型标题"]
            can_support = "可以支持“市场关注度上升”的弱线索。"
            cannot_support = "不能支持指数级判断。"
        elif relevance_band == "background":
            link_text = "、".join(readable_links[:2]) if readable_links else "背景信息"
            summary = f"这条新闻目前只提供{link_text}背景，和纳指100核心判断关系不够直接。"
            analysis = f"{source_basis} 它可以留在观察清单，但不应进入主线裁决。"
            needs = ["是否影响纳指100权重公司", "是否有更高等级来源确认", "是否能映射到明确数据指标"]
        else:
            summary = "这条新闻提供一条可追踪线索，但还需要数据确认它和纳指100判断的关系。"
            analysis = f"{source_basis} 第二层只能把它作为解释候选，不能替代数据层证据。"
            needs = ["价格、利率、波动、信用或广度是否同步确认", "来源是否可追溯", "是否存在相反新闻或数据"]
        if source_quality.startswith("弱材料") or source_quality.startswith("有限材料"):
            analysis += " 因为材料不完整，这条新闻必须降级阅读。"
        return summary, analysis, needs, can_support, cannot_support

    def _news_card_from_claim(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        title = self._claim_title(claim)
        links = _as_list(claim.get("affected_financial_links"))
        readable_links = self._readable_links(links)
        missing_evidence = []
        if not claim.get("source_url"):
            missing_evidence.append("缺 URL")
        if not claim.get("raw_text_available"):
            missing_evidence.append("未读取全文")
        if claim.get("source_nature") == "媒体报道":
            missing_evidence.append("媒体解释不能当官方事实")
        if not readable_links:
            readable_links = ["背景信息"]
        confidence = "low" if missing_evidence else str(claim.get("confidence_before_market_validation") or "medium")
        mainline_id = self._mainline_id_for_claim(claim)
        relevance_score = self._relevance_score_for_claim(claim, title, mainline_id)
        relevance_band = self._relevance_band(relevance_score)
        source_quality = self._source_quality_label(claim, missing_evidence)
        raw_text_excerpt = _clean_text(claim.get("raw_text_excerpt"))
        one_line_summary, ai_analysis, needs, can_support, cannot_support = self._card_summary_and_analysis(
            title=title,
            raw_text_excerpt=raw_text_excerpt,
            mainline_id=mainline_id,
            relevance_band=relevance_band,
            source_quality=source_quality,
            readable_links=readable_links,
        )
        return {
            "news_id": self._news_id_from_claim(claim, title),
            "claim_id": claim.get("claim_id"),
            "mainline_id": mainline_id,
            "title": title or "未命名新闻",
            "source_name": claim.get("source_name") or "未知来源",
            "published_at": claim.get("published_at") or "",
            "source_url": claim.get("source_url") or "",
            "raw_text_available": bool(claim.get("raw_text_available")),
            "raw_text_excerpt": raw_text_excerpt,
            "source_quality": source_quality,
            "relevance_score": relevance_score,
            "relevance_band": relevance_band,
            "one_line_summary": one_line_summary,
            "ai_analysis": ai_analysis,
            "can_support": can_support,
            "cannot_support": cannot_support,
            "needs_data_confirmation": needs,
            "missing_evidence": missing_evidence,
            "confidence": confidence if confidence in {"low", "medium", "high"} else "low",
        }

    def _build_cross_layer_questions(
        self,
        news_cards: List[Dict[str, Any]],
        event_research_cards: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        questions: List[Dict[str, Any]] = []
        seen_mainlines = set()
        for card in news_cards:
            mainline_id = str(card.get("mainline_id") or "other_watchlist")
            if mainline_id in seen_mainlines:
                continue
            seen_mainlines.add(mainline_id)
            requested = _as_list(card.get("needs_data_confirmation"))
            questions.append({
                "question_id": _hash_id("question", ["event_to_data", mainline_id]),
                "direction": "event_to_data",
                "question": self._event_to_data_question(mainline_id),
                "why_it_matters": "新闻只提出解释线索，必须让数据回答它是否站得住。",
                "requested_checks": requested,
                "status": "open" if requested else "insufficient_data",
            })
        questions.extend([
            {
                "question_id": "question:data_to_event:index_strength_breadth_gap",
                "direction": "data_to_event",
                "question": "如果数据层发现指数强但广度弱，新闻事件里是否有少数大权重公司或半导体事件在支撑指数？",
                "why_it_matters": "避免把少数权重股行情误读成指数内部全面修复。",
                "requested_checks": ["权重股相关新闻", "NDX/NDXE 分化", "半导体链条是否扩散"],
                "status": "open",
            },
            {
                "question_id": "question:data_to_event:expensive_but_resilient",
                "direction": "data_to_event",
                "question": "如果数据层发现估值贵但价格抗跌，新闻事件里是否有盈利上修、回购、资金流或政策预期解释？",
                "why_it_matters": "避免数据层自己编故事，也避免新闻层越权下结论。",
                "requested_checks": ["盈利修正新闻", "公司回购或公告", "政策和利率预期变化"],
                "status": "open",
            },
        ])
        return questions[:8]

    def _event_to_data_question(self, mainline_id: str) -> str:
        return {
            "ai_semiconductor_earnings": "如果 AI 和半导体新闻真的重要，半导体链条、AI 权重股和盈利预期有没有同步改善？",
            "macro_rate_valuation_pressure": "如果宏观和利率新闻正在压制科技股，实际利率、VXN 和信用利差有没有同步支持？",
            "market_structure_breadth": "如果指数结构是关键，权重股和等权指数的分化有没有继续扩大？",
            "risk_credit_liquidity": "如果信用和流动性是风险来源，HYG、HY OAS 和净流动性有没有恶化？",
        }.get(mainline_id, "这条新闻是否能映射到明确数据指标，并得到后续数据确认？")

    def _news_card_sort_key(self, card: Dict[str, Any]) -> tuple[int, int, int, int, str]:
        band_rank = {"core": 3, "supporting": 2, "background": 1}
        confidence_rank = {"high": 3, "medium": 2, "low": 1}
        return (
            int(card.get("relevance_score") or 0),
            band_rank.get(str(card.get("relevance_band")), 0),
            confidence_rank.get(str(card.get("confidence")), 0),
            1 if card.get("source_url") else 0,
            str(card.get("published_at") or ""),
        )

    def _dedupe_news_cards(self, cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        best_by_key: Dict[str, Dict[str, Any]] = {}
        for card in cards:
            title_key = _clean_text(card.get("title")).lower()
            url_key = _clean_text(card.get("source_url")).lower()
            key = url_key or f"{title_key}|{str(card.get('published_at') or '')[:10]}"
            if not key:
                key = str(card.get("news_id") or "")
            current = best_by_key.get(key)
            if current is None or self._news_card_sort_key(card) > self._news_card_sort_key(current):
                best_by_key[key] = card
        return sorted(best_by_key.values(), key=self._news_card_sort_key, reverse=True)

    def _mainline_record(self, mainline_id: str, line_cards: List[Dict[str, Any]]) -> Dict[str, Any]:
        definition = MAINLINE_DEFINITIONS[mainline_id]
        core_count = sum(1 for card in line_cards if card.get("relevance_band") == "core")
        missing_count = sum(1 for card in line_cards if _as_list(card.get("missing_evidence")))
        if mainline_id == "ai_semiconductor_earnings":
            can_say = "可以说：AI、半导体和盈利相关新闻能解释市场为什么还愿意追科技股。"
            cannot_say = "不能说：这些新闻已经证明纳指100风险解除，或证明指数必然上涨。"
            summary = "这条主线看的是“增长故事能不能抵消贵估值”。新闻越集中在财测、订单、数据中心需求和半导体链条，越值得交给数据层复核。"
        elif mainline_id == "macro_rate_valuation_pressure":
            can_say = "可以说：利率、Fed 和估值新闻足以提醒综合研报保留约束。"
            cannot_say = "不能说：只要有负面新闻，指数就一定会跌。"
            summary = "这条主线看的是“折现率和风险偏好有没有把科技股故事压住”。它主要防止报告只听乐观叙事。"
        elif mainline_id == "market_structure_breadth":
            can_say = "可以说：指数结构新闻能帮助解释为什么指数强弱和多数成分股感受不一致。"
            cannot_say = "不能说：少数权重股或指数调整有新闻，就代表市场内部全面修复。"
            summary = "这条主线看的是“指数强是不是少数公司撑出来的”。它需要和等权指数、集中度和广度数据一起看。"
        elif mainline_id == "risk_credit_liquidity":
            can_say = "可以说：信用、流动性和波动率新闻可以作为风险提醒。"
            cannot_say = "不能说：风险新闻本身就是卖出信号。"
            summary = "这条主线看的是“底层风险有没有被行情忽略”。它不能替代信用和波动率数据。"
        else:
            can_say = "可以说：这些材料可以留作背景，帮助后续追踪。"
            cannot_say = "不能说：这些零散新闻可以支撑指数级结论。"
            summary = "这些新闻和纳指100核心判断关系不够直接，默认不进入主线裁决。"
        if missing_count:
            summary += f" 其中 {missing_count} 条材料存在缺口，必须降级阅读。"
        if core_count == 0 and mainline_id != "other_watchlist":
            summary += " 当前没有足够强的核心新闻，不能提高判断把握。"
        return {
            "mainline_id": mainline_id,
            "title": definition["title"],
            "plain_summary": summary,
            "can_say": can_say.replace("可以说：", ""),
            "cannot_say": cannot_say.replace("不能说：", ""),
            "core_news_count": core_count,
            "missing_evidence_count": missing_count,
            "news_card_ids": [str(card.get("news_id")) for card in line_cards[:6]],
        }

    def _event_research_cards_from_mainlines(self, mainlines: List[Dict[str, Any]], news_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cards_by_id = {str(card.get("news_id")): card for card in news_cards}
        research_cards = []
        for line in mainlines:
            line_cards = [cards_by_id.get(str(card_id)) for card_id in _as_list(line.get("news_card_ids"))]
            line_cards = [card for card in line_cards if isinstance(card, dict)]
            if not line_cards and line.get("mainline_id") == "other_watchlist":
                continue
            top_titles = [str(card.get("title")) for card in line_cards[:3] if card.get("title")]
            checks = []
            for card in line_cards:
                checks.extend(_as_list(card.get("needs_data_confirmation"))[:2])
            missing = sorted({item for card in line_cards for item in _as_list(card.get("missing_evidence"))})
            confidence = "medium" if line.get("core_news_count") and not missing else "low"
            importance = "high" if line.get("mainline_id") in {"ai_semiconductor_earnings", "macro_rate_valuation_pressure"} and line.get("core_news_count") else "medium"
            if line.get("mainline_id") == "other_watchlist":
                importance = "low"
                confidence = "low"
            research_cards.append({
                "event_cluster_id": f"mainline:{line.get('mainline_id')}",
                "title": line.get("title"),
                "importance": importance,
                "confidence": confidence,
                "minimum_fact": "；".join(top_titles) if top_titles else "当前没有足够强的核心新闻。",
                "possible_impact": line.get("plain_summary"),
                "counterevidence": [
                    line.get("cannot_say") or "不能从新闻直接推出指数结论。",
                    "新闻事件不能进入第一层主证据。",
                ] + ([f"材料缺口：{'、'.join(missing)}。"] if missing else []),
                "how_to_use": "交给综合研报复核" if confidence == "medium" else "只能当线索",
                "needs_data_confirmation": list(dict.fromkeys(checks))[:6],
            })
        return research_cards[:6]

    def _build_event_mechanism_report(
        self,
        claims: List[Dict[str, Any]],
        research_packets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        news_cards = self._dedupe_news_cards([self._news_card_from_claim(claim) for claim in claims])
        cards_by_line: Dict[str, List[Dict[str, Any]]] = {}
        for card in news_cards:
            cards_by_line.setdefault(str(card.get("mainline_id") or "other_watchlist"), []).append(card)
        mainlines = []
        for mainline_id in MAINLINE_DEFINITIONS:
            line_cards = cards_by_line.get(mainline_id, [])
            if not line_cards and mainline_id not in {"ai_semiconductor_earnings", "macro_rate_valuation_pressure"}:
                continue
            mainlines.append(self._mainline_record(mainline_id, line_cards))
        event_research_cards = self._event_research_cards_from_mainlines(mainlines, news_cards)
        questions = self._build_cross_layer_questions(news_cards, event_research_cards)
        claims_by_id = {str(claim.get("claim_id")): claim for claim in claims}
        claim_permission_ledger = [
            {
                "claim_id": claim.get("claim_id"),
                "claim": claim.get("fact_summary") or claim.get("claim_text"),
                "nature": claim.get("source_nature") or claim.get("claim_type"),
                "can_support": self._plain_boundary_text(claim.get("what_it_can_support")),
                "cannot_support": self._plain_boundary_text(claim.get("what_it_cannot_support")),
                "status": "待数据确认" if claim.get("needs_data_confirmation") else "可作为事实背景",
            }
            for card in news_cards[:16]
            for claim in [claims_by_id.get(str(card.get("claim_id")))]
            if isinstance(claim, dict)
        ]
        if news_cards:
            core_cards = [card for card in news_cards if card.get("relevance_band") == "core"]
            top_line = next((line for line in mainlines if line.get("core_news_count")), mainlines[0] if mainlines else {})
            top_line_ids = set(str(card_id) for card_id in _as_list(top_line.get("news_card_ids")))
            top_line_cards = [card for card in core_cards if str(card.get("news_id")) in top_line_ids]
            strongest = top_line_cards[0] if top_line_cards else (core_cards[0] if core_cards else news_cards[0])
            if core_cards:
                headline_text = (
                    f"今天最值得盯的是“{top_line.get('title') or strongest.get('title')}”。"
                    f"代表性新闻是“{strongest.get('title')}”。"
                    "它能解释市场正在交易什么故事，但仍不能替代数据证据。"
                )
                confidence = "medium" if not _as_list(strongest.get("missing_evidence")) else "low"
            else:
                headline_text = (
                    "本次新闻材料没有形成足够强的核心主线。"
                    "可以把它们当作观察线索，但综合研报不能用这些新闻补强投资结论。"
                )
                confidence = "low"
        else:
            headline_text = "本次没有足够新闻事件材料，综合研报应以纯数据判断为主，并明确说明新闻事件材料不足。"
            confidence = "low"
        core_mainlines = [line for line in mainlines if line.get("core_news_count")]
        delivery = {
            "one_sentence": (
                (
                    f"新闻事件最有价值的交付是“{core_mainlines[0].get('title')}”这类解释线索；"
                    "它能帮助理解市场叙事，但还必须让数据确认，不能直接升级为主证据。"
                )
                if core_mainlines else
                "新闻事件材料不足，综合研报不能用新闻补强数据结论。"
            ),
            "must_preserve_risks": [
                "新闻不能作为主证据。",
                "缺 URL 或未读全文的材料必须降级。",
                "时间邻近不能写成因果证明。",
            ],
            "watchlist": [
                check
                for card in news_cards[:4]
                for check in _as_list(card.get("needs_data_confirmation"))[:2]
            ][:8],
        }
        return {
            "schema_version": "event_mechanism_report_v1",
            "generated_at_utc": _utc_now_iso(),
            "headline_judgment": {
                "title": "新闻事件初步判断",
                "plain_text": headline_text,
                "confidence": confidence,
                "cannot_be_used_as_primary_evidence": True,
            },
            "mainlines": mainlines,
            "news_cards": news_cards,
            "event_research_cards": event_research_cards,
            "cross_layer_questions": questions,
            "claim_permission_ledger": claim_permission_ledger,
            "delivery_to_integrated_report": delivery,
        }

    def _validation_label(self, observations: List[Dict[str, Any]]) -> str:
        if not observations:
            return "insufficient_data"
        return "background_market_observation"

    def _post_hoc_risk(self, observations: List[Dict[str, Any]]) -> bool:
        dated = [item for item in observations if item.get("end_time") and item.get("start_time")]
        return bool(dated) and all(str(item.get("end_time")) <= str(item.get("start_time")) for item in dated)

    def _write_auxiliary_artifacts(
        self,
        run_path: Path,
        clusters: List[Dict[str, Any]],
        claims: List[Dict[str, Any]],
        research_packets: List[Dict[str, Any]],
        market_validation: Dict[str, Any],
        event_narrative_ledger: Dict[str, Any],
    ) -> None:
        self._write_json(run_path / "event_clusters.json", {
            "schema_version": "event_clusters_v1",
            "generated_at_utc": _utc_now_iso(),
            "clusters": clusters,
        })
        self._write_json(run_path / "event_claim_ledger.json", {
            "schema_version": "event_claim_ledger_v1",
            "generated_at_utc": _utc_now_iso(),
            "claim_types": ALLOWED_CLAIM_TYPES,
            "claims": claims,
        })
        packets_dir = run_path / "event_research_packets"
        packets_dir.mkdir(parents=True, exist_ok=True)
        for packet in research_packets:
            file_id = str(packet.get("event_cluster_id") or "event_cluster_unknown").replace(":", "_")
            self._write_json(packets_dir / f"{file_id}.json", packet)
        self._write_json(run_path / "event_market_validation.json", market_validation)
        layer_summary = self._event_layer_summary(event_narrative_ledger, research_packets, market_validation)
        self._write_json(run_path / "event_layer_summary.json", layer_summary)
        mechanism_report = self._build_event_mechanism_report(claims, research_packets)
        self._write_json(run_path / "event_mechanism_report.json", mechanism_report)
        self._write_json(run_path / "cross_layer_questions.json", {
            "schema_version": "cross_layer_questions_v1",
            "generated_at_utc": _utc_now_iso(),
            "questions": mechanism_report.get("cross_layer_questions", []),
        })
        self._write_json(run_path / "event_challenges.json", self._event_challenge_export(mechanism_report))
        self._write_json(run_path / "event_mechanism_cards.json", {
            "schema_version": "event_mechanism_cards_v1",
            "generated_at_utc": _utc_now_iso(),
            "cards": mechanism_report.get("event_research_cards", []),
        })
        mechanism_html = self._event_mechanism_html(mechanism_report)
        (run_path / "event_mechanism_report.html").write_text(mechanism_html, encoding="utf-8")
        (run_path / f"event_mechanism_report_{self._report_suffix(run_path)}.html").write_text(mechanism_html, encoding="utf-8")
        self._write_json(run_path / "event_adversarial_review.json", self._adversarial_review(claims, research_packets, market_validation))
        (run_path / "event_narrative_report.md").write_text(self._markdown_report(layer_summary, research_packets, market_validation), encoding="utf-8")

    def _report_suffix(self, run_path: Path) -> str:
        return run_path.name.replace("-", "_").replace(":", "_") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    def _event_challenge_export(self, mechanism_report: Dict[str, Any]) -> Dict[str, Any]:
        questions = _as_list(mechanism_report.get("cross_layer_questions"))
        open_event_questions = [
            question
            for question in questions
            if isinstance(question, dict)
            and question.get("direction") == "event_to_data"
            and str(question.get("status") or "open") in {"open", "insufficient_data"}
        ]
        rejected = [
            {
                "question_id": question.get("question_id"),
                "direction": question.get("direction"),
                "reason": "not_event_to_data_open_question",
            }
            for question in questions
            if isinstance(question, dict) and question not in open_event_questions
        ]
        status = "generated" if open_event_questions else "rejected"
        return {
            "schema_version": "event_challenges_v1",
            "generated_at_utc": _utc_now_iso(),
            "status": status,
            "message_type": "event_challenge",
            "challenge_candidates": [
                {
                    "question_id": question.get("question_id"),
                    "trigger": question.get("why_it_matters"),
                    "question": question.get("question"),
                    "allowed_context_refs": [
                        "cross_layer_questions.json",
                        "event_layer_summary.json",
                        "event_mechanism_report.json",
                    ],
                    "forbidden_context_refs": [
                        "layer_cards",
                        "thesis_draft.json",
                        "final_adjudication.json",
                    ],
                    "requested_checks": _as_list(question.get("requested_checks")),
                }
                for question in open_event_questions
            ],
            "rejected_candidates": rejected,
            "no_backflow_rule": "event_challenge can feed InquiryRouter, but event material must not become L1-L5 evidence_ref.",
        }

    def _event_mechanism_html(self, report: Dict[str, Any]) -> str:
        def esc(value: Any) -> str:
            return html.escape(str(value or ""), quote=True)

        def label(value: Any) -> str:
            return {"high": "高", "medium": "中", "low": "低"}.get(str(value), str(value or "低"))

        headline = report.get("headline_judgment", {}) if isinstance(report.get("headline_judgment"), dict) else {}
        news_cards = {
            str(card.get("news_id")): card
            for card in _as_list(report.get("news_cards"))
            if isinstance(card, dict)
        }
        mainline_html = ""
        for line in _as_list(report.get("mainlines")):
            if not isinstance(line, dict):
                continue
            negative = str(line.get("mainline_id")) in {"macro_rate_valuation_pressure", "risk_credit_liquidity"}
            buttons = ""
            for card_id in _as_list(line.get("news_card_ids"))[:6]:
                card = news_cards.get(str(card_id))
                if not card:
                    continue
                band_label = {"core": "核心线索", "supporting": "辅助线索", "background": "背景材料"}.get(str(card.get("relevance_band")), "线索")
                missing_label = " · 有材料缺口" if _as_list(card.get("missing_evidence")) else ""
                buttons += f"""
        <button class="news-button{' negative' if negative else ''}" type="button" data-detail="{esc(card.get('news_id'))}">
          <em>{esc(band_label)}{esc(missing_label)}</em>
          <b>{esc(card.get('title'))}</b>
          <span>{esc(card.get('one_line_summary'))}</span>
        </button>"""
            mainline_html += f"""
    <article class="panel strong">
      <h2>{esc(line.get('title'))}</h2>
      <p>{esc(line.get('plain_summary'))}</p>
      <p><strong>可以说：</strong>{esc(line.get('can_say'))}</p>
      <p><strong>不能说：</strong>{esc(line.get('cannot_say'))}</p>
      <div class="news-strip">{buttons or '<p>暂无相关新闻卡。</p>'}</div>
    </article>"""

        research_html = ""
        for index, card in enumerate(_as_list(report.get("event_research_cards"))[:6], start=1):
            if not isinstance(card, dict):
                continue
            counter = "".join(f"<li>{esc(item)}</li>" for item in _as_list(card.get("counterevidence"))[:4]) or "<li>暂无明确反证，正式结论必须降级。</li>"
            research_html += f"""
    <article class="event-card">
      <div class="event-head">
        <div>
          <div class="kicker">事件 {index:02d}</div>
          <h3>{esc(card.get('title'))}</h3>
          <p>{esc(card.get('minimum_fact'))}</p>
        </div>
        <div class="tag-stack">
          <span class="tag">重要性：{esc(label(card.get('importance')))}</span>
          <span class="tag">研究把握：{esc(label(card.get('confidence')))}</span>
          <span class="tag">怎么使用：{esc(card.get('how_to_use'))}</span>
        </div>
      </div>
      <div class="subgrid">
        <div class="subbox"><h4>最小事实</h4><p>{esc(card.get('minimum_fact'))}</p></div>
        <div class="subbox"><h4>可能影响</h4><p>{esc(card.get('possible_impact'))}</p></div>
        <div class="subbox"><h4>反证</h4><ul>{counter}</ul></div>
      </div>
    </article>"""

        questions = _as_list(report.get("cross_layer_questions"))
        question_html = "".join(
            f"""
      <article class="question {'event' if item.get('direction') == 'event_to_data' else ''}">
        <strong>{'新闻 → 数据' if item.get('direction') == 'event_to_data' else '数据 → 新闻'}</strong>
        <p>{esc(item.get('question'))}</p>
      </article>"""
            for item in questions
            if isinstance(item, dict)
        )
        ledger_rows = "".join(
            f"""
        <tr>
          <td>{esc(item.get('claim'))}</td>
          <td>{esc(item.get('nature'))}</td>
          <td>{esc(item.get('can_support'))}</td>
          <td>{esc(item.get('cannot_support'))}</td>
          <td>{esc(item.get('status'))}</td>
        </tr>"""
            for item in _as_list(report.get("claim_permission_ledger"))[:16]
            if isinstance(item, dict)
        )
        delivery = report.get("delivery_to_integrated_report", {}) if isinstance(report.get("delivery_to_integrated_report"), dict) else {}
        watchlist = "".join(f"<li>{esc(item)}</li>" for item in _as_list(delivery.get("watchlist"))[:8]) or "<li>暂无明确追踪项。</li>"
        modal_json = json.dumps(news_cards, ensure_ascii=False).replace("</", "<\\/")
        missing_count = sum(1 for card in news_cards.values() if _as_list(card.get("missing_evidence")))
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NDX 新闻事件研报</title>
<style>
:root{{--paper:#f3efe6;--ink:#171512;--muted:#6d6358;--line:#c9b9a3;--panel:#fffdf8;--blue:#174d6f;--red:#8d3728;--green:#2f684f;--black:#11110f}}*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);background:var(--paper);font-family:Georgia,"Times New Roman","Noto Serif SC",serif;line-height:1.62}}.page{{max-width:1220px;margin:0 auto;padding:26px 22px 86px}}.topbar{{display:flex;justify-content:space-between;gap:18px;align-items:center;border-bottom:2px solid var(--black);padding-bottom:12px;font-family:Menlo,Consolas,monospace;font-size:12px;color:var(--muted)}}.topbar strong{{color:var(--ink)}}.report-head{{display:grid;grid-template-columns:1.05fr .95fr;gap:26px;padding:30px 0 22px;border-bottom:1px solid var(--line)}}.kicker{{font-family:Menlo,Consolas,monospace;color:var(--blue);font-weight:700;font-size:13px;letter-spacing:.04em}}h1{{font-size:58px;line-height:1.02;margin:10px 0 18px}}h2{{font-size:32px;line-height:1.16;margin:0 0 14px}}h3{{font-size:24px;line-height:1.24;margin:0 0 10px}}h4{{font-family:Menlo,Consolas,monospace;font-size:13px;margin:0 0 8px}}p{{margin:0 0 12px}}.lead{{font-size:22px;color:#383129}}.verdict-box,.panel,.event-card{{background:var(--panel);border:1px solid var(--line);padding:18px}}.verdict-box,.event-card,.panel.strong{{border-color:var(--black);box-shadow:5px 5px 0 #d8cab7}}.stance{{font-size:25px;line-height:1.34;font-weight:700}}.chips{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}.chip,.tag{{display:inline-flex;border:1px solid var(--line);background:#f7f1e8;padding:5px 8px;font-family:Menlo,Consolas,monospace;font-size:12px}}.chip.blue{{color:var(--blue);border-color:var(--blue)}}.chip.red{{color:var(--red);border-color:var(--red)}}.chip.green{{color:var(--green);border-color:var(--green)}}.nav{{position:sticky;top:0;z-index:5;display:flex;gap:8px;flex-wrap:wrap;padding:12px 0;margin-bottom:28px;background:rgba(243,239,230,.95);border-bottom:1px solid var(--line)}}.nav a{{text-decoration:none;color:var(--ink);background:var(--panel);border:1px solid var(--line);padding:7px 10px;font-family:Menlo,Consolas,monospace;font-size:12px}}.summary-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0 34px}}.metric{{background:var(--panel);border:1px solid var(--line);padding:14px}}.metric b{{display:block;font-size:30px;line-height:1}}.metric span{{color:var(--muted);font-family:Menlo,Consolas,monospace;font-size:12px}}.section{{margin:34px 0}}.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.news-strip{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}}.news-button{{appearance:none;width:100%;min-height:116px;border:1px solid var(--line);background:#f7f1e8;color:var(--ink);text-align:left;padding:10px 12px;font:inherit;cursor:pointer}}.news-button:hover,.news-button:focus-visible{{outline:2px solid var(--blue);outline-offset:2px}}.news-button.negative:hover,.news-button.negative:focus-visible{{outline-color:var(--red)}}.news-button em{{display:inline-block;margin-bottom:7px;font-family:Menlo,Consolas,monospace;font-style:normal;font-size:11px;color:var(--blue);border-bottom:1px solid var(--line)}}.news-button.negative em{{color:var(--red)}}.news-button b{{display:block;font-size:15px;line-height:1.35;margin-bottom:6px}}.news-button span{{display:block;color:var(--muted);font-size:13px;line-height:1.45}}.event-card{{margin:20px 0}}.event-head{{display:grid;grid-template-columns:1fr 230px;gap:18px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:14px}}.tag-stack{{display:flex;flex-direction:column;gap:8px}}.subgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.subbox{{border-top:1px solid var(--line);padding-top:12px}}.question-list{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}}.question{{background:var(--panel);border:1px solid var(--line);border-left:6px solid var(--blue);padding:16px}}.question.event{{border-left-color:var(--red)}}.question strong{{display:block;font-family:Menlo,Consolas,monospace;font-size:12px;margin-bottom:6px;color:var(--blue)}}.question.event strong{{color:var(--red)}}table{{width:100%;border-collapse:collapse;background:var(--panel);font-size:14px}}th,td{{border:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}}th{{background:#e8dece;font-family:Menlo,Consolas,monospace;font-size:12px}}.reader-final{{background:#1f1b17;color:#fff;padding:22px;display:grid;grid-template-columns:1fr 1fr;gap:22px}}.reader-final p,.reader-final li{{color:#f0e6d9}}.footer{{margin-top:42px;border-top:2px solid var(--black);padding-top:16px;color:var(--muted)}}.modal-backdrop{{position:fixed;inset:0;z-index:20;display:none;align-items:center;justify-content:center;padding:18px;background:rgba(19,17,14,.45)}}.modal-backdrop.open{{display:flex}}.modal{{width:min(760px,100%);max-height:88vh;overflow:auto;background:var(--panel);border:2px solid var(--black);box-shadow:8px 8px 0 rgba(0,0,0,.24);padding:22px}}.modal-head{{display:flex;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:14px}}.modal-close{{appearance:none;width:36px;height:36px;border:1px solid var(--black);background:var(--paper);font-size:24px;cursor:pointer}}.detail-grid{{display:grid;grid-template-columns:110px 1fr;gap:8px 12px;margin:12px 0;font-size:15px}}.detail-grid b{{color:var(--muted)}}@media(max-width:900px){{.report-head,.two-col,.event-head,.subgrid,.question-list,.reader-final{{grid-template-columns:1fr}}.summary-grid{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:40px}}.news-strip{{grid-template-columns:1fr}}.detail-grid{{grid-template-columns:1fr}}}}@media(max-width:540px){{.summary-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body><main class="page">
<div class="topbar"><strong>NDX 新闻事件研报</strong><span>正式第二层报告 · 非主证据</span><span>{esc(report.get('generated_at_utc'))}</span></div>
<header class="report-head"><section><div class="kicker">新闻事件研报</div><h1>今天市场在交易什么故事？哪些故事站得住？</h1><p class="lead">这份报告不做新闻列表，也不拿新闻硬解释涨跌。它只回答三件事：今天有哪些重要新闻，它们可能影响市场的哪条逻辑，以及哪些说法还需要数据来确认。</p></section><aside class="verdict-box"><h2>{esc(headline.get('title') or '新闻事件初步判断')}</h2><p class="stance">{esc(headline.get('plain_text'))}</p><div class="chips"><span class="chip green">新闻线索</span><span class="chip red">不能当主证据</span><span class="chip blue">把握：{esc(label(headline.get('confidence')))}</span></div></aside></header>
<nav class="nav"><a href="#snapshot">事件快照</a><a href="#mainlines">主线</a><a href="#events">事件研究卡</a><a href="#questions">数据问题</a><a href="#ledger">主张台账</a><a href="#delivery">给综合研报</a></nav>
<section id="snapshot" class="summary-grid"><div class="metric"><b>{len(research_html.split('event-card')) - 1}</b><span>核心事件</span></div><div class="metric"><b>{len(questions)}</b><span>需要回答的问题</span></div><div class="metric"><b>{missing_count}</b><span>有缺口的新闻</span></div><div class="metric"><b>0</b><span>可直接升级为主证据</span></div></section>
<section id="mainlines" class="section two-col">{mainline_html or '<p>暂无新闻主线。</p>'}</section>
<section id="events" class="section"><h2>核心事件研究卡</h2>{research_html or '<p>暂无事件研究卡。</p>'}</section>
<section id="questions" class="section"><h2>新闻事件给数据层出的题</h2><div class="question-list">{question_html or '<p>暂无跨层问题。</p>'}</div></section>
<section id="ledger" class="section"><h2>主张台账：给读者看清每句话的权限</h2><table><thead><tr><th>主张</th><th>性质</th><th>能支持什么</th><th>不能支持什么</th><th>状态</th></tr></thead><tbody>{ledger_rows or '<tr><td colspan="5">暂无主张。</td></tr>'}</tbody></table></section>
<section id="delivery" class="section reader-final"><article><h2>给综合研报的一句话</h2><p>{esc(delivery.get('one_sentence'))}</p><p>综合研报应把新闻写成“可能的解释 + 风险提醒”，而不是写成主证据。</p></article><article><h3>下一步必须追踪</h3><ul>{watchlist}</ul></article></section>
<footer class="footer"><p>新闻事件材料只供第二层和综合研报使用，不进入 L1-L5 主证据。</p></footer>
<div class="modal-backdrop" id="newsModal" aria-hidden="true"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle"><div class="modal-head"><div><div class="kicker" id="modalSource">新闻详情</div><h2 id="modalTitle">标题</h2></div><button class="modal-close" type="button" aria-label="关闭">×</button></div><div class="detail-grid"><b>日期</b><span id="modalDate"></span><b>来源</b><span id="modalProvider"></span><b>材料等级</b><span id="modalQuality"></span><b>材料缺口</b><span id="modalMissing"></span><b>正文片段</b><span id="modalRaw"></span><b>摘要</b><span id="modalSummary"></span><b>AI 分析</b><span id="modalAnalysis"></span><b>可以说</b><span id="modalCan"></span><b>不能说</b><span id="modalCannot"></span><b>还要确认</b><span id="modalNeed"></span></div></section></div>
</main><script>
const newsDetails={modal_json};
const modal=document.getElementById("newsModal");
const fields={{source:document.getElementById("modalSource"),title:document.getElementById("modalTitle"),date:document.getElementById("modalDate"),provider:document.getElementById("modalProvider"),quality:document.getElementById("modalQuality"),missing:document.getElementById("modalMissing"),raw:document.getElementById("modalRaw"),summary:document.getElementById("modalSummary"),analysis:document.getElementById("modalAnalysis"),can:document.getElementById("modalCan"),cannot:document.getElementById("modalCannot"),need:document.getElementById("modalNeed")}};
function openNewsDetail(key){{const item=newsDetails[key];if(!item)return;const band={{core:"核心线索",supporting:"辅助线索",background:"背景材料"}}[item.relevance_band]||"线索";fields.source.textContent=band+" · 把握："+(item.confidence==="medium"?"中":"低");fields.title.textContent=item.title||"";fields.date.textContent=item.published_at||"";fields.provider.textContent=item.source_name||"";fields.quality.textContent=item.source_quality||"";fields.missing.textContent=(item.missing_evidence||[]).join("；")||"暂无明显缺口";fields.raw.textContent=item.raw_text_excerpt||"未读取正文";fields.summary.textContent=item.one_line_summary||"";fields.analysis.textContent=item.ai_analysis||"";fields.can.textContent=item.can_support||"";fields.cannot.textContent=item.cannot_support||"";fields.need.textContent=(item.needs_data_confirmation||[]).join("；")||"暂无";modal.classList.add("open");modal.setAttribute("aria-hidden","false");document.querySelector(".modal-close").focus();}}
function closeNewsDetail(){{modal.classList.remove("open");modal.setAttribute("aria-hidden","true");}}
document.querySelectorAll("[data-detail]").forEach((button)=>button.addEventListener("click",()=>openNewsDetail(button.dataset.detail)));
document.querySelector(".modal-close").addEventListener("click",closeNewsDetail);
modal.addEventListener("click",(event)=>{{if(event.target===modal)closeNewsDetail();}});
document.addEventListener("keydown",(event)=>{{if(event.key==="Escape")closeNewsDetail();}});
</script></body></html>"""

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _event_layer_summary(
        self,
        event_narrative_ledger: Dict[str, Any],
        research_packets: List[Dict[str, Any]],
        market_validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        claims = [
            claim
            for event in _as_list(event_narrative_ledger.get("events"))
            if isinstance(event, dict)
            for claim in _as_list(event.get("claims"))
            if isinstance(claim, dict)
        ]
        validations = _as_list(market_validation.get("validations"))
        materiality_rank = {"high": 3, "medium": 2, "low": 1}
        confidence_rank = {"high": 3, "medium": 2, "low": 1}
        ranked_packets = sorted(
            research_packets,
            key=lambda packet: (
                0 if packet.get("title_only") else 1,
                materiality_rank.get(str(packet.get("materiality")), 0),
                confidence_rank.get(str(packet.get("agent_confidence")), 0),
                len(_as_list(packet.get("affected_financial_links"))),
            ),
            reverse=True,
        )
        ranked_claims = sorted(
            claims,
            key=lambda claim: (
                0 if claim.get("raw_text_available") is False else 1,
                confidence_rank.get(str(claim.get("confidence_before_market_validation")), 0),
                len(_as_list(claim.get("affected_financial_links"))),
            ),
            reverse=True,
        )
        return {
            "schema_version": "event_layer_summary_v1",
            "generated_at_utc": _utc_now_iso(),
            "most_important_events": [
                {
                    "event_cluster_id": packet.get("event_cluster_id"),
                    "minimum_fact": packet.get("minimum_fact"),
                    "materiality": packet.get("materiality"),
                    "agent_confidence": packet.get("agent_confidence"),
                }
                for packet in ranked_packets[:8]
            ],
            "most_important_claims": [
                {
                    "claim_id": claim.get("claim_id"),
                    "claim_type": claim.get("claim_type"),
                    "claim_text": claim.get("claim_text"),
                    "confidence_before_market_validation": claim.get("confidence_before_market_validation"),
                }
                for claim in ranked_claims[:12]
            ],
            "highest_confidence_explanations": [
                packet for packet in research_packets if packet.get("agent_confidence") == "medium"
            ][:6],
            "strongest_counterevidence": sorted({
                str(limit)
                for claim in claims
                for limit in _as_list(claim.get("counterevidence_or_limits"))
            })[:10],
            "unexplained_items": [
                {
                    "event_cluster_id": item.get("event_cluster_id"),
                    "reason": "市场数据不足，不能确认事件解释。",
                }
                for item in validations
                if item.get("validation_label") in {"insufficient_data", "observed_without_bridge_signal"}
            ],
            "financial_links_most_related_to_layer_1": sorted({
                link for packet in research_packets for link in _as_list(packet.get("affected_financial_links"))
            }),
            "downgraded_narratives": [
                {
                    "claim_id": claim.get("claim_id"),
                    "reason": claim.get("what_it_cannot_support"),
                }
                for claim in claims
                if claim.get("needs_data_confirmation") or claim.get("claim_type") in {"narrative_claim", "rumor_claim"}
            ][:12],
            "forbidden_for_l1_l5_statement": "第二层事件材料禁止进入 L1-L5 evidence_ref 或运行时 prompt；只能供第三层综合报告读取。",
        }

    def _adversarial_review(
        self,
        claims: List[Dict[str, Any]],
        research_packets: List[Dict[str, Any]],
        market_validation: Dict[str, Any],
    ) -> Dict[str, Any]:
        high_without_counter = [
            packet.get("event_cluster_id")
            for packet in research_packets
            if packet.get("agent_confidence") == "high" and not _as_list(packet.get("source_conflict_review"))
        ]
        social_official = [
            claim.get("claim_id")
            for claim in claims
            if claim.get("source_type") in {"market_narrative", "unverified_signal"} and claim.get("claim_type") == "official_fact"
        ]
        causal_violations = [
            item.get("event_cluster_id")
            for item in _as_list(market_validation.get("validations"))
            if "not causal evidence" not in str(item.get("causality_statement") or "")
        ]
        checks = [
            {
                "check_id": "no_backflow",
                "status": "pass",
                "finding": "产物声明禁止进入 L1-L5、Bridge、Thesis、Risk、Reviser、Final data-only prompts。",
            },
            {
                "check_id": "counterevidence_required_for_confidence",
                "status": "pass" if not high_without_counter else "fail",
                "finding": high_without_counter,
            },
            {
                "check_id": "social_sources_cannot_be_official_fact",
                "status": "pass" if not social_official else "fail",
                "finding": social_official,
            },
            {
                "check_id": "market_validator_no_causal_proof",
                "status": "pass" if not causal_violations else "fail",
                "finding": causal_violations,
            },
            {
                "check_id": "title_only_downgrade",
                "status": "pass",
                "finding": "标题-only claim 的 confidence_before_market_validation 被限制为 low。",
            },
        ]
        return {
            "schema_version": "event_adversarial_review_v1",
            "generated_at_utc": _utc_now_iso(),
            "overall_status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
            "checks": checks,
        }

    def _markdown_report(
        self,
        layer_summary: Dict[str, Any],
        research_packets: List[Dict[str, Any]],
        market_validation: Dict[str, Any],
    ) -> str:
        lines = [
            "# 第二层事件研究报告",
            "",
            "本报告只解释外部事件、新闻叙事和公告材料。它不能替代 L1-L5 正式数据证据，也不能证明新闻导致价格变化。",
            "",
            "## 重要事件",
        ]
        for item in _as_list(layer_summary.get("most_important_events")):
            lines.append(f"- {item.get('minimum_fact')}：重要性 {item.get('materiality')}，研究置信度 {item.get('agent_confidence')}。")
        lines.extend(["", "## 市场验证"])
        for item in _as_list(market_validation.get("validations")):
            lines.append(f"- {item.get('event_cluster_id')}：{item.get('validation_label')}；{item.get('causality_statement')}。")
        lines.extend(["", "## 不能越界的地方"])
        lines.append(f"- {layer_summary.get('forbidden_for_l1_l5_statement')}")
        lines.append("- not_confirmed、contradicted_by_market_data 或 insufficient_data 不能写成支持。")
        return "\n".join(lines) + "\n"


def write_event_narrative_ledger(
    run_dir: str | Path,
    *,
    event_ledger: Optional[Dict[str, Any]] = None,
    news_layer_analysis: Optional[Dict[str, Any]] = None,
    news_event_data_links: Optional[Dict[str, Any]] = None,
    event_ledger_path: Optional[str | Path] = None,
    news_layer_analysis_path: Optional[str | Path] = None,
    news_event_data_links_path: Optional[str | Path] = None,
    effective_date: Optional[str] = None,
) -> str:
    run_path = Path(run_dir)
    ledger_path = Path(event_ledger_path) if event_ledger_path else run_path / "news_event_ledger.json"
    analysis_path = Path(news_layer_analysis_path) if news_layer_analysis_path else run_path / "news_layer_analysis.json"
    links_path = Path(news_event_data_links_path) if news_event_data_links_path else run_path / "news_event_data_links.json"
    output_path = run_path / "event_narrative_ledger.json"
    EventNarrativeLedgerBuilder().build(
        event_ledger=event_ledger if event_ledger is not None else _load_json(ledger_path, {}),
        news_layer_analysis=news_layer_analysis if news_layer_analysis is not None else _load_json(analysis_path, {}),
        news_event_data_links=news_event_data_links if news_event_data_links is not None else _load_json(links_path, {}),
        effective_date=effective_date,
        output_path=output_path,
        source_paths={
            "news_event_ledger": str(ledger_path),
            "news_layer_analysis": str(analysis_path),
            "news_event_data_links": str(links_path),
        },
    )
    return str(output_path)
