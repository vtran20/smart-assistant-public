"""P16 isolated policy enforcement and persistence; synthetic host fixtures only."""
from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from smart_assistant.contracts import GateResult, TaskStatus, ValidationError, RevisionConflict, to_dict
from smart_assistant.state import TaskStore
from tests.test_state import record
from tests.test_delivery_records import fixture
from tests import test_cli as cli_tests


def completing(task):
    return replace(task, status=TaskStatus.COMPLETED)


class MandatoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.calls=[]
        self.store=TaskStore(self.root,lambda task:self.calls.append(task) or GateResult(True,[]))

    def denied(self,task,code):
        with self.assertRaises(ValidationError) as raised:
            self.store.update(completing(task),task.revision)
        self.assertIn(code,[e.code for e in raised.exception.errors])
        self.assertEqual(self.store.read(task.id),task)
        self.assertFalse(self.calls,'Mandatory denial must happen before alternate callback')

    def test_alternate_callback_cannot_complete_reserved_task_without_registration(self):
        task,snapshot=fixture(str(self.root/'worktree')); task.status=TaskStatus.VERIFYING
        saved=self.store.create(task)
        self.denied(saved,'missing_registration')

    def test_malformed_reserved_policy_fails_before_callback(self):
        task=record('verifying'); task.request.source_refs.append('smart-assistant:delivery-policy:garbage')
        self.denied(self.store.create(task),'missing_registration')

    def test_existing_delivery_directory_without_marker_fails_closed(self):
        saved=self.store.create(record('verifying'))
        (self.root/'delivery'/saved.id).mkdir(parents=True)
        self.denied(saved,'missing_registration')

    def test_legacy_alternate_callback_stays_supported(self):
        saved=self.store.create(record('verifying'))
        self.assertIs(self.store.update(completing(saved),saved.revision).status,TaskStatus.COMPLETED)
        self.assertEqual(len(self.calls),1)

    def test_f01_legacy_diagnostics_preserve_disk_and_completion_policy(self):
        from smart_assistant.delivery_store import DeliveryStore
        from smart_assistant.delivery_gate import DeliveryEvidenceStore
        actions=('delivery_read','evidence_read','evidence_check','update','recover')
        for action in actions:
            with self.subTest(action=action), TemporaryDirectory() as tmp:
                root=Path(tmp).resolve(); store=TaskStore(root,lambda task:GateResult(True,[]))
                saved=store.create(record('verifying'))
                before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                directories={str(p.relative_to(root)) for p in root.rglob('*') if p.is_dir()}
                delivery=DeliveryStore(root); evidence=DeliveryEvidenceStore(root)
                if action=='evidence_check':
                    result=evidence.check(saved.id)
                    self.assertFalse(result.passed)
                    self.assertIn('missing_registration',[e.code for e in result.errors])
                else:
                    with self.assertRaises(ValidationError):
                        if action=='delivery_read':delivery.read(saved.id)
                        elif action=='evidence_read':evidence.read(saved.id)
                        elif action=='recover':delivery.recover(saved.id,'operation-unknown','reject')
                        else:delivery.update(fixture(str(root/'tree'))[1],1,1)
                self.assertEqual({str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()},before)
                self.assertEqual({str(p.relative_to(root)) for p in root.rglob('*') if p.is_dir()},directories)
                self.assertIs(store.update(completing(saved),saved.revision).status,TaskStatus.COMPLETED)

    def test_f01_rejected_api_legacy_registration_still_allows_legacy_completion(self):
        from smart_assistant.delivery_records import request_digest
        from smart_assistant.delivery_store import DeliveryStore
        saved=self.store.create(record('running')); initial=fixture(str(self.root/'tree'))[1]
        digest=request_digest(saved.request)
        initial=replace(initial,registration=replace(initial.registration,request_sha256=digest),
            plan=replace(initial.plan,request_sha256=digest))
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises(ValidationError) as caught:DeliveryStore(self.root).register(initial,1)
        self.assertIn('policy_mismatch',[e.code for e in caught.exception.errors])
        self.assertEqual({str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)
        self.assertFalse((self.root/'delivery').exists())
        verifying=self.store.update(replace(saved,status=TaskStatus.VERIFYING),1)
        self.assertIs(self.store.update(completing(verifying),verifying.revision).status,TaskStatus.COMPLETED)

    def test_f01_inspection_preserves_legacy_task_beside_registered_sibling(self):
        from smart_assistant.delivery_store import DeliveryStore
        from smart_assistant.delivery_gate import DeliveryEvidenceStore
        sibling,initial=fixture(str(self.root/'tree')); self.store.create(sibling)
        DeliveryStore(self.root).register(initial,1)
        saved=self.store.create(replace(record('verifying'),id='legacy-task'))
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaises(ValidationError):DeliveryStore(self.root).read(saved.id)
        result=DeliveryEvidenceStore(self.root).check(saved.id)
        self.assertFalse(result.passed)
        self.assertEqual({str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)
        self.assertFalse((self.root/'delivery/legacy-task').exists())
        self.assertIs(self.store.update(completing(saved),saved.revision).status,TaskStatus.COMPLETED)

    def test_shared_store_rejects_rewriting_prior_cycles(self):
        saved=self.store.create(record('running')); changed=deepcopy(saved)
        self.assertTrue(changed.cycles)
        changed.cycles[0].design_ref='rewritten.md'
        with self.assertRaises(ValidationError) as raised:self.store.update(changed,saved.revision)
        self.assertIn('history_changed',[e.code for e in raised.exception.errors])
        self.assertEqual(self.store.read(saved.id),saved)

    def test_shared_store_rejects_nonconsecutive_cycle_append(self):
        saved=self.store.create(record('running')); changed=deepcopy(saved)
        changed.cycles.append(replace(changed.cycles[-1],cycle_number=3))
        with self.assertRaises(ValidationError) as raised:self.store.update(changed,saved.revision)
        self.assertIn('invalid_cycle_sequence',[e.code for e in raised.exception.errors])

    def test_create_rejects_nonconsecutive_cycles(self):
        task=record('running'); task.cycles[0].cycle_number=2
        with self.assertRaises(ValidationError) as raised:self.store.create(task)
        self.assertIn('invalid_cycle_sequence',[e.code for e in raised.exception.errors])

    def test_resume_failed_preserves_cycle_history(self):
        saved=self.store.create(record('failed')); changed=deepcopy(saved)
        changed.status=TaskStatus.RUNNING; changed.cycles=[]
        with self.assertRaises(ValidationError) as raised:self.store.resume_failed(changed,saved.revision)
        self.assertIn('history_changed',[e.code for e in raised.exception.errors])


class DeliveryCLITests(unittest.TestCase):
    """Actual subprocess CLI with synthetic quality fixtures."""
    setUp=cli_tests.CLITests.setUp
    save=cli_tests.CLITests.save
    run_cli=cli_tests.CLITests.run_cli
    response=cli_tests.CLITests.response
    create=cli_tests.CLITests.create
    update=cli_tests.CLITests.update
    stored_bytes=cli_tests.CLITests.stored_bytes
    verified_cycle=cli_tests.CLITests.verified_cycle
    def test_malformed_delivery_policy_cannot_complete_either_cli_path(self):
        self.wire['request']['source_refs'].append('smart-assistant:delivery-policy:garbage')
        saved=self.create('verifying',cycles=[self.verified_cycle()])
        before=self.stored_bytes()
        result=self.response(4,'task','complete','task-01','--expected-revision','1','--state-dir',self.state)
        self.assertIn('missing_registration',[e['code'] for e in result['errors']])
        self.assertEqual(self.stored_bytes(),before)
        saved['status']='completed'; self.save(saved)
        result=self.response(4,'task','update','--record',self.record_path,'--expected-revision','1','--state-dir',self.state)
        self.assertIn('missing_registration',[e['code'] for e in result['errors']])
        self.assertEqual(self.stored_bytes(),before)


    def test_f01_actual_cli_legacy_inspection_and_rejected_registration_preserve_policy(self):
        from smart_assistant.delivery_records import delivery_to_dict, request_digest
        actions=('show','evidence_show','check','register')
        for action in actions:
            with self.subTest(action=action), TemporaryDirectory() as tmp:
                self.state=Path(tmp).resolve()/'state'
                saved=self.create('running' if action=='register' else 'verifying',cycles=[self.verified_cycle()])
                before={str(p.relative_to(self.state)):p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
                directories={str(p.relative_to(self.state)) for p in self.state.rglob('*') if p.is_dir()}
                if action=='register':
                    snapshot=fixture(str(self.root/'tree'))[1]
                    digest=request_digest(TaskStore(self.state).read(saved['id']).request)
                    snapshot=replace(snapshot,registration=replace(snapshot.registration,request_sha256=digest),
                        plan=replace(snapshot.plan,request_sha256=digest))
                    source=self.root/'legacy-delivery.json'; source.write_text(json.dumps(delivery_to_dict(snapshot)))
                    result=self.response(2,'delivery','create','--record',source,'--expected-task-revision','1','--state-dir',self.state)
                    self.assertIn('policy_mismatch',[e['code'] for e in result['errors']])
                elif action=='evidence_show':
                    self.response(2,'delivery','evidence','show',saved['id'],'--state-dir',self.state)
                else:
                    self.response(4 if action=='check' else 2,'delivery',action,saved['id'],'--state-dir',self.state)
                self.assertEqual({str(p.relative_to(self.state)):p.read_bytes() for p in self.state.rglob('*') if p.is_file()},before)
                self.assertEqual({str(p.relative_to(self.state)) for p in self.state.rglob('*') if p.is_dir()},directories)
                if action=='register':
                    saved['status']='verifying'; saved=self.update(saved,1)['data']
                completed=self.response(0,'task','complete',saved['id'],'--expected-revision',saved['revision'],'--state-dir',self.state)
                self.assertEqual(completed['data']['status'],'completed')

    def test_f01_actual_cli_unknown_inspection_creates_no_delivery_subtree(self):
        self.create('verifying',cycles=[self.verified_cycle()]); before=self.stored_bytes()
        for args,code in ((('show','unknown-task'),2),(('evidence','show','unknown-task'),2),(('check','unknown-task'),4)):
            with self.subTest(args=args):
                self.response(code,'delivery',*args,'--state-dir',self.state)
                self.assertFalse((self.state/'delivery').exists())
                self.assertEqual(self.stored_bytes(),before)


class EvidenceStoreTests(unittest.TestCase):
    def test_evidence_store_api_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('smart_assistant.delivery_gate'))
        module=importlib.import_module('smart_assistant.delivery_gate')
        for name in ('read','save','check','recover'):
            self.assertTrue(callable(getattr(module.DeliveryEvidenceStore,name,None)),name)


def combined_fixture(test):
    """Genuine helper persistence, entirely synthetic observations/review evidence."""
    import hashlib
    from smart_assistant import contracts as c
    from smart_assistant import delivery_records as d
    from smart_assistant.delivery_store import DeliveryStore
    from smart_assistant.delivery_evidence import evidence_to_dict
    from tests.test_delivery_evidence import DeliveryEvidenceTests
    data=DeliveryEvidenceTests('test_valid_bug_codec_digest_and_no_mutation'); data.setUp()
    test.addCleanup(data.doCleanups)
    data.root=data.root.resolve()
    state=data.root/'state'; state.mkdir()
    task=replace(data.task,status=TaskStatus.RUNNING,artifact_root=str(data.root))
    task.request.source_refs.append(d.policy_source_ref(data.delivery.policy))
    plan=replace(data.delivery.plan,request_sha256=d.request_digest(task.request),
        assignment_ids=['assignment-0','assignment-1'])
    registration=replace(data.delivery.registration,request_sha256=d.request_digest(task.request))
    runs=[o.run for o in data.bundle.observations]
    envelopes=[]
    for i in range(2):
        payload=c.from_dict('TaskAssignment',json.loads((Path(__file__).resolve().parents[1]/'examples/contracts/TaskAssignment.json').read_text()))
        payload=replace(payload,task_id=task.id,criteria=task.criteria,owned_paths=['product.txt'])
        selected=payload.selection.agents[0]
        envelopes.append(d.AssignmentEnvelope('1.0',f'assignment-{i}',1,task.id,None,True,payload,
            payload.role_id,selected.version,selected.deployed_sha256,'synthetic-baseline',f'worker-{i}',
            str(data.root/f'worker-{i}'),['product.txt'],[],'proposed',None,None,None,None,[],[]))
    current=replace(data.delivery,registration=registration,plan=plan,assignments=envelopes,dispatches=[])
    task=TaskStore(state).create(task); store=DeliveryStore(state); current=store.register(current,task.revision)
    task=TaskStore(state).update(replace(task,status=TaskStatus.VERIFYING),task.revision)
    def update(**changes):
        nonlocal current
        current=store.update(replace(current,previous_sha256=d.delivery_digest(current),**changes),current.revision,task.revision)
    for i,run in enumerate(runs):
        e=replace(current.assignments[i],revision=2,state='dispatched',dispatch_token=run.dispatch_token)
        intent=d.DispatchIntent('1.0',run.dispatch_token,e.assignment_id,2,d.delivery_digest(e),run.observed_at,'pending',None,None)
        assignments=list(current.assignments); assignments[i]=e
        update(assignments=assignments,dispatches=[*current.dispatches,intent])
        e=replace(e,revision=3,state='working',observed_run=run)
        assignments=list(current.assignments); assignments[i]=e
        intents=list(current.dispatches); intents[i]=replace(intent,state='observed',observed_run=run)
        update(assignments=assignments,dispatches=intents)
        tree=Path(e.worktree_root); tree.mkdir(); (tree/'product.txt').write_text('synthetic child output')
        (tree/'check.txt').write_text('synthetic child check')
        e=replace(e,revision=4,state='ready_for_review',handoff_submission_id=f'submit-{i}')
        artifact=c.Artifact('product','product.txt',hashlib.sha256((tree/'product.txt').read_bytes()).hexdigest())
        handoff=c.from_dict('Handoff',json.loads((Path(__file__).resolve().parents[1]/'examples/contracts/Handoff.json').read_text()))
        handoff=replace(handoff,task_id=task.id,role_id=e.selected_role_id,artifacts=[artifact],
            criteria_coverage={'works':['check.txt']},evidence_refs=['check.txt'],next_step='Review synthetic output')
        sub=d.HandoffSubmission('1.0',f'submit-{i}',task.id,e.assignment_id,4,d.delivery_digest(e),handoff,
            hashlib.sha256(c.canonical_json(c.to_dict(handoff))).hexdigest(),run,'2026-11-03T12:00:00Z')
        assignments=list(current.assignments); assignments[i]=e
        update(assignments=assignments,submissions=[*current.submissions,sub])
        output=hashlib.sha256(c.canonical_json([c.to_dict(artifact)])).hexdigest()
        e=replace(e,revision=5,state='accepted',output_sha256=output,review_refs=['review.json'])
        assignments=list(current.assignments); assignments[i]=e
        intents=list(current.dispatches); intents[i]=replace(intents[i],state='terminated',reconciliation_ref='synthetic stopped receipt')
        update(assignments=assignments,dispatches=intents)
    data.task=task; data.delivery=current
    data.bundle=replace(data.bundle,delivery_revision=current.revision,plan_sha256=d.delivery_digest(current.plan))
    data.seal()
    return data,state


class CombinedFixture:
    def setUp(self):
        from smart_assistant.delivery_gate import DeliveryEvidenceStore
        self.data,self.state=combined_fixture(self)
        self.store=DeliveryEvidenceStore(self.state)
        self.delivery=self.data.delivery
        self.base=self.state/'delivery/task/evidence'

    def save(self,expected=0):
        return self.store.save('task',self.data.bundle,expected_revision=expected,
            expected_task_revision=self.data.task.revision,expected_delivery_revision=self.delivery.revision)

    def crash(self):
        import smart_assistant.delivery_gate as g
        atomic=g._atomic
        def fail(base,name,wire):
            if name=='head.json':raise OSError('simulated pre-head interruption')
            return atomic(base,name,wire)
        with patch('smart_assistant.delivery_gate._atomic',side_effect=fail):
            with self.assertRaises(OSError):self.save()
        path=next((self.base/'revisions').iterdir())
        return path.name.split('-',1)[1][:-5],path.read_bytes()

    def recover(self,digest,action='finish',expected=0):
        return self.store.recover('task',1,digest,action,expected_revision=expected,
            expected_task_revision=self.data.task.revision,expected_delivery_revision=self.delivery.revision)

class CombinedPersistenceTests(CombinedFixture,unittest.TestCase):
    def test_saved_evidence_authoritative_gate_completes_with_alternate_callback(self):
        saved=self.save(); self.assertEqual(saved,self.store.read('task'))
        checked=self.store.check('task'); self.assertTrue(checked.passed,checked.errors)
        taskstore=TaskStore(self.state,lambda task:GateResult(True,[]))
        final=taskstore.update(completing(self.data.task),self.data.task.revision)
        self.assertIs(final.status,TaskStatus.COMPLETED)

    def test_bad_evidence_no_head_and_stale_cas_preserve_head(self):
        from smart_assistant.delivery_evidence import evidence_digest
        self.save(); before=(self.base/'head.json').read_bytes()
        for args in [dict(expected_revision=0,expected_task_revision=self.data.task.revision,expected_delivery_revision=self.delivery.revision),
            dict(expected_revision=1,expected_task_revision=self.data.task.revision+1,expected_delivery_revision=self.delivery.revision),
            dict(expected_revision=1,expected_task_revision=self.data.task.revision,expected_delivery_revision=self.delivery.revision+1)]:
            with self.assertRaises(RevisionConflict):self.store.save('task',self.data.bundle,**args)
        self.assertEqual((self.base/'head.json').read_bytes(),before)

    def test_first_save_crash_exact_finish_is_retryable_and_preserves_bytes(self):
        digest,before=self.crash()
        with self.assertRaises(ValidationError):self.save()
        self.recover(digest)
        self.assertEqual(self.store.read('task').revision,1)
        # Retry after a completed recovery is idempotent with refreshed head CAS.
        result=self.recover(digest,expected=1)
        self.assertEqual(result['action'],'finish')
        self.assertEqual(next((self.base/'revisions').iterdir()).read_bytes(),before)

    def test_rejected_orphan_preserved_and_new_save_can_proceed(self):
        digest,before=self.crash(); result=self.recover(digest,'reject')
        self.assertEqual(result['action'],'reject')
        self.assertEqual(next((self.base/'revisions').iterdir()).read_bytes(),before)
        with self.assertRaises(ValidationError):self.recover(digest,'finish')
        # A fresh reviewed receipt yields distinct bytes; rejected envelope stays excluded.
        self.data.bundle=replace(self.data.bundle,reviews=[replace(self.data.bundle.reviews[0],assessment='Fresh independent review after rejected write')])
        self.data.seal()
        saved=self.save()
        self.assertEqual(saved.revision,1)

    def test_delivery_change_invalidates_authoritative_evidence(self):
        from smart_assistant.delivery_store import DeliveryStore
        from smart_assistant.delivery_records import delivery_digest
        self.save()
        snapshot=self.delivery
        updated=replace(snapshot,previous_sha256=delivery_digest(snapshot),
            plan=replace(snapshot.plan,revision=snapshot.plan.revision+1,next_step='New exact plan'))
        DeliveryStore(self.state).update(updated,snapshot.revision,self.data.task.revision)
        with self.assertRaises(ValidationError):self.store.read('task')
        self.assertFalse(self.store.check('task').passed)

    def test_tampered_receipt_and_head_or_revision_cannot_complete(self):
        self.save(); self.data.root.joinpath('after.log').write_text('tampered')
        self.assertFalse(self.store.check('task').passed)
        with self.assertRaises(ValidationError):TaskStore(self.state,lambda task:GateResult(True,[])).update(completing(self.data.task),self.data.task.revision)
        for target in [self.base/'head.json',next((self.base/'revisions').iterdir())]:
            before=target.read_bytes(); target.write_text('{}')
            with self.assertRaises(ValidationError):self.store.read('task')
            target.write_bytes(before)

    def test_cli_delivery_show_evidence_check_and_profile(self):
        import subprocess,sys
        def command(*args):
            return subprocess.run([sys.executable,'-m','smart_assistant',*map(str,args)],
                cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=15)
        self.save()
        for args in [('delivery','show','task','--state-dir',self.state),
            ('delivery','evidence','show','task','--state-dir',self.state),
            ('delivery','check','task','--state-dir',self.state),
            ('team','show','--profile','examples/teams/core/team.json')]:
            with self.subTest(args=args):
                result=command(*args); self.assertEqual(result.returncode,0,result.stdout)
                self.assertTrue(json.loads(result.stdout)['ok'])


def evidence_writer(root,bundle_wire,ready,proceed,result):
    from smart_assistant.delivery_evidence import evidence_from_dict
    from smart_assistant.delivery_gate import DeliveryEvidenceStore
    from smart_assistant.delivery_store import DeliveryStore
    task=TaskStore(Path(root)).read('task'); delivery=DeliveryStore(Path(root)).read('task')
    ready.put(True); proceed.wait(10)
    try:
        saved=DeliveryEvidenceStore(Path(root)).save('task',evidence_from_dict(bundle_wire),expected_revision=0,
            expected_task_revision=task.revision,expected_delivery_revision=delivery.revision)
        result.put(saved.revision)
    except RevisionConflict:result.put('conflict')
    except Exception as error:result.put(type(error).__name__)


def complete_process(root,result):
    try:
        store=TaskStore(Path(root),lambda task:GateResult(True,[])); task=store.read('task')
        result.put(store.update(completing(task),task.revision).status.value)
    except ValidationError as error:result.put([e.code for e in error.errors])


def unsafe_evidence_probe(root,result):
    from smart_assistant.delivery_gate import DeliveryEvidenceStore
    try:DeliveryEvidenceStore(Path(root)).read('task')
    except ValidationError as error:result.put([e.code for e in error.errors])
    except Exception as error:result.put(type(error).__name__)
    else:result.put('accepted')


class PersistenceBoundaryTests(CombinedFixture,unittest.TestCase):
    def test_two_process_evidence_saves_have_one_cas_winner(self):
        from smart_assistant.delivery_evidence import evidence_to_dict
        context=multiprocessing.get_context('spawn'); ready=context.Queue(); output=context.Queue(); proceed=context.Event()
        children=[context.Process(target=evidence_writer,args=(str(self.state),evidence_to_dict(self.data.bundle),ready,proceed,output)) for _ in range(2)]
        for child in children:child.start()
        try:
            for child in children:ready.get(timeout=15)
            proceed.set(); outcomes=[output.get(timeout=15) for _ in children]
            self.assertCountEqual(outcomes,[1,'conflict'])
        finally:
            for child in children:
                child.join(10)
                if child.is_alive():child.terminate(); child.join(); self.fail('Shared task lock deadlock')
                self.assertEqual(child.exitcode,0)

    def test_actual_taskstore_completion_in_bounded_process_does_not_nested_lock(self):
        self.save(); context=multiprocessing.get_context('spawn'); output=context.Queue()
        child=context.Process(target=complete_process,args=(str(self.state),output)); child.start()
        try:self.assertEqual(output.get(timeout=15),'completed')
        finally:
            child.join(10)
            if child.is_alive():child.terminate(); child.join(); self.fail('Nested task/delivery lock deadlock')
            self.assertEqual(child.exitcode,0)

    def test_evidence_head_symlink_hardlink_fifo_never_block_or_load(self):
        self.save(); head=self.base/'head.json'; original=head.read_bytes()
        for kind in ('symlink','hardlink','fifo'):
            with self.subTest(kind=kind):
                head.unlink()
                if kind=='symlink':head.symlink_to(self.state/'tasks/task.json')
                elif kind=='hardlink':
                    head.write_bytes(original); os.link(head,self.base/'head-alias')
                else:os.mkfifo(head)
                context=multiprocessing.get_context('spawn'); output=context.Queue()
                child=context.Process(target=unsafe_evidence_probe,args=(str(self.state),output)); child.start()
                try:self.assertIn('unsafe_path',output.get(timeout=15))
                finally:
                    child.join(10)
                    if child.is_alive():child.terminate(); child.join(); self.fail('Unsafe evidence read blocked')
                    self.assertEqual(child.exitcode,0)
                if kind=='hardlink':(self.base/'head-alias').unlink()
                head.unlink(); head.write_bytes(original)

    def test_missing_evidence_and_unaccepted_child_deny_passing_callback(self):
        checked=self.store.check('task'); self.assertFalse(checked.passed)
        self.assertIn('missing_delivery_evidence',[e.code for e in checked.errors])
        from smart_assistant.delivery_records import delivery_digest, DecisionReceipt
        from smart_assistant.delivery_store import DeliveryStore
        snapshot=self.delivery; e=snapshot.assignments[0]
        receipt=DecisionReceipt('1.0','invalidation-one','task','invalidation','root',snapshot.plan.revision,
            e.assignment_id,e.revision+1,e.output_sha256,['invalidation.txt'],'Reopen accepted output','2026-11-03T12:00:00Z')
        e=replace(e,revision=e.revision+1,state='changes_requested',output_sha256=None,review_refs=[],invalidated_by=[e.assignment_id])
        proposed=replace(snapshot,previous_sha256=delivery_digest(snapshot),
            assignments=[e,*snapshot.assignments[1:]],decisions=[*snapshot.decisions,receipt])
        DeliveryStore(self.state).update(proposed,snapshot.revision,self.data.task.revision)
        checked=self.store.check('task'); self.assertFalse(checked.passed)
        self.assertIn('required_assignment_unaccepted',[e.code for e in checked.errors])

    def test_stale_orphan_cannot_finish_after_delivery_change_but_can_reject(self):
        from smart_assistant.delivery_records import delivery_digest
        from smart_assistant.delivery_store import DeliveryStore
        digest,before=self.crash(); old=self.delivery
        self.delivery=DeliveryStore(self.state).update(replace(old,previous_sha256=delivery_digest(old),
            plan=replace(old.plan,revision=old.plan.revision+1,next_step='Changed plan')),old.revision,self.data.task.revision)
        with self.assertRaises(ValidationError):self.recover(digest)
        self.assertEqual(self.recover(digest,'reject')['action'],'reject')
        self.assertEqual(next((self.base/'revisions').iterdir()).read_bytes(),before)

    def test_corrupt_authority_and_wrong_named_orphan_recovery_never_fallback(self):
        digest,before=self.crash()
        with self.assertRaises(FileNotFoundError):self.recover('0'*64)
        self.recover(digest); head=self.base/'head.json'; original=head.read_bytes(); head.write_text('{}')
        with self.assertRaises(ValidationError):self.recover(digest,expected=1)
        self.assertEqual(head.read_text(),'{}')
        head.write_bytes(original)

    def test_borrowed_session_checks_root_and_expires_without_closing_lock(self):
        from smart_assistant import state
        from smart_assistant.delivery_store import DeliveryStore
        store=TaskStore(self.state)
        with store._directories(False) as (root,tasks,_):
            locks=state._open_directory(root,'locks')
            try:
                with state._lock(locks,'task') as lock:
                    with DeliveryStore(self.state).borrowed('task',root_fd=root,tasks_fd=tasks,locks_fd=locks,lock_fd=lock) as session:
                        self.assertEqual(session.read().task_id,'task')
                    self.assertTrue(os.fstat(lock))
                    with self.assertRaises(ValidationError):session.read()
                    with TemporaryDirectory() as other:
                        with self.assertRaises(ValidationError):
                            with DeliveryStore(Path(other)).borrowed('task',root_fd=root,tasks_fd=tasks,locks_fd=locks,lock_fd=lock):pass
            finally:os.close(locks)

    def test_cli_failed_gate_sanitizes_nested_error_details(self):
        import subprocess,sys
        self.save(); (self.data.root/'after.log').unlink()
        result=subprocess.run([sys.executable,'-m','smart_assistant','delivery','check','task','--state-dir',str(self.state)],
            cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,4,result.stdout)
        payload=json.loads(result.stdout)
        self.assertTrue(payload['data']['errors'])
        self.assertTrue(all(e['path']=='$' for e in payload['data']['errors']),payload)

    def test_actual_cli_register_update_preserves_task_and_reports_cas(self):
        import subprocess,sys
        from smart_assistant.delivery_records import delivery_to_dict,delivery_digest
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); state=root/'state'; task,snapshot=fixture(str(root/'tree'))
            task=TaskStore(state).create(task)
            source=root/'snapshot.json'; source.write_text(json.dumps(delivery_to_dict(snapshot)))
            def command(*args):
                result=subprocess.run([sys.executable,'-m','smart_assistant','delivery',*map(str,args)],
                    cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=15)
                return result.returncode,json.loads(result.stdout)
            before=(state/'tasks/task-01.json').read_bytes()
            code,payload=command('create','--record',source,'--expected-task-revision',1,'--state-dir',state)
            self.assertEqual(code,0,payload)
            code,payload=command('create','--record',source,'--expected-task-revision',1,'--state-dir',state)
            self.assertEqual(code,3,payload)
            current=snapshot; updated=replace(current,previous_sha256=delivery_digest(current),
                plan=replace(current.plan,revision=2,next_step='Review registered work'))
            source.write_text(json.dumps(delivery_to_dict(updated)))
            code,payload=command('update','--record',source,'--expected-revision',1,'--expected-task-revision',1,'--state-dir',state)
            self.assertEqual(code,0,payload); self.assertEqual(payload['data']['revision'],2)
            self.assertEqual((state/'tasks/task-01.json').read_bytes(),before)

    def test_actual_cli_evidence_save_and_completion_enforce_current_bindings(self):
        import subprocess,sys
        from smart_assistant.delivery_evidence import evidence_to_dict
        bundle=self.data.root/'bundle.json'; bundle.write_text(json.dumps(evidence_to_dict(self.data.bundle)))
        def command(*args):
            result=subprocess.run([sys.executable,'-m','smart_assistant',*map(str,args)],
                cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=15)
            return result.returncode,json.loads(result.stdout)
        code,payload=command('delivery','evidence','save','task','--bundle',bundle,'--expected-revision',0,
            '--expected-task-revision',self.data.task.revision,'--expected-delivery-revision',self.delivery.revision,'--state-dir',self.state)
        self.assertEqual(code,0,payload)
        code,payload=command('task','complete','task','--expected-revision',self.data.task.revision,'--state-dir',self.state)
        self.assertEqual(code,0,payload); self.assertEqual(payload['data']['status'],'completed')

    def test_actual_cli_exact_evidence_recovery(self):
        import subprocess,sys
        digest,before=self.crash()
        result=subprocess.run([sys.executable,'-m','smart_assistant','delivery','evidence','recover','task',
            '--revision','1','--revision-sha256',digest,'--action','finish','--expected-revision','0',
            '--expected-task-revision',str(self.data.task.revision),'--expected-delivery-revision',str(self.delivery.revision),
            '--state-dir',str(self.state)],cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(self.store.read('task').revision,1)
        self.assertEqual(next((self.base/'revisions').iterdir()).read_bytes(),before)


def nested_callback_process(root,output):
    from smart_assistant.delivery_store import DeliveryStore
    def callback(task):
        output.put('callback-entered')
        DeliveryStore(Path(root)).read(task.id)
        return GateResult(True,[])
    store=TaskStore(Path(root),callback); task=store.read('task')
    try:store.update(completing(task),task.revision); output.put('completed')
    except ValidationError as error:output.put([e.code for e in error.errors])


class CallbackBoundaryTests(CombinedFixture,unittest.TestCase):
    def test_callback_receipt_mutation_denies_completion_with_unchanged_task(self):
        self.save(); before=(self.state/'tasks/task.json').read_bytes(); calls=[]
        def callback(task):
            calls.append(True); (self.data.root/'after.log').write_text('refreshed check output')
            return GateResult(True,[])
        store=TaskStore(self.state,callback)
        with self.assertRaises(ValidationError) as raised:store.update(completing(self.data.task),self.data.task.revision)
        self.assertEqual(calls,[True])
        self.assertIn('evidence_hash_mismatch',[e.code for e in raised.exception.errors])
        self.assertEqual((self.state/'tasks/task.json').read_bytes(),before)

    def test_callback_candidate_mutation_denies_completion_with_unchanged_task(self):
        self.save(); before=(self.state/'tasks/task.json').read_bytes(); calls=[]
        def callback(task):
            calls.append(True); (self.data.root/'product.txt').write_text('candidate changed during callback')
            return GateResult(True,[])
        store=TaskStore(self.state,callback)
        with self.assertRaises(ValidationError) as raised:store.update(completing(self.data.task),self.data.task.revision)
        self.assertEqual(calls,[True])
        self.assertIn('stale_candidate',[e.code for e in raised.exception.errors])
        self.assertEqual((self.state/'tasks/task.json').read_bytes(),before)

    def test_nested_callback_delivery_read_fails_fast_under_same_task_lock(self):
        self.save(); before=(self.state/'tasks/task.json').read_bytes()
        context=multiprocessing.get_context('spawn'); output=context.Queue()
        child=context.Process(target=nested_callback_process,args=(str(self.state),output)); child.start()
        try:
            self.assertEqual(output.get(timeout=15),'callback-entered')
            child.join(3)
            self.assertFalse(child.is_alive(),'Callback attempted a second task flock and hung')
            self.assertEqual(child.exitcode,0)
            self.assertIn('nested_lock',output.get(timeout=2))
        finally:
            if child.is_alive():child.terminate(); child.join(5)
        self.assertEqual((self.state/'tasks/task.json').read_bytes(),before)

    def test_initial_mandatory_receipt_denial_prevents_callback_side_effects(self):
        self.save(); calls=[]; (self.data.root/'after.log').write_text('already stale before callback')
        store=TaskStore(self.state,lambda task:calls.append(True) or GateResult(True,[]))
        with self.assertRaises(ValidationError):store.update(completing(self.data.task),self.data.task.revision)
        self.assertFalse(calls)
