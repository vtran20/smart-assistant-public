"""Synthetic local evidence tests; no native/runtime authenticity claim."""
import copy
from dataclasses import asdict, replace
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from smart_assistant import delivery_evidence as ev
from smart_assistant.contracts import (Artifact, CheckMethod, CheckOutcome, CheckReceipt,
    Criterion, CycleEvidence, Limits, RequestEnvelope, ReviewReceipt, Selection,
    TaskPhase, TaskRecord, TaskStatus, ValidationError, canonical_json)
from smart_assistant.delivery_records import (DeliveryPolicy, DeliveryRegistration,
    DeliveryPlan, DeliverySnapshot, ObservedRun, DispatchIntent, delivery_digest,
    delivery_to_dict, request_digest)
from smart_assistant.quality import snapshot, acceptance_snapshot
ZERO='0'*64
BASELINE='b'*64
STAMP='2026-11-03T12:00:00Z'
def sha(data): return hashlib.sha256(data).hexdigest()
class DeliveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name,data in [('product.txt','fixed'),('design.md','approved'),('v1.log','tests pass')]:
            (self.root/name).write_text(data)
        criteria=[Criterion('works','works as expected','unit')]
        candidate=snapshot(self.root,[Artifact('product','product.txt',ZERO)])
        acceptance=acceptance_snapshot(criteria,self.root/'design.md')
        self.task=TaskRecord(1,'task',1,RequestEnvelope(1,'request','repair','project',[],None),
            TaskStatus.RUNNING,TaskPhase.TESTING,None,[],criteria,Selection(1,[],[]),Limits(),[],[],
            [CycleEvidence(1,'design.md',candidate,acceptance,ReviewReceipt('reviewer:b','implementer:a',
                candidate.candidate_id,acceptance.acceptance_id,STAMP,[]),[],[CheckReceipt('unit',['works'],
                candidate.candidate_id,acceptance.acceptance_id,CheckMethod.COMMAND,
                'arbitrary unsafe command never execute',None,{},CheckOutcome.PASS,'v1.log',STAMP)])],[], '',str(self.root))
        policy=DeliveryPolicy('1.0','policy','1.0','bug','source',ZERO,True,True,['unit'],2,3)
        plan=DeliveryPlan('1.0','task',1,request_digest(self.task.request),delivery_digest(policy),'root',
            acceptance.design_sha256,acceptance.acceptance_id,'repair',['works'],[],2,3,ZERO,'')
        registration=DeliveryRegistration('1.0','task',request_digest(self.task.request),'policy',delivery_digest(policy),STAMP)
        runs=[ObservedRun('1.0','host','implementer:a','run-a','token-a','2026-11-03T09:00:00Z','host:run-a'),
            ObservedRun('1.0','host','reviewer:b','run-b','token-b',STAMP,'host:run-b')]
        dispatches=[DispatchIntent('1.0',r.dispatch_token,'assignment-'+str(i),1,ZERO,r.observed_at,
            'terminated',r,'termination') for i,r in enumerate(runs)]
        self.delivery=DeliverySnapshot('1.0','task',1,None,registration,policy,plan,[],dispatches,[],[])
        observations=[ev.RunObservation('obs-'+str(i),r,self.receipt('run-'+str(i)+'.json',delivery_to_dict(r))) for i,r in enumerate(runs)]
        entries=[self.entry('before',BASELINE,'fail','2026-11-03T10:00:00Z'),
            self.entry('after',candidate.candidate_id,'pass','2026-11-03T11:00:00Z'),
            self.entry('test',candidate.candidate_id,'pass','2026-11-03T11:30:00Z')]
        case=ev.VerificationCase('case-one',['works'],'scenario-one',True,'required regression','review-one',
            'expected behavior',['unit'],'pass',['before'],['after'],['test'],None,None)
        review=ev.SemanticReview('review-one','obs-0','obs-1',candidate.candidate_id,acceptance.acceptance_id,
            ['before','after','test'],['case-one'],ZERO,STAMP,True,'Reported symptom matches before; final regression supports fix',[],ev.HashedReceipt('review.json',ZERO))
        self.bundle=ev.EvidenceBundle('1.0','task',1,delivery_digest(plan),candidate.candidate_id,
            acceptance.acceptance_id,BASELINE,[case],entries,observations,[review]); self.seal()
    def receipt(self,path,value):
        data=value if type(value) is bytes else canonical_json(value)
        (self.root/path).write_bytes(data); return ev.HashedReceipt(path,sha(data))
    def entry(self,kind,candidate,outcome,stamp):
        return ev.EvidenceEntry(kind,self.receipt(kind+'.log',(kind+' observed '+outcome).encode()),
            ['works'],'case-one','scenario-one',kind,'unit',stamp,'obs-0','unittest capture',ZERO,candidate,ZERO,
            candidate,'expected behavior','original defect' if kind=='before' else 'expected behavior',outcome,
            'arbitrary unsafe command never execute',1 if outcome=='fail' else 0,None,'internal','review-one')
    def seal(self):
        reviews=[]
        for review in self.bundle.reviews:
            selected_entries = [e for e in sorted(self.bundle.entries, key=lambda e:e.id)
                                if e.id in review.entry_ids]
            observation_ids = {review.implementer_observation_id, review.reviewer_observation_id}
            observation_ids.update(e.observation_id for e in selected_entries)
            payload = {
                'plan_sha256': delivery_digest(self.delivery.plan),
                'context_sha256': self.delivery.plan.context_sha256,
                'entries': [asdict(e) for e in selected_entries],
                'cases': [asdict(c) for c in sorted(self.bundle.cases, key=lambda c:c.id)
                          if c.id in review.case_ids],
                'observations': [asdict(o) for o in sorted(self.bundle.observations, key=lambda o:o.id)
                                 if o.id in observation_ids],
            }
            review=replace(review,evidence_sha256=sha(canonical_json(payload)))
            raw=asdict(review); raw.pop('receipt'); reviews.append(replace(review,receipt=self.receipt(review.receipt.path,raw)))
        self.bundle=replace(self.bundle,reviews=reviews)
    def change_entry(self,index=0,**changes):
        entries=list(self.bundle.entries); entries[index]=replace(entries[index],**changes)
        self.bundle=replace(self.bundle,entries=entries)
    def change_case(self,**changes): self.bundle=replace(self.bundle,cases=[replace(self.bundle.cases[0],**changes)])
    def gate(self): return ev.validate_delivery_evidence(self.task,self.delivery,self.bundle,self.root)
    def deny(self,code=None):
        result=self.gate(); self.assertFalse(result.passed,result)
        if code: self.assertIn(code,[e.code for e in result.errors],result.errors)
    def test_valid_bug_codec_digest_and_no_mutation(self):
        original=copy.deepcopy((self.task,self.delivery,self.bundle))
        self.assertTrue(self.gate().passed,self.gate().errors)
        wire=ev.evidence_to_dict(self.bundle)
        self.assertEqual(ev.evidence_from_dict(wire),self.bundle)
        self.assertEqual(ev.evidence_digest(self.bundle),sha(canonical_json(wire)))
        self.assertEqual(original,(self.task,self.delivery,self.bundle))
    def test_strict_decode(self):
        wire=ev.evidence_to_dict(self.bundle)
        for field,value in [('delivery_revision',True),('delivery_revision',0),('candidate_id','A'*64),
                ('task_id','BAD'),('schema_version','2.0'),('entries',{})]:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError): ev.evidence_from_dict(dict(wire,**{field:value}))
        with self.assertRaises(ValidationError): ev.evidence_from_dict(dict(wire,extra=True))
        wire.pop('task_id')
        with self.assertRaises(ValidationError): ev.evidence_from_dict(wire)

    def test_dates_paths_duplicate_ids_command_types_rejected(self):
        for changes in [dict(captured_at='2026-02-30T00:00:00Z'),dict(captured_at='2026-11-03T10:00:00+00:00'),
                dict(exit_code=True),dict(exit_code=None),dict(requirement_ids=['works','works']),
                dict(receipt=ev.HashedReceipt('../escape',ZERO)),dict(command=None,observation=None)]:
            with self.subTest(changes=changes):
                bad=replace(self.bundle,entries=[replace(self.bundle.entries[0],**changes)]+self.bundle.entries[1:])
                with self.assertRaises(ValidationError): ev.evidence_to_dict(bad)
        with self.assertRaises(ValidationError): ev.evidence_to_dict(replace(self.bundle,entries=self.bundle.entries*2))
    def test_unknown_requirement_wrong_case_scenario_expected_deny(self):
        original=self.bundle
        for changes in [dict(requirement_ids=['unknown']),dict(case_id='other'),dict(scenario_id='other'),dict(expected_result='other')]:
            self.bundle=original; self.change_entry(**changes); self.seal(); self.deny()
    def test_stale_bindings_deny(self):
        original=self.bundle
        for changes in [dict(task_id='other'),dict(delivery_revision=2),dict(plan_sha256=ZERO),
                dict(candidate_id=ZERO),dict(acceptance_id=ZERO)]:
            self.bundle=replace(original,**changes); self.deny()
    def test_current_product_design_mutation_deny(self):
        for filename in ['product.txt','design.md']:
            path=self.root/filename; original=path.read_bytes(); path.write_bytes(b'changed')
            self.deny(); path.write_bytes(original)
    def test_plan_requirement_design_acceptance_mismatch_deny(self):
        original=self.delivery
        for changes in [dict(requirement_ids=['other']),dict(design_sha256=ZERO),dict(acceptance_sha256=ZERO)]:
            self.delivery=replace(original,plan=replace(original.plan,**changes))
            self.bundle=replace(self.bundle,plan_sha256=delivery_digest(self.delivery.plan)); self.deny()
    def test_missing_tampered_symlink_fifo_hardlink_product_deny(self):
        path=self.root/'before.log'; path.unlink(); self.deny()
        path.write_bytes(b'tamper'); self.deny(); path.unlink()
        path.symlink_to(self.root/'product.txt'); self.deny(); path.unlink()
        os.mkfifo(path); self.deny(); path.unlink()
        os.link(self.root/'product.txt',path)
        self.change_entry(receipt=ev.HashedReceipt('before.log',sha(path.read_bytes())))
        self.seal(); self.deny('evidence_as_artifact')
    def test_nested_symlink_and_root_mismatch_deny(self):
        (self.root/'outside').symlink_to(self.root,target_is_directory=True)
        self.change_entry(receipt=ev.HashedReceipt('outside/before.log',self.bundle.entries[0].receipt.sha256))
        self.seal(); self.deny()
        self.assertFalse(ev.validate_delivery_evidence(self.task,self.delivery,self.bundle,self.root/'outside').passed)
    def test_malformed_duplicate_unknown_nonfinite_observation_json_deny(self):
        for bad in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{"extra":true}',b'not json']:
            receipt=self.receipt('run-0.json',bad)
            observations=[replace(self.bundle.observations[0],receipt=receipt),self.bundle.observations[1]]
            self.bundle=replace(self.bundle,observations=observations); self.deny()
    def test_review_file_tamper_deny(self):
        (self.root/'review.json').write_text('different review'); self.deny()
    def test_same_id_metadata_change_requires_new_semantic_review(self):
        original=self.bundle
        self.change_case(applicability_rationale='changed scope'); self.deny('stale_semantic_review')
        self.bundle=original; self.change_entry(observed_result='different symptom'); self.deny('stale_semantic_review')
    def test_required_statuses_and_optional_not_fill_gap(self):
        original=self.bundle
        for status in ['fail','blocked','not_run','not_applicable']:
            self.bundle=original; self.change_case(status=status); self.seal(); self.deny()
        self.bundle=original; self.change_case(required=False); self.seal(); self.deny('missing_criterion_coverage')
    def test_missing_before_after_regression_deny(self):
        original=self.bundle
        for field in ['before_ids','after_ids','test_ids']:
            self.bundle=original; self.change_case(**{field:[]}); self.seal(); self.deny()
    def test_unit_cannot_fill_pos_levels_or_omit_policy_level(self):
        self.change_case(required_levels=['unit','pos']); self.seal(); self.deny()
        self.change_case(required_levels=['unit']); self.seal()
        self.delivery=replace(self.delivery,policy=replace(self.delivery.policy,required_verification_levels=['pos']))
        self.deny()
    def test_unexplained_input_environment_diff_deny_reviewed_pass(self):
        original=self.bundle
        for field in ['input_sha256','environment_sha256']:
            self.bundle=original; self.change_entry(1,**{field:'c'*64}); self.seal(); self.deny('reproduction_mismatch')
            self.change_case(differences='intentional isolated config; reviewer accepted equivalence',differences_review_id='review-one')
            self.seal(); self.assertTrue(self.gate().passed,self.gate().errors)
    def test_before_wrong_candidate_outcome_late_capture_deny(self):
        original=self.bundle
        for changes in [dict(candidate_id=self.bundle.candidate_id),dict(outcome='pass',exit_code=0),dict(captured_at='2026-11-03T11:50:00Z')]:
            self.bundle=original; self.change_entry(**changes); self.seal(); self.deny()
    def test_baseline_distinct_required_after_final_binding(self):
        original=self.bundle
        for baseline in [None,self.bundle.candidate_id]:
            self.bundle=replace(original,baseline_candidate_id=baseline); self.deny()
        self.bundle=original; self.change_entry(1,candidate_id=BASELINE); self.seal(); self.deny()
    def test_same_observed_context_different_labels_not_independent(self):
        original=self.bundle.observations[1]
        run=replace(original.run,observation_ref=self.bundle.observations[0].run.observation_ref)
        obs=replace(original,run=run,receipt=self.receipt('run-1.json',delivery_to_dict(run)))
        dispatches=list(self.delivery.dispatches); dispatches[1]=replace(dispatches[1],observed_run=run)
        self.delivery=replace(self.delivery,dispatches=dispatches)
        self.bundle=replace(self.bundle,observations=[self.bundle.observations[0],obs]); self.seal(); self.deny('nonindependent_review')
    def test_missing_host_observation_wrong_actor_deny(self):
        original=self.delivery; self.delivery=replace(original,dispatches=[]); self.deny('unobserved_run')
        self.delivery=original; self.task.cycles[-1].review.reviewer_ref='different reviewer'; self.deny('nonindependent_review')
    def test_unapproved_unresolved_stale_review_deny(self):
        original=self.bundle
        for changes in [dict(approved=False),dict(unresolved_findings=['finding']),dict(candidate_id=ZERO),
                dict(acceptance_id=ZERO),dict(entry_ids=['after','test'])]:
            self.bundle=replace(original,reviews=[replace(original.reviews[0],**changes)]); self.seal(); self.deny()
    def test_task_blockers_and_failed_v1_checks_deny(self):
        self.task.blockers=['POS unavailable']; self.deny('task_blocked'); self.task.blockers=[]
        self.task.cycles[-1].checks[0].outcome=CheckOutcome.FAIL; self.deny()
    def test_nonbug_no_baseline_and_after_regression_pass(self):
        self.delivery=replace(self.delivery,policy=replace(self.delivery.policy,workflow_kind='feature',reproduction_required=False))
        self.bundle=replace(self.bundle,baseline_candidate_id=None,entries=self.bundle.entries[1:]); self.change_case(before_ids=[])
        self.bundle=replace(self.bundle,reviews=[replace(self.bundle.reviews[0],entry_ids=['after','test'])]); self.seal()
        self.assertTrue(self.gate().passed,self.gate().errors)
        self.bundle=replace(self.bundle,baseline_candidate_id=BASELINE); self.deny()
    def test_optional_not_applicable_requires_independent_review(self):
        optional=replace(self.bundle.cases[0],id='optional-case',required=False,status='not_applicable',
            before_ids=[],after_ids=[],test_ids=[],applicability_review_id=None)
        self.bundle=replace(self.bundle,cases=self.bundle.cases+[optional]); self.seal(); self.deny()
    def test_wrong_kind_reuse_and_orphans_deny(self):
        self.change_case(after_ids=['test']); self.seal(); self.deny()

    def test_oversized_raw_receipt_is_bounded_before_hashing(self):
        with (self.root/'before.log').open('wb') as handle:
            handle.truncate(ev.MAX_EVIDENCE_BYTES+1)
        self.deny('evidence_too_large')
    def test_duplicate_raw_entry_hardlinks_rejected(self):
        (self.root/'after.log').unlink(); os.link(self.root/'test.log',self.root/'after.log')
        self.change_entry(1,receipt=ev.HashedReceipt('after.log',sha((self.root/'after.log').read_bytes())))
        self.seal(); self.deny('duplicate_evidence')
    def test_missing_semantic_review_and_observation_references_deny(self):
        original=self.bundle
        self.bundle=replace(original,reviews=[]); self.deny('missing_semantic_review')
        self.bundle=original; self.change_entry(observation_id='unknown'); self.seal(); self.deny('unobserved_run')
    def test_final_pass_command_cannot_have_nonzero_exit(self):
        self.change_entry(1,exit_code=9); self.deny('invalid_command')
    def test_baseline_and_final_builds_consistent(self):
        self.change_entry(1,build_sha256=ZERO); self.seal(); self.deny('reproduction_mismatch')
    def test_invalid_task_delivery_and_bundle_objects_fail_closed(self):
        for task,delivery,bundle in [(None,self.delivery,self.bundle),(self.task,None,self.bundle),(self.task,self.delivery,{})]:
            self.assertFalse(ev.validate_delivery_evidence(task,delivery,bundle,self.root).passed)
    def test_second_criterion_cannot_disappear_from_required_coverage(self):
        self.task.criteria.append(Criterion('second','second requirement','unit'))
        acceptance=acceptance_snapshot(self.task.criteria,self.root/'design.md')
        self.task.cycles[-1].acceptance=acceptance
        self.task.cycles[-1].review.acceptance_id=acceptance.acceptance_id
        check=self.task.cycles[-1].checks[0]; check.acceptance_id=acceptance.acceptance_id
        check.criterion_ids.append('second')
        plan=replace(self.delivery.plan,requirement_ids=['works','second'],acceptance_sha256=acceptance.acceptance_id)
        self.delivery=replace(self.delivery,plan=plan)
        self.bundle=replace(self.bundle,plan_sha256=delivery_digest(plan),acceptance_id=acceptance.acceptance_id,
            reviews=[replace(self.bundle.reviews[0],acceptance_id=acceptance.acceptance_id)])
        self.seal(); self.deny('missing_criterion_coverage')
    def test_optional_nonapplicable_with_review_does_not_remove_required_coverage(self):
        optional=replace(self.bundle.cases[0],id='optional-case',required=False,status='not_applicable',
            before_ids=[],after_ids=[],test_ids=[],applicability_review_id='review-one')
        self.bundle=replace(self.bundle,cases=self.bundle.cases+[optional],reviews=[replace(self.bundle.reviews[0],case_ids=['case-one','optional-case'])])
        self.seal(); self.assertTrue(self.gate().passed,self.gate().errors)
    def test_pass_is_not_proof_that_command_was_executed(self):
        marker=self.root/'SHOULD_NOT_EXIST'
        self.change_entry(1,command='touch '+str(marker)); self.seal()
        self.assertTrue(self.gate().passed,self.gate().errors); self.assertFalse(marker.exists())

    def replace_observation_without_review(self, index):
        original = self.bundle.observations[index]
        run = replace(original.run, run_ref=original.run.run_ref + '-replacement',
                      dispatch_token=original.run.dispatch_token + '-replacement',
                      observation_ref=original.run.observation_ref + '-replacement')
        replacement = replace(original, run=run,
            receipt=self.receipt(original.receipt.path, delivery_to_dict(run)))
        observations = list(self.bundle.observations)
        observations[index] = replacement
        dispatch = DispatchIntent('1.0', run.dispatch_token, 'assignment-replacement', 1,
            ZERO, run.observed_at, 'terminated', run, 'termination')
        self.delivery = replace(self.delivery, dispatches=self.delivery.dispatches + [dispatch])
        self.bundle = replace(self.bundle, observations=observations)

    def test_capture_observation_replacement_requires_new_semantic_review(self):
        source = self.bundle.observations[0]
        capture = replace(source, id='capture-observation',
            receipt=self.receipt('capture-run.json', delivery_to_dict(source.run)))
        self.bundle = replace(self.bundle, observations=self.bundle.observations + [capture])
        self.change_entry(observation_id=capture.id)
        self.seal()
        self.assertTrue(self.gate().passed, self.gate().errors)
        original_review = copy.deepcopy(self.bundle.reviews[0])
        original_receipt = (self.root / 'review.json').read_bytes()
        self.replace_observation_without_review(2)
        self.assertEqual(self.bundle.reviews[0], original_review)
        self.assertEqual((self.root / 'review.json').read_bytes(), original_receipt)
        self.deny('stale_semantic_review')

    def test_implementer_observation_replacement_requires_new_semantic_review(self):
        self.replace_observation_without_review(0)
        self.deny('stale_semantic_review')

    def test_reviewer_observation_replacement_requires_new_semantic_review(self):
        self.replace_observation_without_review(1)
        self.deny('stale_semantic_review')

    def test_plan_and_context_rebinding_requires_new_semantic_review(self):
        original = self.delivery
        for changes in [dict(routing_rationale='updated routing'), dict(context_sha256='c' * 64)]:
            self.delivery = replace(original, plan=replace(original.plan, **changes))
            self.bundle = replace(self.bundle, plan_sha256=delivery_digest(self.delivery.plan))
            self.deny('stale_semantic_review')

    def test_v1_review_cannot_predate_final_evidence(self):
        self.task.cycles[-1].review.observed_at = '2026-11-03T10:30:00Z'
        self.deny('stale_semantic_review')

    def test_reviewer_can_capture_later_in_same_run_before_review_completion(self):
        self.change_entry(2, observation_id='obs-1', captured_at='2026-11-03T12:05:00Z')
        self.task.cycles[-1].review.observed_at = '2026-11-03T12:10:00Z'
        self.bundle = replace(self.bundle, reviews=[replace(self.bundle.reviews[0],
            reviewed_at='2026-11-03T12:10:00Z')])
        self.seal()
        self.assertTrue(self.gate().passed, self.gate().errors)

    def test_review_completion_before_observed_run_is_invalid(self):
        stamp = '2026-11-03T11:45:00Z'
        self.task.cycles[-1].review.observed_at = stamp
        self.bundle = replace(self.bundle, reviews=[replace(self.bundle.reviews[0], reviewed_at=stamp)])
        self.seal()
        self.deny('stale_semantic_review')

    def test_semantic_completion_must_match_actual_v1_review_time(self):
        self.bundle = replace(self.bundle, reviews=[replace(self.bundle.reviews[0],
            reviewed_at='2026-11-03T12:10:00Z')])
        self.seal()
        self.deny('stale_semantic_review')

    def test_review_completion_is_strict_utc_and_in_hashed_receipt(self):
        review = self.bundle.reviews[0]
        with self.assertRaises(ValidationError):
            ev.evidence_to_dict(replace(self.bundle, reviews=[replace(review,
                reviewed_at='2026-02-30T12:00:00Z')]))
        self.task.cycles[-1].review.observed_at = '2026-11-03T12:10:00Z'
        self.bundle = replace(self.bundle, reviews=[replace(review, reviewed_at='2026-11-03T12:10:00Z')])
        self.deny('invalid_receipt')

    def test_observation_receipt_path_change_requires_new_semantic_review(self):
        observation = self.bundle.observations[0]
        copied = self.receipt('same-run-different-path.json',
            (self.root / observation.receipt.path).read_bytes())
        self.assertEqual(copied.sha256, observation.receipt.sha256)
        self.bundle = replace(self.bundle, observations=[replace(observation, receipt=copied),
            self.bundle.observations[1]])
        self.deny('stale_semantic_review')
