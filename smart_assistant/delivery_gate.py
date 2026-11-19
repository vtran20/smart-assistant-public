"""Mandatory delivery completion and private immutable evidence under task lock.

Hashes establish consistency, not authenticity. P12 validates receipts and genuine
host observations remain a caller/workflow responsibility. No command is executed.
"""
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path

from .contracts import GateResult, ValidationError, ErrorDetail, RevisionConflict, TaskStatus, canonical_json
from .delivery_records import PREFIX, _require, _fail
from .delivery_codec import record_digest as delivery_digest, validate_snapshot as validate_delivery
from .builtin_records import MODE_PREFIX
from .delivery_evidence import EvidenceBundle, evidence_from_dict, evidence_to_dict, evidence_digest, validate_delivery_evidence
from .delivery_store import DeliveryStore, _read, _optional, _write_immutable, _atomic, _shape
from .state import _open_directory, _assert_attached, _id


def requires_delivery(root_fd,task):
    if any(ref.startswith((PREFIX,MODE_PREFIX)) for ref in task.request.source_refs):return True
    try: delivery=_open_directory(root_fd,'delivery')
    except FileNotFoundError:return False
    try:
        try: os.stat(task.id,dir_fd=delivery,follow_symlinks=False)
        except FileNotFoundError:return False
        return True
    finally:os.close(delivery)


def mandatory_completion(current,proposed,session):
    try:
        _require(proposed.artifact_root==current.artifact_root,'stale_context','$','Completion cannot change artifact root')
        delivery=session.read()
        structural=validate_delivery(delivery,current)
        if not structural.passed:raise ValidationError(structural.errors)
        _require(not proposed.blockers,'unresolved_blockers','$','Task blockers remain')
        _require(len(proposed.cycles)<=min(delivery.plan.max_correction_cycles,delivery.policy.max_correction_cycles),
            'correction_limit','$','Correction cycle bound exceeded')
        _require(all(not e.required or (e.state=='accepted' and not e.invalidated_by) for e in delivery.assignments),
            'required_assignment_unaccepted','$','Required child is not accepted')
        _require(all(i.state in ('terminated','absent') for i in delivery.dispatches),
            'unconfirmed_run','$','Live or ambiguous dispatch remains')
        revision=_read_evidence(session,delivery)
        return validate_delivery_evidence(proposed,delivery,revision.bundle,Path(proposed.artifact_root))
    except (ValidationError,FileNotFoundError) as error:
        return GateResult(False,error.errors if isinstance(error,ValidationError) else [
            ErrorDetail('missing_registration','$','Missing registered delivery/evidence')])


@dataclass(frozen=True)
class EvidenceRevision:
    schema_version: str
    task_id: str
    revision: int
    previous_sha256: str | None
    delivery_revision: int
    delivery_sha256: str
    plan_sha256: str
    bundle_sha256: str
    bundle: EvidenceBundle


def revision_to_dict(value):
    return dict(schema_version=value.schema_version,task_id=value.task_id,revision=value.revision,
        previous_sha256=value.previous_sha256,delivery_revision=value.delivery_revision,
        delivery_sha256=value.delivery_sha256,plan_sha256=value.plan_sha256,
        bundle_sha256=value.bundle_sha256,bundle=evidence_to_dict(value.bundle))


def _digest(wire):return hashlib.sha256(canonical_json(wire)).hexdigest()


def _sha(value):
    _require(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),
        'invalid_digest','$','Expected lowercase SHA256')
    return value


def _positive(value,zero=False):
    _require(type(value) is int and value>=(0 if zero else 1),'invalid_revision','$','Invalid revision')
    return value


def _revision(wire):
    _shape(wire,('schema_version','task_id','revision','previous_sha256','delivery_revision',
        'delivery_sha256','plan_sha256','bundle_sha256','bundle'))
    _id(wire['task_id']); _positive(wire['revision']); _positive(wire['delivery_revision'])
    if wire['revision']==1:_require(wire['previous_sha256'] is None,'history_mismatch','$','Initial revision has predecessor')
    else:_sha(wire['previous_sha256'])
    for name in ('delivery_sha256','plan_sha256','bundle_sha256'):_sha(wire[name])
    bundle=evidence_from_dict(wire['bundle'])
    _require(evidence_digest(bundle)==wire['bundle_sha256'] and bundle.task_id==wire['task_id']
        and bundle.delivery_revision==wire['delivery_revision'] and bundle.plan_sha256==wire['plan_sha256'],
        'history_mismatch','$','Evidence envelope binding differs')
    return EvidenceRevision(**dict(wire,bundle=bundle))


def _head(wire):
    _shape(wire,('schema_version','revision','revision_sha256'))
    _positive(wire['revision']); _sha(wire['revision_sha256']); return wire


@contextmanager
def _evidence_dirs(session,create=False):
    session._attached()
    try:evidence=_open_directory(session._base,'evidence',create)
    except FileNotFoundError:_fail('missing_delivery_evidence','$','Missing authoritative evidence')
    try:
        revisions=_open_directory(evidence,'revisions',create)
        try:
            resolutions=_open_directory(evidence,'resolutions',create)
            try:
                yield evidence,revisions,resolutions
                session._attached(); _assert_attached(session._base,'evidence',evidence)
                _assert_attached(evidence,'revisions',revisions); _assert_attached(evidence,'resolutions',resolutions)
            finally:os.close(resolutions)
        finally:os.close(revisions)
    finally:os.close(evidence)


