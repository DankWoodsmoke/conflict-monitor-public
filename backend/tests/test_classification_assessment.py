"""Offline source fidelity, impact provenance and permission boundaries."""
import copy
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.models import Event
from app.schemas import EventCreate, EventRead, EventWS
from app.services import classifier as c, telegram as tg, news_feeds as rss
from app.services.assessment import event_assessment, valid_extraction, valid_classification
from app.services.evidence import make_report
from app.services.local_briefing import ensure_artifact_source_permission, SourcePermissionRequired
from test_ingestion_integration import pipeline, ingest, RAW

STAMP=datetime(2026,10,30,tzinfo=timezone.utc)
TEXT="Officials reported sustained disruption across the city after the strike."

def model(raw=TEXT,**changes):
    fields=dict(event_type="military",severity=7,location_name="Unknown",summary=raw,
                evidence_quote=raw,stance="reported",military_subtype="airstrike")
    fields.update(changes)
    return c._post_process(c.ClassifierResult(**fields),raw)

def record(raw=TEXT,**changes):
    result=model(raw)
    value=dict(id=1,source="rss_fixture",channel_name="fixture",raw_text=raw,summary=result["summary"],
        event_type="military",severity=7,classification_status="extracted",lat=None,lon=None,
        timestamp=STAMP,created_at=STAMP,source_url="https://example.org/source",reports=[])
    value["reports"]=[make_report({**value,"extraction":result["extraction"]})]
    value.update(changes)
    return value


@pytest.mark.parametrize("change",[{"severity":True},{"severity":"9"},{"severity":11},
    {"military_subtype":"nuclear_verified"},{"event_type":"diplomatic"},
    {"is_noise":"false"},{"stance":"verified"},{"confidence":1}])
def test_malformed_model_fields_do_not_become_scores(change):
    with pytest.raises(ValidationError):model(**change)


def test_noise_is_explicit_and_never_recast_as_military_impact():
    raw="Subscribe to receive new cooking recipes each week."
    result=model(raw,event_type="unclassified",severity=0,stance="unknown",military_subtype="",is_noise=True)
    assert result["classification_status"]=="filtered" and result["is_noise"] is True
    assert result["severity"]==0 and "extraction" not in result


@pytest.mark.parametrize("raw",[
    "Officials denied that a missile struck the hospital.",
    "The airport might be targeted next week, according to a columnist.",
    'The official said "the hospital was hit" but provided no evidence.',
    "Correction: the report about a destroyed hospital was withdrawn."])
def test_denial_quote_ambiguity_and_correction_cannot_carry_unreviewed_critical_score(raw):
    result=model(raw,severity=10)
    assert result["classification_status"]=="invalid" and result["severity"]==0


def test_denied_report_is_preserved_unscored_with_literal_qualifiers():
    raw="Officials denied that a missile struck the hospital."
    result=model(raw,severity=0,stance="denied")
    assert result["classification_status"]=="extracted" and result["summary"]==raw
    assert result["extraction"]["stance"]=="denied"


@pytest.mark.parametrize("replacement",[
    "Three people were killed in a strike yesterday.",
    "The missile travelled 3 miles yesterday.",
    "The missile travelled 3 km today."])
def test_numbers_units_and_time_cannot_be_rewritten_in_published_excerpt(replacement):
    raw="The missile travelled 3 km yesterday."
    result=model(raw,summary=replacement,evidence_quote=replacement)
    assert result["classification_status"]=="invalid" and result["severity"]==0


def test_omitting_denial_from_otherwise_literal_excerpt_is_rejected():
    raw="The hospital was hit. Officials denied the initial report."
    result=model(raw,summary="The hospital was hit.",evidence_quote="The hospital was hit.",severity=0,stance="denied")
    assert result["classification_error"]=="source_qualifier_omitted"


def test_invented_actor_and_quantity_fail_closed():
    assert model(actor="Invented Forces")["classification_status"]=="invalid"
    assert model(casualties="50 killed")["classification_status"]=="invalid"


def test_month_date_is_not_a_modal_may_guard():
    raw="On May 4, officials reported a temporary road closure."
    assert model(raw,severity=3)["classification_status"]=="extracted"


