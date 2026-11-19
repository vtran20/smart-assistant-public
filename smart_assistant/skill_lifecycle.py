"""Validate a documented minimal skill format and stage immutable complete assets.

This module does not parse full YAML, run scripts, evaluate model behavior,
activate native assets, or write the capability catalog. See docs/tasks/p06.
"""
from __future__ import annotations

from dataclasses import replace
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
from urllib.parse import unquote, urlsplit
import uuid

from .catalog import (deployment_manifest, load_catalog, validate_catalog,
                      _paths, _project, _safe)
from .contracts import (CapabilityKind, CapabilityRecord, CapabilityState,
                        ErrorDetail, GateResult, ValidationError, canonical_json,
                        from_dict, to_dict)


_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


def _reject(code, path, message):
    raise ValidationError([ErrorDetail(code, str(path), message)])


def _ancestors(path):
    path = Path(os.path.abspath(path))
    for part in [path, *path.parents]:
        if part.is_symlink():
            _reject('unsafe_path', part, 'Skill assets and ancestors cannot be symlinks')
    return path


def _definition(path):
    path = _ancestors(path)
    if path.is_dir(): path = path / 'SKILL.md'
    if path.name != 'SKILL.md' or not path.is_file():
        _reject('invalid_definition', path, 'Expected a regular SKILL.md file or skill directory')
    if not stat.S_ISREG(path.lstat().st_mode):
        _reject('unsafe_path', path, 'Skill definition must be a regular file')
    return path


def _tree(root):
    _ancestors(root)
    paths = []
    for item in sorted(root.rglob('*')):
        mode = item.lstat().st_mode
        if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
            _reject('unsafe_path', item, 'Skill resources must be nonsymlink regular files/directories')
        paths.append(item)
    return paths


def _scalar(raw, path):
    raw = raw.strip()
    if not raw:
        _reject('unsupported_metadata', path, 'Empty/multiline YAML scalars are unsupported; use one-line text')
    if raw.startswith('"'):
        try: value = json.loads(raw)
        except ValueError:
            _reject('unsupported_metadata', path, 'Double quoted scalars must use JSON-compatible escaping')
        if type(value) is not str:
            _reject('unsupported_metadata', path, 'Metadata requires text scalars')
    elif raw.startswith("'"):
        if not re.fullmatch(r"'(?:[^']|'')*'", raw):
            _reject('unsupported_metadata', path, 'Single quoted scalars use doubled quote escaping')
        value = raw[1:-1].replace("''", "'")
    else:
        implicit = re.fullmatch(r'(?i:null|true|false|yes|no|on|off|~|\.nan|[-+]?\.inf)', raw)
        numeric = re.fullmatch(r'[-+]?(?:\d[\d_.eExXa-fA-F:+-]*|\.\d[\d.eE+-]*)', raw)
        if (implicit or numeric or raw[0] in '-?:,[]{}#&*!|>\'"%@`'
                or raw.endswith(':') or re.search(r'\s#|:\s|[\[\]{}]', raw)):
            _reject('unsupported_metadata', path, 'Ambiguous YAML plain scalar; quote this one-line text')
        value = raw
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        _reject('unsupported_metadata', path, 'Metadata values must be one-line text without control characters')
    return value


def _parse(path):
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    if not lines or lines[0] != '---':
        _reject('missing_metadata', path, 'SKILL.md must start with name/description frontmatter')
    try: end = lines.index('---', 1)
    except ValueError:
        _reject('unsupported_metadata', path, 'Frontmatter requires a closing --- line')
    metadata = {}
    for line in lines[1:end]:
        if not line.strip(): continue
        match = re.fullmatch(r'(name|description):[ \t]*(.*)', line)
        if not match or match[1] in metadata:
            _reject('unsupported_metadata', path, 'Supported frontmatter has unique top-level name and description only')
        metadata[match[1]] = _scalar(match[2], path)
    if set(metadata) != {'name', 'description'}:
        _reject('missing_metadata', path, 'Both name and description are required')
    if not _NAME.fullmatch(metadata['name']) or len(metadata['name']) >= 64:
        _reject('invalid_metadata', path, 'Name requires lowercase letters/digits separated by hyphens, under 64 characters')
    if not metadata['description'].strip() or len(metadata['description']) > 1024:
        _reject('invalid_metadata', path, 'Description must be nonempty text of at most 1024 characters')
    return metadata, '\n'.join(lines[end + 1:])


