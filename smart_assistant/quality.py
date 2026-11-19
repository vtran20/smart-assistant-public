"""Current-file snapshots and completion evidence checks, without task mutation.

Evidence paths are local POSIX relative regular files under artifact_root. Child
traversal uses directory descriptors and rejects symlinks. The caller must
serialize review/completion with artifact mutations; this is not an atomic
filesystem snapshot or proof of a reviewer's independence or truthfulness.
"""
from contextlib import contextmanager
from dataclasses import replace
import errno
import hashlib
import os
from pathlib import Path
import stat

from .contracts import (
    AcceptanceSnapshot, Artifact, CandidateSnapshot, CheckOutcome, Criterion,
    CycleEvidence, ErrorDetail, GateResult, TaskRecord, ValidationError,
    canonical_json, from_dict, to_dict,
)


def _fail(code: str, path: str, message: str) -> None:
    raise ValidationError([ErrorDetail(code, path, message)])


def _relative(ref: str, code: str, path: str) -> list[str]:
    if (type(ref) is not str or not ref.strip() or ref.startswith('/') or '\\' in ref
            or ':' in ref or '\x00' in ref or any(p in ('', '.', '..') for p in ref.split('/'))):
        _fail(code, path, 'Expected a local safe POSIX relative file path')
    canonical_json(ref)
    return ref.split('/')


@contextmanager
def _root(root: Path, code: str, path: str):
    if not isinstance(root, Path) or not root.is_absolute():
        _fail(code, path, 'Expected an absolute artifact directory')
    try:
        resolved = root.resolve(strict=True)
        fd = os.open(resolved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, ValueError, RuntimeError):
        _fail(code, path, 'Artifact directory is unavailable or unsafe')
    try:
        yield fd
    finally:
        os.close(fd)


def _file_hash(root_fd: int, ref: str, code: str, missing: str, path: str,
               identities: set[tuple[int, int]] | None = None) -> str:
    parts = _relative(ref, code, path)
    directory = os.dup(root_fd)
    file_fd = None
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        # O_NONBLOCK prevents a FIFO from blocking before the regular-file check.
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            _fail(code, path, 'Reference must name a regular file')
        if identities is not None:
            identities.add((info.st_dev, info.st_ino))
        digest = hashlib.sha256()
        while chunk := os.read(file_fd, 65536):
            digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        failure = missing if error.errno == errno.ENOENT else code
        _fail(failure, path, 'Referenced file is missing, unreadable or unsafe')
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory)


def _records(items: list, expected: type, path: str) -> list:
    if type(items) is not list:
        _fail('invalid_type', path, 'Expected a list of records')
    normalized = []
    for index, item in enumerate(items):
        if type(item) is not expected:
            _fail('invalid_type', f'{path}[{index}]', f'Expected {expected.__name__}')
        normalized.append(from_dict(expected.__name__, to_dict(item)))
    return normalized


def _criteria(criteria: list[Criterion]) -> list[Criterion]:
    criteria = _records(criteria, Criterion, '$.criteria')
    ids = [item.id for item in criteria]
    if not ids or len(ids) != len(set(ids)):
        _fail('invalid_criteria', '$.criteria', 'Completion criteria must be nonempty with unique IDs')
    return sorted((replace(item) for item in criteria), key=lambda item: item.id)


def _candidate(root_fd: int, artifacts: list[Artifact],
               identities: set[tuple[int, int]] | None = None) -> CandidateSnapshot:
    artifacts = _records(artifacts, Artifact, '$.artifacts')
    ids = [item.id for item in artifacts]
    paths = [item.relative_path for item in artifacts]
    if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
        _fail('invalid_candidate', '$.artifacts', 'Artifact IDs and paths must be unique')
    current = []
    for index, artifact in enumerate(artifacts):
        digest = _file_hash(root_fd, artifact.relative_path, 'invalid_artifact_path',
                            'missing_artifact', f'$.artifacts[{index}].relative_path', identities)
        current.append(replace(artifact, sha256=digest))
    current.sort(key=lambda item: item.id)
    fingerprint = hashlib.sha256(canonical_json([to_dict(item) for item in current])).hexdigest()
    return CandidateSnapshot(current, fingerprint)


