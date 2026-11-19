"""Serialized catalog transactions with journaled, recoverable native asset changes.

Native probes are provided by callers; these helpers never run a client or claim
that synthetic observations demonstrate discovery in an installed client.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from .catalog import (_activation, _asset_manifest, _consistent, _evidence_refs, _json,
    _paths, _project, _record_manifest, _reject, _safe, _validation, load_catalog,
    validate_catalog)
from .contracts import (CapabilityCatalog, CapabilityRecord, CapabilityState,
    NativeProbeReceipt, ProbePurpose, RevisionConflict, canonical_json, from_dict, to_dict)

_STATES = {'preparing', 'replacing', 'prepared', 'finalizing', 'restoring', 'finalized', 'restored'}
_FIELDS = {'schema_version', 'operation_id', 'mode', 'state', 'started_at', 'old_catalog',
    'old_catalog_sha256', 'candidate', 'target', 'old_existed', 'old_manifest',
    'candidate_manifest', 'final_catalog'}
_OPERATION = re.compile(r'op-[0-9a-f]{32}')


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _time(value):
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', value):
        _reject('Invalid journal timestamp')
    try: return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: _reject('Invalid journal timestamp')


def _mkdir(root, relative):
    path = _safe(root, relative)
    path.mkdir(parents=True, exist_ok=True)
    _safe(root, relative)
    return path


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _atomic(path, data):
    temporary = path.parent / ('.' + path.name + '-' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists(): temporary.unlink()


def _save(directory, journal):
    _atomic(directory / 'journal.json', canonical_json(journal))


def _copy(source, destination):
    if source == destination or source in destination.parents or destination in source.parents:
        _reject('Private copy source and destination must not overlap')
    if destination.exists() or destination.is_symlink(): _reject('Copy destination must be absent and nonsymlink')
    if source.is_dir(): shutil.copytree(source, destination, copy_function=shutil.copy2)
    else: shutil.copy2(source, destination)
    files = [destination] if destination.is_file() else [p for p in destination.rglob('*') if p.is_file()]
    for path in files:
        with path.open('rb') as stream: os.fsync(stream.fileno())
    if destination.is_dir():
        for path in sorted([destination, *[p for p in destination.rglob('*') if p.is_dir()]], key=lambda p: len(p.parts), reverse=True):
            _fsync_directory(path)
    _fsync_directory(destination.parent)


def _remove(path):
    if path.is_symlink(): _reject('Cannot remove symlink')
    if path.is_dir():
        for child in path.rglob('*'):
            if child.is_symlink(): _reject('Cannot remove tree containing symlink')
        shutil.rmtree(path)
    elif path.exists(): path.unlink()
    _fsync_directory(path.parent)


def _catalog_text(root):
    path = _safe(root, 'capabilities/catalog.json')
    load_catalog(root)
    # Decode bytes directly: text mode would normalize CRLF and hide external edits.
    return path.read_bytes().decode('utf-8')


def _original(journal):
    return from_dict('CapabilityCatalog', json.loads(journal['old_catalog']))


def _final(journal, root):
    old = _original(journal)
    candidate = from_dict('CapabilityRecord', journal['candidate'])
    op = journal['operation_id']
    if journal['mode'] == 'activate':
        candidate = replace(candidate, state=CapabilityState.ACTIVE,
            discovery_probe_ref=f'.smart-assistant/deployments/{op}/activation-receipt.json',
            rollback_ref=f'.smart-assistant/deployments/{op}/journal.json')
    else:
        candidate = replace(candidate, state=CapabilityState.DISABLED,
            discovery_probe_ref=None, rollback_ref=f'.smart-assistant/deployments/{op}/journal.json')
    records = [candidate if r.id == candidate.id else r for r in old.records]
    if all(r.id != candidate.id for r in old.records): records.append(candidate)
    return CapabilityCatalog(1, old.revision + 1, records)


def _read_journal(root, directory):
    _safe(root, directory.relative_to(root).as_posix())
    journal = _json(directory / 'journal.json')
    if type(journal) is not dict or set(journal) != _FIELDS: _reject('Malformed deployment journal')
    if (type(journal['schema_version']) is not int or journal['schema_version'] != 1
            or not _OPERATION.fullmatch(directory.name)
            or type(journal['state']) is not str or type(journal['mode']) is not str
            or journal['operation_id'] != directory.name or journal['state'] not in _STATES
            or journal['mode'] not in ('activate', 'disable') or type(journal['old_existed']) is not bool
            or type(journal['old_catalog']) is not str):
        _reject('Invalid deployment journal metadata')
    canonical_json(journal)  # Validate JSON scalar text before hashing stored catalog bytes.
    _time(journal['started_at'])
    if hashlib.sha256(journal['old_catalog'].encode()).hexdigest() != journal['old_catalog_sha256']:
        _reject('Original catalog backup digest mismatch')
    try: old = _original(journal)
    except (ValueError, TypeError): _reject('Malformed original catalog backup')
    _consistent(old, root)
    candidate = from_dict('CapabilityRecord', journal['candidate'])
    _, target = _paths(candidate, root)
    if target is None or journal['target'] != candidate.deployed_path: _reject('Journal target mismatch')
    manifest = from_dict('DeploymentManifest', journal['candidate_manifest'])
    if manifest.manifest_sha256 != candidate.deployed_sha256: _reject('Journal manifest mismatch')
    previous = next((r for r in old.records if r.id == candidate.id), None)
    if previous and (previous.kind != candidate.kind or previous.deployed_path != candidate.deployed_path):
        _reject('Journal changes native target or capability kind')
    if previous and previous.state == CapabilityState.ACTIVE and not journal['old_existed']:
        _reject('An original ACTIVE deployment requires original files and backup manifest')
    if not journal['old_existed'] and (directory / 'backup').exists():
        _reject('Journal denies an original deployment but backup files exist')
    if journal['mode'] == 'activate' and candidate.state != CapabilityState.DRAFT:
        _reject('Activation journal must contain a draft candidate')
    if journal['old_existed']:
        old_manifest = from_dict('DeploymentManifest', journal['old_manifest'])
        if previous is None or previous.deployed_sha256 != old_manifest.manifest_sha256:
            _reject('Backup manifest must match registered previous version')
    elif journal['old_manifest'] is not None: _reject('Unexpected backup manifest')
    if journal['mode'] == 'disable' and (previous is None or to_dict(previous) != journal['candidate'] or not journal['old_existed']):
        _reject('Disable must bind to the original registered deployment')
    if journal['final_catalog'] is not None:
        expected = canonical_json(to_dict(_final(journal, root))).decode()
        if journal['final_catalog'] != expected: _reject('Final catalog journal mismatch')
    if journal['state'] in ('finalizing', 'finalized') and journal['final_catalog'] is None:
        _reject('Commit journal requires final catalog')
    return journal


def _journals(root):
    base = _safe(root, '.smart-assistant/deployments')
    if not base.exists(): return []
    if not base.is_dir(): _reject('Deployment storage must be a directory')
    result = []
    for directory in sorted(base.iterdir()):
        if not directory.is_dir() or directory.is_symlink(): _reject('Unexpected deployment storage entry')
        result.append((directory, _read_journal(root, directory)))
    return result


class DeploymentStore:
    def __init__(self, project_root: Path):
        self.root = _project(project_root)

    @contextmanager
    def _lock(self):
        _mkdir(self.root, '.smart-assistant')
        path = _safe(self.root, '.smart-assistant/catalog.lock')
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _operation(self, operation_id):
        if type(operation_id) is not str or not _OPERATION.fullmatch(operation_id): _reject('Invalid operation ID')
        directory = _safe(self.root, '.smart-assistant/deployments/' + operation_id)
        return directory, _read_journal(self.root, directory)

    def _unmodified(self, journal):
        if _catalog_text(self.root) != journal['old_catalog']:
            raise RevisionConflict('Catalog changed externally; recovery refuses to overwrite it')

    def _reconcile(self, directory, journal):
        if journal['state'] == 'finalizing' and _catalog_text(self.root) == journal['final_catalog']:
            journal['state'] = 'finalized'
            _save(directory, journal)
        return journal

    def _prepare(self, record, revision, mode):
        journals = _journals(self.root)
        if any(j['state'] not in ('finalized', 'restored') for _, j in journals):
            _reject('Unfinished deployment must be reconciled before another prepare')
        catalog = load_catalog(self.root)
        if type(revision) is not int or catalog.revision != revision: raise RevisionConflict('Stale expected catalog revision')
        gate = validate_catalog(catalog, self.root)
        if not gate.passed:
            from .contracts import ValidationError
            raise ValidationError(gate.errors)
        _paths(record, self.root)
        if record.deployed_path is None or record.deployed_sha256 is None: _reject('Candidate requires target and complete manifest')
        previous = next((r for r in catalog.records if r.id == record.id), None)
        if previous and (previous.kind != record.kind or previous.deployed_path != record.deployed_path):
            _reject('Updating a capability cannot change its kind or native target')
        if any(r.id != record.id and r.deployed_path == record.deployed_path for r in catalog.records):
            _reject('Native target belongs to another capability')
        target = _safe(self.root, record.deployed_path)
        old_existed = target.exists()
        old_manifest = _record_manifest(record, self.root) if old_existed else None
        if old_existed and (previous is None or old_manifest.manifest_sha256 != previous.deployed_sha256):
            _reject('Cannot replace unregistered or drifted native deployment')
        if mode == 'activate':
            if record.state != CapabilityState.DRAFT: _reject('Activation candidate must be draft')
            manifest = _record_manifest(record, self.root, staged=True)
            if manifest.manifest_sha256 != record.deployed_sha256: _reject('Staged manifest differs from candidate')
            _validation(record, self.root, manifest.manifest_sha256)
        else:
            if previous is None or record.state != CapabilityState.ACTIVE or not old_existed: _reject('Only an active deployed capability can be disabled')
            manifest = old_manifest
        operation_id = 'op-' + uuid.uuid4().hex
        directory = _mkdir(self.root, '.smart-assistant/deployments/' + operation_id)
        original_text = _catalog_text(self.root)
        journal = dict(schema_version=1, operation_id=operation_id, mode=mode,
            state='preparing', started_at=_now(), old_catalog=original_text,
            old_catalog_sha256=hashlib.sha256(original_text.encode()).hexdigest(),
            candidate=to_dict(record), target=record.deployed_path,
            old_existed=old_existed, old_manifest=to_dict(old_manifest) if old_manifest else None,
            candidate_manifest=to_dict(manifest), final_catalog=None)
        _save(directory, journal)
        if old_existed:
            _copy(target, directory / 'backup')
            if _asset_manifest(record, directory / 'backup').manifest_sha256 != old_manifest.manifest_sha256:
                _reject('Backup does not match original manifest')
        if mode == 'activate':
            _copy(_safe(self.root, record.source_path), directory / 'candidate')
            if _asset_manifest(record, directory / 'candidate').manifest_sha256 != manifest.manifest_sha256:
                _reject('Prepared copy does not match staged manifest')
        # Recheck exact catalog and original native contents immediately before destructive I/O.
        self._unmodified(journal)
        if old_existed and _record_manifest(record, self.root).manifest_sha256 != old_manifest.manifest_sha256:
            _reject('Native deployment changed while preparing')
        _mkdir(self.root, str(Path(record.deployed_path).parent))
        journal['state'] = 'replacing'
        _save(directory, journal)
        if old_existed: _remove(target)
        if mode == 'activate':
            os.replace(directory / 'candidate', target)
            _fsync_directory(target.parent)
        journal['state'] = 'prepared'
        _save(directory, journal)
        return operation_id

    def prepare(self, candidate: CapabilityRecord, expected_revision: int) -> str:
        candidate = from_dict('CapabilityRecord', to_dict(candidate))
        with self._lock(): return self._prepare(candidate, expected_revision, 'activate')

    def prepare_disable(self, capability_id: str, expected_revision: int) -> str:
        with self._lock():
            catalog = load_catalog(self.root)
            record = next((r for r in catalog.records if r.id == capability_id), None)
            if record is None: _reject('Unknown capability ID')
            return self._prepare(record, expected_revision, 'disable')

    def _restore(self, directory, journal):
        self._reconcile(directory, journal)
        if journal['state'] == 'finalized': _reject('Committed deployment requires a fresh rollback transaction and probe')
        self._unmodified(journal)
        if journal['state'] == 'restored': return load_catalog(self.root)
        target = _safe(self.root, journal['target'])
        record = from_dict('CapabilityRecord', journal['candidate'])
        if journal['state'] == 'preparing':
            if journal['old_existed']:
                if _asset_manifest(record, target).manifest_sha256 != journal['old_manifest']['manifest_sha256']:
                    _reject('Original native files changed during interrupted preparation')
            elif target.exists(): _reject('Unexpected native files appeared during interrupted preparation')
            # No destructive native I/O occurs until replacing is durable.
            journal['state'] = 'restored'
            _save(directory, journal)
            return load_catalog(self.root)
        if journal['old_existed']:
            backup = _safe(self.root, (directory / 'backup').relative_to(self.root).as_posix())
            expected = journal['old_manifest']['manifest_sha256']
            if _asset_manifest(record, backup).manifest_sha256 != expected: _reject('Backup corruption; surviving native files preserved')
        journal['state'] = 'restoring'
        _save(directory, journal)
        restored = directory / 'restoring-assets'
        if journal['old_existed']:
            if restored.exists(): _remove(restored)
            _copy(backup, restored)
            if _asset_manifest(record, restored).manifest_sha256 != expected: _reject('Restoration copy corruption')
        if target.exists(): _remove(target)
        if journal['old_existed']:
            os.replace(restored, target)
            _fsync_directory(target.parent)
        self._unmodified(journal)
        journal['state'] = 'restored'
        _save(directory, journal)
        return load_catalog(self.root)

    def restore(self, operation_id: str) -> CapabilityCatalog:
        with self._lock():
            directory, journal = self._operation(operation_id)
            return self._restore(directory, journal)

    def _probe(self, journal, probe):
        to_dict(probe)
        record = from_dict('CapabilityRecord', journal['candidate'])
        purpose = ProbePurpose.ACTIVATE if journal['mode'] == 'activate' else ProbePurpose.DISABLE
        if (probe.operation_id != journal['operation_id'] or probe.capability_id != record.id
                or probe.version != record.version or probe.manifest_sha256 != record.deployed_sha256
                or probe.purpose != purpose or _time(probe.observed_at) < _time(journal['started_at'])):
            _reject('Probe identity, manifest, purpose or observation time does not match transaction')
        _evidence_refs(self.root, probe.evidence_refs)
        if purpose == ProbePurpose.ACTIVATE:
            if probe.discovered is not True or probe.invoked is not True: _reject('Activation discovery/invocation failed')
        else:
            if probe.discovered is not False or probe.invoked is not None: _reject('Disable absence observation failed')
            prior = _activation(record, self.root)
            if probe.session_ref == prior.session_ref: _reject('Disable requires a fresh native session')

    def _finalize(self, operation_id, probe, mode):
        directory, journal = self._operation(operation_id)
        if journal['mode'] != mode: _reject('Wrong finalization method for journal purpose')
        self._reconcile(directory, journal)
        if journal['state'] == 'finalized':
            # Idempotent retries still validate the supplied receipt against saved proof.
            name = 'activation-receipt.json' if mode == 'activate' else 'absence-receipt.json'
            if to_dict(probe) != _json(directory / name): _reject('Finalized receipt differs from committed proof')
            if _catalog_text(self.root) != journal['final_catalog']: raise RevisionConflict('Catalog advanced after finalization')
            return load_catalog(self.root)
        if journal['state'] not in ('prepared', 'finalizing'): _reject('Only prepared deployments can finalize')
        self._unmodified(journal)
        from .contracts import ValidationError
        try:
            probe = from_dict('NativeProbeReceipt', to_dict(probe))
            self._probe(journal, probe)
            record = from_dict('CapabilityRecord', journal['candidate'])
            if mode == 'activate':
                if _record_manifest(record, self.root).manifest_sha256 != record.deployed_sha256: _reject('Native manifest drift during probe')
                _validation(record, self.root, record.deployed_sha256)
            elif _safe(self.root, record.deployed_path).exists(): _reject('Disabled assets reappeared')
        except ValidationError:
            if mode == 'activate': self._restore(directory, journal)
            raise
        name = 'activation-receipt.json' if mode == 'activate' else 'absence-receipt.json'
        _atomic(directory / name, canonical_json(to_dict(probe)))
        final = _final(journal, self.root)
        journal['final_catalog'] = canonical_json(to_dict(final)).decode()
        journal['state'] = 'finalizing'
        _save(directory, journal)
        self._unmodified(journal)
        _atomic(_safe(self.root, 'capabilities/catalog.json'), journal['final_catalog'].encode())
        journal['state'] = 'finalized'
        _save(directory, journal)
        return final

    def finalize(self, operation_id: str, discovery_receipt: NativeProbeReceipt) -> CapabilityCatalog:
        with self._lock(): return self._finalize(operation_id, discovery_receipt, 'activate')

    def finalize_disable(self, operation_id: str, absence_receipt: NativeProbeReceipt) -> CapabilityCatalog:
        with self._lock(): return self._finalize(operation_id, absence_receipt, 'disable')
