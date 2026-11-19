"""Real temporary files prove freshness, coverage and containment boundaries."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from smart_assistant.contracts import (
    Artifact, CandidateSnapshot, Criterion, AcceptanceSnapshot, CheckReceipt, CheckMethod,
    CheckOutcome, CycleEvidence, Disposition, DispositionDecision, Finding, ReviewReceipt,
    Severity, TaskRecord, RequestEnvelope, TaskStatus, TaskPhase, Selection, Limits,
    ValidationError,
)
from smart_assistant.quality import snapshot, acceptance_snapshot, completion_gate


ZERO = '0' * 64
STAMP = '2026-10-13T12:00:00Z'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = self.root / 'product.txt'
        self.product.write_bytes(b'first candidate')
        self.design = self.root / 'design.md'
        self.design.write_bytes(b'approved design')
        (self.root / 'check.log').write_bytes(b'checks pass')
        (self.root / 'fix.log').write_bytes(b'finding addressed')
        self.criteria = [Criterion('works', 'Product works', 'unit test')]
        self.artifacts = [Artifact('product', 'product.txt', ZERO)]

    def task(self):
        candidate = snapshot(self.root, self.artifacts)
        acceptance = acceptance_snapshot(self.criteria, self.design)
        review = ReviewReceipt('reviewer:b', 'implementer:a', candidate.candidate_id,
                               acceptance.acceptance_id, STAMP, [])
        check = CheckReceipt('unit', ['works'], candidate.candidate_id, acceptance.acceptance_id,
                             CheckMethod.COMMAND, 'python3 -m unittest', None, {'python': '3.11'},
                             CheckOutcome.PASS, 'check.log', STAMP)
        cycle = CycleEvidence(1, 'design.md', candidate, acceptance, review, [], [check])
        return TaskRecord(1, 'task', 1, RequestEnvelope(1, 'request', 'build', 'project', [], None),
                          TaskStatus.COMPLETED, TaskPhase.TESTING, None, [], copy.deepcopy(self.criteria),
                          Selection(1, [], []), Limits(), [], [], [cycle], [], '', str(self.root))

    def assert_code(self, task, code):
        result = completion_gate(task)
        self.assertFalse(result.passed, result)
        self.assertIn(code, [error.code for error in result.errors], result.errors)

    def test_snapshot_rehashes_bytes_and_uses_independent_canonical_digest(self):
        result = snapshot(self.root, self.artifacts)
        current = hashlib.sha256(b'first candidate').hexdigest()
        self.assertEqual(result.artifacts[0].sha256, current)
        self.assertEqual(result.candidate_id, digest([{'id': 'product', 'relative_path': 'product.txt',
                                                     'sha256': current}]))
        self.assertEqual(self.artifacts[0].sha256, ZERO)

    def test_acceptance_hashes_all_fields_and_current_design_bytes(self):
        result = acceptance_snapshot(self.criteria, self.design)
        self.assertEqual(result.acceptance_id, digest({'criteria': [{'id': 'works',
            'description': 'Product works', 'verification_method': 'unit test'}],
            'design_sha256': hashlib.sha256(b'approved design').hexdigest()}))
        self.criteria[0].description = 'Changed'
        self.assertEqual(result.criteria[0].description, 'Product works')

    def test_snapshot_sorts_artifacts_and_criteria_without_mutating_inputs(self):
        (self.root / 'second.txt').write_bytes(b'2')
        artifacts = [Artifact('zz', 'second.txt', ZERO), self.artifacts[0]]
        self.assertEqual([a.id for a in snapshot(self.root, artifacts).artifacts], ['product', 'zz'])
        self.assertEqual(artifacts[0].id, 'zz')
        criteria = [Criterion('zz', 'z', 'test'), self.criteria[0]]
        self.assertEqual([c.id for c in acceptance_snapshot(criteria, self.design).criteria], ['works', 'zz'])

    def test_valid_proposed_completed_record_passes_without_mutation(self):
        task = self.task()
        before = copy.deepcopy(task)
        self.assertTrue(completion_gate(task).passed)
        self.assertEqual(task, before)

    def test_mutated_artifact_requires_new_candidate_review_and_checks(self):
        task = self.task()
        self.product.write_bytes(b'changed after review')
        self.assert_code(task, 'stale_candidate')
        cycle = task.cycles[-1]
        cycle.candidate = snapshot(self.root, self.artifacts)
        self.assert_code(task, 'stale_review')
        cycle.review.candidate_id = cycle.candidate.candidate_id
        self.assert_code(task, 'stale_check')
        cycle.checks[0].candidate_id = cycle.candidate.candidate_id
        self.assertTrue(completion_gate(task).passed)

    def test_missing_artifact_fails(self):
        task = self.task()
        self.product.unlink()
        self.assert_code(task, 'missing_artifact')

    def test_criterion_description_or_method_changes_invalidate_same_ids(self):
        for field in ['description', 'verification_method']:
            task = self.task()
            setattr(task.criteria[0], field, 'changed')
            with self.subTest(field=field):
                self.assert_code(task, 'stale_acceptance')

    def test_changed_design_invalidates_acceptance(self):
        task = self.task()
        self.design.write_bytes(b'changed design')
        self.assert_code(task, 'stale_acceptance')

    def test_review_and_check_acceptance_fingerprints_must_match(self):
        for target, code in [('review', 'stale_review'), ('check', 'stale_check')]:
            task = self.task()
            receipt = task.cycles[0].review if target == 'review' else task.cycles[0].checks[0]
            receipt.acceptance_id = ZERO
            with self.subTest(target=target):
                self.assert_code(task, code)

    def test_same_reviewer_and_implementer_rejects(self):
        task = self.task()
        task.cycles[0].review.reviewer_ref = 'implementer:a'
        self.assert_code(task, 'same_reviewer_implementer')

    def test_missing_cycles_or_review_fails(self):
        task = self.task()
        task.cycles = []
        self.assert_code(task, 'missing_review')
        task = self.task()
        task.cycles[0].review = None
        self.assert_code(task, 'missing_review')

    def finding_task(self):
        task = self.task()
        task.cycles[0].review.findings = [Finding('bug', Severity.MAJOR, 'Broken case', ['works'])]
        return task

    def test_unresolved_finding_fails(self):
        self.assert_code(self.finding_task(), 'unresolved_feedback')

    def test_disposition_requires_real_local_evidence(self):
        task = self.finding_task()
        cycle = task.cycles[0]
        cycle.dispositions = [Disposition('bug', DispositionDecision.CORRECTED, 'Fixed', [])]
        self.assert_code(task, 'unresolved_feedback')
        cycle.dispositions[0].evidence_refs = ['fix.log']
        self.assertTrue(completion_gate(task).passed)
        (self.root / 'fix.log').unlink()
        self.assert_code(task, 'missing_evidence')

    def test_rejected_finding_with_evidence_is_resolved(self):
        task = self.finding_task()
        task.cycles[0].dispositions = [Disposition('bug', DispositionDecision.REJECTED,
                                                'Reproduced desired behavior', ['fix.log'])]
        self.assertTrue(completion_gate(task).passed)

    def test_duplicate_or_orphan_dispositions_fail(self):
        for refs in [['orphan'], ['bug', 'bug']]:
            task = self.finding_task()
            task.cycles[0].dispositions = [Disposition(ref, DispositionDecision.CORRECTED,
                                                     'Fixed', ['fix.log']) for ref in refs]
            with self.subTest(refs=refs):
                self.assert_code(task, 'invalid_dispositions')

    def test_duplicate_findings_or_unknown_criterion_reference_fail(self):
        for change in ['duplicate', 'unknown']:
            task = self.finding_task()
            if change == 'duplicate':
                task.cycles[0].review.findings *= 2
            else:
                task.cycles[0].review.findings[0].criterion_ids = ['unknown']
            with self.subTest(change=change):
                self.assert_code(task, 'invalid_findings')

    def test_failed_checks_or_missing_coverage_fail(self):
        task = self.task()
        task.cycles[0].checks[0].outcome = CheckOutcome.FAIL
        self.assert_code(task, 'failed_check')
        task = self.task()
        task.cycles[0].checks = []
        self.assert_code(task, 'missing_criterion_coverage')
        task = self.task()
        task.cycles[0].checks[0].criterion_ids = []
        self.assert_code(task, 'missing_criterion_coverage')

    def test_duplicate_checks_or_unknown_coverage_fails(self):
        for change in ['duplicate', 'unknown']:
            task = self.task()
            if change == 'duplicate':
                task.cycles[0].checks *= 2
            else:
                task.cycles[0].checks[0].criterion_ids = ['unknown']
            with self.subTest(change=change):
                self.assert_code(task, 'invalid_checks')

    def test_every_criterion_requires_coverage(self):
        self.criteria.append(Criterion('other', 'Other requirement', 'manual observation'))
        task = self.task()
        self.assert_code(task, 'missing_criterion_coverage')
        check = replace(task.cycles[0].checks[0], check_id='other-check', criterion_ids=['other'],
                        method=CheckMethod.OBSERVATION, command=None, observation='Observed requirement')
        task.cycles[0].checks.append(check)
        self.assertTrue(completion_gate(task).passed)

    def test_missing_check_evidence_rejects_passing_claim(self):
        task = self.task()
        (self.root / 'check.log').unlink()
        self.assert_code(task, 'missing_evidence')

    def test_empty_or_duplicate_criteria_never_complete(self):
        task = self.task()
        task.criteria = []
        self.assert_code(task, 'invalid_criteria')
        task = self.task()
        task.criteria *= 2
        self.assert_code(task, 'invalid_criteria')

    def test_empty_candidate_cannot_complete(self):
        task = self.task()
        task.cycles[0].candidate = CandidateSnapshot([], digest([]))
        self.assert_code(task, 'invalid_candidate')

    def test_old_failed_cycle_does_not_block_new_passing_cycle(self):
        task = self.task()
        previous = copy.deepcopy(task.cycles[0])
        previous.checks[0].outcome = CheckOutcome.FAIL
        task.cycles[0].cycle_number = 2
        task.cycles.insert(0, previous)
        self.assertTrue(completion_gate(task).passed)

    def test_latest_failed_cycle_does_not_fall_back_to_passing_history(self):
        task = self.task()
        latest = copy.deepcopy(task.cycles[0])
        latest.cycle_number = 2
        latest.checks[0].outcome = CheckOutcome.FAIL
        task.cycles.append(latest)
        self.assert_code(task, 'failed_check')

    def test_duplicate_or_descending_cycle_numbers_fail(self):
        for numbers in [(1, 1), (2, 1)]:
            task = self.task()
            task.cycles.append(copy.deepcopy(task.cycles[0]))
            for cycle, number in zip(task.cycles, numbers):
                cycle.cycle_number = number
            with self.subTest(numbers=numbers):
                self.assert_code(task, 'invalid_cycle_history')

    def test_absolute_parent_uri_and_backslash_evidence_reject(self):
        for path in ['/etc/passwd', '../outside', 'https://example.com/log', 'dir\\log', './check.log']:
            task = self.task()
            task.cycles[0].checks[0].evidence_ref = path
            with self.subTest(path=path):
                self.assert_code(task, 'invalid_evidence_path')

    def test_evidence_directory_is_not_a_receipt_file(self):
        task = self.task()
        task.cycles[0].checks[0].evidence_ref = '.'
        self.assert_code(task, 'invalid_evidence_path')
        (self.root / 'logs').mkdir()
        task.cycles[0].checks[0].evidence_ref = 'logs'
        self.assert_code(task, 'invalid_evidence_path')

    def test_evidence_symlink_and_directory_symlink_escape_reject(self):
        task = self.task()
        (self.root / 'alias.log').symlink_to(self.root / 'check.log')
        task.cycles[0].checks[0].evidence_ref = 'alias.log'
        self.assert_code(task, 'invalid_evidence_path')
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / 'proof').write_bytes(b'outside proof')
            (self.root / 'escape').symlink_to(outside, target_is_directory=True)
            task.cycles[0].checks[0].evidence_ref = 'escape/proof'
            self.assert_code(task, 'invalid_evidence_path')

    def test_artifact_and_design_symlinks_reject(self):
        task = self.task()
        self.product.unlink()
        self.product.symlink_to(self.design)
        self.assert_code(task, 'invalid_artifact_path')
        self.product.unlink()
        self.product.write_bytes(b'first candidate')
        task = self.task()
        self.design.unlink()
        self.design.symlink_to(self.product)
        self.assert_code(task, 'invalid_evidence_path')

    def test_receipt_file_cannot_be_candidate_artifact(self):
        self.artifacts.append(Artifact('receipt', 'check.log', ZERO))
        self.assert_code(self.task(), 'evidence_as_artifact')

    def test_snapshot_rejects_bad_paths_duplicate_paths_and_missing_files(self):
        for artifacts in [[Artifact('bad', '../outside', ZERO)],
                          [self.artifacts[0], Artifact('second', 'product.txt', ZERO)],
                          [Artifact('missing', 'missing.txt', ZERO)]]:
            with self.subTest(artifacts=artifacts), self.assertRaises(ValidationError):
                snapshot(self.root, artifacts)

    def test_standalone_acceptance_rejects_empty_duplicate_and_symlink_design(self):
        for criteria in [[], self.criteria * 2]:
            with self.subTest(criteria=criteria), self.assertRaises(ValidationError):
                acceptance_snapshot(criteria, self.design)
        alias = self.root / 'alias.md'
        alias.symlink_to(self.design)
        with self.assertRaises(ValidationError):
            acceptance_snapshot(self.criteria, alias)

    def test_malformed_task_returns_structured_failure(self):
        for value in [None, {}, self.task()]:
            if isinstance(value, TaskRecord):
                value.cycles[0].checks[0].outcome = 'success'
            with self.subTest(value=value):
                result = completion_gate(value)
                self.assertFalse(result.passed)
                self.assertTrue(result.errors)

    def test_hardlinked_receipt_alias_cannot_hide_as_product_artifact(self):
        import os
        os.link(self.root / 'check.log', self.root / 'receipt-copy.txt')
        self.artifacts.append(Artifact('receipt-copy', 'receipt-copy.txt', ZERO))
        self.assert_code(self.task(), 'evidence_as_artifact')

    def test_missing_design_and_disposition_escape_are_rejected(self):
        task = self.task()
        self.design.unlink()
        self.assert_code(task, 'missing_evidence')
        self.design.write_bytes(b'approved design')
        task = self.finding_task()
        task.cycles[0].dispositions = [Disposition('bug', DispositionDecision.CORRECTED,
                                                 'Fixed', ['../outside-proof'])]
        self.assert_code(task, 'invalid_evidence_path')

    def test_fifo_evidence_rejects_without_blocking(self):
        import os
        os.mkfifo(self.root / 'pipe')
        task = self.task()
        task.cycles[0].checks[0].evidence_ref = 'pipe'
        self.assert_code(task, 'invalid_evidence_path')

    def test_artifact_root_requires_existing_absolute_directory(self):
        task = self.task()
        for root in ['.', str(self.root / 'absent'), str(self.product)]:
            task.artifact_root = root
            with self.subTest(root=root):
                self.assert_code(task, 'invalid_artifact_path')

    def test_nested_regular_files_are_supported(self):
        nested = self.root / 'nested'
        nested.mkdir()
        self.product.rename(nested / 'product.txt')
        self.design.rename(nested / 'design.md')
        (self.root / 'check.log').rename(nested / 'check.log')
        self.artifacts = [Artifact('product', 'nested/product.txt', ZERO)]
        self.design = nested / 'design.md'
        task = self.task()
        task.cycles[0].design_ref = 'nested/design.md'
        task.cycles[0].checks[0].evidence_ref = 'nested/check.log'
        self.assertTrue(completion_gate(task).passed)

    def test_raw_nested_wire_records_normalize_without_mutating_input(self):
        from smart_assistant.contracts import to_dict
        for target in ['cycle', 'review', 'candidate', 'acceptance', 'artifact', 'check',
                       'finding', 'disposition', 'criterion']:
            task = self.finding_task()
            cycle = task.cycles[0]
            cycle.dispositions = [Disposition('bug', DispositionDecision.CORRECTED,
                                             'Fixed', ['fix.log'])]
            if target == 'cycle':
                task.cycles[0] = to_dict(cycle)
            elif target in ['review', 'candidate', 'acceptance']:
                setattr(cycle, target, to_dict(getattr(cycle, target)))
            elif target == 'artifact':
                cycle.candidate.artifacts[0] = to_dict(cycle.candidate.artifacts[0])
            elif target == 'check':
                cycle.checks[0] = to_dict(cycle.checks[0])
            elif target == 'finding':
                cycle.review.findings[0] = to_dict(cycle.review.findings[0])
            elif target == 'disposition':
                cycle.dispositions[0] = to_dict(cycle.dispositions[0])
            else:
                task.criteria[0] = to_dict(task.criteria[0])
            before = copy.deepcopy(task)
            with self.subTest(target=target):
                self.assertTrue(completion_gate(task).passed)
                self.assertEqual(task, before)

    def test_raw_check_outcomes_preserve_failure_and_input(self):
        for outcome, passed in [('pass', True), ('fail', False)]:
            task = self.task()
            task.cycles[0].checks[0].outcome = outcome
            task.cycles[0].checks[0].method = 'command'
            before = copy.deepcopy(task)
            with self.subTest(outcome=outcome):
                result = completion_gate(task)
                self.assertEqual(result.passed, passed)
                self.assertEqual(task, before)
                if not passed:
                    self.assertIn('failed_check', [error.code for error in result.errors])

    def test_raw_nested_failed_check_still_denies_completion(self):
        from smart_assistant.contracts import to_dict
        task = self.task()
        check = to_dict(task.cycles[0].checks[0])
        check['outcome'] = 'fail'
        task.cycles[0].checks[0] = check
        before = copy.deepcopy(task)
        self.assert_code(task, 'failed_check')
        self.assertEqual(task, before)

    def test_raw_nested_invalid_enum_returns_structured_error(self):
        from smart_assistant.contracts import to_dict
        task = self.task()
        cycle = to_dict(task.cycles[0])
        cycle['checks'][0]['outcome'] = 'unrecognized'
        task.cycles[0] = cycle
        before = copy.deepcopy(task)
        self.assert_code(task, 'invalid_enum')
        self.assertEqual(task, before)

    def test_standalone_snapshot_and_acceptance_reject_raw_top_level_dicts(self):
        from smart_assistant.contracts import to_dict
        for operation in [lambda: snapshot(self.root, [to_dict(self.artifacts[0])]),
                          lambda: acceptance_snapshot([to_dict(self.criteria[0])], self.design)]:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()
