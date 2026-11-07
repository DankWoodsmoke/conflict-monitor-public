"""DRAFT: read-token-only packaging gate; never publishes or invokes a network."""
from argparse import ArgumentParser
from hashlib import sha256,sha1
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess

REPOSITORY='DankWoodsmoke/conflict-monitor-public'
BRANCH='refs/heads/codex/public-release'
VERSION='0.2.0-rc.5'
READY='docs/qualification/RELEASE_READY.json'
MANIFEST='docs/qualification/RELEASE_SOURCE_MANIFEST.json'
ROLES={'backend','database','operator','public','tunnel'}
GATES={'security','full_pipeline_soak','google_operator','google_public','media_replay','backup_restore'}
RUNTIME_PREFIXES=('backend/','frontend/','tools/postgis/','tools/hosting/')
RUNTIME_FILES={'docker-compose.yml','compose.public.yml','compose.publisher.yml','compose.tunnel.yml'}


def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
def checksum(value):return sha256(value).hexdigest()
def valid_sha(value):return isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value) is not None
def strict_json(data):
    def constant(_):raise ValueError('Non-finite JSON number refused')
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('Duplicate JSON field refused')
            value[key]=item
        return value
    return json.loads(data,parse_constant=constant,object_pairs_hook=pairs)
def finite_number(value,minimum):return type(value) in {int,float} and math.isfinite(value) and value>=minimum
def exact_int(value,minimum=0):return type(value) is int and value>=minimum


def identity(event,ref,repository,commit,actor):
    if event!='push' or ref!=BRANCH or repository!=REPOSITORY or actor!='DankWoodsmoke':raise ValueError('Untrusted release trigger')
    if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('Exact commit required')


def file_rows(snapshots):
    rows=[]
    for name,data in sorted(snapshots.items()):
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or str(path)!=name:raise ValueError('Unsafe archive path')
        if name not in {READY,MANIFEST}:rows.append({'path':name,'bytes':len(data),'sha256':checksum(data)})
    return rows


# BEGIN REVIEWED ADMISSION POLICY
"""Private draft, stdlib-only release admission policy. No I/O or publication.

Hashes bind retained evidence; they do not independently prove a human review.
The private projector checks those bytes before creating the sanitized record.
"""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re

ap_IMAGE_ROLES = {'backend', 'database', 'operator', 'public', 'tunnel'}
ap_SERVICES = {'writer': 'backend', 'reader': 'backend', 'operator': 'operator', 'public': 'public', 'database': 'database'}
ap_OBSERVERS = {'server', 'publication', 'delivery', 'operator-google', 'public-google'}
ap_SCANS = {**{'image-' + r: r for r in ap_IMAGE_ROLES}, 'native-ffmpeg': 'backend', 'native-curl': 'backend', 'native-database': 'database'}
ap_SEVERITIES = {'Critical': 4, 'High': 3, 'Medium': 2, 'Low': 1, 'Negligible': 0, 'Unknown': 5}


def ap_require(condition, message):
    if not condition:
        raise ValueError(message)


def ap_strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            ap_require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def ap_canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()


def ap_digest(value):
    return sha256(value).hexdigest()


def ap_keys(value, expected, name):
    ap_require(type(value) is dict and set(value) == set(expected.split()), name + ' fields differ')


def ap_number(value, minimum=0, maximum=1e12):
    ap_require(type(value) in {int, float} and math.isfinite(value) and minimum <= value <= maximum, 'Finite bounded number required')


def ap_integer(value, minimum=0, maximum=1_000_000):
    ap_require(type(value) is int and minimum <= value <= maximum, 'Bounded integer required')


def ap_hash_value(value):
    ap_require(type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None, 'SHA256 required')


def ap_hashes(value, minimum=1):
    ap_require(type(value) is list and minimum <= len(value) <= 2000 and len(set(value)) == len(value), 'Unique bounded evidence hashes required')
    for item in value:
        ap_hash_value(item)


def ap_clock(value):
    ap_require(type(value) is str and len(value) <= 40, 'UTC clock required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Invalid clock') from error
    ap_require(result.tzinfo is not None and result.utcoffset().total_seconds() == 0, 'UTC clock required')
    return result


def ap_images(value):
    ap_require(type(value) is dict and set(value) == ap_IMAGE_ROLES, 'Five candidate artifact roles required')
    ap_require(all(type(v) is str and re.fullmatch('sha256:[a-f0-9]{64}', v) for v in value.values()), 'Immutable image IDs required')


def ap_common(proof):
    ap_require(type(proof) is dict and proof.get('status') == 'PASS', 'Final proof is not admitted')
    ap_images(proof.get('qualified_images'))
    ap_hash_value(proof.get('runtime_source_sha256'))
    ap_hash_value(proof.get('source_receipt_sha256'))
    ap_require(proof.get('execution') in {'fresh', 'rebound'}, 'Execution provenance required')
    if proof['execution'] == 'rebound':
        ap_hash_value(proof.get('equivalence_sha256'))


