"""Strict builtin 2.0 records. Integrity is not host authenticity or acceptance."""
from __future__ import annotations
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import UnionType
from typing import Literal, Union, get_args, get_origin, get_type_hints, Annotated
from . import contracts as c
from . import delivery_records as d
from .delivery_records import ID, Digest, UTC, Positive, FilePath, Absolute, Text
from .delivery_records import DeliveryRegistration, DeliveryPolicy, DeliveryPlan, DependencyPin, ObservedRun, DecisionReceipt
from .preflight import preflight
from .quality import _root, _file_hash, _candidate, _acceptance
from .delivery_semantics import check_snapshot, check_history, check_submission_binding, scope_key, check_ownership
SCHEMA = Literal['2.0']
MODE_PREFIX = 'smart-assistant:execution-mode:'
Responsibility = Literal['implementer','reviewer','qa','technical-lead']
AssignmentState = Literal['proposed','dispatched','working','ready_for_review','changes_requested','accepted','blocked','failed','cancelled','superseded']
IntentState = Literal['pending','observed','ambiguous','terminated','absent']

@dataclass(frozen=True)
class BuiltinReceipt:
    path: FilePath
    sha256: Digest

@dataclass(frozen=True)
class BuiltinDecision:
    schema_version: SCHEMA
    task_id: ID
    base_request_sha256: Digest
    mode: Literal['builtin']
    authorization_source_ref: Text
    decided_by_actor_ref: Text
    decided_at: UTC
    rationale: Text
    configured_capability_requested: Literal[False]

@dataclass(frozen=True)
class BuiltinAuthority:
    schema_version: SCHEMA
    task_id: ID
    request_sha256: Digest
    project_id: ID
    artifact_root: Absolute
    required_tools: list[Text]
    available_tools: list[Text]
    requested_actions: list[c.RequestedAction]
    authorization: list[c.AuthorizationScope]
    observed_at: UTC
    observation: BuiltinReceipt

@dataclass(frozen=True)
class BuiltinRepairAuthorization:
    schema_version: SCHEMA
    task_id: ID
    request_sha256: Digest
    design_sha256: Digest
    acceptance_sha256: Digest
    context_sha256: Digest
    baseline_candidate: c.CandidateSnapshot
    baseline_archive: dict[FilePath,BuiltinReceipt]
    before_receipts: list[BuiltinReceipt]
    assessed_by_actor_ref: Text
    assessed_at: UTC
    assessment_ref: BuiltinReceipt

@dataclass(frozen=True)
class BuiltinPayload:
    schema_version: SCHEMA
    task_id: ID
    assignment_revision: Positive
    responsibility: Responsibility
    design_ref: FilePath
    criteria: list[c.Criterion]
    context: c.ContextBundle
    owned_paths: list[FilePath]
    limits: c.Limits
    prompt: BuiltinReceipt
    instructions: list[BuiltinReceipt]
    authority: BuiltinAuthority
    purpose: Literal['reproduce','repair','review','other']
    repair_authorization: BuiltinRepairAuthorization | None

@dataclass(frozen=True)
class BuiltinAssignment:
    schema_version: SCHEMA
    assignment_id: ID
    revision: Positive
    task_id: ID
    parent_assignment_id: ID | None
    required: bool
    payload: BuiltinPayload
    base_ref: Text
    workspace_id: ID
    worktree_root: Absolute
    owned_paths: list[FilePath]
    dependencies: list[DependencyPin]
    state: AssignmentState
    dispatch_token: ID | None
    observed_run: ObservedRun | None
    output_sha256: Digest | None
    handoff_submission_id: ID | None
    review_refs: list[Text]
    invalidated_by: list[ID]

@dataclass(frozen=True)
class BuiltinHostBinding:
    schema_version: SCHEMA
    task_id: ID
    assignment_id: ID
    dispatch_token: ID
    dispatched_envelope_sha256: Digest
    prompt_sha256: Digest
    instruction_sha256: list[Digest]
    authority_sha256: Digest
    run: ObservedRun
    submitted_call: BuiltinReceipt
    observed_response: BuiltinReceipt

@dataclass(frozen=True)
class BuiltinDispatch:
    schema_version: SCHEMA
    dispatch_token: ID
    assignment_id: ID
    envelope_revision: Positive
    envelope_sha256: Digest
    created_at: UTC
    state: IntentState
    observed_run: ObservedRun | None
    reconciliation_ref: Text | None
    host_binding: BuiltinHostBinding | None

