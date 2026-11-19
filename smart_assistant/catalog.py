"""Filesystem-backed capability catalog, manifest and fail-closed eligibility."""
from __future__ import annotations

import hashlib
import fcntl
import os
import json
from pathlib import Path, PurePosixPath
import stat

from .contracts import (CapabilityCatalog, CapabilityRecord, CapabilityKind, CapabilityState, DeploymentFile,
    DeploymentManifest, ErrorDetail, GateResult, ProbePurpose, ValidationError,
    canonical_json, from_dict, to_dict)


def _reject(message, code='invalid_deployment', path='$'):
    raise ValidationError([ErrorDetail(code, path, message)])


def _project(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        _reject('Project root must be an existing nonsymlink directory')
    return root.resolve()


def _safe(root, relative):
    if type(relative) is not str or not relative or '\\' in relative:
        _reject('Expected a safe project-relative POSIX path')
    path = PurePosixPath(relative)
    if path.is_absolute() or any(p in ('', '.', '..') for p in relative.split('/')):
        _reject('Path must remain inside the project')
    result = root
    for part in path.parts:
        result = result / part
        if result.is_symlink(): _reject('Symlinks are forbidden', path=relative)
    if not result.resolve().is_relative_to(root): _reject('Path escapes project', path=relative)
    return result


def _json(path):
    if path.is_symlink() or not path.is_file(): _reject('JSON reference must be a regular nonsymlink file', path=str(path))
    def unique(items):
        value = {}
        for key, item in items:
            if key in value: _reject('Duplicate JSON key')
            value[key] = item
        return value
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique,
            parse_constant=lambda _: _reject('Nonfinite JSON value'))
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, ValidationError): raise
        _reject(f'Cannot read JSON evidence: {error}', path=str(path))


def _manifest(path, basename=None):
    if path.is_symlink(): _reject('Asset symlinks are forbidden')
    if not path.exists(): _reject('Asset is missing', path=str(path))
    files = []
    if path.is_file():
        paths = [(basename or path.name, path)]
    elif path.is_dir():
        paths = []
        for item in sorted(path.rglob('*')):
            mode = item.lstat().st_mode
            if stat.S_ISLNK(mode): _reject('Asset symlinks are forbidden', path=str(item))
            if stat.S_ISDIR(mode): continue
            if not stat.S_ISREG(mode): _reject('Only regular asset files are allowed', path=str(item))
            paths.append((item.relative_to(path).as_posix(), item))
    else:
        _reject('Only regular files or directories are allowed')
    for relative, item in paths:
        if not stat.S_ISREG(item.lstat().st_mode): _reject('Only regular asset files are allowed')
        files.append(DeploymentFile(relative, hashlib.sha256(item.read_bytes()).hexdigest()))
    if not files: _reject('Deployment tree must contain files')
    wire = [{'relative_path': f.relative_path, 'sha256': f.sha256} for f in files]
    manifest = DeploymentManifest(files, hashlib.sha256(canonical_json(wire)).hexdigest())
    to_dict(manifest)
    return manifest


def deployment_manifest(root: Path) -> DeploymentManifest:
    """Hash every regular file; a file root uses its basename in the manifest."""
    path = Path(root)
    # Check existing ancestors without treating macOS /var's system alias as an asset.
    for ancestor in [path, *path.parents]:
        if ancestor.is_symlink(): _reject('Manifest roots cannot cross symlinks')
    return _manifest(path)


def _paths(record, root):
    to_dict(record)
    source = _safe(root, record.source_path)
    target = _safe(root, record.deployed_path) if record.deployed_path else None
    if record.source_path.split('/')[0] in ('.agents', '.codex'):
        _reject('Staging must be outside native discovery directories')
    storage = _safe(root, '.smart-assistant/deployments')
    if source == storage or source in storage.parents or storage in source.parents:
        _reject('Staging must not overlap deployment journal storage in either direction')
    if target is not None:
        parts = PurePosixPath(record.deployed_path).parts
        prefix = ('.codex', 'agents') if record.kind == CapabilityKind.AGENT else ('.agents', 'skills')
        if len(parts) != 3 or parts[:2] != prefix or parts[2].startswith('.'):
            _reject('Unsafe native target')
        if record.kind == CapabilityKind.AGENT and not parts[2].endswith('.toml'):
            _reject('Agent target must be a TOML file')
        if source == target or source in target.parents or target in source.parents:
            _reject('Staging and native target overlap')
    return source, target


def _record_manifest(record, root, staged=False):
    source, target = _paths(record, root)
    if target is None: _reject('Deployment target is required')
    path = source if staged else target
    return _asset_manifest(record, path)


def _asset_manifest(record, path):
    if path.is_symlink(): _reject('Native asset must be nonsymlink')
    if record.kind == CapabilityKind.AGENT and not path.is_file(): _reject('Agent must be a file')
    if record.kind == CapabilityKind.SKILL and not path.is_dir(): _reject('Skill must be a directory')
    return _manifest(path, Path(record.deployed_path).name if record.kind == CapabilityKind.AGENT else None)


