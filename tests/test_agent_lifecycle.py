import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import threading

from smart_assistant.catalog import deployment_manifest, load_catalog
from smart_assistant.contracts import (CapabilityCatalog, CapabilityKind, CapabilityRecord,
    CapabilityState, ValidationError, to_dict, canonical_json)
from smart_assistant.lifecycle import DeploymentStore
try:
    from smart_assistant.agent_lifecycle import validate_agent_definition, stage_agent
except ModuleNotFoundError as error:
    if error.name != 'smart_assistant.agent_lifecycle':
        raise
    validate_agent_definition = stage_agent = None

CYCLE = 'Follow design → implement → independent review → feedback → test → repeat until acceptance passes.'

def definition(name='researcher', instructions=CYCLE):
    return f'name = {json.dumps(name)}\ndescription = "Extract facts from supplied local text."\ndeveloper_instructions = {json.dumps(instructions, ensure_ascii=False)}\n'

def record(**changes):
    result = CapabilityRecord(1, 'researcher', CapabilityKind.AGENT, 'Researcher', '1.0.0',
        CapabilityState.DRAFT, 'examples/input.toml', '.codex/agents/researcher.toml', None,
        ['extract supplied facts'], ['no outside research'], ['supplied text'],
        'grounded extracted facts', [], [], None, None)
    return replace(result, **changes)

class AgentLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / 'capabilities').mkdir()
        self.catalog([])
        self.path = self.root / 'examples/input.toml'
        self.path.parent.mkdir()
        self.path.write_text(definition(), encoding='utf-8')
    def tearDown(self):
        self.temp.cleanup()
    def catalog(self, records):
        (self.root / 'capabilities/catalog.json').write_bytes(canonical_json(to_dict(CapabilityCatalog(1, 1, records))))
    def validate(self, path=None):
        self.assertIsNotNone(validate_agent_definition, 'P05 validation helper is not implemented')
        return validate_agent_definition(path or self.path)
    def stage(self, candidate=None, path=None, root=None):
        self.assertIsNotNone(stage_agent, 'P05 staging helper is not implemented')
        return stage_agent(root or self.root, path or self.path, candidate or record())
    def rejected(self, code):
        gate = self.validate()
        self.assertFalse(gate.passed)
        self.assertIn(code, [e.code for e in gate.errors])
    def test_minimal_native_schema_with_inherited_defaults(self):
        self.assertTrue(self.validate().passed)
    def test_missing_fields_and_blank_fields(self):
        for field in ('name', 'description', 'developer_instructions'):
            with self.subTest(field=field):
                self.path.write_text('\n'.join(line for line in definition().splitlines() if not line.startswith(field + ' =')))
                self.rejected('missing_field')
        self.path.write_text(definition().replace('"researcher"', '" "'))
        self.rejected('invalid_field')
    def test_malformed_toml_and_utf8(self):
        self.path.write_text('name = [')
        self.rejected('invalid_toml')
        self.path.write_bytes(b'\xff')
        self.rejected('invalid_toml')
    def test_identity_must_be_contract_compatible(self):
        for identity in ('Researcher', '../escape', 'a', 'bad identity'):
            self.path.write_text(definition(identity))
            self.rejected('invalid_identity')
    def test_missing_or_unordered_cycle(self):
        for cycle in ('Extract facts.', CYCLE.replace('independent review', 'review'),
                      'test feedback design implement independent review repeat'):
            self.path.write_text(definition(instructions=cycle))
            self.rejected('missing_work_cycle')
    def test_natural_cycle_variants(self):
        for instructions in (
            'Use design, implementation, review independently, feedback, testing, then repeat.',
            'Design → implement → review (independent) → feedback → test → repeat.',
            CYCLE + ' Do not skip independent review or testing.',
            CYCLE + ' Never bypass tests.',
        ):
            self.path.write_text(definition(instructions=instructions))
            self.assertTrue(self.validate().passed)
    def test_instructions_to_skip_review_or_testing_rejected(self):
        for instruction in ('Skip independent review.', 'Bypass testing.', 'Omit tests.'):
            self.path.write_text(definition(instructions=CYCLE + ' ' + instruction))
            self.rejected('missing_work_cycle')
    def test_missing_or_malformed_catalog_fails_before_staging(self):
        catalog = self.root / 'capabilities/catalog.json'
        catalog.unlink()
        with self.assertRaises(ValidationError): self.stage()
        catalog.write_text('{}')
        with self.assertRaises(ValidationError): self.stage()
        self.assertFalse((self.root / 'capabilities/staging').exists())
    def test_unidentifiable_native_asset_fails_closed(self):
        path = self.root / '.codex/agents/unknown.toml'
        path.parent.mkdir(parents=True)
        for data in ('name = [', 'description = "missing identity"'):
            path.write_text(data)
            with self.assertRaises(ValidationError): self.stage()
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(ValidationError): self.stage()
    def test_plain_string_enum_inputs_are_normalized(self):
        staged = self.stage(record(kind='agent', state='draft'))
        self.assertIs(staged.kind, CapabilityKind.AGENT)
        self.assertIs(staged.state, CapabilityState.DRAFT)
    def test_non_directory_stage_parent_and_native_directory(self):
        for path in (self.root / 'capabilities/staging', self.root / '.codex/agents'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('occupied')
            with self.assertRaises(ValidationError): self.stage()
            self.assertEqual(path.read_text(), 'occupied')
            path.unlink()
    def test_overrides_require_observed_catalog(self):
        for field in ('model', 'model_reasoning_effort'):
            self.path.write_text(definition() + f'{field} = "guessed-value"\n')
            self.rejected('unobserved_catalog')
    def test_unknown_and_permission_configuration_rejected(self):
        for field in ('sandbox_mode', 'approval_policy', 'tools', 'nickname'):
            self.path.write_text(definition() + f'{field} = "anything"\n')
            self.rejected('unsupported_field')
    def test_validation_rejects_symlinks_missing_directory_and_special_file(self):
        for path in (self.root / 'missing.toml', self.root):
            self.assertFalse(self.validate(path).passed)
        link = self.root / 'link.toml'
        link.symlink_to(self.path)
        self.assertFalse(self.validate(link).passed)
        fifo = self.root / 'fifo.toml'
        os.mkfifo(fifo)
        self.assertFalse(self.validate(fifo).passed)
    def test_ancestor_symlink_rejected(self):
        directory = self.root / 'alias'
        directory.symlink_to(self.path.parent, target_is_directory=True)
        self.assertFalse(self.validate(directory / self.path.name).passed)
    def test_stage_complete_copy_normalized_manifest_and_no_mutations(self):
        before = (self.root / 'capabilities/catalog.json').read_bytes()
        result = self.stage(record(deployed_path='.codex/agents/custom-target.toml'))
        target = self.root / result.source_path
        self.assertEqual(target.read_bytes(), self.path.read_bytes())
        self.assertEqual(result.source_path, 'capabilities/staging/agents/researcher/1.0.0/custom-target.toml')
        expected = [{'relative_path':'custom-target.toml', 'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}]
        self.assertEqual(result.deployed_sha256, hashlib.sha256(canonical_json(expected)).hexdigest())
        self.assertEqual(result.deployed_sha256, deployment_manifest(target).manifest_sha256)
        self.assertEqual((self.root / 'capabilities/catalog.json').read_bytes(), before)
        self.assertFalse((self.root / '.codex').exists())
        self.assertFalse((self.root / '.smart-assistant/deployments').exists())
    def test_fresh_record_clears_stale_proof_and_does_not_alias(self):
        original = record(validation_refs=['old-validation.json'], discovery_probe_ref='old-probe.json', rollback_ref='old-rollback.json')
        result = self.stage(original)
        self.assertEqual(result.validation_refs, [])
        self.assertIsNone(result.discovery_probe_ref)
        self.assertIsNone(result.rollback_ref)
        result.triggers.append('another')
        self.assertEqual(original.triggers, ['extract supplied facts'])
        self.assertEqual(original.validation_refs, ['old-validation.json'])
    def test_reject_non_draft_kind_and_malformed_public_record(self):
        for candidate in (record(kind=CapabilityKind.SKILL), record(state=CapabilityState.ACTIVE),
                          record(version='invalid'), record(id='different')):
            with self.assertRaises(ValidationError): self.stage(candidate)
        self.assertFalse((self.root / 'capabilities/staging').exists())
    def test_reject_unsafe_target_and_missing_target(self):
        for target in (None, 'outside.toml', '.codex/agents/sub/x.toml', '.codex/agents/.hidden.toml', '.codex/agents/x.txt', '../escape.toml'):
            with self.assertRaises(ValidationError): self.stage(record(deployed_path=target))
        self.assertFalse((self.root / 'capabilities/staging').exists())
    def test_reject_source_outside_project_native_and_journal(self):
        with TemporaryDirectory() as elsewhere:
            outside = Path(elsewhere).resolve() / 'input.toml'
            outside.write_text(definition())
            with self.assertRaises(ValidationError): self.stage(path=outside)
        for relative in ('.codex/agents/native.toml', '.agents/input.toml', '.smart-assistant/deployments/input.toml'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(definition())
            with self.assertRaises(ValidationError): self.stage(path=path)
    def test_reject_symlink_root_destination_and_source(self):
        alias = self.root / 'root-link'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValidationError): self.stage(root=alias)
        (self.root / 'capabilities/staging').symlink_to(self.path.parent, target_is_directory=True)
        with self.assertRaises(ValidationError): self.stage()
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ['input.toml'])
    def test_catalog_identity_kind_target_and_version_collisions(self):
        for old in (record(kind=CapabilityKind.SKILL, deployed_path='.agents/skills/researcher'),
                    record(deployed_path='.codex/agents/other.toml'), record()):
            self.catalog([old])
            with self.assertRaises(ValidationError): self.stage()
        self.catalog([record(id='another', deployed_path='.codex/agents/researcher.toml')])
        with self.assertRaises(ValidationError): self.stage()
    def test_native_identity_collision_at_other_basename(self):
        path = self.root / '.codex/agents/other.toml'
        path.parent.mkdir(parents=True)
        path.write_text(definition())
        with self.assertRaises(ValidationError): self.stage()
    def test_native_unregistered_target_collision(self):
        path = self.root / '.codex/agents/researcher.toml'
        path.parent.mkdir(parents=True)
        path.write_text(definition('another'))
        with self.assertRaises(ValidationError): self.stage()
    def test_replacement_same_registered_identity_kind_target_new_version(self):
        old = record()
        self.catalog([old])
        path = self.root / old.deployed_path
        path.parent.mkdir(parents=True)
        path.write_text(definition())
        self.assertEqual(self.stage(record(version='2.0.0')).version, '2.0.0')
    def test_version_staging_immutable(self):
        first = self.stage()
        before = (self.root / first.source_path).read_bytes()
        self.path.write_text(definition(instructions=CYCLE + ' Revised behavior.'))
        with self.assertRaises(ValidationError): self.stage()
        self.assertEqual((self.root / first.source_path).read_bytes(), before)
    def test_staging_does_not_manufacture_evaluation(self):
        staged = self.stage()
        with self.assertRaises(ValidationError): DeploymentStore(self.root).prepare(staged, 1)
        self.assertFalse((self.root / staged.deployed_path).exists())
        self.assertEqual(load_catalog(self.root).revision, 1)

    def test_failed_fsync_leaves_no_version_and_same_version_can_retry(self):
        before = (self.root / 'capabilities/catalog.json').read_bytes()
        with patch('smart_assistant.agent_lifecycle.os.fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(ValidationError): self.stage()
        version = self.root / 'capabilities/staging/agents/researcher/1.0.0'
        self.assertFalse(version.exists())
        staged = self.stage()
        self.assertEqual((self.root / staged.source_path).read_bytes(), self.path.read_bytes())
        self.assertEqual((self.root / 'capabilities/catalog.json').read_bytes(), before)
        self.assertFalse((self.root / '.codex').exists())
    def test_failed_partial_write_leaves_no_version_and_same_version_can_retry(self):
        real_fdopen = os.fdopen
        class FailedWriter:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def write(self, data):
                self.stream.write(data[:10])
                raise OSError('partial write')
        def faulty_fdopen(descriptor, mode):
            stream = real_fdopen(descriptor, mode)
            return FailedWriter(stream) if mode == 'wb' else stream
        with patch('smart_assistant.agent_lifecycle.os.fdopen', side_effect=faulty_fdopen):
            with self.assertRaises(ValidationError): self.stage()
        self.assertFalse((self.root / 'capabilities/staging/agents/researcher/1.0.0').exists())
        staged = self.stage()
        self.assertEqual((self.root / staged.source_path).read_bytes(), self.path.read_bytes())
    def test_failed_open_does_not_consume_version(self):
        real_open = os.open
        def faulty_open(path, flags, *args, **kwargs):
            if Path(path).name == 'researcher.toml' and flags & os.O_WRONLY:
                raise OSError('file open failure')
            return real_open(path, flags, *args, **kwargs)
        with patch('smart_assistant.agent_lifecycle.os.open', side_effect=faulty_open):
            with self.assertRaises(ValidationError): self.stage()
        self.assertFalse((self.root / 'capabilities/staging/agents/researcher/1.0.0').exists())
        self.assertEqual(self.stage().version, '1.0.0')
    def test_valid_later_cycle_not_hidden_by_role_prose(self):
        for prose in (
            'Design the extraction and implement a draft. Review the supplied source for ambiguity. ',
            'Design and implement the extraction with review of source quality. ',
            'Design, implement, review independently. Feedback describes earlier work. ',
        ):
            self.path.write_text(definition(instructions=prose + CYCLE))
            self.assertTrue(self.validate().passed)
    def test_explicit_review_testing_waivers_rejected(self):
        for waiver in (
            'Review and tests are optional.',
            'No independent review is required.',
            'Testing is not required.',
            'Independent review is unnecessary.',
            'No need for independent review or testing.',
        ):
            self.path.write_text(definition(instructions=CYCLE + ' ' + waiver))
            self.rejected('missing_work_cycle')
    def test_prohibitions_and_incomplete_review_guidance_remain_valid(self):
        for directive in (
            'Do not skip independent review or testing.',
            'No independent review is complete without tests.',
            'Never bypass tests.',
        ):
            self.path.write_text(definition(instructions=CYCLE + ' ' + directive))
            self.assertTrue(self.validate().passed)

    def test_concurrent_success_published_version_preserved(self):
        real_fsync = os.fsync
        barrier = threading.Barrier(2)
        def synchronized_fsync(descriptor):
            real_fsync(descriptor)
            barrier.wait(timeout=5)
        def attempt():
            try:
                return self.stage()
            except ValidationError as error:
                return error
        with patch('smart_assistant.agent_lifecycle.os.fsync', side_effect=synchronized_fsync):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: attempt(), range(2)))
        success = [result for result in results if isinstance(result, CapabilityRecord)]
        failures = [result for result in results if isinstance(result, ValidationError)]
        self.assertEqual(len(success), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].errors[0].code, 'immutable_version')
        published = self.root / success[0].source_path
        self.assertEqual(published.read_bytes(), self.path.read_bytes())
        self.assertEqual(deployment_manifest(published).manifest_sha256, success[0].deployed_sha256)
        self.assertEqual(sorted(p.name for p in published.parent.parent.iterdir()), ['.stage.lock', '1.0.0'])
        with self.assertRaises(ValidationError): self.stage()
        self.assertEqual(published.read_bytes(), self.path.read_bytes())
    def test_failed_hash_cleans_only_private_temporary_slot(self):
        with patch('smart_assistant.agent_lifecycle.deployment_manifest', side_effect=OSError('hash read failure')):
            with self.assertRaises(ValidationError): self.stage()
        parent = self.root / 'capabilities/staging/agents/researcher'
        self.assertEqual(list(parent.iterdir()), [])
        self.assertEqual(self.stage().version, '1.0.0')
    def test_independent_reviewer_word_alone_is_not_cycle_review_stage(self):
        self.path.write_text(definition(instructions=CYCLE.replace('independent review', 'independent reviewer')))
        self.rejected('missing_work_cycle')

    def test_direct_no_required_and_no_need_to_waivers_rejected(self):
        for waiver in (
            'No tests required.',
            'No independent review required.',
            'No need to test.',
            'No tests needed.',
            'No testing necessary.',
            'No independent review needed.',
            'No independent review necessary.',
            'No need to review.',
            'No need to independently review.',
            'No need to verify.',
        ):
            with self.subTest(waiver=waiver):
                self.path.write_text(definition(instructions=CYCLE + ' ' + waiver))
                self.rejected('missing_work_cycle')
    def test_compound_review_and_testing_requirements_remain_valid(self):
        for controls in (
            'No independent review is complete without tests. Do not skip independent review or testing.',
            'Review and tests are not optional. Never bypass tests.',
            'Independent review is required. Tests are necessary.',
            'Independent review is not optional. Independent review and tests are required.',
            'No independent review is complete without tests. Do not skip independent review or tests.',
        ):
            with self.subTest(controls=controls):
                self.path.write_text(definition(instructions=CYCLE + ' ' + controls))
                self.assertTrue(self.validate().passed)
