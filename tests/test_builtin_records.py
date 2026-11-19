"""Synthetic core integrity tests; these never assert host authenticity."""
import hashlib
import importlib
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from smart_assistant import contracts as c, delivery_records as d, quality
from tests.test_delivery_records import fixture as managed_fixture, STAMP, HASH


def core():
    return importlib.import_module('smart_assistant.builtin_records')


def fixture(root, workflow_kind="feature"):
    b = core()
    task, managed = managed_fixture(str(root))
    if workflow_kind!='feature':
        policy=replace(managed.policy,workflow_kind=workflow_kind,reproduction_required=True)
        task.request.source_refs[-1]=d.policy_source_ref(policy)
        managed=replace(managed,policy=policy,registration=replace(managed.registration,policy_sha256=d.delivery_digest(policy)),
            plan=replace(managed.plan,policy_sha256=d.delivery_digest(policy)))
    task.capability_ids = []
    task.selection = c.Selection(1, [], [])
    task.cycles = []
    task.artifact_root = str(root)
    task.requested_actions = []
    task.authorization = []
    (root / 'design.md').write_text('Synthetic design\n')
    (root / 'prompt.txt').write_text('Implement synthetic request\n')
    (root / 'instructions.md').write_text('Synthetic instructions\n')
    (root / 'authority.json').write_text('Observed local authority\n')
    (root / 'result.txt').write_text('baseline\n')
    def receipt(path):
        return b.BuiltinReceipt(path, hashlib.sha256((root/path).read_bytes()).hexdigest())
    decision = b.BuiltinDecision('2.0', task.id, b.base_request_digest(task.request, allow_unmarked=True),
        'builtin', 'user:2026-11-03:option-b', 'root', STAMP, 'Explicit builtin authorization', False)
    task.request.source_refs.append(b.mode_source_ref(decision))
    request_hash = d.request_digest(task.request)
    authority = b.BuiltinAuthority('2.0', task.id, request_hash, task.request.project_id, str(root),
        ['local'], ['local'], [], [], STAMP, receipt('authority.json'))
    context = c.ContextBundle(1, task.request.project_id, {}, [])
    acceptance = quality.acceptance_snapshot(task.criteria, root/'design.md')
    plan = replace(managed.plan, request_sha256=request_hash, design_sha256=acceptance.design_sha256,
        acceptance_sha256=acceptance.acceptance_id, context_sha256=hashlib.sha256(c.canonical_json(c.to_dict(context))).hexdigest())
    payload = b.BuiltinPayload('2.0', task.id, 1, 'implementer', 'design.md', task.criteria, context,
        ['result.txt'], c.Limits(), receipt('prompt.txt'), [receipt('instructions.md')], authority, 'other', None)
    e = b.BuiltinAssignment('2.0', 'worker-01', 1, task.id, None, True, payload, 'synthetic-base',
        'project-01', str(root), ['result.txt'], [], 'proposed', None, None, None, None, [], [])
    reg = replace(managed.registration, request_sha256=request_hash)
    s = b.BuiltinSnapshot('2.0', 'builtin', task.id, 1, None, decision, reg, managed.policy, plan, [e], [], [], [])
    return task, s, receipt


def dispatch(s):
    b=core(); e=replace(s.assignments[0], revision=2, state='dispatched', dispatch_token='token-01')
    i=b.BuiltinDispatch('2.0', 'token-01', e.assignment_id, e.revision, b.builtin_digest(e), STAMP,
        'pending', None, None, None)
    return replace(s, assignments=[e], dispatches=[i])


def observe(s, root, receipt):
    b=core(); original=dispatch(s); e=original.assignments[0]; i=original.dispatches[0]
    run=d.ObservedRun('1.0', 'host', 'worker', 'run-01', i.dispatch_token, STAMP, 'response.json')
    (root/'call.json').write_text(json.dumps({'tool':'spawn_agent','arguments':{'message':(root/'prompt.txt').read_text()}}))
    (root/'response.json').write_text(json.dumps({'agent_id':'run-01'}))
    binding=b.BuiltinHostBinding('2.0', s.task_id, e.assignment_id, i.dispatch_token, b.builtin_digest(e),
        e.payload.prompt.sha256, [r.sha256 for r in e.payload.instructions], b.builtin_digest(e.payload.authority),
        run, receipt('call.json'), receipt('response.json'))
    e=replace(e, revision=3, state='working', observed_run=run)
    i=replace(i,state='observed',observed_run=run,host_binding=binding)
    return replace(original, assignments=[e],dispatches=[i]), original.assignments[0]