def ap_validate_security(proof):
    ap_common(proof)
    ap_keys(proof, 'status execution source_receipt_sha256 runtime_source_sha256 qualified_images security' + (' equivalence_sha256' if proof['execution'] == 'rebound' else ''), 'security proof')
    ap_require('raw_high_critical_gate' not in proof, 'Raw findings must not be relabeled PASS')
    s = proof.get('security')
    ap_keys(s, 'schema admission reviewed_at candidate_receipt_sha256 matrix_sha256 validation_sha256 independent_review_sha256 verified_evidence_sha256s reference_verification scans dispositions residuals non_cve_issues final_refresh', 'security')
    ap_require(s['schema'] == 1 and type(s['schema']) is int, 'Security schema mismatch')
    ap_require(s['admission'] == 'SCOPED_COMPONENT_REVIEW_WITH_RESIDUALS', 'Explicit scoped admission required')
    reviewed_at = ap_clock(s['reviewed_at'])
    for key in ('candidate_receipt_sha256', 'matrix_sha256', 'validation_sha256', 'independent_review_sha256'):
        ap_hash_value(s[key])
    ap_require(s['independent_review_sha256'] == proof['source_receipt_sha256'], 'Independent review binding differs')
    ap_hashes(s['verified_evidence_sha256s'])
    evidence = set(s['verified_evidence_sha256s'])
    references = s['reference_verification']
    ap_keys(references, 'status receipt_sha256 verified_sha256s', 'independent reference verification')
    ap_require(references['status'] == 'INDEPENDENT_REFERENCE_BYTES_VERIFIED', 'Reference bytes lack independent review')
    ap_hash_value(references['receipt_sha256'])
    ap_hashes(references['verified_sha256s'])
    checked_references = set(references['verified_sha256s'])
    ap_require(evidence <= checked_references, 'Original reviewed evidence omitted from reference verification')
    ap_require({s[k] for k in ('candidate_receipt_sha256', 'matrix_sha256', 'validation_sha256', 'independent_review_sha256')} <= checked_references, 'Unverified candidate/matrix/validation/review reference')
    ap_require(type(s['scans']) is dict and set(s['scans']) == set(ap_SCANS), 'Complete image and native scan inventory required')
    records = {}
    for scan_id, scan in s['scans'].items():
        ap_keys(scan, 'role image raw_sha256 receipt_sha256 execution equivalence_sha256 inventory_sha256 exit_code database_sha256 database_built record_count severity_counts records', 'scan')
        ap_require(scan['role'] == ap_SCANS[scan_id] and scan['image'] == proof['qualified_images'][scan['role']], 'Scan image binding differs')
        for key in ('raw_sha256', 'receipt_sha256', 'database_sha256'):
            ap_hash_value(scan[key])
        ap_require({scan['raw_sha256'], scan['receipt_sha256']} <= checked_references, 'Unverified raw scan or receipt reference')
        ap_clock(scan['database_built'])
        ap_require(scan['execution'] in {'fresh', 'rebound'}, 'Scan execution provenance required')
        if scan['execution'] == 'rebound':
            ap_hash_value(scan['equivalence_sha256'])
            ap_require(scan['equivalence_sha256'] in checked_references, 'Unverified scan equivalence reference')
        else:
            ap_require(scan['equivalence_sha256'] is None, 'Fresh scan must not claim a rebind')
        if scan_id.startswith('native-'):
            ap_hash_value(scan['inventory_sha256'])
            ap_require(scan['inventory_sha256'] in checked_references, 'Unverified native inventory reference')
        else:
            ap_require(scan['inventory_sha256'] is None, 'Image scan inventory is its exact image')
        ap_integer(scan['record_count'])
        ap_require(type(scan['records']) is list and len(scan['records']) == scan['record_count'], 'Scan record count differs')
        counts = Counter()
        for row in scan['records']:
            ap_keys(row, 'key vulnerability severity package version namespace match_sha256', 'raw match')
            for field in ('vulnerability', 'package', 'version', 'namespace'):
                ap_require(type(row[field]) is str and 0 < len(row[field]) <= 300, 'Bounded match identity required')
            ap_require(row['severity'] in ap_SEVERITIES, 'Unknown severity label')
            ap_hash_value(row['match_sha256'])
            identity = {k: v for k, v in row.items() if k != 'key'}
            ap_require(row['key'] == ap_digest(ap_canonical(identity)), 'Normalized record digest differs')
            key = scan_id + ':' + row['key']
            ap_require(key not in records, 'Duplicate raw match')
            records[key] = (scan['role'], row)
            counts[row['severity']] += 1
        ap_require(type(scan['severity_counts']) is dict, 'Severity counts must be an object')
        for value in scan['severity_counts'].values():
            ap_integer(value, 1)
        ap_require(scan['severity_counts'] == dict(counts), 'Raw severity counts changed')
        ap_integer(scan['exit_code'], 0, 2)
        expected_exit = 2 if counts['High'] or counts['Critical'] else 0
        ap_require(scan['exit_code'] == expected_exit, 'Recorded fail-on-high scanner exit inconsistent')
    ap_require(type(s['dispositions']) is list and 1 <= len(s['dispositions']) <= 1000, 'Reviewed dispositions required')
    covered, pairs, residuals = set(), set(), []
    for row in s['dispositions']:
        ap_keys(row, 'role vulnerability severity disposition reason limits image evidence_sha256s image_binding_sha256s record_keys source_row_sha256 review_row_sha256', 'disposition')
        pair = (row['role'], row['vulnerability'])
        ap_require(row['role'] in ap_IMAGE_ROLES and pair not in pairs, 'Duplicate/invalid disposition role')
        pairs.add(pair)
        ap_require(row['image'] == proof['qualified_images'][row['role']], 'Disposition image differs')
        ap_require(row['severity'] in ap_SEVERITIES, 'Disposition severity invalid')
        ap_require(row['disposition'] in {'fixed', 'vulnerable_code_absent', 'affected_unresolved'}, 'Unreviewed status cannot admit')
        for field in ('reason', 'limits'):
            ap_require(type(row[field]) is str and 1 <= len(row[field]) <= 5000, 'Review rationale and scope required')
        for field in ('evidence_sha256s', 'image_binding_sha256s'):
            ap_hashes(row[field])
            ap_require(set(row[field]) <= evidence, 'Evidence hash was not independently checked')
        ap_hash_value(row['source_row_sha256']); ap_hash_value(row['review_row_sha256'])
        ap_require(type(row['record_keys']) is list and len(row['record_keys']) == len(set(row['record_keys'])), 'Duplicate row mapping')
        for key in row['record_keys']:
            ap_require(key in records and key not in covered, 'Missing/duplicate raw disposition')
            role, match = records[key]
            ap_require((role, match['vulnerability']) == pair, 'Wrong finding assigned to disposition')
            ap_require(ap_SEVERITIES[row['severity']] >= ap_SEVERITIES[match['severity']], 'Severity was lowered')
            covered.add(key)
        if row['disposition'] == 'affected_unresolved':
            ap_require(row['severity'] in {'Medium', 'Low', 'Negligible'}, 'Unresolved High/Critical/Unknown blocks release')
            residuals.append({'role': row['role'], 'vulnerability': row['vulnerability'], 'severity': row['severity']})
    ap_require(covered == set(records), 'Raw or supplemental finding omitted')
    ap_require(s['residuals'] == sorted(residuals, key=lambda x: (x['role'], x['vulnerability'])), 'Residual findings omitted or altered')
    ap_require(type(s['non_cve_issues']) is list and len(s['non_cve_issues']) <= 100, 'Non-CVE scope inventory required')
    for row in s['non_cve_issues']:
        ap_keys(row, 'role issue disposition source_disposition limits evidence_sha256s', 'non-CVE issue')
        ap_require(row['role'] in ap_IMAGE_ROLES, 'Invalid non-CVE role')
        ap_require(row['disposition'] in {'fixed', 'reviewed_scope_limit'}, 'Pending non-CVE review blocks admission')
        for field in ('issue', 'source_disposition', 'limits'):
            ap_require(type(row[field]) is str and 1 <= len(row[field]) <= 3000, 'Non-CVE scope missing')
        ap_hashes(row['evidence_sha256s'])
        ap_require(set(row['evidence_sha256s']) <= evidence, 'Non-CVE evidence is unbound')
    refresh = s['final_refresh']
    ap_keys(refresh, 'status started_at completed_at official_database_sha256 upstream_review_sha256 receipt_sha256', 'final refresh')
    ap_require(refresh['status'] == 'COMPLETE_NO_UNRESOLVED_HIGH_CRITICAL', 'Final advisory review incomplete')
    completed = ap_clock(refresh['completed_at'])
    ap_require(ap_clock(refresh['started_at'])<=completed, 'Final refresh starts after completion')
    ap_require(completed >= reviewed_at, 'Final refresh predates component review')
    for field in ('official_database_sha256', 'upstream_review_sha256', 'receipt_sha256'):
        ap_hash_value(refresh[field])
    ap_require({refresh['upstream_review_sha256'], refresh['receipt_sha256']} <= checked_references, 'Final refresh/upstream review bytes are unverified')
    ap_require(all(scan['database_sha256'] == refresh['official_database_sha256'] for scan in s['scans'].values()), 'Scans do not use the final official advisory database')
    return s


def ap_cadence(elapsed, clocks):
    ap_number(elapsed, 0, 15000)
    ap_require(type(clocks) is list and len(clocks) >= 2, 'Sample clocks missing')
    for item in clocks:
        ap_number(item, 0, elapsed)
    ap_require(all(b > a for a, b in zip(clocks, clocks[1:])), 'Sample clocks not strictly increasing')
    result = {'first_seconds': clocks[0], 'maximum_gap_seconds': max(b-a for a, b in zip(clocks, clocks[1:])), 'final_gap_seconds': elapsed-clocks[-1]}
    ap_require(all(0 <= x <= 90 for x in result.values()), 'Initial, interior or final sample gap exceeds90s')
    return result


ap_SERVER_CHECKS = {'observer_finished', 'requested_duration_observed', 'sample_cadence_bounded', 'rest_requests_successful', 'sampled_integrity_preserved', 'sql_checks_available', 'sql_integrity_preserved', 'websocket_connected', 'websocket_available_over_95_percent', 'websocket_payloads_valid', 'one_backend_and_frontend_image_pair', 'no_recorded_paid_usage', 'explicitly_disabled_telegram_transport', 'no_new_telegram_event_ids'}
ap_SERVER_CHECKS |= {'database_identity_observed_throughout', 'one_three_container_start_and_database_volume_identity', 'database_versions_and_collation_observed', 'expected_postgresql_version', 'expected_postgis_version', 'expected_database_volume', 'expected_database_name_and_role'}
ap_BROWSER_CHECKS = {'all_tabs_seen', 'one_persistent_canvas', 'google_ready_all_samples', 'identities_stable', 'source_hashes_match', 'no_page_errors', 'no_generation_requests'}


