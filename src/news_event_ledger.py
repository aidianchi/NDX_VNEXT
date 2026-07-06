from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from xml.etree import ElementTree

import requests

try:
    from .api_config import get_api_key, get_base_url, get_requests_proxies, is_service_enabled
    from .config import path_config
except ImportError:
    from api_config import get_api_key, get_base_url, get_requests_proxies, is_service_enabled
    from config import path_config

logger = logging.getLogger(__name__)

FetchText = Callable[[str, Dict[str, str], int], str]

M7_SEC_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "NVDA": "0001045810",
    "META": "0001326801",
    "TSLA": "0001318605",
}

OFFICIAL_RSS_SOURCES = [
    {
        "source_id": "federal_reserve_press_all",
        "source_name": "Federal Reserve Press Releases",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "authority_tier": "official",
        "event_type": "policy_or_financial_conditions",
        "relevance_tags": ["L1", "L2", "L4"],
    },
    {
        "source_id": "bls_latest",
        "source_name": "BLS Latest Numbers",
        "url": "https://www.bls.gov/feed/bls_latest.rss",
        "authority_tier": "official",
        "event_type": "macro_data_release",
        "relevance_tags": ["L1"],
    },
    {
        "source_id": "bea_news",
        "source_name": "BEA News",
        "url": "https://www.bea.gov/news/rss.xml",
        "authority_tier": "official",
        "event_type": "macro_data_release",
        "relevance_tags": ["L1", "L4"],
    },
]

YAHOO_FINANCE_RSS_SOURCES = [
    {
        "source_id": "yahoo_finance_qqq_headlines",
        "source_name": "Yahoo Finance QQQ Headlines",
        "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=QQQ&region=US&lang=en-US",
        "source_tier": "reliable_mainstream_report",
        "authority_tier": "market_news_aggregator",
        "event_type": "market_news_report",
        "relevance_tags": ["L3", "L4", "L5"],
        "symbols": ["QQQ", "NDX"],
    },
    {
        "source_id": "yahoo_finance_m7_headlines",
        "source_name": "Yahoo Finance M7 Headlines",
        "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA&region=US&lang=en-US",
        "source_tier": "reliable_mainstream_report",
        "authority_tier": "market_news_aggregator",
        "event_type": "mega_cap_market_news",
        "relevance_tags": ["L3", "L4"],
        "symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA"],
    },
]

SOCIAL_RSS_SOURCES = [
    {
        "source_id": "reddit_stocks_qqq_search",
        "source_name": "Reddit r/stocks QQQ Search",
        "url": "https://www.reddit.com/r/stocks/search.rss?q=QQQ%20OR%20Nasdaq%20100&restrict_sr=on&sort=new&t=week",
        "source_tier": "market_narrative",
        "authority_tier": "social_discussion",
        "event_type": "social_market_narrative",
        "relevance_tags": ["L5"],
        "symbols": ["QQQ", "NDX"],
    }
]

ALPHA_VANTAGE_TICKERS = ["QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA"]

WIND_DOC_QUERIES = [
    {
        "source_id": "wind_company_announcements_m7",
        "source_name": "Wind Company Announcements",
        "tool_name": "get_company_announcements",
        "query": "AAPLMSFTNVDAMETAAMZNGOOGLTSLA公告财报指引",
        "source_tier": "company_disclosure",
        "authority_tier": "licensed_provider/Wind",
        "event_type": "issuer_announcement_or_filing",
        "relevance_tags": ["L3", "L4"],
        "symbols": ["AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL", "TSLA"],
    },
    {
        "source_id": "wind_financial_news_ndx",
        "source_name": "Wind Financial News",
        "tool_name": "get_financial_news",
        "query": "纳斯达克100科技股美联储利率AI财报",
        "source_tier": "reliable_mainstream_report",
        "authority_tier": "licensed_provider/Wind",
        "event_type": "licensed_financial_news",
        "relevance_tags": ["L1", "L3", "L4", "L5"],
        "symbols": ["NDX", "QQQ"],
    },
]

