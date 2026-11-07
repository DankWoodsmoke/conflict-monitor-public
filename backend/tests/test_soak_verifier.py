"""A verification tool must not turn unavailable or missing checks green."""
import importlib.util
import copy
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("soak_assessor", Path(__file__).resolve().parents[2] / "tools/summarize_live_soak.py")
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
observer_spec = importlib.util.spec_from_file_location("soak_observer", Path(__file__).resolve().parents[2] / "tools/live_soak.py")
observer = importlib.util.module_from_spec(observer_spec)
observer_spec.loader.exec_module(observer)


def fixture_run(path):
    progress = {"started_at": "2026-10-29T00:00:00+00:00", "ended_at": "2026-10-29T00:01:00+00:00", "elapsed_seconds": 60,
                "requested_seconds": 60, "ws_messages": 0, "ws_payload_errors": 0}
    samples = [{"elapsed_seconds": offset, "at": "fixture", "findings": [], "providers": {},
                "requests": {key: {"status": 200, "ms": 2} for key in subject.EXPECTED_ENDPOINTS},
                "sql_integrity": {"events": 12, **dict.fromkeys(subject.SQL_INTEGRITY_FIELDS, 0)}} for offset in (0, 30)]
    def save():
        (path / "summary.json").write_text(json.dumps(progress), encoding="utf8")
        (path / "samples.jsonl").write_text("\n".join(map(json.dumps, samples)), encoding="utf8")
        (path / "websocket.jsonl").write_text('{"event":"connected","at":"2026-10-29T00:00:00+00:00"}\n', encoding="utf8")
    save()
    return progress, samples, save


def test_quiet_socket_does_not_claim_message_delivery_even_when_soak_checks_qualify(tmp_path):
    fixture_run(tmp_path)
    result = subject.summarize(tmp_path)
    assert result["status"] == "qualified_sample"
    assert result["websocket"]["delivery_observed"] is False


def telegram_page(at, cursor, fence=None, blocked=None, status="ok"):
    return {"elapsed_seconds": at, "providers": {"telegram": {
        "checkpoint_policy": "ordered_provider_page", "selected_channels": ["fixture"],
        "checkpoint_pages": {"fixture": {"status": status, "checkpoint_message_id": cursor,
            "provider_page_last_message_id": fence, "blocked_message_id": blocked}},
    }}}


@pytest.mark.parametrize("seconds,qualified", [(30, True), (600, False)])
def test_ordered_page_wait_is_distinguished_from_a_stalled_cursor(seconds, qualified):
    samples = [telegram_page(0, 73), telegram_page(1, 73, 75, 74, "pending_receipt"),
               telegram_page(10, None, status="failed"), telegram_page(seconds + 1, 75, 75)]
    requirements, details = subject.ordered_telegram_requirements(samples)
    assert requirements["telegram_ordered_pages_observed"] is True
    assert requirements["telegram_no_sustained_checkpoint_stall"] is qualified
    assert details["channels"]["fixture"]["longest_stall"] == seconds


def test_ordered_profile_requires_telemetry_and_keeps_pending_receipt_gate(tmp_path):
    progress, samples, save = fixture_run(tmp_path)
    progress["observer_version"] = 4
    for sample in samples:
        sample["providers"] = telegram_page(sample["elapsed_seconds"], 73)["providers"]
        sample["sql_integrity"]["checkpoint_behind_stored_message"] = 1
    save()
    assert subject.summarize(tmp_path)["status"] == "qualified_sample"
    samples[0]["sql_integrity"]["pending_receipts_over_5m"] = 1
    save()
    assert subject.summarize(tmp_path)["status"] == "incomplete_or_findings"
    samples[0]["sql_integrity"]["pending_receipts_over_5m"] = 0
    samples[1]["providers"] = {}
    save()
    assert subject.summarize(tmp_path)["requirements"]["telegram_ordered_pages_observed"] is False


