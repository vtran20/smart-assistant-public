"""SYNTHETIC builtin persistence/P12 regressions, not actual host demo evidence."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest

from smart_assistant import builtin_records as b, contracts as c
from smart_assistant import delivery_evidence as ev
from tests.builtin_evidence_fixtures import builtin_evidence_fixture


class BuiltinFixtureContractTests(unittest.TestCase):
    def test_prepared_history_receipts_and_separate_roots_are_valid_core_records(self):
        fixture = builtin_evidence_fixture(self, persist=False)
        previous = None
        for snapshot in fixture.history:
            checked = b.validate_builtin(snapshot, fixture.task, previous)
            self.assertTrue(checked.passed, checked.errors)
            previous = snapshot
        self.assertEqual(len(fixture.history), 9)
        self.assertEqual(len(set([fixture.task.artifact_root, *map(str, fixture.workers)])), 3)
        self.assertFalse(fixture.delivery.policy.reproduction_required)
        self.assertIsNone(fixture.bundle.baseline_candidate_id)
        self.assertFalse(any(entry.kind == 'before' for entry in fixture.bundle.entries))
        self.assertEqual(ev.evidence_from_dict(ev.evidence_to_dict(fixture.bundle)), fixture.bundle)
        checked = b.validate_builtin_receipts(fixture.delivery, Path(fixture.task.artifact_root))
        self.assertTrue(checked.passed, checked.errors)
        for i, assignment in enumerate(fixture.delivery.assignments):
            ready = fixture.history[3 + i * 4].assignments[i]
            original = fixture.history[1 + i * 4].assignments[i]
            sub = fixture.delivery.submissions[i]
            intent = fixture.delivery.dispatches[i]
            checked = b.validate_builtin_submission(ready, sub, intent, fixture.workers[i], dispatched_envelope=original)
            self.assertTrue(checked.passed, checked.errors)


class BuiltinEvidenceIntegrationTests(unittest.TestCase):
    def fixture(self):
        return builtin_evidence_fixture(self)

    def cli(self, *args):
        result = subprocess.run([sys.executable, '-m', 'smart_assistant', *map(str, args)],
            cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=15)
        return result, json.loads(result.stdout)

    def assert_completion_denied_preserves_task(self, fixture):
        path = fixture.state / 'tasks' / f'{fixture.task.id}.json'
        before = path.read_bytes()
        with self.assertRaises(c.ValidationError):
            fixture.tasks.update(replace(fixture.task, status=c.TaskStatus.COMPLETED), fixture.task.revision)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(fixture.tasks.read(fixture.task.id), fixture.task)

    def test_prepared_builtin_bundle_uses_public_p12_gate(self):
        fixture = builtin_evidence_fixture(self, persist=False)
        checked = ev.validate_delivery_evidence(fixture.task, fixture.delivery,
                                               fixture.bundle, fixture.data.root)
        self.assertTrue(checked.passed, checked.errors)

    def test_saved_builtin_evidence_check_and_passing_callback_complete(self):
        fixture = self.fixture()
        saved = fixture.save()
        self.assertEqual(fixture.evidence.read(fixture.task.id), saved)
        checked = fixture.evidence.check(fixture.task.id)
        self.assertTrue(checked.passed, checked.errors)
        for intent in fixture.delivery.dispatches:
            historical = fixture.deliveries.dispatch_envelope(fixture.task.id, intent.dispatch_token)
            self.assertEqual(historical.state, 'dispatched')
            self.assertEqual(b.builtin_digest(historical), intent.envelope_sha256)
        completed = fixture.tasks.update(replace(fixture.task, status=c.TaskStatus.COMPLETED), fixture.task.revision)
        self.assertIs(completed.status, c.TaskStatus.COMPLETED)
        self.assertEqual(fixture.tasks.read(fixture.task.id), completed)

    def test_actual_cli_complete_and_update_completed_each_succeed(self):
        for action in ('complete', 'update'):
            with self.subTest(action=action):
                fixture = self.fixture()
                fixture.save()
                if action == 'complete':
                    args = ['task', 'complete', fixture.task.id]
                else:
                    record = fixture.data.root / 'completed.json'
                    record.write_bytes(c.canonical_json(c.to_dict(replace(fixture.task, status=c.TaskStatus.COMPLETED))))
                    args = ['task', 'update', '--record', record]
                result, payload = self.cli(*args, '--expected-revision', fixture.task.revision, '--state-dir', fixture.state)
                self.assertEqual(result.returncode, 0, (payload, result.stderr))
                self.assertEqual(payload['data']['status'], 'completed')
                self.assertIs(fixture.tasks.read(fixture.task.id).status, c.TaskStatus.COMPLETED)

    def test_stale_prompt_candidate_or_receipt_cannot_complete_with_passing_callback(self):
        for target in ('prompt', 'candidate', 'host-call', 'evidence'):
            with self.subTest(target=target):
                fixture = self.fixture()
                fixture.save()
                path = {'prompt': fixture.workers[0] / 'prompt.txt',
                        'candidate': fixture.data.root / 'product.txt',
                        'host-call': fixture.workers[1] / 'call.json',
                        'evidence': fixture.data.root / 'after.log'}[target]
                path.write_text('SYNTHETIC drift after accepted evidence')
                self.assertFalse(fixture.evidence.check(fixture.task.id).passed)
                self.assert_completion_denied_preserves_task(fixture)

    def test_dispatched_context_cannot_change_and_preserves_head(self):
        fixture = self.fixture()
        fixture.save()
        head = fixture.state / 'delivery' / fixture.task.id / 'head.json'
        before = head.read_bytes()
        e = fixture.delivery.assignments[0]
        changed = replace(e, revision=e.revision + 1,
            payload=replace(e.payload, context=replace(e.payload.context, preferences={'fixture': 'SYNTHETIC drift'})))
        proposed = replace(fixture.delivery, previous_sha256=b.builtin_digest(fixture.delivery),
                           assignments=[changed, fixture.delivery.assignments[1]])
        with self.assertRaises(c.ValidationError):
            fixture.deliveries.update(proposed, fixture.delivery.revision, fixture.task.revision)
        self.assertEqual(head.read_bytes(), before)
        self.assertEqual(fixture.deliveries.read(fixture.task.id), fixture.delivery)

    def test_missing_case_stale_context_and_nonindependent_review_deny_with_saved_task_preserved(self):
        for fault in ('missing-case', 'stale-reviewed-context', 'same-review-context'):
            with self.subTest(fault=fault):
                fixture = self.fixture()
                if fault == 'missing-case':
                    bad = replace(fixture.bundle, cases=[])
                elif fault == 'stale-reviewed-context':
                    # Rehash the review against another context; all actual receipt
                    # bytes remain well formed. Frozen plan/context must still win.
                    current = fixture.data.delivery
                    fixture.data.delivery = replace(current, plan=replace(current.plan, context_sha256='f' * 64))
                    bad = fixture.reseal(fixture.bundle)
                    fixture.data.delivery = current
                else:
                    review = replace(fixture.bundle.reviews[0], reviewer_observation_id='obs-0')
                    bad = fixture.reseal(replace(fixture.bundle, reviews=[review]))
                with self.assertRaises(c.ValidationError):
                    fixture.save(bad)
                self.assertFalse((fixture.state / 'delivery' / fixture.task.id / 'evidence' / 'head.json').exists())
                self.assert_completion_denied_preserves_task(fixture)

    def test_evidence_cas_and_bundle_binding_preserve_saved_head(self):
        fixture = self.fixture()
        fixture.save()
        head = fixture.state / 'delivery' / fixture.task.id / 'evidence' / 'head.json'
        before = head.read_bytes()
        with self.assertRaises(c.RevisionConflict):
            fixture.save(expected_revision=0)
        with self.assertRaises(c.ValidationError):
            fixture.save(replace(fixture.bundle, delivery_revision=fixture.delivery.revision - 1), expected_revision=1)
        self.assertEqual(head.read_bytes(), before)
        self.assertTrue(fixture.evidence.check(fixture.task.id).passed)