@dataclass(frozen=True)
class BuiltinHandoff:
    schema_version: SCHEMA
    task_id: ID
    assignment_revision: Positive
    responsibility: Responsibility
    result: Literal['ready_for_review','blocked','failed']
    artifacts: list[c.Artifact]
    criteria_coverage: dict[ID,list[FilePath]]
    evidence_refs: list[FilePath]
    blocker: str | None
    next_step: str

@dataclass(frozen=True)
class BuiltinSubmission:
    schema_version: SCHEMA
    submission_id: ID
    task_id: ID
    assignment_id: ID
    envelope_revision: Positive
    envelope_sha256: Digest
    payload: BuiltinHandoff
    handoff_sha256: Digest
    observed_run: ObservedRun
    submitted_at: UTC

@dataclass(frozen=True)
class BuiltinSnapshot:
    schema_version: SCHEMA
    execution_mode: Literal['builtin']
    task_id: ID
    revision: Positive
    previous_sha256: Digest | None
    decision: BuiltinDecision
    registration: DeliveryRegistration
    policy: DeliveryPolicy
    plan: DeliveryPlan
    assignments: list[BuiltinAssignment]
    dispatches: list[BuiltinDispatch]
    submissions: list[BuiltinSubmission]
    decisions: list[DecisionReceipt]

_TYPES = {t.__name__:t for t in (BuiltinReceipt,BuiltinDecision,BuiltinAuthority,BuiltinRepairAuthorization,
    BuiltinPayload,BuiltinAssignment,BuiltinHostBinding,BuiltinDispatch,BuiltinHandoff,BuiltinSubmission,BuiltinSnapshot)}
_COMMON = (DeliveryRegistration,DeliveryPolicy,DeliveryPlan,DependencyPin,ObservedRun,DecisionReceipt)
_CONTRACT = (c.RequestedAction,c.AuthorizationScope,c.ContextBundle,c.Criterion,c.Limits,c.Artifact,c.CandidateSnapshot)
_require = d._require
_unique = d._unique

def _decode(expected,value,path):
    origin,args=get_origin(expected),get_args(expected)
    if origin is Annotated:
        result=_decode(args[0],value,path); d._scalar(args[1],result,path);return result
    if origin in (Union,UnionType):
        if value is None and type(None) in args:return None
        for option in args:
            if option is not type(None):
                try:return _decode(option,value,path)
                except c.ValidationError:pass
        d._fail('invalid_type',path,'No permitted union matches')
    if origin is Literal:
        _require(any(type(value) is type(option) and value==option for option in args),
            'unsupported_version' if path.endswith('schema_version') else 'invalid_type',path,'Unsupported literal')
        return value
    if origin is list:
        _require(type(value) is list,'invalid_type',path,'Expected JSON list')
        return [_decode(args[0],v,f'{path}[{i}]') for i,v in enumerate(value)]
    if origin is dict:
        _require(type(value) is dict,'invalid_type',path,'Expected JSON map')
        return {_decode(args[0],k,path):_decode(args[1],v,f'{path}[{k!r}]') for k,v in value.items()}
    if expected in _COMMON:return d.delivery_from_dict(expected.__name__,value)
    if expected in _CONTRACT:return c.from_dict(expected.__name__,value)
    if expected in _TYPES.values():
        _require(type(value) is dict,'invalid_type',path,'Expected builtin record object')
        _require(set(value)=={f.name for f in fields(expected)},'unknown_field',path,'Missing or unknown builtin fields')
        record=expected(**{n:_decode(t,value[n],path+'.'+n) for n,t in get_type_hints(expected,include_extras=True).items()})
        _local(record,path);return record
    _require(type(value) is expected,'invalid_type',path,'Unexpected primitive type')
    return value

def _raw(value,ancestors):
    if type(value) in _COMMON:return d.delivery_to_dict(value)
    if type(value) in _CONTRACT:return c.to_dict(value)
    if is_dataclass(value):_require(type(value) in _TYPES.values(),'invalid_type','$','Unknown builtin record')
    if is_dataclass(value) or type(value) in (list,dict):
        _require(id(value) not in ancestors,'invalid_type','$','Cyclic builtin value');ancestors=ancestors|{id(value)}
        if is_dataclass(value):return {f.name:_raw(getattr(value,f.name),ancestors) for f in fields(value)}
        if type(value) is list:return [_raw(v,ancestors) for v in value]
        return {k:_raw(v,ancestors) for k,v in value.items()}
    return value

