"""Conservative standalone native-agent validation and private draft staging.

Only the documented required native fields are supported. Model overrides need an
observed catalog; this API has no catalog-observation input, so rejects them.
Staging proves structure and bytes, never behavior, discovery or authorization.
"""
from __future__ import annotations

from dataclasses import replace
import fcntl
import os
from pathlib import Path, PurePosixPath
import re
import stat
import shutil
import tempfile
import tomllib

from .catalog import deployment_manifest, load_catalog, validate_catalog
from .contracts import (CapabilityKind, CapabilityRecord, CapabilityState,
    ErrorDetail, GateResult, ValidationError, from_dict, to_dict)

_REQUIRED = {'name', 'description', 'developer_instructions'}
_OVERRIDES = {'model', 'model_reasoning_effort'}
_IDENTITY = re.compile(r'[a-z][a-z0-9_-]{1,63}')


def _reject(code, path, message):
    raise ValidationError([ErrorDetail(code, str(path), message)])


def _nonsymlink(path):
    path = Path(path).absolute()
    for component in [path, *path.parents]:
        if component.is_symlink():
            _reject('unsafe_path', path, 'Paths must not cross symlinks')
    return path


def _read(path):
    path = _nonsymlink(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        _reject('unsafe_path', path, 'Agent definition must be a regular file')
    # O_NOFOLLOW also protects the final component if replaced after inspection.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            _reject('unsafe_path', path, 'Agent definition must be a regular file')
        return stream.read()


def _parse(data, path):
    try:
        return tomllib.loads(data.decode('utf-8'))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        _reject('invalid_toml', path, f'Invalid UTF-8 TOML: {error}')


def _work_cycle(instructions):
    # Match a whole ordered sequence with actual independent review, rather than
    # committing to an earlier unrelated review word in the role description.
    independent_review = (r'(?:\bindependent(?:ly)?\s+review(?:ing)?\b|'
        r'\breview(?:ing)?\s+independently\b|\breview(?:ing)?\s*\(\s*independent\s*\))')
    stages = [r'\bdesign(?:ing)?\b', r'\bimplement(?:ation|ing)?\b',
        independent_review, r'\bfeedback\b', r'\btest(?:ing|s)?\b', r'\brepeat(?:ing)?\b']
    if not re.search(r'[\s\S]*?'.join(stages), instructions, re.IGNORECASE):
        return False
    for directive in re.finditer(r'\b(?:skip|omit|avoid|bypass)\b[^.\n;]{0,80}\b(?:review|test(?:ing|s)?)\b', instructions, re.IGNORECASE):
        prefix = instructions[max(0, directive.start() - 20):directive.start()]
        if not re.search(r'\b(?:not|never)\s+$', prefix, re.IGNORECASE):
            return False
    # Reject concrete operative waivers, not arbitrary semantic interpretations.
    # In particular "no review is complete without tests" remains valid.
    term = r'(?:independent\s+)?(?:review(?:ing)?|test(?:ing|s)?)'
    subject = term + r'(?:\s+(?:and|or)\s+' + term + r')*'
    waivers = [
        r'\b' + subject + r'\s+(?:is|are)\s+(?:optional|unnecessary|not\s+(?:required|needed|necessary|mandatory))\b',
        r'\bno\s+' + subject + r'\s+(?:(?:is|are)\s+)?(?:required|needed|necessary|mandatory)\b',
        r'\bno\s+(?:need|requirement)\s+for\s+' + term + r'\b',
        r'\bno\s+need\s+to\s+(?:independently\s+)?(?:review|test|verify)\b',
    ]
    return not any(re.search(pattern, instructions, re.IGNORECASE) for pattern in waivers)


def _definition(data, path):
    value = _parse(data, path)
    errors = []
    for field in sorted(_REQUIRED):
        if field not in value:
            errors.append(ErrorDetail('missing_field', field, f'Required native field: {field}'))
        elif type(value[field]) is not str or not value[field].strip():
            errors.append(ErrorDetail('invalid_field', field, 'Expected a nonblank string'))
    for field in sorted(set(value) - _REQUIRED):
        if field in _OVERRIDES:
            errors.append(ErrorDetail('unobserved_catalog', field,
                'Override cannot be enabled: no observed available model/effort catalog is supplied; inherit defaults'))
        else:
            errors.append(ErrorDetail('unsupported_field', field,
                'Unsupported optional native configuration; this helper supports name, description and developer_instructions only'))
    identity = value.get('name')
    if type(identity) is str and identity.strip() and not _IDENTITY.fullmatch(identity):
        errors.append(ErrorDetail('invalid_identity', 'name', 'Name must be a contract-compatible lowercase capability ID'))
    instructions = value.get('developer_instructions')
    if type(instructions) is str and instructions.strip() and not _work_cycle(instructions):
        errors.append(ErrorDetail('missing_work_cycle', 'developer_instructions',
            'Include ordered design, implementation, independent review, feedback, testing and repeat; do not skip review/testing'))
    if errors:
        raise ValidationError(errors)
    return value


def validate_agent_definition(path: Path) -> GateResult:
    """Check a conservative required-field schema without native/evaluation proof."""
    try:
        _definition(_read(path), path)
        return GateResult(True, [])
    except ValidationError as error:
        return GateResult(False, error.errors)
    except OSError as error:
        return GateResult(False, [ErrorDetail('filesystem_error', str(path), str(error))])


def _inside(root, path):
    path = _nonsymlink(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        _reject('unsafe_path', path, 'Path must be strictly inside the project')
    return resolved


def _target(root, relative):
    if relative is None:
        _reject('unsafe_path', 'deployed_path', 'Native agent target is required')
    parts = PurePosixPath(relative).parts
    if (len(parts) != 3 or parts[:2] != ('.codex', 'agents')
            or parts[2].startswith('.') or not parts[2].endswith('.toml')):
        _reject('unsafe_path', 'deployed_path', 'Target must be .codex/agents/<basename>.toml')
    return _inside(root, root / relative)


def _collisions(root, record, target):
    catalog = load_catalog(root)
    gate = validate_catalog(catalog, root)
    if not gate.passed:
        raise ValidationError(gate.errors)
    previous = next((r for r in catalog.records if r.id == record.id), None)
    if previous is not None:
        if previous.kind != record.kind or previous.deployed_path != record.deployed_path:
            _reject('identity_collision', record.id, 'Registered identity must preserve kind and native target')
        if previous.version == record.version:
            _reject('immutable_version', record.version, 'Registered versions cannot be reused; stage a new version')
    if any(r.id != record.id and r.deployed_path == record.deployed_path for r in catalog.records):
        _reject('target_collision', record.deployed_path, 'Native target belongs to another capability')
    if target.exists() and previous is None:
        _reject('target_collision', record.deployed_path, 'Unregistered native target already exists')
    native = _inside(root, root / '.codex/agents')
    if native.exists():
        if not native.is_dir():
            _reject('unsafe_path', native, 'Native agent directory must be a directory')
        for asset in sorted(native.iterdir()):
            _nonsymlink(asset)
            if asset.suffix != '.toml':
                continue
            name = _parse(_read(asset), asset).get('name')
            if type(name) is not str or not _IDENTITY.fullmatch(name):
                _reject('invalid_identity', asset, 'Cannot establish native agent identity')
            if name == record.id and (previous is None or asset != target):
                _reject('identity_collision', asset, 'Native agent name already exists')
            if asset == target and name != record.id:
                _reject('identity_collision', asset, 'Registered target contains a different native identity')


def stage_agent(project_root: Path, definition_path: Path, record: CapabilityRecord) -> CapabilityRecord:
    """Copy validated bytes into an immutable private version; never activate."""
    try:
        record = from_dict('CapabilityRecord', to_dict(record))
        if record.kind != CapabilityKind.AGENT or record.state != CapabilityState.DRAFT:
            _reject('invalid_candidate', '$', 'Staging requires an AGENT in DRAFT state')
        root = _nonsymlink(project_root)
        if not root.is_dir():
            _reject('unsafe_path', root, 'Project root must be an existing directory')
        root = root.resolve()
        source = _inside(root, definition_path if Path(definition_path).is_absolute() else root / definition_path)
        relative = source.relative_to(root).parts
        if relative[0] in ('.agents', '.codex') or relative[:2] == ('.smart-assistant', 'deployments'):
            _reject('unsafe_path', source, 'Definition must remain outside native discovery and deployment journals')
        data = _read(source)
        definition = _definition(data, source)
        if definition['name'] != record.id:
            _reject('identity_mismatch', 'name', 'Native name must match capability record ID')
        target = _target(root, record.deployed_path)
        _collisions(root, record, target)
        version = _inside(root, root / 'capabilities/staging/agents' / record.id / record.version)
        if source == version or version in source.parents or source in version.parents:
            _reject('unsafe_path', source, 'Source and version staging must not overlap')
        if version.exists():
            _reject('immutable_version', version, 'Version staging already exists; use a new version')
        version.parent.mkdir(parents=True, exist_ok=True)
        _inside(root, version.parent)
        # Complete the invocation-owned copy before exposing an immutable version.
        # A failed attempt cleans only its unique temporary directory, never a
        # preexisting version or a version published by another invocation.
        temporary = Path(tempfile.mkdtemp(prefix='.stage-', dir=version.parent))
        try:
            staged = temporary / target.name
            descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            digest = deployment_manifest(staged).manifest_sha256
            result = replace(record, source_path=(version / target.name).relative_to(root).as_posix(),
                deployed_sha256=digest, validation_refs=[], discovery_probe_ref=None, rollback_ref=None)
            result = from_dict('CapabilityRecord', to_dict(result))
            lock = _inside(root, version.parent / '.stage.lock')
            if lock.exists() and not stat.S_ISREG(lock.lstat().st_mode):
                _reject('unsafe_path', lock, 'Staging lock must be a regular file')
            descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            with os.fdopen(descriptor, 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    _reject('unsafe_path', lock, 'Staging lock must be a regular file')
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    _inside(root, version)
                    if version.exists():
                        _reject('immutable_version', version, 'Version staging already exists; use a new version')
                    os.rename(temporary, version)
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            return result
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    except OSError as error:
        _reject('filesystem_error', '$', str(error))
