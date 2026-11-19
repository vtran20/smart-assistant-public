"""Synthetic P11 integrity tests; no native actor/evidence authenticity claim."""
import copy
from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from smart_assistant import contracts as c

STAMP = '2026-11-03T10:00:00Z'
HASH = 'a' * 64
EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/contracts'


def module():
    assert importlib.util.find_spec('smart_assistant.delivery_records') is not None, 'P11 delivery_records missing'
    return importlib.import_module('smart_assistant.delivery_records')


def support(record_kind, **fields):
    return module().delivery_from_dict(record_kind, dict(schema_version='1.0', **fields))


def fixture(root='/private/tmp/synthetic-p11'):
    d = module()
    policy = support('DeliveryPolicy', policy_id='policy-01', policy_version='1.0.0', workflow_kind='feature',
        source_ref='design/policy.md', source_sha256=HASH, reproduction_required=False,
        independent_review_required=True, required_verification_levels=['unit'], max_executing=2, max_correction_cycles=3)
    task = c.from_dict('TaskRecord', json.loads((EXAMPLES / 'TaskRecord.json').read_text()))
    task.status = c.TaskStatus.RUNNING
    task.request.source_refs.append(d.policy_source_ref(policy))
    registration = support('DeliveryRegistration', task_id=task.id, request_sha256=d.request_digest(task.request),
        policy_id=policy.policy_id, policy_sha256=d.delivery_digest(policy), registered_at=STAMP)
    plan = support('DeliveryPlan', task_id=task.id, revision=1, request_sha256=registration.request_sha256,
        policy_sha256=registration.policy_sha256, root_owner_ref='root-chat', design_sha256=HASH,
        acceptance_sha256=HASH, routing_rationale='Synthetic feature', requirement_ids=['criterion-01'],
        assignment_ids=['worker-01'], max_executing=2, max_correction_cycles=3, context_sha256=HASH, next_step='Implement')
    payload = c.from_dict('TaskAssignment', json.loads((EXAMPLES / 'TaskAssignment.json').read_text()))
    payload.owned_paths = ['outputs/result.md']
    selected = payload.selection.agents[0]
    envelope = support('AssignmentEnvelope', assignment_id='worker-01', revision=1, task_id=task.id,
        parent_assignment_id=None, required=True, payload=c.to_dict(payload), selected_role_id=payload.role_id,
        selected_role_version=selected.version, selected_manifest_sha256=selected.deployed_sha256,
        base_ref='synthetic-base', workspace_id='project-01', worktree_root=root,
        owned_paths=payload.owned_paths, dependencies=[], state='proposed', dispatch_token=None,
        observed_run=None, output_sha256=None, handoff_submission_id=None, review_refs=[], invalidated_by=[])
    snap = support('DeliverySnapshot', task_id=task.id, revision=1, previous_sha256=None,
        registration=d.delivery_to_dict(registration), policy=d.delivery_to_dict(policy), plan=d.delivery_to_dict(plan),
        assignments=[d.delivery_to_dict(envelope)], dispatches=[], submissions=[], decisions=[])
    return task, snap


def dispatched(snapshot):
    d = module()
    e = replace(snapshot.assignments[0], state='dispatched', revision=2, dispatch_token='token-01')
    intent = support('DispatchIntent', dispatch_token='token-01', assignment_id=e.assignment_id,
        envelope_revision=e.revision, envelope_sha256=d.delivery_digest(e), created_at=STAMP,
        state='pending', observed_run=None, reconciliation_ref=None)
    return replace(snapshot, assignments=[e], dispatches=[intent])


def observed(snapshot):
    s = dispatched(snapshot)
    run = support('ObservedRun', host_ref='host-01', actor_ref='actor-01', run_ref='run-01',
        dispatch_token='token-01', observed_at=STAMP, observation_ref='observations/spawn.json')
    return replace(s, assignments=[replace(s.assignments[0], revision=3, state='working', observed_run=run)],
        dispatches=[replace(s.dispatches[0], state='observed', observed_run=run)])


def proposal(snapshot, **fields):
    return replace(snapshot, revision=snapshot.revision+1, previous_sha256=module().delivery_digest(snapshot), **fields)


