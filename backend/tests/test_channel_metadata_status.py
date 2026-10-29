from copy import deepcopy

from app.routes import channels
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_channel_list_and_detail_disclose_same_historical_prior_without_mutation(
    monkeypatch,
):
    registry = {
        "MixedCaseHandle": {
            "display_name": "Fixture publisher",
            "reliability": 4,
            "affiliation": "Inherited fixture label",
            "bias_notes": "Inherited fixture note",
            "languages": ["en"],
            "flag": "",
        }
    }
    before = deepcopy(registry)
    monkeypatch.setattr(channels, "get_all_channels", lambda: registry)
    app = FastAPI()
    app.include_router(channels.router)
    with TestClient(app) as client:
        listed = client.get("/channels").json()[0]
        detail = client.get("/channels/mixedcasehandle").json()
        assert detail == listed and detail["handle"] == "MixedCaseHandle"
        assert detail["metadata_status"] == "inherited_unverified"
        assert detail["reliability_basis"] == "uncalibrated_legacy_editorial_prior"
        assert detail["affiliation_status"] == "unverified"
        assert detail["metadata_origin_period"] == "2026-03"
        assert (
            detail["reliability"] == 4
            and detail["affiliation"] == before["MixedCaseHandle"]["affiliation"]
        )
        assert (
            detail["bias_notes"]
            == "Legacy March 2026 unverified note: Inherited fixture note"
        )
        assert client.get("/channels/absent").status_code == 404
    assert registry == before


def test_response_nested_values_do_not_alias_original_registry():
    meta = {"reliability": 3, "bias_notes": "Original", "languages": ["en"]}
    result = channels.public_metadata("Canonical", meta)
    result["languages"].append("fixture")
    assert meta == {"reliability": 3, "bias_notes": "Original", "languages": ["en"]}
