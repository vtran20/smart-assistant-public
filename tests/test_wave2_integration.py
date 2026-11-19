"""Wave 2 boundary tests. All proof is synthetic and all state is temporary."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from smart_assistant.agent_lifecycle import stage_agent, validate_agent_definition
from smart_assistant.skill_lifecycle import stage_skill
from smart_assistant.catalog import load_catalog, validate_catalog
from smart_assistant.contracts import (
    Artifact, CapabilityCatalog, CapabilityKind, CapabilityRecord, CapabilityState,
    CheckMethod, CheckOutcome, CheckReceipt, Criterion, CycleEvidence, Limits,
    NativeProbeReceipt, ProbePurpose, ReviewReceipt, Selection, TaskPhase,
    TaskRecord, TaskStatus, ValidationError, from_dict, to_dict,
)
from smart_assistant.lifecycle import DeploymentStore
from smart_assistant.quality import acceptance_snapshot, completion_gate, snapshot
from smart_assistant.state import TaskStore

ROOT = Path(__file__).resolve().parents[1]
STAMP = '2026-10-13T12:00:00Z'
CYCLE = 'Follow design, implement, independent review, feedback, test and repeat until acceptance passes.'


class WaveTwoIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / 'state'
        self.project = self.root / 'project'
        self.project.mkdir()
        self.write_json(self.project / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [])))

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def cli(self, status, *args):
        result = subprocess.run([sys.executable, '-m', 'smart_assistant', *map(str, args)],
                                cwd=ROOT, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, status, (result.stdout, result.stderr))
        self.assertEqual(result.stderr, '')
        response = json.loads(result.stdout)
        self.assertEqual(set(response), {'ok', 'data', 'errors'})
        self.assertIs(response['ok'], status == 0)
        self.assertEqual(bool(response['errors']), status != 0)
        return response

    def task_fixture(self, status=TaskStatus.VERIFYING, blockers=None, outcome=CheckOutcome.PASS):
        outputs = self.root / 'outputs'
        outputs.mkdir()
        (outputs / 'design.md').write_text('Produce a count of supplied local lines.\n')
        (outputs / 'report.txt').write_text('Count: 2\n')
        request = from_dict('RequestEnvelope', {
            'schema_version': 1, 'request_id': 'fixture-request', 'text': 'Count supplied lines',
            'project_id': 'fixture-project', 'source_refs': ['synthetic:user'], 'requested_role': None,
        })
        task = TaskRecord(1, 'fixture-task', 1, request, status, TaskPhase.TESTING, None, [],
                          [Criterion('fixture-count', 'Count is correct', 'Inspect local report')],
                          Selection(1, [], []), Limits(), [], [], [], blockers or [],
                          'Retry the count check', str(outputs))
        return replace(task, cycles=[self.cycle(task, 1, outcome)])

    def cycle(self, task, number, outcome=CheckOutcome.PASS):
        outputs = Path(task.artifact_root)
        (outputs / f'check-{number}.log').write_text('Synthetic local report observation.\n')
        candidate = snapshot(outputs, [Artifact('fixture-report', 'report.txt', '0' * 64)])
        acceptance = acceptance_snapshot(task.criteria, outputs / 'design.md')
        review = ReviewReceipt('fixture-reviewer', 'fixture-writer', candidate.candidate_id,
                               acceptance.acceptance_id, STAMP, [])
        check = CheckReceipt(f'fixture-check-{number}', ['fixture-count'], candidate.candidate_id,
                             acceptance.acceptance_id, CheckMethod.OBSERVATION, None,
                             'Synthetic fixture count inspected', {'fixture': 'integration-only'},
                             outcome, f'check-{number}.log', STAMP)
        return CycleEvidence(number, 'design.md', candidate, acceptance, review, [], [check])

    def update_cli(self, task, status=0):
        path = self.write_json(self.root / 'task-input.json', to_dict(task))
        return self.cli(status, 'task', 'update', '--record', path,
                        '--expected-revision', task.revision, '--state-dir', self.state)

    def complete_cli(self, task, status=0):
        return self.cli(status, 'task', 'complete', task.id,
                        '--expected-revision', task.revision, '--state-dir', self.state)

    def saved_bytes(self):
        return (self.state / 'tasks/fixture-task.json').read_bytes()

    def test_store_seeded_cli_completion_requires_resolved_blockers_and_fresh_cycle(self):
        store = TaskStore(self.state, completion_check=completion_gate)
        current = store.create(self.task_fixture(blockers=['Need supplied source']))
        before = self.saved_bytes()
        self.assertIn('unresolved_blockers', [e['code'] for e in self.complete_cli(current, 4)['errors']])
        self.update_cli(replace(current, status=TaskStatus.COMPLETED), 4)
        self.assertEqual(self.saved_bytes(), before)
        self.update_cli(replace(current, blockers=[]))
        current = store.read(current.id)
        (Path(current.artifact_root) / 'report.txt').write_text('Count: 3\n')
        before = self.saved_bytes()
        self.assertIn('stale_candidate', [e['code'] for e in self.complete_cli(current, 4)['errors']])
        self.update_cli(replace(current, status=TaskStatus.COMPLETED), 4)
        self.assertEqual(self.saved_bytes(), before)
        self.update_cli(replace(current, cycles=[*current.cycles, self.cycle(current, 2)]))
        current = store.read(current.id)
        self.complete_cli(current)
        completed = store.read(current.id)
        self.assertEqual((completed.status, completed.revision), (TaskStatus.COMPLETED, 4))
        self.assertEqual(completed.cycles[0], current.cycles[0])
        self.assertTrue(completion_gate(completed).passed)

    def test_failed_store_record_cli_resume_preserves_failed_history_until_fresh_success(self):
        store = TaskStore(self.state, completion_check=completion_gate)
        failed = store.create(self.task_fixture(TaskStatus.FAILED, outcome=CheckOutcome.FAIL))
        proposed = replace(failed, status=TaskStatus.RUNNING, phase=TaskPhase.IMPLEMENT,
                           resume_next_step='Repeat failed count inspection')
        before = self.saved_bytes()
        with self.assertRaises(ValidationError):
            store.update(proposed, failed.revision)
        self.assertEqual(self.saved_bytes(), before)
        self.update_cli(proposed)
        resumed = store.read(failed.id)
        self.assertEqual((resumed.status, resumed.revision), (TaskStatus.RUNNING, 2))
        self.assertEqual(resumed.cycles, failed.cycles)
        self.assertEqual(resumed.resume_next_step, 'Repeat failed count inspection')
        before = self.saved_bytes()
        for rewritten in ([], [replace(resumed.cycles[0], design_ref='rewritten.md')]):
            with self.subTest(history=rewritten):
                denied = self.update_cli(replace(resumed, cycles=rewritten), 2)
                self.assertIn('history_changed', [e['code'] for e in denied['errors']])
                self.assertEqual(self.saved_bytes(), before)
        self.update_cli(replace(resumed, status=TaskStatus.VERIFYING, phase=TaskPhase.TESTING,
                                cycles=[*resumed.cycles, self.cycle(resumed, 2)]))
        self.complete_cli(store.read(failed.id))
        completed = store.read(failed.id)
        self.assertEqual([c.checks[0].outcome for c in completed.cycles],
                         [CheckOutcome.FAIL, CheckOutcome.PASS])
        self.assertEqual((completed.status, completed.revision), (TaskStatus.COMPLETED, 4))

    def staged_pair(self):
        definitions = self.project / 'definitions'
        definitions.mkdir()
        agent = definitions / 'original-input.toml'
        agent.write_text('name = "fixture-agent"\ndescription = "Extract supplied facts."\n'
                         + 'developer_instructions = ' + json.dumps(CYCLE) + '\n')
        agent_record = CapabilityRecord(1, 'fixture-agent', CapabilityKind.AGENT,
            'Fixture Agent', '1.0.0', CapabilityState.DRAFT, 'placeholder',
            '.codex/agents/named-target.toml', None, ['extract supplied facts'],
            ['supplied local input only'], ['text'], 'facts', ['tool:extract'], [], None, None)
        skill = definitions / 'fixture-list'
        skill.mkdir()
        skill_text = ('---\nname: fixture-list\ndescription: Use when counting supplied local lines.\n---\n'
                      'Use when asked to count a supplied local list. Output a count. Verify the count.\n'
                      + CYCLE + '\nRun `scripts/count.py` and read [scope](references/scope.txt).\n')
        files = {'SKILL.md': skill_text.encode(),
                 'scripts/count.py': b'import sys\nprint(sum(bool(line.strip()) for line in sys.stdin))\n',
                 'references/scope.txt': b'Supplied local lines only.\n'}
        for relative, data in files.items():
            path = skill / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        skill_record = CapabilityRecord(1, 'fixture-skill', CapabilityKind.SKILL,
            'fixture-list', '1.0.0', CapabilityState.DRAFT, 'placeholder', None, None,
            ['count supplied lines'], ['local input only'], ['list'], 'count',
            ['tool:local-read'], [], None, None)
        staged = [stage_agent(self.project, agent, agent_record), stage_skill(self.project, skill, skill_record)]
        expected = [{'named-target.toml': agent.read_bytes()}, files]
        for record, complete_files in zip(staged, expected):
            # Independent wire digest: no product manifest builder computes expectations.
            wire = [{'relative_path': p, 'sha256': hashlib.sha256(data).hexdigest()}
                    for p, data in sorted(complete_files.items())]
            digest = hashlib.sha256(json.dumps(wire, sort_keys=True, separators=(',', ':'),
                                               ensure_ascii=False).encode()).hexdigest()
            self.assertEqual(record.deployed_sha256, digest)
        return staged, expected

    def ready_fixture(self, record, passed=True):
        """Distinct temporary evidence; never claim real agent evaluation/native discovery."""
        evidence = f'evidence/{record.id}-observation.txt'
        if record.kind == CapabilityKind.SKILL:
            observed = subprocess.run([sys.executable, self.project / record.source_path / 'scripts/count.py'],
                                      input='alpha\n\nbeta\n', text=True, capture_output=True, timeout=15)
            self.assertEqual((observed.returncode, observed.stdout, observed.stderr), (0, '2\n', ''))
            observation = 'Synthetic local script evaluation: input alpha/blank/beta; output 2.\n'
        else:
            self.assertTrue(validate_agent_definition(self.project / record.source_path).passed)
            observation = 'Synthetic contract fixture only; no agent invocation or semantic evaluation.\n'
        path = self.project / evidence
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(observation)
        refs = list(record.validation_refs)
        if not refs:
            structural = f'evidence/{record.id}-validation.json'
            self.write_json(self.project / structural, dict(schema_version=1, kind='validation',
                capability_id=record.id, version=record.version, manifest_sha256=record.deployed_sha256,
                passed=True, evidence_refs=[evidence]))
            refs.append(structural)
        evaluation = f'evidence/{record.id}-evaluation.json'
        self.write_json(self.project / evaluation, dict(schema_version=1, kind='evaluation',
            capability_id=record.id, version=record.version, manifest_sha256=record.deployed_sha256,
            passed=passed, evidence_refs=[evidence]))
        return replace(record, validation_refs=[*refs, evaluation])

    def synthetic_probe(self, record, operation, **changes):
        receipt = NativeProbeReceipt(1, operation, record.id, record.version, record.deployed_sha256,
            ProbePurpose.ACTIVATE, 'synthetic-contract-fixture', 'fixture-only',
            f'synthetic-session-{operation}', True, True,
            (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat().replace('+00:00', 'Z'),
            [f'evidence/{record.id}-observation.txt'])
        # Validate the unmodified fixture so negative cases cannot pass on bad setup.
        to_dict(receipt)
        return replace(receipt, **changes)

    def eligible_cli(self, tools):
        path = self.write_json(self.root / 'tools.json', tools)
        return self.cli(0, 'catalog', 'eligible', '--project-root', self.project, '--tools', path)['data']

    def test_staged_agent_and_complete_skill_compose_with_deployment_catalog_and_cli(self):
        staged, expected = self.staged_pair()
        self.assertEqual(load_catalog(self.project).records, [])
        store = DeploymentStore(self.project)
        for record, files in zip(staged, expected):
            ready = self.ready_fixture(record)
            revision = load_catalog(self.project).revision
            operation = store.prepare(ready, revision)
            self.assertEqual(self.eligible_cli(['tool:extract', 'tool:local-read']),
                             [] if revision == 1 else [to_dict(load_catalog(self.project).records[0])])
            store.finalize(operation, self.synthetic_probe(ready, operation))
            target = self.project / ready.deployed_path
            actual = {target.name: target.read_bytes()} if target.is_file() else {
                p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob('*') if p.is_file()}
            self.assertEqual(actual, files)
        catalog = load_catalog(self.project)
        self.assertEqual(catalog.revision, 3)
        self.assertTrue(validate_catalog(catalog, self.project).passed)
        self.assertEqual([r['id'] for r in self.eligible_cli(['tool:extract'])], ['fixture-agent'])
        self.assertEqual([r['id'] for r in self.eligible_cli(['tool:extract', 'tool:local-read'])],
                         ['fixture-agent', 'fixture-skill'])
        (self.project / staged[1].deployed_path / 'references/scope.txt').write_text('drift')
        self.assertFalse(validate_catalog(load_catalog(self.project), self.project).passed)
        self.assertEqual([r['id'] for r in self.eligible_cli(['tool:extract', 'tool:local-read'])],
                         ['fixture-agent'])

    def test_structural_receipts_and_failed_evaluations_never_authorize_prepare(self):
        staged, _ = self.staged_pair()
        store = DeploymentStore(self.project)
        before = (self.project / 'capabilities/catalog.json').read_bytes()
        for record in staged:
            with self.subTest(kind=record.kind):
                failed = self.ready_fixture(record, passed=False)
                structural = replace(failed, validation_refs=failed.validation_refs[:-1])
                for insufficient in (structural, failed):
                    with self.assertRaises(ValidationError):
                        store.prepare(insufficient, 1)
                    self.assertFalse((self.project / record.deployed_path).exists())
                    self.assertEqual((self.project / 'capabilities/catalog.json').read_bytes(), before)
                ready = self.ready_fixture(record)
                operation = store.prepare(ready, 1)
                store.restore(operation)
                self.assertFalse((self.project / record.deployed_path).exists())
                self.assertEqual((self.project / 'capabilities/catalog.json').read_bytes(), before)

    def test_resource_changed_after_skill_evaluation_denies_prepare(self):
        staged, _ = self.staged_pair()
        ready = self.ready_fixture(staged[1])
        before = (self.project / 'capabilities/catalog.json').read_bytes()
        (self.project / ready.source_path / 'references/scope.txt').write_text('Changed after evaluation')
        with self.assertRaises(ValidationError):
            DeploymentStore(self.project).prepare(ready, 1)
        self.assertFalse((self.project / ready.deployed_path).exists())
        self.assertEqual((self.project / 'capabilities/catalog.json').read_bytes(), before)
        self.assertEqual(self.eligible_cli(['tool:local-read']), [])

    def test_identity_version_manifest_and_agent_target_cannot_rebind_staged_proof(self):
        staged, _ = self.staged_pair()
        store = DeploymentStore(self.project)
        before = (self.project / 'capabilities/catalog.json').read_bytes()
        for record in staged:
            ready = self.ready_fixture(record)
            for mismatch in ({'capability_id': 'other-fixture'}, {'version': '9.0.0'},
                             {'manifest_sha256': '0' * 64}):
                with self.subTest(kind=record.kind, mismatch=mismatch):
                    operation = store.prepare(ready, 1)
                    with self.assertRaises(ValidationError):
                        store.finalize(operation, self.synthetic_probe(ready, operation, **mismatch))
                    self.assertFalse((self.project / ready.deployed_path).exists())
                    self.assertEqual((self.project / 'capabilities/catalog.json').read_bytes(), before)
        agent = self.ready_fixture(staged[0])
        with self.assertRaises(ValidationError):
            store.prepare(replace(agent, deployed_path='.codex/agents/rebound.toml'), 1)
        self.assertFalse((self.project / '.codex/agents/rebound.toml').exists())
        self.assertEqual(load_catalog(self.project).records, [])


if __name__ == '__main__':
    unittest.main()