def _filename(revision,digest):return f'{revision}-{digest}.json'


def _load(revisions,head,task_id):
    first=None; number=head['revision']; digest=head['revision_sha256']; chain=set()
    while number:
        wire=_read(revisions,_filename(number,digest)); revision=_revision(wire)
        _require(_digest(wire)==digest and revision.revision==number and revision.task_id==task_id,
            'history_mismatch','$','Evidence chain differs')
        chain.add(_filename(number,digest))
        if first is None:first=revision
        number-=1; digest=revision.previous_sha256
    return first,chain


def _resolution(wire,task_id,name,revisions):
    _shape(wire,('schema_version','task_id','revision','revision_sha256','action','prior_head',
        'task_revision','delivery_revision'))
    _positive(wire['revision']); _positive(wire['task_revision']); _positive(wire['delivery_revision'])
    _sha(wire['revision_sha256'])
    _require(wire['task_id']==task_id and wire['action'] in ('finish','reject')
        and _filename(wire['revision'],wire['revision_sha256'])==name,
        'history_mismatch','$','Recovery resolution binding differs')
    prior=wire['prior_head']
    if prior is not None:_head(prior)
    _require(wire['revision']==(prior['revision'] if prior else 0)+1,
        'history_mismatch','$','Recovery prior head differs')
    revision_wire=_read(revisions,name); candidate=_revision(revision_wire)
    _require(_digest(revision_wire)==wire['revision_sha256'] and candidate.task_id==task_id
        and candidate.revision==wire['revision']
        and candidate.previous_sha256==(prior['revision_sha256'] if prior else None),
        'history_mismatch','$','Recovery bytes or predecessor differs')
    return wire


def _inventory(revisions,resolutions,head,task_id,*,allow_unresolved=False):
    result,chain=_load(revisions,head,task_id) if head else (None,set())
    rejected=set()
    for name in os.listdir(resolutions):
        wire=_resolution(_read(resolutions,name),task_id,name,revisions)
        if wire['action']=='reject':
            _require(name not in chain,'history_mismatch','$','Rejected evidence became authority')
            rejected.add(name)
        else:_require(name in chain,'history_mismatch','$','Finished evidence lost authority')
    # Validate every preserved nonauthoritative file, including unsafe/corrupt files.
    extras=set(os.listdir(revisions))-chain-rejected
    for name in extras:
        wire=_read(revisions,name); candidate=_revision(wire)
        _require(candidate.task_id==task_id and _filename(candidate.revision,_digest(wire))==name,
            'history_mismatch','$','Unexpected evidence revision')
    if not allow_unresolved:_require(not extras,'recovery_required','$','Unpublished evidence needs recovery')
    return result,chain,extras


def _bound(revision,delivery):
    _require(revision.delivery_revision==delivery.revision and revision.delivery_sha256==delivery_digest(delivery)
        and revision.plan_sha256==delivery_digest(delivery.plan),'stale_delivery_evidence','$','Evidence delivery/plan changed')


def _read_evidence(session,delivery):
    with _evidence_dirs(session) as (base,revisions,resolutions):
        head=_optional(base,'head.json')
        _require(head is not None,'missing_delivery_evidence','$','Missing authoritative evidence head')
        result,_,_=_inventory(revisions,resolutions,_head(head),session.task_id); _bound(result,delivery)
        return result


