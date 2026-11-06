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
    ap_keys(refresh, 'status completed_at official_database_sha256 upstream_review_sha256 receipt_sha256', 'final refresh')
    ap_require(refresh['status'] == 'COMPLETE_NO_UNRESOLVED_HIGH_CRITICAL', 'Final advisory review incomplete')
    completed = ap_clock(refresh['completed_at'])
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
    ap_require(ap_clock(security['final_refresh']['completed_at']) >= ap_clock(soak['ended_at']), 'Final advisory review must follow the full soak')
    return True
# END REVIEWED ADMISSION POLICY


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
        if name=='media_replay' and (type(proof.get('qualified_engines')) is not int or proof['qualified_engines']!=3 or type(proof.get('implicit_generation_requests')) is not int or proof['implicit_generation_requests']!=0):raise ValueError('Native replay UI gate incomplete')
    ap_validate_pair(admitted_proofs['security'],admitted_proofs['full_pipeline_soak'])
    limits=ready.get('limitations')
    if not isinstance(limits,list) or not 1<=len(limits)<=20 or any(not isinstance(x,str) or not 1<=len(x)<=600 or '\n' in x for x in limits):raise ValueError('Bounded explicit release limitations required')
    return ready


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
    notes=('Verified source prerelease '+version+'\n\nSource commit: '+commit+'\n\n'+'\n'.join('- '+item for item in ready['limitations'])+'\n').encode()
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