def _validation(record, root, digest):
    kinds = set()
    fields = {'schema_version', 'kind', 'capability_id', 'version', 'manifest_sha256', 'passed', 'evidence_refs'}
    for ref in record.validation_refs:
        value = _json(_safe(root, ref))
        if (type(value) is not dict or set(value) != fields or type(value['schema_version']) is not int
                or value['schema_version'] != 1 or value['kind'] not in ('validation', 'evaluation')
                or value['capability_id'] != record.id or value['version'] != record.version
                or value['manifest_sha256'] != digest or value['passed'] is not True
                or type(value['evidence_refs']) is not list or not value['evidence_refs']
                or any(type(r) is not str or not r for r in value['evidence_refs'])):
            _reject('Validation/evaluation evidence must be successful and manifest-bound', path=ref)
        _evidence_refs(root, value['evidence_refs'])
        kinds.add(value['kind'])
    if kinds != {'validation', 'evaluation'}: _reject('Both validation and evaluation evidence are required')


def _activation(record, root):
    if record.discovery_probe_ref is None: _reject('Active capability requires a discovery receipt')
    probe = from_dict('NativeProbeReceipt', _json(_safe(root, record.discovery_probe_ref)))
    if (probe.capability_id != record.id or probe.version != record.version
            or probe.manifest_sha256 != record.deployed_sha256 or probe.purpose != ProbePurpose.ACTIVATE
            or probe.discovered is not True or probe.invoked is not True or not probe.evidence_refs):
        _reject('Active capability requires matching successful discovery/invocation evidence')
    _evidence_refs(root, probe.evidence_refs)
    expected_ref = f'.smart-assistant/deployments/{probe.operation_id}/activation-receipt.json'
    if record.discovery_probe_ref != expected_ref: _reject('Probe operation does not match its saved reference')
    from .lifecycle import _read_journal, _time
    journal = _read_journal(root, _safe(root, f'.smart-assistant/deployments/{probe.operation_id}'))
    if (journal['mode'] != 'activate' or journal['state'] != 'finalized'
            or journal['candidate']['id'] != record.id or journal['candidate']['version'] != record.version
            or journal['candidate']['deployed_sha256'] != record.deployed_sha256
            or journal['candidate']['deployed_path'] != record.deployed_path
            or journal['candidate']['kind'] != record.kind
            or _time(probe.observed_at) < _time(journal['started_at'])):
        _reject('Discovery proof does not bind to a committed activation')
    return probe


def _evidence_refs(root, refs):
    if not refs: _reject('Evidence references must be nonempty')
    for ref in refs:
        if not _safe(root, ref).is_file(): _reject('Evidence reference must be an existing local file', path=ref)


def load_catalog(root: Path) -> CapabilityCatalog:
    """Read the typed catalog without mutating journals or filesystem state."""
    root = _project(root)
    return from_dict('CapabilityCatalog', _json(_safe(root, 'capabilities/catalog.json')))


def _pending(root):
    from .lifecycle import _journals
    return {j['candidate']['id'] for _, j in _journals(root) if j['state'] not in ('finalized', 'restored')}


def _consistent(catalog, root):
    catalog = from_dict('CapabilityCatalog', to_dict(catalog))
    ids, targets = set(), set()
    for record in catalog.records:
        if record.id in ids: _reject('Duplicate capability ID')
        ids.add(record.id)
        _, target = _paths(record, root)
        if target is not None:
            if target in targets: _reject('Duplicate native target')
            targets.add(target)
    return catalog


def _active(record, root):
    manifest = _record_manifest(record, root)
    if manifest.manifest_sha256 != record.deployed_sha256: _reject('Native deployment manifest drift')
    _validation(record, root, manifest.manifest_sha256)
    _activation(record, root)


def validate_catalog(catalog: CapabilityCatalog, project_root: Path) -> GateResult:
    errors = []
    try:
        root = _project(project_root)
        catalog = _consistent(catalog, root)
        pending = _pending(root)
        for record in catalog.records:
            if record.id in pending: _reject('Capability has an unfinished deployment')
            if record.state == CapabilityState.ACTIVE: _active(record, root)
    except ValidationError as error:
        errors.extend(error.errors)
    except OSError as error:
        errors.append(ErrorDetail('filesystem_error', '$', str(error)))
    return GateResult(not errors, errors)


def _eligible(catalog: CapabilityCatalog, available_tools: set[str], project_root: Path) -> list[CapabilityRecord]:
    try:
        root = _project(project_root)
        catalog = _consistent(catalog, root)
        if to_dict(catalog) != to_dict(load_catalog(root)): return []
        pending = _pending(root)
    except (ValidationError, OSError): return []
    eligible = []
    for record in catalog.records:
        if record.state != CapabilityState.ACTIVE or record.id in pending or not set(record.tool_dependencies) <= available_tools:
            continue
        try: _active(record, root)
        except (ValidationError, OSError): continue
        eligible.append(record)
    return eligible


def eligible_capabilities(catalog: CapabilityCatalog, available_tools: set[str], project_root: Path) -> list[CapabilityRecord]:
    """Select current active records while holding the existing catalog lock shared.

    Readers never create state. A catalog with deployed proof has an existing
    lifecycle lock; initial empty projects can be inspected without one.
    """
    descriptor = None
    try:
        root = _project(project_root)
        lock = _safe(root, '.smart-assistant/catalog.lock')
        if lock.exists():
            if not lock.is_file(): _reject('Catalog lock must be a regular file')
            descriptor = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
            fcntl.flock(descriptor, fcntl.LOCK_SH)
        return _eligible(catalog, available_tools, root)
    except (ValidationError, OSError): return []
    finally:
        if descriptor is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
