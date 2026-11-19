"""P11 isolated persistence/race/recovery tests; no live user state."""
from dataclasses import replace
import importlib
import hashlib
import importlib.util
import json
import multiprocessing
import os
import queue
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from smart_assistant.contracts import RevisionConflict, ValidationError, TaskStatus
from smart_assistant.state import TaskStore
from tests.test_delivery_records import fixture, module, dispatched, observed, support, STAMP, EXAMPLES
from smart_assistant import contracts as c


def store_module():
    assert importlib.util.find_spec('smart_assistant.delivery_store') is not None, 'P11 delivery_store missing'
    return importlib.import_module('smart_assistant.delivery_store')


def writer(root, ready, proceed, output, label):
    store = store_module().DeliveryStore(Path(root))
    snapshot = store.read('task-01')
    ready.put(label); proceed.wait(10)
    try:
        updated = store.update(replace(snapshot, plan=replace(snapshot.plan, revision=2, next_step=label),
            previous_sha256=module().delivery_digest(snapshot)), 1, 1)
        output.put(updated.revision)
    except RevisionConflict: output.put('conflict')


def nested_lock_probe(root,output):
    store=store_module().DeliveryStore(Path(root))
    with store.locked('task-01'):
        try: store_module().DeliveryStore(Path(root)).read('task-01')
        except ValidationError as error: output.put([item.code for item in error.errors])
        else: output.put('wrongly-accepted')


def task_writer_holding_lock(root,ready,proceed,output):
    from smart_assistant import state
    store=TaskStore(Path(root)); task=store.read('task-01'); original=state._write_record
    def paused(tasks,task_id,record):
        ready.set()
        if not proceed.wait(10): raise RuntimeError('Task writer release timed out')
        return original(tasks,task_id,record)
    try:
        with patch('smart_assistant.state._write_record',side_effect=paused):
            output.put(('task',store.update(task,1).revision))
    except Exception as error: output.put(('task-error',type(error).__name__))


def waiting_delivery_writer(root,wire,ready,output):
    d=module(); store=store_module().DeliveryStore(Path(root)); snapshot=d.delivery_from_dict('DeliverySnapshot',wire)
    candidate=replace(snapshot,previous_sha256=d.delivery_digest(snapshot),plan=replace(snapshot.plan,revision=2,next_step='Waited'))
    ready.set()
    try: output.put(('delivery',store.update(candidate,1,1).revision))
    except RevisionConflict: output.put(('delivery','task-conflict'))
    except Exception as error: output.put(('delivery-error',type(error).__name__))


def unsafe_leaf_probe(root,output):
    try: store_module().DeliveryStore(Path(root)).read('task-01')
    except ValidationError as error: output.put([e.code for e in error.errors])
    else: output.put('wrongly-accepted')


class DeliveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.m = store_module()
        self.d = module()
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.task, self.snapshot = fixture(str(self.root/'worktree'))
        self.task = TaskStore(self.root).create(self.task)
        self.store = self.m.DeliveryStore(self.root)

    def register(self):
        return self.store.register(self.snapshot, 1)

    def next(self, snapshot):
        return replace(snapshot, previous_sha256=self.d.delivery_digest(snapshot),
            plan=replace(snapshot.plan, revision=snapshot.plan.revision+1, next_step='Review'))

    def test_reserved_missing_registration_denied(self):
        with self.assertRaises(ValidationError): self.store.read(self.task.id)

    def test_f01_invalid_registration_does_not_create_storage(self):
        cases=('missing_marker','wrong_marker','stale_task','verifying_task','terminal_task',
            'wrong_request','initial_revision','initial_plan','initial_dispatch')
        for case, direct in ((case,direct) for case in cases for direct in (False,True)):
            with self.subTest(case=case,direct=direct), TemporaryDirectory() as tmp:
                root=Path(tmp).resolve(); task,initial=fixture(str(root/'tree')); expected=1
                if case=='missing_marker':task.request.source_refs=[ref for ref in task.request.source_refs if not ref.startswith(self.d.PREFIX)]
                elif case=='wrong_marker':task.request.source_refs[-1]=self.d.PREFIX+'wrong'
                elif case=='verifying_task':task.status=TaskStatus.VERIFYING
                elif case=='terminal_task':task.status=TaskStatus.CANCELLED
                if case in ('missing_marker','wrong_marker'):
                    digest=self.d.request_digest(task.request)
                    initial=replace(initial,registration=replace(initial.registration,request_sha256=digest),
                        plan=replace(initial.plan,request_sha256=digest))
                elif case=='wrong_request':initial=replace(initial,registration=replace(initial.registration,request_sha256='b'*64))
                elif case=='stale_task':expected=2
                elif case=='initial_revision':initial=replace(initial,revision=2)
                elif case=='initial_plan':initial=replace(initial,plan=replace(initial.plan,revision=2))
                elif case=='initial_dispatch':initial=dispatched(initial)
                TaskStore(root).create(task)
                before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises((ValidationError,RevisionConflict)):
                    store=self.m.DeliveryStore(root)
                    if direct:
                        with store.locked(task.id,create=True) as session:
                            self.assertFalse((root/'delivery').exists())
                            session.register(initial,expected)
                    else:store.register(initial,expected)
                self.assertFalse((root/'delivery').exists())
                self.assertEqual({str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()},before)

    def test_f01_unknown_task_access_creates_no_delivery_storage(self):
        before=(self.root/'tasks/task-01.json').read_bytes()
        for action in ('read','recover','register'):
            with self.subTest(action=action):
                with self.assertRaises((ValidationError,FileNotFoundError)):
                    if action=='read':self.store.read('unknown-task')
                    elif action=='recover':self.store.recover('unknown-task','operation-unknown','reject')
                    else:
                        self.store.register(replace(self.snapshot,task_id='unknown-task'),1)
                self.assertFalse((self.root/'delivery').exists())
                self.assertEqual((self.root/'tasks/task-01.json').read_bytes(),before)

    def test_f01_explicit_registration_context_defers_storage_and_checks_locked_identity(self):
        with self.store.locked(self.task.id,create=True) as session:
            self.assertEqual(session.read_task(),self.task)
            self.assertFalse((self.root/'delivery').exists())
            with self.assertRaises(ValidationError):session.read()
            with self.assertRaises(ValidationError):
                session.register(replace(self.snapshot,task_id='wrong-task'),1)
            self.assertFalse((self.root/'delivery').exists())
            first=session.register(self.snapshot,1)
            self.assertEqual(session.read(),first)
            self.assertEqual(session.update(self.next(first),1,1).revision,2)
        self.assertEqual(self.store.read(self.task.id).revision,2)

    def test_f01_default_context_and_incomplete_existing_sidecar_create_nothing(self):
        before=(self.root/'tasks/task-01.json').read_bytes()
        with self.assertRaises(ValidationError):
            with self.store.locked(self.task.id):self.fail('Missing storage must not open by default')
        self.assertFalse((self.root/'delivery').exists())
        base=self.root/'delivery/task-01'; base.mkdir(parents=True)
        sentinel=base/'unexplained.json'; sentinel.write_bytes(b'preserved unexplained bytes')
        with self.assertRaises(ValidationError):self.register()
        self.assertEqual({p.name for p in base.iterdir()},{'unexplained.json'})
        self.assertEqual(sentinel.read_bytes(),b'preserved unexplained bytes')
        self.assertEqual((self.root/'tasks/task-01.json').read_bytes(),before)

    def test_register_update_roundtrip_leaves_v1_task_unchanged(self):
        before = (self.root/'tasks/task-01.json').read_bytes()
        first = self.register()
        self.assertEqual(first, self.store.read(self.task.id))
        second = self.store.update(self.next(first), 1, 1)
        self.assertEqual(second.revision, 2)
        self.assertEqual(self.store.read(self.task.id), second)
        self.assertEqual((self.root/'tasks/task-01.json').read_bytes(), before)
        self.assertEqual(len(list((self.root/'delivery/task-01/revisions').iterdir())), 2)

    def test_stale_delivery_or_task_cas_preserves_head(self):
        first = self.register()
        with self.assertRaises(RevisionConflict): self.store.update(self.next(first), 2, 1)
        task = TaskStore(self.root).read(self.task.id)
        TaskStore(self.root).update(task, 1)
        with self.assertRaises(RevisionConflict): self.store.update(self.next(first), 1, 1)
        self.assertEqual(self.store.read(self.task.id), first)

    def test_two_processes_one_cas_winner(self):
        self.register()
        ctx=multiprocessing.get_context('spawn')
        ready,output,proceed=ctx.Queue(),ctx.Queue(),ctx.Event()
        children=[ctx.Process(target=writer,args=(str(self.root),ready,proceed,output,str(i))) for i in range(2)]
        for child in children: child.start()
        for child in children: ready.get(timeout=10)
        proceed.set()
        results=[output.get(timeout=15) for child in children]
        for child in children:
            child.join(10); self.assertEqual(child.exitcode,0)
        self.assertCountEqual(results,[2,'conflict'])

    def test_locked_session_expires(self):
        self.register()
        with self.store.locked(self.task.id) as session:
            self.assertEqual(session.read_task(),self.task)
            first=session.read()
            self.assertEqual(session.update(self.next(first),1,1).revision,2)
        with self.assertRaises(ValidationError): session.read()

    def test_terminal_task_update_denied(self):
        self.register()
        task=TaskStore(self.root).read(self.task.id)
        task.status=TaskStatus.CANCELLED
        TaskStore(self.root).update(task,1)
        with self.assertRaises(ValidationError): self.store.update(self.next(self.snapshot),1,2)

    def test_corrupt_authoritative_components_never_fall_back(self):
        for relative in ['head.json','registration.json','revisions']:
            with self.subTest(component=relative), TemporaryDirectory() as subroot:
                root=Path(subroot).resolve(); task,snapshot=fixture(str(root/'tree'))
                TaskStore(root).create(task); store=self.m.DeliveryStore(root); store.register(snapshot,1)
                target=root/'delivery/task-01'/relative
                if target.is_dir():
                    target=next(target.iterdir())
                target.write_text('{}')
                with self.assertRaises(ValidationError): store.read(task.id)

    def test_symlink_hardlink_fifo_rejected(self):
        self.register(); base=self.root/'delivery/task-01'; head=base/'head.json'
        saved=head.read_bytes(); head.unlink(); head.symlink_to(self.root/'tasks/task-01.json')
        with self.assertRaises(ValidationError): self.store.read(self.task.id)
        head.unlink(); head.write_bytes(saved)
        os.link(head,base/'alias')
        with self.assertRaises(ValidationError): self.store.read(self.task.id)
        (base/'alias').unlink(); head.unlink(); os.mkfifo(head)
        with self.assertRaises(ValidationError): self.store.read(self.task.id)

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        self.register(); head=self.root/'delivery/task-01/head.json'
        for text in ['{"revision":1,"revision":1}', '{"revision":NaN}']:
            head.write_text(text)
            with self.assertRaises(ValidationError): self.store.read(self.task.id)

    def test_crash_before_head_blocks_until_explicit_finish(self):
        first=self.register()
        with patch('smart_assistant.delivery_store.os.replace', side_effect=OSError('crash')):
            with self.assertRaises(OSError): self.store.update(self.next(first),1,1)
        with self.assertRaises(ValidationError): self.store.read(self.task.id)
        operations=list((self.root/'delivery/task-01/operations').glob('*.json'))
        unresolved=[p.stem for p in operations if not (self.root/'delivery/task-01/resolutions'/p.name).exists()]
        self.assertEqual(len(unresolved),1)
        # First replace fails before staging snapshot; finish must not manufacture it.
        with self.assertRaises(ValidationError): self.store.recover(self.task.id,unresolved[0],'finish')
        report=self.store.recover(self.task.id,unresolved[0],'reject')
        self.assertEqual(report.outcome,'rejected')
        self.assertEqual(self.store.read(self.task.id),first)
        self.assertEqual(self.store.recover(self.task.id,unresolved[0],'reject'),report)

    def test_crash_after_snapshot_can_finish_same_operation(self):
        first=self.register(); original=self.m.os.replace
        def fail_head(source,target,*args,**kwargs):
            if target=='head.json': raise OSError('before head')
            return original(source,target,*args,**kwargs)
        with patch('smart_assistant.delivery_store.os.replace',side_effect=fail_head):
            with self.assertRaises(OSError): self.store.update(self.next(first),1,1)
        operation=json.loads((self.root/'delivery/task-01/pending.json').read_text())['operation_id']
        result=self.store.recover(self.task.id,operation,'finish')
        self.assertEqual(result.head_revision,2)
        self.assertEqual(self.store.read(self.task.id).revision,2)
        with self.assertRaises(ValidationError): self.store.recover(self.task.id,operation,'reject')


    def prepared_submission(self):
        first=self.register()
        dispatch=dispatched(first)
        second=self.store.update(replace(dispatch,previous_sha256=self.d.delivery_digest(first)),1,1)
        observation=observed(first)
        third=self.store.update(replace(second,previous_sha256=self.d.delivery_digest(second),
            assignments=observation.assignments,dispatches=observation.dispatches),2,1)
        e=replace(third.assignments[0],revision=4,state='ready_for_review',handoff_submission_id='submit-01')
        worktree=Path(e.worktree_root); (worktree/'outputs').mkdir(parents=True); (worktree/'evidence').mkdir()
        (worktree/'outputs/result.md').write_text('actual output')
        (worktree/'evidence/check.md').write_text('synthetic check')
        payload=json.loads((EXAMPLES/'Handoff.json').read_text())
        payload.update(artifacts=[{'id':'result-01','relative_path':'outputs/result.md',
            'sha256':hashlib.sha256((worktree/'outputs/result.md').read_bytes()).hexdigest()}],
            evidence_refs=['evidence/check.md'],criteria_coverage={'criterion-01':['evidence/check.md']}, next_step='Review output')
        sub=support('HandoffSubmission',submission_id='submit-01',task_id=third.task_id,
            assignment_id=e.assignment_id,envelope_revision=e.revision,envelope_sha256=self.d.delivery_digest(e),
            payload=payload,handoff_sha256=hashlib.sha256(c.canonical_json(payload)).hexdigest(),
            observed_run=self.d.delivery_to_dict(e.observed_run),submitted_at=STAMP)
        proposed=replace(third,previous_sha256=self.d.delivery_digest(third),assignments=[e],submissions=[sub])
        return third,proposed,worktree

    def test_tampered_real_artifact_denies_submission(self):
        third,proposed,worktree=self.prepared_submission()
        (worktree/'outputs/result.md').write_text('changed after capture')
        with self.assertRaises(ValidationError) as caught: self.store.update(proposed,3,1)
        self.assertIn('artifact_digest_mismatch',[e.code for e in caught.exception.errors])
        self.assertEqual(self.store.read(self.task.id),third)

    def test_tampered_real_artifact_denies_acceptance_after_ready(self):
        third,proposed,worktree=self.prepared_submission()
        ready=self.store.update(proposed,3,1)
        output=hashlib.sha256(c.canonical_json([c.to_dict(a) for a in ready.submissions[0].payload.artifacts])).hexdigest()
        e=replace(ready.assignments[0],revision=5,state='accepted',review_refs=['review.md'],output_sha256=output)
        candidate=replace(ready,previous_sha256=self.d.delivery_digest(ready),assignments=[e])
        (worktree/'outputs/result.md').write_text('changed after review')
        with self.assertRaises(ValidationError) as caught: self.store.update(candidate,4,1)
        self.assertIn('artifact_digest_mismatch',[e.code for e in caught.exception.errors])
        self.assertEqual(self.store.read(self.task.id),ready)


    def test_review_r1_missing_head_cannot_reregister_old_revision(self):
        first=self.register(); second=self.store.update(self.next(first),1,1)
        (self.root/'delivery/task-01/head.json').unlink()
        with self.assertRaises(ValidationError): self.store.register(self.snapshot,1)
        self.assertTrue(any(p.name.startswith('2-') for p in (self.root/'delivery/task-01/revisions').iterdir()))

    def test_review_r2_old_operation_digest_tampering_denied(self):
        first=self.register(); base=self.root/'delivery/task-01'
        old=json.loads((base/'head.json').read_text())
        self.store.update(self.next(first),1,1)
        path=base/'operations'/f"{old['operation_id']}.json"
        data=json.loads(path.read_text()); data['expected_task_revision']=999; path.write_text(json.dumps(data))
        with self.assertRaises(ValidationError): self.store.read(self.task.id)

    def test_review_r3_locked_register_detaches_caller_owned_lists(self):
        original=self.m._write_immutable; changed=False
        def mutate_after_operation(parent,name,wire):
            nonlocal changed
            result=original(parent,name,wire)
            if not changed and name.startswith('op-'):
                changed=True; self.snapshot.plan.requirement_ids.append('criterion-02')
            return result
        with self.store.locked(self.task.id,create=True) as session:
            with patch('smart_assistant.delivery_store._write_immutable',side_effect=mutate_after_operation):
                result=session.register(self.snapshot,1)
        self.assertEqual(result.plan.requirement_ids,['criterion-01'])
        self.assertEqual(self.store.read(self.task.id).plan.requirement_ids,['criterion-01'])

    def test_review_r3_locked_update_detaches_caller_owned_lists(self):
        first=self.register(); candidate=self.next(first); original=self.m._write_immutable; changed=False
        def mutate_after_operation(parent,name,wire):
            nonlocal changed
            result=original(parent,name,wire)
            if not changed and name.startswith('op-'):
                changed=True; candidate.plan.requirement_ids.append('criterion-02')
            return result
        with self.store.locked(self.task.id) as session:
            with patch('smart_assistant.delivery_store._write_immutable',side_effect=mutate_after_operation):
                result=session.update(candidate,1,1)
        self.assertEqual(result.plan.requirement_ids,['criterion-01'])
        self.assertEqual(self.store.read(self.task.id).plan.requirement_ids,['criterion-01'])


    def test_review_r6_nested_cross_instance_lock_promptly_rejected(self):
        self.register(); ctx=multiprocessing.get_context('spawn'); output=ctx.Queue()
        child=ctx.Process(target=nested_lock_probe,args=(str(self.root),output)); child.start(); child.join(3)
        hung=child.is_alive()
        if hung: child.terminate(); child.join(3)
        self.assertFalse(hung,'Nested DeliveryStore acquisition deadlocked')
        self.assertEqual(child.exitcode,0)
        self.assertIn('nested_lock',output.get(timeout=2))


    def test_review_r2_old_operation_missing_or_misbound_resolution_denied(self):
        for change in ('missing_operation','wrong_resolution','missing_resolution'):
            with self.subTest(change=change),TemporaryDirectory() as tmp:
                root=Path(tmp).resolve(); task,snapshot=fixture(str(root/'tree')); TaskStore(root).create(task)
                store=self.m.DeliveryStore(root); first=store.register(snapshot,1); base=root/'delivery/task-01'
                old=json.loads((base/'head.json').read_text()); store.update(self.next(first),1,1)
                operation=base/'operations'/f"{old['operation_id']}.json"
                resolution=base/'resolutions'/f"{old['operation_id']}.json"
                if change=='missing_operation': operation.unlink()
                elif change=='missing_resolution': resolution.unlink()
                else:
                    wire=json.loads(resolution.read_text()); wire['head_revision']=99; resolution.write_text(json.dumps(wire))
                with self.assertRaises(ValidationError): store.read(task.id)

    def test_review_r2_finished_resolution_cannot_report_success_with_missing_head(self):
        self.register(); base=self.root/'delivery/task-01'
        head=json.loads((base/'head.json').read_text()); (base/'head.json').unlink()
        with self.assertRaises(ValidationError): self.store.recover(self.task.id,head['operation_id'],'finish')

    def test_review_r5_public_original_dispatch_lookup(self):
        third,proposed,worktree=self.prepared_submission()
        original=self.store.dispatch_envelope(self.task.id,'token-01')
        self.assertEqual(original.revision,2); self.assertEqual(original.state,'dispatched')
        self.assertEqual(self.d.delivery_digest(original),third.dispatches[0].envelope_sha256)
        self.assertTrue(self.d.validate_submission(proposed.assignments[0],proposed.submissions[0],third.dispatches[0],worktree,
            dispatched_envelope=original).passed)


    def test_review_r7_waiting_delivery_writer_observes_taskstore_cas(self):
        first=self.register(); ctx=multiprocessing.get_context('spawn')
        task_ready,release,delivery_ready=ctx.Event(),ctx.Event(),ctx.Event(); output=ctx.Queue()
        task_child=ctx.Process(target=task_writer_holding_lock,args=(str(self.root),task_ready,release,output))
        delivery_child=ctx.Process(target=waiting_delivery_writer,args=(str(self.root),self.d.delivery_to_dict(first),delivery_ready,output))
        task_child.start()
        try:
            self.assertTrue(task_ready.wait(5)); delivery_child.start(); self.assertTrue(delivery_ready.wait(5))
            with self.assertRaises(queue.Empty): output.get(timeout=.2)
        finally: release.set()
        results=[output.get(timeout=10),output.get(timeout=10)]
        for child in (task_child,delivery_child):
            child.join(5)
            if child.is_alive(): child.terminate(); child.join(3)
            self.assertEqual(child.exitcode,0)
        self.assertCountEqual(results,[('task',2),('delivery','task-conflict')])
        self.assertEqual(self.store.read(self.task.id),first)

    def test_review_r7_distinct_initial_crash_boundaries(self):
        phases=['operation','pending','registration','snapshot','final_revalidation','head_fsync','resolution']
        for phase in phases:
            with self.subTest(phase=phase),TemporaryDirectory() as tmp:
                root=Path(tmp).resolve(); task,snapshot=fixture(str(root/'tree')); TaskStore(root).create(task)
                store=self.m.DeliveryStore(root); base=root/'delivery/task-01'; fired=False
                original_write=self.m._write_immutable; original_atomic=self.m._atomic
                original_check=self.m.LockedDelivery._check_task; original_fsync=self.m.os.fsync; checks=0
                def fail_after_write(parent,name,wire):
                    nonlocal fired
                    result=original_write(parent,name,wire)
                    match=(phase=='operation' and 'expected_task_revision' in wire or
                        phase=='registration' and name=='registration.json' or
                        phase=='snapshot' and 'assignments' in wire or phase=='resolution' and 'action' in wire)
                    if match and not fired: fired=True; raise OSError('crash '+phase)
                    return result
                def fail_after_atomic(parent,name,wire):
                    nonlocal fired
                    result=original_atomic(parent,name,wire)
                    if phase=='pending' and name=='pending.json' and not fired:
                        fired=True; raise OSError('crash pending')
                    return result
                def fail_final_check(session,expected):
                    nonlocal checks,fired
                    result=original_check(session,expected); checks+=1
                    if phase=='final_revalidation' and checks==2:
                        fired=True; raise OSError('crash revalidation')
                    return result
                def fail_head_fsync(fd):
                    nonlocal fired
                    if phase=='head_fsync' and not fired and (base/'head.json').exists():
                        info=os.fstat(fd); named=base.stat()
                        if (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino):
                            fired=True; raise OSError('crash after head replace before directory fsync')
                    return original_fsync(fd)
                with patch('smart_assistant.delivery_store._write_immutable',side_effect=fail_after_write),                         patch('smart_assistant.delivery_store._atomic',side_effect=fail_after_atomic),                         patch.object(self.m.LockedDelivery,'_check_task',new=fail_final_check),                         patch('smart_assistant.delivery_store.os.fsync',side_effect=fail_head_fsync):
                    with self.assertRaises(OSError): store.register(snapshot,1)
                self.assertTrue(fired)
                with self.assertRaises(ValidationError): store.read(task.id)
                operation=next((base/'operations').glob('*.json')).stem
                self.assertTrue((base/'operations'/f'{operation}.json').exists())
                if phase in ('operation','pending','registration'):
                    self.assertFalse((base/'head.json').exists())
                    with self.assertRaises(ValidationError): store.recover(task.id,operation,'finish')
                    report=store.recover(task.id,operation,'reject')
                    self.assertEqual(report,store.recover(task.id,operation,'reject'))
                    self.assertFalse((base/'head.json').exists())
                    with self.assertRaises(ValidationError): store.read(task.id)
                    self.assertEqual(store.register(snapshot,1),snapshot)
                else:
                    report=store.recover(task.id,operation,'finish')
                    self.assertEqual(report.head_revision,1)
                    self.assertEqual(report,store.recover(task.id,operation,'finish'))
                    self.assertEqual(store.read(task.id),snapshot)
                    with self.assertRaises(ValidationError): store.recover(task.id,operation,'reject')

    def test_review_r7_detached_revisions_denies_publish_and_preserves_staging(self):
        first=self.register(); base=self.root/'delivery/task-01'; original=self.m._write_immutable; detached=False
        def detach_after_snapshot(parent,name,wire):
            nonlocal detached
            result=original(parent,name,wire)
            if 'assignments' in wire and not detached:
                detached=True; (base/'revisions').rename(base/'detached-revisions'); (base/'revisions').mkdir()
            return result
        with patch('smart_assistant.delivery_store._write_immutable',side_effect=detach_after_snapshot):
            with self.assertRaises(ValidationError) as caught: self.store.update(self.next(first),1,1)
        self.assertIn('unsafe_path',[e.code for e in caught.exception.errors])
        self.assertEqual(json.loads((base/'head.json').read_text())['revision'],1)
        self.assertTrue(any(p.name.startswith('2-') for p in (base/'detached-revisions').iterdir()))
        (base/'revisions').rmdir(); (base/'detached-revisions').rename(base/'revisions')
        operation=json.loads((base/'pending.json').read_text())['operation_id']
        self.assertEqual(self.store.recover(self.task.id,operation,'finish').head_revision,2)

    def test_review_r7_replaced_lock_denies_publish(self):
        first=self.register(); original=self.m._write_immutable; changed=False
        lock=self.root/'locks/task-01.lock'; saved=self.root/'locks/saved.lock'
        def replace_after_snapshot(parent,name,wire):
            nonlocal changed
            result=original(parent,name,wire)
            if 'assignments' in wire and not changed:
                changed=True; lock.rename(saved); lock.write_text('replacement')
            return result
        with patch('smart_assistant.delivery_store._write_immutable',side_effect=replace_after_snapshot):
            with self.assertRaises(ValidationError) as caught: self.store.update(self.next(first),1,1)
        self.assertIn('unsafe_path',[e.code for e in caught.exception.errors])
        self.assertEqual(json.loads((self.root/'delivery/task-01/head.json').read_text())['revision'],1)
        lock.unlink(); saved.rename(lock)

    def test_review_r7_unsafe_fifo_leaf_is_bounded(self):
        self.register(); head=self.root/'delivery/task-01/head.json'; head.unlink(); os.mkfifo(head)
        ctx=multiprocessing.get_context('spawn'); output=ctx.Queue()
        child=ctx.Process(target=unsafe_leaf_probe,args=(str(self.root),output)); child.start(); child.join(3)
        hung=child.is_alive()
        if hung: child.terminate(); child.join(3)
        self.assertFalse(hung,'Unsafe FIFO read blocked'); self.assertEqual(child.exitcode,0)
        self.assertIn('unsafe_path',output.get(timeout=2))


    def test_round2_missing_head_and_operation_remnants_never_reregister(self):
        for remnants in ('all','registration','revisions','resolutions'):
            with self.subTest(remnants=remnants),TemporaryDirectory() as tmp:
                root=Path(tmp).resolve(); task,snapshot=fixture(str(root/'tree')); TaskStore(root).create(task)
                store=self.m.DeliveryStore(root); first=store.register(snapshot,1)
                store.update(self.next(first),1,1); base=root/'delivery/task-01'
                (base/'head.json').unlink()
                for path in (base/'operations').iterdir(): path.unlink()
                if remnants!='all':
                    if remnants!='registration': (base/'registration.json').unlink()
                    for directory in ('revisions','resolutions'):
                        if remnants!=directory:
                            for path in (base/directory).iterdir(): path.unlink()
                before={str(path.relative_to(base)):path.read_bytes() for path in base.rglob('*') if path.is_file()}
                with self.assertRaises(ValidationError): store.register(snapshot,1)
                self.assertFalse((base/'head.json').exists())
                self.assertEqual(list((base/'operations').iterdir()),[])
                self.assertEqual({str(path.relative_to(base)):path.read_bytes() for path in base.rglob('*') if path.is_file()},before)

    def test_round2_rejected_initial_retry_requires_retained_operation_proof(self):
        original=self.m.os.replace
        def fail_head(source,target,*args,**kwargs):
            if target=='head.json': raise OSError('before initial head')
            return original(source,target,*args,**kwargs)
        with patch('smart_assistant.delivery_store.os.replace',side_effect=fail_head):
            with self.assertRaises(OSError): self.register()
        base=self.root/'delivery/task-01'
        operation=json.loads((base/'pending.json').read_text())['operation_id']
        self.store.recover(self.task.id,operation,'reject')
        (base/'operations'/f'{operation}.json').unlink()
        with self.assertRaises(ValidationError): self.register()
        self.assertFalse((base/'head.json').exists())
        self.assertEqual(list((base/'operations').iterdir()),[])

    def test_committed_head_cleanup_and_reject_denied(self):
        first=self.register(); original=self.m.os.unlink
        def fail_pending(path,*args,**kwargs):
            if path=='pending.json': raise OSError('after head')
            return original(path,*args,**kwargs)
        with patch('smart_assistant.delivery_store.os.unlink',side_effect=fail_pending):
            with self.assertRaises(OSError): self.store.update(self.next(first),1,1)
        operation=json.loads((self.root/'delivery/task-01/pending.json').read_text())['operation_id']
        with self.assertRaises(ValidationError): self.store.recover(self.task.id,operation,'reject')
        self.assertEqual(self.store.recover(self.task.id,operation,'finish').head_revision,2)
        self.assertEqual(self.store.read(self.task.id).revision,2)

if __name__=='__main__': unittest.main()
