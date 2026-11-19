"""Real CLI subprocess behavior; state, assets and evidence are temporary."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from smart_assistant.contracts import (
    Artifact, CheckMethod, CheckOutcome, CheckReceipt, CycleEvidence,
    ReviewReceipt, from_dict, to_dict,
)
from smart_assistant.quality import acceptance_snapshot, snapshot
from smart_assistant.lifecycle import DeploymentStore
from tests.test_catalog import candidate, receipt, write_json

ROOT = Path(__file__).resolve().parents[1]
STAMP = '2026-10-13T12:00:00Z'


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / 'state'
        self.record_path = self.root / 'record.json'
        self.wire = json.loads((ROOT / 'examples/contracts/TaskRecord.json').read_text())
        self.wire.update(status='queued', phase='design', cycles=[], capability_ids=[],
                         selection={'catalog_revision': 1, 'agents': [], 'skills': []},
                         blockers=[], resume_next_step='Implement report', artifact_root=str(self.root))
        self.save(self.wire)

    def save(self, value, path=None):
        path = path or self.record_path
        path.write_text(json.dumps(value), encoding='utf-8')
        return str(path)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'smart_assistant', *map(str, args)],
                              cwd=ROOT, text=True, capture_output=True, timeout=15)

    def response(self, expected, *args):
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertEqual(result.stderr, '')
        try:
            wire = json.loads(result.stdout)
        except ValueError:
            self.fail(f'Expected one JSON response; got {result.stdout!r}')
        self.assertEqual(set(wire), {'ok', 'data', 'errors'})
        self.assertIs(wire['ok'], expected == 0)
        self.assertEqual(bool(wire['errors']), expected != 0)
        return wire

    def create(self, status='queued', cycles=None, blockers=None):
        self.wire['status'] = status
        if cycles is not None:
            self.wire['cycles'] = cycles
        if blockers is not None:
            self.wire['blockers'] = blockers
        self.save(self.wire)
        return self.response(0, 'task', 'create', '--record', self.record_path,
                             '--state-dir', self.state)['data']

    def update(self, wire, expected, code=0):
        self.save(wire)
        return self.response(code, 'task', 'update', '--record', self.record_path,
                             '--expected-revision', expected, '--state-dir', self.state)

    def stored_bytes(self):
        return (self.state / 'tasks/task-01.json').read_bytes()

    def verified_cycle(self, number=1):
        (self.root / 'design.md').write_text('Write report and inspect supplied facts.\n')
        (self.root / 'report.txt').write_text('Report contains supplied facts.\n')
        (self.root / 'check.log').write_text('Synthetic test fixture inspected.\n')
        task = from_dict('TaskRecord', self.wire)
        artifact = snapshot(self.root, [Artifact('report', 'report.txt', '0' * 64)])
        acceptance = acceptance_snapshot(task.criteria, self.root / 'design.md')
        review = ReviewReceipt('reviewer:b', 'implementer:a', artifact.candidate_id,
                               acceptance.acceptance_id, STAMP, [])
        check = CheckReceipt('report_check', ['criterion-01'], artifact.candidate_id,
                             acceptance.acceptance_id, CheckMethod.OBSERVATION, None,
                             'Synthetic report inspected', {'fixture': 'only'},
                             CheckOutcome.PASS, 'check.log', STAMP)
        return to_dict(CycleEvidence(number, 'design.md', artifact, acceptance, review, [], [check]))

    def test_create_show_update_persist_revision_and_resume_step(self):
        created = self.create()
        self.assertEqual(created['revision'], 1)
        shown = self.response(0, 'task', 'show', created['id'], '--state-dir', self.state)
        self.assertEqual(shown['data'], created)
        created.update(status='running', phase='implement', resume_next_step='Review report')
        updated = self.update(created, 1)['data']
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['resume_next_step'], 'Review report')
        self.assertEqual(self.response(0, 'task', 'show', 'task-01', '--state-dir', self.state)['data'], updated)

    def test_duplicate_create_and_stale_update_conflict_without_overwrite(self):
        original = self.create()
        before = self.stored_bytes()
        self.response(3, 'task', 'create', '--record', self.record_path, '--state-dir', self.state)
        self.assertEqual(self.stored_bytes(), before)
        original['status'] = 'running'
        self.update(original, 1)
        before = self.stored_bytes()
        self.update(original, 1, code=3)
        self.assertEqual(self.stored_bytes(), before)

    def test_failed_update_is_reachable_explicit_resume(self):
        failed = self.create('failed')
        failed.update(status='running', resume_next_step='Retry failed check')
        resumed = self.update(failed, 1)['data']
        self.assertEqual((resumed['status'], resumed['revision']), ('running', 2))

    def test_history_drop_or_edit_rejected_but_new_cycle_appends(self):
        first = self.verified_cycle()
        current = self.create('running', [first])
        before = self.stored_bytes()
        for cycles in ([], [{**first, 'design_ref': 'other.md'}]):
            with self.subTest(cycles=cycles):
                self.update({**current, 'cycles': cycles}, 1, code=2)
                self.assertEqual(self.stored_bytes(), before)
        appended = self.update({**current, 'cycles': [first, self.verified_cycle(2)]}, 1)['data']
        self.assertEqual([c['cycle_number'] for c in appended['cycles']], [1, 2])
        self.assertEqual(appended['cycles'][0], first)

    def test_new_cycles_must_be_monotonic_contiguous(self):
        first = self.verified_cycle()
        current = self.create('running', [first])
        before = self.stored_bytes()
        self.update({**current, 'cycles': [first, self.verified_cycle(3)]}, 1, code=2)
        self.assertEqual(self.stored_bytes(), before)

    def test_complete_success_and_terminal_update_denied(self):
        current = self.create('verifying', [self.verified_cycle()])
        completed = self.response(0, 'task', 'complete', 'task-01', '--expected-revision', 1,
                                  '--state-dir', self.state)['data']
        self.assertEqual((completed['status'], completed['revision']), ('completed', 2))
        self.update(completed, 2, code=2)

    def test_complete_missing_evidence_denied_and_stale_revision_conflicts(self):
        self.create('verifying')
        before = self.stored_bytes()
        self.response(4, 'task', 'complete', 'task-01', '--expected-revision', 1, '--state-dir', self.state)
        self.assertEqual(self.stored_bytes(), before)
        self.response(3, 'task', 'complete', 'task-01', '--expected-revision', 99, '--state-dir', self.state)

    def test_both_completion_paths_reject_unresolved_blockers(self):
        current = self.create('verifying', [self.verified_cycle()], ['Need supplied source'])
        before = self.stored_bytes()
        self.response(4, 'task', 'complete', 'task-01', '--expected-revision', 1, '--state-dir', self.state)
        self.update({**current, 'status': 'completed'}, 1, code=4)
        self.assertEqual(self.stored_bytes(), before)

    def test_update_completed_requires_real_gate_even_with_no_blocker(self):
        current = self.create('verifying')
        before = self.stored_bytes()
        self.update({**current, 'status': 'completed'}, 1, code=4)
        self.assertEqual(self.stored_bytes(), before)

    def test_stale_artifact_or_changed_criteria_deny_completion(self):
        current = self.create('verifying', [self.verified_cycle()])
        before = self.stored_bytes()
        (self.root / 'report.txt').write_text('Changed after review')
        result = self.response(4, 'task', 'complete', 'task-01', '--expected-revision', 1, '--state-dir', self.state)
        self.assertIn('stale_candidate', [e['code'] for e in result['errors']])
        self.assertEqual(self.stored_bytes(), before)
        (self.root / 'report.txt').write_text('Report contains supplied facts.\n')
        current['criteria'][0]['description'] = 'Additional requirement'
        self.update({**current, 'status': 'completed'}, 1, code=4)
        self.assertEqual(self.stored_bytes(), before)

    def catalog_project(self):
        project = self.root / 'project'
        write_json(project / 'capabilities/catalog.json', {'schema_version': 1, 'revision': 1, 'records': []})
        return project

    def test_empty_catalog_validate_and_eligible(self):
        project = self.catalog_project()
        self.assertTrue(self.response(0, 'catalog', 'validate', '--project-root', project)['data']['passed'])
        tools = self.save([], self.root / 'tools.json')
        self.assertEqual(self.response(0, 'catalog', 'eligible', '--project-root', project, '--tools', tools)['data'], [])

    def test_catalog_validation_invalid_active_record_and_eligibility_boundaries(self):
        project = self.catalog_project()
        record = candidate(project)
        write_json(project / 'capabilities/catalog.json', {'schema_version': 1, 'revision': 1, 'records': [to_dict(replace(record, state='active'))]})
        self.response(2, 'catalog', 'validate', '--project-root', project)
        # Restore the empty catalog, then activate using synthetic helper receipts.
        write_json(project / 'capabilities/catalog.json', {'schema_version': 1, 'revision': 1, 'records': []})
        store = DeploymentStore(project)
        operation = store.prepare(record, 1)
        store.finalize(operation, receipt(record, operation))
        tools = self.save([], self.root / 'tools.json')
        self.assertEqual(self.response(0, 'catalog', 'eligible', '--project-root', project, '--tools', tools)['data'], [])
        self.save(['tool.write'], Path(tools))
        selected = self.response(0, 'catalog', 'eligible', '--project-root', project, '--tools', tools)['data']
        self.assertEqual([r['id'] for r in selected], ['worker'])
        (project / '.agents/skills/worker/references/help.txt').write_text('drift')
        self.assertEqual(self.response(0, 'catalog', 'eligible', '--project-root', project, '--tools', tools)['data'], [])

    def test_tools_input_rejects_nonlist_or_blank_values(self):
        project = self.catalog_project()
        for value in ({'secret': 'credential-marker'}, [''], [1], ['  ']):
            with self.subTest(value=value):
                tools = self.save(value, self.root / 'tools.json')
                self.response(2, 'catalog', 'eligible', '--project-root', project, '--tools', tools)

    def test_preflight_ready_missing_tools_and_no_inferred_authorization(self):
        request = json.loads((ROOT / 'examples/contracts/PreflightRequest.json').read_text())
        path = self.root / 'request.json'
        self.save(request, path)
        self.assertTrue(self.response(0, 'preflight', '--request', path)['data']['ready'])
        request['available_tools'] = []
        self.save(request, path)
        denied = self.response(4, 'preflight', '--request', path)
        self.assertEqual(denied['data']['missing_tools'], ['tool:local-write'])
        request['available_tools'] = request['required_tools']
        request['authorization'] = []
        self.save(request, path)
        denied = self.response(4, 'preflight', '--request', path)
        self.assertEqual([a['action_ref'] for a in denied['data']['pending_actions']], ['action-01'])

    def test_help_and_argument_errors_are_json_and_do_not_echo_secrets(self):
        for args in (('--help',), ('task', '--help'), ('task', 'complete', '--help')):
            result = self.response(0, *args)
            self.assertIn('usage:', result['data']['help'])
        for args in ((), ('unknown-credential-marker',), ('task',),
                     ('task', 'complete', 'task-01', '--expected-revision', 'credential-marker', '--state-dir', self.state),
                     ('task', 'show', 'task-01', '--state-dir', self.state, '--secret', 'credential-marker')):
            result = self.response(2, *args)
            self.assertNotIn('credential-marker', json.dumps(result))

    def test_malformed_contract_io_and_duplicate_json_errors_are_sanitized(self):
        cases = ['{"schema_version": 1, "secret": "credential-marker"}',
                 '{"id":"credential-marker",',
                 '{"schema_version":1,"schema_version":1}',
                 '{"schema_version":NaN}']
        for text in cases:
            self.record_path.write_text(text)
            result = self.response(2, 'task', 'create', '--record', self.record_path, '--state-dir', self.state)
            self.assertNotIn('credential-marker', json.dumps(result))
        missing = self.root / 'credential-marker.json'
        result = self.response(2, 'task', 'create', '--record', missing, '--state-dir', self.state)
        self.assertNotIn('credential-marker', json.dumps(result))
        self.response(2, 'task', 'show', 'missing-task', '--state-dir', self.state)

    def test_abbreviated_flags_are_invalid_without_mutating_task(self):
        current = self.create()
        current['status'] = 'running'
        self.save(current)
        before = self.stored_bytes()
        self.response(2, 'task', 'update', '--record', self.record_path,
                      '--expected-rev', 1, '--state-dir', self.state)
        self.assertEqual(self.stored_bytes(), before)

    def test_main_accepts_explicit_argv_and_returns_without_system_exit(self):
        result = subprocess.run([sys.executable, '-c',
            'from smart_assistant.cli import main; result=main(["--help"]); assert result == 0'],
            cwd=ROOT, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertIn('help', json.loads(result.stdout)['data'])


if __name__ == '__main__':
    unittest.main()
