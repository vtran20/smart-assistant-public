"""Read-only explicit Markdown selection; integrity is not semantic approval.

No pack resolver, profile loader, content classifier or delivery gate is implied.
Applicability/version/conflict declarations remain caller assertions for review.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .contracts import ErrorDetail, ValidationError
from .state import _canonical_root, _id, _open_directory, _open_regular, _root_fd

_MAX_BYTES = 1024 * 1024
_PROJECT_PATHS = ('AGENTS.md', 'docs/project-context.md', 'docs/implementation-lessons.md')
_REVALIDATE = ('source_changed', 'project_context_changed', 'scope_or_version_changed',
               'conflict_resolution_required', 'downstream_revalidation_required')
_SYMBOL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')


@dataclass(frozen=True)
class ScopeMetadata:
    releases: tuple[str, ...] = ()
    jdk: str | None = None
    platform: str | None = None
    custom_layers: tuple[str, ...] = ()
    business_constraints: tuple[str, ...] = ()
    integration_ownership: tuple[str, ...] = ()
    test_entrypoints: tuple[str, ...] = ()
    build_entrypoints: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeRequest:
    project_id: str
    topic_paths: tuple[str, ...]
    project_paths: tuple[str, ...]
    scope: ScopeMetadata
    guidance_version: str | None = None
    applicability: str = 'unknown'
    conflict_refs: tuple[str, ...] = ()
    revalidation_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourcePin:
    origin: str
    path: str
    sha256: str | None
    size_bytes: int | None


@dataclass(frozen=True)
class GitProvenance:
    commit: str | None
    dirty: bool | None
    selected_dirty_paths: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class KnowledgeSelection:
    schema_version: int
    project_id: str
    project_binding: str
    kb_binding: str
    sources: tuple[SourcePin, ...]
    project_context_digest: str
    request: KnowledgeRequest
    git: GitProvenance
    retrieved_at: str
    revalidation_codes: tuple[str, ...]
    usable: bool
    selection_digest: str


@dataclass(frozen=True)
class RevalidationResult:
    valid: bool
    reason_codes: tuple[str, ...]


def _invalid(code: str = 'invalid_selection') -> ValidationError:
    return ValidationError([ErrorDetail(code, '$', 'Invalid or unavailable knowledge selection input')])


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True).encode()).hexdigest()


def selection_to_dict(selection: KnowledgeSelection) -> dict:
    """Serialize references and integrity metadata, never document bodies."""
    _validate_selection(selection)
    return asdict(selection)


def _selection_digest(selection: KnowledgeSelection) -> str:
    wire = asdict(selection)
    del wire['selection_digest']
    return _digest(wire)


def _path(value: str) -> tuple[str, ...]:
    if type(value) is not str or len(value) > 512 or '\\' in value:
        raise _invalid('unsafe_path')
    parts = tuple(value.split('/'))
    if (not value.endswith('.md') or any(not _SYMBOL.fullmatch(p) or p.startswith('.')
                                          for p in parts)
            or any(p.lower().removesuffix('.md') in (
                'client-notes', 'tools', 'profile', 'profiles', 'private',
                'credential', 'credentials', 'secret', 'secrets') for p in parts)):
        raise _invalid('unsafe_path')
    return parts


def _symbol_or_ref(value: str) -> None:
    if type(value) is not str:
        raise _invalid()
    if '/' in value:
        _path(value)
    elif not _SYMBOL.fullmatch(value) or value.startswith('.'):
        raise _invalid()


def _tuple(value) -> None:
    if type(value) is not tuple or len(value) > 64:
        raise _invalid()


def _validate_request(request: KnowledgeRequest) -> None:
    if type(request) is not KnowledgeRequest or type(request.scope) is not ScopeMetadata:
        raise _invalid()
    _id(request.project_id)
    for paths in (request.project_paths, request.topic_paths):
        _tuple(paths)
        for path in paths:
            _path(path)
        if len(set(paths)) != len(paths):
            raise _invalid('duplicate_source')
    if (not request.project_paths or request.project_paths[0] != 'AGENTS.md'
            or any(p not in _PROJECT_PATHS for p in request.project_paths)):
        raise _invalid('invalid_project_sources')
    if any(p in ('AGENTS.md', 'README.md') for p in request.topic_paths):
        raise _invalid('duplicate_source')
    if len(request.topic_paths) + 2 > 64:
        raise _invalid('selection_limit')
    if request.applicability not in ('applicable', 'unknown', 'inapplicable'):
        raise _invalid()
    if request.guidance_version is not None:
        _symbol_or_ref(request.guidance_version)
    for refs in (request.conflict_refs, request.revalidation_refs):
        _tuple(refs)
        for ref in refs:
            _symbol_or_ref(ref)
    for field in fields(request.scope):
        value = getattr(request.scope, field.name)
        if field.name in ('jdk', 'platform'):
            if value is not None:
                _symbol_or_ref(value)
        else:
            _tuple(value)
            for item in value:
                _symbol_or_ref(item)


def _timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value):
        raise _invalid('invalid_timestamp')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise _invalid('invalid_timestamp') from None
    return value


def _usable(request: KnowledgeRequest, git: GitProvenance) -> bool:
    complete = all(bool(getattr(request.scope, f.name)) for f in fields(request.scope))
    return (request.applicability == 'applicable' and bool(request.guidance_version)
            and complete and not request.conflict_refs and git.status != 'unavailable')


def _hash(value) -> bool:
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _validate_selection(selection: KnowledgeSelection) -> None:
    """Check types and cross-field consistency before exposing any record values."""
    if type(selection) is not KnowledgeSelection:
        raise _invalid('invalid_record')
    _validate_request(selection.request)
    request = selection.request
    if (type(selection.schema_version) is not int or selection.schema_version != 1
            or selection.project_id != request.project_id
            or selection.revalidation_codes != _REVALIDATE
            or not all(_hash(v) for v in (selection.project_binding, selection.kb_binding,
                                         selection.project_context_digest, selection.selection_digest))):
        raise _invalid('invalid_record')
    if type(selection.retrieved_at) is not str:
        raise _invalid('invalid_record')
    _timestamp(selection.retrieved_at)
    if type(selection.sources) is not tuple:
        raise _invalid('invalid_record')
    expected = [('project', p) for p in request.project_paths] + [
        ('kb', p) for p in ('AGENTS.md', 'README.md', *request.topic_paths)]
    if len(selection.sources) != len(expected):
        raise _invalid('invalid_record')
    for source, (origin, path) in zip(selection.sources, expected):
        if type(source) is not SourcePin or source.origin != origin or source.path != path:
            raise _invalid('invalid_record')
        if source.sha256 is None:
            if origin != 'project' or path == 'AGENTS.md' or source.size_bytes is not None:
                raise _invalid('invalid_record')
        elif not _hash(source.sha256) or type(source.size_bytes) is not int or not 0 <= source.size_bytes <= _MAX_BYTES:
            raise _invalid('invalid_record')
    if selection.project_context_digest != _digest([
            asdict(p) for p in selection.sources if p.origin == 'project']):
        raise _invalid('invalid_record')
    git = selection.git
    if type(git) is not GitProvenance or type(git.selected_dirty_paths) is not tuple:
        raise _invalid('invalid_record')
    if git.status == 'git':
        if (type(git.commit) is not str or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', git.commit)
                or type(git.dirty) is not bool
                or any(type(p) is not str or ('kb', p) not in expected for p in git.selected_dirty_paths)
                or tuple(sorted(set(git.selected_dirty_paths))) != git.selected_dirty_paths
                or (git.selected_dirty_paths and not git.dirty)):
            raise _invalid('invalid_record')
    elif git.status not in ('not_git', 'unavailable') or git.commit is not None or git.dirty is not None or git.selected_dirty_paths:
        raise _invalid('invalid_record')
    if (type(selection.usable) is not bool or selection.usable != _usable(request, git)
            or selection.selection_digest != _selection_digest(selection)):
        raise _invalid('invalid_record')


def _identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _read(root_fd: int, origin: str, path: str, optional: bool) -> SourcePin:
    parts = _path(path)
    current = os.dup(root_fd)
    chain = []
    fd = None
    try:
        for part in parts[:-1]:
            child = _open_directory(current, part)
            chain.append((current, part, child))
            current = child
        fd = _open_regular(current, parts[-1], os.O_RDONLY)
        before = os.fstat(fd)
        if before.st_size > _MAX_BYTES:
            raise _invalid('source_limit')
        chunks = []
        remaining = _MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b''.join(chunks)
        if len(body) > _MAX_BYTES:
            raise _invalid('source_limit')
        body.decode('utf-8')
        named = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        if _identity(before) != _identity(os.fstat(fd)) or _identity(before) != _identity(named):
            raise _invalid('source_changed')
        for parent, name, child in chain:
            attached = os.stat(name, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(child)
            if (attached.st_dev, attached.st_ino, attached.st_mode) != (opened.st_dev, opened.st_ino, opened.st_mode):
                raise _invalid('source_changed')
        return SourcePin(origin, path, hashlib.sha256(body).hexdigest(), len(body))
    except FileNotFoundError:
        if optional:
            return SourcePin(origin, path, None, None)
        raise _invalid('missing_source') from None
    except (OSError, UnicodeError):
        raise _invalid('unsafe_source') from None
    finally:
        if fd is not None:
            os.close(fd)
        os.close(current)
        for parent, _, _ in reversed(chain):
            os.close(parent)


def _git(root: Path, paths: tuple[str, ...]) -> GitProvenance:
    absent = GitProvenance(None, None, (), 'not_git')
    unavailable = GitProvenance(None, None, (), 'unavailable')
    # Only a root with its own Git metadata is eligible; never inherit an ancestor.
    try:
        metadata = root / '.git'
        if metadata.is_symlink():
            return unavailable
        if not metadata.exists():
            return absent
        if (root / '.gitmodules').exists() or (root / '.gitmodules').is_symlink():
            return unavailable
        environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        environment.update(GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1',
                           GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_LAZY_FETCH='1')

        def run(*args):
            result = subprocess.run(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
                                     '-c', 'core.untrackedCache=false', '-c', 'submodule.recurse=false',
                                     '-c', 'core.excludesFile=' + os.devnull,
                                     '-C', str(root), *args], capture_output=True,
                                    timeout=5, env=environment, check=False)
            if result.returncode:
                raise ValueError
            return result.stdout

        # Config inspection itself does not run filters/fsmonitor. Never run status
        # when local includes, helper definitions or worktree-specific config could
        # supply executable behavior. Values remain private and are never emitted.
        config = run('config', '--local', '--no-includes', '--null', '--list')
        if len(config) > _MAX_BYTES or (config and not config.endswith(b'\0')):
            return unavailable
        for entry in config.split(b'\0'):
            if not entry:
                continue
            key = entry.split(b'\n', 1)[0].decode('utf-8').lower()
            if not re.fullmatch(r'[a-z][a-z0-9-]*\.[^\x00-\x1f]+', key):
                return unavailable
            if (key.startswith(('filter.', 'include.', 'includeif.'))
                    or key in ('core.fsmonitor', 'extensions.worktreeconfig')
                    or (key.startswith('diff.') and key.endswith(('.command', '.textconv')))):
                return unavailable
        top = run('rev-parse', '--show-toplevel').decode().strip()
        if Path(top) != root:
            return unavailable
        commit = run('rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
            return unavailable
        index = run('ls-files', '--stage', '-z')
        if len(index) > _MAX_BYTES or (index and not index.endswith(b'\0')):
            return unavailable
        for entry in index.split(b'\0'):
            if not entry:
                continue
            if not re.match(rb'[0-9]{6} [0-9a-f]{40,64} [0-3]\t', entry) or entry.startswith(b'160000 '):
                return unavailable
        status = run('status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=all')
        entries = status.split(b'\0')
        changed = set()
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if not entry:
                continue
            if len(entry) < 4 or entry[2:3] != b' ':
                return unavailable
            path = entry[3:].decode('utf-8')
            if path in paths:
                changed.add(path)
            if b'R' in entry[:2] or b'C' in entry[:2]:
                if index >= len(entries) or not entries[index]:
                    return unavailable
                previous = entries[index].decode('utf-8')
                index += 1
                if previous in paths:
                    changed.add(previous)
        return GitProvenance(commit, bool(status), tuple(sorted(changed)), 'git')
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return unavailable


def select_knowledge(*, project_root: Path, kb_root: Path, request: KnowledgeRequest,
                     retrieved_at: str | None = None) -> KnowledgeSelection:
    """Pin explicit project context and KB references without reading profiles."""
    _validate_request(request)
    stamp = _timestamp(retrieved_at)
    kb_paths = ('AGENTS.md', 'README.md', *request.topic_paths)
    try:
        project = _canonical_root(Path(project_root))
        kb = _canonical_root(Path(kb_root))
        with _root_fd(project) as project_fd, _root_fd(kb) as kb_fd:
            project_stat, kb_stat = os.fstat(project_fd), os.fstat(kb_fd)
            before_git = _git(kb, kb_paths)

            def pins():
                return tuple([_read(project_fd, 'project', p, p != 'AGENTS.md')
                              for p in request.project_paths] +
                             [_read(kb_fd, 'kb', p, False) for p in kb_paths])

            sources = pins()
            if sources != pins():
                raise _invalid('source_changed')
            after_git = _git(kb, kb_paths)
            if before_git != after_git:
                raise _invalid('source_changed')
            # Verify roots remain attached to the originally opened directories.
            with _root_fd(project) as fresh_project, _root_fd(kb) as fresh_kb:
                for old, fresh in ((project_stat, os.fstat(fresh_project)), (kb_stat, os.fstat(fresh_kb))):
                    if (old.st_dev, old.st_ino) != (fresh.st_dev, fresh.st_ino):
                        raise _invalid('source_changed')
            binding = _digest([str(project), project_stat.st_dev, project_stat.st_ino])
            kb_binding = _digest([str(kb), kb_stat.st_dev, kb_stat.st_ino])
    except OSError:
        raise _invalid('unavailable_source') from None
    usable = _usable(request, after_git)
    selection = KnowledgeSelection(
        1, request.project_id, binding, kb_binding, sources,
        _digest([asdict(pin) for pin in sources if pin.origin == 'project']),
        request, after_git, stamp, _REVALIDATE, usable, '')
    return replace(selection, selection_digest=_selection_digest(selection))


def revalidate_selection(selection: KnowledgeSelection, *, project_root: Path,
                         kb_root: Path, request: KnowledgeRequest) -> RevalidationResult:
    """Recompute actual pins; do not replace stale evidence or approve semantics."""
    if type(selection) is not KnowledgeSelection:
        return RevalidationResult(False, ('invalid_record',))
    try:
        _validate_selection(selection)
        current = select_knowledge(project_root=project_root, kb_root=kb_root,
                                   request=request, retrieved_at=selection.retrieved_at)
    except (ValidationError, TypeError, ValueError):
        return RevalidationResult(False, ('unavailable_or_unsafe_source',))
    reasons = []
    for name, reason in (('project_binding', 'project_changed'), ('kb_binding', 'kb_changed'),
                         ('project_id', 'project_changed'), ('request', 'scope_or_version_changed'),
                         ('sources', 'source_changed'), ('project_context_digest', 'project_context_changed'),
                         ('git', 'git_provenance_changed'), ('revalidation_codes', 'invalid_record')):
        if getattr(selection, name) != getattr(current, name):
            reasons.append(reason)
    if not selection.usable or not current.usable:
        reasons.append('unusable_selection')
    return RevalidationResult(not reasons, tuple(reasons))
