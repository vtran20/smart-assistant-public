"""Tests pin the public v1 boundary using independently hashed synthetic JSON."""
import copy
import dataclasses
import hashlib
import json
import math
from pathlib import Path
import unittest

from smart_assistant import contracts as c

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples' / 'contracts'
KINDS = ['RequestEnvelope', 'ContextFact', 'ContextBundle', 'Criterion', 'RequestedAction',
         'AuthorizationScope', 'SelectedCapability', 'Selection', 'Limits', 'Artifact',
         'CandidateSnapshot', 'AcceptanceSnapshot', 'Finding', 'Disposition', 'ReviewReceipt',
         'CheckReceipt', 'CycleEvidence', 'TaskRecord', 'TaskAssignment', 'Handoff',
         'PendingAction', 'PreflightResult', 'ErrorDetail', 'GateResult', 'DeploymentFile',
         'DeploymentManifest', 'NativeProbeReceipt', 'PreflightRequest', 'CapabilityRecord',
         'CapabilityCatalog']

def fixture(kind):
    return json.loads((EXAMPLES / f'{kind}.json').read_text())

def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()

class ContractTests(unittest.TestCase):
    def assert_error(self, kind, data, code, path):
        result = c.validate_record(kind, data)
        self.assertFalse(result.passed)
        self.assertIn((code, path), [(e.code, e.path) for e in result.errors])

    def test_valid_examples_pass_and_round_trip_as_typed_dataclasses(self):
        # Missing field/enum decoding or mistaken schema invention breaks real fixtures.
        self.assertEqual(len(KINDS), 30)
        for path in sorted(EXAMPLES.glob('*.json')):
            with self.subTest(example=path.name):
                kind = path.stem.split('__')[0]
                wire = json.loads(path.read_text())
                self.assertTrue(c.validate_record(kind, wire).passed)
                record = c.from_dict(kind, wire)
                self.assertTrue(dataclasses.is_dataclass(record))
                self.assertIsInstance(record, getattr(c, kind))
                self.assertEqual(c.to_dict(record), wire)
                json.dumps(c.to_dict(record), allow_nan=False)
        task = c.from_dict('TaskRecord', fixture('TaskRecord'))
        self.assertIsInstance(task.request, c.RequestEnvelope)
        self.assertIsInstance(task.cycles[0].checks[0], c.CheckReceipt)
        self.assertIsInstance(task.status, c.TaskStatus)
        self.assertIsInstance(task.selection.agents[0], c.SelectedCapability)
        assignment = c.from_dict('TaskAssignment', fixture('TaskAssignment'))
        self.assertIsInstance(assignment.context.facts[0], c.ContextFact)
        catalog = c.from_dict('CapabilityCatalog', fixture('CapabilityCatalog'))
        self.assertIsInstance(catalog.records[0].kind, c.CapabilityKind)

    def test_all_wire_fields_are_required_and_unknown_fields_rejected(self):
        for kind in KINDS:
            wire = fixture(kind)
            for field in wire:
                with self.subTest(kind=kind, omitted=field):
                    changed = dict(wire)
                    del changed[field]
                    self.assert_error(kind, changed, 'missing_field', '$.'+field)
            with self.subTest(kind=kind, unknown=True):
                self.assert_error(kind, dict(wire, extra='x'), 'unknown_field', '$.extra')

    def test_unknown_kind_schema_versions_and_non_object_inputs(self):
        self.assert_error('NonRecord', {}, 'unknown_kind', '$')
        self.assert_error('RequestEnvelope', {'schema_version':99}, 'unsupported_schema', '$.schema_version')
        for value in [None, [], 'text', 2]:
            self.assert_error('RequestEnvelope', value, 'invalid_type', '$')
        for kind in KINDS:
            wire = fixture(kind)
            if 'schema_version' in wire:
                self.assert_error(kind, dict(wire, schema_version=2), 'unsupported_schema', '$.schema_version')
                self.assert_error(kind, dict(wire, schema_version=True), 'invalid_type', '$.schema_version')

    def test_scalar_and_collection_types_are_recursive_and_bool_is_not_int(self):
        cases = [('TaskRecord','revision',True), ('Limits','max_parallel_children',1.5),
                 ('RequestEnvelope','source_refs',('notes',)), ('RequestEnvelope','text',False),
                 ('TaskAssignment','limits',[]), ('CheckReceipt','environment',[]),
                 ('NativeProbeReceipt','discovered',1), ('NativeProbeReceipt','invoked','true')]
        for kind, field, value in cases:
            with self.subTest(kind=kind, field=field):
                self.assert_error(kind, dict(fixture(kind), **{field:value}), 'invalid_type', '$.'+field)
        task = fixture('TaskRecord')
        task['cycles'][0]['checks'][0]['environment']['python'] = 3
        self.assert_error('TaskRecord', task, 'invalid_type', '$.cycles[0].checks[0].environment["python"]')
        task = fixture('TaskRecord')
        task['cycles'][0]['checks'][0]['extra'] = None
        self.assert_error('TaskRecord', task, 'unknown_field', '$.cycles[0].checks[0].extra')
        del task['cycles'][0]['checks'][0]['observed_at']
        self.assert_error('TaskRecord', task, 'missing_field', '$.cycles[0].checks[0].observed_at')
        task = fixture('TaskRecord')
        task['capability_ids'] = ['writer-01', 3]
        self.assert_error('TaskRecord', task, 'invalid_type', '$.capability_ids[1]')
        request = fixture('RequestEnvelope')
        request['source_refs'] = [None]
        self.assert_error('RequestEnvelope', request, 'invalid_type', '$.source_refs[0]')

    def test_ids_versions_and_digests_follow_exact_formats(self):
        for value in ['', 'a', 'Avalid', 'bad.id', 'bad/id', 'a'*65, 'id\n', 'é-id']:
            with self.subTest(id=value):
                self.assert_error('Criterion', dict(fixture('Criterion'), id=value), 'invalid_id', '$.id')
        for value in ['a0', 'a'*64, 'valid-id_01']:
            self.assertTrue(c.validate_record('Criterion', dict(fixture('Criterion'), id=value)).passed)
        for value in ['1', '1.2', '1.2.3.4', '-1.0.0', '1.2.x', '１.0.0', '1.2.3\n']:
            self.assert_error('SelectedCapability', dict(fixture('SelectedCapability'), version=value), 'invalid_version', '$.version')
        for value in ['0.0.0', '01.2.003']:
            self.assertTrue(c.validate_record('SelectedCapability', dict(fixture('SelectedCapability'), version=value)).passed)
        for value in ['a'*63, 'A'*64, 'g'*64, 'a'*64+'\n']:
            self.assert_error('Artifact', dict(fixture('Artifact'), sha256=value), 'invalid_digest', '$.sha256')
        self.assert_error('Handoff', dict(fixture('Handoff'), criteria_coverage={'BAD':['evidence']}), 'invalid_id', '$.criteria_coverage["BAD"]')

    def test_positive_values_empty_strings_and_nullable_fields(self):
        for kind, field in [('TaskRecord','revision'), ('TaskAssignment','assignment_revision'),
                            ('CapabilityCatalog','revision'), ('CycleEvidence','cycle_number'),
                            ('Selection','catalog_revision'), ('Limits','max_correction_cycles')]:
            for value in [0, -1]:
                self.assert_error(kind, dict(fixture(kind), **{field:value}), 'invalid_value', '$.'+field)
        self.assert_error('RequestEnvelope', dict(fixture('RequestEnvelope'), text=''), 'invalid_value', '$.text')
        self.assertTrue(c.validate_record('TaskRecord', dict(fixture('TaskRecord'), resume_next_step='')).passed)
        self.assertTrue(c.validate_record('Handoff', dict(fixture('Handoff'), next_step='')).passed)
        self.assertEqual(c.to_dict(c.Limits()), {'max_correction_cycles':3, 'max_parallel_children':2})
        self.assert_error('RequestEnvelope', dict(fixture('RequestEnvelope'), requested_role='X'), 'invalid_id', '$.requested_role')
        self.assert_error('RequestedAction', dict(fixture('RequestedAction'), required_tool=''), 'invalid_value', '$.required_tool')

    def test_timestamps_validate_calendar_and_utc_syntax(self):
        for stamp in ['2025-02-29T00:00:00Z', '2026-13-01T00:00:00Z', '2026-10-13T24:00:00Z',
                      '2026-10-13T12:34:60Z', '2026-10-13T12:34:00+00:00', '2026-10-13 12:34:00Z',
                      '0000-10-13T12:34:00Z', '2026-10-13T12:34:00Z\n']:
            with self.subTest(stamp=stamp):
                self.assert_error('ContextFact', dict(fixture('ContextFact'), observed_at=stamp), 'invalid_timestamp', '$.observed_at')
        for stamp in ['2024-02-29T00:00:00Z', '2026-10-13T12:34:00.123456789Z']:
            self.assertTrue(c.validate_record('ContextFact', dict(fixture('ContextFact'), observed_at=stamp)).passed)

    def test_paths_are_lexically_safe_without_touching_filesystem(self):
        for value in ['', '/', '/tmp/a', '.', '..', 'a/../b', 'a/./b', 'a//b', 'a/', 'a\\b', 'a\x00b']:
            with self.subTest(path=value):
                self.assert_error('Artifact', dict(fixture('Artifact'), relative_path=value), 'unsafe_path', '$.relative_path')
                self.assert_error('TaskAssignment', dict(fixture('TaskAssignment'), owned_paths=[value]), 'unsafe_path', '$.owned_paths[0]')
        for value in ['not-existing/result.txt', '.hidden/name', '中文/file.txt']:
            self.assertTrue(c.validate_record('Artifact', dict(fixture('Artifact'), relative_path=value)).passed)
        self.assert_error('CapabilityRecord', dict(fixture('CapabilityRecord'), deployed_path='/tmp/x'), 'unsafe_path', '$.deployed_path')

    def test_every_enum_and_task_terminal_state_is_structurally_supported(self):
        cases = [('TaskRecord','status',['queued','running','waiting_input','waiting_approval','verifying','completed','failed','paused','cancelled']),
                 ('TaskRecord','phase',['design','implement','review','feedback','testing']),
                 ('CapabilityRecord','kind',['agent','skill']), ('CapabilityRecord','state',['draft','active','disabled','retired']),
                 ('RequestedAction','kind',['read_local','write_local','external_read','external_write']),
                 ('AuthorizationScope','action_kind',['read_local','write_local','external_read','external_write']),
                 ('RequestedAction','host_decision',['allowed','approval_required','denied','unknown']),
                 ('Finding','severity',['critical','major','minor','info']), ('Disposition','decision',['corrected','rejected']),
                 ('CheckReceipt','outcome',['pass','fail']), ('Handoff','result',['ready_for_review','blocked','failed']),
                 ('NativeProbeReceipt','purpose',['activate','disable'])]
        for kind, field, values in cases:
            for value in values:
                with self.subTest(kind=kind, field=field, value=value):
                    self.assertTrue(c.validate_record(kind, dict(fixture(kind), **{field:value})).passed)
            self.assert_error(kind, dict(fixture(kind), **{field:'unrecognized'}), 'invalid_enum', '$.'+field)
        self.assert_error('CheckReceipt', dict(fixture('CheckReceipt'), method='unrecognized'), 'invalid_enum', '$.method')

    def test_gate_and_preflight_consistency(self):
        self.assertTrue(c.validate_record('GateResult', {'passed':True, 'errors':[]}).passed)
        self.assert_error('GateResult', {'passed':False, 'errors':[]}, 'inconsistent_gate', '$.passed')
        self.assert_error('GateResult', dict(fixture('GateResult'), passed=True), 'inconsistent_gate', '$.passed')
        self.assertTrue(c.validate_record('PreflightResult', {'ready':True, 'missing_tools':[], 'pending_actions':[]}).passed)
        self.assert_error('PreflightResult', {'ready':False, 'missing_tools':[], 'pending_actions':[]}, 'inconsistent_gate', '$.ready')
        self.assert_error('PreflightResult', dict(fixture('PreflightResult'), ready=True), 'inconsistent_gate', '$.ready')

    def test_check_receipt_method_discriminates_command_and_observation(self):
        wire = fixture('CheckReceipt')
        self.assert_error('CheckReceipt', dict(wire, command=None), 'invalid_value', '$.command')
        self.assert_error('CheckReceipt', dict(wire, observation='Also observed'), 'invalid_value', '$.observation')
        observed = fixture('CheckReceipt__observation')
        self.assert_error('CheckReceipt', dict(observed, observation=None), 'invalid_value', '$.observation')
        self.assert_error('CheckReceipt', dict(observed, command='unexpected'), 'invalid_value', '$.command')

    def test_snapshot_hashes_have_independent_literal_inputs_and_exclude_receipts(self):
        for kind, field, key in [('CandidateSnapshot','artifacts','candidate_id'),
                                 ('AcceptanceSnapshot','criteria','acceptance_id'),
                                 ('DeploymentManifest','files','manifest_sha256')]:
            wire = fixture(kind)
            payload = {'criteria':wire[field], 'design_sha256':wire['design_sha256']} if kind == 'AcceptanceSnapshot' else wire[field]
            self.assertEqual(wire[key], hash_json(payload))
            self.assertTrue(c.validate_record(kind, wire).passed)
            changed = copy.deepcopy(wire)
            changed[field][0][next(k for k in changed[field][0] if k in ('sha256','description'))] = 'b'*64
            self.assert_error(kind, changed, 'digest_mismatch', '$.'+key)
            changed = dict(wire, **{key:'0'*64})
            self.assert_error(kind, changed, 'digest_mismatch', '$.'+key)
        task = fixture('TaskRecord')
        original = task['cycles'][0]['candidate']['candidate_id']
        task['cycles'][0]['review']['observed_at'] = '2026-10-14T00:00:00Z'
        task['cycles'][0]['checks'][0]['outcome'] = 'fail'
        self.assertEqual(original, task['cycles'][0]['candidate']['candidate_id'])
        self.assertTrue(c.validate_record('TaskRecord', task).passed)
        with_receipts = fixture('CandidateSnapshot')
        with_receipts['receipts'] = []
        self.assert_error('CandidateSnapshot', with_receipts, 'unknown_field', '$.receipts')

    def test_snapshot_identity_sorting_uniqueness_and_empty_vectors(self):
        cases = [('CandidateSnapshot','artifacts','id','candidate_id'),
                 ('AcceptanceSnapshot','criteria','id','acceptance_id'),
                 ('DeploymentManifest','files','relative_path','manifest_sha256')]
        for kind, field, identity, digestfield in cases:
            wire = fixture(kind)
            first = wire[field][0]
            second = dict(first, **{identity:'zz-item'})
            wire[field] = [second, first]
            payload = {'criteria':wire[field], 'design_sha256':wire['design_sha256']} if kind == 'AcceptanceSnapshot' else wire[field]
            wire[digestfield] = hash_json(payload)
            self.assert_error(kind, wire, 'unsorted', '$.'+field)
            wire[field] = [first, first]
            payload = {'criteria':wire[field], 'design_sha256':wire['design_sha256']} if kind == 'AcceptanceSnapshot' else wire[field]
            wire[digestfield] = hash_json(payload)
            self.assert_error(kind, wire, 'duplicate_id', '$.'+field+'[1].'+identity)
            wire[field] = []
            payload = {'criteria':[], 'design_sha256':wire['design_sha256']} if kind == 'AcceptanceSnapshot' else []
            wire[digestfield] = hash_json(payload)
            self.assertTrue(c.validate_record(kind, wire).passed)

    def test_manifest_fingerprint_is_complete_list_even_for_one_file(self):
        catalog = fixture('CapabilityCatalog')
        selection = fixture('Selection')
        for index, name in enumerate(['DeploymentManifest','DeploymentManifest__multi']):
            manifest = fixture(name)
            expected = hash_json(manifest['files'])
            self.assertEqual(manifest['manifest_sha256'], expected)
            self.assertEqual(catalog['records'][index]['deployed_sha256'], expected)
            selected = selection['agents' if index == 0 else 'skills'][0]
            self.assertEqual(selected['deployed_sha256'], expected)
            self.assertNotEqual(manifest['files'][0]['sha256'], expected)

    def test_preferences_reject_non_json_recursive_values_and_non_string_keys(self):
        for value in [math.nan, math.inf, -math.inf, object(), b'bytes', {1:'value'}, ('a','b'), {1,2}]:
            wire = fixture('ContextBundle')
            wire['preferences']['nested'] = [value]
            codepath = '$.preferences["nested"][0][1]' if isinstance(value, dict) else '$.preferences["nested"][0]'
            with self.subTest(value=repr(value)):
                self.assert_error('ContextBundle', wire, 'not_json', codepath)
        wire = fixture('ContextBundle')
        wire['preferences'] = {1:True}
        self.assert_error('ContextBundle', wire, 'invalid_type', '$.preferences[1]')
        cyclic = []
        cyclic.append(cyclic)
        wire = fixture('ContextBundle')
        wire['preferences']['cycle'] = cyclic
        self.assert_error('ContextBundle', wire, 'not_json', '$.preferences["cycle"][0]')

    def test_decoder_failure_exposes_same_errors_and_serializer_validates(self):
        wire = dict(fixture('RequestEnvelope'), request_id='INVALID')
        result = c.validate_record('RequestEnvelope', wire)
        with self.assertRaises(c.ValidationError) as caught:
            c.from_dict('RequestEnvelope', wire)
        self.assertEqual(caught.exception.errors, result.errors)
        record = c.from_dict('RequestEnvelope', fixture('RequestEnvelope'))
        record.request_id = 'INVALID'
        with self.assertRaises(c.ValidationError) as caught:
            c.to_dict(record)
        self.assertIn(('invalid_id','$.request_id'), [(e.code,e.path) for e in caught.exception.errors])
        with self.assertRaises(c.ValidationError):
            c.to_dict({'schema_version':1})
        context = c.from_dict('ContextBundle', fixture('ContextBundle'))
        context.preferences['bad'] = float('nan')
        with self.assertRaises(c.ValidationError) as caught:
            c.to_dict(context)
        self.assertIn('not_json', [e.code for e in caught.exception.errors])
        self.assertTrue(issubclass(c.RevisionConflict, Exception))

    def test_canonical_json_pins_unicode_finite_data_and_public_boundary_failures(self):
        self.assertEqual(c.canonical_json({'z':[True, None], 'a':'é'}),
                         b'{"a":"\xc3\xa9","z":[true,null]}')
        for value in [float('nan'), {1:'bad'}, object()]:
            with self.assertRaises(c.ValidationError) as caught:
                c.canonical_json(value)
            self.assertIn('not_json', [e.code for e in caught.exception.errors])
        for kind in [None, [], {}]:
            self.assert_error(kind, {}, 'unknown_kind', '$')
            with self.assertRaises(c.ValidationError):
                c.from_dict(kind, {})
        wire = fixture('RequestEnvelope')
        wire[1] = 'bad key'
        self.assert_error('RequestEnvelope', wire, 'invalid_type', '$[1]')

    def test_serialization_does_not_coerce_non_json_preferences(self):
        for value in [c.TaskStatus.RUNNING, c.Limits()]:
            context = c.from_dict('ContextBundle', fixture('ContextBundle'))
            context.preferences['bad'] = value
            with self.subTest(value=repr(value)):
                with self.assertRaises(c.ValidationError) as caught:
                    c.to_dict(context)
                self.assertIn(('not_json', '$.preferences["bad"]'),
                              [(e.code, e.path) for e in caught.exception.errors])
        context = c.from_dict('ContextBundle', fixture('ContextBundle'))
        cyclic = []
        cyclic.append(cyclic)
        context.preferences['cycle'] = cyclic
        with self.assertRaises(c.ValidationError) as caught:
            c.to_dict(context)
        self.assertIn('not_json', [e.code for e in caught.exception.errors])

    def test_canonical_json_rejects_high_and_low_surrogates_in_values_and_keys(self):
        for bad in ['\ud800', '\udfff']:
            escaped_key_path = '$[' + json.dumps(bad, ensure_ascii=True) + ']'
            for value, path in [({'label':bad}, '$["label"]'),
                                ({bad:'label'}, escaped_key_path),
                                ({'nested':[bad]}, '$["nested"][0]')]:
                with self.subTest(bad=ascii(bad), path=path):
                    with self.assertRaises(c.ValidationError) as caught:
                        c.canonical_json(value)
                    self.assertIn(('not_json', path),
                                  [(e.code, e.path) for e in caught.exception.errors])
                    str(caught.exception).encode('utf-8')
                    rejected = c.GateResult(False, caught.exception.errors)
                    c.canonical_json(c.to_dict(rejected))

    def test_surrogate_snapshot_descriptions_fail_structurally_before_hashing(self):
        for bad in ['\ud800', '\udfff']:
            for kind, path in [('AcceptanceSnapshot', '$.criteria[0].description'),
                               ('TaskRecord', '$.cycles[0].acceptance.criteria[0].description')]:
                with self.subTest(kind=kind, bad=ascii(bad)):
                    wire = fixture(kind)
                    snapshot = wire if kind == 'AcceptanceSnapshot' else wire['cycles'][0]['acceptance']
                    snapshot['criteria'][0]['description'] = bad
                    rejected = c.validate_record(kind, wire)
                    self.assertFalse(rejected.passed)
                    self.assertIn(('not_json', path), [(e.code,e.path) for e in rejected.errors])
                    self.assertNotIn('digest_mismatch', [e.code for e in rejected.errors])
                    c.canonical_json(c.to_dict(rejected))
                    with self.assertRaises(c.ValidationError) as caught:
                        c.from_dict(kind, wire)
                    self.assertEqual(caught.exception.errors, rejected.errors)
                    str(caught.exception).encode('utf-8')
                    record = c.from_dict(kind, fixture(kind))
                    acceptance = record if kind == 'AcceptanceSnapshot' else record.cycles[0].acceptance
                    acceptance.criteria[0].description = bad
                    with self.assertRaises(c.ValidationError) as caught:
                        c.to_dict(record)
                    self.assertIn(('not_json', path), [(e.code,e.path) for e in caught.exception.errors])
                    c.canonical_json(c.to_dict(c.GateResult(False, caught.exception.errors)))

    def test_bad_mapping_and_unknown_field_keys_have_serializable_rejections(self):
        for bad in ['\ud800', '\udfff']:
            cases = [('Handoff','criteria_coverage',['evidence']),
                     ('ContextBundle','preferences',True),
                     ('CheckReceipt','environment','synthetic')]
            for kind, field, value in cases:
                path = '$.' + field + '[' + json.dumps(bad, ensure_ascii=True) + ']'
                with self.subTest(kind=kind, bad=ascii(bad)):
                    wire = fixture(kind)
                    wire[field] = {bad:value}
                    self.assert_error(kind, wire, 'not_json', path)
                    result = c.validate_record(kind, wire)
                    c.canonical_json(c.to_dict(result))
                    with self.assertRaises(c.ValidationError) as caught:
                        c.from_dict(kind, wire)
                    str(caught.exception).encode('utf-8')
                    record = c.from_dict(kind, fixture(kind))
                    setattr(record, field, {bad:value})
                    with self.assertRaises(c.ValidationError) as caught:
                        c.to_dict(record)
                    self.assertIn(('not_json',path), [(e.code,e.path) for e in caught.exception.errors])
                    c.canonical_json(c.to_dict(c.GateResult(False, caught.exception.errors)))
            wire = fixture('RequestEnvelope')
            wire[bad] = 'unknown field'
            path = '$[' + json.dumps(bad, ensure_ascii=True) + ']'
            self.assert_error('RequestEnvelope', wire, 'not_json', path)
            c.canonical_json(c.to_dict(c.validate_record('RequestEnvelope', wire)))
            # Nested untyped JSON keys follow the same safe error-path rule.
            context = fixture('ContextBundle')
            context['preferences']['nested'] = [{bad:'value'}]
            path = '$.preferences["nested"][0][' + json.dumps(bad, ensure_ascii=True) + ']'
            self.assert_error('ContextBundle', context, 'not_json', path)
            c.canonical_json(c.to_dict(c.validate_record('ContextBundle', context)))
            # Unknown malformed record kinds do not interpolate unsafe text.
            result = c.validate_record(bad, {})
            self.assertFalse(result.passed)
            self.assertIn(('unknown_kind','$'), [(e.code,e.path) for e in result.errors])
            c.canonical_json(c.to_dict(result))
            with self.assertRaises(c.ValidationError) as caught:
                c.from_dict(bad, {})
            str(caught.exception).encode('utf-8')

    def test_all_wire_string_categories_reject_surrogates(self):
        for kind, field in [('RequestEnvelope','text'), ('RequestEnvelope','request_id'),
                            ('TaskRecord','resume_next_step'), ('Artifact','relative_path'),
                            ('Artifact','sha256'), ('SelectedCapability','version'),
                            ('ContextFact','observed_at'), ('NativeProbeReceipt','purpose')]:
            for bad in ['\ud800', '\udfff']:
                with self.subTest(kind=kind, field=field, bad=ascii(bad)):
                    self.assert_error(kind, dict(fixture(kind), **{field:bad}), 'not_json', '$.'+field)
                    c.canonical_json(c.to_dict(c.validate_record(kind, dict(fixture(kind), **{field:bad}))))
        context = fixture('ContextBundle')
        context['preferences']['nested'] = ['\ud800']
        self.assert_error('ContextBundle', context, 'not_json', '$.preferences["nested"][0]')

    def test_valid_supplementary_unicode_remains_literal_in_fingerprints(self):
        text = 'é 😀 𐍈'
        expected_bytes = b'{"label":"\xc3\xa9 \xf0\x9f\x98\x80 \xf0\x90\x8d\x88"}'
        self.assertEqual(c.canonical_json({'label':text}), expected_bytes)
        snapshot = fixture('AcceptanceSnapshot')
        snapshot['criteria'][0]['description'] = text
        payload = {'criteria':snapshot['criteria'], 'design_sha256':snapshot['design_sha256']}
        snapshot['acceptance_id'] = hash_json(payload)
        self.assertTrue(c.validate_record('AcceptanceSnapshot', snapshot).passed)
        self.assertEqual(c.to_dict(c.from_dict('AcceptanceSnapshot', snapshot)), snapshot)
        self.assertEqual(hashlib.sha256(c.canonical_json(payload)).hexdigest(), snapshot['acceptance_id'])
        context = fixture('ContextBundle')
        context['preferences'][text] = text
        self.assertEqual(c.to_dict(c.from_dict('ContextBundle', context)), context)
        # Safe non-ASCII unknown-field paths keep their ordinary .field shape.
        request = fixture('RequestEnvelope')
        request[text] = 'unknown'
        self.assert_error('RequestEnvelope', request, 'unknown_field', '$.'+text)
        c.canonical_json(c.to_dict(c.validate_record('RequestEnvelope', request)))

    def test_validation_does_not_mutate_input_or_apply_later_package_gates(self):
        wire = fixture('TaskRecord')
        original = copy.deepcopy(wire)
        c.validate_record('TaskRecord', wire)
        self.assertEqual(wire, original)
        for name in ['NativeProbeReceipt__failed_activate','NativeProbeReceipt__failed_invoke', 'NativeProbeReceipt__failed_disable']:
            self.assertTrue(c.validate_record('NativeProbeReceipt', fixture(name)).passed)
        wire['status'] = 'completed'
        wire['cycles'] = []
        self.assertTrue(c.validate_record('TaskRecord', wire).passed)
        handoff = fixture('Handoff')
        handoff['criteria_coverage'] = {}
        self.assertTrue(c.validate_record('Handoff', handoff).passed)

if __name__ == '__main__':
    unittest.main()
