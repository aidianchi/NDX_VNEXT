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
    from .tools_L4 import get_m7_earnings_blackout_calendar
except ImportError:
    from api_config import get_api_key, get_base_url, get_requests_proxies, is_service_enabled
    from config import path_config
    from tools_L4 import get_m7_earnings_blackout_calendar

logger = logging.getLogger(__name__)

FetchText = Callable[[str, Dict[str, str], int], str]

TOPIC_MACRO_RATES = "topic:macro_rates"
TOPIC_CREDIT_VOL = "topic:credit_vol"
TOPIC_INDEX_STRUCTURE = "topic:index_structure"
TOPIC_VALUATION_EARNINGS = "topic:valuation_earnings"
TOPIC_TREND_EXECUTION = "topic:trend_execution"

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
        "relevance_tags": [TOPIC_MACRO_RATES, TOPIC_CREDIT_VOL, TOPIC_VALUATION_EARNINGS],
    },
    {
        "source_id": "bls_latest",
        "source_name": "BLS Latest Numbers",
        "url": "https://www.bls.gov/feed/bls_latest.rss",
        "authority_tier": "official",
        "event_type": "macro_data_release",
        "relevance_tags": [TOPIC_MACRO_RATES],
    },
    {
        "source_id": "bea_news",
        "source_name": "BEA News",
        "url": "https://www.bea.gov/news/rss",
        "authority_tier": "official",
        "event_type": "macro_data_release",
        "relevance_tags": [TOPIC_MACRO_RATES, TOPIC_VALUATION_EARNINGS],
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
        "relevance_tags": [TOPIC_INDEX_STRUCTURE, TOPIC_VALUATION_EARNINGS, TOPIC_TREND_EXECUTION],
        "symbols": ["QQQ", "NDX"],
    },
    {
        "source_id": "yahoo_finance_m7_headlines",
        "source_name": "Yahoo Finance M7 Headlines",
        "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA&region=US&lang=en-US",
        "source_tier": "reliable_mainstream_report",
        "authority_tier": "market_news_aggregator",
        "event_type": "mega_cap_market_news",
        "relevance_tags": [TOPIC_INDEX_STRUCTURE, TOPIC_VALUATION_EARNINGS],
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
        "relevance_tags": [TOPIC_TREND_EXECUTION],
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
        "source_tier": "aggregator_report",
        "authority_tier": "licensed_provider/Wind",
        "event_type": "issuer_announcement_or_filing",
        "relevance_tags": [TOPIC_INDEX_STRUCTURE, TOPIC_VALUATION_EARNINGS],
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
        "relevance_tags": [TOPIC_MACRO_RATES, TOPIC_INDEX_STRUCTURE, TOPIC_VALUATION_EARNINGS, TOPIC_TREND_EXECUTION],
        "symbols": ["NDX", "QQQ"],
    },
]

OFFICIAL_CALENDAR_SOURCES = {
    "fomc_meeting_calendar": {
        "source_name": "Federal Reserve FOMC Meeting Calendar",
        "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "relevance_tags": [TOPIC_MACRO_RATES],
    },
    "bls_release_calendar": {
        "source_name": "BLS Release Calendar",
        "url": "https://www.bls.gov/schedule/news_release/bls.ics",
        "relevance_tags": [TOPIC_MACRO_RATES],
    },
    "bea_release_calendar": {
        "source_name": "BEA Release Calendar",
        "url": "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics",
        "relevance_tags": [TOPIC_MACRO_RATES, TOPIC_VALUATION_EARNINGS],
    },
    "nasdaq_index_announcements": {
        "source_name": "Nasdaq Press Center Index Announcements",
        "url": "https://www.nasdaq.com/about/press-center",
        "relevance_tags": [TOPIC_INDEX_STRUCTURE],
    },
}

