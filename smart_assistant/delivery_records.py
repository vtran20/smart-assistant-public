"""Versioned delivery integrity. Hashes bind bytes, not actor authenticity.

P12/P16 enforce semantic evidence, authorization and native observations.
Frozen v1 payloads and wire validators remain unchanged.
"""
from __future__ import annotations
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
import hashlib
from pathlib import Path
import re
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin, get_type_hints
import unicodedata
from . import delivery_semantics as _semantics
from .contracts import (TaskAssignment, Handoff, RequestEnvelope, TaskRecord,
    TaskStatus, GateResult, ValidationError, ErrorDetail, canonical_json,
    from_dict, to_dict, validate_handoff)

ID = Annotated[str, 'id']
Digest = Annotated[str, 'digest']
UTC = Annotated[str, 'utc']
Positive = Annotated[int, 'positive']
FilePath = Annotated[str, 'path']
Absolute = Annotated[str, 'absolute']
Text = Annotated[str, 'text']
SCHEMA = Literal['1.0']
PREFIX = 'smart-assistant:delivery-policy:'

@dataclass(frozen=True)
class DeliveryPolicy:
    schema_version: SCHEMA
    policy_id: ID
    policy_version: Text
    workflow_kind: Literal['bug', 'feature', 'document', 'research']
    source_ref: Text
    source_sha256: Digest
    reproduction_required: bool
    independent_review_required: bool
    required_verification_levels: list[Text]
    max_executing: Positive
    max_correction_cycles: Positive

@dataclass(frozen=True)
class DeliveryRegistration:
    schema_version: SCHEMA
    task_id: ID
    request_sha256: Digest
    policy_id: ID
    policy_sha256: Digest
    registered_at: UTC

@dataclass(frozen=True)
class DeliveryPlan:
    schema_version: SCHEMA
    task_id: ID
    revision: Positive
    request_sha256: Digest
    policy_sha256: Digest
    root_owner_ref: Text
    design_sha256: Digest
    acceptance_sha256: Digest
    routing_rationale: Text
    requirement_ids: list[ID]
    assignment_ids: list[ID]
    max_executing: Positive
    max_correction_cycles: Positive
    context_sha256: Digest
    next_step: str

@dataclass(frozen=True)
class DependencyPin:
    schema_version: SCHEMA
    assignment_id: ID
    accepted_revision: Positive | None
    output_sha256: Digest | None

@dataclass(frozen=True)
class ObservedRun:
    schema_version: SCHEMA
    host_ref: Text
    actor_ref: Text
    run_ref: Text
    dispatch_token: ID
    observed_at: UTC
    observation_ref: Text

@dataclass(frozen=True)
class DispatchIntent:
    schema_version: SCHEMA
    dispatch_token: ID
    assignment_id: ID
    envelope_revision: Positive
    envelope_sha256: Digest
    created_at: UTC
    state: Literal['pending', 'observed', 'ambiguous', 'terminated', 'absent']
    observed_run: ObservedRun | None
    reconciliation_ref: Text | None

@dataclass(frozen=True)
class AssignmentEnvelope:
    schema_version: SCHEMA
    assignment_id: ID
    revision: Positive
    task_id: ID
    parent_assignment_id: ID | None
    required: bool
    payload: TaskAssignment
    selected_role_id: ID
    selected_role_version: Text
    selected_manifest_sha256: Digest
    base_ref: Text
    workspace_id: ID
    worktree_root: Absolute
    owned_paths: list[FilePath]
    dependencies: list[DependencyPin]
    state: Literal['proposed', 'dispatched', 'working', 'ready_for_review',
        'changes_requested', 'accepted', 'blocked', 'failed', 'cancelled', 'superseded']
    dispatch_token: ID | None
    observed_run: ObservedRun | None
    output_sha256: Digest | None
    handoff_submission_id: ID | None
    review_refs: list[Text]
    invalidated_by: list[ID]

@dataclass(frozen=True)
class HandoffSubmission:
    schema_version: SCHEMA
    submission_id: ID
    task_id: ID
    assignment_id: ID
    envelope_revision: Positive
    envelope_sha256: Digest
    payload: Handoff
    handoff_sha256: Digest
    observed_run: ObservedRun
    submitted_at: UTC