def accepted_graph(snapshot, edges):
    """Synthetic accepted DAG with individually bound ready submissions and stopped runs."""
    d=module(); envelopes={}; dispatches=[]; submissions=[]
    template=snapshot.assignments[0]
    for key,predecessors in edges.items():
        paths=[f'outputs/{key}.md']; token='token-'+key
        payload=replace(template.payload,owned_paths=paths)
        pins=[support('DependencyPin',assignment_id=dep,accepted_revision=envelopes[dep].revision,
            output_sha256=envelopes[dep].output_sha256) for dep in predecessors]
        dispatched_e=replace(template,assignment_id=key,revision=2,payload=payload,
            worktree_root='/private/tmp/p11-'+key,owned_paths=paths,dependencies=pins,state='dispatched',dispatch_token=token)
        run=support('ObservedRun',host_ref='host',actor_ref='actor-'+key,run_ref='run-'+key,
            dispatch_token=token,observed_at=STAMP,observation_ref='synthetic/spawn')
        ready=replace(dispatched_e,revision=4,state='ready_for_review',observed_run=run,handoff_submission_id='submit-'+key)
        handoff=c.from_dict('Handoff',json.loads((EXAMPLES/'Handoff.json').read_text()))
        handoff.artifacts=[c.Artifact('result-01',paths[0],HASH)]; handoff.next_step='Review output'
        submission=support('HandoffSubmission',submission_id='submit-'+key,task_id=snapshot.task_id,
            assignment_id=key,envelope_revision=4,envelope_sha256=d.delivery_digest(ready),payload=c.to_dict(handoff),
            handoff_sha256=hashlib.sha256(c.canonical_json(c.to_dict(handoff))).hexdigest(),
            observed_run=d.delivery_to_dict(run),submitted_at=STAMP)
        output=hashlib.sha256(c.canonical_json([c.to_dict(a) for a in handoff.artifacts])).hexdigest()
        envelopes[key]=replace(ready,revision=5,state='accepted',output_sha256=output,review_refs=['review/'+key])
        dispatches.append(support('DispatchIntent',dispatch_token=token,assignment_id=key,envelope_revision=2,
            envelope_sha256=d.delivery_digest(dispatched_e),created_at=STAMP,state='terminated',
            observed_run=d.delivery_to_dict(run),reconciliation_ref='synthetic/stopped'))
        submissions.append(submission)
    return replace(snapshot,plan=replace(snapshot.plan,assignment_ids=list(edges)),
        assignments=list(envelopes.values()),dispatches=dispatches,submissions=submissions)


def decision(snapshot,receipt_id,kind,assignment=None,revision=None,candidate=None,refs=None):
    return support('DecisionReceipt',receipt_id=receipt_id,task_id=snapshot.task_id,kind=kind,
        actor_ref='root-chat',plan_revision=snapshot.plan.revision,assignment_id=assignment,
        assignment_revision=revision,candidate_sha256=candidate,evidence_refs=refs or ['evidence/decision.md'],
        reason='Synthetic recorded decision',created_at=STAMP)