def _prose(body):
    # Ignore examples when checking actual instructions and local resource links.
    lines, fence = [], None
    for line in body.splitlines():
        match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if match:
            marker = match[1][0]
            if fence is None: fence = marker
            elif fence == marker: fence = None
            continue
        if fence is None: lines.append(line)
    return '\n'.join(lines)


def _body_errors(body, path):
    prose = _prose(body).lower()
    errors = []
    def require(pattern, code, message):
        if not re.search(pattern, prose): errors.append(ErrorDetail(code, str(path), message))
    require(r'\b(?:use when|invoke|trigger|intended scope|boundar\w*)\b',
            'missing_scope', 'Instructions must describe intended invocation scope')
    require(r'\b(?:output|deliver\w*|produce\w*|artifact|result)\b',
            'missing_output', 'Instructions must specify the produced output')
    require(r'\b(?:verif\w*|test\w*|checks?|validat\w*)\b',
            'missing_verification', 'Instructions must specify verification')
    categories = [r'\b(?:design|plan\w*)\b', r'\b(?:implement\w*|build|write)\b',
                  r'(?:\b(?:independent|fresh|separate)\b.{0,50}\breview\w*\b|\breview\w*\b.{0,30}\bindependently\b)',
                  r'\b(?:feedback|findings|dispositions?)\b',
                  r'\b(?:test\w*|checks?|verif\w*)\b',
                  r'\b(?:repeat|iterat\w*)\b']
    if any(not re.search(pattern, prose, re.DOTALL) for pattern in categories):
        errors.append(ErrorDetail('missing_work_cycle', str(path),
            'Instructions require design, implementation, independent review, feedback, tests and repetition'))
    waiver_prose = re.sub(r"\b(?:never|must not|do not|don't)\s+(?:skip|omit|bypass|avoid)\b", '', prose)
    # Exempt only a requiring prefix through "without", not its object or
    # later clauses. Explicit waivers after conjunctions must stay visible.
    step_object = r'(?:(?:the|an?|any|independent|fresh|separate)\s+)*(?:review\w*|test\w*|checks?)\b'
    object_lookahead = r'(?=\s+(?:(?:doing|performing|running)\s+)?' + step_object + ')'
    waiver_prose = re.sub(
        r"\b(?:never|must not|do not|don't)\s+(?:proceed|continue|finish|complete|ship|submit|deliver)\s+without\b" + object_lookahead,
        '', waiver_prose)
    required_subject = r'(?:(?:independent|fresh|separate|verified|completed)\s+)*(?:review\w*|test\w*|checks?|task|result|deliverable|work|acceptance)\b'
    waiver_prose = re.sub(
        r'\bno\s+' + required_subject + r'\s+(?:is|are)\s+(?:complete|acceptable|valid)\s+without\b' + object_lookahead,
        '', waiver_prose)
    waiver_patterns = [
        r'\b(?:skip|omit|bypass|avoid|without|no need (?:for|to))\s+(?:(?:doing|performing|running)\s+)?' + step_object,
        r'\bno\s+(?:independent\s+)?(?:review|testing|tests|checks)\s+(?:is |are )?(?:needed|required|necessary)',
        r'\b(?:review\w*|test\w*|checks?)\b[^.\n]{0,30}\b(?:optional|unnecessary|not required|not necessary)\b',
    ]
    if any(re.search(pattern, waiver_prose) for pattern in waiver_patterns):
        errors.append(ErrorDetail('unsafe_work_cycle', str(path), 'Instructions cannot waive review or testing'))
    return errors


