import copy
from contextlib import redirect_stdout
import io
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile
from types import SimpleNamespace
import yaml

FOLDER=Path(__file__).resolve().parent
WORKFLOW_PATH=FOLDER.parent/'.github/workflows/verify.yml'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
gate=module('packager',FOLDER/'prepare_release_publication.py')
export=module('export',FOLDER/'release_gate.py')
scoped=module('scoped_test_fixtures',FOLDER/'test_release_proof_fixtures.py')
workflow=yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf8'))
INLINE_SOURCE=next(step for step in workflow['jobs']['publish_qualified_prerelease']['steps'] if 'GH_TOKEN' in step.get('env',{}))['run'].split("python3 - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
from types import ModuleType
publisher=ModuleType('publisher_under_test')
exec(compile(INLINE_SOURCE,'reviewed-inline-workflow-publisher','exec'),publisher.__dict__)


def fixture(proof_override=None,ready_override=None):
    snapshots={name:b'authored runtime fixture\n' for name in gate.RUNTIME_FILES}
    snapshots['backend/app/main.py']=b'authored backend fixture\n'
    snapshots['frontend/src/App.tsx']=b'authored frontend fixture\n'
    runtime_hash=gate.checksum(gate.canonical(gate.file_rows(snapshots)))
    images={role:'sha256:'+str(index)*64 for index,role in enumerate(sorted(gate.ROLES),1)}
    evidence={}
    for name in gate.GATES:
        proof={'status':'PASS','runtime_source_sha256':runtime_hash,'qualified_images':images,'source_receipt_sha256':'a'*64,'execution':'fresh'}
        if name=='full_pipeline_soak':proof=admission_soak();proof['runtime_source_sha256']=runtime_hash
        if name=='security':proof=admission_security();proof['runtime_source_sha256']=runtime_hash
        if name in {'google_operator','google_public','media_replay','backup_restore'}:proof=scoped.scoped_fixture(name);proof['runtime_source_sha256']=runtime_hash
        if proof_override and name in proof_override:
            override=proof_override[name]
            if callable(override):override(proof)
            else:proof.update(override)
        path='docs/qualification/'+name+'.json';snapshots[path]=gate.canonical(proof)
        evidence[name]={'path':path,'sha256':gate.checksum(snapshots[path])}
    snapshots[gate.MANIFEST]=gate.canonical({'schema':1,'files':gate.file_rows(snapshots)})
    ready={'schema':1,'ready':True,'prerelease':True,'version':gate.VERSION,'repository':gate.REPOSITORY,'release_ref':gate.BRANCH,
           'source_manifest_sha256':gate.checksum(snapshots[gate.MANIFEST]),'runtime_source_sha256':runtime_hash,'images':images,'evidence':evidence,
           'limitations':['Authored test evidence only; never publish this fixture.']}
    if ready_override:ready.update(ready_override)
    snapshots[gate.READY]=gate.canonical(ready)
    return snapshots


# Authored policy fixtures only; these never become release evidence.
ADMISSION_H = 'a' * 64
ADMISSION_IMAGES = {role: 'sha256:' + str(index)*64 for index, role in enumerate(sorted(gate.ap_IMAGE_ROLES), 1)}


def admission_base():
    return {'status': 'PASS', 'execution': 'fresh', 'source_receipt_sha256': ADMISSION_H,
            'runtime_source_sha256': ADMISSION_H, 'qualified_images': dict(ADMISSION_IMAGES)}


def admission_match(cve, severity):
    row = {'vulnerability': cve, 'severity': severity, 'package': 'authored-package', 'version': '1.0',
           'namespace': 'authored:test', 'match_sha256': ADMISSION_H}
    return {'key': gate.ap_digest(gate.ap_canonical(row)), **row}


def admission_security():
    proof = admission_base()
    scans = {}
    for scan_id, role in gate.ap_SCANS.items():
        rows = [admission_match('CVE-2099-0001', 'High'), admission_match('CVE-2099-0002', 'Low')] if scan_id == 'image-backend' else []
        scans[scan_id] = {'role': role, 'image': ADMISSION_IMAGES[role], 'raw_sha256': ADMISSION_H, 'receipt_sha256': ADMISSION_H,
            'execution': 'fresh', 'equivalence_sha256': None, 'inventory_sha256': ADMISSION_H if scan_id.startswith('native-') else None,
            'exit_code': 2 if rows else 0, 'database_sha256': ADMISSION_H, 'database_built': '2026-11-06T00:00:00Z',
            'record_count': len(rows), 'severity_counts': {'High': 1, 'Low': 1} if rows else {}, 'records': rows}
    dispositions = []
    for row in scans['image-backend']['records']:
        dispositions.append({'role': 'backend', 'vulnerability': row['vulnerability'], 'severity': row['severity'],
            'disposition': 'fixed' if row['severity'] == 'High' else 'affected_unresolved', 'reason': 'Authored test only.',
            'limits': 'Not real evidence.', 'image': ADMISSION_IMAGES['backend'], 'evidence_sha256s': [ADMISSION_H], 'image_binding_sha256s': [ADMISSION_H],
            'record_keys': ['image-backend:'+row['key']], 'source_row_sha256': ADMISSION_H, 'review_row_sha256': ADMISSION_H})
    proof['security'] = {'schema': 1, 'admission': 'SCOPED_COMPONENT_REVIEW_WITH_RESIDUALS', 'reviewed_at': '2026-11-06T05:01:00Z',
        'candidate_receipt_sha256': ADMISSION_H, 'matrix_sha256': ADMISSION_H, 'validation_sha256': ADMISSION_H, 'independent_review_sha256': ADMISSION_H,
        'verified_evidence_sha256s': [ADMISSION_H],
        'reference_verification': {'status':'INDEPENDENT_REFERENCE_BYTES_VERIFIED','receipt_sha256':ADMISSION_H,'verified_sha256s':[ADMISSION_H]},
        'scans': scans, 'dispositions': dispositions,
        'residuals': [{'role': 'backend', 'vulnerability': 'CVE-2099-0002', 'severity': 'Low'}], 'non_cve_issues': [],
        'final_refresh': {'status': 'COMPLETE_NO_UNRESOLVED_HIGH_CRITICAL', 'started_at':'2026-11-06T05:01:00Z', 'completed_at': '2026-11-06T05:02:00Z',
                          'official_database_sha256': ADMISSION_H, 'upstream_review_sha256': ADMISSION_H, 'receipt_sha256': ADMISSION_H}}
    return proof


def admission_soak():
    proof = admission_base()
    observers = {}
    for name in gate.ap_OBSERVERS:
        row = {'status': 'completed_sample' if name.endswith('-google') else 'qualified_sample', 'exit_code': 0,
            'summary_sha256': ADMISSION_H, 'samples_sha256': ADMISSION_H, 'requested_seconds': 14400, 'elapsed_seconds': 14400,
            'samples': 480, 'cadence': {'first_seconds': 1, 'maximum_gap_seconds': 30, 'final_gap_seconds': 29}}
        if name == 'server':
            row.update(checks={k: True for k in gate.ap_SERVER_CHECKS}, metrics={'sql_checks': 48, 'unavailable_sql_checks': 0, 'websocket_connected_fraction': 1})
        elif name == 'publication':
            row.update(checks={k: True for k in ['identities_stable', 'no_findings', 'exact_download_sql_display_projection', 'resource_sampling_complete']},
                metrics={k: {'samples': 480, 'distinct_batches': 2, 'maximum_rows': 10} for k in ['observations', 'aircraft']})
        elif name == 'delivery':
            row.update(checks={k: True for k in ['identities_stable', 'no_findings', 'cadence_sufficient']}, metrics={'upserts': 2, 'verified_offsets': 2, 'pages': 480})
        else:
            checks = {k: True for k in gate.ap_BROWSER_CHECKS}
            if name == 'public-google':
                checks.update(public_http_scene_agreement=True, public_response_success=True)
            row.update(checks=checks, metrics={'scope': 'genuine_google_long_session_stable_profile', 'roots_requested': 2, 'roots_succeeded': 2,
                'natural_rotation_after_first_root_seconds': 9000, 'child_successes_after_three_hours': 10,
                'child_requests_after_three_hours': 10, 'post_three_hour_camera_action': True,
                'public_observations_max': 10 if name == 'public-google' else 0, 'public_aircraft_max': 10 if name == 'public-google' else 0})
        observers[name] = row
    proof['soak'] = {'schema': 1, 'launch_sha256': ADMISSION_H, 'candidate_receipt_sha256': ADMISSION_H,
        'started_at': '2026-11-06T01:00:00Z', 'ended_at': '2026-11-06T05:00:05Z', 'rehearsal_only': False,
        'observer_sources_unchanged': True, 'private_runners_unchanged': True, 'observer_source_hashes': [ADMISSION_H], 'private_runner_hashes': [ADMISSION_H],
        'observed_services': {name: {'image': ADMISSION_IMAGES[role], 'started_at': '2026-11-06T00:59:00Z', 'identity_sha256': gate.ap_digest(name.encode())} for name, role in gate.ap_SERVICES.items()},
        'unobserved_image_roles': ['tunnel'], 'observers': observers}
    return proof


class PackagingAdmissionTests(unittest.TestCase):
    def assert_both_gates_reject(self, name, mutation):
        snapshots=fixture({name:mutation})
        for qualifier in [gate.qualify,publisher.qualify]:
            with self.subTest(qualifier=qualifier.__module__),self.assertRaises(ValueError):qualifier(snapshots,gate.VERSION)

    def test_security_keeps_raw_high_exit_and_scoped_low_residual(self):
        for qualifier in [gate.qualify,publisher.qualify]:
            ready=qualifier(fixture(),gate.VERSION)
            proof=gate.strict_json(fixture()[ready['evidence']['security']['path']])
            self.assertEqual(proof['security']['scans']['image-backend']['exit_code'],2)
            self.assertEqual(proof['security']['residuals'][0]['severity'],'Low')
            self.assertNotIn('raw_high_critical_gate',proof)

    def test_every_observer_is_required_and_failed_observer_blocks(self):
        for observer in gate.ap_OBSERVERS:
            self.assert_both_gates_reject('full_pipeline_soak',lambda p,o=observer:p['soak']['observers'].pop(o))
            self.assert_both_gates_reject('full_pipeline_soak',lambda p,o=observer:p['soak']['observers'][o].update(exit_code=1))

    def test_actual_observer_counts_clocks_and_natural_google_renewal_required(self):
        for field,value in [('samples',True),('samples',480.0),('elapsed_seconds','14400'),('elapsed_seconds',14399.999),('requested_seconds',330)]:
            self.assert_both_gates_reject('full_pipeline_soak',lambda p,f=field,v=value:p['soak']['observers']['publication'].update({f:v}))
        for name in ['operator-google','public-google']:
            for field,value in [('natural_rotation_after_first_root_seconds',330),('roots_succeeded',2.0),('child_successes_after_three_hours',0),('post_three_hour_camera_action',False)]:
                self.assert_both_gates_reject('full_pipeline_soak',lambda p,n=name,f=field,v=value:p['soak']['observers'][n]['metrics'].update({f:v}))
        self.assert_both_gates_reject('full_pipeline_soak',lambda p:p['soak']['observers']['public-google']['checks'].update(public_http_scene_agreement=False))

    def test_original_findings_reference_membership_and_residuals_cannot_be_omitted(self):
        mutations=[
            lambda p:p.update(raw_high_critical_gate='PASS'),
            lambda p:p['security']['scans'].pop('native-curl'),
            lambda p:p['security']['scans']['image-backend'].update(exit_code=0),
            lambda p:p['security']['scans']['image-backend']['severity_counts'].update(High=True),
            lambda p:p['security']['scans']['image-backend'].update(raw_sha256='b'*64),
            lambda p:p['security']['dispositions'].pop(0),
            lambda p:p['security']['dispositions'][0].update(disposition='affected_unresolved'),
            lambda p:p['security'].update(residuals=[]),
            lambda p:p['security']['reference_verification'].update(status='PENDING'),
            lambda p:p['security']['final_refresh'].update(upstream_review_sha256='b'*64),
        ]
        for mutation in mutations:self.assert_both_gates_reject('security',mutation)

    def test_final_advisory_refresh_follows_full_soak_and_binds_same_candidate(self):
        self.assert_both_gates_reject('security',lambda p:(p['security'].update(reviewed_at='2026-11-06T00:00:00Z'),p['security']['final_refresh'].update(completed_at='2026-11-06T00:01:00Z')))
        def different_candidate(p):
            p['security']['candidate_receipt_sha256']='b'*64
            p['security']['reference_verification']['verified_sha256s'].append('b'*64)
        self.assert_both_gates_reject('security',different_candidate)

    def test_shared_backend_image_does_not_collapse_writer_reader_identity(self):
        self.assert_both_gates_reject('full_pipeline_soak',lambda p:p['soak']['observed_services']['reader'].update(identity_sha256=p['soak']['observed_services']['writer']['identity_sha256']))
        self.assert_both_gates_reject('full_pipeline_soak',lambda p:p['soak'].update(unobserved_image_roles=[]))
        self.assert_both_gates_reject('full_pipeline_soak',lambda p:p.update(execution='rebound',equivalence_sha256='a'*64))

    def test_strict_json_and_numeric_types_reject_nonfinite_or_coerced_claims(self):
        for raw in ['{"elapsed_seconds":NaN}','{"elapsed_seconds":Infinity}','{"ready":true,"ready":false}']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):gate.strict_json(raw)
        for fields in [{'samples':True},{'samples':400.0},{'failures':False},{'elapsed_seconds':'14400'}]:
            with self.subTest(fields=fields),self.assertRaises(ValueError):gate.qualify(fixture({'full_pipeline_soak':fields}),gate.VERSION)

    def test_export_requires_exact_regular_committed_git_blob(self):
        name='backend/app/main.py';data=b'authored source';oid=gate.sha1(b'blob 15\0'+data).hexdigest()
        for mode,kind,wanted in [('100644','blob',True),('100755','blob',True),('120000','blob',False),('160000','commit',False)]:
            responses=[b'a'*40+b'\n',(mode+' '+kind+' '+oid+'\t'+name).encode()+b'\0']
            with self.subTest(mode=mode),patch.object(gate.subprocess,'check_output',side_effect=responses):
                if wanted:gate.verify_git_tree(Path('.'),'a'*40,{name:data})
                else:
                    with self.assertRaises(ValueError):gate.verify_git_tree(Path('.'),'a'*40,{name:data})
    def test_explicit_complete_authored_ready_fixture_passes(self):
        self.assertTrue(gate.qualify(fixture(),gate.VERSION)['ready'])

    def test_trigger_identity_rejects_untrusted_events_refs_repos_actors(self):
        baseline=['push',gate.BRANCH,gate.REPOSITORY,'a'*40,'DankWoodsmoke']
        gate.identity(*baseline)
        for index,value in [(0,'pull_request'),(0,'pull_request_target'),(0,'workflow_dispatch'),(1,'refs/heads/main'),(1,'refs/heads/codex/verify-rc5-candidate13'),(2,'fork/repo'),(3,'HEAD'),(4,'someone-else')]:
            changed=baseline.copy();changed[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):gate.identity(*changed)

    def test_ready_false_missing_evidence_and_unknown_metadata_fail(self):
        for fields in [{'ready':False},{'prerelease':False},{'evidence':{}},{'private_extra':'forbidden field'},{'version':'0.2.0-rc.6'}]:
            with self.subTest(fields=fields),self.assertRaises(ValueError):gate.qualify(fixture(ready_override=fields),gate.VERSION)

    def test_changed_added_removed_and_unsafe_source_files_fail(self):
        for mode in ['changed','added','removed','escape']:
            data=fixture()
            if mode=='changed':data['frontend/src/App.tsx']+=b'changed'
            if mode=='added':data['frontend/src/New.tsx']=b'new'
            if mode=='removed':del data['frontend/src/App.tsx']
            if mode=='escape':data['../outside']=b'new'
            with self.subTest(mode=mode),self.assertRaises(ValueError):gate.qualify(data,gate.VERSION)

    def test_incomplete_real_time_or_security_and_media_gates_fail(self):
        cases=[('full_pipeline_soak',{'elapsed_seconds':14399.999}),('full_pipeline_soak',{'samples':1}),('full_pipeline_soak',{'failures':1}),
               ('full_pipeline_soak',{'genuine_clock':False}),('full_pipeline_soak',{'profiles_unchanged':False}),('security',{'raw_high_critical_gate':'FAIL'}),
               ('media_replay',{'qualified_engines':2}),('media_replay',{'implicit_generation_requests':1}),('backup_restore',{'execution':'rebound'}),
               ('google_public',{'qualified_images':{}})]
        for name,fields in cases:
            with self.subTest(name=name,fields=fields),self.assertRaises(ValueError):gate.qualify(fixture({name:fields}),gate.VERSION)

    def test_explicit_rebound_and_browser_limit_preserve_original_scope(self):
        self.assert_both_gates_reject('backup_restore', {'execution':'rebound','equivalence_sha256':'b'*64})
        self.assertTrue(gate.qualify(fixture({'media_replay':{'status':'QUALIFIED_WITH_LIMITATIONS'}}),gate.VERSION)['ready'])

    def test_zip_metadata_is_deterministic(self):
        values=fixture();rows=[{'path':p,'bytes':len(v),'sha256':gate.checksum(v)} for p,v in values.items()]
        self.assertEqual(export.candidate_archive(values,rows,gate.VERSION),export.candidate_archive(dict(reversed(list(values.items()))),list(reversed(rows)),gate.VERSION))


class PublisherDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.folder=Path(self.temporary.name)/'assets';self.folder.mkdir()
        self.snapshots=fixture();ready=json.loads(self.snapshots[gate.READY]);rows=[{'path':p,'bytes':len(v),'sha256':gate.checksum(v)} for p,v in self.snapshots.items()]
        archive=export.candidate_archive(self.snapshots,rows,gate.VERSION);filename='conflict-monitor-'+gate.VERSION+'-source.zip'
        notes=gate.release_notes(gate.VERSION,'a'*40,ready['limitations'])
        (self.folder/filename).write_bytes(archive);(self.folder/(filename+'.sha256')).write_text(gate.checksum(archive)+'  '+filename+'\n',newline='\n')
        verification={'schema':1,'status':'READY_FOR_PRERELEASE','repository':gate.REPOSITORY,'source_commit':'a'*40,'release_ref':gate.BRANCH,'tag':'v'+gate.VERSION,
            'archive':{'name':filename,'bytes':len(archive),'sha256':gate.checksum(archive)},'ready_receipt_sha256':gate.checksum(self.snapshots[gate.READY]),'source_manifest_sha256':ready['source_manifest_sha256'],
            **{key:ready[key] for key in ['runtime_source_sha256','images','evidence','limitations']},'release_notes_sha256':gate.checksum(notes),'ci':gate.ci_identity('123456','1')}
        raw=gate.canonical(verification);(self.folder/'verification.json').write_bytes(raw);(self.folder/'RELEASE_NOTES.txt').write_bytes(notes)
        self.env={'GITHUB_EVENT_NAME':'push','GITHUB_REF':gate.BRANCH,'GITHUB_REPOSITORY':gate.REPOSITORY,'GITHUB_SHA':'a'*40,'GITHUB_ACTOR':'DankWoodsmoke',
            'EXPECTED_ARCHIVE_SHA256':gate.checksum(archive),'EXPECTED_VERIFICATION_SHA256':gate.checksum(raw),'EXPECTED_TAG':'v'+gate.VERSION,'GH_TOKEN':'offline-test-placeholder','GITHUB_RUN_ID':'123456','GITHUB_RUN_ATTEMPT':'1','PUBLISHER_RECEIPT':str(self.folder.parent/'publication-receipt.json')}

    def tearDown(self):self.temporary.cleanup()

    def test_bound_data_assets_pass_without_execution(self):
        self.assertEqual(publisher.validate(self.folder,self.env)['source_commit'],'a'*40)

    def test_wrong_commit_corrupt_archive_extra_executable_and_checksum_fail(self):
        original=self.env.copy()
        for key,value in [('GITHUB_SHA','b'*40),('EXPECTED_ARCHIVE_SHA256','b'*64),('EXPECTED_VERIFICATION_SHA256','b'*64),('EXPECTED_TAG','v0.2.0-rc.6'),('GITHUB_RUN_ID','654321'),('GITHUB_RUN_ATTEMPT','2')]:
            with self.subTest(key=key),self.assertRaises(ValueError):publisher.validate(self.folder,{**original,key:value})
        (self.folder/'unexpected.py').write_text('raise RuntimeError()')
        with self.assertRaises(ValueError):publisher.validate(self.folder,original)
        (self.folder/'unexpected.py').unlink()
        (self.folder/('conflict-monitor-'+gate.VERSION+'-source.zip.sha256')).write_text('changed')
        with self.assertRaises(ValueError):publisher.validate(self.folder,original)

    def test_bound_archive_still_rejects_mode_or_timestamp_changes(self):
        filename='conflict-monitor-'+gate.VERSION+'-source.zip';archive=self.folder/filename;baseline=archive.read_bytes()
        for field,value in [('external_attr',0o040755<<16),('external_attr',0o100755<<16),('date_time',(2021,1,1,0,0,0)),('create_system',0)]:
            changed=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(baseline)) as source,zipfile.ZipFile(changed,'w') as target:
                for index,entry in enumerate(source.infolist()):
                    item=copy.copy(entry)
                    if index==0:setattr(item,field,value)
                    target.writestr(item,source.read(entry.filename))
            data=changed.getvalue();archive.write_bytes(data)
            self.folder.joinpath(filename+'.sha256').write_bytes((gate.checksum(data)+'  '+filename+'\n').encode())
            verification=json.loads(self.folder.joinpath('verification.json').read_bytes())
            verification['archive'].update(bytes=len(data),sha256=gate.checksum(data));raw=gate.canonical(verification);self.folder.joinpath('verification.json').write_bytes(raw)
            env={**self.env,'EXPECTED_ARCHIVE_SHA256':gate.checksum(data),'EXPECTED_VERIFICATION_SHA256':gate.checksum(raw)}
            with self.subTest(field=field,value=value),self.assertRaisesRegex(ValueError,'mode or deterministic metadata'):publisher.validate(self.folder,env)

    def test_existing_tag_or_api_error_prevents_every_write(self):
        with patch.object(publisher,'api',side_effect=ValueError('Already exists')),patch.object(publisher.subprocess,'run') as run:
            with self.assertRaises(ValueError):publisher.publish(self.folder,self.env)
            run.assert_not_called()
        receipt=json.loads(Path(self.env['PUBLISHER_RECEIPT']).read_bytes())
        self.assertEqual(receipt['status'],'INCOMPLETE_OR_FAILED')
        self.assertEqual(receipt['failed_stage'],'absence_and_head')

    def simulated_publication(self,*,stale_at=None,corrupt_draft=False,bad_asset=None,omit_digest=False):
        remote={'draft':None,'assets':{},'heads':0,'commands':[]}
        def api(path,token,expected=200):
            if expected==404:return None
            if '/heads/' in path:
                remote['heads']+=1
                return {'object':{'type':'commit','sha':'b'*40 if remote['heads']==stale_at else 'a'*40}}
            if '/git/ref/tags/' in path:return {'object':{'type':'commit','sha':'a'*40}}
            assets=[{'id':200+index,'name':name,'size':len(data),'digest':'sha256:'+gate.checksum(data),'state':'uploaded','browser_download_url':'https://example.invalid/ignored'} for index,(name,data) in enumerate(remote['assets'].items())]
            if omit_digest:
                for asset in assets:asset.pop('digest')
            if bad_asset=='size':assets[0]['size']+=1
            if bad_asset=='digest':assets[0]['digest']='sha256:'+'b'*64
            return {'id':123,'draft':remote['draft'],'prerelease':True,'tag_name':self.env['EXPECTED_TAG'],'assets':assets}
        def run(command,**kwargs):
            remote['commands'].append(command[:])
            if command[:2]==['gh','api']:
                return SimpleNamespace(returncode=0,stdout=json.dumps({'ref':'refs/tags/'+self.env['EXPECTED_TAG'],'object':{'type':'commit','sha':'a'*40}}).encode())
            if command[2]=='create':
                self.assertIn('--draft',command);remote['draft']=True
                for path in list(self.folder.iterdir()):
                    if path.name!='RELEASE_NOTES.txt':remote['assets'][path.name]=path.read_bytes()
            elif command[2]=='download':
                target=Path(command[command.index('--dir')+1])
                names=[command[i+1] for i,arg in enumerate(command) if arg=='--pattern']
                for name in names:target.joinpath(name).write_bytes(b'bad draft data' if corrupt_draft and remote['draft'] else remote['assets'][name])
            elif command[2]=='edit':remote['draft']=False
            elif command[2]=='upload':
                path=Path(command[4]);remote['assets'][path.name]=path.read_bytes()
            return SimpleNamespace(returncode=0,stdout=b'')
        with patch.object(publisher,'api',side_effect=api),patch.object(publisher.subprocess,'run',side_effect=run):
            if stale_at or corrupt_draft or bad_asset:
                with self.assertRaises(ValueError):publisher.publish(self.folder,self.env)
            else:
                with redirect_stdout(io.StringIO()):publisher.publish(self.folder,self.env)
        return remote

    def test_draft_assets_download_verify_before_promotion_and_durable_receipt(self):
        remote=self.simulated_publication()
        operations=[c[2] for c in remote['commands'] if c[:2]==['gh','release']]
        self.assertEqual(operations,['create','download','upload','download','edit','download'])
        self.assertIs(remote['draft'],False);self.assertEqual(remote['heads'],2)
        public=json.loads(remote['assets']['publication-receipt.json'])
        final=json.loads(Path(self.env['PUBLISHER_RECEIPT']).read_bytes())
        self.assertEqual(public['status'],'DRAFT_SOURCE_ASSETS_DOWNLOADED_VERIFIED')
        self.assertIs(public['publication_not_yet_performed'],True)
        self.assertEqual(final['status'],'PUBLISHED_AND_DOWNLOADED_BYTES_VERIFIED')
        self.assertEqual(final['stage'],'complete')
        self.assertEqual(final['durable_receipt_sha256'],gate.checksum(remote['assets']['publication-receipt.json']))
        self.assertEqual(final['created_tag'],{'ref':'refs/tags/'+self.env['EXPECTED_TAG'],'object_type':'commit','commit':'a'*40})
        phases=final['remote_observations']
        self.assertEqual([p['phase'] for p in phases],['draft_source_assets','durable_receipt_while_draft','before_promotion','published_assets'])
        self.assertTrue(all(p['actual_tag_commit']=='a'*40 and p['release_id']==123 and p['tag_matches'] for p in phases))
        self.assertEqual(len(phases[-1]['downloads']),4)
        self.assertTrue(all(a['asset_id']>=200 and a['api_bytes']==a['expected_bytes'] and a['api_sha256']==a['local_sha256'] for p in phases for a in p['assets']))
        self.assertTrue(all(d['matches'] and d['local_sha256']==d['downloaded_sha256'] for p in phases for d in p['downloads']))
        self.assertEqual(len(public['remote_observations']),1)
        self.assertEqual(len(public['remote_observations'][0]['assets']),3)
        self.assertNotIn('publication-receipt.json',[a['name'] for a in public['remote_observations'][0]['assets']])
        self.assertNotIn('example.invalid',gate.canonical(final).decode())
        self.assertNotIn(self.env['GH_TOKEN'],gate.canonical(final).decode())

    def test_wrong_remote_asset_size_and_digest_keep_draft_and_observed_failure(self):
        for issue in ['size','digest']:
            with self.subTest(issue=issue):
                report=Path(self.env['PUBLISHER_RECEIPT'])
                if report.exists():report.unlink()
                remote=self.simulated_publication(bad_asset=issue)
                self.assertIs(remote['draft'],True)
                self.assertFalse(any(c[2]=='edit' for c in remote['commands'] if c[:2]==['gh','release']))
                partial=gate.strict_json(report.read_bytes())
                self.assertEqual(partial['failed_stage'],'verify_draft_downloads')
                actual=partial['remote_observations'][0]['assets'][0]
                self.assertGreaterEqual(actual['asset_id'],200)
                if issue=='size':self.assertNotEqual(actual['api_bytes'],actual['expected_bytes'])
                else:self.assertNotEqual(actual['api_sha256'],actual['local_sha256'])

    def test_optional_api_digest_absence_still_requires_actual_download_hashes(self):
        self.simulated_publication(omit_digest=True)
        final=gate.strict_json(Path(self.env['PUBLISHER_RECEIPT']).read_bytes())
        self.assertTrue(all(not a['api_digest_present'] and a['api_sha256'] is None for p in final['remote_observations'] for a in p['assets']))
        self.assertTrue(all(d['local_sha256']==d['downloaded_sha256'] and d['matches'] for p in final['remote_observations'] for d in p['downloads']))

    def test_changed_head_before_any_write_stops_publication(self):
        remote=self.simulated_publication(stale_at=1)
        self.assertEqual(remote['commands'],[])

    def test_changed_head_after_draft_leaves_it_unpublished(self):
        remote=self.simulated_publication(stale_at=2)
        self.assertIs(remote['draft'],True)
        self.assertFalse(any(c[2]=='edit' for c in remote['commands'] if c[:2]==['gh','release']))

    def test_corrupted_draft_download_can_never_be_promoted(self):
        remote=self.simulated_publication(corrupt_draft=True)
        self.assertIs(remote['draft'],True)
        self.assertFalse(any(c[2]=='edit' for c in remote['commands'] if c[:2]==['gh','release']))

    def test_api_401_is_never_mistaken_for_absence(self):
        error=urllib.error.HTTPError('https://api.github.com/',401,'denied',{},None)
        with patch.object(publisher.urllib.request,'build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaisesRegex(ValueError,'HTTP 401'):publisher.api('repos/fixture/repo','offline-test-placeholder',404)


class WorkflowBoundaryTests(unittest.TestCase):
    def test_inline_and_packager_pure_admission_policy_match_exactly(self):
        packager=(FOLDER/'prepare_release_publication.py').read_text(encoding='utf8')
        expected=packager[packager.index('REPOSITORY='):packager.index('\ndef verify_git_tree(')].strip()
        inline=INLINE_SOURCE
        actual=inline.split('# BEGIN REVIEWED PURE POLICY\n',1)[1].split('# END REVIEWED PURE POLICY',1)[0].strip()
        self.assertEqual(actual,expected)

    def test_all_verification_dependencies_and_only_publisher_write_token(self):
        workflow=yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf8'))
        jobs=workflow['jobs'];self.assertEqual(set(jobs),{'frontend','backend','container_profile','release_package','publish_qualified_prerelease'})
        self.assertEqual(jobs['release_package']['permissions'],{'contents':'read'})
        publish=jobs['publish_qualified_prerelease'];self.assertEqual(publish['permissions'],{'contents':'write'})
        self.assertEqual(set(publish['needs']),{'frontend','backend','container_profile','release_package'})
        self.assertTrue(all("github.event_name == 'push'" in jobs[name]['if'] for name in ['release_package','publish_qualified_prerelease']))
        self.assertEqual(len(publish['steps']),4);self.assertTrue(publish['steps'][1]['uses'].startswith('actions/download-artifact@9000827'))
        self.assertEqual(publish['steps'][3]['if'],'always()');self.assertEqual(publish['steps'][3]['with']['retention-days'],90)
        step=publish['steps'][2];self.assertEqual(step['env']['GH_TOKEN'],'${{ github.token }}')
        inline=step['run'].split("python3 - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
        self.assertEqual(inline.strip(),INLINE_SOURCE.strip())
        self.assertNotIn('checkout',str(publish['steps']));self.assertNotIn('pull_request_target',str(workflow))

    def test_empty_or_multiple_artifact_ids_fail_before_download(self):
        workflow=yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf8'))
        step=workflow['jobs']['publish_qualified_prerelease']['steps'][0]
        code=step['run'].split("python3 - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
        for value in ['', '1,2', 'latest', '0', '12']:
            with self.subTest(value=value),patch.dict('os.environ',{'EXPECTED_ARTIFACT_ID':value,'EXPECTED_ARCHIVE_SHA256':'a'*64,'EXPECTED_VERIFICATION_SHA256':'b'*64}):
                if value=='12':exec(code,{})
                else:
                    with self.assertRaises(AssertionError):exec(code,{})


if __name__=='__main__':unittest.main()