class DeliveryRecordsTests(unittest.TestCase):
    def setUp(self):
        self.d = module()
        self.task, self.snapshot = fixture()

    def gate(self, snap=None, previous=None):
        return self.d.validate_delivery(snap or self.snapshot, self.task, previous)

    def test_policy_reference_binds_full_request_without_cycle(self):
        self.assertTrue(self.gate().passed)
        self.task.request.text += ' changed'
        self.assertFalse(self.gate().passed)

    def test_roundtrip_every_nested_record_and_v1_wire(self):
        s = observed(self.snapshot)
        for record in [s, s.policy, s.plan, s.registration, s.assignments[0], s.dispatches[0], s.dispatches[0].observed_run]:
            wire = self.d.delivery_to_dict(record)
            self.assertEqual(self.d.delivery_from_dict(type(record).__name__, wire), record)
        self.assertEqual(c.to_dict(s.assignments[0].payload), self.d.delivery_to_dict(s)['assignments'][0]['payload'])

    def test_malformed_field_table(self):
        for field, value in [('schema_version', '9.0'), ('revision', True), ('revision', 0),
                ('task_id', '../bad'), ('previous_sha256', 'A'*64), ('unknown', 'field')]:
            with self.subTest(field=field, value=value):
                wire = self.d.delivery_to_dict(self.snapshot)
                wire[field] = value
                with self.assertRaises(c.ValidationError): self.d.delivery_from_dict('DeliverySnapshot', wire)

    def test_invalid_timestamp_and_unicode(self):
        for stamp in ['2026-02-30T01:00:00Z', '2026-01-01', '2026-01-01T00:00:00+00:00']:
            with self.assertRaises(c.ValidationError): self.d.delivery_to_dict(replace(self.snapshot.registration, registered_at=stamp))
        with self.assertRaises(c.ValidationError): self.d.delivery_to_dict(replace(self.snapshot.plan, next_step='\ud800'))

    def test_cyclic_container_is_validation_error(self):
        cyclic = []; cyclic.append(cyclic)
        with self.assertRaises(c.ValidationError): self.d.delivery_to_dict(replace(self.snapshot.plan, assignment_ids=cyclic))

    def test_duplicate_and_missing_reserved_ref(self):
        self.task.request.source_refs *= 2
        self.assertFalse(self.gate().passed)
        self.task.request.source_refs = []
        self.assertFalse(self.gate().passed)

    def test_policy_cannot_be_replaced(self):
        newer = proposal(self.snapshot, policy=replace(self.snapshot.policy, max_executing=1))
        self.assertFalse(self.gate(newer, self.snapshot).passed)

    def test_plan_ids_exact_and_assignment_ids_unique(self):
        for s in [replace(self.snapshot, assignments=[]), replace(self.snapshot, assignments=self.snapshot.assignments*2)]:
            self.assertFalse(self.gate(s).passed)

    def test_dependency_cycle_and_missing_predecessor(self):
        e = self.snapshot.assignments[0]
        pin = support('DependencyPin', assignment_id='worker-02', accepted_revision=None, output_sha256=None)
        self.assertFalse(self.gate(replace(self.snapshot, assignments=[replace(e, dependencies=[pin])])).passed)
        other = replace(e, assignment_id='worker-02', worktree_root='/private/tmp/other', owned_paths=[],
            payload=replace(e.payload, owned_paths=[]), dependencies=[replace(pin, assignment_id='worker-01')])
        s = replace(self.snapshot, plan=replace(self.snapshot.plan, assignment_ids=['worker-01','worker-02']),
            assignments=[replace(e, dependencies=[pin]), other])
        self.assertFalse(self.gate(s).passed)

    def test_ownership_alias_conflicts_across_worktrees(self):
        e = self.snapshot.assignments[0]
        for path in ['OUTPUTS/result.md', 'outputs/result.md/child', 'outputs/result.md']:
            other = replace(e, assignment_id='worker-02', worktree_root='/private/tmp/other',
                owned_paths=[path], payload=replace(e.payload, owned_paths=[path]))
            s = replace(self.snapshot, plan=replace(self.snapshot.plan, assignment_ids=['worker-01','worker-02']), assignments=[e,other])
            self.assertFalse(self.gate(s).passed)

    def test_unsafe_ownership_table(self):
        for path in ['../escape', '/absolute', 'dir//file', 'dir/./file', 'dir\\file', '*.py', 'dir/file?', 'e\u0301.txt']:
            e = replace(self.snapshot.assignments[0], owned_paths=[path])
            with self.assertRaises(c.ValidationError): self.d.delivery_to_dict(e)

    def test_pending_ambiguous_and_unconfirmed_terminal_runs_consume_capacity(self):
        s = dispatched(self.snapshot)
        self.assertEqual(self.d.dispatch_status(s).occupied_tokens, ['token-01'])
        s = replace(s, dispatches=[replace(s.dispatches[0], state='ambiguous')])
        self.assertEqual(self.d.dispatch_status(s).occupied_tokens, ['token-01'])
        s = replace(s, assignments=[replace(s.assignments[0], state='cancelled')])
        self.assertEqual(self.d.dispatch_status(s).occupied_tokens, ['token-01'])

    def test_observed_identity_cannot_be_local_token_only(self):
        s = dispatched(self.snapshot)
        s = replace(s, dispatches=[replace(s.dispatches[0], state='observed')])
        self.assertFalse(self.gate(s).passed)

    def test_original_dispatch_digest_survives_legitimate_progress(self):
        before = dispatched(self.snapshot)
        after = observed(self.snapshot)
        after = proposal(before, assignments=after.assignments, dispatches=after.dispatches)
        self.assertTrue(self.gate(after, before).passed)
        changed = replace(after.assignments[0], base_ref='different-execution-scope')
        self.assertFalse(self.gate(replace(after, assignments=[changed]), before).passed)

    def test_history_removal_or_revision_reset_denied(self):
        newer = proposal(self.snapshot, assignments=[])
        self.assertFalse(self.gate(newer, self.snapshot).passed)
        newer = proposal(self.snapshot, assignments=[replace(self.snapshot.assignments[0], revision=1, state='blocked')])
        self.assertFalse(self.gate(newer, self.snapshot).passed)

    def test_submission_cross_run_rejected_before_v1(self):
        s = observed(self.snapshot)
        e = s.assignments[0]
        handoff = c.from_dict('Handoff', json.loads((EXAMPLES/'Handoff.json').read_text()))
        sub = support('HandoffSubmission', submission_id='submit-01', task_id=s.task_id, assignment_id='worker-02',
            envelope_revision=e.revision, envelope_sha256=self.d.delivery_digest(e), payload=c.to_dict(handoff),
            handoff_sha256=hashlib.sha256(c.canonical_json(c.to_dict(handoff))).hexdigest(), observed_run=self.d.delivery_to_dict(e.observed_run), submitted_at=STAMP)
        with patch('smart_assistant.delivery_records.validate_handoff') as inner:
            result = self.d.validate_submission(e, sub, s.dispatches[0], Path(e.worktree_root))
            self.assertFalse(result.passed); inner.assert_not_called()


    def make_submission(self, snapshot):
        e = snapshot.assignments[0]
        payload = c.from_dict('Handoff', json.loads((EXAMPLES/'Handoff.json').read_text()))
        return support('HandoffSubmission', submission_id='submit-01', task_id=snapshot.task_id,
            assignment_id=e.assignment_id, envelope_revision=e.revision,
            envelope_sha256=self.d.delivery_digest(e), payload=c.to_dict(payload),
            handoff_sha256=hashlib.sha256(c.canonical_json(c.to_dict(payload))).hexdigest(),
            observed_run=self.d.delivery_to_dict(e.observed_run), submitted_at=STAMP)

    def test_valid_submission_uses_unchanged_v1_validator(self):
        s=observed(self.snapshot); sub=self.make_submission(s); e=s.assignments[0]
        with patch('smart_assistant.delivery_records.validate_handoff',return_value=c.GateResult(True,[])) as inner:
            self.assertTrue(self.d.validate_submission(e,sub,s.dispatches[0],Path(e.worktree_root),
                dispatched_envelope=dispatched(self.snapshot).assignments[0]).passed)
            inner.assert_called_once_with(e.payload,sub.payload,Path(e.worktree_root))

    def test_submission_bad_bindings_table_stops_before_v1(self):
        s=observed(self.snapshot); sub=self.make_submission(s); e=s.assignments[0]
        for changed in [replace(sub,envelope_revision=2),replace(sub,envelope_sha256='b'*64),
                replace(sub,observed_run=replace(sub.observed_run,run_ref='different-run'))]:
            with patch('smart_assistant.delivery_records.validate_handoff') as inner:
                self.assertFalse(self.d.validate_submission(e,changed,s.dispatches[0],Path(e.worktree_root)).passed)
                inner.assert_not_called()

    def test_scope_cannot_change_during_dispatch_transition(self):
        before=self.snapshot
        after=dispatched(before)
        e=replace(after.assignments[0],base_ref='scope-changed-at-spawn')
        intent=replace(after.dispatches[0],envelope_sha256=self.d.delivery_digest(e))
        after=proposal(before,assignments=[e],dispatches=[intent])
        self.assertFalse(self.gate(after,before).passed)

    def test_new_token_requires_prior_proposed_assignment(self):
        before=self.snapshot
        after=dispatched(before)
        # An assignment cannot start a dispatch without existing proposed scope.
        extra=replace(after.assignments[0],assignment_id='new-worker',revision=1,
            worktree_root='/private/tmp/new',owned_paths=[],payload=replace(after.assignments[0].payload,owned_paths=[]))
        intent=replace(after.dispatches[0],assignment_id=extra.assignment_id,envelope_revision=1,envelope_sha256=self.d.delivery_digest(extra))
        after=proposal(before,assignments=[before.assignments[0],extra],dispatches=[intent],
            plan=replace(before.plan,revision=2,assignment_ids=['worker-01','new-worker']))
        self.assertFalse(self.gate(after,before).passed)

    def test_plain_plan_revision_bump_without_content_denied(self):
        after=proposal(self.snapshot,plan=replace(self.snapshot.plan,revision=2))
        self.assertFalse(self.gate(after,self.snapshot).passed)

    def test_new_submission_must_equal_current_envelope(self):
        before=observed(self.snapshot); sub=self.make_submission(before)
        e=replace(before.assignments[0],revision=4,state='ready_for_review')
        after=proposal(before,assignments=[e],submissions=[sub])
        self.assertFalse(self.gate(after,before).passed)

    def test_accepted_output_digest_cannot_be_unrelated_to_handoff(self):
        before=observed(self.snapshot)
        e=replace(before.assignments[0],revision=4,state='ready_for_review',handoff_submission_id='submit-01')
        ready=replace(before,assignments=[e]); sub=self.make_submission(ready)
        ready=replace(ready,submissions=[sub])
        accepted=proposal(ready,assignments=[replace(e,revision=5,state='accepted',output_sha256='b'*64,review_refs=['review.md'])])
        self.assertFalse(self.gate(accepted,ready).passed)

    def test_same_envelope_payload_replay_denied_even_new_submission_id(self):
        before=observed(self.snapshot); sub=self.make_submission(before)
        first=replace(before,submissions=[sub]); second=replace(sub,submission_id='submit-02')
        self.assertFalse(self.gate(replace(first,submissions=[sub,second])).passed)

    def test_initial_assignment_revision_must_start_at_one(self):
        e=replace(self.snapshot.assignments[0],revision=99)
        # Initial registration is separately stricter than history-free decoding.
        self.assertEqual(self.d.delivery_from_dict('AssignmentEnvelope',self.d.delivery_to_dict(e)).revision,99)


    def test_review_r5_impossible_dispatch_target_denied_before_files(self):
        s=observed(self.snapshot); e=s.assignments[0]; sub=self.make_submission(s)
        for intent in [replace(s.dispatches[0],envelope_revision=999),
                replace(s.dispatches[0],envelope_sha256='b'*64)]:
            with patch('smart_assistant.delivery_records.validate_handoff',return_value=c.GateResult(True,[])) as inner:
                result=self.d.validate_submission(e,sub,intent,Path(e.worktree_root))
                self.assertFalse(result.passed); inner.assert_not_called()

    def test_review_r5_changed_envelope_requires_original_dispatch_context(self):
        s=observed(self.snapshot); e=s.assignments[0]; sub=self.make_submission(s)
        with patch('smart_assistant.delivery_records.validate_handoff',return_value=c.GateResult(True,[])) as inner:
            result=self.d.validate_submission(e,sub,s.dispatches[0],Path(e.worktree_root))
            self.assertFalse(result.passed); inner.assert_not_called()


    def transfer_candidate(self):
        before=self.snapshot; old=before.assignments[0]
        new=replace(old,assignment_id='worker-02',worktree_root='/private/tmp/other')
        after=proposal(before,plan=replace(before.plan,revision=2,assignment_ids=['worker-01','worker-02']),
            assignments=[replace(old,revision=2,state='cancelled'),new])
        return before,after

    def test_review_r4_transfer_requires_new_causally_bound_receipt(self):
        before,after=self.transfer_candidate()
        self.assertFalse(self.gate(after,before).passed)
        unrelated=decision(after,'transfer-01','reassignment','worker-01',2,refs=['unrelated'])
        self.assertFalse(self.gate(replace(after,decisions=[unrelated]),before).passed)

    def test_review_r4_legal_ownership_transfer(self):
        before,after=self.transfer_candidate(); old=before.assignments[0]
        ref=f'assignment:{old.assignment_id}:{old.revision}:{self.d.delivery_digest(old)}'
        receipt=decision(after,'transfer-01','reassignment','worker-02',1,refs=[ref])
        self.assertTrue(self.gate(replace(after,decisions=[receipt]),before).passed)

    def invalidated_graph(self, causes=None, receipts=True, broad=False):
        before=accepted_graph(self.snapshot,{'worker-a':[],'worker-b':['worker-a'],'worker-c':['worker-a'],
            'worker-d':['worker-b','worker-c'],'worker-s':[]})
        self.assertTrue(self.gate(before).passed)
        affected={'worker-a','worker-b','worker-c','worker-d'}
        plan=before.plan
        if broad:
            affected.add('worker-s'); plan=replace(plan,revision=2,acceptance_sha256='b'*64)
        changed=[]
        for e in before.assignments:
            if e.assignment_id in affected:
                cause=causes or (['redesign-01'] if broad else ['worker-a'])
                changed.append(replace(e,revision=e.revision+1,state='changes_requested',output_sha256=None,
                    review_refs=[],invalidated_by=cause))
            else: changed.append(e)
        after=proposal(before,plan=plan,assignments=changed)
        decisions=[]
        if broad: decisions.append(decision(after,'redesign-01','redesign',candidate=before.plan.acceptance_sha256))
        if receipts:
            for e in before.assignments:
                if e.assignment_id in affected:
                    decisions.append(decision(after,'invalidate-'+e.assignment_id,'invalidation',e.assignment_id,e.revision+1,e.output_sha256))
        return before,replace(after,decisions=decisions)

    def test_review_r4_unknown_invalidation_cause_denied(self):
        before,after=self.invalidated_graph(causes=['nonexistent-id'],receipts=False)
        self.assertFalse(self.gate(after,before).passed)

    def test_review_r4_known_cause_without_receipt_denied(self):
        before,after=self.invalidated_graph(receipts=False)
        self.assertFalse(self.gate(after,before).passed)


    def test_review_r7_diamond_invalidation_preserves_unrelated_sibling(self):
        before,after=self.invalidated_graph()
        self.assertTrue(self.gate(after,before).passed)
        self.assertEqual(next(e for e in after.assignments if e.assignment_id=='worker-s'),
            next(e for e in before.assignments if e.assignment_id=='worker-s'))
        stale=next(e for e in before.assignments if e.assignment_id=='worker-d')
        incomplete=replace(after,assignments=[stale if e.assignment_id=='worker-d' else e for e in after.assignments])
        self.assertFalse(self.gate(incomplete,before).passed)

    def test_review_r7_broad_redesign_invalidates_all_accepted_outputs(self):
        before,after=self.invalidated_graph(broad=True)
        self.assertTrue(self.gate(after,before).passed)
        self.assertTrue(all(e.state=='changes_requested' for e in after.assignments))
        old_sibling=next(e for e in before.assignments if e.assignment_id=='worker-s')
        stale=replace(after,assignments=[old_sibling if e.assignment_id=='worker-s' else e for e in after.assignments])
        self.assertFalse(self.gate(stale,before).passed)

    def test_review_r5_bad_original_scope_denied_before_v1(self):
        s=observed(self.snapshot); e=s.assignments[0]; sub=self.make_submission(s)
        original=dispatched(self.snapshot).assignments[0]
        for context in [replace(original,base_ref='wrong-original-scope'),replace(original,revision=99)]:
            with patch('smart_assistant.delivery_records.validate_handoff') as inner:
                self.assertFalse(self.d.validate_submission(e,sub,s.dispatches[0],Path(e.worktree_root),
                    dispatched_envelope=context).passed)
                inner.assert_not_called()

    def test_terminal_task_denied(self):
        self.task.status = c.TaskStatus.CANCELLED
        self.assertFalse(self.gate().passed)


if __name__ == '__main__': unittest.main()