def _destination(reference, document):
    """Extract the supported Markdown destination before an optional quoted title."""
    reference = reference.strip()
    if reference.startswith('<'):
        match = re.fullmatch(r"<([^<>\n]*)>(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?", reference)
    else:
        match = re.fullmatch(r"(\S+)(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?", reference)
    if not match:
        _reject('unsupported_resource_reference', document,
                'Resource references require a plain or angle destination and optional quoted title')
    return match[1]


def _resource(root, document, reference):
    reference = _destination(reference, document)
    if re.match(r'^[a-zA-Z]:[\\/]', reference):
        _reject('unsafe_path', document, f'Local drive path is forbidden: {reference}')
    parsed = urlsplit(reference)
    if parsed.scheme and parsed.scheme.lower() != 'file': return
    if not parsed.scheme and parsed.netloc and reference.startswith('//'): return
    if not parsed.path and not parsed.netloc: return  # In-document anchor.
    decoded = unquote(parsed.path)
    if (parsed.scheme or parsed.netloc or decoded.startswith('/') or '\\' in decoded
            or '..' in decoded.split('/')):
        _reject('unsafe_path', document, f'Local resource cannot escape the skill directory: {reference}')
    candidate = document.parent / decoded
    if not candidate.resolve().is_relative_to(root):
        _reject('unsafe_path', document, f'Resource escapes skill directory: {reference}')
    _ancestors(candidate)
    if not candidate.exists():
        _reject('missing_resource', document, f'Local resource is missing: {reference}')


_CODE_SPAN = re.compile(r'(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)', re.DOTALL)


def _resources(root, paths):
    for document in paths:
        if document.suffix.lower() != '.md' or not document.is_file(): continue
        prose = _prose(document.read_text(encoding='utf-8'))
        markup = _CODE_SPAN.sub(' ', prose)
        for match in re.finditer(r'!?\[[^\]\n]*\]\(([^\n]*?)\)', markup):
            _resource(root, document, match[1])
        definitions = {}
        for match in re.finditer(r'^\s*\[([^\]]+)\]:\s*(.+?)\s*$', markup, re.MULTILINE):
            definitions[match[1].casefold()] = match[2]
            _resource(root, document, match[2])
        for match in re.finditer(r'\[([^\]\n]+)\]\[([^\]\n]*)\]', markup):
            key = (match[2] or match[1]).casefold()
            if key not in definitions:
                _reject('missing_resource', document, f'Undefined resource reference: {key}')
        for match in _CODE_SPAN.finditer(prose):
            token = match[2].strip()
            # A standalone path token is attested. Literal markup and whole
            # command examples are not interpreted as a file dependency.
            if (('/' in token or '\\' in token) and not re.search(r'\s', token)
                    and not re.match(r'!?\[', token)):
                _resource(root, document, token)


def validate_skill_definition(path: Path) -> GateResult:
    """Structural validation only; unsupported YAML returns unsupported_metadata."""
    try:
        definition = _definition(path)
        paths = _tree(definition.parent)
        _, body = _parse(definition)
        errors = _body_errors(body, definition)
        _resources(definition.parent, paths)
        return GateResult(not errors, errors)
    except ValidationError as error:
        return GateResult(False, error.errors)
    except (OSError, UnicodeError, ValueError) as error:
        return GateResult(False, [ErrorDetail('filesystem_error', str(path), str(error))])


def _collisions(root, record):
    catalog = load_catalog(root)
    gate = validate_catalog(catalog, root)
    if not gate.passed: raise ValidationError(gate.errors)
    previous = next((item for item in catalog.records if item.id == record.id), None)
    if previous:
        if previous.kind != record.kind or previous.deployed_path != record.deployed_path:
            _reject('identity_collision', record.id, 'Registered ID must preserve kind and native target')
        if previous.version == record.version:
            _reject('immutable_version', record.version, 'Registered version cannot be restaged; reuse its preserved assets')
    if any(item.id != record.id and item.deployed_path == record.deployed_path for item in catalog.records):
        _reject('identity_collision', record.deployed_path, 'Native target belongs to another capability')
    _, target = _paths(record, root)
    if target.exists():
        if previous is None:
            _reject('identity_collision', record.deployed_path, 'Unregistered native target already exists')
        manifest = deployment_manifest(target)
        if manifest.manifest_sha256 != previous.deployed_sha256:
            _reject('identity_collision', record.deployed_path, 'Native target differs from registered manifest')