def ap_validate_soak(proof):
    ap_common(proof)
    ap_keys(proof, 'status execution source_receipt_sha256 runtime_source_sha256 qualified_images soak', 'soak proof')
    ap_require(proof['execution'] == 'fresh', 'Full soak must be a fresh exact-profile execution')
    s = proof.get('soak')
    ap_keys(s, 'schema launch_sha256 candidate_receipt_sha256 started_at ended_at rehearsal_only observer_sources_unchanged private_runners_unchanged observer_source_hashes private_runner_hashes observed_services unobserved_image_roles observers', 'soak')
    ap_require(type(s['schema']) is int and s['schema'] == 1, 'Soak schema mismatch')
    ap_hash_value(s['launch_sha256']); ap_hash_value(s['candidate_receipt_sha256'])
    ap_require(s['launch_sha256'] == proof['source_receipt_sha256'], 'Launch binding differs')
    start, end = ap_clock(s['started_at']), ap_clock(s['ended_at'])
    ap_number((end-start).total_seconds(), 14400, 14760)
    ap_require(s['rehearsal_only'] is False and s['observer_sources_unchanged'] is True and s['private_runners_unchanged'] is True, 'Rehearsal or changed observer source cannot qualify')
    ap_hashes(s['observer_source_hashes']); ap_hashes(s['private_runner_hashes'])
    ap_require(type(s['observed_services']) is dict and set(s['observed_services']) == set(ap_SERVICES), 'Five observed service roles required')
    for service, binding in s['observed_services'].items():
        ap_keys(binding, 'image started_at identity_sha256', 'service')
        ap_require(binding['image'] == proof['qualified_images'][ap_SERVICES[service]], 'Observed service uses wrong candidate image')
        ap_require(ap_clock(binding['started_at']) <= start, 'Service started during observation')
        ap_hash_value(binding['identity_sha256'])
    ap_require(len({row['identity_sha256'] for row in s['observed_services'].values()}) == 5, 'Five distinct service identities required')
    ap_require(s['unobserved_image_roles'] == ['tunnel'], 'Offline connector must not be represented as observed')
    ap_require(type(s['observers']) is dict and set(s['observers']) == ap_OBSERVERS, 'All five observers required')
    for name, row in s['observers'].items():
        ap_keys(row, 'status exit_code summary_sha256 samples_sha256 requested_seconds elapsed_seconds samples cadence checks metrics', 'observer')
        ap_require(row['status'] == ('completed_sample' if name.endswith('-google') else 'qualified_sample'), 'Observer did not qualify')
        ap_require(type(row['exit_code']) is int and row['exit_code'] == 0, 'Observer exit failed')
        ap_hash_value(row['summary_sha256']); ap_hash_value(row['samples_sha256'])
        ap_integer(row['requested_seconds'], 14400, 14400)
        ap_number(row['elapsed_seconds'], 14400, 14600)
        ap_integer(row['samples'], 479, 600)
        ap_keys(row['cadence'], 'first_seconds maximum_gap_seconds final_gap_seconds', 'cadence')
        for value in row['cadence'].values():
            ap_number(value, 0, 90)
        checks, metrics = row['checks'], row['metrics']
        ap_require(type(checks) is dict and checks and all(v is True for v in checks.values()), 'Observer assertion failed or missing')
        if name == 'server':
            ap_require(ap_SERVER_CHECKS <= set(checks), 'Missing independent server requirements')
            ap_keys(metrics, 'sql_checks unavailable_sql_checks websocket_connected_fraction', 'server metrics')
            ap_integer(metrics['sql_checks'], 2); ap_integer(metrics['unavailable_sql_checks'], 0, 0)
            ap_number(metrics['websocket_connected_fraction'], .95, 1)
        elif name == 'publication':
            ap_require(set(checks) == {'identities_stable', 'no_findings', 'exact_download_sql_display_projection', 'resource_sampling_complete'}, 'Publication assertions differ')
            ap_keys(metrics, 'observations aircraft', 'publication metrics')
            for dataset in metrics.values():
                ap_keys(dataset, 'samples distinct_batches maximum_rows', 'dataset')
                ap_integer(dataset['samples'], 479, 600)
                ap_require(dataset['samples'] == row['samples'], 'Dataset samples incomplete')
                ap_integer(dataset['distinct_batches'], 2); ap_integer(dataset['maximum_rows'], 1, 10000)
        elif name == 'delivery':
            ap_require(set(checks) == {'identities_stable', 'no_findings', 'cadence_sufficient'}, 'Delivery assertions differ')
            ap_keys(metrics, 'upserts verified_offsets pages', 'delivery metrics')
            for value in metrics.values():
                ap_integer(value, 1)
        else:
            required = ap_BROWSER_CHECKS | ({'public_http_scene_agreement', 'public_response_success'} if name == 'public-google' else set())
            ap_require(set(checks) == required, 'Browser assertions differ')
            ap_keys(metrics, 'scope roots_requested roots_succeeded natural_rotation_after_first_root_seconds child_successes_after_three_hours child_requests_after_three_hours post_three_hour_camera_action public_observations_max public_aircraft_max', 'Google metrics')
            ap_require(metrics['scope'] == 'genuine_google_long_session_stable_profile', 'Browser was not in genuine stable long-session mode')
            ap_integer(metrics['roots_requested'], 2, 20); ap_integer(metrics['roots_succeeded'], 2, 20)
            ap_require(metrics['roots_succeeded'] == metrics['roots_requested'], 'Google root request/response coverage differs')
            ap_number(metrics['natural_rotation_after_first_root_seconds'], 8998, row['elapsed_seconds'])
            ap_integer(metrics['child_successes_after_three_hours'], 1); ap_integer(metrics['child_requests_after_three_hours'], metrics['child_successes_after_three_hours'])
            ap_require(metrics['post_three_hour_camera_action'] is True, 'No post-three-hour exploration')
            for field in ('public_observations_max', 'public_aircraft_max'):
                ap_integer(metrics[field], 1 if name == 'public-google' else 0, 10000)
    return s


def ap_validate_pair(security_proof, soak_proof):
    security, soak = ap_validate_security(security_proof), ap_validate_soak(soak_proof)
    ap_require(security_proof['qualified_images'] == soak_proof['qualified_images'] and security_proof['runtime_source_sha256'] == soak_proof['runtime_source_sha256'], 'Security/soak artifact binding differs')
    ap_require(security['candidate_receipt_sha256'] == soak['candidate_receipt_sha256'], 'Candidate receipts differ')
    ap_require(ap_clock(security['final_refresh']['started_at']) > ap_clock(soak['ended_at']), 'Final advisory review must follow the full soak')
    return True
# END REVIEWED ADMISSION POLICY

# BEGIN SCOPED BROWSER AND RESTORE POLICY
# Structural admission of reviewed, hash-bound projections; never execution evidence by itself.
ev_COMMON = 'status execution source_receipt_sha256 runtime_source_sha256 qualified_images'
ev_ENGINES = {'chromium': '158.0.8127.18', 'firefox': '159.0', 'webkit': '27.2'}
ev_OPERATOR_CHECKS = set('actual_google_tiles_connected_with_attribution native_attribution_text_pointer_access_and_popup_open_close all_three_workspaces_fit_and_preserve_same_earth_canvas coordinate_bounds_and_zero_position last_known_position_count_and_optional_aging_visibility_control layer_and_settings_dialog_layout_and_keyboard_dismissal unobscured_composed_earth_pixels_are_nonblank_and_textured all_four_configured_regions_have_successful_bounded_collection_receipts'.split())
ev_PUBLIC_CHECKS = set('actual_nonempty_NASA_and_ADSB_public_capabilities real_google_ready_native_attribution_visible_clickable public_panel_actual_thermal_aircraft_counts_citation_exact_NASA_download visible_ODbL_attribution_exact_aircraft_download_both_enabled_nonempty_Earth_layers all_tabs_explicit_publication_states_same_earth_canvas_no_operator_controls public_source_health_scope_and_mobile_dialog unobscured_composed_earth_pixels_are_nonblank_and_textured 35_second_settle_no_hidden_data_media_operator_polls_or_websockets_no_page_errors'.split())
ev_MEDIA_CHECKS = set('google_native_attribution_visible_and_operable actual_validated_source_id_and_exact_original_excerpt_visible native_user_play_advances_actual_h264_aac_artifact native_caption_cues_exact_text_measured_timings_and_visible_on_off_pixels exact_complete_transcript_keyboard_scroll_and_native_track_state_sync native_decoded_frames_and_user_resume_pause persistent_earth_no_implicit_jobs_and_mobile_layout'.split())
ev_RESTORE_CHECKS = set('all_snapshot_tables_rows_indexes_revision_locale_equal sequence_definitions_and_non_mvcc_bounds restored_sequences_cover_snapshot_keys bootstrap_preserves_all_snapshot_data reader_exact_unprivileged_identity reader_two_table_only_and_negative_sql reader_no_dml_creation writer_exact_identity_and_publication_grants restore_has_no_host_ports_or_external_networks reader_collection_generation_explicitly_disabled main_image_start_identity_unchanged bound_helpers_unchanged reviewed_source_inventory_unchanged'.split())
ev_RASTER_THRESHOLDS = {'samples': 16, 'bright_fraction': .25, 'stddev': 10, 'color_bins': 16}
ev_RANGE_TRANSFORM = 'Fixed studio RGB (c-16)*255/219, clipped and rounded; independently tested with separate tagged known-color H264 control'
ev_FF_REQUIREMENT = 'Paused caption enable repaints without resuming'
ev_WK_REQUIREMENT = 'Unadjusted video RGB identity with independent reference decoder'


def ev_text(value, maximum=1200):
    ap_require(type(value) is str and 1 <= len(value) <= maximum and not any(ord(c)<32 for c in value), 'Bounded plain text required')


def ev_limits(value, minimum=1):
    ap_require(type(value) is list and minimum <= len(value) <= 25, 'Explicit scoped limitations required')
    for item in value: ev_text(item)
    ap_require(len(set(value)) == len(value), 'Duplicate limitation')


def ev_set(value, expected, name):
    ap_require(type(value) is list and all(type(v) is str for v in value) and len(value) == len(expected) and set(value) == expected, name + ' inventory differs')


def ev_zero(value): ap_integer(value, 0, 0)


def ev_true_checks(value, expected):
    ap_keys(value, ' '.join(expected), 'check set')
    ap_require(all(v is True for v in value.values()), 'A required check failed or is incomplete')


