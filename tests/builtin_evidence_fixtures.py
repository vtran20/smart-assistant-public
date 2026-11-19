"""SYNTHETIC builtin feature receipts; never native host or CLI execution proof.

The fixture uses actual strict records, receipt files and DeliveryStore history.
Only the host observations and semantic assertions are invented test data.
"""
from dataclasses import replace
import hashlib
from pathlib import Path

from smart_assistant import builtin_records as b, contracts as c, delivery_records as d
from smart_assistant import delivery_evidence as ev
from smart_assistant.delivery_store import DeliveryStore
from smart_assistant.delivery_gate import DeliveryEvidenceStore
from smart_assistant.state import TaskStore
from tests import test_delivery_evidence as p12_fixtures

AUTHORITY_AT = '2026-11-03T08:00:00Z'
STAMP = '2026-11-03T12:00:00Z'


def digest(value):
    return hashlib.sha256(value).hexdigest()


class BuiltinEvidenceFixture:
    """Prepared records, with explicit real persistence and evidence-save steps."""
    def __init__(self, data, state, history, workers):
        self.data = data
        self.state = state
        self.history = history
        self.workers = workers
        self.task = data.task
        self.delivery = history[-1]
        self.bundle = data.bundle
        self.tasks = TaskStore(state, lambda task: c.GateResult(True, []))
        self.deliveries = DeliveryStore(state)
        self.evidence = DeliveryEvidenceStore(state)

    def persist(self):
        """Never bypass registration/history or seed immutable store files directly."""
        self.task = self.tasks.create(self.task)
        current = self.deliveries.register(self.history[0], self.task.revision)
        self.task = self.tasks.update(replace(self.task, status=c.TaskStatus.VERIFYING),
                                      self.task.revision)
        for candidate in self.history[1:]:
            proposed = replace(candidate, revision=current.revision)
            current = self.deliveries.update(proposed, current.revision, self.task.revision)
            if current != candidate:
                raise AssertionError('Persisted transition differs from prepared strict history')
        self.delivery = current
        self.data.task = self.task
        return self

    def save(self, bundle=None, expected_revision=0):
        return self.evidence.save(self.task.id, self.bundle if bundle is None else bundle,
            expected_revision=expected_revision, expected_task_revision=self.task.revision,
            expected_delivery_revision=self.delivery.revision)

    def reseal(self, bundle):
        self.data.bundle = bundle
        self.data.seal()
        return self.data.bundle