def snapshot(artifact_root: Path, artifacts: list[Artifact]) -> CandidateSnapshot:
    """Hash current product files; supplied artifact digests never establish truth."""
    with _root(artifact_root, 'invalid_artifact_path', '$.artifact_root') as root_fd:
        return _candidate(root_fd, artifacts)


def _acceptance(criteria: list[Criterion], design_hash: str) -> AcceptanceSnapshot:
    current = _criteria(criteria)
    payload = {'criteria': [to_dict(item) for item in current], 'design_sha256': design_hash}
    return AcceptanceSnapshot(current, design_hash, hashlib.sha256(canonical_json(payload)).hexdigest())


def acceptance_snapshot(criteria: list[Criterion], design_path: Path) -> AcceptanceSnapshot:
    """Bind all current criterion fields to current regular-file design bytes."""
    criteria = _criteria(criteria)
    if not isinstance(design_path, Path):
        _fail('invalid_evidence_path', '$.design_ref', 'Expected a design Path')
    if not design_path.is_absolute():
        design_path = design_path.absolute()
    with _root(design_path.parent, 'invalid_evidence_path', '$.design_ref') as root_fd:
        digest = _file_hash(root_fd, design_path.name, 'invalid_evidence_path',
                            'missing_evidence', '$.design_ref')
        return _acceptance(criteria, digest)


def _latest(task: TaskRecord, errors: list[ErrorDetail]) -> CycleEvidence | None:
    if not task.cycles:
        errors.append(ErrorDetail('missing_review', '$.cycles', 'No review cycle exists'))
        return None
    numbers = [cycle.cycle_number for cycle in task.cycles]
    if any(a >= b for a, b in zip(numbers, numbers[1:])):
        errors.append(ErrorDetail('invalid_cycle_history', '$.cycles',
                                  'Cycle numbers must be strictly increasing in history order'))
        return None
    return task.cycles[-1]


