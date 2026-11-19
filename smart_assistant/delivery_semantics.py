"""Mode-neutral delivery integrity over strict normalized wire views.

Callers first use their closed record parser/serializer. These helpers accept its
wire dictionaries, never fabricated v1 envelopes or caller-supplied validators.
They raise ValidationError; record wrappers own GateResult and file/preflight
checks. This module deliberately imports no record, codec or persistence module.
"""
import hashlib
from .contracts import ValidationError, ErrorDetail, canonical_json, to_dict

POLICY_PREFIX = 'smart-assistant:delivery-policy:'

def _require(ok, code, path, message):
    if not ok:
        raise ValidationError([ErrorDetail(code,path,message)])

def _unique(values,path):
    _require(len(values)==len(set(values)),'invalid_type',path,'Duplicate values')

class _Node(dict):
    # Internal read-only field view, not a contract or managed envelope.
    def __getattr__(self,key):
        try: return self[key]
        except KeyError: raise AttributeError(key) from None

def _node(value):
    if type(value) is dict: return _Node({k:_node(v) for k,v in value.items()})
    if type(value) is list: return [_node(v) for v in value]
    return value

def _plain(value):
    if isinstance(value,dict): return {k:_plain(v) for k,v in value.items()}
    if type(value) is list: return [_plain(v) for v in value]
    return value

def wire_digest(wire):
    return hashlib.sha256(canonical_json(_plain(wire))).hexdigest()

def request_digest(request):
    return hashlib.sha256(canonical_json(to_dict(request))).hexdigest()

def policy_source_ref(policy):
    return f'{POLICY_PREFIX}1.0:{policy.policy_id}:{wire_digest(policy)}'

def _view(wire,mode,kind):
    _require(mode in ('managed','builtin'),'invalid_type','$','Unknown execution mode')
    _require(type(wire) is dict,'invalid_type','$','Expected normalized wire dictionary')
    _require(wire.get('schema_version')==('1.0' if mode=='managed' else '2.0'),
        'unsupported_version','$','Mode/version mismatch')
    if kind=='snapshot':
        _require((mode=='builtin')==(wire.get('execution_mode')=='builtin'),
            'mode_mismatch','$','Snapshot execution mode differs')
    return _node(wire)

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

def _scope(e, mode):
    common = (e.task_id,e.parent_assignment_id,e.required,_plain(e.payload),e.base_ref,
        e.workspace_id,e.worktree_root,e.owned_paths,e.dependencies)
    if mode == 'managed':
        return common + (e.selected_role_id,e.selected_role_version,e.selected_manifest_sha256)
    return common + (e.payload.responsibility,)

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

def _submission_binding(e,s,intent):
    _require((s.task_id,s.assignment_id,s.envelope_revision,s.envelope_sha256)==
        (e.task_id,e.assignment_id,e.revision,wire_digest(e)),
        'stale_assignment','$.submission','Submission does not bind current envelope')
    _require(intent.assignment_id==e.assignment_id and intent.state in ('observed','terminated')
        and e.observed_run is not None and s.observed_run==e.observed_run==intent.observed_run
        and s.observed_run.dispatch_token==intent.dispatch_token==e.dispatch_token,
        'wrong_run','$.submission.observed_run','No matching observed dispatch identity')

def _overlap(first,second):
    first,second=first.casefold(),second.casefold()
    return first==second or first.startswith(second+'/') or second.startswith(first+'/')

def _physical_paths(assignment):
    # Strict record parsers guarantee exact canonical POSIX root/path syntax.
    # Comparing root plus path catches nested canonical roots without filesystem
    # access or weakening logical repository ownership across isolated copies.
    return [assignment.worktree_root+'/'+path for path in assignment.owned_paths]

def _ownership(assignments):
    logical=[];physical=[];roots=set()
    for e in assignments:
        if e.state in _TERMINAL:continue
        for path in e.owned_paths:
            _require(not any(space==e.workspace_id and _overlap(path,other) for space,other in logical),
                'ownership_overlap','$.assignments','Logical exact ownership overlaps')
            logical.append((e.workspace_id,path))
        for path in _physical_paths(e):
            _require(not any(_overlap(path,other) for other in physical),
                'ownership_overlap','$.assignments','Canonical root plus owned path overlaps')
            physical.append(path)
        if e.owned_paths:
            _require(e.worktree_root.casefold() not in roots,
                'ownership_overlap','$.assignments','Live writers share worktree')
            roots.add(e.worktree_root.casefold())