@dataclass(frozen=True)
class DecisionReceipt:
    schema_version: SCHEMA
    receipt_id: ID
    task_id: ID
    kind: Literal['dispatch', 'handoff_rejected', 'handoff_accepted', 'review', 'feedback',
        'integration', 'reassignment', 'invalidation', 'cancellation', 'research', 'redesign', 'recovery']
    actor_ref: Text
    plan_revision: Positive
    assignment_id: ID | None
    assignment_revision: Positive | None
    candidate_sha256: Digest | None
    evidence_refs: list[Text]
    reason: Text
    created_at: UTC

@dataclass(frozen=True)
class DeliverySnapshot:
    schema_version: SCHEMA
    task_id: ID
    revision: Positive
    previous_sha256: Digest | None
    registration: DeliveryRegistration
    policy: DeliveryPolicy
    plan: DeliveryPlan
    assignments: list[AssignmentEnvelope]
    dispatches: list[DispatchIntent]
    submissions: list[HandoffSubmission]
    decisions: list[DecisionReceipt]

DeliveryRecord = (DeliveryPolicy | DeliveryRegistration | DeliveryPlan | DependencyPin |
    ObservedRun | DispatchIntent | AssignmentEnvelope | HandoffSubmission | DecisionReceipt | DeliverySnapshot)
_TYPES = {t.__name__: t for t in get_args(DeliveryRecord)}

@dataclass(frozen=True)
class DispatchStatus:
    allowed: bool
    occupied_tokens: list[str]
    blockers: list[str]

def _fail(code, path, message):
    raise ValidationError([ErrorDetail(code, path, message)])

def _require(condition, code, path, message):
    if not condition: _fail(code, path, message)

def _path(value, path):
    _require(bool(value) and not value.startswith('/') and not any(c in value for c in '\\:\x00*?[]')
        and all(p not in ('', '.', '..') for p in value.split('/'))
        and unicodedata.normalize('NFC', value) == value, 'unsafe_path', path,
        'Expected canonical exact POSIX relative file path')

