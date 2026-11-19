"""Synthetic checker/runner tests; these are never registered host-demo proof."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ASSETS = Path(__file__).resolve().parents[1] / 'examples/scenarios/builtin-normalizer'


def load_checker():
    path = ASSETS / 'suite_checks.py'
    if not path.is_file():
        raise AssertionError('Required frozen capture checker is not implemented')
    spec = importlib.util.spec_from_file_location('builtin_suite_checks_tests', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SuiteCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import is delayed so preimplementation RED is an explicit assertion.
        cls.checker = None

    def setUp(self):
        self.checker = load_checker()
        self.manifest = json.loads((ASSETS / 'cases.json').read_text())

    def run_synthetic(self, *, fixed=True, mutation=None, go_mutation=None,
                      use_packet_path=False, capture_path='capture.json', post_run=None):
        with tempfile.TemporaryDirectory(prefix='synthetic-normalizer-harness-') as temp:
            root = Path(temp)
            for path in ASSETS.glob('*.py'):
                shutil.copy2(path, root / path.name)
            shutil.copy2(ASSETS / 'cases.json', root / 'cases.json')
            if fixed:
                (root / 'normalize.py').write_text(
                    'def normalize_spaces(text):\n    return " ".join(text.split())\n')
            go = {'task_id': 'synthetic-task', 'assignment_id': 'synthetic-assignment',
                  'dispatch_token': 'synthetic-token', 'capture_path': capture_path, 'run': {
                      'schema_version': '1.0', 'host_ref': 'synthetic-host',
                      'actor_ref': 'synthetic-worker', 'run_ref': 'synthetic-run',
                      'dispatch_token': 'synthetic-token',
                      'observed_at': '2026-01-01T00:00:00Z',
                      'observation_ref': 'synthetic-response.json'}}
            if go_mutation:
                go_mutation(go)
            (root / 'go.json').write_text(json.dumps(go))
            if mutation:
                mutation(root)
            command = [sys.executable, 'run_suite.py', '--run-info', 'go.json']
            if not use_packet_path:
                command += ['--capture', capture_path]
            proc = subprocess.run(command,
                                  cwd=root, capture_output=True, text=True)
            destination = root / capture_path
            try:
                capture = json.loads(destination.read_text()) if destination.is_file() else None
            except json.JSONDecodeError:
                capture = None  # A rejected protected-input alias still contains its original bytes.
            if post_run:
                post_run(root)
            return proc, capture, go

    def assert_invalid(self, capture, *, run=None, digests=None):
        result = self.checker.validate_capture(capture, self.manifest,
                                              expected_run=run, expected_digests=digests)
        self.assertFalse(result['valid'], result)
        self.assertFalse(result['complete'], result)
        self.assertTrue(result['errors'])
        self.assertEqual(result['exit_code'], 2)

    def test_complete_passing_capture(self):
        proc, cap, go = self.run_synthetic()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = self.checker.validate_capture(cap, self.manifest,
                       expected_run=go, expected_digests=cap['digests'])
        self.assertTrue(result['valid'], result)
        self.assertTrue(result['complete'])
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(cap['counts']['cases_passed'], 8)
        self.assertEqual(cap['counts']['inputs_passed'], 9)

    def test_packet_selects_unique_safe_capture_path_with_identical_command(self):
        commands = []
        for stage in ('reproduce', 'repair', 'qa'):
            proc, cap, go = self.run_synthetic(use_packet_path=True,
                                             capture_path=f'captures/{stage}.json')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIsNotNone(cap)
            self.assertTrue(self.checker.validate_capture(cap, self.manifest, expected_run=go)['valid'])
            commands.append(cap['command'])
        self.assertEqual(commands[0], commands[1])
        self.assertEqual(commands[1], commands[2])
        self.assertNotIn('--capture', commands[0])

    def test_packet_rejects_unsafe_capture_paths(self):
        for unsafe in ('/tmp/unsafe-capture.json', '../unsafe-capture.json',
                       'captures/../../unsafe.json', './capture.json',
                       'captures//capture.json', 'captures/./capture.json',
                       'C:\\unsafe.json', 'captures\\unsafe.json', '', '.', '..',
                       'normalize.py', 'go.json'):
            proc, cap, _ = self.run_synthetic(use_packet_path=True,
                go_mutation=lambda go: go.update(capture_path=unsafe))
            self.assertEqual(proc.returncode, 2, (unsafe, proc.stderr))
            self.assertIsNone(cap, unsafe)
            self.assertIn('capture_path', proc.stderr)

    def test_packet_rejects_symlink_escape_and_explicit_path_mismatch(self):
        def escaped(root):
            (root / 'captures').symlink_to(root.parent, target_is_directory=True)
        proc, cap, _ = self.run_synthetic(use_packet_path=True,
            capture_path='captures/synthetic-escape.json', mutation=escaped)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIsNone(cap)
        proc, cap, _ = self.run_synthetic(go_mutation=lambda go: go.update(capture_path='other.json'))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIsNotNone(cap)
        self.assert_invalid(cap)

    def test_malformed_manifest_is_diagnostic_exit_two_without_product_execution(self):
        for invalid in (None, {'cases': None}, {'cases': [{}]}):
            executed = []
            def mutate(root):
                (root / 'cases.json').write_text(json.dumps(invalid))
                product = root / 'normalize.py'
                product.write_text('from pathlib import Path\nPath("product-executed").touch()\n' + product.read_text())
            proc, cap, _ = self.run_synthetic(mutation=mutate,
                post_run=lambda root: executed.append((root / 'product-executed').exists()))
            self.assertEqual(proc.returncode, 2, (invalid, proc.stderr))
            self.assertIsNotNone(cap, invalid)
            self.assertFalse(cap['complete'])
            self.assertEqual(cap['exit_code'], 2)
            self.assertEqual(cap['counts']['tests_run'], 0)
            self.assertEqual(executed, [False])
            self.assert_invalid(cap)

    def test_unencodable_manifest_is_diagnostic_exit_two_without_product_execution(self):
        snapshots, after, executed = {}, {}, []
        def mutate(root):
            (root / 'cases.json').write_text('{"cases": "\\ud800"}')
            product = root / 'normalize.py'
            product.write_text('from pathlib import Path\nPath("product-executed").touch()\n' + product.read_text())
            snapshots['product'] = product.read_bytes()
        def observe(root):
            executed.append((root / 'product-executed').exists())
            after['product'] = (root / 'normalize.py').read_bytes()
        proc, cap, _ = self.run_synthetic(mutation=mutate, post_run=observe)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIsNotNone(cap)
        self.assertFalse(cap['complete'])
        self.assertEqual(cap['exit_code'], 2)
        self.assertIsNone(cap['manifest_contract_sha256'])
        self.assertEqual(cap['counts']['tests_run'], 0)
        self.assertEqual(executed, [False])
        self.assertEqual(after, snapshots)
        self.assert_invalid(cap)

    def test_protected_product_and_packet_hardlinks_are_preserved(self):
        for protected in ('normalize.py', 'go.json'):
            snapshots, after = {}, {}
            def mutate(root):
                destination = root / 'captures/hardlink.json'
                destination.parent.mkdir()
                destination.hardlink_to(root / protected)
                for name in ('normalize.py', 'go.json'):
                    snapshots[name] = (root / name).read_bytes()
            def observe(root):
                for name in snapshots:
                    after[name] = (root / name).read_bytes()
            proc, _, _ = self.run_synthetic(use_packet_path=True,
                capture_path='captures/hardlink.json', mutation=mutate, post_run=observe)
            self.assertEqual(after, snapshots, f'Protected input changed through {protected} hardlink')
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn('capture_path', proc.stderr)

    def test_safe_existing_ordinary_capture_can_be_rerun(self):
        def previous_capture(root):
            destination = root / 'captures/rerun.json'
            destination.parent.mkdir()
            destination.write_text('{"synthetic_previous_output": true}\n')
        proc, cap, _ = self.run_synthetic(use_packet_path=True,
            capture_path='captures/rerun.json', mutation=previous_capture)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(cap['complete'])
        self.assertTrue(self.checker.validate_capture(cap, self.manifest)['valid'])

    def test_output_write_failure_is_exit_two(self):
        def blocked_parent(root):
            (root / 'captures').write_text('synthetic non-directory parent')
        proc, cap, _ = self.run_synthetic(use_packet_path=True,
            capture_path='captures/output.json', mutation=blocked_parent)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIsNone(cap)
        self.assertIn('capture', proc.stderr)

    def test_complete_failing_capture_preserves_passing_regressions(self):
        proc, cap, _ = self.run_synthetic(fixed=False)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = self.checker.validate_capture(cap, self.manifest)
        self.assertTrue(result['valid'], result)
        self.assertTrue(result['complete'])
        self.assertEqual(result['exit_code'], 1)
        self.assertEqual(cap['counts']['cases_failed'], 4)
        self.assertEqual(cap['counts']['cases_passed'], 4)
        self.assertEqual(cap['counts']['inputs_failed'], 4)
        self.assertEqual(cap['counts']['inputs_passed'], 5)
        self.assertEqual(sum(len(row['inputs']) for row in cap['cases']), 9)
        self.assertIn('AssertionError', cap['raw_unittest_output'])

    def test_omitted_row_rejected_even_with_new_outer_hash(self):
        _, cap, _ = self.run_synthetic()
        cap['cases'].pop()
        new_digest = hashlib.sha256(json.dumps(cap, sort_keys=True).encode()).hexdigest()
        self.assertEqual(len(new_digest), 64)  # A new receipt hash does not restore membership.
        self.assert_invalid(cap)

    def test_duplicate_case_and_input_rejected(self):
        _, original, _ = self.run_synthetic()
        for mutate in (lambda c: c['cases'].append(copy.deepcopy(c['cases'][0])),
                       lambda c: c['cases'][-1]['inputs'].append(copy.deepcopy(c['cases'][-1]['inputs'][0]))):
            cap = copy.deepcopy(original)
            mutate(cap)
            self.assert_invalid(cap)

    def test_wrong_missing_extra_membership_rejected(self):
        _, original, _ = self.run_synthetic()
        for field in ('discovered_case_ids', 'executed_case_ids'):
            for replacement in ([], original[field] + ['extra'],
                                original[field][:-1] + [original[field][0]]):
                cap = copy.deepcopy(original)
                cap[field] = replacement
                self.assert_invalid(cap)

    def test_input_indexes_values_expectations_and_statuses_rejected(self):
        _, original, _ = self.run_synthetic()
        mutations = [lambda c: c['cases'][-1]['inputs'].pop(),
                     lambda c: next(row for row in c['cases'] if row['case_id'] == 'empty-blank')['inputs'][1].update(index=0),
                     lambda c: c['cases'][0]['inputs'][0].update(input='different'),
                     lambda c: c['cases'][0]['inputs'][0].update(expected='wrong'),
                     lambda c: c['cases'][0]['inputs'][0].update(observed='wrong'),
                     lambda c: c['cases'][0]['inputs'][0].update(status='not-run'),
                     lambda c: c['cases'][0].update(status='fail'),
                     lambda c: c['cases'][0].update(requirement_ids=['r04'])]
        for mutate in mutations:
            cap = copy.deepcopy(original)
            mutate(cap)
            self.assert_invalid(cap)

    def test_counts_raw_exit_and_complete_must_match(self):
        _, original, _ = self.run_synthetic()
        mutations = [lambda c: c['counts'].update(tests_run=7),
                     lambda c: c['counts'].update(inputs_passed=8),
                     lambda c: c.update(exit_code=1),
                     lambda c: c.update(complete=False),
                     lambda c: c.update(raw_unittest_output='OK\n'),
                     lambda c: c.update(harness_errors=['synthetic error'])]
        for mutate in mutations:
            cap = copy.deepcopy(original)
            mutate(cap)
            self.assert_invalid(cap)

    def test_digest_and_provenance_external_binding(self):
        _, cap, go = self.run_synthetic()
        wrong_go = copy.deepcopy(go)
        wrong_go['run']['run_ref'] = 'another-run'
        self.assert_invalid(cap, run=wrong_go)
        wrong_digests = dict(cap['digests'], **{'normalize.py': '0' * 64})
        self.assert_invalid(cap, digests=wrong_digests)
        for mutate in (lambda c: c['provenance']['run'].update(dispatch_token='wrong'),
                       lambda c: c['provenance'].update(capture_path='../unsafe.json'),
                       lambda c: c['provenance']['run'].update(observed_at='2099-01-01T00:00:00Z'),
                       lambda c: c['provenance']['run'].pop('actor_ref'),
                       lambda c: c['digests'].pop('test_normalize.py')):
            changed = copy.deepcopy(cap)
            mutate(changed)
            self.assert_invalid(changed)

    def test_removed_required_method_is_harness_error(self):
        def mutate(root):
            path = root / 'test_normalize.py'
            path.write_text(path.read_text().replace('def test_repeated_tabs(', 'def unused_repeated_tabs('))
        proc, cap, _ = self.run_synthetic(mutation=mutate)
        self.assertEqual(proc.returncode, 2)
        self.assert_invalid(cap)

    def test_extra_method_is_harness_error(self):
        def mutate(root):
            path = root / 'test_normalize.py'
            path.write_text(path.read_text() + '\n    def test_extra(self):\n        self._exercise("repeated-tabs")\n')
        proc, cap, _ = self.run_synthetic(mutation=mutate)
        self.assertEqual(proc.returncode, 2)
        self.assert_invalid(cap)

    def test_skips_errors_expected_failures_and_unexpected_successes_denied(self):
        changes = ["@unittest.skip('synthetic skip')\n    ",
                   '@unittest.expectedFailure\n    ']
        for decorator in changes:
            def mutate(root):
                path = root / 'test_normalize.py'
                path.write_text(path.read_text().replace('    def test_repeated_tabs(',
                                         '    ' + decorator + 'def test_repeated_tabs('))
            proc, cap, _ = self.run_synthetic(mutation=mutate)
            self.assertEqual(proc.returncode, 2)
            self.assert_invalid(cap)
            if 'expectedFailure' in decorator:
                proc, cap, _ = self.run_synthetic(fixed=False, mutation=mutate)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(cap['counts']['expected_failures'], 1)
                self.assert_invalid(cap)
        def broken_product(root):
            (root / 'normalize.py').write_text('def normalize_spaces(text):\n    raise ValueError("synthetic")\n')
        proc, cap, _ = self.run_synthetic(mutation=broken_product)
        self.assertEqual(proc.returncode, 2)
        self.assert_invalid(cap)

    def test_collection_error_and_token_mismatch_are_exit_two(self):
        def broken_tests(root):
            (root / 'test_normalize.py').write_text('raise ImportError("synthetic collection failure")\n')
        for kwargs in ({'mutation': broken_tests},
                       {'go_mutation': lambda g: g['run'].update(dispatch_token='wrong')}):
            proc, cap, _ = self.run_synthetic(**kwargs)
            self.assertEqual(proc.returncode, 2)
            self.assert_invalid(cap)

    def test_manifest_change_and_malformed_capture_fail_closed(self):
        _, cap, _ = self.run_synthetic()
        manifest = copy.deepcopy(self.manifest)
        manifest['cases'][0]['inputs'][0]['expected'] = 'changed'
        self.assertFalse(self.checker.validate_capture(cap, manifest)['valid'])
        for malformed in (None, [], {}, {'cases': None}):
            self.assertFalse(self.checker.validate_capture(malformed, self.manifest)['valid'])


if __name__ == '__main__':
    unittest.main()
