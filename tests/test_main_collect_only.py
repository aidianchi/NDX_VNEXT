import os
import sys
import json
import hashlib
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main
from agent_analysis.packet_builder import AnalysisPacketBuilder


class _FakeCollector:
    def run(self, backtest_date=None, enable_news=False):
        return {
            "backtest_date": backtest_date,
            "indicators": [
                {"function_id": "get_vix", "raw_data": {"value": {"level": 17.2}}},
            ],
        }


def test_collect_only_exits_after_data_collection(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DataCollector", lambda: _FakeCollector())
    monkeypatch.setattr(main.path_config, "data_dir", str(tmp_path))

    summary = main.run_collect_only(
        SimpleNamespace(date="2026-05-09", data_json=None, enable_news=False)
    )

    assert summary["mode"] == "collect_only"
    assert summary["indicator_count"] == 1
    assert summary["data_json"].endswith("data_collected_v9_20260509.json")


def test_load_data_json_normalizes_legacy_indicator_contracts(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "backtest_date": "2025-04-09",
                "indicators": [
                    {
                        "layer": 3,
                        "function_id": "get_advance_decline_line",
                        "collection_timestamp_utc": "2025-04-10T00:00:00Z",
                        "raw_data": {
                            "name": "Advance/Decline Line",
                            "value": {"level": None, "date": None},
                            "notes": "Failed to calculate: Insufficient data returned from yfinance.",
                            "data_quality": {"availability": "available"},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = main.load_data_json(str(path))

    quality = loaded["indicators"][0]["raw_data"]["data_quality"]
    assert quality["availability"] == "unavailable"
    assert quality["effective_date"] == "2025-04-09"


def test_load_data_json_records_exact_snapshot_identity(tmp_path):
    path = tmp_path / "data_collected_v9_20250409.json"
    raw = json.dumps({
        "backtest_date": "2025-04-09",
        "collection_timestamp": "2025-04-10T01:02:03Z",
        "indicators": [],
    }).encode()
    path.write_bytes(raw)

    loaded = main.load_data_json(str(path))
    audit = loaded["source_snapshot"]

    assert audit["mode"] == "snapshot_replay"
    assert audit["source_filename"] == path.name
    assert audit["source_path"] == str(path.resolve())
    assert audit["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert audit["effective_date"] == "2025-04-09"
    assert audit["collection_time"] == "2025-04-10T01:02:03Z"
    assert "source_snapshot" not in json.dumps(
        AnalysisPacketBuilder().build(loaded).model_dump(mode="json")
    )


def test_load_data_json_migrates_nested_recompute_input_out_of_analysis_packet(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({
        "backtest_date": "2025-04-09",
        "indicators": [{
            "layer": 5,
            "function_id": "get_unit_metric",
            "raw_data": {
                "value": {"level": 1.0},
                "recompute_input": {"raw_series": [{"date": "2025-04-09", "value": 1.0}]},
            },
        }],
    }), encoding="utf-8")

    loaded = main.load_data_json(str(path))

    assert "recompute_input" not in loaded["indicators"][0]["raw_data"]
    assert loaded["recompute_inputs"]["get_unit_metric"]["raw_series"][0]["value"] == 1.0
    assert "recompute_input" not in AnalysisPacketBuilder().build(loaded).model_dump_json()


def test_collector_snapshot_records_the_written_file_hash(monkeypatch, tmp_path):
    monkeypatch.setattr(main.path_config, "data_dir", str(tmp_path))
    source = tmp_path / "data_collected_v9_live.json"
    raw = b'{"indicators": []}'
    source.write_bytes(raw)

    audit = main._collector_source_snapshot(None, {
        "timestamp_utc": "2026-07-17T01:02:03Z",
        "collection_timestamp_utc": "wrong-field-fallback",
    })

    assert audit["source_file_status"] == "observed"
    assert audit["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert audit["file_modified_at_utc"] != "not_recorded"
    assert audit["collection_time"] == "2026-07-17T01:02:03Z"


def test_collector_snapshot_does_not_invent_a_collection_time(monkeypatch, tmp_path):
    monkeypatch.setattr(main.path_config, "data_dir", str(tmp_path))

    audit = main._collector_source_snapshot(None, {})

    assert audit["source_file_status"] == "not_recorded"
    assert audit["source_sha256"] == "not_recorded"
    assert audit["collection_time"] == "not_recorded"


def test_snapshot_effective_date_cannot_be_relabelled():
    data = {"source_snapshot": {"effective_date": "2025-04-09"}}

    assert main._resolve_snapshot_effective_date(None, data) == "2025-04-09"
    assert main._resolve_snapshot_effective_date("2025-04-09", data) == "2025-04-09"
    try:
        main._resolve_snapshot_effective_date("2025-04-10", data)
    except ValueError as exc:
        assert "refusing to relabel" in str(exc)
    else:
        raise AssertionError("conflicting snapshot date must fail closed")


def test_live_snapshot_cannot_be_relabelled_as_historical():
    data = {"source_snapshot": {"effective_date": "not_recorded", "mode": "snapshot_replay"}}

    try:
        main._resolve_snapshot_effective_date("2025-04-09", data)
    except ValueError as exc:
        assert "explicit historical effective_date" in str(exc)
    else:
        raise AssertionError("an undated live snapshot must not be relabelled as historical")


def test_event_only_rejects_snapshot_date_before_creating_run(monkeypatch, tmp_path):
    snapshot = tmp_path / "live.json"
    snapshot.write_text(json.dumps({"timestamp_utc": "2026-07-17T01:02:03Z", "indicators": []}), encoding="utf-8")
    monkeypatch.setattr(main, "build_run_dir", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("too late")))

    args = SimpleNamespace(
        date="2025-04-09",
        data_json=str(snapshot),
        run_id=None,
        output_dir=None,
        resume_from_existing=False,
    )
    try:
        main.run_event_only(args)
    except ValueError as exc:
        assert "explicit historical effective_date" in str(exc)
    else:
        raise AssertionError("event-only must enforce snapshot date before creating artifacts")


def test_declared_snapshot_effective_date_becomes_canonical_backtest_date(tmp_path):
    snapshot = tmp_path / "dated_snapshot.json"
    snapshot.write_text(json.dumps({
        "effective_date": "2025-04-09",
        "indicators": [{
            "layer": 2,
            "function_id": "get_vix",
            "raw_data": {
                "name": "VIX",
                "value": {"level": 18.0},
                "date": "2026-07-17",
                "source_name": "market data provider",
            },
        }],
    }), encoding="utf-8")

    loaded = main.load_data_json(str(snapshot))
    resolved = main._resolve_snapshot_effective_date("2025-04-09", loaded)
    packet = AnalysisPacketBuilder().build(loaded)

    assert resolved == "2025-04-09"
    assert loaded["backtest_date"] == "2025-04-09"
    assert packet.meta["backtest_date"] == "2025-04-09"
    assert packet.raw_data["L2"]["get_vix"]["error"] == "data_evidence_hard_block"
    assert packet.raw_data["L2"]["get_vix"]["value"] is None
