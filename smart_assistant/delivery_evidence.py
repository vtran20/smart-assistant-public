"""Immutable local delivery evidence consistency checks.

Hashes bind bytes, not host origin or semantic truth. P16 must supply actual host
observations and serialize this check with artifact/state changes under its lock.
This module never executes commands, mutates task state or grants runtime approval.
"""
from __future__ import annotations
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin, get_type_hints
import unicodedata
from .contracts import (TaskRecord, GateResult, ErrorDetail, ValidationError,
                        canonical_json, from_dict, to_dict)
from .delivery_records import ObservedRun, DeliverySnapshot, delivery_from_dict
from .delivery_codec import (record_from_dict, record_to_dict as delivery_to_dict,
    record_digest as delivery_digest, mode_for_task)
from .builtin_records import BuiltinSnapshot, validate_builtin_receipts
from .quality import completion_gate, _root, _candidate, _acceptance, _file_hash

ID = Annotated[str, 'id']
Digest = Annotated[str, 'digest']
UTC = Annotated[str, 'utc']
Text = Annotated[str, 'text']
FilePath = Annotated[str, 'path']
Positive = Annotated[int, 'positive']
MAX_EVIDENCE_BYTES = 16 * 1024 * 1024

@dataclass(frozen=True)
class HashedReceipt:
    path: FilePath
    sha256: Digest

@dataclass(frozen=True)
class RunObservation:
    id: ID
    run: ObservedRun
    receipt: HashedReceipt

@dataclass(frozen=True)
class EvidenceEntry:
    id: ID
    receipt: HashedReceipt
    requirement_ids: list[ID]
    case_id: ID
    scenario_id: ID
    kind: Literal['before', 'after', 'test', 'review', 'observation']
    proof_level: Text
    captured_at: UTC
    observation_id: ID
    capture_source: Text
    environment_sha256: Digest
    build_sha256: Digest
    input_sha256: Digest
    candidate_id: Digest
    expected_result: Text
    observed_result: Text
    outcome: Literal['pass', 'fail', 'blocked']
    command: Text | None
    exit_code: int | None
    observation: Text | None
    privacy: Literal['public', 'internal', 'restricted']
    semantic_review_id: ID

@dataclass(frozen=True)
class VerificationCase:
    id: ID
    requirement_ids: list[ID]
    scenario_id: ID
    required: bool
    applicability_rationale: Text
    applicability_review_id: ID | None
    expected_result: Text
    required_levels: list[Text]
    status: Literal['pass', 'fail', 'blocked', 'not_run', 'not_applicable']
    before_ids: list[ID]
    after_ids: list[ID]
    test_ids: list[ID]
    differences: Text | None
    differences_review_id: ID | None

@dataclass(frozen=True)
class SemanticReview:
    id: ID
    implementer_observation_id: ID
    reviewer_observation_id: ID
    candidate_id: Digest
    acceptance_id: Digest
    entry_ids: list[ID]
    case_ids: list[ID]
    evidence_sha256: Digest
    reviewed_at: UTC
    approved: bool
    assessment: Text
    unresolved_findings: list[Text]
    receipt: HashedReceipt

@dataclass(frozen=True)
class EvidenceBundle:
    schema_version: Literal['1.0']
    task_id: ID
    delivery_revision: Positive
    plan_sha256: Digest
    candidate_id: Digest
    acceptance_id: Digest
    baseline_candidate_id: Digest | None
    cases: list[VerificationCase]
    entries: list[EvidenceEntry]
    observations: list[RunObservation]
    reviews: list[SemanticReview]

_RECORDS = (HashedReceipt, RunObservation, EvidenceEntry, VerificationCase,
            SemanticReview, EvidenceBundle)

def _require(condition, code, path, message):
    if not condition:
        raise ValidationError([ErrorDetail(code, path, message)])

def _safe_path(value):
    return (bool(value) and not value.startswith('/')
        and not any(c in value for c in '\\:\x00*?[]')
        and all(p not in ('', '.', '..') for p in value.split('/'))
        and unicodedata.normalize('NFC', value) == value)

