import json
from pathlib import Path

from src.analog_history_audit import (
    build_audit,
    count_independent_directional_clusters,
    detect_source_breaks,
    normalize_rows,
    write_audit,
)


def _dated_rows(count: int, *, source_id: str = "TEST", state: str | None = None):
    rows = []
    for index in range(count):
        row = {
            "date": f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}",
            "value": float(index),
            "source_id": source_id,
        }
        if state:
            row["state"] = state
        rows.append(row)
    return rows


def test_detects_source_break_without_stitching():
    rows = normalize_rows(
        [
            {"date": "2026-01-01", "value": 1, "source_id": "old"},
            {"date": "2026-01-02", "value": 2, "source_id": "new"},
        ],
        default_source_id="fallback",
    )

    assert detect_source_breaks(rows) == [
        {
            "date": "2026-01-02",
            "from_source_id": "old",
            "to_source_id": "new",
            "reasons": ["source_id_changed"],
        }
    ]


def test_same_direction_cluster_requires_63_cleaned_trading_day_positions():
    rows = _dated_rows(127)
    for row in rows:
        row["state"] = None
    rows[0]["state"] = "up"
    rows[62]["state"] = "up"
    rows[63]["state"] = "up"
    rows[1]["state"] = "down"
    rows[64]["state"] = "down"

    result = count_independent_directional_clusters(rows)

    assert result["count_by_direction"] == {"up": 2, "down": 2}
    assert [(row["index"], row["state"]) for row in result["accepted_observations"]] == [
        (0, "up"),
        (1, "down"),
        (63, "up"),
        (64, "down"),
    ]


def test_constructed_smoke_writes_audit_only_artifacts(tmp_path: Path):
    histories = {
        "dfii10": {"rows": _dated_rows(70, source_id="FRED_DFII10")},
        "hy_oas": {"rows": _dated_rows(70, source_id="FRED_BAMLH0A0HYM2")},
        "vix": {"rows": _dated_rows(70, source_id="YFINANCE_VIX")},
        "ndx_valuation_percentile": {
            "rows": [
                {"date": "2020-01-01", "value": 20, "source_id": "HOM_TRAILING_PE"},
                {"date": "2021-01-01", "value": 25, "source_id": "HOM_FORWARD_PE"},
            ]
        },
    }

    audit = build_audit(as_of="2026-07-19", candidate_histories=histories)
    paths = write_audit(audit, tmp_path)
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    markdown = paths["markdown"].read_text(encoding="utf-8")

    assert payload["purpose"] == "data_history_audit_only"
    assert payload["metric_authority"] == "audit_only"
    assert payload["admission"]["analogy_engine"] == "rejected_insufficient_clean_pit_history"
    assert any(
        "non_stitchable_source_and_methodology_lineage" in item["reasons"]
        for item in payload["candidates"][2]["source_migration_breaks"]
    )
    assert "未计算状态后的收益分布" in markdown
    serialized = json.dumps(payload, ensure_ascii=False)
    assert '"win_rate":' not in serialized
    assert '"conditional_return":' not in serialized


def test_as_of_hard_filter_excludes_future_rows_from_history_and_clusters():
    histories = {
        key: {
            "rows": [
                {"date": "2020-01-01", "value": 1, "state": "up"},
                {"date": "2026-01-01", "value": 2, "state": "up"},
            ]
        }
        for key in ("dfii10", "hy_oas", "vix", "ndx_valuation_percentile")
    }

    audit = build_audit(as_of="2020-01-01", candidate_histories=histories)

    for candidate in audit["candidates"]:
        assert candidate["history"]["usable_end"] == "2020-01-01"
        assert candidate["history"]["observation_count"] == 1
        assert candidate["as_of_filter"]["excluded_after_as_of_count"] == 1
        assert candidate["independent_directional_cluster_audit"]["count_total"] == 1
    assert not audit["candidates"][1]["source_migration_breaks"]
