from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routes import events as subject


def session(event):
    return SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: event)))


@pytest.mark.asyncio
@pytest.mark.parametrize("lat,lon", [(0, 0), (31.5, 34.5), (-12.25, -77.125)])
async def test_basemap_reference_keeps_coordinate_order_zeroes_and_unknown_acquisition_date(monkeypatch, lat, lon):
    monkeypatch.setattr(subject.settings, "sentinel_hub_instance_id", "fixture-unused-instance")
    event = SimpleNamespace(lat=lat, lon=lon, timestamp=datetime(2026, 10, 28, tzinfo=timezone.utc),
                            location_name="مكان & quoted / location")
    result = await subject.get_event_imagery(1, session(event))
    query = parse_qs(urlsplit(result["arcgis_url"]).query)
    assert list(map(float, query["bbox"][0].split(","))) == pytest.approx([lon-.04, lat-.04, lon+.04, lat+.04])
    assert query["bboxSR"] == ["4326"] and query["imageSR"] == ["4326"]
    assert parse_qs(urlsplit(result["unosat_url"]).query)["q"] == [event.location_name]
    assert result["capture_date"] is None and result["incident_evidence"] is False
    assert result["imagery_kind"] == "basemap_reference"
    assert any("unknown" in note and "reported event" in note for note in result["limitations"])
    assert "fixture-unused-instance" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [None, SimpleNamespace(lat=None, lon=None), SimpleNamespace(lat=0, lon=None)])
async def test_missing_source_or_coordinates_never_create_a_default_reference_location(event):
    with pytest.raises(HTTPException) as failure:
        await subject.get_event_imagery(1, session(event))
    assert failure.value.status_code == 404
