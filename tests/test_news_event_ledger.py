import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import news_event_ledger
from news_event_ledger import NewsEventLedgerBuilder


def test_news_event_ledger_builds_official_sidecar_without_layer_injection(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel><item>
  <title>Federal Reserve issues FOMC statement</title>
  <link>https://www.federalreserve.gov/example.htm</link>
  <pubDate>Fri, 17 Jul 2026 18:00:00 GMT</pubDate>
</item></channel></rss>"""
    sec = {
        "filings": {
            "recent": {
                "form": ["8-K", "4"],
                "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
                "filingDate": ["2026-07-17", "2026-07-16"],
                "primaryDocument": ["aapl-20260508.htm", "xslF345X05/doc4.xml"],
            }
        }
    }

    def fake_fetch(url, headers, timeout):
        assert "User-Agent" in headers
        if "data.sec.gov" in url:
            return json.dumps(sec)
        return rss

    output = tmp_path / "news_event_ledger.json"
    payload = NewsEventLedgerBuilder(fetch_text=fake_fetch, max_events_per_source=1).build(
        output,
        include_market_news=False,
        include_social=False,
        include_wind=False,
        include_calendars=False,
    )

    assert output.exists()
    assert payload["schema_version"] == "news_event_ledger_v2"
    assert "not injected into L1-L5" in payload["policy"]["runtime_context_rule"]
    assert payload["governance"]["lookback_days"] == 45
    assert any(event["source_id"] == "federal_reserve_press_all" for event in payload["events"])
    assert any(event["source_id"] == "sec_submissions" and event["symbols"] == ["AAPL"] for event in payload["events"])
    for event in payload["events"]:
        assert event["event_id"].startswith("event:")
        assert event["dedupe_id"]
        assert event["source_tier"] in {"official_macro", "official_filing"}
        assert event["event_type"]
        assert event["published_at"]
        assert isinstance(event["layers"], list)


def test_news_event_ledger_backtest_window_uses_effective_date(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel>
<item><title>Past FOMC statement</title><link>https://www.federalreserve.gov/past.htm</link><pubDate>Tue, 08 Apr 2025 18:00:00 GMT</pubDate></item>
<item><title>Future FOMC statement</title><link>https://www.federalreserve.gov/future.htm</link><pubDate>Thu, 10 Apr 2025 18:00:00 GMT</pubDate></item>
</channel></rss>"""

    def fake_fetch(url, headers, timeout):
        return rss

    output = tmp_path / "news_event_ledger.json"
    payload = NewsEventLedgerBuilder(
        fetch_text=fake_fetch,
        max_events_per_source=5,
        effective_date="2025-04-09",
        lookback_days=45,
    ).build(
        output,
        include_sec=False,
        include_market_news=False,
        include_social=False,
        include_wind=False,
        include_calendars=False,
    )

    titles = {event["title"] for event in payload["events"]}
    assert "Past FOMC statement" in titles
    assert "Future FOMC statement" not in titles
    assert payload["governance"]["effective_date"] == "2025-04-09"


def test_news_event_ledger_writes_source_records_and_excludes_undated_history(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel>
<item><title>Dated FOMC statement</title><link>https://www.federalreserve.gov/dated.htm</link><pubDate>Tue, 08 Apr 2025 18:00:00 GMT</pubDate></item>
<item><title>Undated FOMC statement</title><link>https://www.federalreserve.gov/undated.htm</link></item>
</channel></rss>"""

    def fake_fetch(url, headers, timeout):
        return rss

    output = tmp_path / "news_event_ledger.json"
    payload = NewsEventLedgerBuilder(
        fetch_text=fake_fetch,
        max_events_per_source=5,
        effective_date="2025-04-09",
    ).build(
        output,
        include_sec=False,
        include_market_news=False,
        include_social=False,
        include_wind=False,
        include_calendars=False,
    )

    assert {event["title"] for event in payload["events"]} == {"Dated FOMC statement"}
    raw_path = tmp_path / "event_source_raw.jsonl"
    records = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["source_id"].startswith("src:")
    assert records[0]["information_available_at"]
    assert records[0]["effective_date_passed"] is True
    assert records[0]["raw_text_available"] is False
    assert records[0]["layer_boundary"] == "layer_2_source_record_only_not_l1_l5_evidence"


def test_news_event_ledger_classifies_reddit_rumor_as_unverified_signal(tmp_path: Path):
    reddit = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Rumor about QQQ mega cap guidance</title>
    <link href="https://www.reddit.com/r/stocks/example"/>
  <updated>2026-07-17T18:00:00Z</updated>
  </entry>
</feed>"""

    def fake_fetch(url, headers, timeout):
        return reddit

    output = tmp_path / "news_event_ledger.json"
    payload = NewsEventLedgerBuilder(fetch_text=fake_fetch, max_events_per_source=2).build(
        output,
        include_sec=False,
        include_rss=False,
        include_market_news=False,
        include_wind=False,
        include_calendars=False,
    )

    assert payload["events"][0]["source_tier"] == "unverified_signal"
    assert payload["events"][0]["confidence"] == "low"


def test_news_event_ledger_fetches_body_for_high_relevance_market_news(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel><item>
  <title>Micron guidance lifts AI chip outlook for Nasdaq</title>
  <link>https://finance.yahoo.com/news/micron-ai-chip-outlook.html</link>
  <pubDate>Fri, 17 Jul 2026 18:00:00 GMT</pubDate>
</item></channel></rss>"""
    article = """<!doctype html><html><body><article>
<p>Micron raised its outlook as demand for AI memory chips improved.</p>
<p>Analysts said the update may affect semiconductor earnings expectations.</p>
</article></body></html>"""

    def fake_fetch(url, headers, timeout):
        if "micron-ai-chip-outlook" in url:
            return article
        return rss

    output = tmp_path / "news_event_ledger.json"
    payload = NewsEventLedgerBuilder(fetch_text=fake_fetch, max_events_per_source=1).build(
        output,
        include_sec=False,
        include_rss=False,
        include_social=False,
        include_wind=False,
        include_calendars=False,
    )

    event = payload["events"][0]
    assert event["raw_text_available"] is True
    assert "Micron raised its outlook" in event["raw_text_excerpt"]
    assert "article_body_status=body_fetch_ok" in event["notes"]


def test_news_event_ledger_does_not_treat_error_shell_as_article_body(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel><item>
  <title>AI Funds Were Unstoppable in the Second Quarter</title>
  <link>https://finance.yahoo.com/news/ai-funds.html</link>
  <pubDate>Fri, 17 Jul 2026 18:00:00 GMT</pubDate>
</item></channel></rss>"""
    shell = """<!doctype html><html><body>
<p>AI Funds Were Unstoppable in the Second Quarter Oops, something went wrong Skip to navigation Skip to main content</p>
</body></html>"""

    def fake_fetch(url, headers, timeout):
        if "ai-funds" in url:
            return shell
        return rss

    output = tmp_path / "news_event_ledger.json"
    payload = NewsEventLedgerBuilder(fetch_text=fake_fetch, max_events_per_source=1).build(
        output,
        include_sec=False,
        include_rss=False,
        include_social=False,
        include_wind=False,
        include_calendars=False,
    )

    event = payload["events"][0]
    assert event["raw_text_available"] is False
    assert event["raw_text_excerpt"] == ""
    assert "body_fetch_empty_or_unreadable" in event["notes"]


def test_news_event_ledger_alpha_vantage_skip_is_source_error(tmp_path: Path, monkeypatch):
    import news_event_ledger

    monkeypatch.setattr(news_event_ledger, "is_service_enabled", lambda service: False)

    output = tmp_path / "news_event_ledger.json"
    payload = NewsEventLedgerBuilder(fetch_text=lambda *_: "", max_events_per_source=1).build(
        output,
        include_sec=False,
        include_rss=False,
        include_social=False,
        include_wind=False,
        include_calendars=False,
    )

    assert any(error["source_id"] == "alpha_vantage_news_sentiment" for error in payload["source_errors"])


def test_news_event_ledger_without_effective_date_still_filters_old_events(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel><item>
  <title>Two year old market headline</title>
  <link>https://example.com/old</link>
  <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
</item></channel></rss>"""
    builder = NewsEventLedgerBuilder(fetch_text=lambda *_: rss, max_events_per_source=1)
    builder.collected_at = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)

    payload = builder.build(
        tmp_path / "news_event_ledger.json",
        include_sec=False,
        include_rss=False,
        include_social=False,
        include_wind=False,
        include_calendars=False,
    )

    assert payload["events"] == []
    assert payload["governance"]["window_anchor"] == "collected_at"


def test_rss_parser_accepts_federal_reserve_mojibake_bom():
    rss = """ï»¿<?xml version="1.0" encoding="utf-8"?>
<rss><channel><item>
  <title>Federal Reserve issues FOMC statement</title>
  <link>https://www.federalreserve.gov/example.htm</link>
  <pubDate>Fri, 17 Jul 2026 18:00:00 GMT</pubDate>
</item></channel></rss>"""

    items = news_event_ledger._parse_rss_items(rss)

    assert [item["title"] for item in items] == ["Federal Reserve issues FOMC statement"]


def test_bea_rss_source_uses_current_official_endpoint():
    source = next(item for item in news_event_ledger.OFFICIAL_RSS_SOURCES if item["source_id"] == "bea_news")

    assert source["url"] == "https://www.bea.gov/news/rss"


def test_news_event_ledger_does_not_assign_default_symbols_without_entity_match(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel><item>
  <title>Mountview announces local community award</title>
  <link>https://example.com/mountview</link>
  <pubDate>Fri, 17 Jul 2026 12:00:00 GMT</pubDate>
</item></channel></rss>"""
    builder = NewsEventLedgerBuilder(fetch_text=lambda *_: rss, max_events_per_source=1)
    builder.collected_at = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)

    payload = builder.build(
        tmp_path / "news_event_ledger.json",
        include_sec=False,
        include_rss=False,
        include_social=False,
        include_wind=False,
        include_calendars=False,
    )

    assert payload["events"]
    assert all(event["symbols"] == [] for event in payload["events"])
    assert all(event["relevance"] == "low" for event in payload["events"])
    assert all(event["confidence"] == "low" for event in payload["events"])


def test_wind_company_announcements_drop_mountview_without_m7_entity(monkeypatch):
    def fake_wind(tool_name, query, top_k, timeout):
        if tool_name == "get_company_announcements":
            return {
                "data": [
                    {
                        "title": "Mountview announces board update",
                        "content": "Mountview published a local governance notice.",
                        "date": "2026-07-17",
                    }
                ]
            }, None
        return None, "fixture_skip_other_source"

    monkeypatch.setattr(news_event_ledger, "_call_wind_docs", fake_wind)

    events, errors = NewsEventLedgerBuilder(max_events_per_source=3)._collect_wind_doc_events()

    assert events == []
    dropped = next(error for error in errors if error["source_id"] == "wind_company_announcements_m7")
    assert dropped["error"] == "dropped_no_entity_match"
    assert dropped["count"] == 1


def test_wind_company_announcements_are_aggregator_reports(monkeypatch):
    def fake_wind(tool_name, query, top_k, timeout):
        if tool_name == "get_company_announcements":
            return {
                "data": [
                    {
                        "title": "Microsoft updates earnings guidance",
                        "content": "Microsoft discussed its latest outlook.",
                        "date": "2026-07-17",
                    }
                ]
            }, None
        return None, "fixture_skip_other_source"

    monkeypatch.setattr(news_event_ledger, "_call_wind_docs", fake_wind)

    events, _errors = NewsEventLedgerBuilder(max_events_per_source=3)._collect_wind_doc_events()

    assert len(events) == 1
    assert events[0].source_tier == "aggregator_report"
    assert events[0].symbols == ["MSFT"]


def test_wind_company_announcements_do_not_match_english_alias_substrings(monkeypatch):
    def fake_wind(tool_name, query, top_k, timeout):
        if tool_name == "get_company_announcements":
            return {
                "data": [
                    {
                        "title": "Pineapple Research publishes a local board update",
                        "content": "The Pineapple Research cooperative discussed community grants.",
                        "date": "2026-07-17",
                    }
                ]
            }, None
        return None, "fixture_skip_other_source"

    monkeypatch.setattr(news_event_ledger, "_call_wind_docs", fake_wind)

    events, errors = NewsEventLedgerBuilder(max_events_per_source=3)._collect_wind_doc_events()

    assert events == []
    dropped = next(error for error in errors if error["source_id"] == "wind_company_announcements_m7")
    assert dropped["count"] == 1


def test_official_calendars_keep_future_as_scheduled_and_exclude_old_items(tmp_path: Path, monkeypatch):
    fed = """
    <h4>2026 FOMC Meetings</h4>
    <div class="fomc-meeting__month">July</div><div class="fomc-meeting__date">28-29</div>
    <h4>2024 FOMC Meetings</h4>
    <div class="fomc-meeting__month">January</div><div class="fomc-meeting__date">30-31</div>
    """
    bls = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Consumer Price Index
DTSTART:20260714T123000Z
DTSTAMP:20260701T120000Z
END:VEVENT
END:VCALENDAR
"""
    bea = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Gross Domestic Product
DTSTART:20260730T123000Z
DTSTAMP:20260701T120000Z
END:VEVENT
END:VCALENDAR
"""

    def fake_fetch(url, headers, timeout):
        if "federalreserve.gov" in url:
            return fed
        if "bls.gov" in url:
            return bls
        if "bea.gov" in url:
            return bea
        raise RuntimeError("nasdaq fixture unavailable")

    monkeypatch.setattr(
        news_event_ledger,
        "get_m7_earnings_blackout_calendar",
        lambda _date: {
            "source_name": "Yahoo Finance earnings dates",
            "source_tier": "third_party_unofficial",
            "source_url": "https://finance.yahoo.com/calendar/earnings/",
            "value": {
                "upcoming_28d_calendar": [
                    {"ticker": "AAPL", "earnings_date": "2026-07-22"}
                ]
            },
        },
    )
    builder = NewsEventLedgerBuilder(
        fetch_text=fake_fetch,
        max_events_per_source=10,
        effective_date="2026-07-18",
    )
    builder.collected_at = datetime(2026, 7, 18, 1, 0, tzinfo=timezone.utc)

    payload = builder.build(
        tmp_path / "news_event_ledger.json",
        include_sec=False,
        include_rss=False,
        include_market_news=False,
        include_social=False,
        include_wind=False,
    )

    assert not any(event["collection_status"] == "scheduled_future" for event in payload["events"])
    assert payload["scheduled_future_events"]
    assert all(event["collection_status"] == "scheduled_future" for event in payload["scheduled_future_events"])
    calendar_events = [
        event
        for event in payload["events"] + payload["scheduled_future_events"]
        if event["event_type"] == "official_calendar"
    ]
    assert calendar_events
    assert all(event["event_date"] >= "2026-06-03" for event in calendar_events)
    assert not any(event["event_date"].startswith("2024-") for event in calendar_events)
    future = [event for event in calendar_events if event["event_date"] > "2026-07-18"]
    assert future
    assert all(event["collection_status"] == "scheduled_future" for event in future)
    official = [event for event in calendar_events if event["source_id"] != "m7_earnings_calendar"]
    assert all(event["source_tier"] == "official" for event in official)
    bls_event = next(event for event in calendar_events if event["source_id"] == "bls_release_calendar")
    assert bls_event["published_at"] == "2026-07-01T12:00:00Z"
    assert bls_event["published_at_basis"] == "source_timestamp"
    m7 = next(event for event in calendar_events if event["source_id"] == "m7_earnings_calendar")
    assert m7["source_tier"] == "third_party_calendar"
    assert any(error["source_id"] == "nasdaq_index_announcements" for error in payload["source_errors"])


def test_news_source_relevance_tags_use_topics_not_layer_labels():
    source_groups = [
        news_event_ledger.OFFICIAL_RSS_SOURCES,
        news_event_ledger.YAHOO_FINANCE_RSS_SOURCES,
        news_event_ledger.SOCIAL_RSS_SOURCES,
        news_event_ledger.WIND_DOC_QUERIES,
        list(news_event_ledger.OFFICIAL_CALENDAR_SOURCES.values()),
    ]

    tags = [tag for group in source_groups for source in group for tag in source["relevance_tags"]]

    assert tags
    assert all(tag.startswith("topic:") for tag in tags)
    assert not any(tag in {"L1", "L2", "L3", "L4", "L5"} for tag in tags)


def test_fomc_calendar_parser_falls_back_to_official_page_text_without_css_classes():
    raw = """
    <h4>2026 FOMC Meetings</h4>
    <p>January</p><p>27-28</p>
    <p>Minutes: (Released February 18, 2026)</p>
    <p>July</p><p>28-29</p>
    <p>September</p><p>15-16*</p>
    """

    records = news_event_ledger._parse_fomc_calendar(raw)

    assert [record["event_date"] for record in records] == [
        "2026-01-28",
        "2026-07-29",
        "2026-09-16",
    ]


def test_official_calendar_limit_preserves_nearest_future_releases(tmp_path: Path, monkeypatch):
    bls_rows = "\n".join(
        f"""BEGIN:VEVENT
SUMMARY:Past release {day}
DTSTART:202607{day:02d}T123000Z
DTSTAMP:20260701T120000Z
END:VEVENT"""
        for day in range(1, 11)
    )
    bls = f"""BEGIN:VCALENDAR
{bls_rows}
BEGIN:VEVENT
SUMMARY:Future CPI release
DTSTART:20260720T123000Z
DTSTAMP:20260701T120000Z
END:VEVENT
BEGIN:VEVENT
SUMMARY:Future employment release
DTSTART:20260724T123000Z
DTSTAMP:20260701T120000Z
END:VEVENT
END:VCALENDAR
"""

    def fake_fetch(url, headers, timeout):
        if "bls.gov" in url:
            return bls
        if "bea.gov" in url:
            return "BEGIN:VCALENDAR\nEND:VCALENDAR"
        if "federalreserve.gov" in url:
            return "<h4>2026 FOMC Meetings</h4>"
        raise RuntimeError("candidate unavailable")

    monkeypatch.setattr(
        news_event_ledger,
        "get_m7_earnings_blackout_calendar",
        lambda _date: {"value": {"upcoming_28d_calendar": []}},
    )
    builder = NewsEventLedgerBuilder(fetch_text=fake_fetch, max_events_per_source=4)
    builder.collected_at = datetime(2026, 7, 18, 1, 0, tzinfo=timezone.utc)

    payload = builder.build(
        tmp_path / "news_event_ledger.json",
        include_sec=False,
        include_rss=False,
        include_market_news=False,
        include_social=False,
        include_wind=False,
    )

    bls_events = [
        event
        for event in payload["events"] + payload["scheduled_future_events"]
        if event["source_id"] == "bls_release_calendar"
    ]
    assert len(bls_events) == 4
    assert {event["title"] for event in bls_events if event["collection_status"] == "scheduled_future"} == {
        "Future CPI release",
        "Future employment release",
    }