def test_disabled_telegram_is_explicit_and_checks_for_unexpected_live_events(tmp_path):
    progress, samples, save = fixture_run(tmp_path)
    progress["expect_telegram_disabled"] = True
    for sample in samples:
        sample["providers"] = observer.provider_summary({"telegram": {
            "transport": "disabled", "enabled": False, "status": "disabled", "checkpoint_policy": "none"
        }})
        sample["sql_integrity"].update(latest_telegram_event_id=100, checkpoint_behind_stored_message=1)
    save()
    result = subject.summarize(tmp_path)
    assert result["status"] == "qualified_sample"
    assert result["telegram_live_coverage"] == "disabled"
    samples[1]["providers"]["workers"]["telegram_bot"] = "running"
    samples[1]["sql_integrity"]["latest_telegram_event_id"] = 101
    save()
    result = subject.summarize(tmp_path)
    assert result["status"] == "incomplete_or_findings"
    assert result["requirements"]["explicitly_disabled_telegram_transport"] is False
    assert result["requirements"]["no_new_telegram_event_ids"] is False


@pytest.mark.parametrize("gap", ["short_duration", "still_running", "no_sql", "missing_endpoint", "bad_sql", "late_sample"])
def test_missing_or_failed_qualification_never_succeeds(tmp_path, gap):
    progress, samples, save = fixture_run(tmp_path)
    if gap == "short_duration":
        progress["elapsed_seconds"] = 50
    elif gap == "still_running":
        progress.pop("ended_at")
    elif gap == "no_sql":
        for row in samples:
            row.pop("sql_integrity")
    elif gap == "missing_endpoint":
        samples[0]["requests"].pop("/api/status")
    elif gap == "bad_sql":
        samples[0]["sql_integrity"]["pending_receipts_over_5m"] = 1
    else:
        progress["elapsed_seconds"] = 300
    save()
    assert subject.summarize(tmp_path)["status"] == "incomplete_or_findings"


def test_no_socket_connection_is_incomplete(tmp_path):
    fixture_run(tmp_path)
    (tmp_path / "websocket.jsonl").unlink()
    result = subject.summarize(tmp_path)
    assert result["requirements"]["websocket_connected"] is False
    assert result["status"] == "incomplete_or_findings"


def test_brief_connection_does_not_qualify_a_mostly_disconnected_socket(tmp_path):
    fixture_run(tmp_path)
    with (tmp_path / "websocket.jsonl").open("a", encoding="utf8") as handle:
        handle.write('{"event":"disconnected","at":"2026-10-29T00:00:03+00:00"}\n')
    result = subject.summarize(tmp_path)
    assert result["websocket"]["connected_fraction"] == .05
    assert result["status"] == "incomplete_or_findings"


@pytest.mark.parametrize("raw,expected", [("128MiB / 2GiB", 128), ("1GiB / 16GiB", 1024),
    ("1048576B / 16GiB", 1), ("1GB / 2GB", 953.67431640625), ("unavailable", None)])
def test_resource_units_are_not_silently_confused(raw, expected):
    assert subject.memory_mib(raw) == expected


@pytest.mark.parametrize("position,valid", [({"lat": 0, "lon": 0}, True), ({"lat": None, "lon": None}, True),
    ({"lat": 90, "lon": -180}, True), ({"lat": True, "lon": 2}, False),
    ({"lat": float("nan"), "lon": 2}, False), ({"lat": 0, "lon": None}, False),
    ({"lat": 91, "lon": 2}, False)])
def test_observer_coordinate_check_preserves_nulls_zeroes_and_rejects_boolean_positions(position, valid):
    assert observer.finite_coordinates(position) is valid


@pytest.mark.parametrize("payload", [None, [], {"type": "new_event", "event": []},
    {"type": "new_event", "event": {"id": True, "raw_text": "text"}},
    {"type": "new_event", "event": {"id": 1, "raw_text": None}}])
def test_malformed_websocket_payload_cannot_count_as_valid_delivery(payload):
    assert observer.valid_event_payload(payload) is False


