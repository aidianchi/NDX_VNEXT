from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CLAIM_TYPE_BY_SOURCE = {
    "official_macro": "official_fact",
    "official_fact": "official_fact",
    "official_regulatory": "official_fact",
    "company_disclosure": "disclosure_claim",
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
    "company_disclosure": "company_disclosure",
    "primary_market_data_release": "primary_market_data_release",
    "reliable_mainstream_report": "reliable_mainstream_report",
    "sell_side_or_expert_view": "sell_side_or_expert_view",
    "market_narrative": "market_narrative",
    "unverified_signal": "unverified_signal",
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
    title = str(event.get("title") or "").lower()
    if "sec" in source_id or any(token in title for token in ["10-q", "10-k", "8-k", "earnings", "guidance"]):
        return "company_disclosure"
    return SOURCE_TYPE_BY_TIER.get(tier, "reliable_mainstream_report" if "news" in source_id else "official_fact")


def _claim_type(source_type: str, event: Dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "").lower()
    if "data" in event_type or "macro" in event_type:
        return "data_release_claim"
    return CLAIM_TYPE_BY_SOURCE.get(source_type, "interpretation_claim")


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
        events = []
        for event in _as_list(event_ledger.get("events")):
            if not isinstance(event, dict):
                continue
            published_dt = _parse_datetime(event.get("published_at"))
            if effective_dt is not None and published_dt is not None and published_dt > effective_dt:
                continue
            events.append(self._event_entry(event, summaries.get(str(event.get("event_id")), {}), data_links.get(str(event.get("event_id")), {})))

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
            "events": events,
            "claim_count": sum(len(_as_list(event.get("claims"))) for event in events),
        }
        if output_path:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def _event_entry(self, event: Dict[str, Any], summary: Dict[str, Any], data_link: Dict[str, Any]) -> Dict[str, Any]:
        event_id = str(event.get("event_id") or "")
        source_type = _source_type(event)
        affected_links = _affected_links(summary, data_link)
        can_support, cannot_support = _support_boundary(source_type, affected_links)
        fact_summary = _clean_text(summary.get("summary_zh") or event.get("title"))
        interpretation_summary = _clean_text(summary.get("possible_equity_impact_zh"))
        claim = {
            "claim_id": f"claim:{event_id.removeprefix('event:')}:primary",
            "claim_type": _claim_type(source_type, event),
            "source_type": source_type,
            "source_name": event.get("source_name"),
            "source_url": event.get("url"),
            "published_at": event.get("published_at"),
            "event_date": event.get("event_date") or _iso_date_or_none(event.get("published_at")),
            "information_available_at": event.get("published_at"),
            "related_index_object": _related_object(event),
            "affected_financial_links": affected_links,
            "fact_summary": fact_summary,
            "interpretation_summary": interpretation_summary,
            "what_it_can_support": can_support,
            "what_it_cannot_support": cannot_support,
            "needs_data_confirmation": True,
            "counterevidence_or_limits": [
                "时间邻近不等于因果证明。",
                "需要纯数据研报或后续价格/信用/利率/广度数据确认。",
            ],
            "status": _status(source_type),
        }
        return {
            "event_id": event_id,
            "dedupe_id": event.get("dedupe_id"),
            "title": event.get("title"),
            "published_at": event.get("published_at"),
            "source_name": event.get("source_name"),
            "source_type": source_type,
            "claims": [claim],
        }


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

