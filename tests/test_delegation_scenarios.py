"""Hypothetical local scenarios, never installed-native proof."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'examples/scenarios/delegation/scenario.py'

class DelegationScenarioTests(unittest.TestCase):
    def run_case(self, case):
        self.assertTrue(SOURCE.exists(), 'Runnable delegation helper is missing')
        spec = importlib.util.spec_from_file_location('delegation_scenario', SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            return module.run_case(case, Path(directory).resolve())

    def test_two_child_handoffs_complete_real_parent(self):
        result = self.run_case('positive')
        self.assertEqual(result['accepted_children'], ['child-a', 'child-b'])
        self.assertEqual(result['parent_status'], 'completed')
        self.assertTrue(result['hypothetical'])

    def test_stale_handoff_rejected(self):
        result = self.run_case('stale')
        self.assertIn('stale_assignment', result['errors'])
        history = result['saved_dispatches'][0]
        self.assertEqual(history['handoff']['assignment_revision'], 1)
        self.assertEqual(history['assignment']['assignment_revision'], 2)
        self.assertFalse(history['gate']['passed'])

    def test_wrong_ownership_rejected(self):
        self.assertIn('outside_ownership', self.run_case('ownership')['errors'])

    def test_blocked_required_child_is_persisted_and_denies_completion(self):
        result = self.run_case('blocked')
        self.assertEqual(result['accepted_children'], ['child-a'])
        self.assertEqual(result['parent_status'], 'verifying')
        self.assertTrue(result['parent_blockers'])
        self.assertTrue(result['completion_denied'])
        self.assertEqual(result['preserved_outputs'], ['outputs/a.md'])

    def test_cancelled_parent_stays_terminal_and_preserves_partial_output(self):
        result = self.run_case('cancelled')
        self.assertEqual(result['parent_status'], 'cancelled')
        self.assertTrue(result['resume_denied'])
        self.assertEqual(result['preserved_outputs'], ['outputs/a.md'])

    def test_failed_child_preserves_successful_sibling_and_partial_failure(self):
        result = self.run_case('failed')
        self.assertEqual(result['accepted_children'], ['child-a'])
        self.assertEqual(result['parent_status'], 'verifying')
        self.assertTrue(result['completion_denied'])
        self.assertEqual(result['preserved_outputs'], ['outputs/a.md', 'outputs/b.md'])
        self.assertEqual(result['saved_dispatches'][1]['handoff']['result'], 'failed')
        self.assertEqual(len(result['saved_dispatches'][1]['handoff']['artifacts']), 1)

    def test_dependency_dispatched_only_after_predecessor_acceptance(self):
        result = self.run_case('dependent')
        self.assertEqual(result['timeline'], ['dispatch-a', 'accept-a', 'dispatch-b', 'accept-b'])
        self.assertEqual(result['parent_status'], 'completed')

class NativeEvaluatorPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        spec = importlib.util.spec_from_file_location('native_eval', SOURCE.with_name('native_eval.py'))
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.project, self.fixture = self.root / 'source', self.root / 'fixture'
        self.fixture.mkdir()
        (self.fixture / 'notes-a.md').write_text('Original fixture')
        for role in self.module.ROLES:
            path = self.project / '.codex/agents' / (role + '.toml')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('name = "' + role + '"')
        for skill in self.module.SKILLS:
            path = self.project / '.agents/skills' / skill / 'SKILL.md'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Fixture skill ' + skill)
        path = self.project / 'smart_assistant/__init__.py'
        path.parent.mkdir()
        path.write_text('# Fixture helper')

    def test_prepare_copies_exact_sources_and_fixtures_without_model_call(self):
        import json
        output = self.root / 'evaluation'
        prepared, sources = self.module.prepare(self.project, self.fixture, output)
        self.assertEqual((prepared / 'notes-a.md').read_text(), 'Original fixture')
        self.assertIn('.codex/agents/engineering-lead.toml', sources)
        self.assertIn('.agents/skills/delegate-work/SKILL.md', sources)
        self.assertEqual(json.loads((output / 'manifest-before.json').read_text())['files'], sources)
        self.assertFalse((output / 'events.jsonl').exists())
        with self.assertRaises(ValueError):
            self.module.prepare(self.project, self.fixture, output)

    def test_missing_asset_fails_before_creating_output(self):
        (self.project / '.codex/agents/engineering-lead.toml').unlink()
        output = self.root / 'evaluation'
        with self.assertRaises(ValueError):
            self.module.prepare(self.project, self.fixture, output)
        self.assertFalse(output.exists())

    def test_fixture_cannot_replace_helpers(self):
        (self.fixture / 'smart_assistant').mkdir()
        (self.fixture / 'smart_assistant/__init__.py').write_text('overwrite')
        with self.assertRaises(ValueError):
            self.module.prepare(self.project, self.fixture, self.root / 'evaluation')

    def test_symlinked_source_directory_rejected(self):
        directory = self.project / '.codex/agents'
        directory.rename(self.project / 'actual-agents')
        directory.symlink_to(self.project / 'actual-agents', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.module.prepare(self.project, self.fixture, self.root / 'evaluation')

    def test_symlinked_skill_subdirectory_rejected_before_output(self):
        directory = self.project / '.agents/skills/delegate-work/resources'
        external = self.root / 'resources'
        external.mkdir()
        (external / 'resource.txt').write_text('Resource')
        directory.symlink_to(external, target_is_directory=True)
        output = self.root / 'evaluation'
        with self.assertRaises(ValueError):
            self.module.prepare(self.project, self.fixture, output)
        self.assertFalse(output.exists())

    def test_nonregular_source_resource_rejected_before_output(self):
        import os
        resource = self.project / '.agents/skills/delegate-work/resource.fifo'
        os.mkfifo(resource)
        with self.assertRaises(ValueError):
            self.module.prepare(self.project, self.fixture, self.root / 'evaluation')

    def test_after_manifest_detects_input_and_config_changes(self):
        import json
        output = self.root / 'evaluation'
        prepared, sources = self.module.prepare(self.project, self.fixture, output)
        before = json.loads((output / 'manifest-before.json').read_text())
        initial = self.module.capture_after(prepared, sources, before)
        self.assertTrue(initial['fixture_unchanged'])
        self.assertTrue(initial['config_unchanged'])
        (prepared / 'notes-a.md').write_text('Tampered input')
        (prepared / '.codex/config.toml').write_text('Tampered config')
        final = self.module.capture_after(prepared, sources, before)
        self.assertFalse(final['fixture_unchanged'])
        self.assertFalse(final['config_unchanged'])
        self.assertTrue(final['sources_unchanged'])
