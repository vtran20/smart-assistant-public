import importlib
import json
from pathlib import Path
import unittest
from smart_assistant import contracts as c, delivery_records as d
from tests.test_delivery_records import fixture
from tests.test_builtin_records import fixture as builtin_fixture
import tempfile

class DeliveryCodecTests(unittest.TestCase):
    def setUp(self): self.codec=importlib.import_module('smart_assistant.delivery_codec')

    def test_managed_hash_unchanged(self):
        golden=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/core-managed-golden.json').read_text())
        for kind,item in golden.items():
            record=self.codec.record_from_dict(kind,item['wire'],mode='managed')
            self.assertEqual(self.codec.record_to_dict(record),item['wire'])
            self.assertEqual(self.codec.record_digest(record),item['sha256'])
            self.assertEqual(d.delivery_digest(record),item['sha256'])

    def test_mode_for_task_and_strict_marker_fail_closed(self):
        task,_=fixture();self.assertEqual(self.codec.mode_for_task(task),'managed')
        for marker in ['smart-assistant:execution-mode:garbage','smart-assistant:execution-mode:builtin:3.0:'+'a'*64]:
            task.request.source_refs.append(marker)
            with self.assertRaises(c.ValidationError):self.codec.mode_for_task(task)
            task.request.source_refs.pop()
        with tempfile.TemporaryDirectory() as tmp:
            task,s,_=builtin_fixture(Path(tmp).resolve())
            self.assertEqual(self.codec.mode_for_task(task),'builtin')
            task.request.requested_role='configured'
            with self.assertRaises(c.ValidationError):self.codec.mode_for_task(task)

    def test_no_unknown_version_cross_mode_or_snapshot_fallback(self):
        task,s=fixture();wire=d.delivery_to_dict(s)
        with self.assertRaises(c.ValidationError):self.codec.record_from_dict('DeliverySnapshot',wire)
        with self.assertRaises(c.ValidationError):self.codec.record_from_dict('DeliverySnapshot',wire,mode='builtin')
        wire['schema_version']='2.0'
        with self.assertRaises(c.ValidationError):self.codec.record_from_dict('DeliverySnapshot',wire,mode='managed')
        with tempfile.TemporaryDirectory() as tmp:
            task,s,_=builtin_fixture(Path(tmp).resolve());b=importlib.import_module('smart_assistant.builtin_records')
            wire=b.builtin_to_dict(s)
            self.assertEqual(self.codec.record_from_dict('BuiltinSnapshot',wire,mode='builtin'),s)
            with self.assertRaises(c.ValidationError):self.codec.record_from_dict('BuiltinSnapshot',wire,mode='managed')
            self.assertTrue(self.codec.validate_snapshot(s,task).passed)
            with self.assertRaises(c.ValidationError):d.delivery_to_dict(s)
        with self.assertRaises(c.ValidationError):self.codec.record_to_dict(object())

    def test_shared_helpers_replay_all_existing_managed_semantic_regressions(self):
        from unittest.mock import patch
        from smart_assistant import delivery_semantics as semantics
        from tests.test_delivery_records import DeliveryRecordsTests
        def check(s,task):
            return semantics.check_snapshot(d.delivery_to_dict(s),task,mode='managed')
        def history(s,previous):
            return semantics.check_history(d.delivery_to_dict(s),d.delivery_to_dict(previous),mode='managed')
        def binding(e,s,i):
            return semantics.check_submission_binding(d.delivery_to_dict(e),d.delivery_to_dict(s),d.delivery_to_dict(i),mode='managed')
        def scope(e):
            return semantics.scope_key(d.delivery_to_dict(e),mode='managed')
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(DeliveryRecordsTests)
        result=unittest.TestResult()
        with patch.object(d,'_snapshot_checks',check),patch.object(d,'_history',history),patch.object(d,'_submission_binding',binding),patch.object(d,'_scope',scope):
            suite.run(result)
        self.assertEqual(result.testsRun,35)
        self.assertFalse(result.failures+result.errors, result.failures+result.errors)

    def test_C01_shared_managed_view_rejects_nested_root_file_alias(self):
        from dataclasses import replace
        from smart_assistant import delivery_semantics as semantics
        with tempfile.TemporaryDirectory(prefix='managed-owned-root-') as tmp:
            root=Path(tmp).resolve();(root/'child').mkdir()
            task,s=fixture(str(root));first=s.assignments[0]
            first=replace(first,owned_paths=['child/result.txt'],payload=replace(first.payload,owned_paths=['child/result.txt']))
            second=replace(first,assignment_id='worker-02',worktree_root=str(root/'child'),owned_paths=['result.txt'],
                payload=replace(first.payload,owned_paths=['result.txt']))
            collision=replace(s,plan=replace(s.plan,assignment_ids=['worker-01','worker-02']),assignments=[first,second])
            for check in [lambda wire:semantics.check_snapshot(wire,task,mode='managed'),
                    lambda wire:semantics.check_ownership(wire,mode='managed')]:
                with self.assertRaises(c.ValidationError) as raised:check(d.delivery_to_dict(collision))
                self.assertIn('ownership_overlap',[error.code for error in raised.exception.errors])
            first=replace(first,owned_paths=['outer.txt'],payload=replace(first.payload,owned_paths=['outer.txt']))
            valid=replace(collision,assignments=[first,second])
            semantics.check_snapshot(d.delivery_to_dict(valid),task,mode='managed')
            terminal=replace(collision,assignments=[replace(collision.assignments[0],state='cancelled'),second])
            semantics.check_snapshot(d.delivery_to_dict(terminal),task,mode='managed')

    def test_C01_R1_managed_physical_transfer_needs_source_across_workspaces(self):
        from dataclasses import replace
        from smart_assistant import delivery_semantics as semantics
        from tests.test_delivery_records import decision
        with tempfile.TemporaryDirectory(prefix='managed-transfer-') as tmp:
            root=Path(tmp).resolve();(root/'child').mkdir()
            task,before=fixture(str(root));first=before.assignments[0]
            first=replace(first,owned_paths=['child/result.txt'],payload=replace(first.payload,owned_paths=['child/result.txt']))
            before=replace(before,assignments=[first])
            second=replace(first,assignment_id='worker-02',worktree_root=str(root/'child'),workspace_id='other-project',
                owned_paths=['result.txt'],payload=replace(first.payload,owned_paths=['result.txt']))
            after=replace(before,revision=2,previous_sha256=d.delivery_digest(before),
                plan=replace(before.plan,revision=2,assignment_ids=['worker-01','worker-02']),
                assignments=[replace(first,revision=2,state='cancelled'),second])
            source=f'assignment:{first.assignment_id}:{first.revision}:{d.delivery_digest(first)}'
            receipt=decision(after,'transfer-01','reassignment',second.assignment_id,1,refs=[source])
            valid=replace(after,decisions=[receipt])
            semantics.check_snapshot(d.delivery_to_dict(valid),task,mode='managed')
            semantics.check_history(d.delivery_to_dict(valid),d.delivery_to_dict(before),mode='managed')
            for receipts in [[],[replace(receipt,evidence_refs=['unrelated'])],
                    [replace(receipt,assignment_id=first.assignment_id)],
                    [replace(receipt,assignment_revision=2)]]:
                with self.subTest(receipts=receipts):
                    with self.assertRaises(c.ValidationError) as raised:
                        semantics.check_history(d.delivery_to_dict(replace(after,decisions=receipts)),d.delivery_to_dict(before),mode='managed')
                    self.assertIn('history_mismatch',[error.code for error in raised.exception.errors])