def _scalar(rule, value, path):
    if rule == 'id':
        _require(bool(re.fullmatch(r'[a-z][a-z0-9_-]{1,63}', value)), 'invalid_id', path, 'Invalid record ID')
    elif rule == 'digest':
        _require(bool(re.fullmatch(r'[a-f0-9]{64}', value)), 'invalid_digest', path, 'Expected lowercase SHA256')
    elif rule == 'positive':
        _require(value > 0, 'invalid_revision', path, 'Expected positive integer')
    elif rule == 'text':
        _require(bool(value.strip()), 'invalid_type', path, 'Expected nonblank text')
    elif rule == 'utc':
        _require(bool(re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z', value)),
            'invalid_timestamp', path, 'Expected explicit UTC timestamp')
        try: datetime.fromisoformat(value[:-1] + '+00:00')
        except ValueError: _fail('invalid_timestamp', path, 'Invalid calendar timestamp')
    elif rule == 'path': _path(value, path)
    elif rule == 'absolute':
        _require(value.startswith('/') and value != '/', 'unsafe_path', path, 'Expected absolute worktree path')
        _path(value[1:], path)

def _decode(expected, value, path):
    origin, args = get_origin(expected), get_args(expected)
    if origin is Annotated:
        result = _decode(args[0], value, path); _scalar(args[1], result, path)
        return result
    if origin in (Union, UnionType):
        if value is None and type(None) in args: return None
        for option in args:
            if option is not type(None):
                try: return _decode(option, value, path)
                except ValidationError: pass
        _fail('invalid_type', path, 'No permitted union type matches')
    if origin is Literal:
        _require(type(value) is str and value in args, 'unsupported_version' if path.endswith('schema_version') else 'invalid_type', path, 'Unsupported value')
        return value
    if origin is list:
        _require(type(value) is list, 'invalid_type', path, 'Expected list')
        return [_decode(args[0], v, f'{path}[{i}]') for i,v in enumerate(value)]
    if expected in (TaskAssignment, Handoff): return from_dict(expected.__name__, value)
    if expected in _TYPES.values():
        _require(type(value) is dict, 'invalid_type', path, 'Expected record object')
        _require(set(value) == {f.name for f in fields(expected)}, 'unknown_field', path, 'Missing or unknown fields')
        hints = get_type_hints(expected, include_extras=True)
        result = expected(**{name: _decode(hints[name], value[name], f'{path}.{name}') for name in hints})
        _local(result,path)
        return result
    _require(type(value) is expected, 'invalid_type', path, f'Expected {expected.__name__}')
    return value

def _raw(value, ancestors):
    if type(value) in (TaskAssignment, Handoff): return to_dict(value)
    if is_dataclass(value) and type(value) not in _TYPES.values(): _fail('invalid_type','$','Unknown record')
    if is_dataclass(value) or type(value) in (list, dict):
        _require(id(value) not in ancestors, 'invalid_type', '$', 'Cyclic delivery value')
        ancestors = ancestors | {id(value)}
        if is_dataclass(value): return {f.name:_raw(getattr(value,f.name),ancestors) for f in fields(value)}
        if type(value) is list: return [_raw(v,ancestors) for v in value]
        return {k:_raw(v,ancestors) for k,v in value.items()}
    return value

def delivery_from_dict(kind: str, data: dict) -> DeliveryRecord:
    _require(type(kind) is str and kind in _TYPES,'invalid_type','$','Unknown delivery kind')
    canonical_json(data)
    return _decode(_TYPES[kind],data,'$')

def delivery_to_dict(record: DeliveryRecord) -> dict:
    _require(type(record) in _TYPES.values(),'invalid_type','$','Expected delivery record')
    raw = _raw(record,set()); delivery_from_dict(type(record).__name__,raw)
    return raw

def delivery_digest(record: DeliveryRecord) -> str:
    return hashlib.sha256(canonical_json(delivery_to_dict(record))).hexdigest()

def request_digest(request: RequestEnvelope) -> str:
    _require(type(request) is RequestEnvelope,'invalid_type','$','Expected v1 request')
    return hashlib.sha256(canonical_json(to_dict(request))).hexdigest()

def policy_source_ref(policy: DeliveryPolicy) -> str:
    return f'{PREFIX}1.0:{policy.policy_id}:{delivery_digest(policy)}'

def _unique(values,path):
    _require(len(values)==len(set(values)),'invalid_type',path,'Duplicate values')

def _local(record,path):
    if isinstance(record,DeliveryPolicy):
        _require(record.max_executing<=2 and record.max_correction_cycles<=3,'invalid_type',path,'Policy exceeds bounds')
        _require(bool(record.required_verification_levels),'invalid_type',path,'Verification levels required')
        _unique(record.required_verification_levels,path)
    elif isinstance(record,DeliveryPlan):
        _require(bool(record.requirement_ids),'invalid_type',path,'Requirements required')
        _unique(record.requirement_ids,path); _unique(record.assignment_ids,path)
    elif isinstance(record,DependencyPin):
        _require((record.accepted_revision is None)==(record.output_sha256 is None),'stale_dependency',path,'Pin fields must both be null or populated')
    elif isinstance(record,AssignmentEnvelope):
        for name in ('owned_paths','review_refs','invalidated_by'): _unique(getattr(record,name),f'{path}.{name}')
        _unique([p.assignment_id for p in record.dependencies],f'{path}.dependencies')
    elif isinstance(record,HandoffSubmission):
        digest=hashlib.sha256(canonical_json(to_dict(record.payload))).hexdigest()
        _require(digest==record.handoff_sha256,'invalid_digest',path,'Handoff digest differs')
    elif isinstance(record,DecisionReceipt):
        _unique(record.evidence_refs,path)
        _require((record.assignment_id is None)==(record.assignment_revision is None),'invalid_type',path,'Assignment fields must both be null/populated')

_ASSIGNMENT_TRANSITIONS = {
    'proposed': {'dispatched','blocked','cancelled','superseded'},
    'dispatched': {'working','ready_for_review','blocked','failed','cancelled','superseded'},
    'working': {'ready_for_review','blocked','failed','cancelled','superseded'},
    'ready_for_review': {'changes_requested','accepted','blocked','failed','cancelled','superseded'},
    'changes_requested': {'working','blocked','failed','cancelled','superseded'},
    'blocked': {'proposed','working','failed','cancelled','superseded'},
    'accepted': {'superseded','changes_requested'}, 'failed': set(), 'cancelled': set(), 'superseded': set()}
_INTENT_TRANSITIONS = {'pending': {'observed','ambiguous','absent'},
    'ambiguous': {'observed','absent'}, 'observed': {'terminated'}, 'terminated': set(), 'absent': set()}
_TERMINAL = {'failed','cancelled','superseded'}

def _scope(e):
    return _semantics.scope_key(delivery_to_dict(e),mode='managed')

def _acyclic(edges):
    degrees={key:len(deps) for key,deps in edges.items()}
    dependents={key:[] for key in edges}
    for key,deps in edges.items():
        for dep in deps:
            _require(dep in edges and dep!=key,'invalid_graph','$.assignments','Unknown/self edge')
            dependents[dep].append(key)
    pending=[key for key,n in degrees.items() if not n]; seen=0
    while pending:
        key=pending.pop(); seen+=1
        for child in dependents[key]:
            degrees[child]-=1
            if not degrees[child]: pending.append(child)
    _require(seen==len(edges),'invalid_graph','$.assignments','Cyclic assignment graph')

def _pins_current(e,assignments):
    return all((pin.accepted_revision,pin.output_sha256)==
        (assignments[pin.assignment_id].revision,assignments[pin.assignment_id].output_sha256)
        and assignments[pin.assignment_id].state=='accepted' for pin in e.dependencies)

def dispatch_status(snapshot: DeliverySnapshot) -> DispatchStatus:
    snapshot=delivery_from_dict('DeliverySnapshot',delivery_to_dict(snapshot))
    occupied=[d.dispatch_token for d in snapshot.dispatches if d.state not in ('terminated','absent')]
    blockers=['Shared execution limit reached'] if len(occupied)>=snapshot.plan.max_executing else []
    return DispatchStatus(not blockers,occupied,blockers)

def _submission_binding(e,s,intent):
    return _semantics.check_submission_binding(delivery_to_dict(e),delivery_to_dict(s),
        delivery_to_dict(intent),mode='managed')

def validate_submission(envelope: AssignmentEnvelope, submission: HandoffSubmission,
                        intent: DispatchIntent, artifact_root: Path, *,
                        dispatched_envelope: AssignmentEnvelope | None = None) -> GateResult:
    try:
        envelope=delivery_from_dict('AssignmentEnvelope',delivery_to_dict(envelope))
        submission=delivery_from_dict('HandoffSubmission',delivery_to_dict(submission))
        intent=delivery_from_dict('DispatchIntent',delivery_to_dict(intent))
        _submission_binding(envelope,submission,intent)
        _require(intent.envelope_revision<=envelope.revision,'stale_assignment','$.intent','Dispatch targets a future envelope')
        if dispatched_envelope is None:
            _require(intent.envelope_revision==envelope.revision,'missing_dispatch_context','$.intent',
                'Changed current envelope requires immutable original dispatched envelope')
            original=envelope
        else:
            original=delivery_from_dict('AssignmentEnvelope',delivery_to_dict(dispatched_envelope))
        _require(original.assignment_id==envelope.assignment_id and original.task_id==envelope.task_id
            and original.revision==intent.envelope_revision and delivery_digest(original)==intent.envelope_sha256
            and original.dispatch_token==intent.dispatch_token and original.state=='dispatched'
            and original.observed_run is None and _scope(original)==_scope(envelope),
            'stale_assignment','$.intent','Original dispatch digest/identity/scope differs')
        _require(isinstance(artifact_root,Path) and str(artifact_root)==envelope.worktree_root,
            'unsafe_path','$.artifact_root','Artifact root differs from assigned worktree')
        return validate_handoff(envelope.payload,submission.payload,artifact_root)
    except ValidationError as error: return GateResult(False,error.errors)

def _snapshot_checks(s,task):
    _semantics.check_snapshot(delivery_to_dict(s),task,mode='managed')
    return {e.assignment_id:e for e in s.assignments}

def _history(s,previous):
    return _semantics.check_history(delivery_to_dict(s),delivery_to_dict(previous),mode='managed')

def validate_delivery(snapshot: DeliverySnapshot, task: TaskRecord,
                      previous: DeliverySnapshot | None = None) -> GateResult:
    """Check structural integrity; a pass is not delivery approval/completion."""
    try:
        s=delivery_from_dict('DeliverySnapshot',delivery_to_dict(snapshot))
        _require(type(task) is TaskRecord,'invalid_type','$','Expected current TaskRecord')
        task=from_dict('TaskRecord',to_dict(task))
        _require(task.status not in (TaskStatus.CANCELLED,TaskStatus.COMPLETED),
            'invalid_transition','$.status','Terminal task cannot mutate delivery')
        _snapshot_checks(s,task)
        if previous is not None:
            previous=delivery_from_dict('DeliverySnapshot',delivery_to_dict(previous)); _history(s,previous)
        return GateResult(True,[])
    except ValidationError as error: return GateResult(False,error.errors)
