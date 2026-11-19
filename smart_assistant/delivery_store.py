"""Shared-lock delivery CAS, immutable history and explicit crash recovery.

No completion, native dispatch or semantic approval is performed here. Filesystem
integrity assumes cooperating task writers use the common lock; digests are not
signatures. Callers must reconcile an uncertain write rather than blindly retry.
"""
from __future__ import annotations
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import threading
from typing import Iterator, Literal

from .contracts import RevisionConflict, TaskStatus, ValidationError, canonical_json
from .delivery_records import DeliverySnapshot, _require, _fail
from .delivery_codec import (record_from_dict, record_to_dict as delivery_to_dict,
    record_digest as delivery_digest, validate_snapshot as validate_delivery,
    validate_submission, mode_for_task)
from .builtin_records import (BuiltinSnapshot, validate_builtin_dispatch,
    validate_builtin_receipts)
from .state import (_root_fd, _open_directory, _open_regular, _assert_attached,
    _lock, _read_record, _id, _same_file)


_LOCK_CONTEXT=threading.local()

@contextmanager
def _claim_lock(root_fd,task_id):
    identity=os.fstat(root_fd)
    key=(os.getpid(),identity.st_dev,identity.st_ino,task_id)
    active=getattr(_LOCK_CONTEXT,'active',set())
    _require(key not in active,'nested_lock','$','Nested same-task delivery lock acquisition')
    _LOCK_CONTEXT.active=active | {key}
    try: yield
    finally: _LOCK_CONTEXT.active=active


@dataclass(frozen=True)
class RecoveryReport:
    operation_id: str
    outcome: str
    head_revision: int | None
    preserved_refs: list[str]
    blockers: list[str]


def _hash(wire):
    return hashlib.sha256(canonical_json(wire)).hexdigest()


def _regular(parent,name,flags,mode=0o600):
    fd=_open_regular(parent,name,flags,mode)
    if os.fstat(fd).st_nlink!=1:
        os.close(fd); _fail('unsafe_path','$','Hardlinked store file')
    return fd


def _pairs(pairs):
    result={}
    for key,value in pairs:
        _require(key not in result,'malformed_json','$','Duplicate JSON key')
        result[key]=value
    return result


def _read(parent,name):
    fd=_regular(parent,name,os.O_RDONLY)
    with os.fdopen(fd,'r',encoding='utf-8') as stream:
        try:
            value=json.load(stream,object_pairs_hook=_pairs,
                parse_constant=lambda value: _fail('malformed_json','$','Non-finite JSON'))
            canonical_json(value)
            _require(type(value) is dict,'malformed_json','$','Expected JSON object')
            return value
        except (ValueError,UnicodeError) as error:
            if isinstance(error,ValidationError): raise
            _fail('malformed_json','$','Malformed store JSON')


def _optional(parent,name):
    try: return _read(parent,name)
    except FileNotFoundError: return None


