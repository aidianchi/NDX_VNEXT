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
    payload = NewsEventLedgerBuilder(fetch_text=fake_fetch, max_events_per_source=1).build(output)

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
