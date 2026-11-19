"""Builtin integration regressions; synthetic authority/receipts use isolated state."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from smart_assistant.contracts import GateResult, TaskStatus, ValidationError
from smart_assistant.state import TaskStore
from tests.test_state import record
from tests import test_cli as cli_fixtures

MODE_PREFIX = 'smart-assistant:execution-mode:'
MARKERS = (
    [MODE_PREFIX],
    [MODE_PREFIX + 'unsupported:9.0:' + 'a' * 64],
    [MODE_PREFIX + 'builtin:2.0:' + 'a' * 64],
    [MODE_PREFIX + 'builtin:2.0:' + 'a' * 64] * 2,
)


class ReservedExecutionModeTests(unittest.TestCase):
    def test_reserved_execution_markers_without_policy_cannot_use_passing_callback(self):
        for markers in MARKERS:
            with self.subTest(markers=markers), TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                calls = []
                store = TaskStore(root, lambda task: calls.append(task) or GateResult(True, []))
                task = record('verifying')
                task.request.source_refs.extend(markers)
                saved = store.create(task)
                before = (root / 'tasks' / f'{saved.id}.json').read_bytes()
                with self.assertRaises(ValidationError):
                    store.update(replace(saved, status=TaskStatus.COMPLETED), saved.revision)
                self.assertEqual(calls, [])
                self.assertEqual((root / 'tasks' / f'{saved.id}.json').read_bytes(), before)
                self.assertFalse((root / 'delivery').exists())

    def _cli_marker_cases(self, action):
        for markers in MARKERS:
            with self.subTest(markers=markers):
                helper = cli_fixtures.CLITests()
                helper.setUp()
                self.addCleanup(helper.doCleanups)
                helper.wire['request']['source_refs'].extend(markers)
                saved = helper.create('verifying', cycles=[helper.verified_cycle()])
                before = helper.stored_bytes()
                if action == 'complete':
                    helper.response(4, 'task', 'complete', saved['id'], '--expected-revision',
                                    saved['revision'], '--state-dir', helper.state)
                else:
                    saved['status'] = 'completed'
                    helper.update(saved, saved['revision'], code=4)
                self.assertEqual(helper.stored_bytes(), before)
                self.assertFalse((helper.state / 'delivery').exists())

    def test_actual_cli_complete_denies_reserved_mode_without_policy_or_sidecar(self):
        self._cli_marker_cases('complete')

    def test_actual_cli_update_completed_denies_reserved_mode_without_policy_or_sidecar(self):
        self._cli_marker_cases('update')


class BuiltinPersistenceTests(unittest.TestCase):
    def setUp(self):
        from smart_assistant import builtin_records as builtin
        from smart_assistant.delivery_store import DeliveryStore
        from tests import test_builtin_records as core_fixtures
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.tree = self.root / 'worker'; self.tree.mkdir()
        self.builtin = builtin
        self.task, self.initial, self.receipt = core_fixtures.fixture(self.tree)
        self.state = self.root / 'state'
        self.tasks = TaskStore(self.state, lambda task: GateResult(True, []))
        self.task = self.tasks.create(self.task)
        self.store = DeliveryStore(self.state)

    def test_builtin_register_update_read_preserves_request_and_task(self):
        from smart_assistant.contracts import RevisionConflict
        saved = self.store.register(self.initial, self.task.revision)
        self.assertEqual(saved, self.initial)
        self.assertEqual(self.store.read(self.task.id), saved)
        update = replace(saved, previous_sha256=self.builtin.builtin_digest(saved),
                         plan=replace(saved.plan, revision=2, next_step='Dispatch worker'))
        updated = self.store.update(update, 1, self.task.revision)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(self.store.read(self.task.id), updated)
        self.assertEqual(self.tasks.read(self.task.id), self.task)
        with self.assertRaises(RevisionConflict): self.store.update(update, 1, self.task.revision)
        self.assertEqual(self.store.read(self.task.id), updated)

    def test_builtin_request_rejects_managed_snapshot_before_sidecar_creation(self):
        from tests.test_delivery_records import fixture
        from smart_assistant.delivery_records import request_digest
        _, managed = fixture(str(self.tree))
        request_hash = request_digest(self.task.request)
        managed = replace(managed, registration=replace(managed.registration, request_sha256=request_hash),
                          plan=replace(managed.plan, request_sha256=request_hash))
        with self.assertRaises(ValidationError): self.store.register(managed, self.task.revision)
        self.assertFalse((self.state / 'delivery').exists())
        self.assertEqual(self.tasks.read(self.task.id), self.task)

    def test_managed_request_rejects_builtin_snapshot_before_sidecar_creation(self):
        from tests.test_delivery_records import fixture
        from smart_assistant.delivery_store import DeliveryStore
        state = self.root / 'managed-state'
        managed_task, _ = fixture(str(self.tree))
        tasks = TaskStore(state); saved = tasks.create(managed_task)
        with self.assertRaises(ValidationError): DeliveryStore(state).register(self.initial, saved.revision)
        self.assertFalse((state / 'delivery').exists())
        self.assertEqual(tasks.read(saved.id), saved)

    def test_actual_cli_builtin_create_show_and_update(self):
        import json, subprocess, sys
        from smart_assistant.delivery_codec import record_to_dict
        source = self.root / 'builtin-record.json'; source.write_text(json.dumps(record_to_dict(self.initial)))
        def invoke(*args):
            return subprocess.run([sys.executable, '-m', 'smart_assistant', *map(str, args)],
                                  cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=15)
        result = invoke('delivery', 'create', '--record', source, '--expected-task-revision',
                        self.task.revision, '--state-dir', self.state)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        shown = invoke('delivery', 'show', self.task.id, '--state-dir', self.state)
        self.assertEqual(shown.returncode, 0, (shown.stdout, shown.stderr))
        self.assertEqual(json.loads(shown.stdout)['data'], record_to_dict(self.initial))
        update = replace(self.initial, previous_sha256=self.builtin.builtin_digest(self.initial),
                         plan=replace(self.initial.plan, revision=2, next_step='Dispatch'))
        source.write_text(json.dumps(record_to_dict(update)))
        result = invoke('delivery', 'update', '--record', source, '--expected-revision', '1',
                        '--expected-task-revision', self.task.revision, '--state-dir', self.state)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(json.loads(result.stdout)['data']['revision'], 2)
        self.assertEqual(self.tasks.read(self.task.id), self.task)

    def test_builtin_registered_completion_cannot_use_passing_callback(self):
        self.store.register(self.initial, self.task.revision)
        verifying = self.tasks.update(replace(self.task, status=TaskStatus.VERIFYING), self.task.revision)
        with self.assertRaises(ValidationError) as raised:
            self.tasks.update(replace(verifying, status=TaskStatus.COMPLETED), verifying.revision)
        self.assertIn('required_assignment_unaccepted', [e.code for e in raised.exception.errors])
        self.assertEqual(self.tasks.read(verifying.id), verifying)

    def test_builtin_snapshot_recovery_finishes_exact_operation(self):
        import json
        import os
        from unittest.mock import patch
        first = self.store.register(self.initial, self.task.revision)
        update = replace(first, previous_sha256=self.builtin.builtin_digest(first),
                         plan=replace(first.plan, revision=2, next_step='Recover exact builtin update'))
        original = os.replace
        def fail_head(source, target, *args, **kwargs):
            if target == 'head.json': raise OSError('isolated crash before authoritative head')
            return original(source, target, *args, **kwargs)
        with patch('smart_assistant.delivery_store.os.replace', side_effect=fail_head):
            with self.assertRaises(OSError): self.store.update(update, 1, self.task.revision)
        with self.assertRaises(ValidationError): self.store.read(self.task.id)
        base = self.state / 'delivery' / self.task.id
        operation = json.loads((base / 'pending.json').read_text())['operation_id']
        report = self.store.recover(self.task.id, operation, 'finish')
        self.assertEqual(report.head_revision, 2)
        self.assertIs(type(self.store.read(self.task.id)), self.builtin.BuiltinSnapshot)
        self.assertEqual(self.store.read(self.task.id).plan.next_step, update.plan.next_step)
        self.assertEqual(self.store.recover(self.task.id, operation, 'finish'), report)
        with self.assertRaises(ValidationError): self.store.recover(self.task.id, operation, 'reject')

    def test_builtin_dispatch_requires_current_prompt_before_new_intent_is_persisted(self):
        from tests import test_builtin_records as core_fixtures
        first = self.store.register(self.initial, self.task.revision)
        proposed = replace(core_fixtures.dispatch(first), previous_sha256=self.builtin.builtin_digest(first))
        head = self.state / 'delivery' / self.task.id / 'head.json'
        before = head.read_bytes()
        (self.tree / 'prompt.txt').unlink()
        with self.assertRaises(ValidationError): self.store.update(proposed, first.revision, self.task.revision)
        self.assertEqual(head.read_bytes(), before)
        self.assertFalse((head.parent / 'pending.json').exists())
        self.assertEqual(self.store.read(self.task.id), first)


class BuiltinCompletionAndObservationTests(unittest.TestCase):
    def test_callback_prompt_mutation_denies_final_completion(self):
        from tests.builtin_evidence_fixtures import builtin_evidence_fixture
        fixture = builtin_evidence_fixture(self)
        fixture.save()
        task_path = fixture.state / 'tasks' / f'{fixture.task.id}.json'
        before = task_path.read_bytes()
        called = []
        def mutate_after_initial_gate(task):
            called.append(task.id)
            (fixture.workers[0] / 'prompt.txt').write_text('Changed after initial mandatory validation')
            return GateResult(True, [])
        store = TaskStore(fixture.state, mutate_after_initial_gate)
        with self.assertRaises(ValidationError) as caught:
            store.update(replace(fixture.task, status=TaskStatus.COMPLETED), fixture.task.revision)
        self.assertEqual(called, [fixture.task.id])
        self.assertIn('stale_receipt', [e.code for e in caught.exception.errors])
        self.assertEqual(task_path.read_bytes(), before)
        self.assertEqual(store.read(fixture.task.id), fixture.task)

    def test_observed_host_call_is_validated_before_delivery_head_changes(self):
        import hashlib
        import json
        from tests.builtin_evidence_fixtures import builtin_evidence_fixture
        from smart_assistant import builtin_records as b
        fixture = builtin_evidence_fixture(self, persist=False)
        task = fixture.tasks.create(fixture.task)
        first = fixture.deliveries.register(fixture.history[0], task.revision)
        dispatched = fixture.deliveries.update(replace(fixture.history[1], revision=first.revision),
                                              first.revision, task.revision)
        head = fixture.state / 'delivery' / task.id / 'head.json'; before = head.read_bytes()
        path = fixture.workers[0] / 'call.json'
        call = json.loads(path.read_text()); call['arguments']['unsupported_option'] = True
        path.write_text(json.dumps(call))
        observed = fixture.history[2]; intent = observed.dispatches[0]
        binding = replace(intent.host_binding,
            submitted_call=b.BuiltinReceipt('call.json', hashlib.sha256(path.read_bytes()).hexdigest()))
        observed = replace(observed, revision=dispatched.revision,
                           dispatches=[replace(intent, host_binding=binding)])
        with self.assertRaises(ValidationError) as caught:
            fixture.deliveries.update(observed, dispatched.revision, task.revision)
        self.assertIn('invalid_host_call', [e.code for e in caught.exception.errors])
        self.assertEqual(head.read_bytes(), before)
        self.assertEqual(fixture.deliveries.read(task.id), dispatched)