M7_ENTITY_ALIASES = {
    "AAPL": ["APPLE", "苹果"],
    "MSFT": ["MICROSOFT", "微软"],
    "GOOGL": ["ALPHABET", "GOOGLE", "谷歌"],
    "AMZN": ["AMAZON", "亚马逊"],
    "NVDA": ["NVIDIA", "英伟达"],
    "META": ["META PLATFORMS", "FACEBOOK", "脸书"],
    "TSLA": ["TESLA", "特斯拉"],
}

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
    event_date: str = ""
    relevance: str = "medium"
    raw_text_available: bool = False
    raw_text: str = ""
    collection_status: str = "ok"
    published_at_basis: str = "source_timestamp"

    def to_dict(self) -> Dict[str, Any]:
        event_date = self.event_date
        parsed = _parse_event_datetime(self.published_at)
        if not event_date and parsed is not None:
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
            "published_at_basis": self.published_at_basis,
            "event_date": event_date,
            "information_available_at": self.published_at,
            "raw_text_available": bool(self.raw_text_available),
            "raw_text_excerpt": _clean_text(self.raw_text, 2200) if self.raw_text_available else "",
            "raw_text_hash": hashlib.sha1(hash_basis.encode("utf-8")).hexdigest(),
            "collection_status": self.collection_status if self.published_at else "date_uncertain",
            "relevance_tags": self.relevance_tags,
            "layers": self.layers,
            "symbols": self.symbols,
            "relevance": self.relevance,
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


def _symbols_from_text(text: str) -> List[str]:
    upper = text.upper()
    found = [
        symbol
        for symbol in ALPHA_VANTAGE_TICKERS + ["NDX"]
        if re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", upper)
    ]
    if "NASDAQ 100" in upper or "NASDAQ-100" in upper:
        found.extend(["NDX", "QQQ"])
    return sorted(dict.fromkeys(found))


def _m7_symbols_from_text(text: str) -> List[str]:
    upper = text.upper()
    symbols = _symbols_from_text(text)
    for symbol, aliases in M7_ENTITY_ALIASES.items():
        if any(
            (
                re.search(rf"(?<![A-Z0-9]){re.escape(alias.upper())}(?![A-Z0-9])", upper)
                if alias.isascii()
                else alias in text
            )
            for alias in aliases
        ):
            symbols.append(symbol)
    return sorted({symbol for symbol in symbols if symbol in M7_SEC_CIKS})


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unfold_ics(raw: str) -> List[str]:
    lines: List[str] = []
    for line in str(raw or "").replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line.strip())
    return lines


def _ics_datetime(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc)
    return None


def _parse_ics_events(raw: str) -> List[Dict[str, str]]:
    events: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for line in _unfold_ics(raw):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and current.get("summary") and current.get("event_date"):
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        raw_key, value = line.split(":", 1)
        key = raw_key.split(";", 1)[0].upper()
        if key == "SUMMARY":
            current["summary"] = value.replace("\\,", ",").replace("\\n", " ").strip()
        elif key == "DTSTART":
            parsed = _ics_datetime(value)
            if parsed is not None:
                current["event_date"] = parsed.date().isoformat()
        elif key == "DTSTAMP":
            parsed = _ics_datetime(value)
            if parsed is not None:
                current["published_at"] = _iso_utc(parsed)
    return events