def ev_fresh(proof, status='PASS'):
    ap_require(type(proof) is dict and proof.get('status') == status and proof.get('execution') == 'fresh', 'Fresh final scoped proof required')
    ap_images(proof.get('qualified_images'))
    for key in ['runtime_source_sha256', 'source_receipt_sha256']: ap_hash_value(proof.get(key))


def ev_times(start, end, minimum=0, maximum=3600):
    seconds = (ap_clock(end)-ap_clock(start)).total_seconds()
    ap_number(seconds, minimum, maximum)
    return seconds


def ev_raster(row, minima=False):
    ap_keys(row, 'samples bright_fraction stddev color_bins' + ('' if minima else ' mean'), 'composed raster')
    ap_integer(row['samples'], 16, 713)
    ap_number(row['bright_fraction'], .25, 1)
    ap_number(row['stddev'], 10, 255)
    ap_integer(row['color_bins'], 16, row['samples'])
    if not minima: ap_number(row['mean'], 0, 255)


def ev_validate_raster(proof, name):
    row = proof['supplemental_raster']
    ap_keys(row, 'schema status execution gate artifact_profile browser version candidate_receipt_sha256 source_receipt_sha256 summary_sha256 samples_sha256 observer_sha256 raster_helper_sha256 started_at ended_at requested_seconds elapsed_seconds samples raster_samples findings cadence thresholds minima checks observed_services unobserved_image_roles limitations', 'supplemental raster')
    ap_integer(row['schema'], 1, 1)
    ap_require(row['gate']==name and row['artifact_profile']==('operator-free' if name=='google_operator' else 'public-context') and row['browser']=='chromium' and row['version']==ev_ENGINES['chromium'],'Raster observer/profile binding differs')
    ap_require(row['status'] == 'completed_sample' and row['execution'] == 'fresh', 'Actual completed raster observation required')
    for key in ['candidate_receipt_sha256','source_receipt_sha256','summary_sha256','samples_sha256','observer_sha256','raster_helper_sha256']: ap_hash_value(row[key])
    ap_require(row['candidate_receipt_sha256'] == proof['candidate_receipt_sha256'], 'Raster candidate differs')
    span = ev_times(row['started_at'], row['ended_at'], 14400, 14760)
    ap_integer(row['requested_seconds'],14400,14400)
    ap_number(row['elapsed_seconds'],14400,14600)
    ap_require(abs(span-row['elapsed_seconds']) <= 90, 'Raster wall and monotonic clocks differ')
    ap_integer(row['samples'],479,600)
    ap_integer(row['raster_samples'],row['samples'],row['samples'])
    ev_zero(row['findings'])
    ap_keys(row['cadence'], 'first_seconds maximum_gap_seconds final_gap_seconds', 'raster cadence')
    for value in row['cadence'].values(): ap_number(value,0,90)
    ap_keys(row['thresholds'], ' '.join(ev_RASTER_THRESHOLDS), 'raster thresholds')
    for key, value in ev_RASTER_THRESHOLDS.items():
        ap_number(row['thresholds'][key],value,value)
    ev_raster(row['minima'],True)
    ev_true_checks(row['checks'], {'no_findings','all_samples_have_raster','identities_stable','sources_unchanged','private_helpers_unchanged','browser_closed','no_implicit_generation','all_tabs_observed','google_provider_and_attribution_retained'})
    ap_keys(row['observed_services'], ' '.join(ap_SERVICES), 'raster services')
    identities=[]
    for service, role in ap_SERVICES.items():
        observed=row['observed_services'][service]
        ap_keys(observed,'image identity_sha256 started_at','raster service')
        ap_require(observed['image']==proof['qualified_images'][role],'Raster image differs')
        ap_hash_value(observed['identity_sha256']);identities.append(observed['identity_sha256'])
        ap_require(ap_clock(observed['started_at'])<=ap_clock(row['started_at']),'Service started after raster observation')
    ap_require(len(set(identities))==5,'Raster service identities collapse')
    ev_set(row['unobserved_image_roles'],{'tunnel'},'raster unobserved roles')
    ev_limits(row['limitations'])
    return row


def ev_validate_direct_google_binding(review, candidate_receipt_sha256):
    ap_keys(review,'mode status binding_receipt_sha256 independent_review_sha256 independent_review_status immutable_inventory_before_sha256 immutable_inventory_after_sha256 unchanged_browser_input_files added_files removed_files unchanged_source_files unchanged_executed_helpers checks generated_output','direct Google binding')
    ap_require(review['mode']=='direct_immutable_browser_binding' and review['status']=='passed','Direct Google binding did not pass')
    ap_require(review['independent_review_status']=='PASS_DIRECT_IMMUTABLE_BROWSER_BINDING','Independent direct binding review missing')
    for key in ['binding_receipt_sha256','independent_review_sha256','immutable_inventory_before_sha256','immutable_inventory_after_sha256']:ap_hash_value(review[key])
    ap_require(review['binding_receipt_sha256']!=review['independent_review_sha256'],'Binding and independent review must differ')
    ap_require(review['immutable_inventory_before_sha256']==review['immutable_inventory_after_sha256'],'Immutable browser membership or bytes changed')
    source_counts={'9a4e12bb8d52cba94f38174bb8291c51a89a3d7fb5697d519fa5974167883649':545,'65b92f66754f0e1c20e5df66082361421074e5d57742ecc2e2d791388aef41cf':556}
    ap_require(candidate_receipt_sha256 in source_counts,'Unreviewed direct Google candidate receipt')
    for key,value in [('unchanged_browser_input_files',1030),('unchanged_source_files',source_counts[candidate_receipt_sha256]),('unchanged_executed_helpers',4)]:ap_integer(review[key],value,value)
    ev_zero(review['added_files']);ev_zero(review['removed_files'])
    ev_true_checks(review['checks'],set('immutable_files_and_membership_equal original_frozen_source_unchanged current_source_unchanged private_helpers_unchanged five_services_unchanged all_cases_passed owned_browser_jobs_closed generated_output_retained_privately'.split()))
    generated=review['generated_output'];ap_keys(generated,'path before after contents_exported','separate generated output')
    ap_require(generated['path']=='chromium_headless_shell-1254/chrome-headless-shell-win64/debug.log' and generated['contents_exported'] is False,'Only exact generated diagnostic output may be excluded')
    for row in [generated['before'],generated['after']]:
        ap_keys(row,'sha256 bytes utf8_diagnostic_lines','retained generated log measurement');ap_hash_value(row['sha256'])
        ap_integer(row['bytes'],0,2000000);ap_integer(row['utf8_diagnostic_lines'],1 if row['bytes'] else 0,row['bytes'])
        if row['bytes']==0:ap_require(row['sha256']==sha256(b'').hexdigest(),'Empty diagnostic log hash differs')
    if generated['before']['sha256']==generated['after']['sha256']:ap_require(generated['before']==generated['after'],'Equal log hashes have contradictory measurements')


