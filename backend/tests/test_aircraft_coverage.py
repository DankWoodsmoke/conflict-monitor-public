"""Regional coverage cannot invent freshness, altitude or global completeness."""
import asyncio
import math
from collections import OrderedDict

import httpx
import pytest

from app.config import settings
from app.services import opensky as air
from app.services.tracking_contract import iso

NOW = 1793232000.0


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(air, "_regional_snapshots", {})
    monkeypatch.setattr(air, "_regional_health", {})
    monkeypatch.setattr(air, "_tracks", OrderedDict())
    monkeypatch.setattr(air, "_next_attempt", {"adsb.lol": 0, "opensky": 0})
    monkeypatch.setattr(air, "_cache", {"states": [], "timestamp": 0, "jamming": [], "source": None,
        "last_attempt": None, "last_success": None, "source_time": None, "error": None, "rejected_records": 0})


def snapshot(*rows, now=NOW):
    return air.normalize_adsb({"now": now * 1000, "ac": [
        {"hex": identity, "lat": latitude, "lon": longitude, "seen_pos": age, "alt_geom": 0}
        for identity, latitude, longitude, age in rows]}, received=now)


def distance_nm(lat, lon, latitude, longitude):
    a, b = map(math.radians, [lat, latitude])
    angle = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(longitude-lon)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(angle)) / 1.852


def test_named_circles_cover_presets_without_oversized_radius_or_extra_request_budget():
    # The old Iraq-only circle excluded these actual Earth city presets.
    for city in [(32.0853, 34.7818), (25.2048, 55.2708), (35.6892, 51.3890)]:
        assert any(distance_nm(*city, region["lat"], region["lon"]) < air.RADIUS_NM for region in air.AIRCRAFT_REGIONS)
    assert len(air.AIRCRAFT_REGIONS) == 4 and air.RADIUS_NM == 250
    coverage = air.get_aircraft_status(now=NOW)["coverage"]
    assert coverage["kind"] == "regional_circles"
    assert coverage["minimum_request_interval_seconds"] == 15
    assert coverage["nominal_revisit_seconds"] == 60
    assert all(row["status"] == "not_collected" for row in air.get_aircraft_status(now=NOW)["regions"])


def test_overlap_uses_observation_time_not_last_collected_region():
    air._accept_region("levant", snapshot(("abc123", 33, 35, 2)), now=NOW)
    air._accept_region("gulf", snapshot(("abc123", 25, 54, 60), now=NOW+1), now=NOW+1)
    merged = air._merged_regions(now=NOW+2)
    assert len(merged["states"]) == 1
    assert merged["states"][0]["lat"] == 33
    assert merged["states"][0]["observed_timestamp"] == NOW-2


def test_empty_region_replaces_only_its_snapshot_not_other_coverage():
    air._accept_region("levant", snapshot(("abc123", 33, 35, 0)), now=NOW)
    air._accept_region("gulf", snapshot(("abc456", 25, 54, 0)), now=NOW)
    air._accept_region("levant", snapshot(now=NOW+10), now=NOW+10)
    assert [row["icao24"] for row in air._merged_regions(now=NOW+10)["states"]] == ["abc456"]


def test_failed_region_preserves_original_success_and_does_not_refresh_its_clock():
    air._accept_region("levant", snapshot(("abc123", 33, 35, 0)), now=NOW)
    air._regional_health["levant"].update(last_attempt_at=NOW+30, error="adsb.lol:HTTP_429")
    status = air.get_aircraft_status(now=NOW+60)["regions"][0]
    assert status["status"] == "failed" and status["last_success_at"] == iso(NOW)
    assert status["cache_age_seconds"] == 60
    assert air._merged_regions(now=NOW+119)["states"]
    assert air._merged_regions(now=NOW+121)["states"] == []
    assert air._merged_regions(now=NOW+181) is None


def test_snapshot_and_export_are_independent_copies_and_unknown_regions_rejected():
    data = snapshot(("abc123", 33, 35, 0))
    with pytest.raises(ValueError, match="Unknown"):
        air._accept_region("unbounded-custom", data, now=NOW)
    assert not air._regional_snapshots
    air._accept_region("levant", data, now=NOW)
    data["states"][0]["lat"] = -90
    merged = air._merged_regions(now=NOW)
    assert merged["states"][0]["lat"] == 33
    merged["states"][0]["lat"] = -80
    assert air._merged_regions(now=NOW)["states"][0]["lat"] == 33


def test_merged_identity_budget_keeps_newest_positions_and_expires_future_samples(monkeypatch):
    air._accept_region("levant", snapshot(("abc001", 33, 35, 20), ("abc002", 33, 35, 10)), now=NOW)
    air._accept_region("gulf", snapshot(("abc003", 25, 54, 2), ("abc004", 25, 54, 1)), now=NOW)
    monkeypatch.setattr(air, "MAX_AIRCRAFT", 2)
    assert [row["icao24"] for row in air._merged_regions(now=NOW)["states"]] == ["abc004", "abc003"]
    assert air._merged_regions(now=NOW-1) is None


@pytest.mark.asyncio
async def test_live_loop_rotates_regions_serially_at_existing_request_budget(monkeypatch):
    calls, pauses = [], []
    async def poll(client, *, region):
        calls.append(region["id"])
        return snapshot()
    async def fallback(client):
        raise AssertionError("Valid empty coverage must not spend fallback quota")
    async def pause(seconds):
        pauses.append(seconds)
        if len(pauses) == 5:
            raise asyncio.CancelledError
    monkeypatch.setattr(air, "_poll_adsb_lol", poll)
    monkeypatch.setattr(air, "_poll_opensky", fallback)
    monkeypatch.setattr(air.time, "time", lambda: NOW)
    monkeypatch.setattr(air.asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        await air.start_opensky_poller()
    assert calls == ["levant", "gulf", "iran_iraq", "red_sea", "levant"]
    assert pauses == [15] * 5


@pytest.mark.asyncio
async def test_real_adapter_path_uses_selected_circle_and_public_radius(monkeypatch):
    paths = []
    def respond(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"now": NOW*1000, "ac": []})
    monkeypatch.setattr(air.time, "time", lambda: NOW)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await air._poll_adsb_lol(client, region=air.AIRCRAFT_REGIONS[1]) is not None
    assert paths == ["/v2/lat/25/lon/54/dist/250"]


@pytest.mark.parametrize("changes, expected, source", [
    ({"alt_geom": 0, "alt_baro": 10000}, "geometric_reported", "alt_geom"),
    ({"alt_baro": 10000}, "barometric_standard_pressure", "alt_baro"),
    ({"alt_baro": "ground"}, "unknown", None),
    ({}, "unknown", None),
])
def test_altitude_reference_is_explicit_and_missing_altitude_stays_missing(changes, expected, source):
    row = {"hex": "abc123", "lat": 33, "lon": 35, "seen_pos": 0, **changes}
    value = air.normalize_adsb({"now": NOW*1000, "ac": [row]}, received=NOW)["states"][0]
    assert value["altitude_reference"] == expected and value["altitude_source"] == source
    if expected == "unknown":
        assert value["altitude"] is None
    elif source == "alt_geom":
        assert value["altitude"] == 0