def builtin_from_dict(kind,wire):
    _require(type(kind) is str and kind in _TYPES,'invalid_type','$','Unknown builtin kind')
    c.canonical_json(wire)
    return _decode(_TYPES[kind],wire,'$')

def builtin_to_dict(record):
    _require(type(record) in _TYPES.values(),'invalid_type','$','Expected exact builtin record')
    raw=_raw(record,set());builtin_from_dict(type(record).__name__,raw);return raw

def builtin_digest(record):
    return hashlib.sha256(c.canonical_json(builtin_to_dict(record))).hexdigest()

def _local(record,path):
    if type(record) is BuiltinSnapshot:
        for field,key in [('assignments','assignment_id'),('dispatches','dispatch_token'),('submissions','submission_id')]:
            _unique([getattr(v,key) for v in getattr(record,field)],path+'.'+field)
    elif type(record) is BuiltinAuthority:
        _unique(record.required_tools,path);_unique(record.available_tools,path)
    elif type(record) is BuiltinPayload:
        _unique(record.owned_paths,path);_unique([v.id for v in record.criteria],path)
        _require(bool(record.criteria),'invalid_assignment',path,'Criteria required')
        _unique([v.path for v in record.instructions],path+'.instructions')
        _require(record.purpose=='repair' or record.repair_authorization is None,'invalid_type',path,'Only repair carries repair authorization')
    elif type(record) is BuiltinAssignment:
        for field in ('owned_paths','review_refs','invalidated_by'):_unique(getattr(record,field),path+'.'+field)
        _unique([p.assignment_id for p in record.dependencies],path+'.dependencies')
    elif type(record) is BuiltinHandoff:
        _unique(record.evidence_refs,path+'.evidence_refs');_unique([a.id for a in record.artifacts],path+'.artifacts')
        _unique([a.relative_path for a in record.artifacts],path+'.artifacts')
        for refs in record.criteria_coverage.values():_unique(refs,path+'.criteria_coverage')
    elif type(record) is BuiltinSubmission:
        _require(record.handoff_sha256==builtin_digest(record.payload),'invalid_digest',path,'Handoff digest differs')
    elif type(record) is BuiltinRepairAuthorization:
        _require(bool(record.baseline_candidate.artifacts) and bool(record.before_receipts),'missing_reproduction',path,'Baseline artifacts and failure receipts required')
        originals={a.relative_path:a.sha256 for a in record.baseline_candidate.artifacts}
        _require(set(record.baseline_archive)==set(originals),'missing_reproduction',path,'Archive must cover exact baseline paths')
        _require(all(v.sha256==originals[k] and v.path not in originals for k,v in record.baseline_archive.items()),'stale_baseline',path,'Archive must preserve distinct baseline bytes')
        _unique([v.path for v in record.baseline_archive.values()],path+'.baseline_archive')
        _unique([v.path for v in record.before_receipts],path+'.before_receipts')

def execution_marker(request,*,allow_unmarked=False):
    _require(type(request) is c.RequestEnvelope,'invalid_type','$','Expected v1 request')
    request=c.from_dict('RequestEnvelope',c.to_dict(request));refs=[v for v in request.source_refs if v.startswith(MODE_PREFIX)]
    _require(len(refs)==1 or (allow_unmarked and not refs),'mode_mismatch','$.source_refs','Exactly one execution marker required')
    if not refs:return None
    _require(re.fullmatch(re.escape(MODE_PREFIX)+r'builtin:2\.0:[a-f0-9]{64}',refs[0]) is not None,'mode_mismatch','$.source_refs','Unknown/malformed reserved marker')
    return refs[0]

def base_request_digest(request,*,allow_unmarked=False):
    marker=execution_marker(request,allow_unmarked=allow_unmarked);wire=c.to_dict(request)
    if marker is not None:wire['source_refs']=[v for v in wire['source_refs'] if v!=marker]
    return hashlib.sha256(c.canonical_json(wire)).hexdigest()

def mode_source_ref(decision):return MODE_PREFIX+'builtin:2.0:'+builtin_digest(decision)

