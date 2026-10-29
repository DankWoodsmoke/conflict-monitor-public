"""Receiver-data boundary/freshness tests: no live sources, sockets or paid APIs."""
import json
from collections import OrderedDict

import httpx
import pytest

from app.config import settings
from app.services import maritime as sea, opensky as air
from app.services.tracking_contract import bounded_json, iso

NOW = 1793232000.0


@pytest.fixture(autouse=True)
def isolated_tracking(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(settings, "aisstream_api_key", "offline-fixture")
    monkeypatch.setattr(air, "_cache", {"states": [], "timestamp": 0, "jamming": [], "source": None,
        "last_attempt": None, "last_success": None, "source_time": None, "error": None, "rejected_records": 0})
    monkeypatch.setattr(air, "_tracks", OrderedDict())
    monkeypatch.setattr(air, "_next_attempt", {"adsb.lol": 0, "opensky": 0})
    monkeypatch.setattr(sea, "_cache", {"vessels": OrderedDict(), "last_update": None, "last_attempt": None,
        "last_message": None, "last_prune": 0, "connected": False, "error": None,
        "rejected_messages": 0, "evicted_records": 0, "compression_enabled": None})


def aircraft(**changes):
    return {"hex": "abc123", "flight": "SYNTH", "lat": 30, "lon": 45, "seen_pos": 5,
            "alt_geom": 0, "alt_baro": 10000, "gs": 100, "track": 0, "true_heading": 90,
            "baro_rate": 0, "geom_rate": 1000, **changes}


def adsb(*rows, timestamp=NOW):
    return {"now": timestamp * 1000, "ac": list(rows)}


def ais(*, identity="413123456", when=NOW, kind="PositionReport", **changes):
    report = {"UserID": int(identity), "Valid": True, "Latitude": 30, "Longitude": 45,
              "Sog": 10.1, "Cog": 0, "TrueHeading": 511, "NavigationalStatus": 0, **changes}
    meta = {"MMSI": int(identity), "ShipName": "SYNTHETIC TEST"}
    if when is not None:
        meta["time_utc"] = iso(when)
    return json.dumps({"MessageType": kind, "MetaData": meta, "Message": {kind: report}})


def test_aircraft_preserves_zeroes_and_normalizes_units():
    row = air.normalize_adsb(adsb(aircraft()), received=NOW)["states"][0]
    assert row["altitude"] == row["heading"] == row["climb_rate"] == 0
    assert row["velocity"] == pytest.approx(51.44444444)
    assert row["observed_at"] == iso(NOW - 5)
    assert row["received_at"] == iso(NOW)
    assert row["units"]["altitude"] == "m"


@pytest.mark.parametrize("changes", [{"lat":float("nan")}, {"lon":181}, {"lat":True},
    {"hex":"abc123-too-long"}, {"hex":"invalid"}, {"seen_pos":-1},
    {"lat":None,"lon":None,"rr_lat":30,"rr_lon":45}])
def test_bad_aircraft_position_or_identity_cannot_replace_snapshot(changes):
    with pytest.raises(ValueError):
        air.normalize_adsb(adsb(aircraft(**changes)), received=NOW)


def test_source_clock_not_collection_clock_controls_aircraft_expiry():
    with pytest.raises(ValueError):
        air.normalize_adsb(adsb(aircraft(), timestamp=NOW - 500), received=NOW)
    with pytest.raises(ValueError):
        air.normalize_adsb(adsb(aircraft(), timestamp=NOW + 100), received=NOW)
    snapshot = air.normalize_adsb(adsb(aircraft()), received=NOW)
    air._publish_snapshot(snapshot, now=NOW)
    assert air.get_aircraft(now=NOW + 50)[0]["stale"] is True
    assert air.get_aircraft(now=NOW + 121) == []
    assert air.get_aircraft(now=NOW + 900) == []
    assert air.get_aircraft_status(now=NOW + 900)["last_success_at"] == iso(NOW)


def test_valid_empty_coverage_is_distinct_from_no_success():
    assert air.get_aircraft_status(now=NOW)["status"] == "unavailable"
    air._publish_snapshot(air.normalize_adsb(adsb(), received=NOW), now=NOW)
    status = air.get_aircraft_status(now=NOW)
    assert status["status"] == "ok" and status["count"] == 0
    assert status["coverage"]["radius_nm"] == 250


def test_opensky_units_and_source_time_match_adsb_contract():
    state = ["abc123", "SYNTH", "Unknown", NOW-5, NOW, 45, 30, 1000, False,
             50, 0, 0, None, 0, "1200", False, 0]
    row = air.normalize_opensky({"time":NOW, "states":[state]}, received=NOW)["states"][0]
    assert row["altitude"] == 0 and row["velocity"] == 50 and row["heading"] == 0
    assert row["observed_at"] == iso(NOW-5)
    with pytest.raises(ValueError):
        air.normalize_opensky({"time":NOW, "states":[["too", "short"]]}, received=NOW)


def test_aircraft_history_deduplicates_source_time_and_bounds_identity_memory(monkeypatch):
    monkeypatch.setattr(air, "MAX_TRACKED_AIRCRAFT", 2)
    snapshot = air.normalize_adsb(adsb(*(aircraft(hex=f"abc00{i}") for i in range(3))), received=NOW)
    air._publish_snapshot(snapshot, now=NOW)
    air._publish_snapshot(snapshot, now=NOW + 10)
    assert len(air._tracks) == 2
    assert all(len(points) == 1 for points in air._tracks.values())
    exported = air.get_aircraft(now=NOW + 10)
    exported[0]["lat"] = -90
    assert air.get_aircraft(now=NOW + 10)[0]["lat"] == 30
    assert air.get_aircraft_track("abc002", now=NOW+1900) == []
    assert not air._tracks


@pytest.mark.asyncio
async def test_aircraft_failure_keeps_success_clock_and_obeys_backoff(monkeypatch):
    monkeypatch.setattr(air.time, "time", lambda: NOW)
    air._publish_snapshot(air.normalize_adsb(adsb(aircraft()), received=NOW), now=NOW-10)
    calls = []
    def responder(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After":"300"}, text="private provider diagnostic")
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
        assert await air._poll_adsb_lol(client) is None
        assert await air._poll_adsb_lol(client) is None
    assert len(calls) == 1
    assert air._cache["last_success"] == NOW-10
    assert air._cache["error"] == "adsb.lol:HTTP_429"


@pytest.mark.asyncio
async def test_anonymous_fallback_budget_does_not_use_obsolete_basic_auth(monkeypatch):
    monkeypatch.setattr(air.time, "time", lambda: NOW)
    calls = []
    def responder(request):
        calls.append(request)
        return httpx.Response(200, json={"time":NOW, "states":[]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
        assert await air._poll_opensky(client, ("legacy-user", "legacy-password")) is not None
        assert await air._poll_opensky(client) is None
    assert len(calls) == 1 and "Authorization" not in calls[0].headers
    assert air._next_attempt["opensky"] == NOW + 900


@pytest.mark.asyncio
async def test_decoded_http_body_is_bounded():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200, content=b"x" * 65))) as client:
        with pytest.raises(ValueError, match="byte limit"):
            await bounded_json(client, "https://fixture.invalid", max_bytes=64)


def test_ais_separates_time_preserves_zero_course_and_corrects_mid():
    sea._consume_message(ais(when=NOW-30), now=NOW)
    vessel = sea.get_vessels(now=NOW+10)[0]
    assert vessel["heading"] == 0 and vessel["heading_basis"] == "course_over_ground"
    assert vessel["age_seconds"] == 40 and vessel["received_age_seconds"] == 10
    assert vessel["flag_code"] == "CN"  # inherited code incorrectly labelled MID413 Iranian
    assert vessel["flag_basis"] == "MMSI_allocation_not_ownership"


@pytest.mark.parametrize("changes", [{"Latitude":91}, {"Longitude":181}, {"Latitude":float("nan")},
    {"Latitude":True}, {"Latitude":0,"Longitude":0}, {"Valid":False}, {"UserID":422123456}])
def test_invalid_ais_never_enters_position_cache(changes):
    with pytest.raises(ValueError):
        sea._consume_message(ais(**changes), now=NOW)
    assert sea.get_vessels(now=NOW) == []


def test_ais_unknown_time_is_not_synthesized_and_static_update_does_not_refresh_position():
    sea._consume_message(ais(when=None), now=NOW)
    initial = sea.get_vessels(now=NOW)[0]
    assert initial["observed_at"] is None and initial["age_seconds"] is None and initial["stale"] is None
    sea._consume_message(ais(kind="ShipStaticData", Type=80), now=NOW+500)
    assert sea.get_vessels(now=NOW+601) == []


def test_ais_out_of_order_or_replayed_position_cannot_refresh_freshness():
    sea._consume_message(ais(), now=NOW)
    sea._consume_message(ais(when=NOW-5, Latitude=31), now=NOW+10)
    sea._consume_message(ais(), now=NOW+20)
    row = sea.get_vessels(now=NOW+21)[0]
    assert row["lat"] == 30 and row["last_seen"] == NOW
    assert sea.get_vessels(now=NOW+601) == []


def test_static_only_ais_memory_has_capacity_and_ttl(monkeypatch):
    monkeypatch.setattr(sea, "MAX_VESSELS", 2)
    for i in range(3):
        sea._consume_message(ais(identity=f"41312345{i}", kind="ShipStaticData", Type=80), now=NOW+i)
    assert len(sea._cache["vessels"]) == 2
    assert sea._cache["evicted_records"] == 1
    assert sea.get_vessels(now=NOW+1900) == []
    assert not sea._cache["vessels"]


def test_ais_frame_limit_and_control_confirmation():
    with pytest.raises(ValueError, match="oversized"):
        sea._consume_message("é" * 40000, now=NOW)
    sea._consume_message(json.dumps({"MessageType":"SubscriptionConfirmation", "Message":{"CompressionEnabled":True}}), now=NOW)
    assert sea.get_maritime_status(now=NOW)["subscription_compression"] is True
    assert sea.get_maritime_status(now=NOW)["status"] == "unavailable"


def test_ais_type_codes_do_not_turn_sailing_into_tugs_or_sar_into_government():
    assert sea._classify_vessel({"mmsi":"413123456", "ship_type":31})[0] == "tug"
    assert sea._classify_vessel({"mmsi":"413123456", "ship_type":36})[0] == "other"
    assert sea._classify_vessel({"mmsi":"413123456", "ship_type":51})[0] == "other"
    assert sea._ship_type_name(36) == "Sailing"


@pytest.mark.asyncio
async def test_tracking_loops_remain_off_without_operator_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "live_ingestion_enabled", False)
    await air.start_opensky_poller()
    await sea.start_maritime_poller()
    assert air.get_aircraft_status(now=NOW)["status"] == "disabled"
    assert sea.get_maritime_status(now=NOW)["status"] == "disabled"
