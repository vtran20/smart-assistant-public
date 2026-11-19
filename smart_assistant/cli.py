"""JSON command boundary for local helpers; semantic coordination stays in Codex."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import stat

from .catalog import eligible_capabilities, load_catalog, validate_catalog
from .contracts import (
    ErrorDetail, GateResult, RevisionConflict, TaskStatus, ValidationError,
    from_dict, to_dict,
)
from .preflight import preflight
from .quality import completion_gate
from .state import TaskStore


class _ArgumentError(Exception):
    pass


class _Help(Exception):
    def __init__(self, text):
        self.text = text


class _Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    # argparse's standard messages echo untrusted arguments and exit the process.
    def error(self, message):
        raise _ArgumentError()

    def print_help(self, file=None):
        raise _Help(self.format_help())

    def exit(self, status=0, message=None):
        raise _ArgumentError()


def _parser():
    parser = _Parser(prog='smart_assistant', description='Validated local task and capability helpers')
    commands = parser.add_subparsers(dest='command', required=True)
    task = commands.add_parser('task').add_subparsers(dest='operation', required=True)
    create = task.add_parser('create')
    create.add_argument('--record', required=True)
    show = task.add_parser('show')
    show.add_argument('id')
    update = task.add_parser('update')
    update.add_argument('--record', required=True)
    update.add_argument('--expected-revision', required=True, type=int)
    complete = task.add_parser('complete')
    complete.add_argument('id')
    complete.add_argument('--expected-revision', required=True, type=int)
    for command in (create, show, update, complete):
        command.add_argument('--state-dir', required=True)
    delivery = commands.add_parser('delivery').add_subparsers(dest='operation', required=True)
    for name in ('create', 'show', 'update', 'check'):
        command = delivery.add_parser(name)
        command.add_argument('--state-dir', required=True)
        if name in ('create', 'update'):
            command.add_argument('--record', required=True)
            command.add_argument('--expected-task-revision', required=True, type=int)
            if name == 'update': command.add_argument('--expected-revision', required=True, type=int)
        else: command.add_argument('id')
    evidence = delivery.add_parser('evidence').add_subparsers(dest='evidence_operation', required=True)
    for name in ('show', 'save', 'recover'):
        command = evidence.add_parser(name)
        command.add_argument('id')
        command.add_argument('--state-dir', required=True)
        if name in ('save', 'recover'):
            for argument in ('expected-revision', 'expected-task-revision', 'expected-delivery-revision'):
                command.add_argument('--' + argument, required=True, type=int)
        if name == 'save': command.add_argument('--bundle', required=True)
        if name == 'recover':
            command.add_argument('--revision', required=True, type=int)
            command.add_argument('--revision-sha256', required=True)
            command.add_argument('--action', required=True, choices=('finish', 'reject'))
    team = commands.add_parser('team').add_subparsers(dest='operation', required=True)
    team_show = team.add_parser('show')
    team_show.add_argument('--profile', required=True)
    catalog = commands.add_parser('catalog').add_subparsers(dest='operation', required=True)
    validate = catalog.add_parser('validate')
    validate.add_argument('--project-root', required=True)
    eligible = catalog.add_parser('eligible')
    eligible.add_argument('--project-root', required=True)
    eligible.add_argument('--tools', required=True)
    brief = commands.add_parser('brief').add_subparsers(dest='operation', required=True)
    for operation in ('digest', 'build', 'verify'):
        command = brief.add_parser(operation)
        command.add_argument('--sources', required=True)
        if operation != 'digest':
            command.add_argument('--brief', required=True)
    check = commands.add_parser('preflight')
    check.add_argument('--request', required=True)
    return parser


def _reject(code):
    raise ValidationError([ErrorDetail(code, '$', 'Input rejected')])


def _json_file(path):
    """Do not block on pipes or accept duplicate/nonfinite JSON values."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _reject('duplicate_key')
            result[key] = value
        return result

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            _reject('unsafe_path')
        stream = os.fdopen(descriptor, 'r', encoding='utf-8')
        descriptor = None
        with stream:
            return json.load(stream, object_pairs_hook=unique,
                             parse_constant=lambda value: _reject('malformed_json'))
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _safe_errors(errors):
    """Exceptions can embed unknown keys, paths or private values: never echo them."""
    messages = {
        'revision_conflict': 'Saved revision changed or task already exists; read current state.',
        'invalid_arguments': 'Invalid or missing command arguments; use --help.',
        'history_changed': 'Existing cycle evidence must remain unchanged; append a fresh cycle.',
        'invalid_cycle_sequence': 'Cycles must be numbered consecutively starting at one.',
        'unresolved_blockers': 'Resolve task blockers before completion.',
        'preflight_unmet': 'Required tools, exact authorization or host approval are unavailable.',
        'filesystem_error': 'Required local input or state is unavailable or unsafe.',
        'malformed_json': 'Expected valid UTF-8 JSON without nonfinite values.',
        'duplicate_key': 'Duplicate JSON object keys are invalid.',
        'completion_denied': 'Current review, feedback and checks must satisfy the completion gate.',
        'internal_error': 'Command could not be processed.',
    }
    result = []
    for error in errors:
        code = error.code if re.fullmatch(r'[a-z][a-z0-9_]{0,63}', error.code) else 'invalid_input'
        result.append({'code': code, 'path': '$', 'message': messages.get(
            code, 'Input or evidence was rejected; check the declared contract and current evidence.')})
    return result