def _normalized(record,expected):
    _require(type(record) is expected,'invalid_type','$','Wrong builtin record type')
    return builtin_from_dict(expected.__name__,builtin_to_dict(record))

def _record_set(records):
    values=[c.canonical_json(c.to_dict(record)) for record in records]
    _require(len(values)==len(set(values)),'preflight_denied','$.authority','Duplicate authority declaration')
    return set(values)

def _authority(payload,task=None):
    a=payload.authority
    _require(a.task_id==payload.task_id and a.project_id==payload.context.project_id,'request_mismatch','$.authority','Authority task/project differs')
    if task is not None:
        _require(a.request_sha256==d.request_digest(task.request) and a.project_id==task.request.project_id,'request_mismatch','$.authority','Authority request/project differs')
        _require(_record_set(a.requested_actions)<=_record_set(task.requested_actions)
            and _record_set(a.authorization)<=_record_set(task.authorization),
            'preflight_denied','$.authority','Worker actions/consent must be exact declared task subsets')
    result=preflight(set(a.required_tools),set(a.available_tools),a.requested_actions,a.authorization)
    _require(result.ready,'preflight_denied','$.authority','Observed tool/action/host preflight denied')
    _require(all(action.kind in (c.ActionKind.READ_LOCAL,c.ActionKind.WRITE_LOCAL) for action in a.requested_actions),'preflight_denied','$.authority','Initial builtin mode supports local actions only')

def _historical(e):
    return e.state in ('failed','cancelled','superseded') or (e.state=='changes_requested' and bool(e.invalidated_by))

def _payload_plan(e,plan,task=None,*,policy=None,historical=False):
    p=e.payload;_authority(p,task)
    if policy is not None and policy.workflow_kind=='bug' and p.responsibility=='implementer':
        _require(p.purpose in ('repair','reproduce'),'missing_reproduction','$.purpose','Bug implementation must reproduce or use an authorized repair checkpoint')
    _require(p.authority.artifact_root==e.worktree_root,'unsafe_path','$.authority','Authority/workspace roots differ')
    _require(p.context.project_id==e.workspace_id,'request_mismatch','$.context','Workspace/context project differs')
    if not historical:
        _require(hashlib.sha256(c.canonical_json(c.to_dict(p.context))).hexdigest()==plan.context_sha256,'stale_context','$.payload.context','Context differs from frozen plan')
        _require(_acceptance(p.criteria,plan.design_sha256).acceptance_id==plan.acceptance_sha256,'stale_acceptance','$.payload.criteria','Criteria differ from frozen plan')
        _require({v.id for v in p.criteria}==set(plan.requirement_ids),'stale_acceptance','$.payload.criteria','Plan requirements differ')
    _require(p.limits.max_parallel_children<=plan.max_executing and p.limits.max_correction_cycles<=plan.max_correction_cycles,'policy_mismatch','$.payload.limits','Payload limits exceed shared plan/policy')
    if task is not None:
        _require(p.limits.max_parallel_children<=task.limits.max_parallel_children and p.limits.max_correction_cycles<=task.limits.max_correction_cycles,'policy_mismatch','$.payload.limits','Payload limits exceed task')
    if p.purpose=='repair':
        auth=p.repair_authorization
        _require(auth is not None,'missing_reproduction','$.repair_authorization','Repair requires preserved root checkpoint')
        _require(auth.assessed_by_actor_ref==plan.root_owner_ref,
            'unauthorized_checkpoint','$.repair_authorization.assessed_by_actor_ref',
            'Checkpoint assessor differs from immutable declared root owner')
        _require((auth.task_id,auth.request_sha256,auth.design_sha256,auth.acceptance_sha256,auth.context_sha256)==(e.task_id,p.authority.request_sha256,
                auth.design_sha256 if historical else plan.design_sha256,
                _acceptance(p.criteria,auth.design_sha256).acceptance_id if historical else plan.acceptance_sha256,
                hashlib.sha256(c.canonical_json(c.to_dict(p.context))).hexdigest() if historical else plan.context_sha256),'stale_baseline','$.repair_authorization','Checkpoint scope differs')
    if p.purpose=='review':_require(p.responsibility=='reviewer','invalid_assignment','$.purpose','Review requires reviewer responsibility')

def _time(value):
    return datetime.fromisoformat(value[:-1]+'+00:00')