def _decode(expected, value, path):
    origin, args = get_origin(expected), get_args(expected)
    if origin is Annotated:
        result = _decode(args[0], value, path)
        rule = args[1]
        valid = True
        if rule == 'id': valid = re.fullmatch(r'[a-z][a-z0-9_-]{1,63}', result)
        elif rule == 'digest': valid = re.fullmatch(r'[a-f0-9]{64}', result)
        elif rule == 'text': valid = bool(result.strip())
        elif rule == 'positive': valid = result > 0
        elif rule == 'path': valid = _safe_path(result)
        elif rule == 'utc':
            valid = re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z', result)
            if valid:
                try: datetime.fromisoformat(result[:-1] + '+00:00')
                except ValueError: valid = False
        _require(valid, 'invalid_' + rule, path, 'Invalid ' + rule)
        return result
    if origin in (Union, UnionType):
        if value is None and type(None) in args: return None
        for choice in args:
            if choice is not type(None):
                try: return _decode(choice, value, path)
                except ValidationError: pass
        _require(False, 'invalid_type', path, 'No permitted union type matches')
    if origin is Literal:
        _require(type(value) is str and value in args, 'invalid_type', path, 'Unsupported literal')
        return value
    if origin is list:
        _require(type(value) is list, 'invalid_type', path, 'Expected list')
        result = [_decode(args[0], v, f'{path}[{i}]') for i, v in enumerate(value)]
        if args[0] not in _RECORDS:
            _require(len(result) == len(set(result)), 'duplicate_value', path, 'Duplicate list value')
        return result
    if expected is ObservedRun: return delivery_from_dict('ObservedRun', value)
    if expected in _RECORDS:
        _require(type(value) is dict, 'invalid_type', path, 'Expected record object')
        _require(set(value) == {f.name for f in fields(expected)}, 'unknown_field', path,
                 'Missing or unknown record fields')
        hints = get_type_hints(expected, include_extras=True)
        result = expected(**{n: _decode(t, value[n], path + '.' + n) for n, t in hints.items()})
        _local(result, path)
        return result
    _require(type(value) is expected, 'invalid_type', path, 'Wrong scalar type')
    return value

def _raw(value, ancestors=frozenset()):
    if type(value) is ObservedRun: return delivery_to_dict(value)
    if is_dataclass(value) or type(value) in (list, dict):
        _require(id(value) not in ancestors, 'invalid_type', '$', 'Cyclic value')
        ancestors = ancestors | {id(value)}
        if is_dataclass(value):
            _require(type(value) in _RECORDS, 'invalid_type', '$', 'Unknown dataclass')
            return {f.name: _raw(getattr(value, f.name), ancestors) for f in fields(value)}
        if type(value) is list: return [_raw(v, ancestors) for v in value]
        return {k: _raw(v, ancestors) for k, v in value.items()}
    return value

def _local(record, path):
    if type(record) in (EvidenceEntry, VerificationCase):
        _require(bool(record.requirement_ids), 'invalid_coverage', path, 'Requirements required')
    if type(record) is EvidenceEntry:
        _require((record.command is None) == (record.exit_code is None),
                 'invalid_command', path, 'Command and exact exit must appear together')
        _require(record.command is not None or record.observation is not None,
                 'invalid_command', path, 'Command or observation required')
        _require(record.outcome != 'pass' or record.exit_code in (None, 0),
                 'invalid_command', path, 'Passing command must exit zero')
    if type(record) is VerificationCase:
        _require(bool(record.required_levels), 'invalid_coverage', path, 'Proof levels required')
        _require((record.differences is None) == (record.differences_review_id is None),
                 'invalid_coverage', path, 'Differences need an independent review')
    if type(record) is EvidenceBundle:
        for name in ('cases', 'entries', 'observations', 'reviews'):
            values = getattr(record, name)
            _require(len(values) == len({v.id for v in values}), 'duplicate_id', path + '.' + name,
                     'Record IDs must be unique')

def evidence_from_dict(data: dict) -> EvidenceBundle:
    canonical_json(data)
    return _decode(EvidenceBundle, data, '$')

def evidence_to_dict(bundle: EvidenceBundle) -> dict:
    _require(type(bundle) is EvidenceBundle, 'invalid_type', '$', 'Expected EvidenceBundle')
    raw = _raw(bundle)
    evidence_from_dict(raw)
    return raw

def evidence_digest(bundle: EvidenceBundle) -> str:
    return hashlib.sha256(canonical_json(evidence_to_dict(bundle))).hexdigest()

def _time(value):
    return datetime.fromisoformat(value[:-1] + '+00:00')

