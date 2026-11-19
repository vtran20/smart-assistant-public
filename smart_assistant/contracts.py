"""Version 1 structural contracts and explicit read-only handoff validation.

``from_dict(kind, wire)`` validates JSON objects and reconstructs nested dataclasses
and enums. ``to_dict(record)`` validates before returning a JSON-compatible object.
Validation errors use paths rooted at ``$``; map keys use JSON bracket notation.
``canonical_json(value)`` returns UTF-8 bytes with sorted keys, compact separators,
and literal Unicode scalar text; lone surrogates reject with structured errors.
Snapshot hashes exclude their declared digest and receipts.
Relative paths are checked lexically; consumers must enforce root containment and
symlink rules. Lifecycle eligibility and cross-record evidence gates are later APIs.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import re
from types import UnionType
from typing import Annotated, Union, get_args, get_origin, get_type_hints

# Annotated scalar aliases preserve useful Python field types and wire semantics.
ID = Annotated[str, 'id']
Ref = str
Digest = Annotated[str, 'digest']
Version = Annotated[str, 'version']
UTC = Annotated[str, 'timestamp']
RelativePath = Annotated[str, 'path']
Positive = Annotated[int, 'positive']
Schema = Annotated[int, 'schema']
EmptyString = Annotated[str, 'allow_empty']
JSONValue = Annotated[object, 'json']


class TaskStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    WAITING_INPUT = 'waiting_input'
    WAITING_APPROVAL = 'waiting_approval'
    VERIFYING = 'verifying'
    COMPLETED = 'completed'
    FAILED = 'failed'
    PAUSED = 'paused'
    CANCELLED = 'cancelled'


class TaskPhase(str, Enum):
    DESIGN = 'design'
    IMPLEMENT = 'implement'
    REVIEW = 'review'
    FEEDBACK = 'feedback'
    TESTING = 'testing'


class CapabilityKind(str, Enum):
    AGENT = 'agent'
    SKILL = 'skill'


class CapabilityState(str, Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    DISABLED = 'disabled'
    RETIRED = 'retired'


class ActionKind(str, Enum):
    READ_LOCAL = 'read_local'
    WRITE_LOCAL = 'write_local'
    EXTERNAL_READ = 'external_read'
    EXTERNAL_WRITE = 'external_write'


class HostDecision(str, Enum):
    ALLOWED = 'allowed'
    APPROVAL_REQUIRED = 'approval_required'
    DENIED = 'denied'
    UNKNOWN = 'unknown'


class Severity(str, Enum):
    CRITICAL = 'critical'
    MAJOR = 'major'
    MINOR = 'minor'
    INFO = 'info'


class DispositionDecision(str, Enum):
    CORRECTED = 'corrected'
    REJECTED = 'rejected'


class CheckMethod(str, Enum):
    COMMAND = 'command'
    OBSERVATION = 'observation'


class CheckOutcome(str, Enum):
    PASS = 'pass'
    FAIL = 'fail'


class HandoffResult(str, Enum):
    READY_FOR_REVIEW = 'ready_for_review'
    BLOCKED = 'blocked'
    FAILED = 'failed'


class ProbePurpose(str, Enum):
    ACTIVATE = 'activate'
    DISABLE = 'disable'


@dataclass
class RequestEnvelope:
    schema_version: Schema
    request_id: ID
    text: str
    project_id: ID
    source_refs: list[Ref]
    requested_role: ID | None


@dataclass
class ContextFact:
    text: str
    scope: str
    source_ref: Ref
    observed_at: UTC


@dataclass
class ContextBundle:
    schema_version: Schema
    project_id: ID
    preferences: dict[str, JSONValue]
    facts: list[ContextFact]


@dataclass
class Criterion:
    id: ID
    description: str
    verification_method: str


@dataclass
class RequestedAction:
    action_ref: ID
    kind: ActionKind
    resource_ref: Ref
    required_tool: Ref | None
    host_decision: HostDecision


@dataclass
class AuthorizationScope:
    action_kind: ActionKind
    resource_ref: Ref
    source_ref: Ref


@dataclass
class SelectedCapability:
    id: ID
    version: Version
    deployed_sha256: Digest


@dataclass
class Selection:
    catalog_revision: Positive
    agents: list[SelectedCapability]
    skills: list[SelectedCapability]


@dataclass
class Limits:
    max_correction_cycles: Positive = 3
    max_parallel_children: Positive = 2


@dataclass
class Artifact:
    id: ID
    relative_path: RelativePath
    sha256: Digest


@dataclass
class CandidateSnapshot:
    artifacts: list[Artifact]
    candidate_id: Digest


@dataclass
class AcceptanceSnapshot:
    criteria: list[Criterion]
    design_sha256: Digest
    acceptance_id: Digest


@dataclass
class Finding:
    id: ID
    severity: Severity
    description: str
    criterion_ids: list[ID]


@dataclass
class Disposition:
    finding_id: ID
    decision: DispositionDecision
    reason: str
    evidence_refs: list[Ref]


@dataclass
class ReviewReceipt:
    reviewer_ref: Ref
    implementer_ref: Ref
    candidate_id: Digest
    acceptance_id: Digest
    observed_at: UTC
    findings: list[Finding]


@dataclass
class CheckReceipt:
    check_id: ID
    criterion_ids: list[ID]
    candidate_id: Digest
    acceptance_id: Digest
    method: CheckMethod
    command: str | None
    observation: str | None
    environment: dict[str, str]
    outcome: CheckOutcome
    evidence_ref: Ref
    observed_at: UTC


@dataclass
class CycleEvidence:
    cycle_number: Positive
    design_ref: Ref
    candidate: CandidateSnapshot
    acceptance: AcceptanceSnapshot
    review: ReviewReceipt
    dispositions: list[Disposition]
    checks: list[CheckReceipt]


@dataclass
class TaskRecord:
    schema_version: Schema
    id: ID
    revision: Positive
    request: RequestEnvelope
    status: TaskStatus
    phase: TaskPhase
    parent_task_id: ID | None
    capability_ids: list[ID]
    criteria: list[Criterion]
    selection: Selection
    limits: Limits
    authorization: list[AuthorizationScope]
    requested_actions: list[RequestedAction]
    cycles: list[CycleEvidence]
    blockers: list[str]
    resume_next_step: EmptyString
    artifact_root: Ref


@dataclass
class TaskAssignment:
    task_id: ID
    assignment_revision: Positive
    role_id: ID
    selected_skill_ids: list[ID]
    design_ref: Ref
    criteria: list[Criterion]
    context: ContextBundle
    owned_paths: list[RelativePath]
    selection: Selection
    limits: Limits


@dataclass
class Handoff:
    schema_version: Schema
    task_id: ID
    assignment_revision: Positive
    role_id: ID
    result: HandoffResult
    artifacts: list[Artifact]
    criteria_coverage: dict[ID, list[Ref]]
    evidence_refs: list[Ref]
    blocker: str | None
    next_step: EmptyString


@dataclass
class PendingAction:
    action_ref: ID
    reason: str


@dataclass
class PreflightResult:
    ready: bool
    missing_tools: list[Ref]
    pending_actions: list[PendingAction]


@dataclass
class ErrorDetail:
    code: str
    path: str
    message: str


@dataclass
class GateResult:
    passed: bool
    errors: list[ErrorDetail]


@dataclass
class DeploymentFile:
    relative_path: RelativePath
    sha256: Digest


@dataclass
class DeploymentManifest:
    files: list[DeploymentFile]
    manifest_sha256: Digest


@dataclass
class NativeProbeReceipt:
    schema_version: Schema
    operation_id: ID
    capability_id: ID
    version: Version
    manifest_sha256: Digest
    purpose: ProbePurpose
    client_name: str
    client_version: Ref
    session_ref: Ref
    discovered: bool
    invoked: bool | None
    observed_at: UTC
    evidence_refs: list[Ref]


@dataclass
class PreflightRequest:
    schema_version: Schema
    required_tools: list[Ref]
    available_tools: list[Ref]
    requested_actions: list[RequestedAction]
    authorization: list[AuthorizationScope]


@dataclass
class CapabilityRecord:
    schema_version: Schema
    id: ID
    kind: CapabilityKind
    name: str
    version: Version
    state: CapabilityState
    source_path: RelativePath
    deployed_path: RelativePath | None
    deployed_sha256: Digest | None
    triggers: list[str]
    boundaries: list[str]
    required_inputs: list[str]
    output_contract_ref: Ref
    tool_dependencies: list[Ref]
    validation_refs: list[Ref]
    discovery_probe_ref: Ref | None
    rollback_ref: Ref | None


@dataclass
class CapabilityCatalog:
    schema_version: Schema
    revision: Positive
    records: list[CapabilityRecord]


class ValidationError(ValueError):
    """Rejected contract data, retaining stable structured error details."""

    def __init__(self, errors: list[ErrorDetail]):
        self.errors = errors
        super().__init__('; '.join(f'{e.path}: {e.message}' for e in errors))


class RevisionConflict(Exception):
    """A later task store rejected an update using a stale expected revision."""


_RECORD_TYPES = {
    cls.__name__: cls for cls in (
        RequestEnvelope, ContextFact, ContextBundle, Criterion, RequestedAction,
        AuthorizationScope, SelectedCapability, Selection, Limits, Artifact,
        CandidateSnapshot, AcceptanceSnapshot, Finding, Disposition, ReviewReceipt,
        CheckReceipt, CycleEvidence, TaskRecord, TaskAssignment, Handoff,
        PendingAction, PreflightResult, ErrorDetail, GateResult, DeploymentFile,
        DeploymentManifest, NativeProbeReceipt, PreflightRequest, CapabilityRecord,
        CapabilityCatalog,
    )
}

_ID_PATTERN = re.compile(r'[a-z][a-z0-9_-]{1,63}')
_VERSION_PATTERN = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+')
_DIGEST_PATTERN = re.compile(r'[0-9a-f]{64}')
_TIMESTAMP_PATTERN = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z')


def _error(errors, code, path, message):
    errors.append(ErrorDetail(code, path, message))


def _text(value, path, errors):
    """Reject non-scalar Unicode before payload hashing or serialization."""
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        _error(errors, 'not_json', path, 'Expected UTF-8 encodable Unicode scalar text')
        return False
    return True


def _key_path(path, key):
    if type(key) is str:
        rendered = json.dumps(key, ensure_ascii=False)
    else:
        rendered = repr(key)
    # Only diagnostics escape malformed text; valid canonical payloads stay literal.
    rendered = rendered.encode('utf-8', errors='backslashreplace').decode('utf-8')
    return f'{path}[{rendered}]'


@lru_cache(maxsize=None)
def _hints(cls):
    return get_type_hints(cls, include_extras=True)


def _json_value(value, path, errors, ancestors):
    """Copy finite JSON without accepting arbitrary Python objects or cycles."""
    if type(value) is str:
        return value if _text(value, path, errors) else None
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if math.isfinite(value):
            return value
        _error(errors, 'not_json', path, 'JSON numbers must be finite')
        return None
    if type(value) not in (list, dict):
        _error(errors, 'not_json', path, 'Expected a JSON value')
        return None
    if id(value) in ancestors:
        _error(errors, 'not_json', path, 'Cyclic values cannot be serialized as JSON')
        return None
    ancestors.add(id(value))
    try:
        if type(value) is list:
            return [_json_value(item, f'{path}[{i}]', errors, ancestors)
                    for i, item in enumerate(value)]
        result = {}
        for key, item in value.items():
            child_path = _key_path(path, key)
            if type(key) is not str:
                _error(errors, 'not_json', child_path, 'JSON object keys must be strings')
            elif _text(key, child_path, errors):
                result[key] = _json_value(item, child_path, errors, ancestors)
        return result
    finally:
        ancestors.remove(id(value))


def canonical_json(value: object) -> bytes:
    """Return canonical finite JSON as UTF-8 bytes, or raise ValidationError."""
    errors = []
    wire = _json_value(value, '$', errors, set())
    if errors:
        raise ValidationError(errors)
    return json.dumps(wire, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _scalar_rule(rule, value, path, errors):
    if rule == 'id' and not _ID_PATTERN.fullmatch(value):
        _error(errors, 'invalid_id', path, 'Expected a lowercase record ID of 2–64 characters')
    elif rule == 'version' and not _VERSION_PATTERN.fullmatch(value):
        _error(errors, 'invalid_version', path, 'Expected three nonnegative decimal components')
    elif rule == 'digest' and not _DIGEST_PATTERN.fullmatch(value):
        _error(errors, 'invalid_digest', path, 'Expected a lowercase SHA-256 hex digest')
    elif rule == 'timestamp':
        try:
            if not _TIMESTAMP_PATTERN.fullmatch(value):
                raise ValueError('syntax')
            datetime(int(value[0:4]), int(value[5:7]), int(value[8:10]),
                     int(value[11:13]), int(value[14:16]), int(value[17:19]))
        except ValueError:
            _error(errors, 'invalid_timestamp', path, 'Expected a calendar-valid UTC timestamp with Z suffix')
    elif rule == 'path':
        if (not value or value.startswith('/') or '\\' in value or '\x00' in value
                or any(part in ('', '.', '..') for part in value.split('/'))):
            _error(errors, 'unsafe_path', path, 'Expected a safe nonempty POSIX relative path')
    elif rule == 'positive' and value < 1:
        _error(errors, 'invalid_value', path, 'Expected an integer of at least one')
    elif rule == 'schema' and value != 1:
        _error(errors, 'unsupported_schema', path, 'Only schema version 1 is supported')


def _decode(expected, value, path, errors):
    if type(value) is str and not _text(value, path, errors):
        return None
    origin = get_origin(expected)
    args = get_args(expected)
    if origin is Annotated:
        base, rule = args
        if rule == 'json':
            return _json_value(value, path, errors, set())
        # Annotated strings use the semantic rule's error for malformed/empty values.
        if base is str and type(value) is str:
            _scalar_rule(rule, value, path, errors)
            return value
        before = len(errors)
        decoded = _decode(base, value, path, errors)
        if len(errors) == before:
            _scalar_rule(rule, decoded, path, errors)
        return decoded
    if origin in (Union, UnionType):
        if value is None and type(None) in args:
            return None
        # Contract unions have a single non-null alternative.
        return _decode(next(arg for arg in args if arg is not type(None)), value, path, errors)
    if origin is list:
        if type(value) is not list:
            _error(errors, 'invalid_type', path, 'Expected a JSON array')
            return None
        return [_decode(args[0], item, f'{path}[{i}]', errors)
                for i, item in enumerate(value)]
    if origin is dict:
        if type(value) is not dict:
            _error(errors, 'invalid_type', path, 'Expected a JSON object')
            return None
        result = {}
        for key, item in value.items():
            child_path = _key_path(path, key)
            before = len(errors)
            decoded_key = _decode(args[0], key, child_path, errors)
            decoded_value = _decode(args[1], item, child_path, errors)
            if len(errors) == before:
                result[decoded_key] = decoded_value
        return result
    if isinstance(expected, type) and issubclass(expected, Enum):
        if type(value) is not str:
            _error(errors, 'invalid_type', path, 'Expected an enum string')
            return None
        try:
            return expected(value)
        except ValueError:
            _error(errors, 'invalid_enum', path, f'Unknown {expected.__name__} value')
            return None
    if isinstance(expected, type) and is_dataclass(expected):
        if type(value) is not dict:
            _error(errors, 'invalid_type', path, f'Expected a {expected.__name__} object')
            return None
        before = len(errors)
        hints = _hints(expected)
        for key in value:
            if type(key) is not str:
                _error(errors, 'invalid_type', _key_path(path, key), 'Record keys must be strings')
            elif not _text(key, _key_path(path, key), errors):
                continue
            elif key not in hints:
                _error(errors, 'unknown_field', f'{path}.{key}', 'Unknown v1 field')
        values = {}
        for field, field_type in hints.items():
            child_path = f'{path}.{field}'
            if field not in value:
                _error(errors, 'missing_field', child_path, 'Required field is missing')
            else:
                values[field] = _decode(field_type, value[field], child_path, errors)
        if len(errors) != before:
            return None
        record = expected(**values)
        _invariants(record, value, path, errors)
        return record
    if type(value) is not expected:
        _error(errors, 'invalid_type', path, f'Expected {expected.__name__}')
        return None
    if expected is str and not value:
        _error(errors, 'invalid_value', path, 'Expected a nonempty string')
    return value


def _snapshot(record, wire, path, errors, field, identity, digest_field, payload):
    items = getattr(record, field)
    identities = [getattr(item, identity) for item in items]
    seen = set()
    for index, item_id in enumerate(identities):
        if item_id in seen:
            _error(errors, 'duplicate_id', f'{path}.{field}[{index}].{identity}', 'Duplicate snapshot identity')
        seen.add(item_id)
    if identities != sorted(identities):
        _error(errors, 'unsorted', f'{path}.{field}', 'Snapshot entries must be sorted by identity')
    actual = hashlib.sha256(canonical_json(payload)).hexdigest()
    if getattr(record, digest_field) != actual:
        _error(errors, 'digest_mismatch', f'{path}.{digest_field}', 'Declared fingerprint does not match canonical payload')


def _invariants(record, wire, path, errors):
    if isinstance(record, GateResult):
        if record.passed != (not record.errors):
            _error(errors, 'inconsistent_gate', f'{path}.passed', 'passed must be true iff errors is empty')
    elif isinstance(record, PreflightResult):
        if record.ready != (not record.missing_tools and not record.pending_actions):
            _error(errors, 'inconsistent_gate', f'{path}.ready', 'ready must be true iff tools/actions are clear')
    elif isinstance(record, CheckReceipt):
        required, absent = ('command', 'observation') if record.method is CheckMethod.COMMAND else ('observation', 'command')
        if getattr(record, required) is None:
            _error(errors, 'invalid_value', f'{path}.{required}', f'{required} is required for this check method')
        if getattr(record, absent) is not None:
            _error(errors, 'invalid_value', f'{path}.{absent}', f'{absent} must be null for this check method')
    elif isinstance(record, CandidateSnapshot):
        _snapshot(record, wire, path, errors, 'artifacts', 'id', 'candidate_id', wire['artifacts'])
    elif isinstance(record, AcceptanceSnapshot):
        payload = {'criteria': wire['criteria'], 'design_sha256': wire['design_sha256']}
        _snapshot(record, wire, path, errors, 'criteria', 'id', 'acceptance_id', payload)
    elif isinstance(record, DeploymentManifest):
        _snapshot(record, wire, path, errors, 'files', 'relative_path', 'manifest_sha256', wire['files'])


def _validated(kind, data):
    errors = []
    cls = _RECORD_TYPES.get(kind) if type(kind) is str else None
    if cls is None:
        _error(errors, 'unknown_kind', '$', 'Unknown contract record kind')
        return None, errors
    return _decode(cls, data, '$', errors), errors


def validate_record(kind: str, data: dict) -> GateResult:
    """Validate a complete wire record recursively, returning stable error details."""
    _, errors = _validated(kind, data)
    return GateResult(not errors, errors)


def from_dict(kind: str, data: dict) -> object:
    """Decode valid wire data to nested dataclasses/enums; reject invalid input."""
    record, errors = _validated(kind, data)
    if errors:
        raise ValidationError(errors)
    return record


def _encode(value, path, errors, ancestors, expected=None):
    origin = get_origin(expected)
    args = get_args(expected)
    if origin is Annotated and args[1] == 'json':
        return _json_value(value, path, errors, ancestors)
    if isinstance(value, Enum):
        return value.value
    if type(value) is str:
        return value if _text(value, path, errors) else None
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if math.isfinite(value):
            return value
        _error(errors, 'not_json', path, 'JSON numbers must be finite')
        return None
    if type(value) not in (dict, list) and type(value) not in _RECORD_TYPES.values():
        _error(errors, 'not_json', path, 'Expected a supported dataclass or JSON value')
        return None
    if id(value) in ancestors:
        _error(errors, 'not_json', path, 'Cyclic values cannot be serialized as JSON')
        return None
    ancestors.add(id(value))
    try:
        if type(value) in _RECORD_TYPES.values():
            hints = _hints(type(value))
            return {field.name: _encode(getattr(value, field.name), f'{path}.{field.name}',
                                        errors, ancestors, hints[field.name])
                    for field in fields(value)}
        if type(value) is list:
            child_type = args[0] if origin is list else None
            return [_encode(item, f'{path}[{i}]', errors, ancestors, child_type)
                    for i, item in enumerate(value)]
        result = {}
        for key, item in value.items():
            child_path = _key_path(path, key)
            if type(key) is not str:
                _error(errors, 'not_json', child_path, 'JSON object keys must be strings')
            elif _text(key, child_path, errors):
                child_type = args[1] if origin is dict else None
                result[key] = _encode(item, child_path, errors, ancestors, child_type)
        return result
    finally:
        ancestors.remove(id(value))


def to_dict(record: object) -> dict:
    """Serialize an exported contract dataclass, validating its complete wire form."""
    if type(record) not in _RECORD_TYPES.values():
        raise ValidationError([ErrorDetail('unknown_kind', '$', 'Expected a supported record dataclass')])
    errors = []
    wire = _encode(record, '$', errors, set())
    if errors:
        raise ValidationError(errors)
    result = validate_record(type(record).__name__, wire)
    if not result.passed:
        raise ValidationError(result.errors)
    return wire



def validate_handoff(assignment: TaskAssignment, handoff: Handoff,
                     artifact_root: Path) -> GateResult:
    """Check a child output before integration; a pass means ready for review.

    This reads current files but never updates task state or proves semantic
    coverage, authorization, reviewer independence or completion. Owned paths
    are exact files. The parent serializes file mutations and propagates rejected
    required-child blockers into its own task record.
    """
    errors = []

    def issue(code, path, message):
        errors.append(ErrorDetail(code, path, message))

    if type(assignment) is not TaskAssignment or type(handoff) is not Handoff:
        return GateResult(False, [ErrorDetail('invalid_type', '$',
                                             'Expected TaskAssignment and Handoff')])
    try:
        assignment = from_dict('TaskAssignment', to_dict(assignment))
        handoff = from_dict('Handoff', to_dict(handoff))
    except ValidationError as error:
        return GateResult(False, error.errors)

    if handoff.task_id != assignment.task_id:
        issue('wrong_task', '$.task_id', 'Handoff belongs to another task')
    if handoff.assignment_revision != assignment.assignment_revision:
        issue('stale_assignment', '$.assignment_revision', 'Assignment revision differs')
    if handoff.role_id != assignment.role_id:
        issue('wrong_role', '$.role_id', 'Handoff role differs from assigned role')
    criterion_ids = [criterion.id for criterion in assignment.criteria]
    if (not criterion_ids or len(criterion_ids) != len(set(criterion_ids))
            or not assignment.owned_paths
            or len(assignment.owned_paths) != len(set(assignment.owned_paths))):
        issue('invalid_assignment', '$.assignment', 'Criteria and ownership must be nonempty and unique')
    ready = handoff.result is HandoffResult.READY_FOR_REVIEW
    if ready:
        if handoff.blocker is not None:
            issue('inconsistent_handoff', '$.blocker', 'Ready handoff cannot have a blocker')
        if not handoff.artifacts:
            issue('missing_artifact', '$.artifacts', 'Ready handoff requires product artifacts')
        if set(handoff.criteria_coverage) != set(criterion_ids):
            issue('incomplete_coverage', '$.criteria_coverage', 'Ready handoff must cover assigned criteria')
    else:
        if handoff.blocker is None or not handoff.blocker.strip():
            issue('missing_blocker', '$.blocker', 'Blocked or failed handoff requires a reason')
        issue('blocked_child' if handoff.result is HandoffResult.BLOCKED else 'failed_child',
              '$.result', 'Required child is not ready for integration')
    if not handoff.next_step.strip():
        issue('missing_next_step', '$.next_step', 'Handoff requires an actionable next step')
    for criterion, refs in handoff.criteria_coverage.items():
        if criterion not in criterion_ids:
            issue('unknown_criterion', '$.criteria_coverage', 'Coverage names an unassigned criterion')
        if not refs:
            issue('incomplete_coverage', '$.criteria_coverage', 'Coverage requires local evidence')
    ids = [artifact.id for artifact in handoff.artifacts]
    paths = [artifact.relative_path for artifact in handoff.artifacts]
    if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
        issue('duplicate_artifact', '$.artifacts', 'Artifact IDs and paths must be unique')

    # Deferred import keeps the frozen records importable by quality itself.
    from .quality import _file_hash, _relative, _root
    try:
        if (not isinstance(artifact_root, Path) or not artifact_root.is_absolute()
                or artifact_root.resolve(strict=True) != artifact_root):
            issue('invalid_artifact_root', '$.artifact_root', 'Expected a canonical absolute artifact root')
            return GateResult(False, errors)
        for path in assignment.owned_paths:
            _relative(path, 'invalid_assignment', '$.owned_paths')
        with _root(artifact_root, 'invalid_artifact_root', '$.artifact_root') as fd:
            for index, artifact in enumerate(handoff.artifacts):
                path = f'$.artifacts[{index}]'
                if artifact.relative_path not in assignment.owned_paths:
                    issue('outside_ownership', path, 'Artifact is outside exact-file ownership')
                try:
                    digest = _file_hash(fd, artifact.relative_path, 'invalid_artifact_path',
                                        'missing_artifact', path)
                    if digest != artifact.sha256:
                        issue('artifact_digest_mismatch', path, 'Artifact bytes differ from handoff')
                except ValidationError as error:
                    errors.extend(error.errors)
            references = list(handoff.evidence_refs)
            references.extend(ref for refs in handoff.criteria_coverage.values() for ref in refs)
            for ref in sorted(set(references)):
                try:
                    _file_hash(fd, ref, 'invalid_evidence_path', 'missing_evidence', '$.evidence_refs')
                except ValidationError as error:
                    errors.extend(error.errors)
    except ValidationError as error:
        errors.extend(error.errors)
    except (OSError, ValueError, RuntimeError):
        issue('invalid_artifact_root', '$.artifact_root', 'Artifact root is unavailable or unsafe')
    return GateResult(not errors, errors)


__all__ = list(_RECORD_TYPES) + [
    'TaskStatus', 'TaskPhase', 'CapabilityKind', 'CapabilityState', 'ActionKind',
    'HostDecision', 'Severity', 'DispositionDecision', 'CheckMethod', 'CheckOutcome',
    'HandoffResult', 'ProbePurpose', 'ValidationError', 'RevisionConflict',
    'validate_record', 'from_dict', 'to_dict', 'canonical_json', 'validate_handoff',
]