def _parse_fomc_calendar(raw: str) -> List[Dict[str, str]]:
    year_matches = list(re.finditer(r"(20\d{2})\s+FOMC\s+Meetings", raw, flags=re.IGNORECASE))
    month_pattern = re.compile(
        r'class=["\'][^"\']*fomc-meeting__month[^"\']*["\'][^>]*>(.*?)</',
        flags=re.IGNORECASE | re.DOTALL,
    )
    date_pattern = re.compile(
        r'class=["\'][^"\']*fomc-meeting__date[^"\']*["\'][^>]*>(.*?)</',
        flags=re.IGNORECASE | re.DOTALL,
    )
    month_numbers = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }
    parsed_events: List[Dict[str, str]] = []
    for index, year_match in enumerate(year_matches):
        year = int(year_match.group(1))
        end = year_matches[index + 1].start() if index + 1 < len(year_matches) else len(raw)
        section = raw[year_match.end():end]
        months = [_clean_text(re.sub(r"<[^>]+>", " ", value)) for value in month_pattern.findall(section)]
        dates = [_clean_text(re.sub(r"<[^>]+>", " ", value)) for value in date_pattern.findall(section)]
        for month_text, date_text in zip(months, dates):
            month_key = month_text.split("/")[-1].strip().lower()
            month = month_numbers.get(month_key)
            day_numbers = [int(item) for item in re.findall(r"\d{1,2}", date_text)]
            if month is None or not day_numbers:
                continue
            day = day_numbers[-1]
            try:
                event_date = datetime(year, month, day, tzinfo=timezone.utc).date().isoformat()
            except ValueError:
                continue
            parsed_events.append(
                {
                    "summary": f"FOMC meeting ({month_text} {date_text}, {year})",
                    "event_date": event_date,
                }
            )
    if parsed_events:
        return parsed_events

    plain = html_lib.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    plain = " ".join(plain.split())
    year_matches = list(re.finditer(r"(20\d{2})\s+FOMC\s+Meetings", plain, flags=re.IGNORECASE))
    meeting_pattern = re.compile(
        r"(?<!Released\s)(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}(?:\s*[-–]\s*\d{1,2})?)\*?",
        flags=re.IGNORECASE,
    )
    for index, year_match in enumerate(year_matches):
        year = int(year_match.group(1))
        end = year_matches[index + 1].start() if index + 1 < len(year_matches) else len(plain)
        for match in meeting_pattern.finditer(plain[year_match.end():end]):
            month_text, date_text = match.groups()
            month = month_numbers[month_text.lower()]
            day = int(re.findall(r"\d{1,2}", date_text)[-1])
            try:
                event_date = datetime(year, month, day, tzinfo=timezone.utc).date().isoformat()
            except ValueError:
                continue
            parsed_events.append(
                {
                    "summary": f"FOMC meeting ({month_text} {date_text}, {year})",
                    "event_date": event_date,
                }
            )
    return parsed_events


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
    xml_text = str(xml_text or "").lstrip("\ufeff")
    if xml_text.startswith("ï»¿"):
        xml_text = xml_text[3:]
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
        self.collected_at = datetime.now(timezone.utc)

    def build(
        self,
        output_path: str | Path,
        include_sec: bool = True,
        include_rss: bool = True,
        include_market_news: bool = True,
        include_social: bool = True,
        include_wind: bool = True,
        include_calendars: bool = True,
    ) -> Dict[str, Any]:
        events: List[NewsEvent] = []
        source_errors: List[Dict[str, Any]] = []
        if include_calendars:
            calendar_events, calendar_errors = self._collect_official_calendar_events()
            events.extend(calendar_events)
            source_errors.extend(calendar_errors)
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
        scheduled_future_events = [event for event in events if event.collection_status == "scheduled_future"]
        realized_events = [event for event in events if event.collection_status != "scheduled_future"]

        payload = {
            "schema_version": "news_event_ledger_v2",
            "generated_at_utc": _iso_utc(self.collected_at),
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
                    "aggregator_report",
                    "official",
                    "third_party_calendar",
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
                    "official_calendar_adapter",
                    "m7_earnings_calendar_adapter",
                ],
                "dedupe_key": "source_id + normalized title + url + published date",
                "lookback_days": self.lookback_days,
                "effective_date": self.effective_date,
                "window_anchor": "effective_date" if self.effective_date else "collected_at",
                "collected_at": _iso_utc(self.collected_at),
                "event_fields": ["source_tier", "event_type", "published_at", "event_date", "collection_status", "symbols", "relevance_tags", "dedupe_id", "source_errors"],
                "raw_text_rule": "raw_text_available=true only when an adapter retrieves document/body text, not merely title, URL, or vendor sentiment metadata.",
                "social_rule": "social sources are market_narrative by default; rumor/leak/unconfirmed titles are downgraded to unverified_signal.",
            },
            "sources": {
                "rss": [source["source_id"] for source in OFFICIAL_RSS_SOURCES] if include_rss else [],
                "sec_submissions": sorted(M7_SEC_CIKS) if include_sec else [],
                "market_news": ([source["source_id"] for source in YAHOO_FINANCE_RSS_SOURCES] + ["alpha_vantage_news_sentiment"]) if include_market_news else [],
                "social": [source["source_id"] for source in SOCIAL_RSS_SOURCES] if include_social else [],
                "wind_docs": [source["source_id"] for source in WIND_DOC_QUERIES] if include_wind else [],
                "official_calendars": (list(OFFICIAL_CALENDAR_SOURCES) + ["m7_earnings_calendar"]) if include_calendars else [],
            },
            "events": [event.to_dict() for event in realized_events],
            "scheduled_future_events": [event.to_dict() for event in scheduled_future_events],
            "source_errors": source_errors,
        }
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._write_source_raw(output.parent / "event_source_raw.jsonl", events)
        return payload

    def _dedupe_and_window(self, events: List[NewsEvent]) -> List[NewsEvent]:
        effective = _effective_datetime(self.effective_date) if self.effective_date else self.collected_at
        cutoff = effective - timedelta(days=max(0, self.lookback_days))
        deduped: Dict[str, NewsEvent] = {}
        for event in events:
            is_calendar = event.event_type == "official_calendar"
            parsed = _parse_event_datetime(event.event_date if is_calendar else event.published_at)
            if parsed is None:
                continue
            if not is_calendar and parsed > effective:
                continue
            if self.lookback_days > 0 and parsed < cutoff:
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
                "published_at_basis": event.published_at_basis,
                "event_date": event.event_date or (parsed.date().isoformat() if parsed else ""),
                "information_available_at": event.published_at,
                "retrieved_at": _iso_utc(self.collected_at),
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

    def _calendar_anchor(self) -> datetime:
        return _effective_datetime(self.effective_date) if self.effective_date else self.collected_at

    def _select_calendar_events(self, candidates: List[NewsEvent]) -> List[NewsEvent]:
        limit = max(0, self.max_events_per_source)
        if limit == 0 or len(candidates) <= limit:
            return candidates[:limit] if limit == 0 else candidates
        anchor_date = self._calendar_anchor().date()
        future = sorted(
            (event for event in candidates if str(event.event_date) > anchor_date.isoformat()),
            key=lambda event: str(event.event_date),
        )
        realized = sorted(
            (event for event in candidates if str(event.event_date) <= anchor_date.isoformat()),
            key=lambda event: str(event.event_date),
            reverse=True,
        )
        future_quota = min(len(future), max(1, limit // 2)) if future else 0
        selected = future[:future_quota] + realized[: limit - future_quota]
        if len(selected) < limit:
            selected.extend(future[future_quota : future_quota + (limit - len(selected))])
        return sorted(selected[:limit], key=lambda event: str(event.event_date))

    def _calendar_event(
        self,
        *,
        source_id: str,
        source_name: str,
        source_url: str,
        title: str,
        event_date: str,
        published_at: str = "",
        relevance_tags: List[str],
        source_tier: str = "official",
        authority_tier: str = "official_calendar",
        symbols: Optional[List[str]] = None,
    ) -> Optional[NewsEvent]:
        parsed_event = _parse_event_datetime(event_date)
        if parsed_event is None:
            return None
        anchor = self._calendar_anchor()
        if self.lookback_days > 0 and parsed_event < anchor - timedelta(days=self.lookback_days):
            return None
        collected_at = _iso_utc(self.collected_at)
        parsed_published_at = _parse_event_datetime(published_at)
        published_at_value = _iso_utc(parsed_published_at) if parsed_published_at is not None else collected_at
        published_at_basis = "source_timestamp" if parsed_published_at is not None else "collected_at_fallback"
        status = "scheduled_future" if parsed_event.date() > anchor.date() else "calendar_event_current_or_past"
        dedupe_id = _dedupe_id(source_id, title, source_url, event_date)
        return NewsEvent(
            event_id=f"event:{dedupe_id}",
            dedupe_id=dedupe_id,
            source_id=source_id,
            source_name=source_name,
            source_tier=source_tier,
            authority_tier=authority_tier,
            event_type="official_calendar",
            title=title,
            url=source_url,
            published_at=published_at_value,
            published_at_basis=published_at_basis,
            event_date=parsed_event.date().isoformat(),
            relevance_tags=list(relevance_tags),
            layers=list(relevance_tags),
            symbols=list(symbols or []),
            relevance="medium",
            confidence="high" if source_tier == "official" else "medium",
            notes=(
                f"Scheduled calendar event; event_date is distinct from published_at. published_at_basis={published_at_basis}. "
                "scheduled_future entries are not realized-event evidence."
            ),
            collection_status=status,
        )

    def _collect_official_calendar_events(self) -> tuple[List[NewsEvent], List[Dict[str, Any]]]:
        events: List[NewsEvent] = []
        errors: List[Dict[str, Any]] = []
        anchor = self._calendar_anchor()
        if self.effective_date and self.collected_at.date() > anchor.date():
            reason = "live_calendar_not_pit_safe_for_historical_effective_date"
            return [], [
                {"source_id": source_id, "error": reason}
                for source_id in list(OFFICIAL_CALENDAR_SOURCES) + ["m7_earnings_calendar"]
            ]

        for source_id in ("fomc_meeting_calendar", "bls_release_calendar", "bea_release_calendar"):
            source = OFFICIAL_CALENDAR_SOURCES[source_id]
            try:
                raw = self.fetch_text(str(source["url"]), self._headers(), self.timeout)
                records = _parse_fomc_calendar(raw) if source_id == "fomc_meeting_calendar" else _parse_ics_events(raw)
                candidates: List[NewsEvent] = []
                for record in records:
                    event = self._calendar_event(
                        source_id=source_id,
                        source_name=str(source["source_name"]),
                        source_url=str(source["url"]),
                        title=str(record.get("summary") or "Scheduled official release"),
                        event_date=str(record.get("event_date") or ""),
                        published_at=str(record.get("published_at") or ""),
                        relevance_tags=list(source["relevance_tags"]),
                    )
                    if event is None:
                        continue
                    candidates.append(event)
                selected = self._select_calendar_events(candidates)
                events.extend(selected)
                added = len(selected)
                if added == 0:
                    errors.append({"source_id": source_id, "error": "official_calendar_parse_no_records_in_window"})
            except Exception as exc:
                errors.append({"source_id": source_id, "error": str(exc)[:220]})

        nasdaq_id = "nasdaq_index_announcements"
        nasdaq_source = OFFICIAL_CALENDAR_SOURCES[nasdaq_id]
        try:
            raw = self.fetch_text(str(nasdaq_source["url"]), self._headers(), self.timeout)
            records = self._parse_nasdaq_index_announcements(raw)
            if not records:
                errors.append({"source_id": nasdaq_id, "error": "nasdaq_index_announcements_parse_no_records"})
            for record in records[: self.max_events_per_source]:
                event = self._calendar_event(
                    source_id=nasdaq_id,
                    source_name=str(nasdaq_source["source_name"]),
                    source_url=str(record.get("url") or nasdaq_source["url"]),
                    title=str(record.get("summary") or "Nasdaq index announcement"),
                    event_date=str(record.get("event_date") or ""),
                    relevance_tags=list(nasdaq_source["relevance_tags"]),
                )
                if event is not None:
                    events.append(event)
        except Exception as exc:
            errors.append({"source_id": nasdaq_id, "error": str(exc)[:220]})

        try:
            m7_result = get_m7_earnings_blackout_calendar(anchor.date().isoformat())
            value = m7_result.get("value") if isinstance(m7_result, dict) else None
            rows = value.get("upcoming_28d_calendar", []) if isinstance(value, dict) else []
            added = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ticker = str(row.get("ticker") or "").upper()
                event_date = str(row.get("earnings_date") or "")
                if ticker not in M7_SEC_CIKS:
                    continue
                event = self._calendar_event(
                    source_id="m7_earnings_calendar",
                    source_name=str(m7_result.get("source_name") or "M7 earnings calendar"),
                    source_url=str(m7_result.get("source_url") or "https://finance.yahoo.com/calendar/earnings/"),
                    title=f"{ticker} scheduled earnings date",
                    event_date=event_date,
                    relevance_tags=[TOPIC_VALUATION_EARNINGS],
                    source_tier="third_party_calendar",
                    authority_tier=str(m7_result.get("source_tier") or "third_party_unofficial"),
                    symbols=[ticker],
                )
                if event is not None:
                    events.append(event)
                    added += 1
            if added == 0:
                errors.append({"source_id": "m7_earnings_calendar", "error": "m7_earnings_calendar_no_records_in_window"})
        except Exception as exc:
            errors.append({"source_id": "m7_earnings_calendar", "error": str(exc)[:220]})
        return events, errors

    def _parse_nasdaq_index_announcements(self, raw: str) -> List[Dict[str, str]]:
        records: List[Dict[str, str]] = []
        pattern = re.compile(
            r'<a[^>]+href=["\'](?P<url>[^"\']+)["\'][^>]*>(?P<title>.*?)</a>',
            flags=re.IGNORECASE | re.DOTALL,
        )
        for match in pattern.finditer(raw or ""):
            title = _clean_text(re.sub(r"<[^>]+>", " ", match.group("title")), 240)
            if not re.search(r"nasdaq[- ]?100|\bndx\b|index (?:rebalance|reconstitution|announcement)", title, re.IGNORECASE):
                continue
            nearby = (raw or "")[max(0, match.start() - 180): min(len(raw or ""), match.end() + 180)]
            date_match = re.search(
                r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})|([A-Z][a-z]+)\s+(\d{1,2}),\s*(20\d{2})",
                nearby,
            )
            if not date_match:
                continue
            date_text = date_match.group(0)
            parsed = _parse_event_datetime(date_text)
            if parsed is None:
                for fmt in ("%B %d, %Y", "%b %d, %Y"):
                    try:
                        parsed = datetime.strptime(date_text, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        pass
            if parsed is None:
                continue
            url = match.group("url")
            if url.startswith("/"):
                url = "https://www.nasdaq.com" + url
            records.append({"summary": title, "event_date": parsed.date().isoformat(), "url": url})
        return records

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
                            relevance_tags=[TOPIC_INDEX_STRUCTURE, TOPIC_VALUATION_EARNINGS],
                            layers=[TOPIC_INDEX_STRUCTURE, TOPIC_VALUATION_EARNINGS],
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
                    symbols = _symbols_from_text(title)
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
                            symbols=symbols,
                            relevance="low" if not symbols else "medium",
                            confidence="low" if social or not symbols else "medium",
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
            detected_symbols = _symbols_from_text(" ".join([title, " ".join(symbols)]))
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
                    relevance_tags=[TOPIC_INDEX_STRUCTURE, TOPIC_VALUATION_EARNINGS, TOPIC_TREND_EXECUTION],
                    layers=[TOPIC_INDEX_STRUCTURE, TOPIC_VALUATION_EARNINGS, TOPIC_TREND_EXECUTION],
                    symbols=detected_symbols,
                    relevance="low" if not detected_symbols else "medium",
                    confidence="low" if not detected_symbols else "medium",
                    notes=f"Alpha Vantage NEWS_SENTIMENT item; sentiment={sentiment}. Sentiment is narrative metadata, not investment evidence.",
                    raw_text_available=False,
                    raw_text=summary,
                )
            )
        return events, []

    def _collect_wind_doc_events(self) -> tuple[List[NewsEvent], List[Dict[str, Any]]]:
        events: List[NewsEvent] = []
        errors: List[Dict[str, Any]] = []
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
            dropped_no_entity_match = 0
            for record in records[: self.max_events_per_source]:
                title = _clean_text(_first_field(record, "title", "标题", "name", "summary", "content", "正文"), 240)
                if not title:
                    continue
                url = _first_field(record, "url", "link", "source_url", "链接")
                published_at = _first_field(record, "published_at", "publish_time", "time", "date", "日期", "发布时间")
                raw_text = _clean_text(_first_field(record, "content", "正文", "summary", "摘要", "description"), 1800)
                m7_symbols = _m7_symbols_from_text(f"{title} {raw_text}")
                detected_symbols = _symbols_from_text(f"{title} {raw_text}")
                if source["source_id"] == "wind_company_announcements_m7" and not m7_symbols:
                    dropped_no_entity_match += 1
                    continue
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
                        symbols=m7_symbols or detected_symbols,
                        relevance="low" if not (m7_symbols or detected_symbols) else "medium",
                        confidence="medium" if raw_text and (m7_symbols or detected_symbols) else "low",
                        notes="Wind financial_docs item; licensed source, still layer-2 event material until promoted by formal data rules.",
                        raw_text_available=bool(raw_text),
                        raw_text=raw_text,
                    )
                )
            if dropped_no_entity_match:
                errors.append(
                    {
                        "source_id": str(source["source_id"]),
                        "error": "dropped_no_entity_match",
                        "count": dropped_no_entity_match,
                    }
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
    parser.add_argument("--no-calendars", action="store_true", help="Skip official and M7 calendar event sources.")
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
        include_calendars=not args.no_calendars,
    )
    logging.info("news_event_ledger written: %s (%s events)", args.output, len(payload["events"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