def builtin_evidence_fixture(test, *, persist=True):
    """Build valid SYNTHETIC feature delivery, optionally persist through real APIs.

    ``test`` owns cleanup via addCleanup. No TestCase class is imported into test
    module scope, so unittest discovery does not duplicate the P12 test suite.
    ``persist=False`` exposes the same complete history for fixture-contract tests;
    persistence integration tests always use the default.
    """
    data = p12_fixtures.DeliveryEvidenceTests('test_valid_bug_codec_digest_and_no_mutation')
    data.setUp()
    test.addCleanup(data.doCleanups)
    base = data.root.resolve()
    final = base / 'final'
    final.mkdir()
    for name in ('product.txt', 'design.md', 'v1.log'):
        (base / name).replace(final / name)
    data.root = final
    # P12 root-independent candidate/acceptance remain exact after relocation.
    context = c.ContextBundle(1, data.task.request.project_id, {'fixture': 'SYNTHETIC'}, [])
    context_sha = digest(c.canonical_json(c.to_dict(context)))
    policy = replace(data.delivery.policy, workflow_kind='feature', reproduction_required=False)
    request = replace(data.task.request, text='SYNTHETIC builtin feature fixture',
                      source_refs=[d.policy_source_ref(policy)])
    decision = b.BuiltinDecision('2.0', data.task.id,
        b.base_request_digest(request, allow_unmarked=True), 'builtin',
        'SYNTHETIC:user:2026-11-03:option-b', 'root', AUTHORITY_AT,
        'SYNTHETIC explicit builtin feature fixture; no configured identity requested', False)
    request = replace(request, source_refs=[*request.source_refs, b.mode_source_ref(decision)])
    task = replace(data.task, request=request, status=c.TaskStatus.RUNNING,
                   artifact_root=str(final), requested_actions=[], authorization=[])
    request_sha = d.request_digest(request)
    registration = replace(data.delivery.registration, request_sha256=request_sha,
                           policy_sha256=d.delivery_digest(policy))
    plan = replace(data.delivery.plan, request_sha256=request_sha,
        policy_sha256=d.delivery_digest(policy), context_sha256=context_sha,
        assignment_ids=['assignment-0', 'assignment-1'], next_step='SYNTHETIC feature review')
    runs = [replace(o.run, host_ref='SYNTHETIC-host',
        actor_ref='SYNTHETIC:' + ('implementer-a' if i == 0 else 'reviewer-b'),
        run_ref=f'SYNTHETIC-run-{i}', dispatch_token=f'synthetic-token-{i}',
        observation_ref=f'SYNTHETIC:response-{i}') for i, o in enumerate(data.bundle.observations)]
    cycle = task.cycles[-1]
    task = replace(task, cycles=[replace(cycle, review=replace(cycle.review,
        implementer_ref=runs[0].actor_ref, reviewer_ref=runs[1].actor_ref))])
    workers = []
    assignments = []
    for i, responsibility in enumerate(('implementer', 'reviewer')):
        root = base / responsibility
        root.mkdir()
        workers.append(root)
        (root / 'design.md').write_bytes((final / 'design.md').read_bytes())
        prompt = f'SYNTHETIC {responsibility} task={task.id} assignment=assignment-{i} token={runs[i].dispatch_token}\n'
        (root / 'prompt.txt').write_text(prompt)
        (root / 'instructions.md').write_text('SYNTHETIC local test instructions; no host proof.\n')
        (root / 'authority.json').write_bytes(c.canonical_json({
            'fixture': 'SYNTHETIC', 'task_id': task.id, 'artifact_root': str(root),
            'tools': ['local'], 'requested_actions': [], 'authorization': [],
            'observed_at': AUTHORITY_AT}))
        product, check = ('product.txt', 'check.txt') if i == 0 else ('review.txt', 'review-check.txt')
        (root / product).write_text('SYNTHETIC owned product' if i == 0 else 'SYNTHETIC independent review')
        (root / check).write_text('SYNTHETIC unit verification supports works criterion\n')
        def receipt(name, root=root):
            return b.BuiltinReceipt(name, digest((root / name).read_bytes()))
        authority = b.BuiltinAuthority('2.0', task.id, request_sha, request.project_id,
            str(root), ['local'], ['local'], [], [], AUTHORITY_AT, receipt('authority.json'))
        payload = b.BuiltinPayload('2.0', task.id, 1, responsibility, 'design.md',
            task.criteria, context, [product, check], task.limits, receipt('prompt.txt'),
            [receipt('instructions.md')], authority, 'other' if i == 0 else 'review', None)
        assignments.append(b.BuiltinAssignment('2.0', f'assignment-{i}', 1, task.id,
            None, True, payload, 'SYNTHETIC-base', request.project_id, str(root),
            [product, check], [], 'proposed', None, None, None, None, [], []))
        (root / 'call.json').write_bytes(c.canonical_json({
            'tool': 'collaboration.spawn_agent',
            'arguments': {'task_name': f'synthetic_{responsibility}', 'message': prompt, 'fork_turns': 'none'}}))
        (root / 'response.json').write_bytes(c.canonical_json({'task_name': runs[i].run_ref}))

    current = b.BuiltinSnapshot('2.0', 'builtin', task.id, 1, None, decision,
        registration, policy, plan, assignments, [], [], [])
    history = [current]
    def update(**changes):
        nonlocal current
        current = replace(current, revision=current.revision + 1,
                          previous_sha256=b.builtin_digest(current), **changes)
        history.append(current)
    for i, run in enumerate(runs):
        root = workers[i]
        def receipt(name):
            return b.BuiltinReceipt(name, digest((root / name).read_bytes()))
        e = replace(current.assignments[i], revision=2, state='dispatched', dispatch_token=run.dispatch_token)
        dispatched = e
        intent = b.BuiltinDispatch('2.0', run.dispatch_token, e.assignment_id, 2,
            b.builtin_digest(e), run.observed_at, 'pending', None, None, None)
        assignments = list(current.assignments); assignments[i] = e
        update(assignments=assignments, dispatches=[*current.dispatches, intent])
        binding = b.BuiltinHostBinding('2.0', task.id, e.assignment_id, run.dispatch_token,
            b.builtin_digest(dispatched), e.payload.prompt.sha256,
            [r.sha256 for r in e.payload.instructions], b.builtin_digest(e.payload.authority),
            run, receipt('call.json'), receipt('response.json'))
        e = replace(e, revision=3, state='working', observed_run=run)
        assignments = list(current.assignments); assignments[i] = e
        intents = list(current.dispatches); intents[i] = replace(intent, state='observed', observed_run=run, host_binding=binding)
        update(assignments=assignments, dispatches=intents)
        product, check = e.owned_paths
        artifact = c.Artifact('product' if i == 0 else 'review-artifact', product, receipt(product).sha256)
        handoff = b.BuiltinHandoff('2.0', task.id, e.payload.assignment_revision,
            e.payload.responsibility, 'ready_for_review', [artifact], {'works': [check]},
            [check], None, 'SYNTHETIC review owned output')
        e = replace(e, revision=4, state='ready_for_review', handoff_submission_id=f'submit-{i}')
        sub = b.BuiltinSubmission('2.0', f'submit-{i}', task.id, e.assignment_id, 4,
            b.builtin_digest(e), handoff, b.builtin_digest(handoff), run, STAMP)
        assignments = list(current.assignments); assignments[i] = e
        update(assignments=assignments, submissions=[*current.submissions, sub])
        output = digest(c.canonical_json([c.to_dict(artifact)]))
        e = replace(e, revision=5, state='accepted', output_sha256=output, review_refs=['SYNTHETIC:review.json'])
        assignments = list(current.assignments); assignments[i] = e
        intents = list(current.dispatches); intents[i] = replace(intents[i], state='terminated', reconciliation_ref='SYNTHETIC:terminated')
        update(assignments=assignments, dispatches=intents)

    entries = [replace(e, environment_sha256=context_sha,
        command='SYNTHETIC recorded command, never executed by fixture')
        for e in data.bundle.entries if e.kind != 'before']
    data.task = task
    data.delivery = current
    data.bundle = replace(data.bundle, delivery_revision=current.revision,
        plan_sha256=d.delivery_digest(plan), baseline_candidate_id=None, entries=entries,
        cases=[replace(case, before_ids=[]) for case in data.bundle.cases],
        observations=[ev.RunObservation(o.id, runs[i], data.receipt(o.receipt.path, d.delivery_to_dict(runs[i])))
                      for i, o in enumerate(data.bundle.observations)],
        reviews=[replace(review, entry_ids=['after', 'test'],
            assessment='SYNTHETIC feature unit evidence supports final candidate; no host proof')
                 for review in data.bundle.reviews])
    for entry in data.bundle.entries:
        (final / entry.receipt.path).write_bytes(('SYNTHETIC ' + entry.kind + ' observed pass').encode())
    data.bundle = replace(data.bundle, entries=[replace(entry,
        receipt=ev.HashedReceipt(entry.receipt.path, digest((final / entry.receipt.path).read_bytes())))
        for entry in data.bundle.entries])
    data.seal()
    fixture = BuiltinEvidenceFixture(data, base / 'state', history, workers)
    return fixture.persist() if persist else fixture