HIGH_RELEVANCE_KEYWORDS = [
    "fomc",
    "federal funds",
    "monetary policy",
    "inflation",
    "cpi",
    "ppi",
    "employment",
    "payroll",
    "gdp",
    "treasury",
    "liquidity",
    "8-k",
    "10-q",
    "10-k",
    "earnings",
    "guidance",
]

HIGH_RELEVANCE_BODY_FETCH_KEYWORDS = [
    "ndx",
    "nasdaq",
    "nasdaq-100",
    "qqq",
    "artificial intelligence",
    "semiconductor",
    "chip",
    "chipmaker",
    "micron",
    "nvidia",
    "nvda",
    "amd",
    "intc",
    "fed",
    "fomc",
    "rate",
    "rates",
    "treasury",
    "valuation",
    "selloff",
    "guidance",
    "earnings",
    "美联储",
    "利率",
    "估值",
    "纳指",
    "纳斯达克",
    "人工智能",
    "半导体",
    "美光",
    "英伟达",
    "财测",
    "盈利",
]


class _ReadableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "header", "footer", "form"}:
            self._skip_depth += 1
        if tag.lower() in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "header", "footer", "form"} and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() in {"p", "div", "section", "article", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(html_lib.unescape(data).split())
        if text:
            self.parts.append(text)


def _extract_readable_text(raw: str, limit: int = 2200) -> str:
    text = raw or ""
    lower_start = text[:1200].lower()
    if "<rss" in lower_start or "<feed" in lower_start:
        return ""
    if "<html" not in lower_start and "<body" not in lower_start and "<p" not in lower_start and "<article" not in lower_start:
        return _clean_text(text, limit)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    parser = _ReadableTextParser()
    try:
        parser.feed(text)
    except Exception:
        return ""
    readable = _clean_text(" ".join(parser.parts), limit)
    lower = readable.lower()
    if len(readable) < 120:
        return ""
    if "enable javascript" in lower and "subscribe" in lower:
        return ""
    if "oops, something went wrong" in lower and "skip to navigation" in lower:
        return ""
    return readable


@dataclass
class NewsEvent:
    event_id: str
    dedupe_id: str
    source_id: str
    source_name: str
    source_tier: str
    authority_tier: str
    event_type: str
    title: str
    url: str
    published_at: str
    relevance_tags: List[str]
    layers: List[str]
    symbols: List[str]
    confidence: str
    notes: str
    raw_text_available: bool = False
    raw_text: str = ""
    collection_status: str = "ok"

    def to_dict(self) -> Dict[str, Any]:
        event_date = ""
        parsed = _parse_event_datetime(self.published_at)
        if parsed is not None:
            event_date = parsed.date().isoformat()
        hash_basis = self.raw_text if self.raw_text_available and self.raw_text else f"{self.title}|{self.url}"
        return {
            "event_id": self.event_id,
            "dedupe_id": self.dedupe_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_tier": self.source_tier,
            "authority_tier": self.authority_tier,
            "event_type": self.event_type,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "event_date": event_date,
            "information_available_at": self.published_at,
            "raw_text_available": bool(self.raw_text_available),
            "raw_text_excerpt": _clean_text(self.raw_text, 2200) if self.raw_text_available else "",
            "raw_text_hash": hashlib.sha1(hash_basis.encode("utf-8")).hexdigest(),
            "collection_status": self.collection_status if self.published_at else "date_uncertain",
            "relevance_tags": self.relevance_tags,
            "layers": self.layers,
            "symbols": self.symbols,
            "confidence": self.confidence,
            "notes": self.notes,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_event_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _alpha_time_to_iso(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.strptime(text[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return text
    return parsed.isoformat().replace("+00:00", "Z")


def _effective_datetime(value: Optional[str]) -> datetime:
    parsed = _parse_event_datetime(value) if value else None
    if parsed is None:
        return datetime.now(timezone.utc)
    text = str(value).strip()
    if len(text) == 10:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _dedupe_id(source_id: str, title: str, url: str, published_at: str) -> str:
    published_date = ""
    parsed = _parse_event_datetime(published_at)
    if parsed is not None:
        published_date = parsed.date().isoformat()
    key = "|".join(
        [
            source_id.strip().lower(),
            " ".join(title.strip().lower().split()),
            url.strip().lower(),
            published_date,
        ]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _clean_text(value: Any, max_chars: int = 500) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:max_chars]


def _symbols_from_text(text: str, defaults: Optional[List[str]] = None) -> List[str]:
    defaults = defaults or []
    upper = text.upper()
    found = [symbol for symbol in ALPHA_VANTAGE_TICKERS + ["NDX"] if symbol in upper]
    if "NASDAQ 100" in upper or "NASDAQ-100" in upper:
        found.extend(["NDX", "QQQ"])
    return sorted(dict.fromkeys(found or defaults))


def _social_source_tier(title: str) -> str:
    lowered = title.lower()
    weak_tokens = ["rumor", "unconfirmed", "leak", "hearsay", "有人说", "传闻", "爆料"]
    return "unverified_signal" if any(token in lowered for token in weak_tokens) else "market_narrative"


def _wind_skill_dir() -> Path:
    return Path.home() / ".agents" / "skills" / "wind-mcp-skill"


def _wind_docs_disabled() -> bool:
    return os.environ.get("NDX_DISABLE_WIND_L4") == "1" or os.environ.get("NDX_DISABLE_WIND_EVENT") == "1"


def _wind_payload_body(payload: Any) -> Any:
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                text = first["text"]
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        for key in ("data", "result", "body", "records", "items"):
            if key in payload:
                return payload[key]
    return payload


def _flatten_dict_records(value: Any) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            records.extend(_flatten_dict_records(item))
    elif isinstance(value, dict):
        if any(key in value for key in ("title", "标题", "name", "summary", "content", "正文", "url", "link", "source")):
            records.append(value)
        else:
            for item in value.values():
                records.extend(_flatten_dict_records(item))
    return records


def _first_field(record: Dict[str, Any], *names: str) -> str:
    lowered = {str(key).strip().lower(): value for key, value in record.items()}
    for name in names:
        if name in record and record[name] not in (None, ""):
            return str(record[name]).strip()
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _call_wind_docs(tool_name: str, query: str, top_k: int, timeout: int) -> tuple[Optional[Any], Optional[str]]:
    if _wind_docs_disabled():
        return None, "wind_docs_disabled_by_env"
    skill_dir = _wind_skill_dir()
    script = skill_dir / "scripts" / "cli.mjs"
    if not script.exists():
        return None, "wind_mcp_skill_cli_not_found"
    params = json.dumps({"query": "".join(query.split()), "top_k": top_k}, ensure_ascii=False)
    try:
        completed = subprocess.run(
            ["node", "scripts/cli.mjs", "call", "financial_docs", tool_name, params],
            cwd=str(skill_dir),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "wind_docs_timeout"
    except Exception as exc:
        return None, f"wind_docs_runtime_error:{str(exc)[:120]}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return None, f"wind_docs_failed:{detail[:240]}"
    text = completed.stdout.strip()
    if not text:
        return None, "wind_docs_empty_stdout"
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        return text, None


def _default_fetch_text(url: str, headers: Dict[str, str], timeout: int) -> str:
    response = requests.get(url, headers=headers, timeout=timeout, proxies=get_requests_proxies())
    response.raise_for_status()
    return response.text


def _text_of(element: ElementTree.Element, name: str) -> str:
    child = element.find(name)
    return (child.text or "").strip() if child is not None else ""


def _entry_text(element: ElementTree.Element, names: Iterable[str]) -> str:
    for name in names:
        child = element.find(name)
        if child is not None:
            if child.text:
                return child.text.strip()
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def _parse_rss_items(xml_text: str) -> List[Dict[str, str]]:
    root = ElementTree.fromstring(xml_text)
    channel_items = root.findall(".//item")
    if channel_items:
        return [
            {
                "title": _text_of(item, "title"),
                "url": _text_of(item, "link"),
                "published_at": _text_of(item, "pubDate"),
            }
            for item in channel_items
        ]
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//atom:entry", ns)
    return [
        {
            "title": _entry_text(entry, ["{http://www.w3.org/2005/Atom}title"]),
            "url": _entry_text(entry, ["{http://www.w3.org/2005/Atom}link"]),
            "published_at": _entry_text(entry, ["{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published"]),
        }
        for entry in entries
    ]


class NewsEventLedgerBuilder:
    """Build an independent event ledger; never mutates L1-L5 runtime context."""

    def __init__(
        self,
        fetch_text: FetchText = _default_fetch_text,
        max_events_per_source: int = 8,
        timeout: int = 12,
        lookback_days: int = 45,
        effective_date: Optional[str] = None,
    ) -> None:
        self.fetch_text = fetch_text
        self.max_events_per_source = max_events_per_source
        self.timeout = timeout
        self.lookback_days = lookback_days
        self.effective_date = effective_date

    def build(
        self,
        output_path: str | Path,
        include_sec: bool = True,
        include_rss: bool = True,
        include_market_news: bool = True,
        include_social: bool = True,
        include_wind: bool = True,
    ) -> Dict[str, Any]:
        events: List[NewsEvent] = []
        source_errors: List[Dict[str, str]] = []
        if include_rss:
            rss_events, rss_errors = self._collect_rss_events()
            events.extend(rss_events)
            source_errors.extend(rss_errors)
        if include_sec:
            sec_events, sec_errors = self._collect_sec_events()
            events.extend(sec_events)
            source_errors.extend(sec_errors)
        if include_market_news:
            market_events, market_errors = self._collect_market_news_events()
            events.extend(market_events)
            source_errors.extend(market_errors)
        if include_social:
            social_events, social_errors = self._collect_social_events()
            events.extend(social_events)
            source_errors.extend(social_errors)
        if include_wind:
            wind_events, wind_errors = self._collect_wind_doc_events()
            events.extend(wind_events)
            source_errors.extend(wind_errors)
        events = self._dedupe_and_window(events)

        payload = {
            "schema_version": "news_event_ledger_v2",
            "generated_at_utc": _utc_now_iso(),
            "policy": {
                "runtime_context_rule": "This sidecar is not injected into L1-L5 layer-local prompts.",
                "usage_rule": "Bridge/Thesis may cite event_ref only as catalyst/background/observation, never as numeric indicator evidence or proof.",
                "event_ref_rule": "event_ref is intentionally separate from evidence_ref.",
            },
            "governance": {
                "source_tiers": [
                    "official_macro",
                    "official_filing",
                    "company_disclosure",
                    "reliable_mainstream_report",
                    "market_narrative",
                    "unverified_signal",
                ],
                "source_record_artifact": "event_source_raw.jsonl",
                "source_adapters": [
                    "official_rss_adapter",
                    "sec_edgar_adapter",
                    "wind_financial_docs_adapter",
                    "yahoo_finance_rss_adapter",
                    "alpha_vantage_news_sentiment_adapter",
                    "reddit_social_rss_adapter",
                ],
                "dedupe_key": "source_id + normalized title + url + published date",
                "lookback_days": self.lookback_days,
                "effective_date": self.effective_date,
                "event_fields": ["source_tier", "event_type", "published_at", "symbols", "layers", "dedupe_id", "source_errors"],
                "raw_text_rule": "raw_text_available=true only when an adapter retrieves document/body text, not merely title, URL, or vendor sentiment metadata.",
                "social_rule": "social sources are market_narrative by default; rumor/leak/unconfirmed titles are downgraded to unverified_signal.",
            },
            "sources": {
                "rss": [source["source_id"] for source in OFFICIAL_RSS_SOURCES] if include_rss else [],
                "sec_submissions": sorted(M7_SEC_CIKS) if include_sec else [],
                "market_news": ([source["source_id"] for source in YAHOO_FINANCE_RSS_SOURCES] + ["alpha_vantage_news_sentiment"]) if include_market_news else [],
                "social": [source["source_id"] for source in SOCIAL_RSS_SOURCES] if include_social else [],
                "wind_docs": [source["source_id"] for source in WIND_DOC_QUERIES] if include_wind else [],
            },
            "events": [event.to_dict() for event in events],
            "source_errors": source_errors,
        }
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._write_source_raw(output.parent / "event_source_raw.jsonl", events)
        return payload

    def _dedupe_and_window(self, events: List[NewsEvent]) -> List[NewsEvent]:
        effective = _effective_datetime(self.effective_date) if self.effective_date else datetime.now(timezone.utc)
        cutoff = effective - timedelta(days=max(0, self.lookback_days))
        deduped: Dict[str, NewsEvent] = {}
        for event in events:
            parsed = _parse_event_datetime(event.published_at)
            if self.effective_date and parsed is None:
                continue
            if self.effective_date and parsed is not None and parsed > effective:
                continue
            if self.effective_date and parsed is not None and self.lookback_days > 0 and parsed < cutoff:
                continue
            deduped.setdefault(event.dedupe_id, event)
        return sorted(
            deduped.values(),
            key=lambda item: _parse_event_datetime(item.published_at) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    def _write_source_raw(self, output_path: Path, events: List[NewsEvent]) -> None:
        effective = _effective_datetime(self.effective_date) if self.effective_date else None
        lines: List[str] = []
        for event in events:
            parsed = _parse_event_datetime(event.published_at)
            hash_basis = event.raw_text if event.raw_text_available and event.raw_text else f"{event.title}|{event.url}"
            source_record = {
                "source_id": event.event_id.replace("event:", "src:", 1),
                "provider": event.source_id,
                "source_type": event.source_tier,
                "source_name": event.source_name,
                "source_url": event.url,
                "title": event.title,
                "published_at": event.published_at,
                "event_date": parsed.date().isoformat() if parsed else "",
                "information_available_at": event.published_at,
                "retrieved_at": _utc_now_iso(),
                "effective_date_passed": parsed is None or effective is None or parsed <= effective,
                "raw_text_available": bool(event.raw_text_available),
                "raw_text_excerpt": _clean_text(event.raw_text, 2200) if event.raw_text_available else "",
                "raw_text_hash": hashlib.sha1(hash_basis.encode("utf-8")).hexdigest(),
                "collection_status": event.collection_status if parsed else "date_uncertain",
                "layer_boundary": "layer_2_source_record_only_not_l1_l5_evidence",
            }
            lines.append(json.dumps(source_record, ensure_ascii=False))
        output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "ndx-vnext research console contact=local@example.com",
            "Accept": "application/json, application/rss+xml, application/xml, text/xml;q=0.9,*/*;q=0.8",
        }

    def _should_fetch_article_body(self, title: str, url: str, *, social: bool = False) -> bool:
        if social or not url.lower().startswith(("http://", "https://")):
            return False
        text = f"{title} {url}".lower()
        has_ai = bool(re.search(r"(?<![a-z])ai(?![a-z])", text))
        return has_ai or any(keyword in text for keyword in HIGH_RELEVANCE_BODY_FETCH_KEYWORDS)

    def _fetch_article_body(self, title: str, url: str, *, social: bool = False) -> tuple[str, str]:
        if not self._should_fetch_article_body(title, url, social=social):
            return "", "body_fetch_not_attempted"
        try:
            raw = self.fetch_text(url, self._headers(), self.timeout)
        except Exception as exc:
            return "", f"body_fetch_failed:{str(exc)[:120]}"
        body = _extract_readable_text(raw, 2200)
        if not body:
            return "", "body_fetch_empty_or_unreadable"
        return body, "body_fetch_ok"

    def _collect_rss_events(self) -> tuple[List[NewsEvent], List[Dict[str, str]]]:
        events: List[NewsEvent] = []
        errors: List[Dict[str, str]] = []
        for source in OFFICIAL_RSS_SOURCES:
            try:
                xml_text = self.fetch_text(source["url"], self._headers(), self.timeout)
                for item in _parse_rss_items(xml_text)[: self.max_events_per_source]:
                    title = item.get("title", "").strip()
                    if not title:
                        continue
                    title_l = title.lower()
                    confidence = "high" if any(keyword in title_l for keyword in HIGH_RELEVANCE_KEYWORDS) else "medium"
                    url = item.get("url", "")
                    raw_text, body_status = self._fetch_article_body(title, url)
                    dedupe_id = _dedupe_id(source["source_id"], title, item.get("url", ""), item.get("published_at", ""))
                    events.append(
                        NewsEvent(
                            event_id=f"event:{dedupe_id}",
                            dedupe_id=dedupe_id,
                            source_id=source["source_id"],
                            source_name=source["source_name"],
                            source_tier="official_macro",
                            authority_tier=source["authority_tier"],
                            event_type=source["event_type"],
                            title=title,
                            url=url,
                            published_at=item.get("published_at", ""),
                            relevance_tags=list(source["relevance_tags"]),
                            layers=list(source["relevance_tags"]),
                            symbols=[],
                            confidence=confidence,
                            notes=f"Official RSS item; treat as catalyst/background only. article_body_status={body_status}.",
                            raw_text_available=bool(raw_text),
                            raw_text=raw_text,
                        )
                    )
            except Exception as exc:
                errors.append({"source_id": source["source_id"], "error": str(exc)[:220]})
        return events, errors

    def _collect_sec_events(self) -> tuple[List[NewsEvent], List[Dict[str, str]]]:
        events: List[NewsEvent] = []
        errors: List[Dict[str, str]] = []
        for symbol, cik in M7_SEC_CIKS.items():
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            try:
                raw = self.fetch_text(url, self._headers(), self.timeout)
                data = json.loads(raw)
                recent = data.get("filings", {}).get("recent", {})
                forms = recent.get("form", [])
                accession_numbers = recent.get("accessionNumber", [])
                filing_dates = recent.get("filingDate", [])
                primary_documents = recent.get("primaryDocument", [])
                count = min(len(forms), len(accession_numbers), len(filing_dates), len(primary_documents))
                added = 0
                for idx in range(count):
                    form = forms[idx]
                    if form not in {"8-K", "10-Q", "10-K", "10-K/A", "10-Q/A"}:
                        continue
                    accession = accession_numbers[idx]
                    accession_compact = accession.replace("-", "")
                    document = primary_documents[idx]
                    filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_compact}/{document}"
                    title = f"{symbol} {form} filed {filing_dates[idx]}"
                    dedupe_id = _dedupe_id("sec_submissions", title, filing_url, filing_dates[idx])
                    events.append(
                        NewsEvent(
                            event_id=f"event:{dedupe_id}",
                            dedupe_id=dedupe_id,
                            source_id="sec_submissions",
                            source_name="SEC EDGAR Company Submissions",
                            source_tier="official_filing",
                            authority_tier="official_filing",
                            event_type="issuer_filing",
                            title=title,
                            url=filing_url,
                            published_at=filing_dates[idx],
                            relevance_tags=["L3", "L4"],
                            layers=["L3", "L4"],
                            symbols=[symbol],
                            confidence="high",
                            notes="Official issuer filing for M7 constituent; not a numeric indicator.",
                        )
                    )
                    added += 1
                    if added >= self.max_events_per_source:
                        break
                time.sleep(0.12)
            except Exception as exc:
                errors.append({"source_id": f"sec_submissions:{symbol}", "error": str(exc)[:220]})
        return events, errors

    def _collect_market_news_events(self) -> tuple[List[NewsEvent], List[Dict[str, str]]]:
        events: List[NewsEvent] = []
        errors: List[Dict[str, str]] = []
        yahoo_events, yahoo_errors = self._collect_configured_rss_events(YAHOO_FINANCE_RSS_SOURCES)
        events.extend(yahoo_events)
        errors.extend(yahoo_errors)
        alpha_events, alpha_errors = self._collect_alpha_vantage_events()
        events.extend(alpha_events)
        errors.extend(alpha_errors)
        return events, errors

    def _collect_social_events(self) -> tuple[List[NewsEvent], List[Dict[str, str]]]:
        return self._collect_configured_rss_events(SOCIAL_RSS_SOURCES, social=True)

    def _collect_configured_rss_events(
        self,
        sources: List[Dict[str, Any]],
        *,
        social: bool = False,
    ) -> tuple[List[NewsEvent], List[Dict[str, str]]]:
        events: List[NewsEvent] = []
        errors: List[Dict[str, str]] = []
        for source in sources:
            try:
                xml_text = self.fetch_text(str(source["url"]), self._headers(), self.timeout)
                for item in _parse_rss_items(xml_text)[: self.max_events_per_source]:
                    title = item.get("title", "").strip()
                    if not title:
                        continue
                    source_tier = _social_source_tier(title) if social else str(source["source_tier"])
                    url = item.get("url", "")
                    raw_text, body_status = self._fetch_article_body(title, url, social=social)
                    dedupe_id = _dedupe_id(str(source["source_id"]), title, url, item.get("published_at", ""))
                    events.append(
                        NewsEvent(
                            event_id=f"event:{dedupe_id}",
                            dedupe_id=dedupe_id,
                            source_id=str(source["source_id"]),
                            source_name=str(source["source_name"]),
                            source_tier=source_tier,
                            authority_tier=str(source["authority_tier"]),
                            event_type=str(source["event_type"]),
                            title=title,
                            url=url,
                            published_at=item.get("published_at", ""),
                            relevance_tags=list(source["relevance_tags"]),
                            layers=list(source["relevance_tags"]),
                            symbols=_symbols_from_text(title, list(source.get("symbols", []))),
                            confidence="low" if social else "medium",
                            notes=(
                                f"Social discussion item; useful for narrative temperature only. article_body_status={body_status}."
                                if social
                                else f"Mainstream market-news RSS item; interpretation only, not formal data evidence. article_body_status={body_status}."
                            ),
                            raw_text_available=bool(raw_text),
                            raw_text=raw_text,
                        )
                    )
            except Exception as exc:
                errors.append({"source_id": str(source.get("source_id")), "error": str(exc)[:220]})
        return events, errors

    def _collect_alpha_vantage_events(self) -> tuple[List[NewsEvent], List[Dict[str, str]]]:
        if not is_service_enabled("alphavantage") or not get_api_key("alphavantage"):
            return [], [{"source_id": "alpha_vantage_news_sentiment", "error": "skipped_alpha_vantage_disabled_or_missing_key"}]
        base_url = get_base_url("alphavantage") or "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ",".join(ALPHA_VANTAGE_TICKERS),
            "sort": "LATEST",
            "limit": str(max(10, self.max_events_per_source * 2)),
            "apikey": get_api_key("alphavantage"),
        }
        try:
            response = requests.get(base_url, params=params, headers=self._headers(), timeout=self.timeout, proxies=get_requests_proxies())
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return [], [{"source_id": "alpha_vantage_news_sentiment", "error": str(exc)[:220]}]
        feed = data.get("feed") if isinstance(data, dict) else None
        if not isinstance(feed, list):
            note = data.get("Note") or data.get("Information") if isinstance(data, dict) else ""
            return [], [{"source_id": "alpha_vantage_news_sentiment", "error": str(note or "alpha_vantage_feed_missing")[:220]}]
        events: List[NewsEvent] = []
        for item in feed[: self.max_events_per_source]:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title"), 240)
            if not title:
                continue
            url = str(item.get("url") or "")
            published_at = _alpha_time_to_iso(item.get("time_published"))
            ticker_sentiment = item.get("ticker_sentiment") if isinstance(item.get("ticker_sentiment"), list) else []
            symbols = [
                str(row.get("ticker"))
                for row in ticker_sentiment
                if isinstance(row, dict) and row.get("ticker")
            ]
            dedupe_id = _dedupe_id("alpha_vantage_news_sentiment", title, url, published_at)
            summary = _clean_text(item.get("summary"), 900)
            sentiment = item.get("overall_sentiment_label") or item.get("overall_sentiment_score")
            events.append(
                NewsEvent(
                    event_id=f"event:{dedupe_id}",
                    dedupe_id=dedupe_id,
                    source_id="alpha_vantage_news_sentiment",
                    source_name=str(item.get("source") or "Alpha Vantage News Sentiment"),
                    source_tier="reliable_mainstream_report",
                    authority_tier="third_party_news_sentiment",
                    event_type="structured_news_sentiment",
                    title=title,
                    url=url,
                    published_at=published_at,
                    relevance_tags=["L3", "L4", "L5"],
                    layers=["L3", "L4", "L5"],
                    symbols=_symbols_from_text(" ".join([title, " ".join(symbols)]), symbols),
                    confidence="medium",
                    notes=f"Alpha Vantage NEWS_SENTIMENT item; sentiment={sentiment}. Sentiment is narrative metadata, not investment evidence.",
                    raw_text_available=False,
                    raw_text=summary,
                )
            )
        return events, []

    def _collect_wind_doc_events(self) -> tuple[List[NewsEvent], List[Dict[str, str]]]:
        events: List[NewsEvent] = []
        errors: List[Dict[str, str]] = []
        for source in WIND_DOC_QUERIES:
            payload, error = _call_wind_docs(
                str(source["tool_name"]),
                str(source["query"]),
                top_k=max(1, min(self.max_events_per_source, 10)),
                timeout=max(self.timeout, 30),
            )
            if error:
                errors.append({"source_id": str(source["source_id"]), "error": error})
                continue
            body = _wind_payload_body(payload)
            records = _flatten_dict_records(body)
            if not records and isinstance(body, str) and body.strip():
                records = [{"title": _clean_text(body, 160), "content": _clean_text(body, 1800)}]
            if not records:
                errors.append({"source_id": str(source["source_id"]), "error": "wind_docs_no_records"})
                continue
            for record in records[: self.max_events_per_source]:
                title = _clean_text(_first_field(record, "title", "标题", "name", "summary", "content", "正文"), 240)
                if not title:
                    continue
                url = _first_field(record, "url", "link", "source_url", "链接")
                published_at = _first_field(record, "published_at", "publish_time", "time", "date", "日期", "发布时间")
                raw_text = _clean_text(_first_field(record, "content", "正文", "summary", "摘要", "description"), 1800)
                dedupe_id = _dedupe_id(str(source["source_id"]), title, url, published_at)
                events.append(
                    NewsEvent(
                        event_id=f"event:{dedupe_id}",
                        dedupe_id=dedupe_id,
                        source_id=str(source["source_id"]),
                        source_name=str(source["source_name"]),
                        source_tier=str(source["source_tier"]),
                        authority_tier=str(source["authority_tier"]),
                        event_type=str(source["event_type"]),
                        title=title,
                        url=url,
                        published_at=published_at,
                        relevance_tags=list(source["relevance_tags"]),
                        layers=list(source["relevance_tags"]),
                        symbols=_symbols_from_text(title, list(source.get("symbols", []))),
                        confidence="medium" if raw_text else "low",
                        notes="Wind financial_docs item; licensed source, still layer-2 event material until promoted by formal data rules.",
                        raw_text_available=bool(raw_text),
                        raw_text=raw_text,
                    )
                )
        return events, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an independent vNext news/event ledger.")
    parser.add_argument("--output", default=str(Path(path_config.analysis_dir) / "news_event_ledger.json"))
    parser.add_argument("--no-sec", action="store_true", help="Skip SEC company submissions.")
    parser.add_argument("--no-rss", action="store_true", help="Skip official macro RSS feeds.")
    parser.add_argument("--no-market-news", action="store_true", help="Skip Yahoo Finance and Alpha Vantage market news.")
    parser.add_argument("--no-social", action="store_true", help="Skip social narrative sources such as Reddit RSS.")
    parser.add_argument("--no-wind", action="store_true", help="Skip Wind financial_docs event sources.")
    parser.add_argument("--max-events-per-source", type=int, default=8)
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--effective-date", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    payload = NewsEventLedgerBuilder(
        max_events_per_source=args.max_events_per_source,
        lookback_days=args.lookback_days,
        effective_date=args.effective_date,
    ).build(
        args.output,
        include_sec=not args.no_sec,
        include_rss=not args.no_rss,
        include_market_news=not args.no_market_news,
        include_social=not args.no_social,
        include_wind=not args.no_wind,
    )
    logging.info("news_event_ledger written: %s (%s events)", args.output, len(payload["events"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