def _snapshot_checks(s,task,mode):
    r,p,policy=s.registration,s.plan,s.policy
    _require(s.task_id==task.id==r.task_id==p.task_id,'request_mismatch','$','Task binding differs')
    _require(r.request_sha256==p.request_sha256==request_digest(task.request),
        'request_mismatch','$.registration','Immutable request changed')
    refs=[v for v in task.request.source_refs if v.startswith(POLICY_PREFIX)]
    _require(refs==[policy_source_ref(policy)] and r.policy_id==policy.policy_id
        and r.policy_sha256==p.policy_sha256==wire_digest(policy),
        'policy_mismatch','$.registration','Missing/invalid reserved policy binding')
    _require(p.max_executing<=policy.max_executing and p.max_correction_cycles<=policy.max_correction_cycles,
        'policy_mismatch','$.plan','Plan exceeds immutable policy limits')
    assignments={e.assignment_id:e for e in s.assignments}
    _require(len(assignments)==len(s.assignments) and set(assignments)==set(p.assignment_ids),
        'invalid_graph','$.assignments','Assignment IDs differ from plan or duplicate')
    _acyclic({key:[pin.assignment_id for pin in e.dependencies] for key,e in assignments.items()})
    _acyclic({key:[e.parent_assignment_id] if e.parent_assignment_id else [] for key,e in assignments.items()})
    _ownership(s.assignments)
    for e in s.assignments:
        _require(e.task_id==task.id==e.payload.task_id and e.owned_paths==e.payload.owned_paths,
            'request_mismatch','$.assignments','Payload binding differs')
        if mode == 'managed':
            _require(e.selected_role_id==e.payload.role_id and any(
                (x.id,x.version,x.deployed_sha256)==(e.selected_role_id,e.selected_role_version,e.selected_manifest_sha256)
                for x in e.payload.selection.agents),
                'policy_mismatch','$.assignments','Selected role/manifest differs')
        else:
            _require(e.payload.responsibility in ('implementer','reviewer','qa','technical-lead'),
                'invalid_type','$.assignments','Unknown builtin responsibility')
        if e.state in ('dispatched','working','ready_for_review','accepted'):
            _require(_pins_current(e,assignments),'stale_dependency','$.assignments','Predecessor pin not accepted/current')
            _require(e.dispatch_token is not None,'wrong_run','$.assignments','Dispatch token required')
        if e.state in ('working','ready_for_review','accepted'):
            _require(e.observed_run is not None,'wrong_run','$.assignments','Observed native run required')
        if e.state=='accepted':
            _require(e.output_sha256 is not None and e.handoff_submission_id is not None and bool(e.review_refs)
                and not e.invalidated_by,'invalid_transition','$.assignments','Accepted output lacks structural evidence')
    intents={i.dispatch_token:i for i in s.dispatches}
    _require(len(intents)==len(s.dispatches),'wrong_run','$.dispatches','Duplicate dispatch tokens')
    runs=set()
    for intent in s.dispatches:
        _require(intent.assignment_id in assignments,'wrong_run','$.dispatches','Unknown dispatch assignment')
        e=assignments[intent.assignment_id]
        _require(intent.envelope_revision<=e.revision and e.dispatch_token==intent.dispatch_token,
            'wrong_run','$.dispatches','Dispatch target differs')
        if intent.envelope_revision==e.revision:
            _require(intent.envelope_sha256==wire_digest(e),'stale_assignment','$.dispatches','Original dispatch digest differs')
        _require((intent.observed_run is not None)==(intent.state in ('observed','terminated')),
            'wrong_run','$.dispatches','Dispatch observation state differs')
        if intent.state in ('absent','terminated'):
            _require(intent.reconciliation_ref is not None,'wrong_run','$.dispatches','Termination/absence needs evidence')
        if intent.observed_run:
            identity=(intent.observed_run.host_ref,intent.observed_run.run_ref)
            _require(identity not in runs and intent.observed_run==e.observed_run
                and intent.observed_run.dispatch_token==intent.dispatch_token,'wrong_run','$.dispatches','Observed identity differs/reused')
            runs.add(identity)
    for e in s.assignments:
        if e.dispatch_token: _require(e.dispatch_token in intents,'wrong_run','$.assignments','Missing persisted dispatch intent')
    _require(len([i for i in s.dispatches if i.state not in ('terminated','absent')])<=p.max_executing,'policy_mismatch','$.dispatches','Execution bound exceeded')
    _unique([v.submission_id for v in s.submissions],'$.submissions')
    _unique([(v.assignment_id,v.envelope_revision,v.observed_run.run_ref,v.handoff_sha256) for v in s.submissions],'$.submissions')
    for sub in s.submissions:
        _require(sub.assignment_id in assignments and sub.task_id==s.task_id,'stale_assignment','$.submissions','Unknown submission owner')
        e=assignments[sub.assignment_id]
        _require(sub.envelope_revision<=e.revision,'stale_assignment','$.submissions','Submission revision from future')
        if sub.envelope_revision==e.revision:
            _require(e.dispatch_token in intents,'wrong_run','$.submissions','Missing dispatch')
            _submission_binding(e,sub,intents[e.dispatch_token])
    for e in s.assignments:
        if e.state=='accepted':
            bound=[sub for sub in s.submissions if sub.submission_id==e.handoff_submission_id and sub.assignment_id==e.assignment_id]
            _require(len(bound)==1,'invalid_transition','$.assignments','Missing accepted handoff')
            sub=bound[0]
            output=hashlib.sha256(canonical_json([_plain(a) for a in sorted(sub.payload.artifacts,key=lambda a:a.id)])).hexdigest()
            _require(e.output_sha256==output and sub.observed_run==e.observed_run
                and sub.payload.result=='ready_for_review',
                'invalid_digest','$.assignments','Accepted output does not bind ready handoff artifacts/run')
    _unique([r.receipt_id for r in s.decisions],'$.decisions')
    for receipt in s.decisions:
        _require(receipt.task_id==s.task_id and receipt.plan_revision<=p.revision
            and (receipt.assignment_id is None or receipt.assignment_id in assignments),
            'history_mismatch','$.decisions','Decision references unknown task/plan/assignment')
    return assignments

