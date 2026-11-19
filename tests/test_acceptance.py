"""P09 public boundary composition. Every fixture receipt is HYPOTHETICAL.

Temporary state and subprocess CLI are real; no receipt establishes installed
client discovery, role invocation, independent review or native acceptance.
"""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import unittest

from smart_assistant.catalog import load_catalog
from smart_assistant.contracts import (
    CapabilityCatalog, CapabilityState, CheckOutcome, Criterion, ProbePurpose,
    TaskPhase, TaskStatus, ValidationError, from_dict, to_dict,
)
from smart_assistant.lifecycle import DeploymentStore
from smart_assistant.quality import completion_gate
from smart_assistant.state import TaskStore
from tests import test_wave2_integration as fixtures


class AcceptanceTests(unittest.TestCase):
    # Reuse fixture construction, not inherited package tests or mocked product APIs.
    setUp = fixtures.WaveTwoIntegrationTests.setUp
    write_json = fixtures.WaveTwoIntegrationTests.write_json
    cli = fixtures.WaveTwoIntegrationTests.cli
    task_fixture = fixtures.WaveTwoIntegrationTests.task_fixture
    update_cli = fixtures.WaveTwoIntegrationTests.update_cli
    complete_cli = fixtures.WaveTwoIntegrationTests.complete_cli
    saved_bytes = fixtures.WaveTwoIntegrationTests.saved_bytes
    staged_pair = fixtures.WaveTwoIntegrationTests.staged_pair
    eligible_cli = fixtures.WaveTwoIntegrationTests.eligible_cli

    def cycle(self, task, number, outcome=CheckOutcome.PASS):
        cycle = fixtures.WaveTwoIntegrationTests.cycle(self, task, number, outcome)
        (Path(task.artifact_root) / f'check-{number}.log').write_text(
            'HYPOTHETICAL P09 fixture observation; no native or independent review proof.\n')
        return replace(cycle,
            review=replace(cycle.review, reviewer_ref='HYPOTHETICAL:reviewer',
                           implementer_ref='HYPOTHETICAL:writer'),
            checks=[replace(cycle.checks[0], observation='HYPOTHETICAL local count fixture',
                            environment={'kind': 'HYPOTHETICAL'})])

    def ready_fixture(self, record):
        ready = fixtures.WaveTwoIntegrationTests.ready_fixture(self, record)
        (self.project / f'evidence/{record.id}-observation.txt').write_text(
            'HYPOTHETICAL lifecycle fixture; no installed native discovery or invocation.\n')
        return ready

    def probe(self, record, operation, **changes):
        probe = fixtures.WaveTwoIntegrationTests.synthetic_probe(self, record, operation)
        return replace(probe, **dict({'client_name': 'HYPOTHETICAL:client',
            'client_version': 'HYPOTHETICAL:client',
            'session_ref': f'HYPOTHETICAL:session-{operation}'}, **changes))

    def deny_complete_unchanged(self, task, code):
        before = (self.state / f'tasks/{task.id}.json').read_bytes()
        reply = self.complete_cli(task, 4)
        self.assertIn(code, [e['code'] for e in reply['errors']])
        self.assertEqual((self.state / f'tasks/{task.id}.json').read_bytes(), before)

    def test_interrupted_task_failed_resume_cas_and_terminal_followup_via_cli(self):
        task = replace(self.task_fixture(TaskStatus.RUNNING, outcome=CheckOutcome.FAIL),
                       phase=TaskPhase.IMPLEMENT, resume_next_step='Retry interrupted HYPOTHETICAL count')
        path = self.write_json(self.root / 'create.json', to_dict(task))
        self.cli(0, 'task', 'create', '--record', path, '--state-dir', self.state)
        store = TaskStore(self.state, completion_check=completion_gate)
        self.update_cli(replace(task, status=TaskStatus.PAUSED))
        interrupted = store.read(task.id)
        self.assertEqual(interrupted.resume_next_step, task.resume_next_step)
        self.update_cli(replace(interrupted, status=TaskStatus.RUNNING))
        self.update_cli(replace(store.read(task.id), status=TaskStatus.FAILED))
        failed = store.read(task.id)
        history = to_dict(failed)['cycles']
        self.update_cli(replace(failed, status=TaskStatus.RUNNING))
        resumed = store.read(task.id)
        before = self.saved_bytes()
        self.update_cli(replace(failed, status=TaskStatus.RUNNING), 3)
        self.assertEqual(self.saved_bytes(), before)
        for cycles in ([], [replace(resumed.cycles[0], checks=[])]):
            reply = self.update_cli(replace(resumed, cycles=cycles), 2)
            self.assertIn('history_changed', [e['code'] for e in reply['errors']])
            self.assertEqual(self.saved_bytes(), before)
        self.update_cli(replace(resumed, status=TaskStatus.VERIFYING, phase=TaskPhase.TESTING,
                               cycles=[*resumed.cycles, self.cycle(resumed, 2)]))
        self.complete_cli(store.read(task.id))
        completed = store.read(task.id)
        self.assertEqual(to_dict(completed)['cycles'][:1], history)
        self.assertEqual([c.checks[0].outcome for c in completed.cycles],
                         [CheckOutcome.FAIL, CheckOutcome.PASS])
        terminal = self.saved_bytes()
        reply = self.update_cli(replace(completed, status=TaskStatus.RUNNING), 2)
        self.assertIn('invalid_transition', [e['code'] for e in reply['errors']])
        self.assertEqual(self.saved_bytes(), terminal)
        followup = replace(completed, id='followup-task', revision=1, status=TaskStatus.QUEUED,
                           phase=TaskPhase.DESIGN, cycles=[], resume_next_step='Design follow-up')
        path = self.write_json(self.root / 'followup.json', to_dict(followup))
        self.cli(0, 'task', 'create', '--record', path, '--state-dir', self.state)
        self.assertEqual(store.read(followup.id).status, TaskStatus.QUEUED)
        self.assertEqual(self.saved_bytes(), terminal)

    def test_current_artifact_criteria_and_design_each_require_fresh_cycle(self):
        store = TaskStore(self.state, completion_check=completion_gate)
        current = store.create(self.task_fixture())
        original = to_dict(current.cycles[0])
        outputs = Path(current.artifact_root)
        for kind, code in (('artifact', 'stale_candidate'), ('criteria', 'stale_acceptance'),
                           ('design', 'stale_acceptance')):
            with self.subTest(changed=kind):
                if kind == 'artifact':
                    (outputs / 'report.txt').write_text('Count: 3\n')
                elif kind == 'criteria':
                    self.update_cli(replace(current, criteria=[Criterion(
                        'fixture-count', 'Updated count requirement', 'Inspect local report')]))
                    current = store.read(current.id)
                else:
                    (outputs / 'design.md').write_text('HYPOTHETICAL revised count design\n')
                self.deny_complete_unchanged(current, code)
                self.update_cli(replace(current, cycles=[*current.cycles,
                    self.cycle(current, len(current.cycles) + 1)]))
                current = store.read(current.id)
                self.assertTrue(completion_gate(current).passed)
                self.assertEqual(to_dict(current.cycles[0]), original)
        self.complete_cli(current)
        self.assertEqual(store.read(current.id).status, TaskStatus.COMPLETED)

    def test_current_review_checks_and_feedback_failures_survive_denied_cli_completion(self):
        store = TaskStore(self.state, completion_check=completion_gate)
        current = store.create(self.task_fixture())
        base = current.cycles[0]
        finding = from_dict('Finding', dict(id='hypothetical-finding', severity='minor',
            description='HYPOTHETICAL unresolved count finding', criterion_ids=['fixture-count']))
        variants = [
            ('same_reviewer_implementer', replace(base, review=replace(base.review,
                reviewer_ref=base.review.implementer_ref))),
            ('stale_review', replace(base, review=replace(base.review, candidate_id='0' * 64))),
            ('missing_criterion_coverage', replace(base, checks=[])),
            ('failed_check', replace(base, checks=[replace(base.checks[0], outcome=CheckOutcome.FAIL)])),
            ('unresolved_feedback', replace(base, review=replace(base.review, findings=[finding]))),
        ]
        for code, cycle in variants:
            with self.subTest(denial=code):
                numbered = replace(cycle, cycle_number=len(current.cycles) + 1)
                self.update_cli(replace(current, cycles=[*current.cycles, numbered]))
                current = store.read(current.id)
                self.deny_complete_unchanged(current, code)
        # Wire schema refuses an absent review before persistence, preserving history.
        wire = to_dict(current)
        wire['cycles'].append(dict(to_dict(base), cycle_number=len(current.cycles) + 1, review=None))
        before = self.saved_bytes()
        path = self.write_json(self.root / 'missing-review.json', wire)
        self.cli(2, 'task', 'update', '--record', path, '--expected-revision', current.revision,
                 '--state-dir', self.state)
        self.assertEqual(self.saved_bytes(), before)
        self.update_cli(replace(current, cycles=[*current.cycles, self.cycle(current, len(current.cycles) + 1)]))
        self.complete_cli(store.read(current.id))
        completed = store.read(current.id)
        self.assertEqual(completed.cycles[:-1], current.cycles)
        self.assertTrue(completion_gate(completed).passed)

    def test_catalog_draft_pending_disabled_missing_tools_and_drift_exclusion(self):
        staged, _ = self.staged_pair()
        ready = self.ready_fixture(staged[1])
        self.write_json(self.project / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [ready])))
        self.assertEqual(self.eligible_cli(['tool:local-read']), [])
        store = DeploymentStore(self.project)
        operation = store.prepare(ready, 1)
        self.assertEqual(self.eligible_cli(['tool:local-read']), [])
        store.finalize(operation, self.probe(ready, operation))
        self.assertEqual(self.eligible_cli([]), [])
        self.assertEqual([r['id'] for r in self.eligible_cli(['tool:local-read'])], [ready.id])
        (self.project / ready.deployed_path / 'references/scope.txt').write_text('HYPOTHETICAL drift')
        self.assertEqual(self.eligible_cli(['tool:local-read']), [])

    def test_complete_skill_disable_restore_and_reactivate_preserve_resource_bytes(self):
        staged, expected = self.staged_pair()
        ready = self.ready_fixture(staged[1])
        store = DeploymentStore(self.project)
        operation = store.prepare(ready, 1)
        active = store.finalize(operation, self.probe(ready, operation)).records[0]
        target = self.project / ready.deployed_path
        def deployed_files():
            return {p.relative_to(target).as_posix(): p.read_bytes()
                    for p in target.rglob('*') if p.is_file()}
        self.assertEqual(deployed_files(), expected[1])
        original_catalog = (self.project / 'capabilities/catalog.json').read_bytes()
        operation = store.prepare_disable(active.id, 2)
        self.assertFalse(target.exists())
        self.assertEqual(self.eligible_cli(['tool:local-read']), [])
        prior = json.loads((self.project / active.discovery_probe_ref).read_text())
        absence = replace(self.probe(active, operation), purpose=ProbePurpose.DISABLE,
                          discovered=False, invoked=None)
        with self.assertRaises(ValidationError):
            store.finalize_disable(operation, replace(absence, session_ref=prior['session_ref']))
        self.assertEqual(self.eligible_cli(['tool:local-read']), [])
        store.restore(operation)
        self.assertEqual(deployed_files(), expected[1])
        self.assertEqual((self.project / 'capabilities/catalog.json').read_bytes(), original_catalog)
        operation = store.prepare_disable(active.id, 2)
        absence = replace(self.probe(active, operation), purpose=ProbePurpose.DISABLE,
                          discovered=False, invoked=None)
        disabled = store.finalize_disable(operation, absence)
        self.assertEqual(disabled.records[0].state, CapabilityState.DISABLED)
        self.assertEqual(self.eligible_cli(['tool:local-read']), [])
        with self.assertRaises(ValidationError):
            store.restore(operation)
        operation = store.prepare(ready, 3)
        store.finalize(operation, self.probe(ready, operation))
        self.assertEqual(deployed_files(), expected[1])
        self.assertEqual([r['id'] for r in self.eligible_cli(['tool:local-read'])], [ready.id])

    def test_probe_mismatches_restore_pending_assets_without_catalog_activation(self):
        staged, _ = self.staged_pair()
        ready = self.ready_fixture(staged[1])
        store = DeploymentStore(self.project)
        before = (self.project / 'capabilities/catalog.json').read_bytes()
        for mismatch in ({'operation_id': 'HYPOTHETICAL:wrong-operation'}, {'version': '9.0.0'},
                         {'manifest_sha256': '0' * 64}, {'purpose': ProbePurpose.DISABLE},
                         {'observed_at': '2000-01-01T00:00:00Z'}, {'invoked': False}):
            with self.subTest(mismatch=mismatch):
                operation = store.prepare(ready, 1)
                self.assertEqual(self.eligible_cli(['tool:local-read']), [])
                with self.assertRaises(ValidationError):
                    store.finalize(operation, self.probe(ready, operation, **mismatch))
                self.assertFalse((self.project / ready.deployed_path).exists())
                self.assertEqual((self.project / 'capabilities/catalog.json').read_bytes(), before)
                self.assertEqual(self.eligible_cli(['tool:local-read']), [])

    def test_required_failed_or_blocked_child_can_recover_without_rewriting_sibling(self):
        source = fixtures.ROOT / 'examples/scenarios/delegation/scenario.py'
        spec = importlib.util.spec_from_file_location('p09_hypothetical_scenario', source)
        scenario = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scenario)
        for case in ('blocked', 'failed'):
            with self.subTest(case=case):
                root = self.root / case
                root.mkdir()
                result = scenario.run_case(case, root)
                self.assertTrue(result['hypothetical'])
                self.state = root / 'state'
                store = TaskStore(self.state, completion_check=completion_gate)
                parent = store.read('parent-demo')
                self.deny_complete_unchanged(parent, 'unresolved_blockers')
                sibling = (root / 'outputs/a.md').read_bytes()
                history = {p.name: p.read_bytes() for p in (root / 'hypothetical-history').glob('child-*.json')}
                failed_cycle = to_dict(parent.cycles[0])
                assignment_wire = result['saved_dispatches'][1]['assignment']
                assignment_wire['assignment_revision'] += 1
                assignment = from_dict('TaskAssignment', assignment_wire)
                (root / 'outputs/b.md').write_text('HYPOTHETICAL repaired child-b output\n')
                wire = result['saved_dispatches'][0]['handoff']
                from smart_assistant.contracts import validate_handoff
                from smart_assistant.quality import snapshot
                artifact = snapshot(root, [replace(parent.cycles[0].candidate.artifacts[0],
                    id='repaired-b', relative_path='outputs/b.md')]).artifacts[0]
                repaired = from_dict('Handoff', dict(wire, task_id=assignment.task_id,
                    assignment_revision=assignment.assignment_revision, artifacts=[to_dict(artifact)]))
                self.assertTrue(validate_handoff(assignment, repaired, root).passed)
                self.update_cli(replace(parent, blockers=[], resume_next_step='Review combined repaired outputs'))
                current = store.read(parent.id)
                candidate = snapshot(root, [*current.cycles[0].candidate.artifacts, artifact])
                cycle = replace(current.cycles[0], cycle_number=2, candidate=candidate,
                    review=replace(current.cycles[0].review, candidate_id=candidate.candidate_id),
                    checks=[replace(current.cycles[0].checks[0], candidate_id=candidate.candidate_id)])
                self.update_cli(replace(current, cycles=[*current.cycles, cycle]))
                self.complete_cli(store.read(parent.id))
                completed = store.read(parent.id)
                self.assertEqual(completed.status, TaskStatus.COMPLETED)
                self.assertEqual(to_dict(completed.cycles[0]), failed_cycle)
                self.assertEqual((root / 'outputs/a.md').read_bytes(), sibling)
                self.assertEqual({p.name: p.read_bytes() for p in (root / 'hypothetical-history').glob('child-*.json')}, history)

    def test_cancelled_cli_record_requires_separate_followup_and_preserves_partial_output(self):
        store = TaskStore(self.state, completion_check=completion_gate)
        current = store.create(self.task_fixture(TaskStatus.RUNNING))
        self.update_cli(replace(current, status=TaskStatus.CANCELLED, resume_next_step='Create a follow-up task'))
        cancelled = store.read(current.id)
        before = self.saved_bytes()
        output = (Path(cancelled.artifact_root) / 'report.txt').read_bytes()
        reply = self.update_cli(replace(cancelled, status=TaskStatus.RUNNING), 2)
        self.assertIn('invalid_transition', [e['code'] for e in reply['errors']])
        self.assertEqual(self.saved_bytes(), before)
        followup = replace(cancelled, id='cancelled-followup', revision=1, status=TaskStatus.QUEUED, cycles=[])
        path = self.write_json(self.root / 'cancelled-followup.json', to_dict(followup))
        self.cli(0, 'task', 'create', '--record', path, '--state-dir', self.state)
        self.assertEqual(store.read(followup.id).status, TaskStatus.QUEUED)
        self.assertEqual(self.saved_bytes(), before)
        self.assertEqual((Path(cancelled.artifact_root) / 'report.txt').read_bytes(), output)


if __name__ == '__main__':
    unittest.main()
