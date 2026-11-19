"""P08 handoff acceptance against real isolated files."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from smart_assistant import contracts


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'outputs').mkdir()
        (self.root / 'evidence').mkdir()
        (self.root / 'outputs/result.md').write_text('actual output\n')
        (self.root / 'evidence/check.md').write_text('actual observation\n')
        fixtures = Path(__file__).resolve().parents[1] / 'examples/contracts'
        self.assignment = json.loads((fixtures / 'TaskAssignment.json').read_text())
        self.assignment['owned_paths'] = ['outputs/result.md']
        self.handoff = json.loads((fixtures / 'Handoff.json').read_text())
        self.handoff.update(artifacts=[{'id': 'result-01', 'relative_path': 'outputs/result.md',
            'sha256': hashlib.sha256((self.root / 'outputs/result.md').read_bytes()).hexdigest()}],
            criteria_coverage={'criterion-01': ['evidence/check.md']},
            evidence_refs=['evidence/check.md'], next_step='Obtain independent review')

    def gate(self):
        # Initial RED must be a meaningful assertion of missing behavior.
        validator = getattr(contracts, 'validate_handoff', None)
        self.assertIsNotNone(validator, 'P08 validate_handoff is not implemented')
        return validator(contracts.from_dict('TaskAssignment', self.assignment),
                         contracts.from_dict('Handoff', self.handoff), self.root)

    def rejects(self, code):
        result = self.gate()
        self.assertFalse(result.passed)
        self.assertIn(code, [error.code for error in result.errors])

    def test_valid_ready(self):
        self.assertTrue(self.gate().passed)

    def test_wrong_task(self):
        self.handoff['task_id'] = 'different-task'
        self.rejects('wrong_task')

    def test_stale_revision(self):
        self.assignment['assignment_revision'] = 2
        self.rejects('stale_assignment')

    def test_wrong_role(self):
        self.handoff['role_id'] = 'other-role'
        self.rejects('wrong_role')

    def test_outside_exact_file_ownership(self):
        self.assignment['owned_paths'] = ['outputs']
        self.rejects('outside_ownership')

    def test_missing_artifact(self):
        (self.root / 'outputs/result.md').unlink()
        self.rejects('missing_artifact')

    def test_tampered_hash(self):
        (self.root / 'outputs/result.md').write_text('changed')
        self.rejects('artifact_digest_mismatch')

    def test_unknown_criterion(self):
        self.handoff['criteria_coverage']['unknown-criterion'] = ['evidence/check.md']
        self.rejects('unknown_criterion')

    def test_incomplete_ready_coverage(self):
        self.handoff['criteria_coverage'] = {}
        self.rejects('incomplete_coverage')

    def test_empty_coverage_evidence(self):
        self.handoff['criteria_coverage']['criterion-01'] = []
        self.rejects('incomplete_coverage')

    def test_missing_evidence(self):
        (self.root / 'evidence/check.md').unlink()
        self.rejects('missing_evidence')

    def test_uri_evidence(self):
        self.handoff['evidence_refs'] = ['test:claimed']
        self.rejects('invalid_evidence_path')

    def test_traversal_coverage(self):
        self.handoff['criteria_coverage']['criterion-01'] = ['../outside']
        self.rejects('invalid_evidence_path')

    def test_symlink_file(self):
        output = self.root / 'outputs/result.md'
        output.unlink()
        output.symlink_to(self.root / 'evidence/check.md')
        self.rejects('invalid_artifact_path')

    def test_symlink_directory(self):
        output = self.root / 'outputs/result.md'
        output.unlink()
        (self.root / 'outputs').rmdir()
        (self.root / 'outputs').symlink_to(self.root / 'evidence', target_is_directory=True)
        self.rejects('invalid_artifact_path')

    def test_fifo_does_not_block(self):
        output = self.root / 'outputs/result.md'
        output.unlink()
        os.mkfifo(output)
        self.rejects('invalid_artifact_path')

    def test_duplicate_artifact_id(self):
        self.handoff['artifacts'] *= 2
        self.rejects('duplicate_artifact')

    def test_duplicate_criteria(self):
        self.assignment['criteria'] *= 2
        self.rejects('invalid_assignment')

    def test_empty_ownership(self):
        self.assignment['owned_paths'] = []
        self.rejects('invalid_assignment')

    def test_empty_criteria(self):
        self.assignment['criteria'] = []
        self.rejects('invalid_assignment')

    def test_empty_ready_artifacts(self):
        self.handoff['artifacts'] = []
        self.rejects('missing_artifact')

    def test_ready_with_blocker(self):
        self.handoff['blocker'] = 'not resolved'
        self.rejects('inconsistent_handoff')

    def test_ready_without_next_step(self):
        self.handoff['next_step'] = ' '
        self.rejects('missing_next_step')

    def test_blocked_partial_never_ready(self):
        self.handoff.update(result='blocked', blocker='Required input missing', next_step='Supply input')
        self.rejects('blocked_child')

    def test_failed_child(self):
        self.handoff.update(result='failed', blocker='Tool failed', next_step='Repair tool')
        self.rejects('failed_child')

    def test_blocked_without_reason(self):
        self.handoff.update(result='blocked', blocker=' ', next_step='Supply input')
        self.rejects('missing_blocker')

    def test_blocked_empty_partial_is_valid_but_rejected(self):
        self.handoff.update(result='blocked', blocker='No input', artifacts=[], criteria_coverage={},
                            evidence_refs=[], next_step='Supply input')
        self.assertEqual(['blocked_child'], [e.code for e in self.gate().errors])

    def test_different_cwd(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as other:
            try:
                os.chdir(other)
                self.assertTrue(self.gate().passed)
            finally:
                os.chdir(previous)

    def test_relative_root(self):
        self.root = Path('.')
        self.rejects('invalid_artifact_root')

    def test_symlink_root(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.root = alias
        self.rejects('invalid_artifact_root')

    def test_dataclass_nested_wire_normalized(self):
        a = contracts.from_dict('TaskAssignment', self.assignment)
        h = contracts.from_dict('Handoff', self.handoff)
        a.criteria = self.assignment['criteria']
        h.artifacts = self.handoff['artifacts']
        validator = getattr(contracts, 'validate_handoff', None)
        self.assertIsNotNone(validator, 'P08 validate_handoff is not implemented')
        self.assertTrue(validator(a, h, self.root).passed)

    def test_invalid_record_returns_gate(self):
        validator = getattr(contracts, 'validate_handoff', None)
        self.assertIsNotNone(validator, 'P08 validate_handoff is not implemented')
        self.assertFalse(validator(None, None, self.root).passed)


if __name__ == '__main__':
    unittest.main()