def submission(s, receipt):
    b=core(); e=s.assignments[0]
    handoff=b.BuiltinHandoff('2.0', s.task_id, e.payload.assignment_revision,e.payload.responsibility,
        'ready_for_review',[c.Artifact('result-01','result.txt',receipt('result.txt').sha256)],
        {'criterion-01':['result.txt']}, ['result.txt'],None,'Review result')
    return b.BuiltinSubmission('2.0','submit-01',s.task_id,e.assignment_id,e.revision,b.builtin_digest(e),
        handoff,b.builtin_digest(handoff),e.observed_run,STAMP)


class BuiltinRecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='builtin-core-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.b=core(); self.task,self.s,self.receipt=fixture(self.root)

    def assertDenied(self,result,code=None):
        self.assertFalse(result.passed, result)
        if code: self.assertIn(code,[e.code for e in result.errors])

    def test_builtin_strict_roundtrip(self):
        self.assertTrue(self.b.validate_builtin(self.s,self.task).passed)
        for record in [self.s,self.s.decision,self.s.assignments[0],self.s.assignments[0].payload,
                self.s.assignments[0].payload.authority,self.receipt('prompt.txt')]:
            wire=self.b.builtin_to_dict(record)
            self.assertEqual(self.b.builtin_from_dict(type(record).__name__,wire),record)
        self.assertNotIn('selected_role_id',self.b.builtin_to_dict(self.s.assignments[0]))

    def test_unknown_mixed_version_counterfeit_managed_fields(self):
        for path,value in [('schema_version','1.0'),('selected_role_id','fake'),('revision',True)]:
            wire=self.b.builtin_to_dict(self.s.assignments[0]);wire[path]=value
            with self.assertRaises(c.ValidationError):self.b.builtin_from_dict('BuiltinAssignment',wire)
        wire=self.b.builtin_to_dict(self.s);wire['policy']['schema_version']='2.0'
        with self.assertRaises(c.ValidationError):self.b.builtin_from_dict('BuiltinSnapshot',wire)
        for bad in [replace(self.s,assignments=tuple(self.s.assignments)),replace(self.s,assignments=self.s.assignments*2)]:
            with self.assertRaises(c.ValidationError):self.b.builtin_to_dict(bad)
        wire=self.b.builtin_to_dict(self.s);wire['assignments'].append(wire)
        with self.assertRaises(c.ValidationError):self.b.builtin_from_dict('BuiltinSnapshot',wire)

    def test_base_request_digest_no_cycle(self):
        self.assertEqual(self.s.decision.base_request_sha256,self.b.base_request_digest(self.task.request))
        before=c.to_dict(self.task.request)
        self.b.base_request_digest(self.task.request)
        self.assertEqual(before,c.to_dict(self.task.request))
        self.task.request.text+=' changed'
        self.assertDenied(self.b.validate_builtin(self.s,self.task),'request_mismatch')

    def test_duplicate_unknown_mode_marker_configured_no_fallback(self):
        for refs in [self.task.request.source_refs*2,
                [self.task.request.source_refs[0],'smart-assistant:execution-mode:unknown:9.0:'+HASH],
                [self.task.request.source_refs[-1]], []]:
            task=c.from_dict('TaskRecord',c.to_dict(self.task));task.request.source_refs=refs
            self.assertDenied(self.b.validate_builtin(self.s,task))
        self.task.request.requested_role='configured-role'
        self.assertDenied(self.b.validate_builtin(self.s,self.task),'configured_fallback')

    def test_prompt_authority_context_binding(self):
        self.assertTrue(self.b.validate_builtin_dispatch(self.s,'worker-01',self.root).passed)
        for path in ['prompt.txt','instructions.md','authority.json','design.md']:
            old=(self.root/path).read_bytes();(self.root/path).write_text('changed')
            self.assertDenied(self.b.validate_builtin_dispatch(self.s,'worker-01',self.root))
            (self.root/path).write_bytes(old)
        e=self.s.assignments[0]
        bad=replace(e,payload=replace(e.payload,context=replace(e.payload.context,preferences={'changed':True})))
        self.assertDenied(self.b.validate_builtin(replace(self.s,assignments=[bad]),self.task))
        a=replace(e.payload.authority,available_tools=[])
        self.assertDenied(self.b.validate_builtin(replace(self.s,assignments=[replace(e,payload=replace(e.payload,authority=a))]),self.task),'preflight_denied')

    def test_crossed_handoff_wrong_run_and_exact_prompt_host_binding(self):
        s,original=observe(self.s,self.root,self.receipt);sub=submission(s,self.receipt);e=s.assignments[0];i=s.dispatches[0]
        self.assertTrue(self.b.validate_builtin_submission(e,sub,i,self.root,dispatched_envelope=original).passed)
        for changed in [replace(sub,assignment_id='worker-02'),replace(sub,observed_run=replace(sub.observed_run,run_ref='other')),
                replace(sub,payload=replace(sub.payload,responsibility='reviewer'),handoff_sha256=self.b.builtin_digest(replace(sub.payload,responsibility='reviewer')))]:
            self.assertDenied(self.b.validate_builtin_submission(e,changed,i,self.root,dispatched_envelope=original))
        (self.root/'call.json').write_text(json.dumps({'tool':'spawn_agent','arguments':{'message':'different'}}))
        i=replace(i,host_binding=replace(i.host_binding,submitted_call=self.receipt('call.json')))
        self.assertDenied(self.b.validate_builtin_submission(e,sub,i,self.root,dispatched_envelope=original),'prompt_mismatch')

    def test_same_run_two_tokens(self):
        s,_=observe(self.s,self.root,self.receipt);e=s.assignments[0];i=s.dispatches[0]
        other=replace(e,assignment_id='worker-02',owned_paths=[],worktree_root=str(self.root/'other'),
            payload=replace(e.payload,owned_paths=[]),dispatch_token='token-02')
        other_run=replace(e.observed_run,dispatch_token='token-02');other=replace(other,observed_run=other_run)
        other_i=replace(i,dispatch_token='token-02',assignment_id='worker-02',observed_run=other_run,
            host_binding=replace(i.host_binding,dispatch_token='token-02',assignment_id='worker-02',run=other_run))
        s=replace(s,plan=replace(s.plan,assignment_ids=['worker-01','worker-02']),assignments=[e,other],dispatches=[i,other_i])
        self.assertDenied(self.b.validate_builtin(s,self.task),'wrong_run')

    def repair(self):
        candidate=quality.snapshot(self.root,[c.Artifact('result-01','result.txt',HASH)])
        (self.root/'baseline.txt').write_bytes((self.root/'result.txt').read_bytes())
        (self.root/'before.log').write_text('Expected target bug observed: FAIL\n')
        (self.root/'assessment.md').write_text('Root assessed actual target failure\n')
        auth=self.b.BuiltinRepairAuthorization('2.0',self.task.id,d.request_digest(self.task.request),
            self.s.plan.design_sha256,self.s.plan.acceptance_sha256,self.s.plan.context_sha256,candidate,
            {'result.txt':self.receipt('baseline.txt')},[self.receipt('before.log')],self.s.plan.root_owner_ref,STAMP,self.receipt('assessment.md'))
        e=self.s.assignments[0];e=replace(e,payload=replace(e.payload,purpose='repair',repair_authorization=auth))
        return replace(self.s,assignments=[e])

    def test_missing_stale_checkpoint_changed_live_baseline_denies_dispatch(self):
        e=self.s.assignments[0];s=replace(self.s,assignments=[replace(e,payload=replace(e.payload,purpose='repair'))])
        self.assertDenied(self.b.validate_builtin_dispatch(s,'worker-01',self.root),'missing_reproduction')
        s=self.repair();self.assertTrue(self.b.validate_builtin_dispatch(s,'worker-01',self.root).passed)
        (self.root/'result.txt').write_text('changed before repair')
        self.assertDenied(self.b.validate_builtin_dispatch(s,'worker-01',self.root),'stale_baseline')
        for path in ['baseline.txt','before.log','assessment.md']:
            (self.root/path).write_text('drift')
            self.assertDenied(self.b.validate_builtin_dispatch(s,'worker-01',self.root))

    def test_repaired_candidate_completes_with_archived_baseline(self):
        s=self.repair();s,original=observe(s,self.root,self.receipt)
        (self.root/'result.txt').write_text('repaired product\n');sub=submission(s,self.receipt)
        self.assertTrue(self.b.validate_builtin_submission(s.assignments[0],sub,s.dispatches[0],self.root,dispatched_envelope=original).passed)
        (self.root/'baseline.txt').write_text('changed archive')
        self.assertDenied(self.b.validate_builtin_submission(s.assignments[0],sub,s.dispatches[0],self.root,dispatched_envelope=original))

    def test_DAG_overlap_invalidation(self):
        e=self.s.assignments[0];pin=d.DependencyPin('1.0','worker-02',None,None)
        self.assertDenied(self.b.validate_builtin(replace(self.s,assignments=[replace(e,dependencies=[pin])]),self.task),'invalid_graph')
        other=replace(e,assignment_id='worker-02',parent_assignment_id=e.assignment_id)
        s=replace(self.s,plan=replace(self.s.plan,assignment_ids=['worker-01','worker-02']),assignments=[e,other])
        self.assertDenied(self.b.validate_builtin(s,self.task),'ownership_overlap')
        s=dispatch(self.s);after=replace(s,revision=2,previous_sha256=self.b.builtin_digest(s),
            assignments=[replace(s.assignments[0],revision=3,base_ref='changed')])
        self.assertDenied(self.b.validate_builtin(after,self.task,s),'invalid_transition')

    def test_ambiguous_capacity_payload_limits_nested_assignments(self):
        e=self.s.assignments[0]
        for limits in [c.Limits(4,2),c.Limits(3,3)]:
            bad=replace(e,payload=replace(e.payload,limits=limits))
            self.assertDenied(self.b.validate_builtin(replace(self.s,assignments=[bad]),self.task),'policy_mismatch')
        self.task.limits=c.Limits(4,2)
        self.assertDenied(self.b.validate_builtin(self.s,self.task),'policy_mismatch')
        self.task.limits=c.Limits()
        envelopes=[];intents=[]
        for n in range(3):
            key=f'worker-0{n+1}';token=f'token-0{n+1}'
            child=replace(e,assignment_id=key,parent_assignment_id=None if n==0 else 'worker-01',
                worktree_root=str(self.root/f'child{n}'),owned_paths=[],payload=replace(e.payload,owned_paths=[]),
                state='dispatched',revision=2,dispatch_token=token)
            envelopes.append(child);intents.append(self.b.BuiltinDispatch('2.0',token,key,2,self.b.builtin_digest(child),STAMP,'ambiguous',None,None,None))
        s=replace(self.s,plan=replace(self.s.plan,assignment_ids=[e.assignment_id for e in envelopes]),assignments=envelopes,dispatches=intents)
        self.assertDenied(self.b.validate_builtin(s,self.task),'policy_mismatch')

    def test_correction_history_immutable_decision(self):
        after=replace(self.s,revision=2,previous_sha256=self.b.builtin_digest(self.s),decision=replace(self.s.decision,rationale='changed'))
        self.assertDenied(self.b.validate_builtin(after,self.task,self.s))
        task_with_cycles,_=managed_fixture()
        self.task.cycles=task_with_cycles.cycles*4
        self.assertDenied(self.b.validate_builtin(self.s,self.task),'policy_mismatch')

    def test_completion_receipts_preserve_repaired_product_and_detect_all_drift(self):
        s=self.repair();s,_=observe(s,self.root,self.receipt)
        (self.root/'result.txt').write_text('repaired bytes differ from baseline')
        self.assertTrue(self.b.validate_builtin_receipts(s,self.root).passed)
        for path in ['prompt.txt','instructions.md','authority.json','baseline.txt','before.log','assessment.md','call.json','response.json','design.md']:
            original=(self.root/path).read_bytes();(self.root/path).write_text('drift')
            self.assertDenied(self.b.validate_builtin_receipts(s,self.root))
            (self.root/path).write_bytes(original)
        self.assertTrue(self.b.validate_builtin_receipts(s,self.root).passed)

    def test_distinct_worker_coordinator_roots_and_authority_mismatch(self):
        self.task.artifact_root=str(self.root/'coordinator');(self.root/'coordinator').mkdir()
        self.assertTrue(self.b.validate_builtin(self.s,self.task).passed)
        self.assertTrue(self.b.validate_builtin_receipts(self.s,self.root/'coordinator').passed)
        e=self.s.assignments[0];authority=replace(e.payload.authority,artifact_root=str(self.root/'other'))
        bad=replace(self.s,assignments=[replace(e,payload=replace(e.payload,authority=authority))])
        self.assertDenied(self.b.validate_builtin(bad,self.task),'unsafe_path')

    def test_receipt_symlinks_and_duplicate_json_keys_are_denied(self):
        s,_=observe(self.s,self.root,self.receipt)
        path=self.root/'instructions.md';saved=path.read_bytes();path.unlink();path.symlink_to(self.root/'result.txt')
        self.assertDenied(self.b.validate_builtin_receipts(s,self.root))
        path.unlink();path.write_bytes(saved)
        (self.root/'call.json').write_text('{"tool":"spawn_agent","tool":"spawn_agent","arguments":{}}')
        i=s.dispatches[0];i=replace(i,host_binding=replace(i.host_binding,submitted_call=self.receipt('call.json')))
        self.assertDenied(self.b.validate_builtin_receipts(replace(s,dispatches=[i]),self.root),'invalid_type')

    def test_genuine_collaboration_task_name_response(self):
        s,_=observe(self.s,self.root,self.receipt);i=s.dispatches[0]
        (self.root/'call.json').write_text(json.dumps({'tool':'collaboration.spawn_agent','arguments':{'task_name':'worker','message':(self.root/'prompt.txt').read_text(),'fork_turns':'none'}}))
        (self.root/'response.json').write_text(json.dumps({'task_name':'run-01'}))
        binding=replace(i.host_binding,submitted_call=self.receipt('call.json'),observed_response=self.receipt('response.json'))
        s=replace(s,dispatches=[replace(i,host_binding=binding)])
        self.assertTrue(self.b.validate_builtin_receipts(s,self.root).passed)

    def test_handoff_file_and_coverage_parity(self):
        s,original=observe(self.s,self.root,self.receipt);sub=submission(s,self.receipt);e=s.assignments[0];i=s.dispatches[0]
        for change in [dict(criteria_coverage={}),dict(artifacts=[]),dict(blocker='blocked'),dict(next_step=''),dict(artifacts=[c.Artifact('result-01','outside.txt',HASH)])]:
            handoff=replace(sub.payload,**change);bad=replace(sub,payload=handoff,handoff_sha256=self.b.builtin_digest(handoff))
            self.assertDenied(self.b.validate_builtin_submission(e,bad,i,self.root,dispatched_envelope=original))
        (self.root/'result.txt').write_text('changed output')
        self.assertDenied(self.b.validate_builtin_submission(e,sub,i,self.root,dispatched_envelope=original),'artifact_digest_mismatch')

    def test_corrections_use_narrowest_shared_budget_and_keep_failed_history(self):
        historical_task,_=managed_fixture()
        self.task.cycles=historical_task.cycles*2
        self.task.limits=c.Limits(1,2)
        e=self.s.assignments[0];e=replace(e,payload=replace(e.payload,limits=c.Limits(1,2)))
        s=replace(self.s,assignments=[e])
        self.assertDenied(self.b.validate_builtin(s,self.task),'policy_mismatch')

    def test_four_independent_repairs_do_not_impose_total_team_size_cap(self):
        repair=self.repair();template=repair.assignments[0];assignments=[]
        for n in range(4):
            assignments.append(replace(template,assignment_id=f'worker-{n+1:02}',state='failed',owned_paths=[],payload=replace(template.payload,owned_paths=[])))
        s=replace(repair,assignments=assignments,plan=replace(repair.plan,assignment_ids=[e.assignment_id for e in assignments]))
        self.assertTrue(self.b.validate_builtin(s,self.task).passed)

    def test_authority_uses_exact_authorized_worker_subset(self):
        actions=[c.RequestedAction('action-01',c.ActionKind.WRITE_LOCAL,'result.txt','local',c.HostDecision.ALLOWED),
            c.RequestedAction('action-02',c.ActionKind.READ_LOCAL,'design.md','local',c.HostDecision.ALLOWED)]
        scopes=[c.AuthorizationScope(c.ActionKind.WRITE_LOCAL,'result.txt','user:request'),
            c.AuthorizationScope(c.ActionKind.READ_LOCAL,'design.md','user:request')]
        self.task.requested_actions=actions;self.task.authorization=scopes
        e=self.s.assignments[0];a=replace(e.payload.authority,requested_actions=actions[:1],authorization=scopes[:1])
        good=replace(self.s,assignments=[replace(e,payload=replace(e.payload,authority=a))])
        self.assertTrue(self.b.validate_builtin(good,self.task).passed)
        for bad_a in [replace(a,requested_actions=[replace(actions[0],resource_ref='other.txt')]),
                replace(a,requested_actions=[replace(actions[0],required_tool=None)]),
                replace(a,authorization=[replace(scopes[0],source_ref='invented')]),
                replace(a,authorization=scopes[:1]*2)]:
            bad=replace(self.s,assignments=[replace(e,payload=replace(e.payload,authority=bad_a))])
            self.assertDenied(self.b.validate_builtin(bad,self.task),'preflight_denied')

    def test_direct_dispatch_and_receipts_reject_plan_policy_overflow(self):
        e=self.s.assignments[0];over=replace(e,payload=replace(e.payload,limits=c.Limits(3,3)))
        s=replace(self.s,plan=replace(self.s.plan,max_executing=3),assignments=[over])
        self.assertDenied(self.b.validate_builtin_dispatch(s,e.assignment_id,self.root),'policy_mismatch')
        self.assertDenied(self.b.validate_builtin_receipts(s,self.root),'policy_mismatch')

    def test_bug_implementer_cannot_label_repair_other_to_skip_checkpoint(self):
        self.task,s,self.receipt=fixture(self.root,workflow_kind='bug')
        self.assertDenied(self.b.validate_builtin_dispatch(s,'worker-01',self.root),'missing_reproduction')
        self.assertDenied(self.b.validate_builtin_receipts(s,self.root),'missing_reproduction')

    def test_redesign_keeps_frozen_cancelled_assignment_scope(self):
        old=self.s.assignments[0]
        context=replace(old.payload.context,preferences={'new-design':True})
        new=replace(old,assignment_id='worker-02',owned_paths=['new.txt'],
            payload=replace(old.payload,context=context,owned_paths=['new.txt']))
        plan=replace(self.s.plan,revision=2,assignment_ids=['worker-01','worker-02'],
            context_sha256=hashlib.sha256(c.canonical_json(c.to_dict(context))).hexdigest())
        receipt=d.DecisionReceipt('1.0','redesign-01',self.task.id,'redesign','root',2,None,None,
            self.s.plan.context_sha256,['design.md'],'Observed context redesign',STAMP)
        after=replace(self.s,revision=2,previous_sha256=self.b.builtin_digest(self.s),plan=plan,
            assignments=[replace(old,revision=2,state='cancelled'),new],decisions=[receipt])
        self.assertTrue(self.b.validate_builtin(after,self.task,self.s).passed)
        self.assertEqual(after.assignments[0].payload,self.s.assignments[0].payload)
        self.assertTrue(self.b.validate_builtin_receipts(after,self.root).passed)
        self.assertDenied(self.b.validate_builtin_dispatch(after,'worker-01',self.root))

    def nested_ownership(self):
        child=self.root/'child';child.mkdir()
        _,child_s,_=fixture(child)
        e=self.s.assignments[0]
        first=replace(e,owned_paths=['child/result.txt'],payload=replace(e.payload,owned_paths=['child/result.txt']))
        second=replace(child_s.assignments[0],assignment_id='worker-02')
        return replace(self.s,plan=replace(self.s.plan,assignment_ids=['worker-01','worker-02']),assignments=[first,second])

    def test_C01_nested_canonical_roots_cannot_own_same_physical_file(self):
        s=self.nested_ownership();first,second=s.assignments
        self.assertTrue((Path(first.worktree_root)/first.owned_paths[0]).samefile(Path(second.worktree_root)/second.owned_paths[0]))
        for gate in [self.b.validate_builtin(s,self.task),
                self.b.validate_builtin_dispatch(s,first.assignment_id,Path(first.worktree_root)),
                self.b.validate_builtin_dispatch(s,second.assignment_id,Path(second.worktree_root)),
                self.b.validate_builtin_receipts(s,self.root)]:
            self.assertDenied(gate,'ownership_overlap')

    def test_C01_nested_and_separate_roots_with_disjoint_files_pass(self):
        s=self.nested_ownership();first,second=s.assignments
        first=replace(first,owned_paths=['outer.txt'],payload=replace(first.payload,owned_paths=['outer.txt']))
        (self.root/'outer.txt').write_text('disjoint first output')
        nested=replace(s,assignments=[first,second])
        self.assertTrue(self.b.validate_builtin(nested,self.task).passed)
        for e in nested.assignments:
            self.assertTrue(self.b.validate_builtin_dispatch(nested,e.assignment_id,Path(e.worktree_root)).passed)
        separate=self.root/'separate';separate.mkdir();_,separate_s,_=fixture(separate)
        second=replace(separate_s.assignments[0],assignment_id='worker-02')
        self.assertTrue(self.b.validate_builtin(replace(s,assignments=[first,second]),self.task).passed)

    def test_C01_terminal_physical_ownership_transfer_retains_history(self):
        collision=self.nested_ownership();first,second=collision.assignments
        before=replace(self.s,assignments=[first])
        plan=replace(collision.plan,revision=2)
        source=f'assignment:{first.assignment_id}:{first.revision}:{self.b.builtin_digest(first)}'
        transfer=d.DecisionReceipt('1.0','transfer-01',self.task.id,'reassignment','root-chat',2,
            second.assignment_id,1,None,[source],'Transfer stopped ownership',STAMP)
        after=replace(collision,revision=2,previous_sha256=self.b.builtin_digest(before),plan=plan,
            assignments=[replace(first,revision=2,state='cancelled'),second],decisions=[transfer])
        self.assertTrue(self.b.validate_builtin(after,self.task,before).passed)
        self.assertEqual(after.assignments[0].payload,before.assignments[0].payload)
        self.assertTrue(self.b.validate_builtin_dispatch(after,second.assignment_id,Path(second.worktree_root)).passed)

    def test_C01_R1_physical_transfer_requires_fresh_exact_source_target_receipt(self):
        collision=self.nested_ownership();first,second=collision.assignments
        before=replace(self.s,assignments=[first]);plan=replace(collision.plan,revision=2)
        source=f'assignment:{first.assignment_id}:{first.revision}:{self.b.builtin_digest(first)}'
        transfer=d.DecisionReceipt('1.0','transfer-01',self.task.id,'reassignment','root-chat',2,
            second.assignment_id,1,None,[source],'Transfer stopped ownership',STAMP)
        after=replace(collision,revision=2,previous_sha256=self.b.builtin_digest(before),plan=plan,
            assignments=[replace(first,revision=2,state='cancelled'),second],decisions=[transfer])
        self.assertTrue(self.b.validate_builtin(after,self.task,before).passed)
        for receipts in [[],[replace(transfer,evidence_refs=['unrelated'])],
                [replace(transfer,assignment_id=first.assignment_id)],
                [replace(transfer,assignment_revision=2)],
                [replace(transfer,plan_revision=1)]]:
            with self.subTest(receipts=receipts):
                self.assertDenied(self.b.validate_builtin(replace(after,decisions=receipts),self.task,before),'history_mismatch')
        # An existing earlier receipt is not a fresh transfer authorization.
        before=replace(before,decisions=[replace(transfer,plan_revision=1)])
        after=replace(after,previous_sha256=self.b.builtin_digest(before),decisions=before.decisions)
        self.assertDenied(self.b.validate_builtin(after,self.task,before),'history_mismatch')

    def test_C01_R1_root_change_cannot_use_unchanged_relative_scope_fast_path(self):
        collision=self.nested_ownership();first,second=collision.assignments
        separate=self.root/'separate';separate.mkdir()
        _,separate_s,_=fixture(separate)
        target_before=replace(separate_s.assignments[0],assignment_id=second.assignment_id)
        before=replace(collision,assignments=[first,target_before])
        self.assertTrue(self.b.validate_builtin(before,self.task).passed)
        target=replace(second,revision=2)
        source=f'assignment:{first.assignment_id}:{first.revision}:{self.b.builtin_digest(first)}'
        transfer=d.DecisionReceipt('1.0','transfer-01',self.task.id,'reassignment','root-chat',1,
            target.assignment_id,2,None,[source],'Transfer moved writer',STAMP)
        after=replace(before,revision=2,previous_sha256=self.b.builtin_digest(before),
            assignments=[replace(first,revision=2,state='cancelled'),target],decisions=[transfer])
        self.assertTrue(self.b.validate_builtin(after,self.task,before).passed)
        self.assertDenied(self.b.validate_builtin(replace(after,decisions=[]),self.task,before),'history_mismatch')
        self.assertEqual(after.assignments[0].payload,before.assignments[0].payload)

    def test_C02_checkpoint_assessor_is_declared_root_for_all_snapshot_paths(self):
        s=self.repair();e=s.assignments[0];a=e.payload.repair_authorization
        for actor in [s.plan.root_owner_ref,'worker','unrelated-root']:
            assigned=replace(e,payload=replace(e.payload,repair_authorization=replace(a,assessed_by_actor_ref=actor)))
            checkpoint=replace(s,assignments=[assigned])
            gates=[self.b.validate_builtin(checkpoint,self.task),
                self.b.validate_builtin_dispatch(checkpoint,assigned.assignment_id,self.root)]
            observed,_=observe(checkpoint,self.root,self.receipt)
            gates.append(self.b.validate_builtin_receipts(observed,self.root))
            for gate in gates:
                if actor==s.plan.root_owner_ref:self.assertTrue(gate.passed,gate.errors)
                else:self.assertDenied(gate,'unauthorized_checkpoint')

    def test_C02_historical_checkpoint_still_binds_original_immutable_root(self):
        s=self.repair();e=s.assignments[0]
        checkpoint=replace(e.payload.repair_authorization,assessed_by_actor_ref=s.plan.root_owner_ref)
        e=replace(e,payload=replace(e.payload,repair_authorization=checkpoint))
        s=replace(s,assignments=[e]);after=replace(s,revision=2,previous_sha256=self.b.builtin_digest(s),
            assignments=[replace(e,revision=2,state='cancelled')])
        self.assertTrue(self.b.validate_builtin(after,self.task,s).passed)
        self.assertTrue(self.b.validate_builtin_receipts(after,self.root).passed)
        bad=replace(after,plan=replace(after.plan,root_owner_ref='unrelated-root'))
        self.assertDenied(self.b.validate_builtin_receipts(bad,self.root),'unauthorized_checkpoint')

    def call_snapshot(self,variant,changes=None):
        s,_=observe(self.s,self.root,self.receipt);i=s.dispatches[0]
        args={'message':(self.root/'prompt.txt').read_text()}
        response={'agent_id':'run-01'}
        if variant=='collaboration.spawn_agent':
            args['task_name']='worker';response={'task_name':'run-01'}
        call={'tool':variant,'arguments':args}
        if changes is not None:changes(call)
        (self.root/'call.json').write_text(json.dumps(call))
        (self.root/'response.json').write_text(json.dumps(response))
        binding=replace(i.host_binding,submitted_call=self.receipt('call.json'),observed_response=self.receipt('response.json'))
        return replace(s,dispatches=[replace(i,host_binding=binding)])

    def test_C03_raw_call_and_argument_objects_are_closed_for_each_host(self):
        for variant in ['spawn_agent','collaboration.spawn_agent']:
            mutations=[lambda call:call.update(extra=True),
                lambda call:call['arguments'].update(unsupported_option=True),
                lambda call:call['arguments'].update(permission_mode='allow-all'),
                lambda call:call['arguments'].update(model='another-model'),
                lambda call:call['arguments'].update(reasoning_effort='high')]
            for mutation in mutations:
                with self.subTest(variant=variant,mutation=mutations.index(mutation)):
                    s=self.call_snapshot(variant,mutation)
                    self.assertDenied(self.b.validate_builtin_receipts(s,self.root),'invalid_host_call')

    def test_C03_exact_supported_argument_types_and_optional_fork_turns(self):
        for variant in ['spawn_agent','collaboration.spawn_agent']:
            for fork in [None,'all','none']:
                mutation=None if fork is None else lambda call,fork=fork:call['arguments'].update(fork_turns=fork)
                s=self.call_snapshot(variant,mutation)
                self.assertTrue(self.b.validate_builtin_receipts(s,self.root).passed)
            for field,value in [('message',True),('message',['wrong']),('task_name',True),('task_name',''),
                    ('task_name',None),('fork_turns',True),('fork_turns',None),('fork_turns',1),('fork_turns','sometimes')]:
                with self.subTest(variant=variant,field=field,value=value):
                    s=self.call_snapshot(variant,lambda call,field=field,value=value:call['arguments'].update({field:value}))
                    self.assertDenied(self.b.validate_builtin_receipts(s,self.root),'invalid_host_call')
            for field,value in [('tool',True),('tool','unknown-host'),('arguments',[]),('arguments',None)]:
                s=self.call_snapshot(variant,lambda call,field=field,value=value:call.update({field:value}))
                self.assertDenied(self.b.validate_builtin_receipts(s,self.root),'invalid_host_call')

    def test_no_core_codec_persistence_or_P12_import(self):
        import ast
        for name in ['builtin_records','delivery_semantics']:
            tree=ast.parse(Path(importlib.import_module('smart_assistant.'+name).__file__).read_text())
            imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            self.assertFalse({'delivery_codec','delivery_evidence','delivery_store','delivery_gate','state'} & set(imports))