def _binding(e,intent):
    h=intent.host_binding
    _require((h is not None)==(intent.state in ('observed','terminated')),'wrong_run','$.host_binding','Observed/terminated dispatch requires actual host binding')
    if h is None:return
    _require((h.task_id,h.assignment_id,h.dispatch_token,h.dispatched_envelope_sha256,h.prompt_sha256,h.instruction_sha256,h.authority_sha256,h.run)==(e.task_id,e.assignment_id,intent.dispatch_token,intent.envelope_sha256,e.payload.prompt.sha256,[r.sha256 for r in e.payload.instructions],builtin_digest(e.payload.authority),intent.observed_run),'wrong_run','$.host_binding','Host task/token/run/prompt/instructions/authority differs')
    _require(_time(e.payload.authority.observed_at)<=_time(intent.created_at)<=_time(h.run.observed_at),'wrong_run','$.host_binding','Authority/dispatch/run chronology differs')
    if e.payload.repair_authorization is not None:
        _require(_time(e.payload.repair_authorization.assessed_at)<=_time(intent.created_at),'missing_reproduction','$.repair_authorization','Assessment must precede repair dispatch')

def validate_builtin(snapshot,task,previous=None):
    try:
        s=_normalized(snapshot,BuiltinSnapshot)
        _require(type(task) is c.TaskRecord,'invalid_type','$','Expected current TaskRecord')
        task=c.from_dict('TaskRecord',c.to_dict(task))
        _require(task.status not in (c.TaskStatus.COMPLETED,c.TaskStatus.CANCELLED),'invalid_transition','$.status','Terminal task cannot mutate delivery')
        _require(task.request.requested_role is None,'configured_fallback','$.request','Configured request cannot fall back')
        _require(execution_marker(task.request)==mode_source_ref(s.decision),'mode_mismatch','$.decision','Decision does not bind immutable marker')
        _require(s.decision.task_id==task.id and s.decision.base_request_sha256==base_request_digest(task.request),'request_mismatch','$.decision','Decision base request differs')
        check_snapshot(builtin_to_dict(s),task,mode='builtin')
        _require(task.limits.max_parallel_children<=s.plan.max_executing and task.limits.max_correction_cycles<=s.plan.max_correction_cycles,'policy_mismatch','$.limits','Task limits exceed shared plan/policy')
        _require(len(task.cycles)<=s.plan.max_correction_cycles,'policy_mismatch','$.cycles','Correction history exceeds shared policy')
        for e in s.assignments:_payload_plan(e,s.plan,task,policy=s.policy,historical=_historical(e))
        correction_limit=min([s.plan.max_correction_cycles,task.limits.max_correction_cycles]
            +[e.payload.limits.max_correction_cycles for e in s.assignments])
        _require(len(task.cycles)<=correction_limit,
            'policy_mismatch','$.cycles','Shared correction cycle budget exceeded')
        effective=min([s.plan.max_executing,task.limits.max_parallel_children]+[e.payload.limits.max_parallel_children for e in s.assignments if e.state not in ('failed','cancelled','superseded')])
        _require(len([i for i in s.dispatches if i.state not in ('terminated','absent')])<=effective,'policy_mismatch','$.dispatches','Shared execution pool exceeds narrowest applicable limit')
        assignments={e.assignment_id:e for e in s.assignments}
        for intent in s.dispatches:_binding(assignments[intent.assignment_id],intent)
        if previous is not None:
            previous=_normalized(previous,BuiltinSnapshot)
            _require(s.decision==previous.decision,'history_mismatch','$.decision','Mode decision immutable')
            check_history(builtin_to_dict(s),builtin_to_dict(previous),mode='builtin')
            old={i.dispatch_token:i for i in previous.dispatches}
            for i in s.dispatches:
                if i.dispatch_token in old and old[i.dispatch_token].host_binding is not None:
                    _require(i.host_binding==old[i.dispatch_token].host_binding,'history_mismatch','$.host_binding','Observed binding immutable')
        return c.GateResult(True,[])
    except c.ValidationError as error:return c.GateResult(False,error.errors)

def _receipt(fd,r):
    actual=_file_hash(fd,r.path,'invalid_evidence_path','missing_evidence','$.receipt')
    _require(actual==r.sha256,'stale_receipt','$.receipt','Receipt bytes differ')

