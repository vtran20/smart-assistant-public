"""Task store behavior with synthetic records and isolated directories."""
import copy
import json
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from smart_assistant.contracts import ErrorDetail, GateResult, RevisionConflict, TaskStatus, ValidationError, from_dict
from smart_assistant.state import TaskStore

FIXTURE = Path(__file__).resolve().parents[1] / 'examples/contracts/TaskRecord.json'


def record(status='queued'):
    wire = json.loads(FIXTURE.read_text())
    wire['status'] = status
    wire['phase'] = 'design'
    return from_dict('TaskRecord', wire)


def concurrent_writer(root, ready, proceed, outcome, label):
    store = TaskStore(Path(root))
    proposed = store.read('task-01')
    proposed.status = TaskStatus.RUNNING
    proposed.resume_next_step = label
    ready.put(label)
    proceed.wait()
    try:
        outcome.put((label, store.update(proposed, 1).revision))
    except RevisionConflict:
        outcome.put((label, 'conflict'))


def fifo_probe(root, kind, outcome):
    try:
        store = TaskStore(Path(root))
        if kind == 'record':
            store.read('task-01')
        elif kind == 'update':
            store.update(record('running'), 1)
        else:
            store.create(record())
        outcome.put('accepted')
    except ValidationError:
        outcome.put('rejected')
    except Exception as exc:
        outcome.put(type(exc).__name__)


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = TaskStore(self.root)

    def test_stale_revision_preserves_newer_record(self):
        original = self.store.create(record())
        first = copy.deepcopy(original)
        first.status = TaskStatus.RUNNING
        newer = self.store.update(first, expected_revision=1)
        self.assertEqual(newer.revision, 2)
        stale = copy.deepcopy(original)
        stale.status = TaskStatus.RUNNING
        stale.resume_next_step = 'stale'
        with self.assertRaises(RevisionConflict):
            self.store.update(stale, expected_revision=1)
        self.assertEqual(self.store.read(original.id), newer)

    def test_two_processes_from_same_revision_only_one_wins(self):
        self.store.create(record())
        ctx = multiprocessing.get_context('spawn')
        ready, outcome = ctx.Queue(), ctx.Queue()
        proceed = ctx.Event()
        children = [ctx.Process(target=concurrent_writer, args=(str(self.root), ready, proceed, outcome, name)) for name in ('a', 'b')]
        for child in children:
            child.start()
        for _ in children:
            ready.get(timeout=10)
        proceed.set()
        results = [outcome.get(timeout=10)[1] for _ in children]
        for child in children:
            child.join(timeout=10)
            self.assertEqual(child.exitcode, 0)
        self.assertCountEqual(results, [2, 'conflict'])
        self.assertEqual(self.store.read('task-01').revision, 2)

    def test_completion_without_checker_is_denied(self):
        verifying = record('verifying')
        self.store.create(verifying)
        completing = copy.deepcopy(verifying)
        completing.status = TaskStatus.COMPLETED
        with self.assertRaises(ValidationError):
            self.store.update(completing, 1)
        self.assertEqual(self.store.read(verifying.id).status, TaskStatus.VERIFYING)

    def test_plain_string_completed_cannot_bypass_gate_on_create_or_update(self):
        proposed = record('verifying')
        proposed.status = 'completed'
        with self.assertRaises(ValidationError):
            self.store.create(proposed)
        original = self.store.create(record('verifying'))
        proposed = copy.deepcopy(original)
        proposed.status = 'completed'
        calls = []
        gated = TaskStore(self.root, lambda value: calls.append(value) or GateResult(False, [ErrorDetail('gate', '$', 'failed')]))
        with self.assertRaises(ValidationError):
            gated.update(proposed, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.store.read(original.id), original)

    def test_plain_string_running_is_normalized_on_update_and_resume(self):
        original = self.store.create(record())
        proposed = copy.deepcopy(original)
        proposed.status = 'running'
        updated = self.store.update(proposed, 1)
        self.assertIs(updated.status, TaskStatus.RUNNING)
        self.assertIs(self.store.read(original.id).status, TaskStatus.RUNNING)
        with TemporaryDirectory() as temp:
            store = TaskStore(Path(temp))
            failed = store.create(record('failed'))
            resumed = copy.deepcopy(failed)
            resumed.status = 'running'
            result = store.resume_failed(resumed, 1)
            self.assertIs(result.status, TaskStatus.RUNNING)

    def test_checker_receives_next_revision_and_must_pass(self):
        seen = []
        def check(value):
            seen.append(value.revision)
            return GateResult(True, [])
        store = TaskStore(self.root, check)
        original = store.create(record('verifying'))
        proposed = copy.deepcopy(original)
        proposed.status = TaskStatus.COMPLETED
        self.assertEqual(store.update(proposed, 1).revision, 2)
        self.assertEqual(seen, [2])
        with self.assertRaises(ValidationError):
            TaskStore(self.root, lambda _: GateResult(False, [ErrorDetail('denied', '$', 'denied')])).create(record('completed'))

    def test_failed_checker_denies_without_replacement(self):
        original = self.store.create(record('verifying'))
        proposed = copy.deepcopy(original)
        proposed.status = TaskStatus.COMPLETED
        store = TaskStore(self.root, lambda _: GateResult(False, [ErrorDetail('gate', '$', 'failed')]))
        with self.assertRaises(ValidationError):
            store.update(proposed, 1)
        self.assertEqual(store.read(original.id), original)

    def test_completion_checker_cannot_change_written_record(self):
        def check(value):
            value.status = TaskStatus.RUNNING
            return GateResult(True, [])
        store = TaskStore(self.root, check)
        original = store.create(record('verifying'))
        proposed = copy.deepcopy(original)
        proposed.status = TaskStatus.COMPLETED
        self.assertEqual(store.update(proposed, 1).status, TaskStatus.COMPLETED)
        self.assertEqual(store.read(original.id).status, TaskStatus.COMPLETED)

    def test_interrupted_record_can_resume(self):
        failed = self.store.create(record('failed'))
        resumed = copy.deepcopy(failed)
        resumed.status = TaskStatus.RUNNING
        with self.assertRaises(ValidationError):
            self.store.update(resumed, 1)
        result = self.store.resume_failed(resumed, 1)
        self.assertEqual((result.status, result.revision), (TaskStatus.RUNNING, 2))

    def test_terminal_record_cannot_reopen(self):
        for status in ('cancelled', 'completed'):
            with self.subTest(status=status), TemporaryDirectory() as temp:
                store = TaskStore(Path(temp), lambda _: GateResult(True, []))
                if status == 'completed':
                    first = store.create(record('verifying'))
                    target = copy.deepcopy(first)
                    target.status = TaskStatus.COMPLETED
                    terminal = store.update(target, 1)
                else:
                    terminal = store.create(record(status))
                attempt = copy.deepcopy(terminal)
                attempt.status = TaskStatus.RUNNING
                with self.assertRaises(ValidationError):
                    store.update(attempt, terminal.revision)
                self.assertEqual(store.read('task-01'), terminal)

    def test_replace_failure_preserves_record_and_cleans_temp(self):
        original = self.store.create(record())
        proposed = copy.deepcopy(original)
        proposed.status = TaskStatus.RUNNING
        with patch('smart_assistant.state.os.replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.store.update(proposed, 1)
        self.assertEqual(self.store.read(original.id), original)
        self.assertEqual([p.name for p in (self.root / 'tasks').iterdir()], ['task-01.json'])
        self.assertTrue((self.root / 'locks' / 'task-01.lock').exists())

    def test_read_does_not_mutate_and_rejects_bad_id(self):
        with self.assertRaises(FileNotFoundError):
            self.store.read('task-01')
        self.assertEqual(list(self.root.iterdir()), [])
        for value in ('../other', 'a/b', 'A'):
            with self.assertRaises(ValidationError):
                self.store.read(value)

    def test_symlinked_record_and_directory_rejected(self):
        outside = self.root / 'outside.json'
        outside.write_text('{}')
        tasks = self.root / 'tasks'
        tasks.mkdir()
        (tasks / 'task-01.json').symlink_to(outside)
        with self.assertRaises(ValidationError):
            self.store.read('task-01')
        (tasks / 'task-01.json').unlink()
        tasks.rmdir()
        tasks.symlink_to(self.root)
        with self.assertRaises(ValidationError):
            self.store.create(record())

    def test_record_identity_must_match_filename(self):
        self.store.create(record())
        (self.root / 'tasks' / 'task-02.json').write_bytes(
            (self.root / 'tasks' / 'task-01.json').read_bytes())
        with self.assertRaises(ValidationError):
            self.store.read('task-02')

    def test_parent_swap_at_record_open_cannot_write_outside_root(self):
        current = self.store.create(record())
        tasks = self.root / 'tasks'
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'task-01.json').write_bytes((tasks / 'task-01.json').read_bytes())
        original_open = os.open
        switched = False
        def swap(path, *args, **kwargs):
            nonlocal switched
            if not switched and (Path(path) == tasks / 'task-01.json' or
                                 (str(path) == 'task-01.json' and 'dir_fd' in kwargs)):
                switched = True
                tasks.rename(self.root / 'saved-tasks')
                tasks.symlink_to(outside, target_is_directory=True)
            return original_open(path, *args, **kwargs)
        proposed = copy.deepcopy(current)
        proposed.status = TaskStatus.RUNNING
        with patch('smart_assistant.state.os.open', side_effect=swap):
            try:
                self.store.update(proposed, 1)
            except ValidationError:
                pass
        self.assertTrue(switched)
        self.assertEqual(json.loads((outside / 'task-01.json').read_text())['revision'], 1)

    def test_fifo_records_and_locks_reject_without_blocking(self):
        for kind in ('record', 'update', 'lock'):
            with self.subTest(kind=kind), TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'tasks').mkdir()
                (root / 'locks').mkdir()
                if kind == 'lock':
                    os.mkfifo(root / 'locks' / 'task-01.lock')
                else:
                    os.mkfifo(root / 'tasks' / 'task-01.json')
                ctx = multiprocessing.get_context('spawn')
                outcome = ctx.Queue()
                child = ctx.Process(target=fifo_probe, args=(str(root), kind, outcome))
                child.start()
                child.join(timeout=2)
                if child.is_alive():
                    child.terminate()
                    child.join(timeout=2)
                    self.fail(f'{kind} FIFO blocked')
                self.assertEqual(child.exitcode, 0)
                self.assertEqual(outcome.get(timeout=2), 'rejected')

    def test_arbitrary_root_alias_is_rejected(self):
        actual = self.root / 'actual'
        actual.mkdir()
        alias = self.root / 'alias'
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValidationError):
            TaskStore(alias / 'inner').create(record())
        self.assertEqual(list(actual.iterdir()), [])

    def test_parent_swap_at_lock_open_cannot_create_outside_lock(self):
        current = self.store.create(record())
        locks = self.root / 'locks'
        outside = self.root / 'outside'
        outside.mkdir()
        original_open = os.open
        switched = False
        def swap(path, *args, **kwargs):
            nonlocal switched
            if not switched and (Path(path) == locks / 'task-01.lock' or
                                 (str(path) == 'task-01.lock' and 'dir_fd' in kwargs)):
                switched = True
                locks.rename(self.root / 'saved-locks')
                locks.symlink_to(outside, target_is_directory=True)
            return original_open(path, *args, **kwargs)
        proposed = copy.deepcopy(current)
        proposed.status = TaskStatus.RUNNING
        with patch('smart_assistant.state.os.open', side_effect=swap):
            try:
                self.store.update(proposed, 1)
            except ValidationError:
                pass
        self.assertTrue(switched)
        self.assertEqual(list(outside.iterdir()), [])

    def test_parent_swap_at_replace_cannot_write_outside_root(self):
        current = self.store.create(record())
        tasks = self.root / 'tasks'
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'task-01.json').write_bytes((tasks / 'task-01.json').read_bytes())
        original_replace = os.replace
        switched = False
        def swap(source, destination, *args, **kwargs):
            nonlocal switched
            if not switched:
                switched = True
                tasks.rename(self.root / 'saved-tasks')
                tasks.symlink_to(outside, target_is_directory=True)
            return original_replace(source, destination, *args, **kwargs)
        proposed = copy.deepcopy(current)
        proposed.status = TaskStatus.RUNNING
        with patch('smart_assistant.state.os.replace', side_effect=swap):
            self.store.update(proposed, 1)
        self.assertTrue(switched)
        self.assertEqual(json.loads((outside / 'task-01.json').read_text())['revision'], 1)
        self.assertEqual(json.loads((self.root / 'saved-tasks' / 'task-01.json').read_text())['revision'], 2)
