from dataclasses import replace
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from smart_assistant.catalog import deployment_manifest, load_catalog
from smart_assistant.contracts import (CapabilityCatalog, CapabilityKind, CapabilityRecord,
    CapabilityState, ProbePurpose, ValidationError, to_dict)
from smart_assistant.lifecycle import DeploymentStore
from smart_assistant.skill_lifecycle import stage_skill, validate_skill_definition
from tests.test_catalog import receipt, write_json

BODY = '''Use when asked to count a supplied local list; do not handle unrelated requests.
Output a count and input identity. Verify the result against each nonempty input line.
Follow design, implementation, independent review, feedback, testing and repeat until complete.
'''


class SkillLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        write_json(self.root / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [])))
        self.skill = self.root / 'definitions/count-local-items'
        self.skill.mkdir(parents=True)
        self.path = self.skill / 'SKILL.md'
        self.write()
        self.record = CapabilityRecord(1, 'count-items', CapabilityKind.SKILL,
            'count-local-items', '1.0.0', CapabilityState.DRAFT, 'placeholder', None,
            None, ['count a local list'], ['local only'], ['input list'], 'output',
            [], ['stale.json'], 'stale-native.json', 'stale-rollback.json')

    def tearDown(self): self.temp.cleanup()

    def write(self, metadata='name: count-local-items\ndescription: Use when counting a local list.', body=BODY):
        self.path.write_text('---\n' + metadata + '\n---\n' + body, encoding='utf-8')

    def error(self, code):
        gate = validate_skill_definition(self.path)
        self.assertFalse(gate.passed)
        self.assertIn(code, [error.code for error in gate.errors])

    def test_required_metadata_and_unambiguous_quoted_scalars(self):
        self.assertTrue(validate_skill_definition(self.path).passed)
        self.write('name: "count-local-items"\ndescription: \'Use when input includes: local items.\'')
        self.assertTrue(validate_skill_definition(self.skill).passed)
        for meta in ('name: count-local-items', 'description: Count a list.'):
            with self.subTest(meta=meta):
                self.write(meta)
                self.error('missing_metadata')

    def test_broader_yaml_is_precisely_unsupported(self):
        for meta in ('description: |\n  Count a list', 'metadata:\n  key: value',
                     'description: yes', 'description: [list]', 'description: 123',
                     'description: a # comment', 'description: a: b',
                     'description: &anchor value'):
            with self.subTest(meta=meta):
                self.write('name: count-local-items\n' + meta)
                self.error('unsupported_metadata')
        self.write('name: count-local-items\nname: other\ndescription: Count a list')
        self.error('unsupported_metadata')

    def test_instruction_contract_omissions_and_reasonable_variants(self):
        self.write(body='Use when counting input. Output a count. ' +
                   'Design, implement, independent review, feedback and repeat until complete.')
        self.error('missing_verification')
        self.write(body='Use when counting input. Output and verify a count.')
        self.error('missing_work_cycle')
        self.write(body='Plan and build, obtain a fresh reviewer, resolve findings, run checks, iterate until complete. '
                   'Invoke for local item lists only. Deliver the verified count.')
        self.assertTrue(validate_skill_definition(self.path).passed)
        self.write(body=BODY + '\nSkip independent review and testing to save time.')
        self.error('unsafe_work_cycle')

    def test_external_links_and_fenced_examples_are_not_local_paths(self):
        self.write(body=BODY + '\nSee [docs](https://example.com/docs/../skill?q=../foo).\n'
                   '[Mail](mailto:example@example.com) and [section](#scope).\n'
                   '```markdown\n[illustration](../not-a-real-resource)\n```\n')
        self.assertTrue(validate_skill_definition(self.path).passed)

    def test_local_resources_and_reference_links_are_checked(self):
        (self.skill / 'references').mkdir()
        (self.skill / 'references/help.txt').write_text('help')
        self.write(body=BODY + '\n[help][details]\n[details]: references/help.txt\n')
        self.assertTrue(validate_skill_definition(self.path).passed)
        for ref in ('../outside', '%2e%2e/outside', '/outside', 'references/missing.txt'):
            with self.subTest(ref=ref):
                self.write(body=BODY + '\n[help](' + ref + ')\n')
                self.error('missing_resource' if ref == 'references/missing.txt' else 'unsafe_path')
        self.write(body=BODY + '\nRun `scripts/../../escape.py`.')
        self.error('unsafe_path')

    def test_symlink_ancestors_and_special_resources_are_rejected(self):
        link = self.root / 'alias'
        link.symlink_to(self.skill, target_is_directory=True)
        self.assertFalse(validate_skill_definition(link / 'SKILL.md').passed)
        (self.skill / 'link').symlink_to(self.root / 'outside')
        self.error('unsafe_path')
        (self.skill / 'link').unlink()
        os.mkfifo(self.skill / 'pipe')
        self.error('unsafe_path')

    def test_stage_copies_full_resources_and_clears_stale_proof(self):
        (self.skill / 'scripts').mkdir()
        (self.skill / 'scripts/count.py').write_bytes(b'print(1)\n')
        before = (self.root / 'capabilities/catalog.json').read_bytes()
        staged = stage_skill(self.root, self.path, self.record)
        self.assertEqual(staged.deployed_path, '.agents/skills/count-local-items')
        self.assertEqual(staged.state, CapabilityState.DRAFT)
        self.assertIsNone(staged.discovery_probe_ref)
        self.assertIsNone(staged.rollback_ref)
        self.assertEqual(staged.deployed_sha256,
                         deployment_manifest(self.root / staged.source_path).manifest_sha256)
        self.assertEqual((self.root / staged.source_path / 'scripts/count.py').read_bytes(), b'print(1)\n')
        self.assertEqual((self.root / 'capabilities/catalog.json').read_bytes(), before)
        self.assertFalse((self.root / staged.deployed_path).exists())
        self.assertFalse((self.root / '.smart-assistant/deployments').exists())
        self.assertEqual(len(staged.validation_refs), 1)
        proof = json.loads((self.root / staged.validation_refs[0]).read_text())
        self.assertEqual(proof['kind'], 'validation')
        self.assertTrue(proof['passed'])
        self.assertEqual(proof['manifest_sha256'], staged.deployed_sha256)
        self.assertEqual(self.record.validation_refs, ['stale.json'])
        self.path.write_text('changed after staging')
        self.assertNotEqual(self.path.read_bytes(), (self.root / staged.source_path / 'SKILL.md').read_bytes())

    def test_record_normalization_wrong_kind_state_and_metadata_identity(self):
        staged = stage_skill(self.root, self.path, replace(self.record, kind='skill', state='draft'))
        self.assertIsInstance(staged.kind, CapabilityKind)
        for change in (dict(kind=CapabilityKind.AGENT), dict(state=CapabilityState.ACTIVE),
                       dict(name='other'), dict(deployed_path='.agents/skills/other')):
            with self.subTest(change=change):
                with self.assertRaises(ValidationError): stage_skill(self.root, self.path, replace(self.record, **change))

    def test_immutable_versions_and_new_version_replacement(self):
        first = stage_skill(self.root, self.path, self.record)
        with self.assertRaises(ValidationError): stage_skill(self.root, self.path, self.record)
        write_json(self.root / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [first])))
        self.write(body=BODY + '\nVersion two.')
        newer = stage_skill(self.root, self.path, replace(self.record, version='1.1.0'))
        self.assertNotEqual(first.source_path, newer.source_path)
        self.assertNotEqual(first.deployed_sha256, newer.deployed_sha256)
        with self.assertRaises(ValidationError):
            stage_skill(self.root, self.path, replace(self.record, version='1.0.0'))

    def test_registered_identity_and_target_collisions(self):
        other = replace(self.record, id='other', source_path='old',
                        deployed_path='.agents/skills/count-local-items', validation_refs=[],
                        discovery_probe_ref=None, rollback_ref=None)
        write_json(self.root / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [other])))
        with self.assertRaises(ValidationError): stage_skill(self.root, self.path, self.record)
        for previous in (replace(other, id=self.record.id, kind=CapabilityKind.AGENT,
                                 deployed_path='.codex/agents/other.toml'),
                         replace(other, id=self.record.id, deployed_path='.agents/skills/other')):
            write_json(self.root / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [previous])))
            with self.assertRaises(ValidationError): stage_skill(self.root, self.path, self.record)

    def test_unmanaged_native_and_staging_symlink_collisions(self):
        target = self.root / '.agents/skills/count-local-items'
        target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('existing')
        with self.assertRaises(ValidationError): stage_skill(self.root, self.path, self.record)
        (target / 'SKILL.md').unlink()
        target.rmdir()
        (self.root / 'capabilities/staging').symlink_to(self.skill, target_is_directory=True)
        with self.assertRaises(ValidationError): stage_skill(self.root, self.path, self.record)

    def test_deployment_requires_evaluation_and_fresh_successful_probe(self):
        staged = stage_skill(self.root, self.path, self.record)
        store = DeploymentStore(self.root)
        with self.assertRaises(ValidationError): store.prepare(staged, 1)
        structural = json.loads((self.root / staged.validation_refs[0]).read_text())
        structural['kind'] = 'evaluation'
        write_json(self.root / 'evidence/evaluation.json', structural)
        ready = replace(staged, validation_refs=[*staged.validation_refs, 'evidence/evaluation.json'])
        operation = store.prepare(ready, 1)
        # Synthetic contract observation only; no installed-client claim.
        write_json(self.root / 'evidence/observation.txt', {'synthetic': True})
        with self.assertRaises(ValidationError):
            store.finalize(operation, receipt(ready, operation, discovered=False, invoked=False))
        self.assertEqual(load_catalog(self.root).records, [])
        self.assertFalse((self.root / ready.deployed_path).exists())

    def test_cycle_accepts_reversed_independence_and_forbids_skipping(self):
        self.write(body='Use when counting local items. Deliver and verify the count. '
                   'Design, implement, review independently, resolve feedback, run tests and repeat. '
                   'Never skip review or testing.')
        self.assertTrue(validate_skill_definition(self.path).passed)

    def test_local_windows_paths_and_trailing_yaml_colon_are_rejected(self):
        self.write(body=BODY + '\n[local](C:\\outside\\resource.txt)')
        self.error('unsafe_path')
        self.write('name: count-local-items\ndescription: Counting items:')
        self.error('unsupported_metadata')

    def test_definition_copy_validation_error_leaves_no_version_slot(self):
        self.write(body=BODY + '\n[missing](assets/missing.txt)')
        with self.assertRaises(ValidationError): stage_skill(self.root, self.path, self.record)
        self.assertFalse((self.root / 'capabilities/staging/count-items/1.0.0').exists())

    def test_registered_native_drift_is_rejected_for_new_version(self):
        first = stage_skill(self.root, self.path, self.record)
        write_json(self.root / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [first])))
        target = self.root / first.deployed_path
        target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('drift')
        with self.assertRaises(ValidationError):
            stage_skill(self.root, self.path, replace(self.record, version='2.0.0'))

    def test_packaged_skills_and_repeatable_resources_are_usable(self):
        import subprocess
        repository = Path(__file__).resolve().parents[1]
        packaged = [repository / '.agents/skills/manage-skill',
                    repository / 'examples/skills/count-local-items/v1/count-local-items',
                    repository / 'examples/skills/count-local-items/v2/count-local-items']
        for path in packaged:
            with self.subTest(path=path):
                gate = validate_skill_definition(path)
                self.assertTrue(gate.passed, gate.errors)
        for version, expected in (('v1', 3), ('v2', 2)):
            path = repository / 'examples/skills/count-local-items' / version / 'count-local-items'
            result = subprocess.run(['python3', str(path / 'scripts/count.py'),
                                     str(path / 'assets/items.txt')],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output['count'], expected)
            self.assertEqual(output['fixture_version'], version)
            failed = subprocess.run(['python3', str(path / 'scripts/count.py'),
                                     str(self.root / 'missing-input.txt')],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(failed.returncode, 2)
            self.assertFalse(failed.stdout)
            self.assertIn('input_unavailable', failed.stderr)

    def test_synthetic_activation_disable_and_previous_version_transaction(self):
        store = DeploymentStore(self.root)
        write_json(self.root / 'evidence/observation.txt', {'synthetic_only': True})
        def evaluated(staged, label):
            structural = json.loads((self.root / staged.validation_refs[0]).read_text())
            structural['kind'] = 'evaluation'
            ref = 'evidence/' + label + '.json'
            write_json(self.root / ref, structural)
            return replace(staged, validation_refs=[staged.validation_refs[0], ref],
                           state=CapabilityState.DRAFT, discovery_probe_ref=None, rollback_ref=None)
        first = evaluated(stage_skill(self.root, self.path, self.record), 'first-evaluation')
        operation = store.prepare(first, 1)
        catalog = store.finalize(operation, receipt(first, operation))
        self.assertEqual(catalog.records[0].state, CapabilityState.ACTIVE)
        with self.assertRaises(ValidationError): store.restore(operation)
        self.write(body=BODY + '\nVersion two.')
        second = evaluated(stage_skill(self.root, self.path, replace(self.record, version='2.0.0')),
                           'second-evaluation')
        operation = store.prepare(second, catalog.revision)
        catalog = store.finalize(operation, receipt(second, operation))
        operation = store.prepare_disable(first.id, catalog.revision)
        catalog = store.finalize_disable(operation, receipt(second, operation, purpose=ProbePurpose.DISABLE))
        self.assertEqual(catalog.records[0].state, CapabilityState.DISABLED)
        self.assertFalse((self.root / second.deployed_path).exists())
        rolled_back = evaluated(first, 'fresh-previous-version-evaluation')
        operation = store.prepare(rolled_back, catalog.revision)
        catalog = store.finalize(operation, receipt(rolled_back, operation))
        self.assertEqual(catalog.records[0].version, '1.0.0')
        self.assertEqual(deployment_manifest(self.root / first.deployed_path).manifest_sha256,
                         first.deployed_sha256)

    def test_inline_markup_examples_are_not_resource_links(self):
        self.write(body=BODY + '\nThe syntax `[label](../example)` illustrates Markdown. '
                   'Use inline ``[other](../example)`` as documentation.')
        self.assertTrue(validate_skill_definition(self.path).passed)

    def test_explicit_review_or_test_waivers_are_rejected(self):
        for instruction in ('No independent review is needed.', 'Tests are optional.',
                            'There is no need to test.', 'Testing is unnecessary.'):
            with self.subTest(instruction=instruction):
                self.write(body=BODY + '\n' + instruction)
                self.error('unsafe_work_cycle')

    def test_r1_standalone_inline_paths_reject_custom_traversal_and_drive_paths(self):
        for token in ('tools/missing.py', 'tools/../../outside.py',
                      r'C:\outside\input.txt', 'scripts/../../outside.py'):
            for delimiter in ('`', '``', '```'):
                with self.subTest(token=token, delimiter=delimiter):
                    self.write(body=BODY + '\nRun ' + delimiter + token + delimiter + '.')
                    self.error('missing_resource' if token == 'tools/missing.py' else 'unsafe_path')
                    with self.assertRaises(ValidationError): stage_skill(self.root, self.path, self.record)
                    self.assertFalse((self.root / 'capabilities/staging/count-items/1.0.0').exists())

    def test_r1_existing_custom_paths_and_code_span_examples_are_distinguished(self):
        (self.skill / 'tools').mkdir()
        (self.skill / 'tools/helper.py').write_text('print(1)')
        self.write(body=BODY + '\nRead ``tools/helper.py`` and `tools/helper.py`. '
                   'The markup ``[label](../illustration)`` is a literal example. '
                   'Command `python3 tools/../../placeholder.py --input INPUT` is a whole command example.')
        self.assertTrue(validate_skill_definition(self.path).passed)

    def test_r2_required_review_testing_grammar_is_not_a_waiver(self):
        for instruction in ('Conduct the independent review without bias, then run the tests.',
                            'No independent review is complete without tests.',
                            'Never proceed without independent review and testing.',
                            'Do not finish without running the tests.'):
            with self.subTest(instruction=instruction):
                self.write(body=BODY + '\n' + instruction)
                self.assertTrue(validate_skill_definition(self.path).passed)

    def test_r2_actual_omission_objects_remain_rejected(self):
        for instruction in ('Proceed without independent review.', 'Complete without testing.',
                            'Skip independent review and testing.', 'There is no need for review.',
                            'Independent review is optional. Tests are not required.'):
            with self.subTest(instruction=instruction):
                self.write(body=BODY + '\n' + instruction)
                self.error('unsafe_work_cycle')

    def test_r3_network_documentation_urls_are_external_while_local_escapes_fail(self):
        self.write(body=BODY + '\nSee [guide](//example.com/guide), '
                   '[long](//example.com/docs/../guide?q=../example).')
        self.assertTrue(validate_skill_definition(self.path).passed)
        for reference in ('/etc/passwd', 'file:///etc/passwd', '%2e%2e/outside', r'C:\outside\input.txt'):
            with self.subTest(reference=reference):
                self.write(body=BODY + '\n[resource](' + reference + ')')
                self.error('unsafe_path')

    def test_r4_angle_destinations_titles_and_spaces_use_common_containment(self):
        (self.skill / 'assets').mkdir()
        (self.skill / 'assets/items.txt').write_text('one')
        (self.skill / 'assets/items with spaces.txt').write_text('two')
        self.write(body=BODY + '\nRead [guide](<assets/items.txt> "Guide") and '
                   '[space](<assets/items with spaces.txt> "Space guide").\n'
                   '[reference][details]\n[details]: <assets/items with spaces.txt> "Items"\n')
        self.assertTrue(validate_skill_definition(self.path).passed)
        for reference in ('<../outside> "Escape"', '<assets/%2e%2e/outside> "Escape"',
                          '</outside file> "Escape"', '<file:///outside> "Escape"'):
            with self.subTest(reference=reference):
                self.write(body=BODY + '\n[resource](' + reference + ')')
                self.error('unsafe_path')

    def test_r5_compound_requirements_do_not_hide_later_test_waivers(self):
        for instruction in (
            'Never proceed without independent review, but skip testing for small changes.',
            'No independent review is complete without tests, but tests are optional for small changes.',
            'Never proceed without independent review but skip testing for small changes.',
            'No independent review is complete without tests but tests are optional for small changes.',
            'Never proceed without independent review and skip testing for small changes.',
            'No independent review is complete without tests and tests are optional for small changes.',
            'Do not finish without running the tests, yet omit review for small changes.',
            'No independent review is valid without tests although there is no need to test small changes.',
        ):
            with self.subTest(instruction=instruction):
                self.write(body=BODY + '\n' + instruction)
                self.error('unsafe_work_cycle')
                with self.assertRaises(ValidationError): stage_skill(self.root, self.path, self.record)
                self.assertFalse((self.root / 'capabilities/staging/count-items/1.0.0').exists())

    def test_r5_safe_requirements_preserve_step_objects_and_later_required_clauses(self):
        for instruction in (
            'Never proceed without independent review and testing.',
            'No independent review is complete without tests, and resolve feedback.',
            'Never proceed without independent review but also run the tests.',
            'Do not finish without running the tests and obtain independent review.',
        ):
            with self.subTest(instruction=instruction):
                self.write(body=BODY + '\n' + instruction)
                self.assertTrue(validate_skill_definition(self.path).passed)

    def test_r5_repeated_requirements_do_not_capture_intervening_waiver(self):
        self.write(body=BODY + '\nNo review is valid without tests but skip tests because '
                   'no review is valid without tests.')
        self.error('unsafe_work_cycle')