def _write_immutable(parent,name,wire):
    payload=canonical_json(wire)+b'\n'
    try: fd=_regular(parent,name,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    except FileExistsError:
        _require(_read(parent,name)==wire,'history_mismatch','$','Immutable file collision')
        return
    with os.fdopen(fd,'wb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.fsync(parent)


def _atomic(parent,name,wire):
    prior=_optional(parent,name)  # reject unsafe existing target before replacement
    temporary=f'.{name}.{secrets.token_hex(16)}.tmp'
    fd=_regular(parent,temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(canonical_json(wire)+b'\n'); stream.flush(); os.fsync(stream.fileno())
        _require(_optional(parent,name)==prior,'unsafe_path','$','Mutable target changed during write')
        os.replace(temporary,name,src_dir_fd=parent,dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try: os.unlink(temporary,dir_fd=parent)
        except FileNotFoundError: pass


def _shape(value,names):
    _require(type(value) is dict and set(value)==set(names),'malformed_json','$','Unexpected store fields')
    _require(value.get('schema_version')=='1.0','unsupported_version','$','Unsupported store schema')


def _head(value):
    _shape(value,('schema_version','revision','snapshot_sha256','operation_id','operation_sha256'))
    _require(type(value['revision']) is int and value['revision']>0,'invalid_revision','$','Invalid head revision')
    _id(value['operation_id'])
    for key in ('snapshot_sha256','operation_sha256'):
        digest=value[key]
        _require(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),
            'invalid_digest','$','Invalid head digest')
    return value


def _revision_name(revision,digest):
    return f'{revision}-{digest}.json'


def _snapshot_from_wire(wire,task):
    mode=mode_for_task(task)
    kind='BuiltinSnapshot' if mode=='builtin' else 'DeliverySnapshot'
    return record_from_dict(kind,wire,mode=mode)


class DeliveryStore:
    def __init__(self,root: Path):
        self.root=Path(root)

    @contextmanager
    def locked(self,task_id: str,*,create: bool=False) -> Iterator[LockedDelivery]:
        _id(task_id)
        with ExitStack() as stack:
            root=stack.enter_context(_root_fd(self.root))
            stack.enter_context(_claim_lock(root,task_id))
            tasks=_open_directory(root,'tasks')
            stack.callback(os.close,tasks)
            locks=_open_directory(root,'locks',True)
            stack.callback(os.close,locks)
            lock=stack.enter_context(_lock(locks,task_id))
            _require(os.fstat(lock).st_nlink==1,'unsafe_path','$','Hardlinked task lock')
            # Inspection must not introduce the sidecar used by policy routing.
            # Even create=True only authorizes deferred, validated registration.
            delivery=base=None; directories={}
            try:
                delivery=_open_directory(root,'delivery'); stack.callback(os.close,delivery)
                base=_open_directory(delivery,task_id); stack.callback(os.close,base)
            except FileNotFoundError:
                _require(create,'missing_registration','$','No delivery storage')
            if base is not None:
                try:
                    for name in ('revisions','operations','resolutions'):
                        fd=_open_directory(base,name); stack.callback(os.close,fd); directories[name]=fd
                except FileNotFoundError:
                    _fail('missing_registration','$','Incomplete delivery storage requires recovery')
            session=LockedDelivery(task_id,root,tasks,locks,lock,delivery,base,directories,
                creation_stack=stack if create else None)
            try: yield session
            finally: session._active=False

    @contextmanager
    def borrowed(self,task_id: str,*,root_fd: int,tasks_fd: int,locks_fd: int,
                 lock_fd: int) -> Iterator[LockedDelivery]:
        """Trusted caller owns this task lock; descriptors do not authenticate flock.

        Borrowed descriptors are neither closed nor unlocked. Only TaskStore's
        locked mutation path is a supported caller. Missing storage is not created.
        """
        _id(task_id)
        with ExitStack() as stack:
            named_root=stack.enter_context(_root_fd(self.root))
            _require(_same_file(os.fstat(named_root),os.fstat(root_fd)),
                'unsafe_path','$','Borrowed root differs')
            _assert_attached(root_fd,'tasks',tasks_fd)
            _assert_attached(root_fd,'locks',locks_fd)
            lock=os.stat(f'{task_id}.lock',dir_fd=locks_fd,follow_symlinks=False)
            info=os.fstat(lock_fd)
            _require(stat.S_ISREG(lock.st_mode) and lock.st_nlink==1
                and _same_file(lock,info),'unsafe_path','$','Borrowed lock differs')
            stack.enter_context(_claim_lock(root_fd,task_id))
            delivery=_open_directory(root_fd,'delivery'); stack.callback(os.close,delivery)
            base=_open_directory(delivery,task_id); stack.callback(os.close,base)
            directories={}
            for name in ('revisions','operations','resolutions'):
                fd=_open_directory(base,name); stack.callback(os.close,fd); directories[name]=fd
            session=LockedDelivery(task_id,root_fd,tasks_fd,locks_fd,lock_fd,delivery,base,directories)
            session._attached()
            try: yield session
            finally: session._active=False

    def read(self,task_id: str) -> DeliverySnapshot:
        with self.locked(task_id) as session: return session.read()

    def dispatch_envelope(self,task_id: str,dispatch_token: str):
        with self.locked(task_id) as session: return session.dispatch_envelope(dispatch_token)

    def register(self,initial: DeliverySnapshot,expected_task_revision: int) -> DeliverySnapshot:
        # Normalize before using record identity as any path component.
        wire=delivery_to_dict(initial)
        task_id=_id(wire.get('task_id'))
        with self.locked(task_id,create=True) as session:
            return session.register(_snapshot_from_wire(wire,session.read_task()),expected_task_revision)

    def update(self,proposed: DeliverySnapshot,expected_revision: int,
               expected_task_revision: int) -> DeliverySnapshot:
        wire=delivery_to_dict(proposed)
        task_id=_id(wire.get('task_id'))
        with self.locked(task_id) as session:
            return session.update(_snapshot_from_wire(wire,session.read_task()),expected_revision,expected_task_revision)

    def recover(self,task_id: str,operation_id: str,
                action: Literal['finish','reject']) -> RecoveryReport:
        _id(operation_id)
        _require(action in ('finish','reject'),'invalid_type','$','Unknown recovery action')
        with self.locked(task_id) as session: return session._recover(operation_id,action)


class LockedDelivery:
    """Scoped session; never acquire TaskStore.update's lock inside this context."""
    def __init__(self,task_id,root,tasks,locks,lock,delivery,base,directories,*,creation_stack=None):
        self.task_id=task_id
        self._root,self._tasks,self._locks,self._lock=root,tasks,locks,lock
        self._delivery,self._base=delivery,base
        self._dirs=directories
        self._creation_stack=creation_stack
        self._active=True

    def _attached(self):
        _require(self._active,'unsafe_path','$','Expired locked session')
        for name,fd in [('tasks',self._tasks),('locks',self._locks)]:
            _assert_attached(self._root,name,fd)
        if self._delivery is not None: _assert_attached(self._root,'delivery',self._delivery)
        if self._base is not None:
            _assert_attached(self._delivery,self.task_id,self._base)
            for name,fd in self._dirs.items(): _assert_attached(self._base,name,fd)
        else:
            parent,name=(self._root,'delivery') if self._delivery is None else (self._delivery,self.task_id)
            try: os.stat(name,dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError: pass
            else: _fail('unsafe_path','$','Delivery storage appeared during locked session')
        lock=os.stat(f'{self.task_id}.lock',dir_fd=self._locks,follow_symlinks=False)
        info=os.fstat(self._lock)
        _require(stat.S_ISREG(lock.st_mode) and lock.st_nlink==1 and
            (lock.st_dev,lock.st_ino)==(info.st_dev,info.st_ino),'unsafe_path','$','Lock replaced')

    def _create_storage(self):
        _require(self._creation_stack is not None,'missing_registration','$','Registration requires create=True')
        self._attached()
        # Exclusive mkdir refuses unexplained storage appearing after validation.
        if self._delivery is None:
            os.mkdir('delivery',mode=0o700,dir_fd=self._root)
            self._delivery=_open_directory(self._root,'delivery')
            self._creation_stack.callback(os.close,self._delivery)
        os.mkdir(self.task_id,mode=0o700,dir_fd=self._delivery)
        self._base=_open_directory(self._delivery,self.task_id)
        self._creation_stack.callback(os.close,self._base)
        for name in ('revisions','operations','resolutions'):
            os.mkdir(name,mode=0o700,dir_fd=self._base)
            fd=_open_directory(self._base,name); self._creation_stack.callback(os.close,fd)
            self._dirs[name]=fd
        self._attached()

    def read_task(self):
        self._attached()
        return _read_record(self._tasks,self.task_id)

    def _normalize(self,record):
        wire=delivery_to_dict(record)
        _require(wire.get('task_id')==self.task_id,'request_mismatch','$','Wrong locked task')
        return _snapshot_from_wire(wire,self.read_task())

    def _unresolved(self):
        operations=self._dirs['operations']; resolutions=self._dirs['resolutions']
        result=[]
        for name in os.listdir(operations):
            _require(name.endswith('.json'),'history_mismatch','$','Unexpected operation filename')
            operation_id=_id(name[:-5])
            # Opening both prevents symlink/nonregular names from hiding in history.
            self._operation(operation_id)
            if self._resolution(operation_id) is None: result.append(operation_id)
        return result

    def _clean(self):
        pending=_optional(self._base,'pending.json')
        _require(pending is None and not self._unresolved(),'recovery_required','$','Unresolved delivery operation')

    def _operation(self,operation_id):
        wire=_read(self._dirs['operations'],f'{operation_id}.json')
        _shape(wire,('schema_version','operation_id','task_id','expected_task_revision',
            'prior_head','candidate_head','registration_sha256'))
        _require(wire['operation_id']==operation_id and wire['task_id']==self.task_id,
            'history_mismatch','$','Operation identity differs')
        _require(type(wire['expected_task_revision']) is int and wire['expected_task_revision']>0,
            'invalid_revision','$','Invalid operation task revision')
        candidate=wire['candidate_head']
        _shape(candidate,('schema_version','revision','snapshot_sha256'))
        _require(type(candidate['revision']) is int and candidate['revision']>0,
            'invalid_revision','$','Invalid candidate revision')
        for digest in (candidate['snapshot_sha256'],wire['registration_sha256']):
            _require(type(digest) is str and len(digest)==64 and all(c in 'abcdef0123456789' for c in digest),
                'invalid_digest','$','Invalid operation digest')
        if wire['prior_head'] is not None: _head(wire['prior_head'])
        return wire

    def _candidate_head(self,operation):
        return dict(operation['candidate_head'],operation_id=operation['operation_id'],operation_sha256=_hash(operation))

    def _snapshot(self,revision,digest):
        wire=_read(self._dirs['revisions'],_revision_name(revision,digest))
        result=_snapshot_from_wire(wire,self.read_task())
        _require(result.revision==revision and delivery_digest(result)==digest,'history_mismatch','$','Revision bytes differ')
        return result

    def _load(self,head=None,*,allow_unresolved_current=False):
        if head is None: head=_optional(self._base,'head.json')
        _require(head is not None,'missing_registration','$','No authoritative delivery head')
        registration=_read(self._base,'registration.json')
        task=self.read_task()
        # Only status is ignored for history inspection; immutable request is checked.
        checked_task=replace(task,status=TaskStatus.RUNNING)
        chain=[]; cursor=_head(head); first=True
        while True:
            operation=self._operation(cursor['operation_id'])
            _require(cursor==self._candidate_head(operation),'history_mismatch','$','Historical head/operation binding differs')
            _require(_hash(registration)==operation['registration_sha256'],'history_mismatch','$','Historical registration differs')
            resolution=self._resolution(cursor['operation_id'])
            if not (first and allow_unresolved_current and resolution is None):
                expected_refs=[f"operations/{cursor['operation_id']}.json",
                    'revisions/'+_revision_name(cursor['revision'],cursor['snapshot_sha256'])]
                _require(resolution is not None and resolution['action']=='finish'
                    and resolution['head_revision']==cursor['revision']
                    and resolution['preserved_refs']==expected_refs,
                    'history_mismatch','$','Committed operation lacks matching finish resolution')
            snapshot=self._snapshot(cursor['revision'],cursor['snapshot_sha256'])
            _require(delivery_to_dict(snapshot.registration)==registration,'history_mismatch','$','Registration changed in history')
            chain.append(snapshot)
            prior=operation['prior_head']
            if snapshot.revision==1:
                _require(snapshot.previous_sha256 is None and prior is None,
                    'history_mismatch','$','Initial operation/snapshot has prior state')
                break
            _require(prior is not None,'history_mismatch','$','Missing historical prior head')
            prior=_head(prior)
            _require(prior['revision']==snapshot.revision-1
                and prior['snapshot_sha256']==snapshot.previous_sha256,
                'history_mismatch','$','Operation chain differs from snapshot chain')
            cursor=prior; first=False
        previous=None
        for snapshot in reversed(chain):
            result=validate_delivery(snapshot,checked_task,previous)
            if not result.passed: raise ValidationError(result.errors)
            previous=snapshot
        return chain[0]

    def read(self):
        self._attached()
        _require(self._base is not None,'missing_registration','$','No delivery storage')
        self._clean()
        try: return self._load()
        except FileNotFoundError as error: _fail('missing_registration','$','Missing authoritative delivery component')

    def _check_task(self,expected):
        _require(type(expected) is int and expected>0,'invalid_revision','$','Expected positive task revision')
        task=self.read_task()
        if task.revision!=expected: raise RevisionConflict(f'Expected task revision {expected}, found {task.revision}')
        _require(task.status not in (TaskStatus.COMPLETED,TaskStatus.CANCELLED,TaskStatus.FAILED),
            'invalid_transition','$','Terminal/failed task cannot mutate delivery')
        return task

    def _registration_lineage(self,initial):
        """Allow empty storage or positively proven rejected identical initial attempts."""
        operations=set(os.listdir(self._dirs['operations']))
        resolutions=set(os.listdir(self._dirs['resolutions']))
        revisions=set(os.listdir(self._dirs['revisions']))
        base_entries=set(os.listdir(self._base))
        directories={'operations','resolutions','revisions'}
        _require(base_entries<=directories|{'registration.json'},'missing_registration','$',
            'Unexplained durable remnants require recovery before registration')
        registration=_optional(self._base,'registration.json')
        if not operations:
            _require(not resolutions and not revisions and registration is None,
                'missing_registration','$','Missing operation proof for populated registration history')
            return
        _require(operations==resolutions,'missing_registration','$',
            'Rejected initial lineage requires every operation and matching resolution')
        digest=delivery_digest(initial)
        revision_name=_revision_name(1,digest)
        _require(revisions<={revision_name},'missing_registration','$',
            'Unexplained revision history cannot become new initial authority')
        if registration is not None:
            _require(registration==delivery_to_dict(initial.registration),'history_mismatch','$',
                'Rejected initial registration binding differs')
        if revisions:
            _require(self._snapshot(1,digest)==initial,'history_mismatch','$',
                'Rejected initial snapshot bytes differ from explicit retry')
        for name in operations:
            _require(name.endswith('.json'),'missing_registration','$','Malformed rejected-operation filename')
            operation_id=_id(name[:-5])
            operation=self._operation(operation_id); resolution=self._resolution(operation_id)
            _require(operation['prior_head'] is None
                and operation['candidate_head']=={'schema_version':'1.0','revision':1,'snapshot_sha256':digest}
                and operation['registration_sha256']==_hash(delivery_to_dict(initial.registration))
                and resolution is not None and resolution['action']=='reject'
                and resolution['head_revision'] is None
                and resolution['preserved_refs']==[f'operations/{name}',f'revisions/{revision_name}'],
                'missing_registration','$','Retry lacks complete matching rejected-initial lineage')

    def register(self,initial,expected_task_revision):
        initial=self._normalize(initial)
        self._attached()
        _require(initial.task_id==self.task_id,'request_mismatch','$','Wrong locked task')
        if self._base is not None:
            self._clean()
            if _optional(self._base,'head.json') is not None: raise RevisionConflict('Delivery already registered')
            self._registration_lineage(initial)
        task=self._check_task(expected_task_revision)
        _require(task.status in (TaskStatus.QUEUED,TaskStatus.RUNNING),'invalid_transition','$','Registration requires queued/running task')
        _require(initial.revision==1 and initial.previous_sha256 is None and initial.plan.revision==1
            and not initial.dispatches and not initial.submissions and not initial.decisions
            and all(e.revision==1 and e.state=='proposed' for e in initial.assignments),
            'invalid_revision','$','Initial delivery must start at proposed revision 1')
        result=validate_delivery(initial,task)
        if not result.passed: raise ValidationError(result.errors)
        if self._base is None: self._create_storage()
        return self._commit(initial,None,expected_task_revision)

    def update(self,proposed,expected_revision,expected_task_revision):
        proposed=self._normalize(proposed)
        self._attached()
        _require(type(expected_revision) is int and expected_revision>0,'invalid_revision','$','Expected positive delivery revision')
        current=self.read()
        if current.revision!=expected_revision: raise RevisionConflict(f'Expected delivery revision {expected_revision}, found {current.revision}')
        _require(proposed.task_id==self.task_id and proposed.revision==expected_revision,'invalid_revision','$','Proposed identity/revision differs')
        task=self._check_task(expected_task_revision)
        candidate=replace(proposed,revision=expected_revision+1)
        result=validate_delivery(candidate,task,current)
        if not result.passed: raise ValidationError(result.errors)
        self._validate_files(candidate,current)
        return self._commit(candidate,_read(self._base,'head.json'),expected_task_revision)

    def _dispatch_envelope(self,intent):
        head=_head(_read(self._base,'head.json'))
        revision,digest=head['revision'],head['snapshot_sha256']
        while revision>0:
            snapshot=self._snapshot(revision,digest)
            for e in snapshot.assignments:
                if e.assignment_id==intent.assignment_id and e.revision==intent.envelope_revision:
                    _require(delivery_digest(e)==intent.envelope_sha256,'history_mismatch','$','Original dispatch bytes differ')
                    return e
            digest=snapshot.previous_sha256; revision-=1
        _fail('missing_dispatch_context','$','Original dispatch envelope absent from committed history')

    def dispatch_envelope(self,dispatch_token):
        _id(dispatch_token)
        snapshot=self.read()
        intent=next((i for i in snapshot.dispatches if i.dispatch_token==dispatch_token),None)
        _require(intent is not None,'wrong_run','$','Unknown dispatch token')
        return self._dispatch_envelope(intent)

    def _validate_files(self,candidate,previous):
        if type(candidate) is BuiltinSnapshot:
            prior={i.dispatch_token:i for i in previous.dispatches} if previous else {}
            envelopes={e.assignment_id:e for e in candidate.assignments}
            for intent in candidate.dispatches:
                before=prior.get(intent.dispatch_token)
                if before is None:
                    envelope=envelopes[intent.assignment_id]
                    result=validate_builtin_dispatch(candidate,envelope.assignment_id,Path(envelope.worktree_root))
                    if not result.passed: raise ValidationError(result.errors)
            if any(i.host_binding is not None and (i.dispatch_token not in prior
                    or prior[i.dispatch_token].host_binding is None) for i in candidate.dispatches):
                result=validate_builtin_receipts(candidate,Path(self.read_task().artifact_root))
                if not result.passed: raise ValidationError(result.errors)
        old_submissions={s.submission_id for s in previous.submissions} if previous else set()
        envelopes={e.assignment_id:e for e in candidate.assignments}
        intents={i.dispatch_token:i for i in candidate.dispatches}
        old_envelopes={e.assignment_id:e for e in previous.assignments} if previous else {}
        checks=[]
        for sub in candidate.submissions:
            if sub.submission_id not in old_submissions:
                checks.append((envelopes[sub.assignment_id],sub))
        for e in candidate.assignments:
            before=old_envelopes.get(e.assignment_id)
            if e.state=='accepted' and before is not None and before.state!='accepted':
                sub=next(s for s in candidate.submissions if s.submission_id==e.handoff_submission_id)
                # Acceptance binds the exact last submitted/reviewed ready envelope.
                checks.append((before,sub))
        for envelope,sub in checks:
            intent=intents[envelope.dispatch_token]
            result=validate_submission(envelope,sub,intent,Path(envelope.worktree_root),
                dispatched_envelope=self._dispatch_envelope(intent))
            if not result.passed: raise ValidationError(result.errors)

    def _commit(self,candidate,prior_head,task_revision):
        operation_id='op-'+secrets.token_hex(16)
        candidate_ref={'schema_version':'1.0','revision':candidate.revision,
            'snapshot_sha256':delivery_digest(candidate)}
        operation={'schema_version':'1.0','operation_id':operation_id,'task_id':self.task_id,
            'expected_task_revision':task_revision,'prior_head':prior_head,'candidate_head':candidate_ref,
            'registration_sha256':_hash(delivery_to_dict(candidate.registration))}
        self._attached()
        # Make directory entries durable before publishing anything in them.
        for fd in (self._root,self._delivery,self._base,*self._dirs.values()): os.fsync(fd)
        _write_immutable(self._dirs['operations'],f'{operation_id}.json',operation)
        _atomic(self._base,'pending.json',{'schema_version':'1.0','operation_id':operation_id})
        _write_immutable(self._base,'registration.json',delivery_to_dict(candidate.registration))
        _write_immutable(self._dirs['revisions'],_revision_name(candidate.revision,candidate_ref['snapshot_sha256']),delivery_to_dict(candidate))
        self._attached(); self._check_task(task_revision)
        _require(_optional(self._base,'head.json')==prior_head,'history_mismatch','$','Head changed while locked')
        _atomic(self._base,'head.json',self._candidate_head(operation))
        self._resolve(operation,'finish',candidate.revision)
        return self._normalize(candidate)

    def _resolution(self,operation_id):
        result=_optional(self._dirs['resolutions'],f'{operation_id}.json')
        if result is not None:
            _shape(result,('schema_version','operation_id','action','head_revision','preserved_refs'))
            _require(result['operation_id']==operation_id and result['action'] in ('finish','reject')
                and (result['head_revision'] is None or type(result['head_revision']) is int and result['head_revision']>0)
                and type(result['preserved_refs']) is list and all(type(v) is str for v in result['preserved_refs']),
                'history_mismatch','$','Malformed recovery resolution')
        return result

    def _clear_pending(self,operation_id):
        pending=_optional(self._base,'pending.json')
        if pending is not None:
            _shape(pending,('schema_version','operation_id'))
            _require(pending['operation_id']==operation_id,'recovery_required','$','Different operation is pending')
            self._attached()
            os.unlink('pending.json',dir_fd=self._base); os.fsync(self._base)

    def _resolve(self,operation,action,head_revision):
        operation_id=operation['operation_id']
        candidate=operation['candidate_head']
        resolution={'schema_version':'1.0','operation_id':operation_id,'action':action,
            'head_revision':head_revision,'preserved_refs':[f'operations/{operation_id}.json',
                'revisions/'+_revision_name(candidate['revision'],candidate['snapshot_sha256'])]}
        existing=self._resolution(operation_id)
        if existing is not None:
            _require(existing==resolution,'history_mismatch','$','Conflicting operation resolution')
        else: _write_immutable(self._dirs['resolutions'],f'{operation_id}.json',resolution)
        self._clear_pending(operation_id)
        return self._report(resolution)

    @staticmethod
    def _report(resolution):
        return RecoveryReport(resolution['operation_id'],
            'finished' if resolution['action']=='finish' else 'rejected',
            resolution['head_revision'],list(resolution['preserved_refs']),[])

    def _recover(self,operation_id,action):
        self._attached()
        try: operation=self._operation(operation_id)
        except FileNotFoundError: _fail('recovery_required','$','Unknown recovery operation')
        resolution=self._resolution(operation_id)
        if resolution is not None:
            _require(resolution['action']==action,'history_mismatch','$','Conflicting recovery action')
            head=_optional(self._base,'head.json')
            if action=='finish':
                _require(head is not None,'missing_registration','$','Finished operation lost authoritative head')
                try: self._load(head)
                except FileNotFoundError: _fail('recovery_required','$','Finished operation history is incomplete')
                cursor=head
                while cursor is not None and cursor['operation_id']!=operation_id:
                    cursor=self._operation(cursor['operation_id'])['prior_head']
                _require(cursor==self._candidate_head(operation),'history_mismatch','$','Finished operation is not in authoritative chain')
            elif head is not None:
                try: self._load(head)
                except FileNotFoundError: _fail('recovery_required','$','Rejected operation prior history is incomplete')
            else:
                _require(operation['prior_head'] is None,'missing_registration','$','Rejected operation lost prior committed head')
            self._clear_pending(operation_id)
            return self._report(resolution)
        unresolved=self._unresolved()
        _require(unresolved==[operation_id],'recovery_required','$','Ambiguous unresolved operations')
        head=_optional(self._base,'head.json')
        candidate_head=self._candidate_head(operation)
        if head==candidate_head:
            _require(action=='finish','history_mismatch','$','Committed operation cannot roll back')
            try: self._load(head,allow_unresolved_current=True)
            except FileNotFoundError: _fail('recovery_required','$','Committed history is incomplete')
            return self._resolve(operation,'finish',head['revision'])
        _require(head==operation['prior_head'],'recovery_required','$','Head differs from operation prior state')
        if action=='reject':
            # Reject never publishes candidate state; keep all staged evidence.
            return self._resolve(operation,'reject',head['revision'] if head else None)
        self._check_task(operation['expected_task_revision'])
        candidate_ref=operation['candidate_head']
        try:
            candidate=self._snapshot(candidate_ref['revision'],candidate_ref['snapshot_sha256'])
            registration=_read(self._base,'registration.json')
        except FileNotFoundError: _fail('recovery_required','$','Incomplete staged operation cannot finish')
        _require(_hash(registration)==operation['registration_sha256']
            and registration==delivery_to_dict(candidate.registration),'history_mismatch','$','Staged registration differs')
        previous=self._load(head) if head else None
        if previous is None:
            _require(candidate.revision==1 and candidate.previous_sha256 is None and not candidate.dispatches
                and not candidate.submissions and not candidate.decisions
                and all(e.state=='proposed' and e.revision==1 for e in candidate.assignments),
                'history_mismatch','$','Invalid initial recovery snapshot')
        result=validate_delivery(candidate,self.read_task(),previous)
        if not result.passed: raise ValidationError(result.errors)
        self._validate_files(candidate,previous)
        self._attached()
        _require(_optional(self._base,'head.json')==head,'history_mismatch','$','Recovery head changed')
        _atomic(self._base,'head.json',candidate_head)
        return self._resolve(operation,'finish',candidate.revision)
