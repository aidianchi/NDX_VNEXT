from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from xml.etree import ElementTree

import requests

try:
    from .api_config import get_requests_proxies
    from .config import path_config
except ImportError:
    from api_config import get_requests_proxies
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

    def to_dict(self) -> Dict[str, Any]:
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
    ) -> None:
        self.fetch_text = fetch_text
        self.max_events_per_source = max_events_per_source
        self.timeout = timeout
        self.lookback_days = lookback_days

    def build(self, output_path: str | Path, include_sec: bool = True, include_rss: bool = True) -> Dict[str, Any]:
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
                "source_tiers": ["official_macro", "official_filing"],
                "dedupe_key": "source_id + normalized title + url + published date",
                "lookback_days": self.lookback_days,
                "event_fields": ["source_tier", "event_type", "published_at", "symbols", "layers", "dedupe_id", "source_errors"],
            },
            "sources": {
                "rss": [source["source_id"] for source in OFFICIAL_RSS_SOURCES] if include_rss else [],
                "sec_submissions": sorted(M7_SEC_CIKS) if include_sec else [],
            },
            "events": [event.to_dict() for event in events],
            "source_errors": source_errors,
        }
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def _dedupe_and_window(self, events: List[NewsEvent]) -> List[NewsEvent]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, self.lookback_days))
        deduped: Dict[str, NewsEvent] = {}
        for event in events:
            parsed = _parse_event_datetime(event.published_at)
            if parsed is not None and self.lookback_days > 0 and parsed < cutoff:
                continue
            deduped.setdefault(event.dedupe_id, event)
        return sorted(
            deduped.values(),
            key=lambda item: _parse_event_datetime(item.published_at) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "ndx-vnext research console contact=local@example.com",
            "Accept": "application/json, application/rss+xml, application/xml, text/xml;q=0.9,*/*;q=0.8",
        }

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
                            url=item.get("url", ""),
                            published_at=item.get("published_at", ""),
                            relevance_tags=list(source["relevance_tags"]),
                            layers=list(source["relevance_tags"]),
                            symbols=[],
                            confidence=confidence,
                            notes="Official RSS item; treat as catalyst/background only.",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an independent vNext news/event ledger.")
    parser.add_argument("--output", default=str(Path(path_config.analysis_dir) / "news_event_ledger.json"))
    parser.add_argument("--no-sec", action="store_true", help="Skip SEC company submissions.")
    parser.add_argument("--no-rss", action="store_true", help="Skip official macro RSS feeds.")
    parser.add_argument("--max-events-per-source", type=int, default=8)
    parser.add_argument("--lookback-days", type=int, default=45)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    payload = NewsEventLedgerBuilder(max_events_per_source=args.max_events_per_source, lookback_days=args.lookback_days).build(
        args.output,
        include_sec=not args.no_sec,
        include_rss=not args.no_rss,
    )
    logging.info("news_event_ledger written: %s (%s events)", args.output, len(payload["events"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