def test_nullable_position_report_is_valid_delivery():
    assert observer.valid_event_payload({"type": "new_event", "event": {"id": 1, "raw_text": "Original"}})


def test_isolated_observer_never_silently_queries_live_database():
    command = observer.database_command("owned-fixture-db-1", "conflict_monitor_test")
    assert command[2] == "owned-fixture-db-1"
    assert command[command.index("-d") + 1] == "conflict_monitor_test"
    assert "conflict_monitor" not in command
    assert "ON_ERROR_STOP=1" in command
    with pytest.raises(ValueError, match="Unknown observation database"):
        observer.database_command("owned-fixture-db-1", "other_database")


@pytest.mark.parametrize("second_image,qualified", [("backendA", True), ("backendB", False)])
def test_final_image_profile_does_not_count_mixed_image_time_as_one_image_soak(tmp_path, second_image, qualified):
    fixture_run(tmp_path)
    segments = [{"at": "fixture", "elapsed_seconds": 0, "identity": "backend|backendA|start1\nfrontend|frontendA|start1"},
                {"at": "fixture", "elapsed_seconds": 30, "identity": f"backend|{second_image}|start2\nfrontend|frontendA|start1"}]
    (tmp_path / "segments.jsonl").write_text("\n".join(map(json.dumps, segments)), encoding="utf8")
    assessment = subject.summarize(tmp_path, require_single_image=True)
    assert assessment["requirements"]["one_backend_and_frontend_image_pair"] is qualified
    assert assessment["status"] == ("qualified_sample" if qualified else "incomplete_or_findings")


def database_fixture():
    containers=[{'name':name,'image':name+'Image','started_at':'start1'} for name in ('backend','frontend','database')]
    containers[-1]['pgdata']=[{'Type':'volume','Name':'restored_volume','Destination':'/var/lib/postgresql/data'}]
    identity={'containers':containers,'identity':'backend|backendImage|start1\nfrontend|frontendImage|start1\ndatabase|databaseImage|start1'}
    progress={'observer_version':3,'expected_containers':dict(zip(('backend','frontend','database'),('backend','frontend','database'))),
        'expected_database':{'postgresql':'17.11','postgis':'3.6.4','data_volume':'restored_volume'}}
    samples=[{'elapsed_seconds':offset} for offset in (0,30,60,90)]
    for index in (0,2):samples[index]['deployment_identity']=copy.deepcopy(identity)
    sql=[{'postgresql_version':'17.11 (Debian fixture)','postgis_version':'3.6.4','collation_version_matches':True} for _ in range(2)]
    return progress,samples,[{'elapsed_seconds':0,**identity}],sql


def test_database_image_volume_and_start_identity_are_required_for_new_profile():
    progress,samples,segments,sql=database_fixture()
    requirements,profile=subject.database_identity_requirements(progress,samples,segments,sql,120)
    assert all(requirements.values())
    assert profile['database_identities']==[{'image':'databaseImage','volume':'restored_volume'}]


@pytest.mark.parametrize('defect', ['wrong_database', 'wrong_role', 'missing_scheduled_sql', 'missing_container_memory'])
def test_isolated_full_soak_requires_actual_database_and_complete_scheduled_observations(defect):
    progress, samples, segments, sql = database_fixture()
    progress['observer_version'] = 6
    progress['expected_database']['name'] = 'conflict_monitor_test'
    for row in sql:
        row.update(database_name='conflict_monitor_test', database_role='monitor')
    for index, row in enumerate(samples):
        if index % 10 == 0:
            row['sql_integrity'] = {**sql[0], **dict.fromkeys(subject.SQL_INTEGRITY_FIELDS, 0)}
        if index % 2 == 0:
            row['container_resources'] = [{'Name': name, 'MemUsage': '128MiB / 2GiB'} for name in progress['expected_containers'].values()]
    good, _ = subject.database_identity_requirements(progress, samples, segments, sql, 120)
    assert all(good.values())
    if defect == 'wrong_database':
        sql[0]['database_name'] = 'conflict_monitor'
    elif defect == 'wrong_role':
        sql[0]['database_role'] = 'monitor_admin'
    elif defect == 'missing_scheduled_sql':
        samples[0].pop('sql_integrity')
    else:
        samples[2]['container_resources'][0]['MemUsage'] = 'unavailable'
    requirements, _ = subject.database_identity_requirements(progress, samples, segments, sql, 120)
    assert not all(requirements.values())