def completion_gate(task: TaskRecord) -> GateResult:
    """Check latest-cycle current evidence for P01's proposed completion record.

    A returned pass certifies consistency, current bytes, local evidence presence
    and coverage. Valid nested wire dictionaries/enums are decoded into a fresh
    typed task before inspection. It does not execute receipt commands or
    authorize task actions.
    """
    errors = []
    if type(task) is not TaskRecord:
        return GateResult(False, [ErrorDetail('invalid_type', '$', 'Expected a TaskRecord')])
    # Preserve the useful domain diagnostic even if the frozen nonnullable review
    # field is malformed; all other structural errors are still returned.
    if type(task.cycles) is list and task.cycles:
        latest = task.cycles[-1]
        if ((type(latest) is CycleEvidence and latest.review is None)
                or (type(latest) is dict and latest.get('review') is None)):
            errors.append(ErrorDetail('missing_review', '$.cycles[-1].review', 'Latest review is missing'))
    try:
        # Wire validation alone does not normalize the caller's dataclass fields.
        # Consume the decoded copy for every subsequent cross-record access.
        task = from_dict('TaskRecord', to_dict(task))
    except ValidationError as error:
        return GateResult(False, errors + error.errors)
    cycle = _latest(task, errors)
    try:
        _criteria(task.criteria)
    except ValidationError as error:
        errors.extend(error.errors)
    if cycle is None or errors:
        return GateResult(False, errors)
    if not cycle.candidate.artifacts:
        errors.append(ErrorDetail('invalid_candidate', '$.cycles[-1].candidate',
                                  'Completion requires at least one product artifact'))

    def issue(code, path, message):
        errors.append(ErrorDetail(code, path, message))

    def attempt(operation):
        try:
            return operation()
        except ValidationError as error:
            errors.extend(error.errors)
            return None

    if type(task.artifact_root) is not str or '\x00' in task.artifact_root:
        issue('invalid_artifact_path', '$.artifact_root', 'Expected a local artifact directory')
        return GateResult(False, errors)
    try:
        with _root(Path(task.artifact_root), 'invalid_artifact_path', '$.artifact_root') as root_fd:
            candidate_files = set()
            current = attempt(lambda: _candidate(root_fd, cycle.candidate.artifacts, candidate_files))
            design_hash = attempt(lambda: _file_hash(root_fd, cycle.design_ref,
                                  'invalid_evidence_path', 'missing_evidence', '$.cycles[-1].design_ref'))
            acceptance = _acceptance(task.criteria, design_hash) if design_hash is not None else None
            if current is not None and current.candidate_id != cycle.candidate.candidate_id:
                issue('stale_candidate', '$.cycles[-1].candidate', 'Current artifact bytes differ from the reviewed candidate')
            if acceptance is not None and acceptance.acceptance_id != cycle.acceptance.acceptance_id:
                issue('stale_acceptance', '$.cycles[-1].acceptance', 'Current criteria or design bytes differ from acceptance')
            candidate_id = current.candidate_id if current is not None else None
            acceptance_id = acceptance.acceptance_id if acceptance is not None else None
            review = cycle.review
            if ((candidate_id is not None and review.candidate_id != candidate_id)
                    or (acceptance_id is not None and review.acceptance_id != acceptance_id)):
                issue('stale_review', '$.cycles[-1].review', 'Review does not bind to current candidate and acceptance')
            if review.reviewer_ref == review.implementer_ref:
                issue('same_reviewer_implementer', '$.cycles[-1].review', 'Reviewer and implementer references must differ')
            criteria_ids = {item.id for item in task.criteria}
            finding_ids = [finding.id for finding in review.findings]
            if len(finding_ids) != len(set(finding_ids)):
                issue('invalid_findings', '$.cycles[-1].review.findings', 'Finding IDs must be unique')
            for finding in review.findings:
                if not set(finding.criterion_ids) <= criteria_ids:
                    issue('invalid_findings', '$.cycles[-1].review.findings', 'Finding references an unknown criterion')
            disposition_ids = [item.finding_id for item in cycle.dispositions]
            if len(disposition_ids) != len(set(disposition_ids)) or not set(disposition_ids) <= set(finding_ids):
                issue('invalid_dispositions', '$.cycles[-1].dispositions', 'Duplicate or orphan finding dispositions')
            if set(finding_ids) - set(disposition_ids):
                issue('unresolved_feedback', '$.cycles[-1].dispositions', 'Every finding requires a disposition')
            evidence_paths = set()
            evidence_files = set()

            def evidence(ref, path):
                parts = attempt(lambda: _relative(ref, 'invalid_evidence_path', path))
                if parts is not None:
                    evidence_paths.add(ref)
                    attempt(lambda: _file_hash(root_fd, ref, 'invalid_evidence_path', 'missing_evidence', path, evidence_files))

            for index, disposition in enumerate(cycle.dispositions):
                path = f'$.cycles[-1].dispositions[{index}]'
                if not disposition.evidence_refs or not disposition.reason.strip():
                    issue('unresolved_feedback', path, 'A disposition needs a reason and local evidence')
                for ref in disposition.evidence_refs:
                    evidence(ref, path + '.evidence_refs')
            check_ids = [check.check_id for check in cycle.checks]
            if len(check_ids) != len(set(check_ids)):
                issue('invalid_checks', '$.cycles[-1].checks', 'Check IDs must be unique')
            covered = set()
            for index, check in enumerate(cycle.checks):
                path = f'$.cycles[-1].checks[{index}]'
                if not set(check.criterion_ids) <= criteria_ids:
                    issue('invalid_checks', path, 'Check references an unknown criterion')
                if ((candidate_id is not None and check.candidate_id != candidate_id)
                        or (acceptance_id is not None and check.acceptance_id != acceptance_id)):
                    issue('stale_check', path, 'Check does not bind to current candidate and acceptance')
                if check.outcome != CheckOutcome.PASS:
                    issue('failed_check', path, 'Every current-cycle check must pass')
                else:
                    covered.update(check.criterion_ids)
                evidence(check.evidence_ref, path + '.evidence_ref')
            if criteria_ids - covered:
                issue('missing_criterion_coverage', '$.cycles[-1].checks', 'Passing checks must cover every criterion')
            if (evidence_files & candidate_files
                    or evidence_paths & {artifact.relative_path for artifact in cycle.candidate.artifacts}):
                issue('evidence_as_artifact', '$.cycles[-1].candidate', 'Receipt evidence cannot be a product artifact')
    except ValidationError as error:
        errors.extend(error.errors)
    return GateResult(not errors, errors)
