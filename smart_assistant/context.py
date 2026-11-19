"""Read one project's optional context and one selected role overlay."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .contracts import ContextBundle, ErrorDetail, ValidationError, from_dict
from .state import _id, _open_directory, _open_regular, _root_fd


def _invalid(code: str, path: str, message: str) -> ValidationError:
    return ValidationError([ErrorDetail(code, path, message)])


def _read_optional(root_fd: int, directories: tuple[str, ...], name: str,
                   project_id: str, scope: str) -> ContextBundle | None:
    current_fd = os.dup(root_fd)
    try:
        for directory in directories:
            try:
                next_fd = _open_directory(current_fd, directory)
            except FileNotFoundError:
                return None
            os.close(current_fd)
            current_fd = next_fd
        try:
            fd = _open_regular(current_fd, name, os.O_RDONLY)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            try:
                wire = json.load(stream)
            except (ValueError, UnicodeError) as exc:
                raise _invalid('malformed_json', '$', 'Malformed context JSON') from exc
    finally:
        os.close(current_fd)
    bundle = from_dict('ContextBundle', wire)
    if bundle.project_id != project_id:
        raise _invalid('scope_mismatch', '$.project_id', 'Context project does not match selection')
    for index, fact in enumerate(bundle.facts):
        if fact.scope != scope:
            raise _invalid('scope_mismatch', f'$.facts[{index}].scope', 'Context fact scope does not match selection')
    return bundle


def load_context(root: Path, project_id: str, role_id: str | None = None) -> ContextBundle:
    """Combine exact project context and the selected role's optional context."""
    _id(project_id, '$.project_id')
    if role_id is not None:
        _id(role_id, '$.role_id')
    try:
        with _root_fd(Path(root)) as root_fd:
            project = _read_optional(root_fd, ('context', 'projects'),
                                     f'{project_id}.json', project_id,
                                     f'project:{project_id}')
            role = None
            if role_id is not None:
                role = _read_optional(root_fd, ('context', 'projects', project_id, 'roles'),
                                      f'{role_id}.json', project_id, f'role:{role_id}')
    except FileNotFoundError:
        project = role = None
    return ContextBundle(1, project_id,
                         {**(project.preferences if project else {}),
                          **(role.preferences if role else {})},
                         [*(project.facts if project else []), *(role.facts if role else [])])