def ev_validate_google(proof, name, require_raster=True):
    ev_fresh(proof)
    ap_require(name in {'google_operator','google_public'} and proof.get('gate')==name,'Google gate differs')
    fields=ev_COMMON+' candidate_receipt_sha256 gate started_at ended_at cases_passed cases_failed cases observed_image_roles unobserved_image_roles browser_tool_version browser_manifest_sha256 binding_review limitations'
    ap_keys(proof,fields+(' supplemental_raster' if require_raster or 'supplemental_raster' in proof else ''),'Google proof')
    ap_hash_value(proof['candidate_receipt_sha256']);ap_hash_value(proof['browser_manifest_sha256'])
    ap_require(proof['browser_tool_version']=='1.65.0','Unreviewed browser tool version')
    ev_times(proof['started_at'],proof['ended_at'],1,3600)
    ev_set(proof['observed_image_roles'],{'backend','database','operator','public'},'Google observed roles')
    ev_set(proof['unobserved_image_roles'],{'tunnel'},'Google unobserved roles')
    ev_limits(proof['limitations'],3)
    for required in ['Browser/viewport emulation, not a physical phone test.','Raster sampling is a blank/flat-render guard, not source-location ground truth.','Five-image identity names the complete candidate; the tunnel image was not exercised by this browser gate.']:
        ap_require(required in proof['limitations'],'Google scope limitation omitted')
    sizes={(320,740),(390,844),(768,1024),(844,390)} if name=='google_operator' else {(320,740),(390,844),(1440,900)}
    expected={(browser,*size) for browser in ev_ENGINES for size in sizes}
    ap_integer(proof['cases_passed'],len(expected),len(expected));ev_zero(proof['cases_failed'])
    ap_require(type(proof['cases']) is list and len(proof['cases'])==len(expected),'Google measured case inventory incomplete')
    seen=set()
    for case in proof['cases']:
        ap_keys(case,'browser version viewport status checks composed_earth_raster screenshot_sha256 page_errors'+(' google_provider_end_state' if name=='google_operator' else ' network source_counts exact_downloads'),'Google case')
        ap_require(case['browser'] in ev_ENGINES and case['version']==ev_ENGINES[case['browser']] and case['status']=='passed','Google engine failed or differs')
        ap_keys(case['viewport'],'width height','viewport')
        for v in case['viewport'].values(): ap_integer(v,1,3000)
        key=(case['browser'],case['viewport']['width'],case['viewport']['height'])
        ap_require(key in expected and key not in seen,'Duplicate or unmeasured viewport');seen.add(key)
        expected_checks=ev_OPERATOR_CHECKS | ({'actual_farside_positions_hidden_and_region_restores_visible_hemisphere'} if key[1:]==(390,844) else set()) if name=='google_operator' else ev_PUBLIC_CHECKS
        ev_set(case['checks'],expected_checks,'Google assertions')
        ev_raster(case['composed_earth_raster']);ap_hash_value(case['screenshot_sha256']);ev_zero(case['page_errors'])
        if name=='google_operator': ap_require(case['google_provider_end_state']=='ready','Google imagery unavailable')
        else:
            network=case['network']
            ap_keys(network,'config_requests status_requests forbidden_api_requests media_requests publication_observation_requests publication_aircraft_requests application_nonread_requests websockets google_roots_ok google_tiles_ok','public network')
            for k in ['forbidden_api_requests','media_requests','application_nonread_requests','websockets']: ev_zero(network[k])
            for k,minimum in [('config_requests',1),('status_requests',2),('publication_observation_requests',1),('publication_aircraft_requests',3),('google_roots_ok',1),('google_tiles_ok',1)]: ap_integer(network[k],minimum,10000)
            ap_keys(case['source_counts'],'aircraft observations','source counts');ap_keys(case['exact_downloads'],'aircraft observations','downloads')
            for kind, cap in [('aircraft',5000),('observations',10000)]:
                ap_integer(case['source_counts'][kind],1,2000 if kind=='observations' else cap)
                download=case['exact_downloads'][kind];ap_keys(download,'status records','download')
                ap_integer(download['status'],200,200);ap_integer(download['records'],1,cap)
                ap_require(case['source_counts'][kind]<=download['records'],'Displayed source count exceeds linked packet inventory')
    ap_require(seen==expected,'Missing Google case')
    ap_require(len({case['screenshot_sha256'] for case in proof['cases']})==len(expected),'Repeated screenshot evidence')
    review=proof['binding_review']
    if type(review) is dict and review.get('mode')=='direct_immutable_browser_binding':
        ev_validate_direct_google_binding(review,proof['candidate_receipt_sha256'])
    else:
        ap_keys(review,'original_status original_failure original_failed_receipt_sha256 original_receipt_modified independent_addendum_sha256 independent_addendum_status generated_output unchanged_browser_input_files added_files removed_files unchanged_source_files unchanged_executed_helpers','log binding review')
        ap_require(review['original_status']=='failed' and review['original_failure']=='Installed browser bytes changed' and review['original_receipt_modified'] is False,'Original binding failure must remain explicit')
        for key in ['original_failed_receipt_sha256','independent_addendum_sha256']: ap_hash_value(review[key])
        ap_require(review['original_failed_receipt_sha256']!=review['independent_addendum_sha256'],'Original and review receipts must differ')
        ap_require(review['independent_addendum_status']=='PASS_WITH_EXPLICIT_GENERATED_LOG_BINDING_ADDENDUM','Independent log-only admission required')
        for key,value in [('unchanged_browser_input_files',1030),('unchanged_source_files',545),('unchanged_executed_helpers',4)]: ap_integer(review[key],value,value)
        ev_zero(review['added_files']);ev_zero(review['removed_files'])
        generated=review['generated_output']
        ap_keys(generated,'path before_sha256 after_sha256 bytes utf8_diagnostic_lines contents_exported','generated output')
        ap_require(generated['path']=='chromium_headless_shell-1254/chrome-headless-shell-win64/debug.log' and generated['contents_exported'] is False,'Only exact generated diagnostic output may differ')
        for key in ['before_sha256','after_sha256']: ap_hash_value(generated[key])
        ap_require(generated['before_sha256']!=generated['after_sha256'],'Expected observed log append absent')
        ap_integer(generated['bytes'],3072,3072);ap_integer(generated['utf8_diagnostic_lines'],16,16)
    if require_raster or 'supplemental_raster' in proof: ev_validate_raster(proof,name)
    return proof


def ev_validate_backup(proof):
    ev_fresh(proof);ap_keys(proof,ev_COMMON+' backup_restore','restore proof')
    row=proof['backup_restore']
    ap_keys(row,'schema candidate_receipt_sha256 started_at finished_at elapsed_seconds snapshot_seconds snapshot_lifetime_cap_seconds provider_requests main_service_mutations executed_restore_image_roles checks cleanup_verified archive snapshot_table_count snapshot_fingerprints_sha256 sequence_count sequence_evidence_sha256 cached_public_packets limits','restore')
    ap_integer(row['schema'],1,1);ap_hash_value(row['candidate_receipt_sha256'])
    span=ev_times(row['started_at'],row['finished_at'],1,600)
    ap_number(row['elapsed_seconds'],1,600);ap_require(abs(span-row['elapsed_seconds'])<=.01,'Restore clocks differ')
    ap_integer(row['snapshot_lifetime_cap_seconds'],240,240);ap_number(row['snapshot_seconds'],.001,240)
    ap_require(row['snapshot_seconds']<=row['elapsed_seconds'],'Snapshot lifetime exceeds execution')
    ev_zero(row['provider_requests']);ev_zero(row['main_service_mutations'])
    ev_set(row['executed_restore_image_roles'],{'backend','database'},'Restore executed roles')
    ev_true_checks(row['checks'],ev_RESTORE_CHECKS);ap_require(row['cleanup_verified'] is True,'Restore cleanup incomplete')
    archive=row['archive'];ap_keys(archive,'bytes format ownership_acl_included rows_bound_to_same_exported_snapshot sha256','restore archive')
    ap_integer(archive['bytes'],1,100_000_000);ap_hash_value(archive['sha256'])
    ap_require(archive['format']=='postgresql-custom' and archive['ownership_acl_included'] is False and archive['rows_bound_to_same_exported_snapshot'] is True,'Snapshot/ACL scope differs')
    ap_integer(row['snapshot_table_count'],17,17);ap_integer(row['sequence_count'],6,6)
    ap_hash_value(row['snapshot_fingerprints_sha256']);ap_hash_value(row['sequence_evidence_sha256'])
    ap_keys(row['cached_public_packets'],'aircraft observations','restored packets')
    for kind,cap in [('aircraft',5000),('observations',10000)]:
        packet=row['cached_public_packets'][kind]
        ap_keys(packet,'batch_id display_status displayed_rows stored_rows download_sha256 sql_download_exact','restored packet')
        ap_hash_value(packet['batch_id']);ap_hash_value(packet['download_sha256'])
        ap_integer(packet['stored_rows'],1,cap);ap_integer(packet['displayed_rows'],1,packet['stored_rows'])
        ap_require(packet['display_status']=='fresh' and packet['sql_download_exact'] is True,'Restored packet verification failed')
    ev_limits(row['limits'],4)
    for required in ['Sequence values are non-MVCC; exact snapshot-time equality is not claimed.','Local isolated restore only; encrypted off-machine backup and host disaster recovery were not tested.']:
        ap_require(required in row['limits'],'Restore scope limitation omitted')
    return row


def ev_pixel(row, video):
    extra=' range_normalized_content' if 'range_normalized_content' in row else ''
    ap_keys(row,'media_time width height reference_scale actual_rgba_sha256 reference_rgba_sha256 video_sha256 pixel_buffers_retained mean_absolute_rgb_error p99_absolute_rgb_error reference_rgb_standard_deviation mean_limit p99_limit unadjusted_status'+extra,'native decoded pixels')
    ap_number(row['media_time'],.001,60)
    for k in ['width','height']: ap_integer(row[k],64,4096)
    for k in ['actual_rgba_sha256','reference_rgba_sha256','video_sha256']: ap_hash_value(row[k])
    ap_require(row['video_sha256']==video and type(row['pixel_buffers_retained']) is bool,'Decoded artifact binding differs')
    ap_require(row['reference_scale'] in {'none','bilinear to observed native dimensions'},'Unreviewed reference scaling')
    ev_error_metrics(row)
    return row['mean_absolute_rgb_error']<=2 and row['p99_absolute_rgb_error']<=12


def ev_error_metrics(row):
    ap_number(row['mean_absolute_rgb_error'],0,255);ap_number(row['p99_absolute_rgb_error'],0,255)
    ap_number(row['reference_rgb_standard_deviation'],10,255)
    ap_number(row['mean_limit'],2,2);ap_number(row['p99_limit'],12,12)


