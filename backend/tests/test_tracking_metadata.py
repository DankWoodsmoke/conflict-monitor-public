"""Source-normalization to replay preservation, without claiming ground accuracy."""
from copy import deepcopy

import pytest

from app.services.opensky import normalize_adsb, normalize_opensky
from app.services.snapshots import _compact_aircraft, _compact_vessels

NOW = 1793232000.0

def sample(**fields):
    return {"now": NOW * 1000, "ac": [{"hex": "abc123", "lat": 30.12345678,
        "lon": 45.87654321, "seen_pos": 5, "alt_geom": 2000, "track": 0,
        "true_heading": 90, "nac_p": 10, "nic": 8, **fields}]}

@pytest.mark.parametrize("fields,heading,basis", [
    ({}, 0, "course_over_ground"),
    ({"track": None}, 90, "true_heading"),
    ({"track": 360}, 90, "true_heading"),
    ({"track": False, "true_heading": None}, None, None),
    ({"track": -1, "true_heading": 360}, None, None),
])
def test_direction_basis_survives_provider_to_future_snapshot(fields, heading, basis):
    original = sample(**fields)
    frozen = deepcopy(original)
    row = normalize_adsb(original, received=NOW)["states"][0]
    saved = _compact_aircraft([row])[0]
    assert row["heading"] == saved["h"] == heading
    assert row["heading_basis"] == basis
    assert saved.get("heading_basis") == basis
    assert saved["la"] == row["lat"] == 30.12345678
    assert saved["lo"] == row["lon"] == 45.87654321
    for key in ("observed_at", "received_at", "source", "altitude_reference", "nic", "nac_p"):
        assert saved[key] == row[key]
    assert original == frozen

def test_opensky_track_is_course_and_unknown_snapshot_values_stay_unknown():
    states = ["abc123", "FIXTURE", "", NOW - 5, NOW, 45, 30, 2000, False, 200, 0, 0, None, 2100, "", False, 0]
    row = normalize_opensky({"time": NOW, "states": [states]}, received=NOW)["states"][0]
    assert row["heading_basis"] == "course_over_ground"
    assert _compact_aircraft([row])[0]["heading_basis"] == "course_over_ground"
    legacy = _compact_vessels([{"mmsi": "123456789", "lat": 0, "lon": 0}])[0]
    assert legacy["h"] is None and legacy["sp"] is None
    assert not {"observed_at", "received_at", "heading_basis", "course"} & legacy.keys()

def test_vessel_snapshot_keeps_independent_course_and_source_clocks():
    source = {"mmsi": "123456789", "lat": 0, "lon": 50.12345678, "heading": 55,
        "heading_basis": "true_heading", "course": 0, "observed_at": "2026-10-29T12:00:00Z",
        "received_at": "2026-10-29T12:00:02Z"}
    saved = _compact_vessels([source])[0]
    assert saved["h"] == 55 and saved["course"] == 0 and saved["heading_basis"] == "true_heading"
    assert saved["lo"] == source["lon"]
    assert saved["observed_at"] == source["observed_at"] and saved["received_at"] == source["received_at"]

@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), 181])
def test_invalid_snapshot_coordinates_are_not_admitted(bad):
    assert _compact_vessels([{"lat": 0, "lon": bad}]) == []
    assert _compact_aircraft([{"lat": 30, "lon": bad}]) == []
