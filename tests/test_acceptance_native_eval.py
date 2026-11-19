"""Synthetic adapter contracts; never installed-client/native acceptance proof."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'examples/scenarios/acceptance/native_eval.py'
ROLES = ('engineering-lead', 'writer', 'reviewer')
SKILLS = ('request-coordination', 'manage-agent', 'manage-skill', 'delegate-work', 'draft-document', 'verify-completion')


class AcceptanceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SOURCE.is_file(), 'P09 acceptance adapter is not implemented')
        spec = importlib.util.spec_from_file_location('p09_eval', SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project, self.fixture, self.output = (self.base / n for n in ('source', 'fixture', 'evaluation'))
        self.fixture.mkdir()
        (self.fixture / 'notes.md').write_text('Supplied fact')
        for role in ROLES:
            self.write('.codex/agents/' + role + '.toml', 'name = "' + role + '"')
        for skill in SKILLS:
            self.write('.agents/skills/' + skill + '/SKILL.md', 'Fixture ' + skill)
            self.write('.agents/skills/' + skill + '/references/nested.txt', 'Complete resource')
        self.write('smart_assistant/__init__.py', '# exact helper')
        self.write('smart_assistant/nested/api.py', '# nested helper')
        self.write('.smart-assistant/private.json', 'NEVER COPY')
        self.prompt = self.base / 'prompt.txt'
        self.prompt.write_text('Explicit finite prompt')

    def write(self, name, content):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def prepare(self):
        return self.module.prepare(self.project, self.fixture, self.output)

    def test_complete_exact_copy_with_no_private_or_model_calls(self):
        root, copied = self.prepare()
        self.assertEqual(self.module.SKILLS, SKILLS)
        for skill in SKILLS:
            self.assertIn('.agents/skills/' + skill + '/references/nested.txt', copied)
        self.assertIn('smart_assistant/nested/api.py', copied)
        self.assertEqual((root / 'notes.md').read_text(), 'Supplied fact')
        self.assertFalse((root / '.smart-assistant').exists())
        self.assertFalse((self.output / 'events.jsonl').exists())
        before = json.loads((self.output / 'manifest-before.json').read_text())
        self.assertEqual(before['files'], copied)
        self.assertTrue(self.module.capture_after(root, copied, before)['sources_unchanged'])

    def test_output_existing_or_inside_inputs_rejected(self):
        self.output.mkdir()
        for output in (self.output, self.project / 'out', self.fixture / 'out'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.module.prepare(self.project, self.fixture, output)

    def test_output_may_have_new_parent_directories(self):
        root, _ = self.module.prepare(self.project, self.fixture, self.base / 'new/deep/run')
        self.assertTrue(root.is_dir())

    def test_rejects_collision_even_empty_directories(self):
        for name in ('.codex', '.agents', 'smart_assistant', '.git', '.smart-assistant', 'private-state', 'AGENTS.md'):
            with self.subTest(name=name):
                path = self.fixture / name
                path.mkdir()
                with self.assertRaises(ValueError):
                    self.prepare()
                path.rmdir()
                self.assertFalse(self.output.exists())

    def test_fixture_root_symlink_rejected(self):
        link = self.base / 'link'
        link.symlink_to(self.fixture, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.module.prepare(self.project, link, self.output)

    def test_symlinked_source_ancestor_rejected(self):
        original = self.project / '.codex'
        original.rename(self.project / 'actual-codex')
        original.symlink_to(self.project / 'actual-codex', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_nonregular_and_symlink_fixture_entries_rejected(self):
        path = self.fixture / 'unsafe'
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            self.prepare()
        path.unlink()
        path.symlink_to(self.prompt)
        with self.assertRaises(ValueError):
            self.prepare()

    def test_missing_and_nonregular_resources_fail_before_output(self):
        path = self.project / '.agents/skills/manage-agent/references/fifo'
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            self.prepare()
        path.unlink()
        (self.project / '.agents/skills/manage-agent/SKILL.md').unlink()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_source_changes_during_copy_retained_as_failure(self):
        copy = self.module.shutil.copy2
        changed = False
        def mutate(source, target):
            nonlocal changed
            result = copy(source, target)
            if not changed:
                Path(source).write_text('Changed during copy')
                changed = True
            return result
        with patch.object(self.module.shutil, 'copy2', side_effect=mutate), self.assertRaises(ValueError):
            self.prepare()

    def test_new_helper_source_during_copy_rejected(self):
        copy = self.module.shutil.copy2
        def add_source(source, target):
            result = copy(source, target)
            self.write('smart_assistant/added.py', '# new input source')
            return result
        with patch.object(self.module.shutil, 'copy2', side_effect=add_source), self.assertRaises(ValueError):
            self.prepare()

    def test_after_detects_new_helper_source(self):
        root, copied = self.prepare()
        before = json.loads((self.output / 'manifest-before.json').read_text())
        (root / 'smart_assistant/added.py').write_text('# new helper')
        after = self.module.capture_after(root, copied, before)
        self.assertFalse(after['sources_unchanged'])
        self.assertIn('smart_assistant/added.py', after['helper_files'])

    def test_after_detects_source_fixture_config_and_new_assets(self):
        root, copied = self.prepare()
        before = json.loads((self.output / 'manifest-before.json').read_text())
        (root / 'notes.md').write_text('Changed')
        (root / 'smart_assistant/__init__.py').write_text('Changed')
        (root / '.codex/config.toml').write_text('Changed')
        new = root / '.codex/agents/new-fixture.toml'
        new.write_text('name = "new-fixture"')
        after = self.module.capture_after(root, copied, before)
        for field in ('sources_unchanged', 'fixture_unchanged', 'config_unchanged', 'native_assets_unchanged'):
            self.assertFalse(after[field])
        self.assertIn('.codex/agents/new-fixture.toml', after['native_assets'])

    def test_after_detects_parent_symlink_without_following(self):
        root, copied = self.prepare()
        before = json.loads((self.output / 'manifest-before.json').read_text())
        path = root / 'smart_assistant'
        path.rename(root / 'old-helper')
        path.symlink_to(self.project / 'smart_assistant', target_is_directory=True)
        self.assertFalse(self.module.capture_after(root, copied, before)['sources_unchanged'])

    def args(self):
        return ['--project', str(self.project), '--fixture', str(self.fixture), '--output', str(self.output), '--prompt', str(self.prompt)]

    def test_cli_prepare_explicit_gate_and_timeout_validation(self):
        for timeout in ('0', '901'):
            result = subprocess.run([sys.executable, str(SOURCE), *self.args(), '--timeout', timeout], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.output.exists())
        result = subprocess.run([sys.executable, str(SOURCE), *self.args(), '--cli', '/does/not/exist'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['model_calls'], 0)

    def test_run_rejects_invalid_timeout_before_cli(self):
        root, copied = self.prepare()
        for timeout in (0, 901, True, 1.5):
            with self.assertRaises(ValueError):
                self.module.run('/does/not/exist', root, self.output, 'prompt', timeout, copied)
        self.assertFalse((self.output / 'events.jsonl').exists())

    def test_explicit_run_failure_retains_unassessed_raw_result(self):
        root, copied = self.prepare()
        result = self.module.run('/does/not/exist', root, self.output, 'prompt', 1, copied)
        self.assertIn('UNASSESSED', result['acceptance'])
        self.assertIn('execution_error', result)
        self.assertTrue((self.output / 'stderr.log').exists())
        self.assertTrue((self.output / 'manifest-after.json').exists())
        self.assertFalse((self.output / 'activation-receipt.json').exists())

    def fake_cli(self, behavior):
        """Synthetic local protocol fixture, never actual native proof."""
        path = self.base / 'synthetic-cli'
        path.write_text('#!' + sys.executable + '\n' +
            'import json, sys, time\n' +
            'if "app-server" in sys.argv:\n' +
            ' for line in sys.stdin:\n' +
            '  request=json.loads(line)\n' +
            '  if "id" not in request: continue\n' +
            '  method=request["method"]\n' +
            '  result={"config":{"agents":{"fixture-new":{"description":"dynamic"}}}} if method=="config/read" else {"data":[{"skills":[{"name":"fixture-new-skill","path":"new"}]}]} if method=="skills/list" else {}\n' +
            '  print(json.dumps({"id":request["id"],"result":result}),flush=True)\n' +
            'else:\n' + behavior + '\n')
        path.chmod(0o700)
        return str(path)

    def test_synthetic_public_observer_retains_dynamic_discovery(self):
        import asyncio
        root, copied = self.prepare()
        cli = self.fake_cli(' print("synthetic")')
        proof = asyncio.run(self.module.observe(cli, root, None, self.output))
        self.assertIn('fixture-new', proof['agents'])
        self.assertEqual(proof['skills'][0]['name'], 'fixture-new-skill')
        self.assertIn('UNASSESSED', proof['acceptance'])
        self.assertEqual(proof['native_assets'], json.loads((self.output / 'manifest-before.json').read_text())['native_assets'])

    def test_synthetic_secret_markers_excluded_from_saved_projection(self):
        import asyncio
        root, copied = self.prepare()
        cli = self.fake_cli(' print("synthetic")')
        config = {'config': {
            'model': 'synthetic-model', 'model_reasoning_effort': 'high',
            'unrelated_secret': 'HYPOTHETICAL_CONFIG_SECRET',
            'agents': {'fixture-new': {
                'description': 'Dynamic role', 'config_file': '/synthetic/role.toml',
                'model': 'role-model', 'model_reasoning_effort': 'medium',
                'nested': {'secret': 'HYPOTHETICAL_ROLE_SECRET'}}}},
            'layers': [{'config': {'arbitrary_private': 'HYPOTHETICAL_LAYER_SECRET'}}]}
        skills = {'data': [{'skills': [{'name': 'fixture-new-skill', 'path': '/synthetic/SKILL.md',
            'description': 'Dynamic skill', 'enabled': True, 'source': 'repository',
            'extra': {'secret': 'HYPOTHETICAL_SKILL_SECRET'}}]}],
            'private': 'HYPOTHETICAL_SKILL_RESPONSE_SECRET'}
        script = Path(cli).read_text()
        line = next(line for line in script.splitlines() if line.startswith('  result='))
        script = script.replace(line, '  result=' + repr(config) + ' if method=="config/read" else ' + repr(skills) + ' if method=="skills/list" else {}')
        Path(cli).write_text(script)
        proof = asyncio.run(self.module.observe(cli, root, None, self.output))
        saved = (self.output / 'public-proof.json').read_text()
        self.assertNotIn('HYPOTHETICAL_', saved)
        self.assertNotIn('config_response', proof)
        self.assertNotIn('skills_response', proof)
        self.assertEqual(proof['settings'], {'model': 'synthetic-model', 'model_reasoning_effort': 'high'})
        role = proof['agents']['fixture-new']
        self.assertEqual(role['config_file'], '/synthetic/role.toml')
        self.assertEqual(role['model'], 'role-model')
        self.assertEqual(role['model_reasoning_effort'], 'medium')
        self.assertEqual(proof['skills'][0]['name'], 'fixture-new-skill')
        self.assertEqual(proof['skills'][0]['path'], '/synthetic/SKILL.md')

    def test_synthetic_nonzero_run_preserves_raw_and_cannot_retry(self):
        root, copied = self.prepare()
        cli = self.fake_cli(' print("synthetic failure",file=sys.stderr)\n sys.exit(7)')
        result = self.module.run(cli, root, self.output, 'finite', 1, copied)
        self.assertEqual(result['exit_code'], 7)
        self.assertIn('synthetic failure', (self.output / 'stderr.log').read_text())
        self.assertIn('UNASSESSED', result['acceptance'])
        command = json.loads((self.output / 'command.json').read_text())
        self.assertEqual(command[1:6], ['--no-daemon', '-a', 'on-request', '-s', 'workspace-write'])
        with self.assertRaises(ValueError):
            self.module.run(cli, root, self.output, 'retry', 1, copied)

    def test_synthetic_timeout_retained_as_unassessed(self):
        root, copied = self.prepare()
        cli = self.fake_cli(' print("synthetic prior output",flush=True)\n time.sleep(10)')
        result = self.module.run(cli, root, self.output, 'finite', 1, copied)
        self.assertTrue(result['timed_out'])
        self.assertIn('synthetic prior output', (self.output / 'events.jsonl').read_text())
        self.assertIn('UNASSESSED', result['acceptance'])


if __name__ == '__main__':
    unittest.main()