def _copy_tree(source, target):
    target.mkdir()
    for item in _tree(source):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_dir():
            destination.mkdir()
        else:
            _ancestors(item)
            descriptor = os.open(item, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    _reject('unsafe_path', item, 'Resource changed to a nonregular file while staging')
                with destination.open('xb') as output:
                    shutil.copyfileobj(stream, output)
                    output.flush()
                    os.fsync(output.fileno())
            destination.chmod(stat.S_IMODE(item.stat().st_mode))


def stage_skill(project_root: Path, definition_path: Path, record: CapabilityRecord) -> CapabilityRecord:
    """Return a fresh DRAFT record and actual structural receipt, never evaluation."""
    root = _project(_ancestors(project_root))
    record = from_dict('CapabilityRecord', to_dict(record))
    if record.kind != CapabilityKind.SKILL or record.state != CapabilityState.DRAFT:
        _reject('invalid_candidate', record.id, 'Skill staging requires a normalized DRAFT SKILL record')
    gate = validate_skill_definition(definition_path)
    if not gate.passed: raise ValidationError(gate.errors)
    definition = _definition(definition_path)
    metadata, _ = _parse(definition)
    target = '.agents/skills/' + metadata['name']
    if record.name != metadata['name'] or record.deployed_path not in (None, target):
        _reject('identity_collision', record.id, 'Record name and native target must match skill metadata name')
    source_path = f'capabilities/staging/{record.id}/{record.version}/skill'
    fresh = replace(record, source_path=source_path, deployed_path=target,
                    deployed_sha256=None, validation_refs=[], discovery_probe_ref=None, rollback_ref=None)
    source, _ = _paths(fresh, root)
    original = definition.parent
    if original == source or original in source.parents or source in original.parents:
        _reject('unsafe_path', original, 'Definition and staging trees cannot overlap')
    storage = _safe(root, '.smart-assistant')
    storage.mkdir(exist_ok=True)
    lock = _safe(root, '.smart-assistant/catalog.lock')
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    temporary = None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            _reject('unsafe_path', lock, 'Catalog lock must be a regular file')
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _collisions(root, fresh)
        version = _safe(root, str(Path(source_path).parent))
        if version.exists():
            _reject('immutable_version', version, 'Staged version slot already exists')
        version.parent.mkdir(parents=True, exist_ok=True)
        _safe(root, version.parent.relative_to(root).as_posix())
        temporary = version.parent / ('.staging-' + uuid.uuid4().hex)
        temporary.mkdir()
        before = deployment_manifest(original)
        _copy_tree(original, temporary / 'skill')
        copied_gate = validate_skill_definition(temporary / 'skill')
        if not copied_gate.passed: raise ValidationError(copied_gate.errors)
        manifest = deployment_manifest(temporary / 'skill')
        if manifest != before or deployment_manifest(original) != before:
            _reject('source_changed', definition, 'Complete resource manifest changed during staging')
        observation_ref = str(Path(source_path).parent / 'structural-observation.json')
        validation_ref = str(Path(source_path).parent / 'validation.json')
        observation = dict(schema_version=1, method='validate_skill_definition',
                           passed=True, manifest=to_dict(manifest), errors=[])
        validation = dict(schema_version=1, kind='validation', capability_id=fresh.id,
                          version=fresh.version, manifest_sha256=manifest.manifest_sha256,
                          passed=True, evidence_refs=[observation_ref])
        (temporary / 'structural-observation.json').write_bytes(canonical_json(observation))
        (temporary / 'validation.json').write_bytes(canonical_json(validation))
        # The slot and its structural evidence become visible together.
        os.rename(temporary, version)
        temporary = None
        return replace(fresh, deployed_sha256=manifest.manifest_sha256, validation_refs=[validation_ref])
    finally:
        if temporary is not None: shutil.rmtree(temporary)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