def _history(s,previous,mode):
    _require(s.revision==previous.revision+1 and s.previous_sha256==wire_digest(previous),
        'history_mismatch','$','Revision/previous digest differs')
    _require(s.registration==previous.registration and s.policy==previous.policy
        and s.plan.root_owner_ref==previous.plan.root_owner_ref,'policy_mismatch','$','Immutable registration/policy/root changed')
    for name in ('submissions','decisions'):
        before,after=getattr(previous,name),getattr(s,name)
        _require(after[:len(before)]==before,'history_mismatch',f'$.{name}','Immutable history changed')
    if s.plan!=previous.plan:
        _require(_Node(dict(s.plan, revision=previous.plan.revision))!=previous.plan,
            'invalid_revision','$.plan','Revision cannot change without plan content')
        _require(s.plan.revision==previous.plan.revision+1,'invalid_revision','$.plan','Plan revision must increment')
    fingerprints=('design_sha256','acceptance_sha256','context_sha256','requirement_ids')
    redesign=any(getattr(s.plan,k)!=getattr(previous.plan,k) for k in fingerprints)
    if redesign:
        _require(any(r.kind=='redesign' and r.evidence_refs for r in s.decisions[len(previous.decisions):]),
            'history_mismatch','$.plan','Redesign requires new decision/evidence')
    old={e.assignment_id:e for e in previous.assignments}; new={e.assignment_id:e for e in s.assignments}
    _require(old.keys()<=new.keys(),'history_mismatch','$.assignments','Assignment deleted')
    fresh_receipts=s.decisions[len(previous.decisions):]
    for key,e in new.items():
        before=old.get(key)
        if e.state in _TERMINAL or (before is not None and e.owned_paths==before.owned_paths
                and e.workspace_id==before.workspace_id and e.worktree_root==before.worktree_root):
            continue
        for prior_key,prior in old.items():
            if prior_key==key: continue
            logical=prior.workspace_id==e.workspace_id and any(
                _overlap(a,b) for a in e.owned_paths for b in prior.owned_paths)
            physical=any(_overlap(a,b) for a in _physical_paths(e) for b in _physical_paths(prior))
            overlaps=logical or physical
            if overlaps:
                source_ref=f'assignment:{prior.assignment_id}:{prior.revision}:{wire_digest(prior)}'
                _require(new[prior_key].state in _TERMINAL and any(r.kind=='reassignment'
                    and r.assignment_id==key and r.assignment_revision==e.revision
                    and r.plan_revision==s.plan.revision and source_ref in r.evidence_refs
                    for r in fresh_receipts), 'history_mismatch','$.assignments',
                    'Ownership transfer requires newly bound source-owner reassignment receipt')
    changed_accepted=set()
    for key,e in new.items():
        if key not in old:
            _require(e.revision==1 and e.state=='proposed','invalid_revision','$.assignments','New assignment must start proposed revision 1')
            continue
        before=old[key]
        if e!=before:
            _require(before.state not in _TERMINAL and e.revision==before.revision+1,'invalid_revision','$.assignments','Invalid assignment history')
            _require(e.state==before.state or e.state in _ASSIGNMENT_TRANSITIONS[before.state],'invalid_transition','$.assignments','Illegal state transition')
            if before.dispatch_token or e.dispatch_token:
                _require(_scope(e,mode)==_scope(before,mode) and (before.dispatch_token is None or e.dispatch_token==before.dispatch_token),
                    'invalid_transition','$.assignments','Dispatched execution scope immutable')
            if before.state=='accepted':
                _require(e.state in ('superseded','changes_requested'),'invalid_transition','$.assignments','Accepted output changed without invalidation')
                changed_accepted.add(key)
            if before.state=='blocked' and e.state=='working':
                _require(e.observed_run is not None,'wrong_run','$.assignments','Blocked resume needs run')
            if before.state=='blocked' and e.state=='proposed':
                _require(before.dispatch_token is None,'wrong_run','$.assignments','Dispatched work cannot reset')
    invalid=set(changed_accepted)
    if redesign: invalid|={key for key,e in old.items() if e.state=='accepted'}
    while True:
        extra={key for key,e in old.items() if any(p.assignment_id in invalid for p in e.dependencies)}-invalid
        if not extra: break
        invalid|=extra
    for key in invalid:
        if old[key].state=='accepted':
            e=new[key]
            _require(e.state in ('changes_requested','superseded') and not e.review_refs and e.output_sha256 is None
                and bool(e.invalidated_by),'stale_dependency','$.assignments','Accepted descendant not invalidated')
            ancestors={key}; pending=[key]
            while pending:
                current=pending.pop()
                for pin in old[current].dependencies:
                    if pin.assignment_id not in ancestors:
                        ancestors.add(pin.assignment_id); pending.append(pin.assignment_id)
            causes=ancestors & changed_accepted
            if redesign:
                causes|={r.receipt_id for r in fresh_receipts if r.kind=='redesign'
                    and r.plan_revision==s.plan.revision and r.evidence_refs}
            _require(set(e.invalidated_by)<=causes and bool(e.invalidated_by)
                and any(r.kind=='invalidation' and r.assignment_id==key
                    and r.assignment_revision==e.revision and r.plan_revision==s.plan.revision
                    and r.candidate_sha256==old[key].output_sha256 and r.evidence_refs
                    for r in fresh_receipts), 'history_mismatch','$.assignments',
                    'Invalidation requires known causal predecessor/redesign and newly bound receipt')

    old_intents={i.dispatch_token:i for i in previous.dispatches}; new_intents={i.dispatch_token:i for i in s.dispatches}
    _require(old_intents.keys()<=new_intents.keys(),'history_mismatch','$.dispatches','Dispatch deleted')
    for key,i in new_intents.items():
        if key in old_intents:
            before=old_intents[key]
            _require((i.assignment_id,i.envelope_revision,i.envelope_sha256,i.created_at)==
                (before.assignment_id,before.envelope_revision,before.envelope_sha256,before.created_at),
                'history_mismatch','$.dispatches','Dispatch target mutated')
            if i!=before:
                _require(i.state in _INTENT_TRANSITIONS[before.state],'invalid_transition','$.dispatches','Invalid dispatch transition')
                if before.observed_run: _require(i.observed_run==before.observed_run,'wrong_run','$.dispatches','Observed run mutated')
        else:
            e=new[i.assignment_id]
            _require(i.state=='pending' and i.envelope_revision==e.revision
                and i.envelope_sha256==wire_digest(e) and e.state=='dispatched',
                'wrong_run','$.dispatches','New intent must bind dispatched envelope')
    for sub in s.submissions[len(previous.submissions):]:
        e=new[sub.assignment_id]
        _require(e.dispatch_token in new_intents,'wrong_run','$.submissions','Missing dispatch')
        _submission_binding(e,sub,new_intents[e.dispatch_token])

def check_snapshot(snapshot,task,*,mode):
    """Check normalized mode-specific snapshot graph, bindings and pool."""
    return _snapshot_checks(_view(snapshot,mode,'snapshot'),task,mode)

def check_history(snapshot,previous,*,mode):
    """Check append-only histories, scope, invalidation and transitions."""
    return _history(_view(snapshot,mode,'snapshot'),_view(previous,mode,'snapshot'),mode)

def check_submission_binding(envelope,submission,intent,*,mode):
    return _submission_binding(_view(envelope,mode,'assignment'),
        _view(submission,mode,'submission'),_view(intent,mode,'dispatch'))

def scope_key(envelope,*,mode):
    return _scope(_view(envelope,mode,'assignment'),mode)


def check_ownership(snapshot,*,mode):
    """Check live logical and canonical root-plus-path ownership for preflight."""
    _ownership(_view(snapshot,mode,'snapshot').assignments)