def _reply(code, data=None, errors=()):
    payload = {'ok': code == 0, 'data': data, 'errors': _safe_errors(errors)}
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(',', ':')))
    return code


def _error(code):
    return ErrorDetail(code, '$', '')


def _completion_check(task):
    result = completion_gate(task)
    if task.blockers:
        return GateResult(False, [*result.errors, _error('unresolved_blockers')])
    return result


def _cycle_sequence(task):
    if [cycle.cycle_number for cycle in task.cycles] != list(range(1, len(task.cycles) + 1)):
        _reject('invalid_cycle_sequence')


def _check_update(current, proposed, expected_revision):
    # Check the observed revision before history/quality; TaskStore repeats CAS under lock.
    if type(expected_revision) is not int or expected_revision < 1:
        _reject('invalid_revision')
    if current.revision != expected_revision:
        raise RevisionConflict()
    _cycle_sequence(proposed)
    previous = to_dict(current)['cycles']
    following = to_dict(proposed)['cycles']
    if following[:len(previous)] != previous:
        _reject('history_changed')


def _task(args):
    store = TaskStore(Path(args.state_dir), completion_check=_completion_check)
    if args.operation == 'create':
        record = from_dict('TaskRecord', _json_file(args.record))
        _cycle_sequence(record)
        return _reply(0, to_dict(store.create(record)))
    if args.operation == 'show':
        return _reply(0, to_dict(store.read(args.id)))
    if args.operation == 'update':
        proposed = from_dict('TaskRecord', _json_file(args.record))
        current = store.read(proposed.id)
    else:
        current = store.read(args.id)
        proposed = replace(current, status=TaskStatus.COMPLETED)
    _check_update(current, proposed, args.expected_revision)
    if proposed.status is TaskStatus.COMPLETED:
        # Preserve P01's transition/revision validation priority; store's callback gates
        # persistence. Capture gate detail after its completion_denied response below.
        try:
            saved = store.update(proposed, args.expected_revision)
        except ValidationError as error:
            if any(detail.code == 'completion_denied' for detail in error.errors):
                details = [detail for detail in error.errors if detail.code != 'completion_denied']
                gate = _completion_check(proposed) if not details else GateResult(False, details)
                return _reply(4, None, gate.errors or [_error('completion_denied')])
            raise
    elif current.status is TaskStatus.FAILED and proposed.status is TaskStatus.RUNNING:
        saved = store.resume_failed(proposed, args.expected_revision)
    else:
        saved = store.update(proposed, args.expected_revision)
    return _reply(0, to_dict(saved))


