"""Altered-proof regressions against both independently executed policy copies."""
import copy
import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('release_semantic_test_support',P/'test_release_publication.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)


def set_path(proof,path,value):
    node=proof
    for key in path[:-1]:node=node[key]
    node[path[-1]]=copy.deepcopy(value)


class SemanticProofTests(unittest.TestCase):
    def reject(self,name,path,value):
        for module in [support.gate,support.publisher]:
            with self.subTest(gate=module.__name__,proof=name,path=path,value=repr(value)[:80]):
                snapshots=support.fixture({name:lambda proof:set_path(proof,path,value)})
                with self.assertRaises(ValueError):module.qualify(snapshots,module.VERSION)

    def test_complete_authored_scoped_results_pass_both_copies(self):
        for module in [support.gate,support.publisher]:self.assertTrue(module.qualify(support.fixture(),module.VERSION)['ready'])

    def test_exact_historical_media_candidate_labels_only(self):
        for module in [support.gate,support.publisher]:
            for label in ['historical artifact replayed freshly on exact candidate16','historical artifact replayed freshly on exact candidate17','historical artifact replayed freshly on exact candidate18']:
                snapshots=support.fixture({'media_replay':lambda proof:set_path(proof,['artifact_provenance','execution'],label)})
                self.assertTrue(module.qualify(snapshots,module.VERSION)['ready'])
        for label in ['historical artifact replayed freshly on exact candidate19','fresh generation on candidate17','historical artifact replayed freshly on exact candidate170','',True,None]:
            self.reject('media_replay',['artifact_provenance','execution'],label)

    def test_drafts_and_extra_failure_statuses_cannot_be_admitted(self):
        for name in ['google_operator','google_public','media_replay','backup_restore']:
            for status in ['DRAFT_PENDING_ROOT_REVIEW','INCOMPLETE','failed',None,True]:self.reject(name,['status'],status)
            self.reject(name,['execution'],'rebound')

    def test_google_exact_engine_viewport_and_finite_raster_are_required(self):
        for name in ['google_operator','google_public']:
            cases=support.scoped.scoped_fixture(name)['cases']
            mutations=[(['cases'],[]),(['cases'],cases[:-1]),(['cases'],[cases[0]]*len(cases)),(['cases_passed'],0),(['cases_failed'],1),
                (['cases',0,'browser'],'unknown'),(['cases',0,'version'],'1.0'),(['cases',0,'viewport','width'],True),
                (['cases',0,'viewport','width'],321),(['cases',0,'status'],'failed'),(['cases',0,'checks'],[]),
                (['cases',0,'page_errors'],1),(['cases',0,'composed_earth_raster','samples'],15),
                (['cases',0,'composed_earth_raster','bright_fraction'],.249),(['cases',0,'composed_earth_raster','stddev'],9.99),
                (['cases',0,'composed_earth_raster','color_bins'],15),(['cases',0,'composed_earth_raster','mean'],'100'),
                (['cases',1,'screenshot_sha256'],cases[0]['screenshot_sha256']),(['browser_tool_version'],'1.64.1'),
                (['limitations'],['scope omitted']*3),(['unobserved_image_roles'],[]),(['ended_at'],'2026-11-05T00:00:00Z')]
            for path,value in mutations:self.reject(name,path,value)
        self.reject('google_operator',['cases',0,'google_provider_end_state'],'failed')
        for key in ['forbidden_api_requests','media_requests','application_nonread_requests','websockets']:self.reject('google_public',['cases',0,'network',key],1)
        for key in ['google_roots_ok','google_tiles_ok','publication_observation_requests','publication_aircraft_requests']:self.reject('google_public',['cases',0,'network',key],0)
        self.reject('google_public',['cases',0,'exact_downloads','aircraft','status'],503)
        self.reject('google_public',['cases',0,'source_counts','aircraft'],0)
        self.reject('google_public',['cases',0,'source_counts','aircraft'],5000)
        self.reject('google_public',['cases',0,'source_counts','observations'],2001)

    def test_original_google_failure_and_exact_independent_log_exception_survive(self):
        for path,value in [(['original_status'],'PASS'),(['original_receipt_modified'],True),(['original_failure'],'other'),
            (['independent_addendum_status'],'PASS'),(['independent_addendum_sha256'],None),(['unchanged_source_files'],544),
            (['unchanged_browser_input_files'],0),(['unchanged_executed_helpers'],3),(['added_files'],1),(['removed_files'],1),
            (['generated_output','path'],'chromium.exe'),(['generated_output','contents_exported'],True),
            (['generated_output','bytes'],3073),(['generated_output','utf8_diagnostic_lines'],False)]:
            self.reject('google_operator',['binding_review']+path,value)
        self.reject('google_public',['binding_review','generated_output','before_sha256'],'d'*64)

    def test_both_actual_raster_soaks_mandatory_and_rehearsal_rejected(self):
        for name in ['google_operator','google_public']:
            for path,value in [(['status'],'running'),(['execution'],'rebound'),(['requested_seconds'],330),(['elapsed_seconds'],330),
                (['samples'],11),(['raster_samples'],479),(['findings'],1),(['cadence','maximum_gap_seconds'],91),
                (['thresholds','stddev'],1),(['minima','color_bins'],40),(['minima','stddev'],9),(['checks','sources_unchanged'],False),
                (['checks','all_tabs_observed'],False),(['gate'],'google_other'),(['artifact_profile'],'wrong'),(['browser'],'webkit'),(['observed_services','writer','image'],'sha256:'+'f'*64),
                (['candidate_receipt_sha256'],'f'*64),(['limitations'],[]),(['ended_at'],'2026-11-06T01:05:30Z')]:
                self.reject(name,['supplemental_raster']+path,value)
            for module in [support.gate,support.publisher]:
                snapshots=support.fixture({name:lambda p:p.pop('supplemental_raster')})
                with self.assertRaises(ValueError):module.qualify(snapshots,module.VERSION)
        self.reject('google_public',['supplemental_raster','observed_services','writer','started_at'],'2026-11-06T00:58:00Z')
        # Valid standalone supplemental clocks that finish after security review must still block publication.
        self.reject('google_public',['supplemental_raster','ended_at'],'2026-11-06T05:03:00Z')
        for module in [support.gate,support.publisher]:
            snapshots=support.fixture({'google_public':lambda p:p['supplemental_raster'].update(started_at='2026-11-06T01:03:00Z',ended_at='2026-11-06T05:03:00Z')})
            with self.assertRaises(ValueError):module.qualify(snapshots,module.VERSION)

    def test_independent_raster_profiles_cannot_be_reused_and_refresh_cannot_straddle_run(self):
        for module in [support.gate,support.publisher]:
            operator=support.scoped.scoped_fixture('google_operator')['supplemental_raster']
            for mutate in [lambda p:p.update(supplemental_raster=copy.deepcopy(operator)),
                           lambda p:p['supplemental_raster'].update(summary_sha256=operator['summary_sha256'],source_receipt_sha256=operator['source_receipt_sha256'],samples_sha256=operator['samples_sha256'])]:
                snapshots=support.fixture({'google_public':mutate})
                with self.assertRaises(ValueError):module.qualify(snapshots,module.VERSION)
        self.reject('security',['security','final_refresh','started_at'],'2026-11-06T04:59:59Z')
        self.reject('security',['security','final_refresh','started_at'],'2026-11-06T05:03:00Z')

    def test_media_raw_failures_and_actual_caption_recovery_are_required(self):
        paths=[(['browser_cases'],[]),(['qualified_engines'],True),(['raw_engines_passed'],3),(['implicit_generation_requests'],1),
            (['provider_generation_calls'],1),(['database_connected'],True),(['owned_cleanup_verified'],False),(['bound_inputs_unchanged'],False),
            (['api_execution_scope','entrypoint_overridden'],False),(['api_execution_scope','production_fastapi_routes_executed'],True),
            (['browser_cases',0,'native_decoded_pixels','mean_absolute_rgb_error'],3),(['browser_cases',0,'native_decoded_pixels','reference_rgb_standard_deviation'],0),
            (['browser_cases',0,'native_decoded_pixels','mean_limit'],20),(['browser_cases',0,'decoded_frames'],0),
            (['browser_cases',1,'status'],'passed'),(['browser_cases',1,'paused_caption_restore','status'],'PASS'),
            (['browser_cases',1,'caption_user_resume','status'],'FAIL'),(['browser_cases',1,'caption_user_resume','guidance_visible_before'],False),
            (['browser_cases',1,'caption_user_resume','to_time'],3.81),(['browser_cases',1,'engine_limitations'],[]),
            (['browser_cases',1,'captions','paused_render_restore'],True),(['browser_cases',0,'captions','rendered_caption_on_off_pixels'],False),
            (['browser_cases',0,'captions','exact_transcript'],False),(['browser_cases',2,'native_decoded_pixels','unadjusted_status'],'PASS'),
            (['browser_cases',2,'native_decoded_pixels','range_normalized_content','p99_absolute_rgb_error'],13),
            (['browser_cases',2,'native_decoded_pixels','range_normalized_content','transform'],'fitted gain'),
            (['browser_cases',2,'native_decoded_pixels','range_normalized_content','p99_limit'],50),(['browser_cases',2,'engine_limitations'],[]),
            (['browser_cases',0,'generation_posts'],1),(['browser_cases',1,'blocked_external'],1),(['browser_cases',0,'page_errors'],1),
            (['browser_cases',0,'caption_metadata','cue_count'],0),(['browser_cases',0,'caption_metadata','timings',1,'start'],12),
            (['browser_cases',0,'captions','timings',0,'start'],False),(['browser_cases',0,'frame_callback','samples',1,'media_time'],170),(['browser_cases',0,'caption_metadata','exact_cue_text'],False),(['browser_cases',0,'native_user_pause_resume','after'],1),
            (['browser_cases',1,'frame_callback','status'],'presented'),(['browser_cases',1,'callback_measurement_scope'],'presented_advancing_callbacks'),(['browser_cases',1,'callback_cause'],'browser bug'),(['browser_cases',1,'frame_callback','samples',0,'media_time'],2),(['browser_cases',2,'native_decoded_pixels','pixel_buffers_retained'],False),(['limitations'],['missing']*8)]
        for path,value in paths:self.reject('media_replay',path,value)
        self.reject('media_replay',['status'],'PASS')

    def test_independent_color_control_is_bounded_real_scope_and_not_fitted(self):
        for path,value in [(['cases'],[]),(['binding_checks','exit_code'],1),(['binding_checks','inputs_unchanged'],False),
            (['binding_checks','owned_browser_job_closed'],False),(['scope'],'unknown'),(['playwright_version'],'1.64.1'),
            (['cases',0,'status'],'PASS'),(['cases',0,'raw_interior','mae'],9),(['cases',0,'fixed_studio_to_full_interior','p99'],2),
            (['cases',1,'fixed_studio_to_full_interior','mae'],3),(['cases',1,'raw_interior','mae'],1),(['cases',1,'raw_interior','p99'],2),
            (['cases',1,'fixed_studio_to_full_interior','samples'],0),(['cases',1,'browser_version'],'1'),(['cases',1,'reference_sha256'],'e'*64),(['cases',1,'actual_sample','canvas_width'],720)]:
            # Either error metric alone can still fail its paired bound; mutate both for the two negative controls below.
            if path in [['cases',0,'fixed_studio_to_full_interior','p99'],['cases',1,'raw_interior','mae'],['cases',1,'raw_interior','p99']]:continue
            self.reject('media_replay',['independent_color_control']+path,value)
        for module in [support.gate,support.publisher]:
            for engine_index,key in [(0,'fixed_studio_to_full_interior'),(1,'raw_interior')]:
                snapshots=support.fixture({'media_replay':lambda p,i=engine_index,k=key:p['independent_color_control']['cases'][i][k].update(mae=1,p99=2)})
                with self.assertRaises(ValueError):module.qualify(snapshots,module.VERSION)
            snapshots=support.fixture({'media_replay':lambda p:p['independent_color_control'].update(video_sha256=p['artifact_provenance']['video_sha256'])})
            with self.assertRaises(ValueError):module.qualify(snapshots,module.VERSION)

    def test_replay_audit_does_not_hide_denied_local_reads_or_unknown_routes(self):
        self.reject('media_replay',['api_audit','unknown_reads'],0)
        self.reject('media_replay',['api_audit','unknown_read_routes','<other>'],{'GET 200':1})
        self.reject('media_replay',['api_audit','unknown_read_routes','/ws/events'],{'GET 200':19})

    def test_every_restore_check_and_scope_is_required(self):
        for key in support.gate.ev_RESTORE_CHECKS:self.reject('backup_restore',['backup_restore','checks',key],False)
        for path,value in [(['checks'],{}),(['cleanup_verified'],False),(['elapsed_seconds'],52),(['snapshot_seconds'],241),
            (['snapshot_lifetime_cap_seconds'],300),(['provider_requests'],1),(['main_service_mutations'],1),(['snapshot_table_count'],0),
            (['sequence_count'],0),(['executed_restore_image_roles'],['backend','database','tunnel']),(['archive','rows_bound_to_same_exported_snapshot'],False),
            (['archive','ownership_acl_included'],True),(['archive','bytes'],0),(['cached_public_packets','aircraft','sql_download_exact'],False),
            (['cached_public_packets','aircraft','display_status'],'stale'),(['cached_public_packets','aircraft','displayed_rows'],5001),
            (['limits'],['claims removed']*4),(['candidate_receipt_sha256'],'b'*64)]:self.reject('backup_restore',['backup_restore']+path,value)

    def test_nonfinite_boolean_or_string_metrics_and_extra_nested_fields_rejected(self):
        for name,path in [('google_public',['cases',0,'composed_earth_raster','stddev']),('google_operator',['supplemental_raster','elapsed_seconds']),('media_replay',['browser_cases',0,'native_decoded_pixels','mean_absolute_rgb_error']),('backup_restore',['backup_restore','snapshot_seconds'])]:
            for value in [True,'12',None,-1,float('inf'),float('nan')]:
                # JSON canonicalization itself rejects nonfinite values before either policy executes.
                if isinstance(value,float) and not support.gate.math.isfinite(value):
                    with self.assertRaises(ValueError):support.fixture({name:lambda p:set_path(p,path,value)})
                else:self.reject(name,path,value)
        for name,path in [('google_public',['cases',0]),('google_operator',['binding_review']),('media_replay',['browser_cases',0,'native_decoded_pixels']),('backup_restore',['backup_restore','checks'])]:
            value=support.scoped.scoped_fixture(name)
            node=value
            for key in path:node=node[key]
            node['failed']=True;self.reject(name,path,node)


class DirectGoogleBindingTests(unittest.TestCase):
    def direct(self):
        return {'mode':'direct_immutable_browser_binding','status':'passed','binding_receipt_sha256':'1'*64,'independent_review_sha256':'2'*64,'independent_review_status':'PASS_DIRECT_IMMUTABLE_BROWSER_BINDING','immutable_inventory_before_sha256':'3'*64,'immutable_inventory_after_sha256':'3'*64,'unchanged_browser_input_files':1030,'unchanged_source_files':545,'unchanged_executed_helpers':4,'added_files':0,'removed_files':0,'checks':{name:True for name in 'immutable_files_and_membership_equal original_frozen_source_unchanged current_source_unchanged private_helpers_unchanged five_services_unchanged all_cases_passed owned_browser_jobs_closed generated_output_retained_privately'.split()},'generated_output':{'path':'chromium_headless_shell-1254/chrome-headless-shell-win64/debug.log','before':{'sha256':'4'*64,'bytes':123,'utf8_diagnostic_lines':2},'after':{'sha256':'5'*64,'bytes':234,'utf8_diagnostic_lines':4},'contents_exported':False}}
    def snapshots(self,review,candidate='9a4e12bb8d52cba94f38174bb8291c51a89a3d7fb5697d519fa5974167883649'):
        def bind(proof):
            def visit(value):
                if type(value)is dict:
                    for key,item in value.items():
                        if key=='candidate_receipt_sha256':value[key]=candidate
                        else:visit(item)
                elif type(value)is list:
                    for item in value:visit(item)
            visit(proof)
            if 'security'in proof and type(candidate)is str and len(candidate)==64:
                proof['security']['verified_evidence_sha256s'].append(candidate)
                proof['security']['reference_verification']['verified_sha256s'].append(candidate)
            if proof.get('gate')in {'google_operator','google_public'}:proof['binding_review']=copy.deepcopy(review)
        return support.fixture({name:bind for name in support.gate.GATES})
    def test_direct_binding_count_is_exactly_bound_to_reviewed_candidate(self):
        for module in [support.gate,support.publisher]:
            for candidate,count in [('9a4e12bb8d52cba94f38174bb8291c51a89a3d7fb5697d519fa5974167883649',545),('65b92f66754f0e1c20e5df66082361421074e5d57742ecc2e2d791388aef41cf',556)]:
                review=self.direct();review['unchanged_source_files']=count
                self.assertTrue(module.qualify(self.snapshots(review,candidate),module.VERSION)['ready'])
                for wrong in [True,545 if count==556 else 556,544,555,557,0]:
                    review['unchanged_source_files']=wrong
                    with self.subTest(candidate=candidate,count=wrong),self.assertRaises(ValueError):module.qualify(self.snapshots(review,candidate),module.VERSION)
            for candidate in ['a'*64,'',None,True]:
                with self.subTest(candidate=candidate),self.assertRaises(ValueError):module.qualify(self.snapshots(self.direct(),candidate),module.VERSION)
    def test_direct_binding_accepts_actual_bounds_without_inventing_legacy_failure_or_append(self):
        for module in [support.gate,support.publisher]:
            for changed in [True,False]:
                review=self.direct()
                if not changed:review['generated_output']['after']=copy.deepcopy(review['generated_output']['before'])
                self.assertTrue(module.qualify(self.snapshots(review),module.VERSION)['ready'])
    def test_direct_binding_requires_all_immutable_membership_source_and_cleanup_proofs(self):
        mutations=[(['mode'],'other'),(['status'],'failed'),(['independent_review_status'],'PENDING'),(['independent_review_sha256'],'1'*64),(['immutable_inventory_after_sha256'],'6'*64),(['unchanged_browser_input_files'],1029),(['unchanged_source_files'],544),(['unchanged_executed_helpers'],3),(['added_files'],1),(['removed_files'],1),(['generated_output','path'],'chromium.exe'),(['generated_output','contents_exported'],True),(['generated_output','after','bytes'],2000001),(['generated_output','after','bytes'],True),(['generated_output','after','utf8_diagnostic_lines'],235),(['generated_output','after','utf8_diagnostic_lines'],False),(['generated_output','after','sha256'],'bad')]
        mutations += [(['checks',name],False) for name in self.direct()['checks']]
        for module in [support.gate,support.publisher]:
            for path,value in mutations:
                with self.subTest(module=module.__name__,path=path,value=value):
                    review=self.direct();set_path(review,path,value)
                    with self.assertRaises(ValueError):module.qualify(self.snapshots(review),module.VERSION)
    def test_direct_binding_rejects_missing_extra_and_conflicting_measurements(self):
        for module in [support.gate,support.publisher]:
            for name in list(self.direct()):
                review=self.direct();review.pop(name)
                with self.subTest(module=module.__name__,missing=name),self.assertRaises(ValueError):module.qualify(self.snapshots(review),module.VERSION)
            review=self.direct();review['unexpected']=True
            with self.assertRaises(ValueError):module.qualify(self.snapshots(review),module.VERSION)
            review=self.direct();review['generated_output']['after']['sha256']=review['generated_output']['before']['sha256']
            with self.assertRaises(ValueError):module.qualify(self.snapshots(review),module.VERSION)
            review=self.direct();review['generated_output']['after']={'sha256':'5'*64,'bytes':0,'utf8_diagnostic_lines':0}
            with self.assertRaises(ValueError):module.qualify(self.snapshots(review),module.VERSION)
    def test_direct_binding_still_requires_both_raster_soaks_and_matching_matrix_review(self):
        for module in [support.gate,support.publisher]:
            snapshots=self.snapshots(self.direct())
            # Existing cross-proof and raster rejection tests continue to apply to both admitted variants.
            for name in ['google_operator','google_public']:
                mutated=support.fixture({name:lambda proof:proof.update(binding_review=self.direct())})
                with self.assertRaises(ValueError):module.qualify(mutated,module.VERSION)
                def without_raster(proof):
                    proof['binding_review']=self.direct()
                    if proof['gate']==name:proof.pop('supplemental_raster')
                missing=support.fixture({key:without_raster for key in ['google_operator','google_public']})
                with self.assertRaises(ValueError):module.qualify(missing,module.VERSION)


if __name__=='__main__':unittest.main()