def _read(fd,r):
    parts=r.path.split('/');directory=os.dup(fd);file_fd=None
    try:
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=child
        file_fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        _require(stat.S_ISREG(os.fstat(file_fd).st_mode),'invalid_evidence_path','$.receipt','Receipt must be regular file')
        chunks=[];size=0
        while chunk:=os.read(file_fd,65536):
            size+=len(chunk);_require(size<=16*1024*1024,'invalid_evidence_path','$.receipt','Receipt too large');chunks.append(chunk)
        data=b''.join(chunks)
        _require(hashlib.sha256(data).hexdigest()==r.sha256,'stale_receipt','$.receipt','Receipt bytes differ')
        return data
    except OSError:d._fail('invalid_evidence_path','$.receipt','Missing or unsafe receipt')
    finally:
        if file_fd is not None:os.close(file_fd)
        os.close(directory)

def _json_receipt(fd,r):
    def pairs(items):
        result={}
        for key,value in items:
            _require(key not in result,'invalid_type','$.receipt','Duplicate JSON key');result[key]=value
        return result
    try:
        value=json.loads(_read(fd,r),object_pairs_hook=pairs);c.canonical_json(value)
        _require(type(value) is dict,'invalid_type','$.receipt','Expected receipt JSON object');return value
    except (ValueError,UnicodeError):d._fail('invalid_type','$.receipt','Invalid JSON receipt')

def _files(e,fd,*,plan=None,live_baseline=False):
    p=e.payload;prompt=_read(fd,p.prompt)
    for receipt in p.instructions:_receipt(fd,receipt)
    _receipt(fd,p.authority.observation)
    design=_file_hash(fd,p.design_ref,'invalid_evidence_path','missing_evidence','$.design_ref')
    if plan is not None:_require(design==plan.design_sha256,'stale_acceptance','$.design_ref','Design bytes differ')
    if p.purpose=='repair':
        auth=p.repair_authorization
        _require(auth is not None,'missing_reproduction','$.repair_authorization','Repair requires checkpoint')
        _require(auth.task_id==e.task_id and auth.request_sha256==p.authority.request_sha256 and auth.design_sha256==design and auth.acceptance_sha256==_acceptance(p.criteria,design).acceptance_id and auth.context_sha256==hashlib.sha256(c.canonical_json(c.to_dict(p.context))).hexdigest(),'stale_baseline','$.repair_authorization','Checkpoint request/design/criteria/context differs')
        for receipt in list(auth.baseline_archive.values())+auth.before_receipts+[auth.assessment_ref]:_receipt(fd,receipt)
        if live_baseline:
            _require(_candidate(fd,auth.baseline_candidate.artifacts)==auth.baseline_candidate,'stale_baseline','$.baseline_candidate','Live baseline changed before repair dispatch')
    return prompt

def _snapshot_local(s):
    p,policy,r=s.plan,s.policy,s.registration
    _require(p.max_executing<=policy.max_executing and p.max_correction_cycles<=policy.max_correction_cycles,
        'policy_mismatch','$.plan','Plan exceeds immutable shared policy')
    _require(s.task_id==s.decision.task_id==r.task_id==p.task_id and r.request_sha256==p.request_sha256,
        'request_mismatch','$','Snapshot internal task/request binding differs')
    _require(r.policy_id==policy.policy_id and r.policy_sha256==p.policy_sha256==d.delivery_digest(policy),
        'policy_mismatch','$.registration','Snapshot internal policy binding differs')

