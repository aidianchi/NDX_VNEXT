import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from data_availability import (
    NO_DATA_AVAILABLE,
    has_meaningful_observation_value,
    no_data_reason,
    normalize_no_data_payload,
)


def test_normalize_no_data_payload_overrides_available_availability():
    payload = {
        "value": {"level": None},
        "availability": "available",
        "data_quality": {"availability": "available"},
    }

    normalized = normalize_no_data_payload(payload, reason="empty_observation")

    assert normalized["availability"] == "unavailable"
    assert normalized["availability_sentinel"] == NO_DATA_AVAILABLE
    assert normalized["data_quality"]["availability"] == "unavailable"
    assert normalized["data_quality"]["sentinel"] == NO_DATA_AVAILABLE
    assert no_data_reason(normalized) == "empty_observation"


def test_metadata_only_payload_is_not_meaningful_observation():
    payload = {
        "date": "2026-06-08",
        "source_name": "example",
        "data_quality": {"availability": "available", "source_tier": "proxy"},
    }

    assert has_meaningful_observation_value(payload) is False
