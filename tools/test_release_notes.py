"""Authored offline data only; no release, network or ready evidence is produced."""
from pathlib import Path
import ast,importlib.util,json,unittest

spec=importlib.util.spec_from_file_location('notes_test_support',Path(__file__).with_name('test_release_publication.py'))
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)


class ReleaseNotesTests(unittest.TestCase):
    def setUp(self):
        self.data=support.PublisherDataTests();self.data.setUp()
    def tearDown(self):self.data.tearDown()
    def rebind_notes_hash(self,raw):
        folder=self.data.folder;(folder/'RELEASE_NOTES.txt').write_bytes(raw)
        verification=json.loads((folder/'verification.json').read_bytes());verification['release_notes_sha256']=support.gate.checksum(raw)
        body=support.gate.canonical(verification);(folder/'verification.json').write_bytes(body)
        self.data.env['EXPECTED_VERIFICATION_SHA256']=support.gate.checksum(body)
    def test_both_note_generators_are_identical_and_preserve_literal_limitations(self):
        limits=['Residual Medium findings remain.', 'Unicode scope: emulation ≠ physical-device testing.']
        left=support.gate.release_notes(support.gate.VERSION,'a'*40,limits)
        self.assertEqual(left,support.publisher.release_notes(support.gate.VERSION,'a'*40,limits))
        self.assertTrue(left.startswith(b'RC.5 brings Google Earth imagery'))
        self.assertTrue(left.endswith(('\n'.join('- '+x for x in limits)+'\n').encode('utf-8')))
        self.assertIn(b'Source commit: '+b'a'*40,left)
        def definition(raw):return next(ast.dump(n,include_attributes=False) for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='release_notes')
        self.assertEqual(definition(Path(support.gate.__file__).read_text(encoding='utf-8')),definition(support.INLINE_SOURCE))
        maximum=support.gate.release_notes(support.gate.VERSION,'a'*40,['x'*600]*20)
        self.assertLessEqual(len(maximum),16_000)
    def test_correct_notes_still_validate_the_same_four_asset_handoff(self):
        result=support.publisher.validate(self.data.folder,self.data.env)
        self.assertEqual(len(list(self.data.folder.iterdir())),4)
        self.assertEqual(result['release_notes_sha256'],support.gate.checksum((self.data.folder/'RELEASE_NOTES.txt').read_bytes()))
    def test_changed_intro_cannot_pass_by_rebinding_transport_hash(self):
        raw=(self.data.folder/'RELEASE_NOTES.txt').read_bytes().replace(b'RC.5 brings',b'RC.5 promises',1)
        self.rebind_notes_hash(raw)
        with self.assertRaisesRegex(ValueError,'qualified source content'):support.publisher.validate(self.data.folder,self.data.env)
    def test_omitted_limitations_cannot_pass_by_rebinding_transport_hash(self):
        raw=(self.data.folder/'RELEASE_NOTES.txt').read_bytes();self.rebind_notes_hash(raw.rsplit(b'\n- ',1)[0]+b'\n')
        with self.assertRaisesRegex(ValueError,'qualified source content'):support.publisher.validate(self.data.folder,self.data.env)
    def test_wrong_body_commit_cannot_pass_by_rebinding_transport_hash(self):
        raw=(self.data.folder/'RELEASE_NOTES.txt').read_bytes().replace(b'Source commit: '+b'a'*40,b'Source commit: '+b'b'*40,1)
        self.rebind_notes_hash(raw)
        with self.assertRaisesRegex(ValueError,'qualified source content'):support.publisher.validate(self.data.folder,self.data.env)


if __name__=='__main__':unittest.main()
