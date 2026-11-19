"""Revisioned local task records with anchored filesystem operations."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from copy import deepcopy
from dataclasses import replace
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Callable

from .contracts import (ErrorDetail, GateResult, RevisionConflict, TaskRecord,
                        TaskStatus, ValidationError, from_dict, to_dict)

_ID = re.compile(r'[a-z][a-z0-9_-]{1,63}\Z')
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_ALLOWED = {
    TaskStatus.QUEUED: {TaskStatus.RUNNING},
    TaskStatus.RUNNING: {TaskStatus.WAITING_INPUT, TaskStatus.WAITING_APPROVAL,
                         TaskStatus.VERIFYING, TaskStatus.PAUSED, TaskStatus.FAILED,
                         TaskStatus.CANCELLED},
    TaskStatus.WAITING_INPUT: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.WAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.VERIFYING: {TaskStatus.RUNNING, TaskStatus.COMPLETED,
                           TaskStatus.FAILED, TaskStatus.PAUSED, TaskStatus.CANCELLED},
    TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.FAILED: set(),
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
}


def _invalid(code: str, path: str, message: str) -> ValidationError:
    return ValidationError([ErrorDetail(code, path, message)])


def _id(value: str, path: str = '$.id') -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise _invalid('invalid_id', path, 'Expected a lowercase record ID of 2–64 characters')
    return value


def _canonical_root(root: Path) -> Path:
    raw = Path(os.path.abspath(root))
    current = Path('/')
    system_alias = False
    for part in raw.parts[1:]:
        current /= part
        if current.is_symlink():
            if str(current) not in ('/tmp', '/var') or current.resolve() != Path('/private') / part:
                raise _invalid('unsafe_path', '$', 'Untrusted symlink in root path')
            system_alias = True
    if system_alias:
        return Path('/private', *raw.parts[1:])
    return raw


def _open_directory(parent_fd: int, name: str, create: bool = False) -> int:
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
    try:
        fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise _invalid('unsafe_path', '$', 'Symlink or non-directory path component') from exc
        raise
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        os.close(fd)
        raise _invalid('unsafe_path', '$', 'Expected directory')
    return fd


@contextmanager
def _root_fd(root: Path, create: bool = False):
    canonical = _canonical_root(root)
    fd = os.open('/', _DIR_FLAGS)
    try:
        parts = canonical.parts[1:]
        for index, part in enumerate(parts):
            child = _open_directory(fd, part, create and index == len(parts) - 1)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _same_file(a, b) -> bool:
    return a.st_dev == b.st_dev and a.st_ino == b.st_ino


def _assert_attached(parent_fd: int, name: str, child_fd: int) -> None:
    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise _invalid('unsafe_path', '$', 'Directory was detached') from exc
    if not stat.S_ISDIR(named.st_mode) or not _same_file(named, os.fstat(child_fd)):
        raise _invalid('unsafe_path', '$', 'Directory was replaced')


def _open_regular(parent_fd: int, name: str, flags: int, mode: int = 0o600) -> int:
    try:
        fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, mode, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENXIO):
            raise _invalid('unsafe_path', '$', 'Unsafe file type or symlink') from exc
        raise
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise _invalid('unsafe_path', '$', 'Expected regular file')
    return fd


def _read_record(tasks_fd: int, task_id: str) -> TaskRecord:
    fd = _open_regular(tasks_fd, f'{task_id}.json', os.O_RDONLY)
    with os.fdopen(fd, 'r', encoding='utf-8') as stream:
        try:
            data = json.load(stream)
        except (ValueError, UnicodeError) as exc:
            raise _invalid('malformed_json', '$', 'Malformed task JSON') from exc
    record = from_dict('TaskRecord', data)
    if record.id != task_id:
        raise _invalid('identity_mismatch', '$.id', 'Task ID does not match record filename')
    return record


@contextmanager
def _lock(locks_fd: int, task_id: str):
    name = f'{task_id}.lock'
    fd = _open_regular(locks_fd, name, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            named = os.stat(name, dir_fd=locks_fd, follow_symlinks=False)
            if not _same_file(named, os.fstat(fd)):
                raise _invalid('unsafe_path', '$', 'Lock was replaced')
            yield fd
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _write_record(tasks_fd: int, task_id: str, record: TaskRecord) -> None:
    wire = to_dict(record)
    payload = (json.dumps(wire, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    temporary = f'.{task_id}.{secrets.token_hex(16)}.tmp'
    fd = _open_regular(tasks_fd, temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, f'{task_id}.json', src_dir_fd=tasks_fd,
                   dst_dir_fd=tasks_fd)
        os.fsync(tasks_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=tasks_fd)
        except FileNotFoundError:
            pass


def _cycle_history(candidate: TaskRecord, current: TaskRecord | None = None) -> None:
    if [cycle.cycle_number for cycle in candidate.cycles] != list(range(1, len(candidate.cycles) + 1)):
        raise _invalid('invalid_cycle_sequence', '$.cycles', 'Cycles must be consecutive from one')
    if current is not None:
        previous, following = to_dict(current)['cycles'], to_dict(candidate)['cycles']
        if following[:len(previous)] != previous:
            raise _invalid('history_changed', '$.cycles', 'Existing cycle evidence is immutable')


def _typed(record: TaskRecord) -> TaskRecord:
    return from_dict('TaskRecord', to_dict(record))


class TaskStore:
    """Persist P00 task records with per-ID compare-and-swap revisions."""

    def __init__(self, root: Path,
                 completion_check: Callable[[TaskRecord], GateResult] | None = None):
        self.root = Path(root)
        self.completion_check = completion_check

    @contextmanager
    def _directories(self, create: bool):
        with _root_fd(self.root, create) as root_fd:
            tasks_fd = _open_directory(root_fd, 'tasks', create)
            try:
                if create:
                    locks_fd = _open_directory(root_fd, 'locks', True)
                else:
                    locks_fd = None
                try:
                    yield root_fd, tasks_fd, locks_fd
                finally:
                    if locks_fd is not None:
                        os.close(locks_fd)
            finally:
                os.close(tasks_fd)

    def create(self, record: TaskRecord) -> TaskRecord:
        candidate = _typed(record)
        if candidate.status is TaskStatus.COMPLETED:
            raise _invalid('invalid_transition', '$.status', 'Cannot create a completed task')
        _cycle_history(candidate)
        with self._directories(True) as (root_fd, tasks_fd, locks_fd):
            with _lock(locks_fd, candidate.id) as lock_fd:
                try:
                    os.stat(f'{candidate.id}.json', dir_fd=tasks_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise RevisionConflict(f'Task {candidate.id} already exists')
                stored = replace(candidate, revision=1)
                _assert_attached(root_fd, 'tasks', tasks_fd)
                _assert_attached(root_fd, 'locks', locks_fd)
                _write_record(tasks_fd, candidate.id, stored)
                return stored

    def read(self, task_id: str) -> TaskRecord:
        _id(task_id)
        with self._directories(False) as (_, tasks_fd, __):
            return _read_record(tasks_fd, task_id)

    def update(self, record: TaskRecord, expected_revision: int) -> TaskRecord:
        return self._update(record, expected_revision, resume=False)

    def resume_failed(self, record: TaskRecord, expected_revision: int) -> TaskRecord:
        """Explicitly resume a failed task as running under the same CAS rule."""
        return self._update(record, expected_revision, resume=True)

    def _update(self, record: TaskRecord, expected_revision: int, resume: bool) -> TaskRecord:
        candidate = _typed(record)
        if type(expected_revision) is not int or expected_revision < 1:
            raise _invalid('invalid_revision', '$.revision', 'Expected positive integer revision')
        with self._directories(True) as (root_fd, tasks_fd, locks_fd):
            with _lock(locks_fd, candidate.id) as lock_fd, ExitStack() as delivery_context:
                current = _read_record(tasks_fd, candidate.id)
                if current.revision != expected_revision:
                    raise RevisionConflict(f'Expected revision {expected_revision}, found {current.revision}')
                if candidate.revision != expected_revision:
                    raise _invalid('invalid_revision', '$.revision', 'Proposed revision must equal expected revision')
                if candidate.id != current.id or candidate.request != current.request:
                    raise _invalid('immutable_field', '$', 'Task identity and request are immutable')
                if resume:
                    legal = current.status is TaskStatus.FAILED and candidate.status is TaskStatus.RUNNING
                else:
                    legal = (candidate.status is current.status and current.status not in
                             (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED)) or candidate.status in _ALLOWED[current.status]
                if not legal:
                    raise _invalid('invalid_transition', '$.status', 'Illegal task status transition')
                _cycle_history(candidate, current)
                proposed = replace(candidate, revision=expected_revision + 1)
                if proposed.status is TaskStatus.COMPLETED:
                    session = None
                    # Local imports preserve the existing state/delivery import boundary.
                    from .delivery_gate import mandatory_completion, requires_delivery
                    if requires_delivery(root_fd, current):
                        from .delivery_store import DeliveryStore
                        try:
                            session = delivery_context.enter_context(
                                DeliveryStore(self.root).borrowed(current.id, root_fd=root_fd,
                                    tasks_fd=tasks_fd, locks_fd=locks_fd, lock_fd=lock_fd))
                            result = mandatory_completion(current, proposed, session)
                            if not result.passed:
                                raise ValidationError(result.errors)
                        except (ValidationError, FileNotFoundError) as error:
                            details = error.errors if isinstance(error, ValidationError) else [
                                ErrorDetail('missing_registration', '$', 'Missing delivery registration')]
                            raise ValidationError([ErrorDetail('completion_denied', '$.status',
                                'Mandatory delivery gate failed'), *details]) from error
                    if self.completion_check is None:
                        raise _invalid('completion_denied', '$.status', 'Completion checker is required')
                    result = self.completion_check(deepcopy(proposed))
                    if type(result) is not GateResult:
                        raise _invalid('completion_denied', '$.status', 'Checker must return GateResult')
                    try:
                        to_dict(result)
                    except ValidationError as exc:
                        raise _invalid('completion_denied', '$.status', 'Checker returned invalid GateResult') from exc
                    if not result.passed:
                        raise _invalid('completion_denied', '$.status', 'Completion gate failed')
                    if session is not None:
                        # Callback collectors may refresh artifact/evidence files. Recheck
                        # current bytes under the same lock/session before persistence.
                        observed = _read_record(tasks_fd, candidate.id)
                        if observed != current:
                            raise RevisionConflict('Task changed during completion callback')
                        final = mandatory_completion(observed, proposed, session)
                        if not final.passed:
                            raise ValidationError([ErrorDetail('completion_denied', '$.status',
                                'Final mandatory delivery gate failed'), *final.errors])
                _assert_attached(root_fd, 'tasks', tasks_fd)
                _assert_attached(root_fd, 'locks', locks_fd)
                named_lock = os.stat(f'{candidate.id}.lock', dir_fd=locks_fd, follow_symlinks=False)
                if not _same_file(named_lock, os.fstat(lock_fd)):
                    raise _invalid('unsafe_path', '$', 'Lock was replaced')
                _write_record(tasks_fd, candidate.id, proposed)
                return proposed