def _delivery(args):
    from .delivery_store import DeliveryStore
    from .delivery_records import _require
    from .delivery_codec import record_from_dict, record_to_dict as delivery_to_dict, mode_for_task
    from .delivery_evidence import evidence_from_dict
    from .delivery_gate import DeliveryEvidenceStore, revision_to_dict
    store = DeliveryStore(Path(args.state_dir))
    if args.operation == 'show': return _reply(0, delivery_to_dict(store.read(args.id)))
    if args.operation == 'check':
        result = DeliveryEvidenceStore(Path(args.state_dir)).check(args.id)
        return _reply(0 if result.passed else 4,
                      {'passed': result.passed, 'errors': _safe_errors(result.errors)}, result.errors)
    if args.operation in ('create', 'update'):
        wire = _json_file(args.record)
        _require(type(wire) is dict,'invalid_type','$','Expected delivery JSON object')
        task = TaskStore(Path(args.state_dir)).read(wire.get('task_id'))
        mode = mode_for_task(task)
        kind = 'BuiltinSnapshot' if mode == 'builtin' else 'DeliverySnapshot'
        record = record_from_dict(kind,wire,mode=mode)
        if args.operation == 'create': saved = store.register(record, args.expected_task_revision)
        else: saved = store.update(record, args.expected_revision, args.expected_task_revision)
        return _reply(0, delivery_to_dict(saved))
    evidence = DeliveryEvidenceStore(Path(args.state_dir))
    if args.evidence_operation == 'show': return _reply(0, revision_to_dict(evidence.read(args.id)))
    expected = dict(expected_revision=args.expected_revision,
                    expected_task_revision=args.expected_task_revision,
                    expected_delivery_revision=args.expected_delivery_revision)
    if args.evidence_operation == 'save':
        bundle = evidence_from_dict(_json_file(args.bundle))
        return _reply(0, revision_to_dict(evidence.save(args.id, bundle, **expected)))
    return _reply(0, evidence.recover(args.id, args.revision, args.revision_sha256, args.action, **expected))


def _catalog(args):
    root = Path(args.project_root)
    catalog = load_catalog(root)
    if args.operation == 'validate':
        result = validate_catalog(catalog, root)
        data = {'passed': result.passed, 'errors': _safe_errors(result.errors)}
        return _reply(0 if result.passed else 2, data, result.errors)
    tools = _json_file(args.tools)
    if type(tools) is not list or any(type(tool) is not str or not tool.strip() for tool in tools):
        _reject('invalid_tools')
    # Normalize Unicode/tool references with the existing preflight validator.
    preflight(set(), set(tools), [], [])
    return _reply(0, [to_dict(record) for record in eligible_capabilities(catalog, set(tools), root)])


def main(argv: list[str] | None = None) -> int:
    """Run one command without raising SystemExit or exposing raw error content."""
    try:
        args = _parser().parse_args(argv)
        if args.command == 'task':
            return _task(args)
        if args.command == 'delivery':
            return _delivery(args)
        if args.command == 'team':
            from .team_profile import load_team_profile, team_to_dict
            return _reply(0, team_to_dict(load_team_profile(Path(args.profile))))
        if args.command == 'catalog':
            return _catalog(args)
        if args.command == 'brief':
            from .work_brief import source_digest, verify_brief, render_brief
            sources = _json_file(args.sources)
            if args.operation == 'digest':
                return _reply(0, {'sources_sha256': source_digest(sources)})
            brief = _json_file(args.brief)
            checked = verify_brief(sources, brief)
            if not checked['passed']:
                return _reply(4, errors=[_error(code) for code in checked['errors']])
            return _reply(0, render_brief(sources, brief) if args.operation == 'build' else checked)
        request = from_dict('PreflightRequest', _json_file(args.request))
        result = preflight(set(request.required_tools), set(request.available_tools),
                           request.requested_actions, request.authorization)
        return _reply(0 if result.ready else 4, to_dict(result),
                      [] if result.ready else [_error('preflight_unmet')])
    except _Help as help_request:
        return _reply(0, {'help': help_request.text})
    except _ArgumentError:
        return _reply(2, errors=[_error('invalid_arguments')])
    except RevisionConflict:
        return _reply(3, errors=[_error('revision_conflict')])
    except ValidationError as error:
        return _reply(2, errors=error.errors)
    except (OSError, UnicodeError):
        return _reply(2, errors=[_error('filesystem_error')])
    except (ValueError, RecursionError):
        return _reply(2, errors=[_error('malformed_json')])
    except Exception:
        # The public command boundary intentionally hides implementation exceptions.
        return _reply(2, errors=[_error('internal_error')])