class DeliveryEvidenceStore:
    def __init__(self,root: Path):self.root=Path(root)

    def read(self,task_id):
        with DeliveryStore(self.root).locked(task_id) as session:
            return _read_evidence(session,session.read())

    def save(self,task_id,bundle,*,expected_revision,expected_task_revision,expected_delivery_revision):
        bundle=evidence_from_dict(evidence_to_dict(bundle)); _positive(expected_revision,True)
        _positive(expected_task_revision); _positive(expected_delivery_revision)
        with DeliveryStore(self.root).locked(task_id) as session:
            task=session._check_task(expected_task_revision); delivery=session.read()
            if delivery.revision!=expected_delivery_revision:raise RevisionConflict('Delivery revision changed')
            result=validate_delivery_evidence(replace(task,status=TaskStatus.COMPLETED,revision=task.revision+1),
                delivery,bundle,Path(task.artifact_root))
            if not result.passed:raise ValidationError(result.errors)
            with _evidence_dirs(session,True) as (base,revisions,resolutions):
                prior=_optional(base,'head.json')
                if prior is None:
                    _inventory(revisions,resolutions,None,task_id)
                    actual=0; previous=None
                else:
                    prior=_head(prior); _inventory(revisions,resolutions,prior,task_id)
                    actual=prior['revision']; previous=prior['revision_sha256']
                if actual!=expected_revision:raise RevisionConflict('Evidence revision changed')
                candidate=EvidenceRevision('1.0',task_id,actual+1,previous,delivery.revision,
                    delivery_digest(delivery),delivery_digest(delivery.plan),evidence_digest(bundle),bundle)
                wire=revision_to_dict(candidate); digest=_digest(wire)
                name=_filename(candidate.revision,digest)
                _require(_optional(resolutions,name) is None,'recovery_conflict','$','Rejected revision cannot be reused')
                # Persist new directory entries before publishing files beneath them.
                for descriptor in (session._root,session._delivery,session._base,base,revisions,resolutions):
                    os.fsync(descriptor)
                _write_immutable(revisions,name,wire)
                self._commit_head(session,base,revisions,prior,delivery,expected_task_revision,candidate.revision,digest)
                return candidate

    @staticmethod
    def _commit_head(session,base,revisions,prior,delivery,task_revision,number,digest):
        session._attached(); _assert_attached(session._base,'evidence',base)
        _assert_attached(base,'revisions',revisions); session._check_task(task_revision)
        _require(session.read()==delivery,'stale_delivery_evidence','$','Delivery changed during evidence commit')
        _require(_optional(base,'head.json')==prior,'history_mismatch','$','Evidence head changed while locked')
        _atomic(base,'head.json',dict(schema_version='1.0',revision=number,revision_sha256=digest))

    def check(self,task_id):
        try:
            with DeliveryStore(self.root).locked(task_id) as session:
                task=session.read_task()
                _require(task.status is TaskStatus.VERIFYING,'invalid_transition','$','Task must be verifying')
                return mandatory_completion(task,replace(task,status=TaskStatus.COMPLETED,revision=task.revision+1),session)
        except (ValidationError,FileNotFoundError) as error:
            return GateResult(False,error.errors if isinstance(error,ValidationError) else [ErrorDetail('missing_registration','$','Missing delivery')])

    def recover(self,task_id,revision,revision_sha256,action,*,expected_revision,
                expected_task_revision,expected_delivery_revision):
        """Recover exactly named orphan; never choose a newest file or delete history."""
        _positive(revision); _sha(revision_sha256); _positive(expected_revision,True)
        _positive(expected_task_revision); _positive(expected_delivery_revision)
        _require(action in ('finish','reject'),'invalid_type','$','Unknown recovery action')
        with DeliveryStore(self.root).locked(task_id) as session:
            task=session._check_task(expected_task_revision); delivery=session.read()
            if delivery.revision!=expected_delivery_revision:raise RevisionConflict('Delivery revision changed')
            with _evidence_dirs(session) as (base,revisions,resolutions):
                head=_optional(base,'head.json'); current=_head(head) if head else None
                _,chain,extras=_inventory(revisions,resolutions,current,task_id,allow_unresolved=True)
                actual=current['revision'] if current else 0
                if actual!=expected_revision:raise RevisionConflict('Evidence revision changed')
                wire=_read(revisions,_filename(revision,revision_sha256)); candidate=_revision(wire)
                _require(_digest(wire)==revision_sha256 and candidate.task_id==task_id and candidate.revision==revision,
                    'history_mismatch','$','Named recovery revision differs')
                name=_filename(revision,revision_sha256)
                existing=_optional(resolutions,name)
                if existing is not None:
                    existing=_resolution(existing,task_id,name,revisions)
                    _require(existing['action']==action,'recovery_conflict','$','Recovery decision differs')
                    if action=='finish':
                        _bound(candidate,delivery)
                        result=validate_delivery_evidence(replace(task,status=TaskStatus.COMPLETED,revision=task.revision+1),
                            delivery,candidate.bundle,Path(task.artifact_root))
                        if not result.passed:raise ValidationError(result.errors)
                    return existing
                # A head write may have committed before the resolution write failed.
                committed=name in chain
                _require(not committed or (action=='finish' and current['revision']==revision
                    and current['revision_sha256']==revision_sha256),
                    'recovery_conflict','$','Cannot reject or alter committed evidence')
                prior=(dict(schema_version='1.0',revision=revision-1,revision_sha256=candidate.previous_sha256)
                    if revision>1 else None) if committed else current
                _require(committed or (revision==actual+1 and candidate.previous_sha256==
                    (current['revision_sha256'] if current else None)),
                    'history_mismatch','$','Recovery does not extend current authority')
                resolution=dict(schema_version='1.0',task_id=task_id,revision=revision,revision_sha256=revision_sha256,
                    action=action,prior_head=prior,task_revision=task.revision,delivery_revision=delivery.revision)
                if action=='finish':
                    _require(extras<={name},'recovery_required','$','Resolve other orphan revisions first')
                    _bound(candidate,delivery)
                    result=validate_delivery_evidence(replace(task,status=TaskStatus.COMPLETED,revision=task.revision+1),
                        delivery,candidate.bundle,Path(task.artifact_root))
                    if not result.passed:raise ValidationError(result.errors)
                    if not committed:
                        self._commit_head(session,base,revisions,current,delivery,task.revision,revision,revision_sha256)
                session._attached(); _assert_attached(base,'resolutions',resolutions)
                _write_immutable(resolutions,name,resolution)
                return resolution