@pytest.mark.parametrize("mutation",["omit_denial","actor","casualties","unknown_field","wrong_type"])
def test_hand_built_snapshot_cannot_bypass_authoritative_fidelity_validation(mutation):
    raw="The ministry denied a strike in Tehran."
    value=model(raw,severity=0,stance="denied")
    snapshot=copy.deepcopy(value["extraction"])
    if mutation=="omit_denial":
        quote="a strike in Tehran."
        snapshot.update(evidence_quote=quote,start=raw.index(quote),end=len(raw),stance="reported",severity=9)
        value.update(summary=quote,severity=9)
    elif mutation=="actor":snapshot["actor"]="invented actor"
    elif mutation=="casualties":snapshot["casualties"]="999 killed"
    elif mutation=="unknown_field":snapshot["verified"]=True
    else:snapshot["actor"]=["The ministry"]
    value["extraction"]=snapshot
    assert not valid_extraction(snapshot,raw)
    assert not valid_classification(value,raw)
    assert "extraction" not in make_report(raw_text=raw,extraction=snapshot)


@pytest.mark.asyncio
async def test_model_place_does_not_authorize_geocoding_or_an_incident_position(pipeline):
    pipeline.extracted["location_name"]="Tehran"
    await ingest("rss")
    assert len(pipeline.store.events)==1
    row=pipeline.store.events[0]
    assert row.location_name=="Unknown" and row.lat is row.lon is row.geometry is None
    pipeline.geocode.assert_not_awaited()


def test_duplicate_model_json_keys_are_not_silently_collapsed():
    import json
    with pytest.raises(ValueError):
        json.loads('{"severity":0,"severity":10}',object_pairs_hook=c._strict_json_object)


@pytest.mark.asyncio
async def test_raw_impact_is_not_an_independent_anomaly_baseline():
    from app.services.anomaly import analyze_anomaly
    result=await analyze_anomaly(TEXT,"military",10,"Unknown",TEXT)
    assert not result["is_anomaly"] and result["anomaly_score"]==0
    assert result["assessment_status"]=="unassessed"


@pytest.mark.asyncio
@pytest.mark.parametrize("url",["", "https://t.me/fixture/1"])
async def test_rss_parent_cannot_launder_telegram_child_into_sitrep(url):
    from app.services import sitrep_generator as generator
    row=record()
    row["reports"].append({"source":"telegram","channel_name":"fixture", "source_url":url,
                           "raw_text":"Restricted synthetic source text."})
    event=SimpleNamespace(**row)
    session=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda:SimpleNamespace(all=lambda:[event]))))
    assert not generator._source_permission(event)
    assert await generator._build_event_payload(session)==[]
    with pytest.raises(SourcePermissionRequired):generator._event_snapshot(event)


def test_restricted_middle_child_blocks_entire_sitrep_event_before_excerpt_sampling():
    from app.services import sitrep_generator as generator
    row=record();rss_report=copy.deepcopy(row["reports"][0])
    row["reports"]=[rss_report,{"source":"telegram","source_url":"","raw_text":"Synthetic middle source"},
                    copy.deepcopy(rss_report),copy.deepcopy(rss_report)]
    with pytest.raises(SourcePermissionRequired):generator._event_snapshot(SimpleNamespace(**row))


def test_new_defaults_do_not_invent_military_severity_or_touch_existing_rows():
    value=EventCreate()
    assert value.event_type=="unclassified" and value.severity==0
    assert Event.__table__.c.event_type.default.arg=="unclassified"
    assert Event.__table__.c.severity.default.arg==0
    old=record(classification_status="legacy_unknown",severity=9,reports=[])
    before=copy.deepcopy(old)
    projection=event_assessment(old)
    assert old==before and projection["status"]=="legacy_unreviewed" and projection["severity"] is None


