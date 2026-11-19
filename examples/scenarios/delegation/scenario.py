"""Deterministic hypothetical receipts: NOT native role, review or activation proof."""
from dataclasses import replace
import argparse
import contextlib
import io
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from smart_assistant.contracts import (Artifact, CheckMethod, CheckOutcome, CheckReceipt,
    Criterion, CycleEvidence, HandoffResult, Limits, ReviewReceipt, Selection,
    TaskPhase, TaskRecord, TaskStatus, ValidationError, from_dict, to_dict, validate_handoff)
from smart_assistant.quality import acceptance_snapshot, completion_gate, snapshot
from smart_assistant.state import TaskStore
from smart_assistant.cli import main as cli_main

CASES = ('positive', 'stale', 'ownership', 'blocked', 'cancelled', 'dependent', 'failed')


def run_case(case, root):
    if case not in CASES:
        raise ValueError('Unknown scenario')
    root = Path(root).resolve(strict=True)
    outputs = root / 'outputs'
    outputs.mkdir()
    history = root / 'hypothetical-history'
    history.mkdir()
    (root / 'design.md').write_text('HYPOTHETICAL: integrate required child outputs.\n')
    (root / 'check.log').write_text('HYPOTHETICAL stdlib fixture check; no native proof.\n')
    fixtures = Path(__file__).resolve().parents[2] / 'contracts'
    template = json.loads((fixtures / 'TaskAssignment.json').read_text())
    handoff_template = json.loads((fixtures / 'Handoff.json').read_text())
    request = from_dict('RequestEnvelope', dict(schema_version=1, request_id='request-demo',
        text='Hypothetical two-child scenario', project_id='project-demo',
        source_refs=['hypothetical:fixture'], requested_role=None))
    criteria = [Criterion('criterion-parent', 'Required outputs accepted', 'Inspect outputs')]
    parent = TaskRecord(1, 'parent-demo', 1, request, TaskStatus.QUEUED,
        TaskPhase.DESIGN, None, [], criteria, Selection(1, [], []), Limits(),
        [], [], [], [], 'Start hypothetical fixture', str(root))
    store = TaskStore(root / 'state', completion_check=completion_gate)
    parent = store.create(parent)
    parent = store.update(replace(parent, status=TaskStatus.RUNNING,
        phase=TaskPhase.IMPLEMENT), parent.revision)
    accepted, errors, timeline, artifacts, blockers = [], [], [], [], []
    for suffix in ('a', 'b'):
        child = 'child-' + suffix
        timeline.append('dispatch-' + suffix)
        assignment = dict(template, task_id=child, owned_paths=['outputs/' + suffix + '.md'])
        wire = dict(handoff_template, task_id=child)
        if suffix == 'b' and case == 'blocked':
            wire.update(result='blocked', artifacts=[], criteria_coverage={}, evidence_refs=[],
                blocker='Required input notes-b.md missing', next_step='Supply notes-b.md; refresh assignment')
        else:
            path = 'outputs/' + suffix + '.md'
            (root / path).write_text('HYPOTHETICAL child ' + suffix + ' output\n')
            artifact = Artifact('artifact-' + suffix, path,
                hashlib.sha256((root / path).read_bytes()).hexdigest())
            wire.update(artifacts=[vars(artifact)], criteria_coverage={'criterion-01': ['check.log']},
                evidence_refs=['check.log'], blocker=None, next_step='Obtain independent review')
            if suffix == 'b' and case == 'failed':
                wire.update(result='failed', blocker='Required child-b check failed; partial output retained',
                    next_step='Correct child-b, refresh assignment and independent review')
            if suffix == 'a' and case == 'stale':
                assignment['assignment_revision'] += 1
            if suffix == 'a' and case == 'ownership':
                assignment['owned_paths'] = ['outputs/other.md']
        typed_assignment = from_dict('TaskAssignment', assignment)
        handoff = from_dict('Handoff', wire)
        gate = validate_handoff(typed_assignment, handoff, root)
        # Save exact dispatch/rejection records before parent-state propagation.
        receipt = dict(hypothetical=True, assignment=to_dict(typed_assignment),
            handoff=to_dict(handoff), gate=to_dict(gate))
        with (history / (child + '.json')).open('x') as stream:
            json.dump(receipt, stream, indent=2)
        errors.extend(e.code for e in gate.errors)
        if not gate.passed:
            if handoff.result in (HandoffResult.BLOCKED, HandoffResult.FAILED):
                blockers.append(child + ': ' + handoff.blocker)
                parent = store.update(replace(parent, blockers=blockers,
                    resume_next_step=handoff.next_step), parent.revision)
            break
        accepted.append(child)
        artifacts.extend(handoff.artifacts)
        timeline.append('accept-' + suffix)
        if case == 'cancelled':
            parent = store.update(replace(parent, status=TaskStatus.CANCELLED,
                resume_next_step='Create a follow-up task; retain child-a output'), parent.revision)
            break
    completion_denied = resume_denied = False
    if case == 'cancelled':
        try:
            store.update(replace(parent, status=TaskStatus.RUNNING), parent.revision)
        except ValidationError:
            resume_denied = True
    elif case in ('positive', 'dependent', 'blocked', 'failed'):
        candidate = snapshot(root, artifacts)
        acceptance = acceptance_snapshot(criteria, root / 'design.md')
        observed = '2026-10-13T00:00:00Z'
        review = ReviewReceipt('hypothetical-reviewer', 'hypothetical-writer',
            candidate.candidate_id, acceptance.acceptance_id, observed, [])
        check = CheckReceipt('check-parent', ['criterion-parent'], candidate.candidate_id,
            acceptance.acceptance_id, CheckMethod.OBSERVATION, None,
            'HYPOTHETICAL helper fixture only, no native proof', {'kind': 'hypothetical'},
            CheckOutcome.PASS, 'check.log', observed)
        cycle = CycleEvidence(1, 'design.md', candidate, acceptance, review, [], [check])
        parent = store.update(replace(parent, status=TaskStatus.VERIFYING,
            phase=TaskPhase.TESTING, cycles=[cycle]), parent.revision)
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            code = cli_main(['task', 'complete', parent.id, '--expected-revision',
                str(parent.revision), '--state-dir', str(root / 'state')])
        reply = json.loads(capture.getvalue())
        completion_denied = code != 0
        if case in ('blocked', 'failed'):
            assert 'unresolved_blockers' in [e['code'] for e in reply['errors']]
        else:
            assert code == 0, reply
        parent = store.read(parent.id)
    with (history / 'parent-final.json').open('x') as stream:
        json.dump(to_dict(store.read(parent.id)), stream, indent=2)
    return dict(saved_dispatches=[json.loads(p.read_text()) for p in sorted(history.glob('child-*.json'))],
        hypothetical=True, accepted_children=accepted, errors=errors,
        parent_status=parent.status.value, parent_blockers=parent.blockers,
        completion_denied=completion_denied, resume_denied=resume_denied,
        preserved_outputs=sorted(str(p.relative_to(root)) for p in outputs.iterdir()), timeline=timeline)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='sa-p08-hypothetical-') as directory:
        print(json.dumps(run_case(args.case, Path(directory)), indent=2))
