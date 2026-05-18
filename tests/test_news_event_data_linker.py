import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from news_event_data_linker import NewsEventDataLinker, write_news_event_data_links


def _ledger():
    return {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:fomc",
                "dedupe_id": "fomc",
                "title": "Federal Reserve issues FOMC statement",
                "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                "source_tier": "official_macro",
                "event_type": "policy_or_financial_conditions",
                "symbols": [],
                "layers": ["L1", "L2", "L4"],
            }
        ],
    }


def _chart_time_series():
    return {
        "schema_version": "vnext_chart_time_series_v1",
        "series": {
            "QQQ_OHLCV": {
                "label": "QQQ",
                "frequency": "daily",
                "rows": [
                    {"time": "2026-05-07", "close": 450.0},
                    {"time": "2026-05-08", "close": 455.0},
                    {"time": "2026-05-11", "close": 468.0},
                ],
            },
            "VIX": {
                "label": "VIX",
                "frequency": "daily",
                "rows": [
                    {"time": "2026-05-07", "value": 18.0},
                    {"time": "2026-05-08", "value": 20.0},
                    {"time": "2026-05-11", "value": 23.0},
                ],
            },
        },
    }


def test_news_event_data_linker_writes_observational_sidecar_without_evidence_refs():
    payload = NewsEventDataLinker(windows_days=[1, 5]).build(
        event_ledger=_ledger(),
        chart_time_series=_chart_time_series(),
        analysis_packet={"meta": {"data_date": "2026-05-08"}, "event_refs": {"event:fomc": {}}},
    )

    assert payload["schema_version"] == "news_event_data_links_v1"
    assert "no causal proof" in payload["policy"]["causality_rule"]
    assert "evidence_ref" in payload["policy"]["evidence_rule"]
    assert payload["analysis_packet_context"]["event_refs_available"] == 1
    assert payload["links"][0]["event_ref"] == "event:fomc"
    assert "evidence_ref" not in payload["links"][0]
    observation_types = {item["observation_type"] for item in payload["links"][0]["observations"]}
    assert observation_types <= {"co_movement_observation", "needs_bridge_review"}
    assert any(item["association_type"] == "temporal_association" for item in payload["links"][0]["observations"])
    assert any(item["series_key"] == "QQQ_OHLCV" for item in payload["links"][0]["observations"])


def test_write_news_event_data_links_reads_run_dir_artifacts(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "news_event_ledger.json").write_text(json.dumps(_ledger()), encoding="utf-8")
    (run_dir / "chart_time_series.json").write_text(json.dumps(_chart_time_series()), encoding="utf-8")
    (run_dir / "analysis_packet.json").write_text(json.dumps({"meta": {"data_date": "2026-05-08"}}), encoding="utf-8")

    output = write_news_event_data_links(run_dir)
    payload = json.loads(Path(output).read_text(encoding="utf-8"))

    assert Path(output).name == "news_event_data_links.json"
    assert payload["source_artifacts"]["news_event_ledger"].endswith("news_event_ledger.json")
    assert payload["links"][0]["link_boundary"].startswith("temporal_association only")


def test_news_event_data_linker_drops_future_events_and_observations():
    ledger = _ledger()
    ledger["events"].append(
        {
            "event_id": "event:future",
            "dedupe_id": "future",
            "title": "Future event",
            "published_at": "Tue, 12 May 2026 18:00:00 GMT",
            "source_tier": "official_macro",
            "event_type": "policy_or_financial_conditions",
            "symbols": [],
            "layers": ["L1"],
        }
    )
    chart = _chart_time_series()
    chart["effective_date"] = "2026-05-08"

    payload = NewsEventDataLinker(windows_days=[5]).build(
        event_ledger=ledger,
        chart_time_series=chart,
    )

    assert payload["effective_date"] == "2026-05-08"
    assert {link["event_id"] for link in payload["links"]} == {"event:fomc"}
    for observation in payload["links"][0]["observations"]:
        assert observation["end_time"] <= "2026-05-08"
