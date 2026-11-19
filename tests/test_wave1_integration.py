"""Wave 1 composition uses only synthetic temporary state and evidence."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from smart_assistant.contracts import (
    Artifact, CheckMethod, CheckOutcome, CheckReceipt, Criterion, CycleEvidence,
    Limits, ReviewReceipt, Selection, TaskPhase, TaskRecord,
    TaskStatus, ValidationError, from_dict, to_dict,
)
from smart_assistant.state import TaskStore
from smart_assistant.quality import acceptance_snapshot, completion_gate, snapshot
from smart_assistant.catalog import eligible_capabilities, load_catalog, validate_catalog
from smart_assistant.preflight import preflight


class WaveOneIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.outputs = self.root / "outputs"
        self.outputs.mkdir()
        (self.outputs / "design.md").write_text("Produce and verify the report.\n")
        (self.outputs / "report.txt").write_text("The requested report is complete.\n")
        (self.outputs / "check.log").write_text("Synthetic integration check passed.\n")
        request = from_dict("RequestEnvelope", {
            "schema_version": 1, "request_id": "request_demo", "text": "Write a report",
            "project_id": "project_demo", "source_refs": ["synthetic:user"], "requested_role": None,
        })
        self.task = TaskRecord(
            1, "task_demo", 1, request, TaskStatus.QUEUED, TaskPhase.DESIGN, None, [],
            [Criterion("criterion_report", "Report is complete", "Inspect the report")],
            Selection(1, [], []), Limits(), [], [], [], [], "Start work", str(self.outputs),
        )

    def _verified(self, checker=completion_gate):
        store = TaskStore(self.root / "state", completion_check=checker)
        created = store.create(self.task)
        running = store.update(replace(created, status=TaskStatus.RUNNING, phase=TaskPhase.IMPLEMENT), created.revision)
        candidate = snapshot(self.outputs, [Artifact("artifact_report", "report.txt", "0" * 64)])
        acceptance = acceptance_snapshot(running.criteria, self.outputs / "design.md")
        observed = "2026-10-13T00:00:00Z"
        review = ReviewReceipt("independent_reviewer", "writer_agent", candidate.candidate_id, acceptance.acceptance_id, observed, [])
        check = CheckReceipt(
            "check_report", ["criterion_report"], candidate.candidate_id, acceptance.acceptance_id,
            CheckMethod.OBSERVATION, None, "Synthetic fixture report inspected",
            {"fixture": "integration-only"}, CheckOutcome.PASS, "check.log", observed,
        )
        cycle = CycleEvidence(1, "design.md", candidate, acceptance, review, [], [check])
        verifying = store.update(replace(running, status=TaskStatus.VERIFYING, phase=TaskPhase.TESTING, cycles=[cycle]), running.revision)
        return store, verifying

    def _assert_denied_without_persistence(self, store, verifying, proposed):
        record_path = self.root / "state" / "tasks" / "task_demo.json"
        before = record_path.read_bytes()
        with self.assertRaises(ValidationError):
            store.update(proposed, verifying.revision)
        self.assertEqual(record_path.read_bytes(), before)
        saved = store.read(verifying.id)
        self.assertEqual(saved.revision, verifying.revision)
        self.assertEqual(saved.status, TaskStatus.VERIFYING)

    def test_current_verified_evidence_completes_through_real_store_callback(self):
        store, verifying = self._verified()
        completed = store.update(replace(verifying, status=TaskStatus.COMPLETED), verifying.revision)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertEqual(completed.revision, verifying.revision + 1)
        self.assertTrue(completion_gate(store.read(completed.id)).passed)

    def test_wire_status_and_nested_cycles_normalize_across_store_and_checker(self):
        store, verifying = self._verified()
        wire_cycles = to_dict(verifying)["cycles"]
        proposed = replace(verifying, status="completed", cycles=wire_cycles)
        self.assertTrue(completion_gate(proposed).passed)
        completed = store.update(proposed, verifying.revision)
        self.assertIs(completed.status, TaskStatus.COMPLETED)
        self.assertEqual(completed.revision, verifying.revision + 1)
        self.assertIsInstance(completed.cycles[0], CycleEvidence)
        self.assertTrue(completion_gate(store.read(completed.id)).passed)

    def test_edited_artifact_denies_completion_and_keeps_store_unchanged(self):
        store, verifying = self._verified()
        (self.outputs / "report.txt").write_text("Edited after review.\n")
        proposed = replace(verifying, status=TaskStatus.COMPLETED)
        self.assertIn("stale_candidate", [e.code for e in completion_gate(proposed).errors])
        self._assert_denied_without_persistence(store, verifying, proposed)

    def test_changed_design_or_criterion_denies_completion_without_overwriting(self):
        for change in ("design", "criterion"):
            with self.subTest(change=change):
                # Each scenario creates its own store, avoiding another task's state.
                self.root = Path(self.temp.name) / change
                self.root.mkdir()
                self.outputs = self.root / "outputs"
                self.outputs.mkdir()
                (self.outputs / "design.md").write_text("Original design.\n")
                (self.outputs / "report.txt").write_text("Original report.\n")
                (self.outputs / "check.log").write_text("Synthetic check.\n")
                self.task = replace(self.task, artifact_root=str(self.outputs))
                store, verifying = self._verified()
                proposed = replace(verifying, status=TaskStatus.COMPLETED)
                if change == "design":
                    (self.outputs / "design.md").write_text("Changed design.\n")
                else:
                    proposed = replace(proposed, criteria=[Criterion("criterion_report", "Changed requirement", "Inspect the report")])
                self.assertIn("stale_acceptance", [e.code for e in completion_gate(proposed).errors])
                self._assert_denied_without_persistence(store, verifying, proposed)

    def test_failing_check_denies_completion_with_valid_snapshot_bindings(self):
        store, verifying = self._verified()
        cycle = verifying.cycles[-1]
        failed = replace(cycle, checks=[replace(cycle.checks[0], outcome=CheckOutcome.FAIL)])
        proposed = replace(verifying, status=TaskStatus.COMPLETED, cycles=[failed])
        self.assertIn("failed_check", [e.code for e in completion_gate(proposed).errors])
        self._assert_denied_without_persistence(store, verifying, proposed)

    def test_valid_evidence_cannot_complete_without_an_injected_checker(self):
        store, verifying = self._verified(checker=None)
        self.assertTrue(completion_gate(verifying).passed)
        self._assert_denied_without_persistence(store, verifying, replace(verifying, status=TaskStatus.COMPLETED))

    def test_empty_catalog_is_valid_and_does_not_route_uninstalled_capabilities(self):
        project = self.root / "catalog-project"
        (project / "capabilities").mkdir(parents=True)
        (project / "capabilities" / "catalog.json").write_text(json.dumps({"schema_version": 1, "revision": 1, "records": []}))
        catalog = load_catalog(project)
        self.assertTrue(validate_catalog(catalog, project).passed)
        self.assertEqual(eligible_capabilities(catalog, {"local_read"}, project), [])
        self.assertTrue(preflight(set(), {"local_read"}, [], []).ready)


if __name__ == "__main__":
    unittest.main()