def validate_builtin_dispatch(snapshot,assignment_id,artifact_root):
    try:
        s=_normalized(snapshot,BuiltinSnapshot);_snapshot_local(s)
        check_ownership(builtin_to_dict(s),mode='builtin');found=[e for e in s.assignments if e.assignment_id==assignment_id]
        _require(len(found)==1,'invalid_assignment','$.assignment_id','Unknown assignment')
        e=found[0];_payload_plan(e,s.plan,policy=s.policy)
        _require(e.state in ('proposed','dispatched'),'invalid_transition','$.assignment','Only new dispatch can compare live baseline')
        _require(isinstance(artifact_root,Path) and str(artifact_root)==e.worktree_root and artifact_root.resolve(strict=True)==artifact_root,'unsafe_path','$.artifact_root','Expected assigned canonical root')
        occupied=[i for i in s.dispatches if i.state not in ('terminated','absent') and i.dispatch_token!=e.dispatch_token]
        _require(len(occupied)<min([s.plan.max_executing]+[v.payload.limits.max_parallel_children for v in s.assignments if v.state not in ('failed','cancelled','superseded')]),'policy_mismatch','$.dispatches','Shared execution capacity exhausted')
        pins={v.assignment_id:v for v in s.assignments}
        _require(all(pin.assignment_id in pins and pins[pin.assignment_id].state=='accepted' and (pin.accepted_revision,pin.output_sha256)==(pins[pin.assignment_id].revision,pins[pin.assignment_id].output_sha256) for pin in e.dependencies),'stale_dependency','$.dependencies','Dependency not accepted/current')
        with _root(artifact_root,'unsafe_path','$.artifact_root') as fd:_files(e,fd,plan=s.plan,live_baseline=True)
        return c.GateResult(True,[])
    except c.ValidationError as error:return c.GateResult(False,error.errors)
    except (OSError,ValueError,RuntimeError):return c.GateResult(False,[c.ErrorDetail('unsafe_path','$.artifact_root','Artifact root unavailable')])

def _handoff(e,h,fd):
    p=e.payload
    _require((h.task_id,h.assignment_revision,h.responsibility)==(p.task_id,p.assignment_revision,p.responsibility),'stale_assignment','$.payload','Handoff task/revision/responsibility differs')
    ids=[v.id for v in p.criteria]
    _require(bool(ids) and bool(p.owned_paths),'invalid_assignment','$.assignment','Criteria and ownership required')
    _require(h.result=='ready_for_review','blocked_child' if h.result=='blocked' else 'failed_child','$.result','Child not ready')
    _require(h.blocker is None,'inconsistent_handoff','$.blocker','Ready handoff cannot have blocker')
    _require(bool(h.artifacts),'missing_artifact','$.artifacts','Ready handoff requires actual owned artifacts')
    _require(set(h.criteria_coverage)==set(ids) and all(h.criteria_coverage.values()),'incomplete_coverage','$.criteria_coverage','Ready handoff must cover assigned criteria')
    _require(bool(h.next_step.strip()),'missing_next_step','$.next_step','Actionable next step required')
    for artifact in h.artifacts:
        _require(artifact.relative_path in p.owned_paths,'outside_ownership','$.artifacts','Artifact outside exact ownership')
        actual=_file_hash(fd,artifact.relative_path,'invalid_artifact_path','missing_artifact','$.artifacts')
        _require(actual==artifact.sha256,'artifact_digest_mismatch','$.artifacts','Artifact bytes differ')
    for ref in set(h.evidence_refs+[v for refs in h.criteria_coverage.values() for v in refs]):_file_hash(fd,ref,'invalid_evidence_path','missing_evidence','$.evidence_refs')

def _host_files(e,i,fd,prompt):
    call=_json_receipt(fd,i.host_binding.submitted_call)
    response=_json_receipt(fd,i.host_binding.observed_response)
    _require(set(call)=={'tool','arguments'} and type(call['tool']) is str
        and call['tool'] in ('spawn_agent','collaboration.spawn_agent')
        and type(call['arguments']) is dict,
        'invalid_host_call','$.submitted_call','Unsupported actual host call object')
    arguments=call['arguments']
    required={'message','task_name'} if call['tool']=='collaboration.spawn_agent' else {'message'}
    allowed={'message','task_name','fork_turns','agent_type'}
    _require(required<=set(arguments)<=allowed
        and type(arguments['message']) is str
        and ('task_name' not in arguments or (type(arguments['task_name']) is str and bool(arguments['task_name'].strip())))
        and ('fork_turns' not in arguments or (type(arguments['fork_turns']) is str and arguments['fork_turns'] in ('all','none')))
        and ('agent_type' not in arguments or (type(arguments['agent_type']) is str and arguments['agent_type']=='default')),
        'invalid_host_call','$.submitted_call.arguments','Unsupported actual host argument keys or types')
    _require(arguments['message'].encode('utf-8')==prompt,
        'prompt_mismatch','$.submitted_call','Actual submitted message bytes differ')
    response_key='task_name' if call['tool']=='collaboration.spawn_agent' else 'agent_id'
    _require(set(response)=={response_key} and type(response[response_key]) is str
        and response[response_key]==i.observed_run.run_ref,
        'wrong_run','$.observed_response','Returned context differs from observed run')