def _receipt_bytes(root_fd, receipt, product_files, seen_entries=None):
    directory = os.dup(root_fd)
    file_fd = None
    try:
        parts = receipt.path.split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(file_fd)
        _require(stat.S_ISREG(info.st_mode), 'invalid_evidence_path', receipt.path,
                 'Evidence must be a regular file')
        identity = (info.st_dev, info.st_ino)
        _require(identity not in product_files, 'evidence_as_artifact', receipt.path,
                 'Evidence cannot alias a product artifact')
        if seen_entries is not None:
            _require(identity not in seen_entries, 'duplicate_evidence', receipt.path,
                     'Distinct entries cannot reuse the same raw file')
            seen_entries.add(identity)
        _require(info.st_size <= MAX_EVIDENCE_BYTES, 'evidence_too_large', receipt.path,
                 'Evidence exceeds bounded read limit')
        chunks, count = [], 0
        while chunk := os.read(file_fd, min(65536, MAX_EVIDENCE_BYTES + 1 - count)):
            chunks.append(chunk)
            count += len(chunk)
            _require(count <= MAX_EVIDENCE_BYTES, 'evidence_too_large', receipt.path,
                     'Evidence grew beyond bounded read limit')
        data = b''.join(chunks)
        after = os.fstat(file_fd)
        _require((info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
                 (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                 'changed_evidence', receipt.path, 'Evidence changed during read')
        _require(hashlib.sha256(data).hexdigest() == receipt.sha256,
                 'evidence_hash_mismatch', receipt.path, 'Actual receipt bytes changed')
        return data
    except OSError:
        _require(False, 'invalid_evidence_path', receipt.path, 'Missing, unreadable or unsafe evidence')
    finally:
        if file_fd is not None: os.close(file_fd)
        os.close(directory)

def _receipt_json(data, expected, path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('Duplicate object key')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('Nonfinite JSON')
    try:
        actual = json.loads(data, object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError):
        _require(False, 'invalid_receipt', path, 'Expected strict finite JSON without duplicate fields')
    _require(canonical_json(actual) == canonical_json(expected), 'invalid_receipt', path,
             'Receipt does not match complete declared record')

def _scope_digest(bundle, review, delivery):
    """Bind all reviewed bytes and provenance, rather than mutable local ID labels."""
    selected_entries = [e for e in sorted(bundle.entries, key=lambda e: e.id)
                        if e.id in review.entry_ids]
    observation_ids = {review.implementer_observation_id, review.reviewer_observation_id}
    observation_ids.update(e.observation_id for e in selected_entries)
    observations = {o.id: o for o in bundle.observations}
    _require(observation_ids <= observations.keys(), 'unobserved_run', review.id,
             'Referenced review or capture observation absent')
    payload = {
        'plan_sha256': delivery_digest(delivery.plan),
        'context_sha256': delivery.plan.context_sha256,
        'entries': [_raw(e) for e in selected_entries],
        'cases': [_raw(c) for c in sorted(bundle.cases, key=lambda c: c.id)
                  if c.id in review.case_ids],
        'observations': [_raw(observations[i]) for i in sorted(observation_ids)],
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()

def _check(task, delivery, bundle, artifact_root):
    _require(isinstance(artifact_root, Path) and artifact_root.is_absolute()
             and str(artifact_root) == task.artifact_root,
             'invalid_artifact_path', '$.artifact_root', 'Root differs from registered v1 task')
    _require(not task.blockers, 'task_blocked', '$.blockers', 'Task has unresolved blockers')
    legacy = completion_gate(task)
    if not legacy.passed: raise ValidationError(legacy.errors)
    cycle = task.cycles[-1]
    _require(bundle.task_id == task.id == delivery.task_id == delivery.plan.task_id,
             'task_mismatch', '$.task_id', 'Task bindings differ')
    _require(bundle.delivery_revision == delivery.revision
             and bundle.plan_sha256 == delivery_digest(delivery.plan),
             'stale_plan', '$.plan_sha256', 'Evidence does not bind current delivery/plan revision')
    with _root(artifact_root, 'invalid_artifact_path', '$.artifact_root') as root_fd:
        products = set()
        candidate = _candidate(root_fd, cycle.candidate.artifacts, products)
        design = _file_hash(root_fd, cycle.design_ref, 'invalid_evidence_path',
                            'missing_evidence', '$.design_ref')
        acceptance = _acceptance(task.criteria, design)
        _require(bundle.candidate_id == candidate.candidate_id == cycle.candidate.candidate_id,
                 'stale_candidate', '$.candidate_id', 'Current final product candidate differs')
        _require(bundle.acceptance_id == acceptance.acceptance_id == cycle.acceptance.acceptance_id
                 and delivery.plan.acceptance_sha256 == acceptance.acceptance_id
                 and delivery.plan.design_sha256 == design,
                 'stale_acceptance', '$.acceptance_id', 'Actual criteria/design acceptance differs')
        criteria = {c.id for c in task.criteria}
        _require(set(delivery.plan.requirement_ids) == criteria,
                 'invalid_coverage', '$.plan.requirement_ids', 'Plan must match every task criterion')
        entries = {e.id: e for e in bundle.entries}
        cases = {c.id: c for c in bundle.cases}
        observations = {o.id: o for o in bundle.observations}
        reviews = {r.id: r for r in bundle.reviews}
        _require(bool(cases) and bool(reviews), 'missing_semantic_review', '$',
                 'Case matrix and independent semantic review required')
        for observation in bundle.observations:
            matching = [d for d in delivery.dispatches if d.state in ('observed', 'terminated')
                        and d.observed_run == observation.run
                        and d.dispatch_token == observation.run.dispatch_token]
            _require(len(matching) == 1, 'unobserved_run', observation.id,
                     'Observation must match exactly one supplied observed host dispatch')
            data = _receipt_bytes(root_fd, observation.receipt, products)
            _receipt_json(data, delivery_to_dict(observation.run), observation.receipt.path)
        for review in bundle.reviews:
            _require(review.candidate_id == candidate.candidate_id
                     and review.acceptance_id == acceptance.acceptance_id,
                     'stale_semantic_review', review.id, 'Semantic review is stale')
            _require(review.approved and not review.unresolved_findings,
                     'unresolved_semantic_review', review.id, 'Review approval or feedback unresolved')
            _require(set(review.entry_ids) <= entries.keys() and set(review.case_ids) <= cases.keys(),
                     'invalid_semantic_review', review.id, 'Review refers to unknown entries/cases')
            _require(review.evidence_sha256 == _scope_digest(bundle, review, delivery),
                     'stale_semantic_review', review.id, 'Reviewed metadata, observation provenance or plan/context changed')
            _require(review.implementer_observation_id in observations
                     and review.reviewer_observation_id in observations,
                     'unobserved_run', review.id, 'Review observation absent')
            implementer = observations[review.implementer_observation_id].run
            reviewer = observations[review.reviewer_observation_id].run
            _require((implementer.host_ref, implementer.run_ref) != (reviewer.host_ref, reviewer.run_ref)
                     and implementer.observation_ref != reviewer.observation_ref
                     and implementer.actor_ref != reviewer.actor_ref
                     and implementer.dispatch_token != reviewer.dispatch_token
                     and implementer.actor_ref == cycle.review.implementer_ref
                     and reviewer.actor_ref == cycle.review.reviewer_ref,
                     'nonindependent_review', review.id, 'Distinct labels do not establish distinct review contexts')
            completed = _time(review.reviewed_at)
            _require(completed == _time(cycle.review.observed_at)
                     and completed >= _time(reviewer.observed_at)
                     and completed >= _time(implementer.observed_at)
                     and all(completed >= _time(entries[e].captured_at)
                             for e in review.entry_ids),
                     'stale_semantic_review', review.id,
                     'Review completion must match v1 review and follow run observation/captures')
            raw = _raw(review)
            raw.pop('receipt')
            _receipt_json(_receipt_bytes(root_fd, review.receipt, products), raw, review.receipt.path)
        seen_entries = set()
        for entry in bundle.entries:
            _require(entry.case_id in cases and set(entry.requirement_ids) <= criteria,
                     'invalid_coverage', entry.id, 'Unknown case or requirement')
            case = cases[entry.case_id]
            _require(entry.scenario_id == case.scenario_id
                     and set(entry.requirement_ids) == set(case.requirement_ids)
                     and entry.expected_result == case.expected_result,
                     'reproduction_mismatch', entry.id, 'Evidence differs from exact case/scenario/assertion')
            expected_candidate = bundle.baseline_candidate_id if entry.kind == 'before' else candidate.candidate_id
            _require(entry.candidate_id == expected_candidate,
                     'stale_candidate', entry.id, 'Evidence candidate binding differs')
            _require(entry.observation_id in observations, 'unobserved_run', entry.id,
                     'Evidence capture has no observed run')
            _require(_time(entry.captured_at) >= _time(observations[entry.observation_id].run.observed_at),
                     'invalid_observation', entry.id, 'Capture predates source run observation')
            _require(entry.semantic_review_id in reviews
                     and entry.id in reviews[entry.semantic_review_id].entry_ids
                     and entry.case_id in reviews[entry.semantic_review_id].case_ids,
                     'missing_semantic_review', entry.id, 'Entry lacks current covering semantic review')
            _receipt_bytes(root_fd, entry.receipt, products, seen_entries)
        bug = delivery.policy.workflow_kind == 'bug'
        if bug:
            _require(bundle.baseline_candidate_id is not None
                     and bundle.baseline_candidate_id != candidate.candidate_id,
                     'missing_reproduction', '$.baseline_candidate_id', 'Bug requires distinct baseline identity')
        else:
            _require(bundle.baseline_candidate_id is None
                     and not any(e.kind == 'before' for e in bundle.entries),
                     'invalid_baseline', '$', 'Nonbug must not invent failing bug baseline')
        for kind in ('before', 'final'):
            builds = {e.build_sha256 for e in bundle.entries if (e.kind == 'before') == (kind == 'before')}
            _require(len(builds) <= 1, 'reproduction_mismatch', '$.entries', 'Candidate build identities inconsistent')
        covered, used = set(), set()
        for case in bundle.cases:
            _require(set(case.requirement_ids) <= criteria, 'invalid_coverage', case.id, 'Unknown requirement')
            _require(any(case.id in r.case_ids for r in bundle.reviews),
                     'missing_semantic_review', case.id, 'Case matrix requires independent review')
            def reviewed(ref):
                return ref in reviews and case.id in reviews[ref].case_ids
            if case.applicability_review_id is not None:
                _require(reviewed(case.applicability_review_id), 'missing_semantic_review', case.id,
                         'Applicability review missing')
            if case.status == 'not_applicable':
                _require(not case.required and reviewed(case.applicability_review_id),
                         'invalid_waiver', case.id, 'Required cases cannot be waived')
            if case.required:
                _require(case.status == 'pass', 'required_case_failed', case.id,
                         'Every required case must pass')
                _require(set(delivery.policy.required_verification_levels) <= set(case.required_levels),
                         'missing_proof_level', case.id, 'Case omits policy verification levels')
            groups = {}
            for kind, ids in [('before', case.before_ids), ('after', case.after_ids), ('test', case.test_ids)]:
                _require(all(i in entries and entries[i].kind == kind and entries[i].case_id == case.id for i in ids),
                         'invalid_coverage', case.id, 'Wrong-kind or wrong-case evidence reuse')
                groups[kind] = [entries[i] for i in ids]
                used.update(ids)
            if not bug:
                _require(not case.before_ids, 'invalid_baseline', case.id, 'Nonbug cannot declare bug before')
            if case.status != 'pass': continue
            if case.required: covered.update(case.requirement_ids)
            required_groups = ['after', 'test'] + (['before'] if bug else [])
            for kind in required_groups:
                _require(set(case.required_levels) <= {e.proof_level for e in groups[kind]}
                         and all(e.outcome == ('fail' if kind == 'before' else 'pass') for e in groups[kind]),
                         'missing_reproduction' if kind == 'before' else 'missing_verification',
                         case.id, 'Each declared level requires matching evidence/outcome')
            if bug:
                for before in groups['before']:
                    for after in groups['after'] + groups['test']:
                        if before.proof_level != after.proof_level: continue
                        _require(_time(before.captured_at) < _time(after.captured_at),
                                 'reproduction_mismatch', case.id, 'Before must predate final evidence')
                        differs = (before.input_sha256 != after.input_sha256
                                   or before.environment_sha256 != after.environment_sha256)
                        _require(not differs or (case.differences is not None and reviewed(case.differences_review_id)),
                                 'reproduction_mismatch', case.id, 'Unexplained input/environment difference')
            if case.differences_review_id is not None:
                _require(reviewed(case.differences_review_id), 'missing_semantic_review', case.id,
                         'Difference assessment is not reviewed')
        used.update(e.id for e in bundle.entries if e.kind in ('review', 'observation'))
        _require(used == entries.keys(), 'invalid_coverage', '$.entries', 'Orphan evidence entry')
        _require(covered == criteria, 'missing_criterion_coverage', '$.cases',
                 'Passing required cases must cover every task criterion')

def validate_delivery_evidence(task, delivery, bundle, artifact_root: Path) -> GateResult:
    """Fail closed on malformed/stale local evidence; never execute receipt commands."""
    try:
        _require(type(task) is TaskRecord and type(delivery) in (DeliverySnapshot,BuiltinSnapshot),
                 'invalid_type', '$', 'Expected current task and supported exact delivery snapshot')
        task = from_dict('TaskRecord', to_dict(task))
        mode = mode_for_task(task)
        kind = 'BuiltinSnapshot' if mode == 'builtin' else 'DeliverySnapshot'
        delivery = record_from_dict(kind,delivery_to_dict(delivery),mode=mode)
        bundle = evidence_from_dict(evidence_to_dict(bundle))
        if type(delivery) is BuiltinSnapshot:
            checked = validate_builtin_receipts(delivery,artifact_root)
            if not checked.passed: raise ValidationError(checked.errors)
        _check(task, delivery, bundle, artifact_root)
        return GateResult(True, [])
    except ValidationError as error:
        return GateResult(False, error.errors)