def ev_validate_media(proof):
    ev_fresh(proof,'QUALIFIED_WITH_LIMITATIONS')
    ap_keys(proof,ev_COMMON+' candidate_receipt_sha256 gate qualified_engines implicit_generation_requests raw_engines_passed started_at ended_at browser_receipt_sha256 browser_cases observed_image_roles unobserved_image_roles artifact_provenance independent_color_control provider_generation_calls database_connected api_audit api_execution_scope owned_cleanup_verified temporary_key_inputs_removed bound_inputs_unchanged limitations','Media proof')
    ap_require(proof['gate']=='media_replay','Media gate differs');ap_hash_value(proof['candidate_receipt_sha256']);ap_hash_value(proof['browser_receipt_sha256'])
    ev_times(proof['started_at'],proof['ended_at'],1,600)
    ap_integer(proof['qualified_engines'],3,3);ap_integer(proof['raw_engines_passed'],1,1)
    ev_zero(proof['implicit_generation_requests']);ev_zero(proof['provider_generation_calls'])
    for key in ['owned_cleanup_verified','temporary_key_inputs_removed','bound_inputs_unchanged']: ap_require(proof[key] is True,'Replay cleanup or input binding failed')
    ap_require(proof['database_connected'] is False,'Replay must not imply DB execution')
    ev_set(proof['observed_image_roles'],{'backend','operator'},'Replay observed roles');ev_set(proof['unobserved_image_roles'],{'database','public','tunnel'},'Replay unobserved roles')
    scope=proof['api_execution_scope']
    ap_keys(scope,'mode candidate_backend_image_used entrypoint_overridden production_fastapi_routes_executed database_connected new_model_or_media_generation meaning','Replay API scope')
    ap_require(scope['mode']=='isolated_read_only_replay_server' and scope['candidate_backend_image_used'] is True and scope['entrypoint_overridden'] is True and all(scope[k] is False for k in ['production_fastapi_routes_executed','database_connected','new_model_or_media_generation']),'Replay production API claim forbidden')
    ev_text(scope['meaning']);ev_limits(proof['limitations'],5)
    for required in ['Retained analysis/video replay, not fresh model success or report truth.','No physical-device, Safari or listener-audibility qualification.','Imagery includes Google and the explicitly allowed Esri reference fallback; this is not a Google-only network claim.']:
        ap_require(required in proof['limitations'],'Media scope limitation omitted')
    artifact=proof['artifact_provenance'];ap_keys(artifact,'execution capture_receipt_sha256 capture_started_at video_sha256 video_bytes measured_segments duration_seconds','retained artifact')
    ap_require(artifact['execution'] in {'historical artifact replayed freshly on exact candidate16','historical artifact replayed freshly on exact candidate17','historical artifact replayed freshly on exact candidate18'},'Historical artifact provenance omitted')
    ap_require(ap_clock(artifact['capture_started_at'])<ap_clock(proof['started_at']),'Artifact capture is not historical')
    ap_hash_value(artifact['capture_receipt_sha256']);ap_hash_value(artifact['video_sha256']);ap_integer(artifact['video_bytes'],1,30_000_000)
    ap_integer(artifact['measured_segments'],3,3);ap_number(artifact['duration_seconds'],1,300)
    ap_require(type(proof['browser_cases']) is list and len(proof['browser_cases'])==3,'Three exact native cases required')
    seen=set()
    for case in proof['browser_cases']:
        ap_keys(case,'browser version viewport status checks generation_posts blocked_mutations blocked_external page_errors imagery_requests native_decoded_pixels decoded_frames frame_callback callback_measurement_scope caption_metadata paused_caption_restore native_user_pause_resume engine_limitations captions'+(' caption_user_resume callback_cause' if case.get('browser')=='firefox' else ''),'Media case')
        engine=case['browser'];ap_require(engine in ev_ENGINES and engine not in seen and case['version']==ev_ENGINES[engine],'Missing/duplicate/different Media engine');seen.add(engine)
        ap_keys(case['viewport'],'width height','Media viewport')
        ap_integer(case['viewport']['width'],390,390);ap_integer(case['viewport']['height'],844,844)
        ap_require(case['status']==('passed' if engine=='chromium' else 'qualified_with_limitations'),'Raw native outcome relabeled')
        ev_set(case['checks'],ev_MEDIA_CHECKS,'Media assertions')
        for k in ['generation_posts','blocked_mutations','blocked_external','page_errors']: ev_zero(case[k])
        ap_keys(case['imagery_requests'],'google esri_reference','imagery traffic')
        for value in case['imagery_requests'].values(): ap_integer(value,1,10000)
        pixel=case['native_decoded_pixels'];raw_pass=ev_pixel(pixel,artifact['video_sha256'])
        ap_require(pixel['pixel_buffers_retained'] is (engine=='webkit'),'Native raw-buffer retention scope differs')
        ap_require(pixel['media_time']<artifact['duration_seconds'],'Sample beyond artifact')
        ap_require(raw_pass==(engine!='webkit') and pixel['unadjusted_status']==('PASS' if raw_pass else 'FAIL'),'Raw RGB outcome differs from measured errors')
        if engine=='webkit':
            normalized=pixel.get('range_normalized_content');ap_keys(normalized,'transform status mean_absolute_rgb_error p99_absolute_rgb_error reference_rgb_standard_deviation mean_limit p99_limit','range diagnostic')
            ev_error_metrics(normalized)
            ap_require(normalized['status']=='PASS_CONTENT_WITH_RANGE_LIMITATION' and normalized['transform']==ev_RANGE_TRANSFORM and normalized['mean_absolute_rgb_error']<=2 and normalized['p99_absolute_rgb_error']<=12,'Fixed-range content qualification failed')
        else: ap_require('range_normalized_content' not in pixel,'Unexpected fitted/normalized raw result')
        captions=case['caption_metadata'];ap_keys(captions,'cue_count timings audio_container_delta_seconds exact_cue_text default_showing video_sha256','captions')
        ap_integer(captions['cue_count'],3,3);ap_require(captions['exact_cue_text'] is True and captions['default_showing'] is True and captions['video_sha256']==artifact['video_sha256'],'Caption source identity failed')
        ap_number(captions['audio_container_delta_seconds'],0,.1)
        ap_require(type(captions['timings']) is list and len(captions['timings'])==3,'All measured cues required')
        prior=0
        for cue in captions['timings']:
            ap_keys(cue,'start end','caption cue');ap_number(cue['start'],0,300);ap_number(cue['end'],.001,300)
            ap_require(abs(cue['start']-prior)<.00001 and cue['end']>cue['start'],'Caption cue gap/overlap');prior=cue['end']
        ap_require(abs(artifact['duration_seconds']-prior-captions['audio_container_delta_seconds'])<=.002,'Caption duration disagrees with retained media')
        pause=case['paused_caption_restore'];ap_keys(pause,'native_mode same_frame status','paused caption')
        ap_require(pause['native_mode']=='showing' and pause['same_frame'] is True and pause['status']==('FAIL' if engine=='firefox' else 'PASS'),'Paused-caption raw outcome relabeled')
        rendered=case['captions'];ap_keys(rendered,'cue_count timings audio_container_delta_seconds transcript_sha256 exact_transcript default_showing rendered_caption_on_off_pixels paused_render_restore frame_time native_off_custom_on_state_sync transcript_keyboard_scroll pixel_buffers_retained private_debug_frames_retained limits','caption rendering')
        for key in ['cue_count','timings','audio_container_delta_seconds']: ap_require(ap_canonical(rendered[key])==ap_canonical(captions[key]),'Caption rendering metadata differs')
        ap_hash_value(rendered['transcript_sha256'])
        for key in ['exact_transcript','default_showing','rendered_caption_on_off_pixels','native_off_custom_on_state_sync']: ap_require(rendered[key] is True,'Caption rendering assertion failed')
        ap_require(rendered['paused_render_restore'] is (engine!='firefox'),'Raw paused-render outcome relabeled')
        for key in ['pixel_buffers_retained','private_debug_frames_retained']: ap_require(rendered[key] is False,'Caption diagnostic buffers were not retained by this execution')
        ap_number(rendered['frame_time'],0,artifact['duration_seconds']);ev_text(rendered['limits'])
        scroll=rendered['transcript_keyboard_scroll'];ap_keys(scroll,'top height scroll_height after','transcript scroll')
        for value in scroll.values(): ap_number(value,0,100000)
        ap_require(scroll['height']>0 and scroll['scroll_height']>=scroll['height'] and scroll['after']<=scroll['scroll_height'],'Transcript dimensions invalid')
        if scroll['scroll_height']>scroll['height']: ap_require(scroll['after']>scroll['top'],'Scrollable transcript did not move')
        if engine=='firefox':
            recovery=case['caption_user_resume'];ap_keys(recovery,'status native_user_play_and_pause from_time to_time guidance_visible_before guidance_cleared_on_playing','caption recovery')
            for key in ['native_user_play_and_pause','guidance_visible_before','guidance_cleared_on_playing']: ap_require(recovery[key] is True,'Actual caption recovery incomplete')
            for key in ['from_time','to_time']: ap_number(recovery[key],0,artifact['duration_seconds'])
            ap_require(recovery['status']=='PASS' and recovery['to_time']>=recovery['from_time']+.5,'Caption recovery did not advance')
        resume=case['native_user_pause_resume'];ap_keys(resume,'before after passed','user resume')
        for value in [resume['before'],resume['after']]: ap_number(value,0,artifact['duration_seconds'])
        ap_require(resume['passed'] is True and resume['after']>=resume['before']+.5,'Actual user-resume recovery absent')
        expected_scope={'chromium':'presented_advancing_callbacks','firefox':'unsupported_unqualified_raw_observation','webkit':'unavailable_no_callback_evidence'}[engine]
        ap_require(case['callback_measurement_scope']==expected_scope,'Native callback scope differs')
        if engine=='firefox':
            ap_require(case['callback_cause']=='UNVERIFIED','Unsupported callback cause is unverified')
            ap_require('Firefox reported one callback media_time outside the retained video duration. Its cause is UNVERIFIED; the unsupported callback does not qualify playback or frame time.' in proof['limitations'],'Unsupported out-of-range callback limitation omitted')
        callback=case['frame_callback'];ap_keys(callback,'status samples','frame callback')
        ap_integer(case['decoded_frames'],1 if engine=='chromium' else 0,100000)
        ap_require(type(callback['samples']) is list and len(callback['samples'])<=2,'Bounded native callback evidence required')
        for sample in callback['samples']:
            ap_keys(sample,'callback_time height media_time presented_frames width','callback sample')
            for key in ['callback_time','media_time']: ap_number(sample[key],0,1e9)
            for key in ['height','width','presented_frames']: ap_integer(sample[key],1,100000)
        if engine=='chromium':
            ap_require(callback['status']=='presented' and len(callback['samples'])==2,'Advancing native callbacks absent')
            first,last=callback['samples'];ap_require(last['media_time']>first['media_time'] and last['media_time']<artifact['duration_seconds'] and last['presented_frames']>first['presented_frames'],'Frozen or out-of-range native callback')
            ap_require(all(sample['width']==pixel['width'] and sample['height']==pixel['height'] for sample in callback['samples']),'Native callback dimensions differ')
        else:
            ev_zero(case['decoded_frames'])
            ap_require(callback['status']==('No two callbacks within 2 seconds' if engine=='firefox' else 'API unavailable'),'Unsupported counter limitation relabeled')
            ap_require(len(callback['samples'])==(1 if engine=='firefox' else 0),'Native callback evidence differs')
            if engine=='firefox':ap_require(callback['samples'][0]['media_time']>artifact['duration_seconds'],'Original unsupported out-of-range observation was altered')
        limits=case['engine_limitations'];ap_require(type(limits) is list and len(limits)==(0 if engine=='chromium' else 1),'Native limitation omitted')
        if limits:
            ap_keys(limits[0],'requirement status handling','native limitation')
            ap_require(limits[0]['status']=='FAIL' and limits[0]['requirement']==(ev_FF_REQUIREMENT if engine=='firefox' else ev_WK_REQUIREMENT),'Raw engine failure omitted')
            ev_text(limits[0]['handling'])
            ap_require(engine+': '+limits[0]['requirement']+' remains FAIL. '+limits[0]['handling'] in proof['limitations'],'Top-level native limitation omitted')
    ev_validate_control(proof['independent_color_control'],artifact['video_sha256'])
    audit=proof['api_audit'];ap_keys(audit,'reads video_reads video_ranges unknown_reads unknown_read_routes','replay API audit')
    for k in ['reads','video_reads','video_ranges']: ap_integer(audit[k],1,10000)
    ap_integer(audit['unknown_reads'],1,audit['reads']);ap_keys(audit['unknown_read_routes'],'/costs/summary /ws/events <other>','replay denied routes')
    total=0
    for route in ['/costs/summary','/ws/events']:
        ap_require(type(audit['unknown_read_routes'][route]) is dict and set(audit['unknown_read_routes'][route])=={'GET 404'},'Denied local route fields differ')
        value=audit['unknown_read_routes'][route]['GET 404'];ap_integer(value,1,10000);total+=value
    ap_require(audit['unknown_read_routes']['<other>']=={} and total==audit['unknown_reads'],'Unknown local read not accounted for')
    return proof