def validate_builtin_submission(envelope,submission,intent,artifact_root,*,dispatched_envelope=None):
    try:
        e=_normalized(envelope,BuiltinAssignment);s=_normalized(submission,BuiltinSubmission);i=_normalized(intent,BuiltinDispatch)
        check_submission_binding(builtin_to_dict(e),builtin_to_dict(s),builtin_to_dict(i),mode='builtin')
        _require(i.envelope_revision<=e.revision,'stale_assignment','$.intent','Future dispatch envelope')
        if dispatched_envelope is None:
            _require(i.envelope_revision==e.revision,'missing_dispatch_context','$.intent','Historical dispatched envelope required');original=e
        else:original=_normalized(dispatched_envelope,BuiltinAssignment)
        _require((original.assignment_id,original.task_id,original.revision,builtin_digest(original),original.dispatch_token,original.state,original.observed_run)==(e.assignment_id,e.task_id,i.envelope_revision,i.envelope_sha256,i.dispatch_token,'dispatched',None) and scope_key(builtin_to_dict(original),mode='builtin')==scope_key(builtin_to_dict(e),mode='builtin'),'stale_assignment','$.intent','Historical dispatch scope/digest differs')
        _authority(e.payload);_binding(e,i)
        _require(_time(s.submitted_at)>=_time(i.observed_run.observed_at),'wrong_run','$.submitted_at','Submission predates observation')
        _require(isinstance(artifact_root,Path) and str(artifact_root)==e.worktree_root and artifact_root.resolve(strict=True)==artifact_root,'unsafe_path','$.artifact_root','Expected assigned canonical root')
        with _root(artifact_root,'unsafe_path','$.artifact_root') as fd:
            prompt=_files(e,fd,live_baseline=False);_host_files(e,i,fd,prompt);_handoff(e,s.payload,fd)
        return c.GateResult(True,[])
    except c.ValidationError as error:return c.GateResult(False,error.errors)
    except (OSError,ValueError,RuntimeError):return c.GateResult(False,[c.ErrorDetail('unsafe_path','$.artifact_root','Artifact root unavailable')])


def validate_builtin_receipts(snapshot,artifact_root):
    """Completion-time receipt precheck, without live pre-repair comparison.

    The coordinator root is separately canonical; each assignment's original
    prompt/authority/archive and observed host receipts stay under its immutable
    worktree_root. P12 still checks final product, cases, proof and independence.
    The persistence owner supplies historical dispatched envelopes separately.
    """
    try:
        s=_normalized(snapshot,BuiltinSnapshot);_snapshot_local(s)
        check_ownership(builtin_to_dict(s),mode='builtin')
        _require(isinstance(artifact_root,Path) and artifact_root.is_absolute()
            and artifact_root.resolve(strict=True)==artifact_root,
            'unsafe_path','$.artifact_root','Expected canonical coordinator artifact root')
        with _root(artifact_root,'unsafe_path','$.artifact_root'):
            pass
        assignments={e.assignment_id:e for e in s.assignments}
        intents={i.dispatch_token:i for i in s.dispatches}
        for e in s.assignments:
            _payload_plan(e,s.plan,policy=s.policy,historical=_historical(e))
            root=Path(e.worktree_root)
            _require(root.resolve(strict=True)==root,'unsafe_path','$.worktree_root','Expected canonical assignment root')
            with _root(root,'unsafe_path','$.worktree_root') as fd:
                prompt=_files(e,fd,plan=None if _historical(e) else s.plan,live_baseline=False)
                if e.dispatch_token is not None:
                    _require(e.dispatch_token in intents,'wrong_run','$.dispatches','Missing original dispatch')
                    intent=intents[e.dispatch_token];_binding(e,intent)
                    if intent.host_binding is not None:_host_files(e,intent,fd,prompt)
        for intent in s.dispatches:
            _require(intent.assignment_id in assignments,'wrong_run','$.dispatches','Unknown dispatch owner')
        return c.GateResult(True,[])
    except c.ValidationError as error:return c.GateResult(False,error.errors)
    except (OSError,ValueError,RuntimeError):
        return c.GateResult(False,[c.ErrorDetail('unsafe_path','$.artifact_root','Artifact root unavailable')])
