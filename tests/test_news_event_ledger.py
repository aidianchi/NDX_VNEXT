import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from news_event_ledger import NewsEventLedgerBuilder


def test_news_event_ledger_builds_official_sidecar_without_layer_injection(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel><item>
  <title>Federal Reserve issues FOMC statement</title>
  <link>https://www.federalreserve.gov/example.htm</link>
  <pubDate>Fri, 08 May 2026 18:00:00 GMT</pubDate>
</item></channel></rss>"""
    sec = {
        "filings": {
            "recent": {
                "form": ["8-K", "4"],
                "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
                "filingDate": ["2026-05-08", "2026-05-07"],
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
    ).build(output, include_sec=False, include_market_news=False, include_social=False, include_wind=False)

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
    ).build(output, include_sec=False, include_market_news=False, include_social=False, include_wind=False)

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
    <updated>2026-05-08T18:00:00Z</updated>
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
    )

    assert payload["events"][0]["source_tier"] == "unverified_signal"
    assert payload["events"][0]["confidence"] == "low"


def test_news_event_ledger_fetches_body_for_high_relevance_market_news(tmp_path: Path):
    rss = """<?xml version="1.0"?>
<rss><channel><item>
  <title>Micron guidance lifts AI chip outlook for Nasdaq</title>
  <link>https://finance.yahoo.com/news/micron-ai-chip-outlook.html</link>
  <pubDate>Fri, 08 May 2026 18:00:00 GMT</pubDate>
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
  <pubDate>Fri, 08 May 2026 18:00:00 GMT</pubDate>
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
    )

    assert any(error["source_id"] == "alpha_vantage_news_sentiment" for error in payload["source_errors"])