def ev_validate_control(control, report_video):
    ap_keys(control,'execution binding_sha256 receipt_sha256 video_sha256 decoder_sha256 playwright_version cases limits scope binding_checks','independent control')
    ap_require(control['execution']=='separate prior Playwright1.65 control; all original inputs rehashed for this replay' and control['playwright_version']=='1.65.0','Control provenance differs')
    for key in ['binding_sha256','receipt_sha256','video_sha256','decoder_sha256']: ap_hash_value(control[key])
    ap_require(control['scope']=='Independent known-color H264 control, explicit BT709 limited-range metadata; no report artifact modification','Control source/encoding scope differs')
    binding=control['binding_checks'];ap_keys(binding,'status exit_code owned_browser_job_closed inputs_unchanged','control execution binding')
    ap_require(binding['status']=='measured' and binding['owned_browser_job_closed'] is True and binding['inputs_unchanged'] is True,'Control execution incomplete')
    ev_zero(binding['exit_code'])
    ap_require(control['video_sha256']!=report_video,'Independent control cannot be report artifact')
    ev_limits(control['limits'],2)
    ap_require(type(control['cases']) is list and len(control['cases'])==2,'Both color-control engines required')
    seen=set();references=set();canvas_sizes=set()
    for case in control['cases']:
        ap_keys(case,'browser browser_version status actual_sample actual_sha256 reference_sha256 raw_interior fixed_studio_to_full_interior','color control')
        engine=case['browser'];ap_require(engine in {'chromium','webkit'} and engine not in seen and case['browser_version']==ev_ENGINES[engine] and case['status']=='MEASURED','Control engine mismatch');seen.add(engine)
        for key in ['actual_sha256','reference_sha256']: ap_hash_value(case[key])
        sample=case['actual_sample'];ap_keys(sample,'canvas_height canvas_width native_height native_width time','control sample')
        for key in ['canvas_height','canvas_width','native_height','native_width']: ap_integer(sample[key],64,4096)
        ap_number(sample['time'],.001,10)
        references.add(case['reference_sha256']);canvas_sizes.add((sample['canvas_width'],sample['canvas_height']))
        for key in ['raw_interior','fixed_studio_to_full_interior']:
            row=case[key];ap_keys(row,'mae p99 samples','control errors');ap_number(row['mae'],0,255);ap_number(row['p99'],0,255);ap_integer(row['samples'],7200,7200)
        raw=case['raw_interior'];fixed=case['fixed_studio_to_full_interior']
        raw_pass=raw['mae']<=2 and raw['p99']<=12;fixed_pass=fixed['mae']<=2 and fixed['p99']<=12
        ap_require(raw_pass==(engine=='chromium') and fixed_pass==(engine=='webkit'),'Independent range control/negative control did not reproduce scope')
    ap_require(len(references)==1 and canvas_sizes=={(1280,720)},'Same independent reference/control canvas identity must agree')


def ev_validate_proof_set(proofs):
    security=proofs['security']['security'];soak=proofs['full_pipeline_soak']['soak']
    candidate=security['candidate_receipt_sha256']
    ap_require(soak['candidate_receipt_sha256']==candidate,'Soak candidate differs')
    for name in ['google_operator','google_public','media_replay']:
        ap_require(proofs[name]['candidate_receipt_sha256']==candidate,'Browser candidate differs')
    ap_require(proofs['backup_restore']['backup_restore']['candidate_receipt_sha256']==candidate,'Restore candidate differs')
    operator,public=proofs['google_operator'],proofs['google_public']
    ap_require(operator['binding_review']==public['binding_review'] and operator['browser_manifest_sha256']==public['browser_manifest_sha256'],'Matrix source/addendum binding differs')
    for key in ['summary_sha256','samples_sha256']:
        ap_require(operator['supplemental_raster'][key]!=public['supplemental_raster'][key],'Separate operator/public raster executions required')
    for key in ['source_receipt_sha256','observer_sha256','raster_helper_sha256']:
        ap_require(operator['supplemental_raster'][key]==public['supplemental_raster'][key],'Raster parent/source binding differs')
    for proof in [operator,public]:
        raster=proof['supplemental_raster']
        ap_require(raster['observed_services']==soak['observed_services'],'Supplemental raster must observe the same stable service incarnations')
        ap_require(ap_clock(security['final_refresh']['started_at'])>ap_clock(raster['ended_at']),'Final security refresh must follow both independent raster soaks')
    return True
# END SCOPED BROWSER AND RESTORE POLICY