def test_model_estimate_is_source_bound_unreviewed_and_identical_in_api_and_websocket():
    value=record();api=EventRead.model_validate(value).model_dump()
    ws=EventWS(event=EventRead.model_validate(value)).model_dump()
    assessment=api["evidence"]["assessment"]
    assert assessment==ws["event"]["evidence"]["assessment"]
    assert assessment["status"]=="model_estimate" and assessment["severity"]==7
    assert assessment["model"]==c.settings.classification_model
    assert assessment["source_sha256"]==hashlib.sha256(TEXT.encode()).hexdigest()
    assert assessment["confirmed"] is assessment["critical_alert_eligible"] is False
    assert assessment["review_status"]=="unreviewed"
    assert value["reports"][0]["extraction"]["military_subtype"]=="airstrike"


@pytest.mark.parametrize("field,value",[("model",""),("source_sha256","f"*64),
    ("rubric_version","other-rubric"),("prompt_sha256","broken"),("severity",10),
    ("event_type","economic"),("evidence_quote","Fabricated quote"),("start",True)])
def test_forged_or_mismatched_provenance_never_qualifies_numeric_severity(field,value):
    row=record();row["reports"][0]["extraction"][field]=value
    assessment=event_assessment(row)
    assert assessment["status"]=="legacy_unreviewed" and assessment["severity"] is None


def test_extracted_status_alone_does_not_prove_a_model_or_rubric():
    assessment=event_assessment(record(reports=[],severity=10))
    assert assessment["status"]=="legacy_unreviewed" and assessment["severity"] is None


@pytest.mark.parametrize("changes,status",[
    ({"event_type":"unclassified","severity":0,"classification_status":"not_requested"},"unscored"),
    ({"event_type":"thermal_anomaly","source":"satellite_firms","severity":0},"sensor_not_applicable"),
    ({"severity":True},"invalid"),({"severity":-1},"invalid")])
def test_unscored_sensor_and_invalid_are_distinct(changes,status):
    assessment=event_assessment(record(**changes))
    assert assessment["status"]==status and assessment["severity"] is None


def test_cache_binds_model_prompt_and_copies_nested_provenance(monkeypatch):
    c._CONTENT_SEEN.clear();c._cache_result(TEXT,model())
    result=c._cached_result(TEXT);result["extraction"]["severity"]=10
    assert c._cached_result(TEXT)["extraction"]["severity"]==7
    monkeypatch.setattr(c.settings,"classification_model","another-model")
    assert c._cached_result(TEXT) is None


@pytest.mark.asyncio
async def test_actual_telegram_permission_gate_preserves_receipt_before_any_classifier(pipeline,monkeypatch):
    monkeypatch.setattr(tg,"ensure_artifact_source_permission",ensure_artifact_source_permission)
    await ingest("telegram")
    receipt=next(iter(pipeline.ledger.records.values()))
    assert receipt["report"]["raw_text"]==RAW and receipt["status"]=="source_permission_required"
    assert not pipeline.store.events
    pipeline.model.assert_not_awaited();pipeline.geocode.assert_not_awaited();pipeline.broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_permission_gate_blocks_legacy_unbounded_history_before_provider(pipeline,monkeypatch):
    monkeypatch.setattr(tg,"ensure_artifact_source_permission",ensure_artifact_source_permission)
    client=SimpleNamespace(iter_messages=AsyncMock())
    with pytest.raises(SourcePermissionRequired):await tg._backfill_entity(client,SimpleNamespace(),STAMP)
    client.iter_messages.assert_not_called();pipeline.model.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_telegram_citation_in_rss_cannot_bypass_ai_permission(pipeline):
    await ingest("rss",url="https://t.me/fixture/1")
    assert next(iter(pipeline.ledger.records.values()))["status"]=="source_permission_required"
    pipeline.model.assert_not_awaited()


def test_collector_status_explains_report_mode_without_exposing_keys(monkeypatch):
    monkeypatch.setattr(c.settings,"rss_processing_mode","reports")
    monkeypatch.setattr(c.settings,"telegram_processing_mode","model")
    monkeypatch.setattr(c.settings,"anthropic_api_key","secret-fixture-key")
    value=c.get_classification_status()
    assert value["rss_classification"]=="not_requested" and value["telegram_classification"]=="source_permission_blocked"
    assert value["semantic_quality"]=="unqualified" and not value["verified_critical_alerts_enabled"]
    assert "secret-fixture-key" not in str(value)