@pytest.mark.parametrize('defect',['different_volume','different_database_image','database_restart','missing_mount',
    'bind_mount','identity_unavailable','wrong_expected_volume','changed_sql_version','old_collation','missing_sql_versions'])
def test_new_soak_database_gate_rejects_material_profile_changes_and_missing_evidence(defect):
    progress,samples,segments,sql=database_fixture()
    database=samples[2]['deployment_identity']['containers'][-1]
    if defect=='different_volume':database['pgdata'][0]['Name']='other_volume'
    elif defect=='different_database_image':database['image']='other_database_image'
    elif defect=='database_restart':database['started_at']='start2'
    elif defect=='missing_mount':database['pgdata']=[]
    elif defect=='bind_mount':database['pgdata'][0]['Type']='bind'
    elif defect=='identity_unavailable':samples[2]['deployment_identity']={'status':'unavailable'}
    elif defect=='wrong_expected_volume':progress['expected_database']['data_volume']='wrong_volume'
    elif defect=='changed_sql_version':sql[1]['postgresql_version']='17.5'
    elif defect=='old_collation':sql[1]['collation_version_matches']=False
    else:sql[1].pop('postgis_version')
    requirements,_=subject.database_identity_requirements(progress,samples,segments,sql,120)
    assert not all(requirements.values())


def test_earlier_observer_profile_cannot_be_promoted_to_database_bound_qualification(tmp_path):
    fixture_run(tmp_path)
    result=subject.summarize(tmp_path,require_database_identity=True)
    assert result['status']=='incomplete_or_findings'
    assert result['requirements']['database_identity_observed_throughout'] is False


def test_observer_persists_reviewed_identity_only_and_never_environment_or_host_bind_sources():
    rows=[{'name':'/'+name,'image':name+'Image','started_at':'start1','environment':['PRIVATE_SECRET=do-not-record'],
        'mounts':[{'Type':'bind','Source':'C:/private/voice','Destination':'/opt/voices'}]} for name in ('backend','frontend','database')]
    rows[-1]['mounts'].append({'Type':'volume','Name':'restored_volume','Source':'/private/engine/path','Destination':'/var/lib/postgresql/data'})
    result=observer.deployment_identity('\n'.join(map(json.dumps,rows)),['backend','frontend','database'],'database')
    rendered=json.dumps(result)
    assert 'PRIVATE_SECRET' not in rendered and '/private/' not in rendered and '/opt/voices' not in rendered
    assert result['containers'][1]['pgdata']==[{'Type':'volume','Name':'restored_volume','Destination':'/var/lib/postgresql/data'}]


def test_incomplete_or_duplicate_container_inventory_is_not_identity_evidence():
    row={'name':'/backend','image':'image','started_at':'start1'}
    with pytest.raises(ValueError):
        observer.deployment_identity('\n'.join(map(json.dumps,[row,row,row])),['backend','frontend','database'],'database')


@pytest.mark.parametrize('usage',[None,False,1,0])
def test_free_profile_needs_actual_zero_paid_usage_counts_not_missing_or_boolean_values(tmp_path,usage):
    _,samples,save=fixture_run(tmp_path)
    for row in samples:row['sql_integrity']['usage_calls']=usage
    save()
    result=subject.summarize(tmp_path,require_no_paid_usage=True)
    assert result['requirements']['no_recorded_paid_usage'] is (type(usage) is int and usage==0)