def qualify(snapshots,version):
    if READY not in snapshots or MANIFEST not in snapshots:raise ValueError('Final local qualification is absent')
    ready=strict_json(snapshots[READY]);declared=strict_json(snapshots[MANIFEST])
    if type(ready) is not dict or type(ready.get('schema')) is not int or ready.get('schema')!=1 or ready.get('ready') is not True or ready.get('prerelease') is not True:raise ValueError('Final local qualification is not ready')
    if ready.get('repository')!=REPOSITORY or ready.get('release_ref')!=BRANCH or ready.get('version')!=version or version!=VERSION:raise ValueError('Release identity differs')
    if set(ready)!={'schema','ready','prerelease','repository','release_ref','version','source_manifest_sha256','runtime_source_sha256','images','evidence','limitations'}:raise ValueError('Unexpected readiness fields')
    rows=file_rows(snapshots)
    if type(declared) is not dict or set(declared)!={'schema','files'} or type(declared['schema']) is not int or declared['schema']!=1 or type(declared['files']) is not list:raise ValueError('Source manifest schema differs')
    for row in declared['files']:
        if type(row) is not dict or set(row)!={'path','bytes','sha256'} or type(row['path']) is not str or not exact_int(row['bytes']) or not valid_sha(row['sha256']):raise ValueError('Source inventory field types differ')
    if declared!={'schema':1,'files':rows}:raise ValueError('Source inventory differs, including additions or omissions')
    if ready.get('source_manifest_sha256')!=checksum(snapshots[MANIFEST]):raise ValueError('Source manifest digest differs')
    runtime=[r for r in rows if r['path'].startswith(RUNTIME_PREFIXES) or r['path'] in RUNTIME_FILES]
    if not RUNTIME_FILES<={r['path'] for r in runtime}:raise ValueError('Runtime profile inventory incomplete')
    runtime_hash=checksum(canonical(runtime))
    if ready.get('runtime_source_sha256')!=runtime_hash:raise ValueError('Qualified runtime source differs')
    images=ready.get('images',{})
    if type(images) is not dict or set(images)!=ROLES or not all(type(v) is str and re.fullmatch(r'sha256:[0-9a-f]{64}',v) for v in images.values()):raise ValueError('Five immutable runtime image identities required')
    proofs=ready.get('evidence',{})
    if set(proofs)!=GATES:raise ValueError('Required evidence inventory incomplete')
    admitted_proofs={}
    for name,reference in proofs.items():
        if type(reference) is not dict or set(reference)!={'path','sha256'}:raise ValueError('Evidence reference schema differs')
        path=reference.get('path','')
        if not re.fullmatch(r'docs/qualification/[A-Za-z0-9_.-]+\.json',path) or path in {READY,MANIFEST} or path not in snapshots:raise ValueError('Evidence must be a committed sanitized projection')
        if reference.get('sha256')!=checksum(snapshots[path]):raise ValueError('Evidence digest differs')
        proof=strict_json(snapshots[path])
        if type(proof) is not dict:raise ValueError('Evidence must be an object')
        accepted={'PASS','QUALIFIED_WITH_LIMITATIONS'} if name=='media_replay' else {'PASS'}
        if proof.get('status') not in accepted or proof.get('runtime_source_sha256')!=runtime_hash or proof.get('qualified_images')!=images:raise ValueError('Evidence outcome or source/image identity differs')
        if not valid_sha(proof.get('source_receipt_sha256')) or proof.get('execution') not in {'fresh','rebound'}:raise ValueError('Original execution evidence required')
        if proof['execution']=='rebound' and not valid_sha(proof.get('equivalence_sha256')):raise ValueError('Historical evidence requires explicit equivalence proof')
        admitted_proofs[name]=proof
        if name=='full_pipeline_soak':ap_validate_soak(proof)
        if name=='security':ap_validate_security(proof)
        if name in {'google_operator','google_public'}:ev_validate_google(proof,name)
        if name=='media_replay':ev_validate_media(proof)
        if name=='backup_restore':ev_validate_backup(proof)
    ap_validate_pair(admitted_proofs['security'],admitted_proofs['full_pipeline_soak'])
    ev_validate_proof_set(admitted_proofs)
    limits=ready.get('limitations')
    if not isinstance(limits,list) or not 1<=len(limits)<=20 or any(not isinstance(x,str) or not 1<=len(x)<=600 or '\n' in x for x in limits):raise ValueError('Bounded explicit release limitations required')
    return ready


def release_notes(version,commit,limitations):
    intro=('RC.5 brings Google Earth imagery and clearer source-specific identifiers into one workspace. '
           'Public context uses separate NASA FIRMS thermal observations and ADSB.lol snapshots, with attribution and downloads of the exact published batches. '
           'Reconnect and recovery repairs, restricted public access and native dependency fixes are covered by the scoped browser, pipeline and four-hour qualification recorded with this prerelease.')
    return (intro+'\n\nVerified source prerelease '+version+'\n\nSource commit: '+commit+'\n\n'+'\n'.join('- '+item for item in limitations)+'\n').encode('utf-8')


def ci_identity(run_id,attempt):
    if not re.fullmatch(r'[1-9][0-9]{0,19}',str(run_id)) or not re.fullmatch(r'[1-9][0-9]{0,4}',str(attempt)):raise ValueError('Exact hosted run identity required')
    return {'run_id':str(run_id),'run_attempt':str(attempt),'url':'https://github.com/'+REPOSITORY+'/actions/runs/'+str(run_id)}


def verify_git_tree(root,commit,snapshots):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,timeout=15).decode().strip()
    if head!=commit:raise ValueError('Checked out source differs from event commit')
    raw=subprocess.check_output(['git','ls-tree','-rz','--full-tree',commit],cwd=root,timeout=30)
    tree={}
    for entry in raw.split(b'\0'):
        if not entry:continue
        header,name=entry.split(b'\t',1);mode,kind,oid=header.decode().split();name=name.decode('utf8')
        if name in tree:raise ValueError('Duplicate Git tree entry')
        tree[name]=(mode,kind,oid)
    for name,data in snapshots.items():
        value=tree.get(name)
        if not value or value[0] not in {'100644','100755'} or value[1]!='blob':raise ValueError('Export source is not a regular committed blob')
        if value[2]!=sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest():raise ValueError('Export source bytes differ from committed blob')


def package(root,out,event,ref,repository,commit,actor,run_id,attempt):
    identity(event,ref,repository,commit,actor)
    spec=importlib.util.spec_from_file_location('gate',root/'tools/release_gate.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    if gate.ROOT.resolve()!=root.resolve():raise ValueError('Export root differs')
    snapshots={p.relative_to(root).as_posix():p.read_bytes() for p in gate.export_files()}
    verify_git_tree(root,commit,snapshots)
    if any(gate.content_findings(data,name) for name,data in snapshots.items()):raise ValueError('Public source content gate failed')
    version=gate.release_version(snapshots);ready=qualify(snapshots,version)
    files=[{'path':name,'bytes':len(data),'sha256':checksum(data)} for name,data in sorted(snapshots.items())]
    archive=gate.candidate_archive(snapshots,files,version)
    if archive!=gate.candidate_archive(snapshots,files,version):raise ValueError('Archive is not deterministic in this runtime')
    out.mkdir(parents=True,exist_ok=False)
    filename=f'conflict-monitor-{version}-source.zip'
    (out/filename).write_bytes(archive)
    (out/(filename+'.sha256')).write_text(checksum(archive)+'  '+filename+'\n',encoding='utf8',newline='\n')
    notes=release_notes(version,commit,ready['limitations'])
    verification={'schema':1,'status':'READY_FOR_PRERELEASE','repository':repository,'source_commit':commit,'release_ref':ref,'tag':'v'+version,
        'archive':{'name':filename,'bytes':len(archive),'sha256':checksum(archive)},'source_manifest_sha256':ready['source_manifest_sha256'],
        'ready_receipt_sha256':checksum(snapshots[READY]),'runtime_source_sha256':ready['runtime_source_sha256'],'images':ready['images'],
        'evidence':ready['evidence'],'limitations':ready['limitations'],'release_notes_sha256':checksum(notes),'ci':ci_identity(run_id,attempt)}
    verification_bytes=canonical(verification)
    (out/'verification.json').write_bytes(verification_bytes)
    (out/'RELEASE_NOTES.txt').write_bytes(notes)
    return {'archive_sha256':checksum(archive),'verification_sha256':checksum(verification_bytes),'tag':'v'+version}


if __name__=='__main__':
    import os
    parser=ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=package(args.root.resolve(),args.output.resolve(),*[os.environ[k] for k in ['GITHUB_EVENT_NAME','GITHUB_REF','GITHUB_REPOSITORY','GITHUB_SHA','GITHUB_ACTOR','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT']])
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf8') as output:
        for key,value in result.items():output.write(key+'='+value+'\n')
