"""Observe tool availability and declared authorization without executing actions."""
from .contracts import (
    AuthorizationScope, ErrorDetail, HostDecision, PendingAction, PreflightResult,
    RequestedAction, ValidationError, canonical_json, from_dict, to_dict,
)


def _tools(value: set[str], path: str) -> None:
    if type(value) is not set or any(type(item) is not str or not item.strip() for item in value):
        raise ValidationError([ErrorDetail('invalid_type', path, 'Expected a set of nonempty tool references')])
    # P00 rejects invalid Unicode before it can reach result serialization.
    for item in value:
        canonical_json(item)


def _records(value: list, expected: type, path: str) -> list:
    if type(value) is not list:
        raise ValidationError([ErrorDetail('invalid_type', path, 'Expected a list of declared records')])
    normalized = []
    for index, record in enumerate(value):
        if type(record) is not expected:
            raise ValidationError([ErrorDetail('invalid_type', f'{path}[{index}]',
                                               f'Expected {expected.__name__}')])
        normalized.append(from_dict(expected.__name__, to_dict(record)))
    return normalized


def preflight(required_tools: set[str], available_tools: set[str],
              requested_actions: list[RequestedAction],
              authorization: list[AuthorizationScope]) -> PreflightResult:
    """Require exact scope, allowed host policy and observed required tools.

    Declared authorization sources must be supplied by the orchestrator; neither
    this function nor a role's tool list establishes consent or grants access.
    Validated records are decoded into fresh typed copies before policy checks.
    Invalid input raises ValidationError instead of implying readiness.
    """
    _tools(required_tools, '$.required_tools')
    _tools(available_tools, '$.available_tools')
    requested_actions = _records(requested_actions, RequestedAction, '$.requested_actions')
    authorization = _records(authorization, AuthorizationScope, '$.authorization')
    refs = [action.action_ref for action in requested_actions]
    if len(refs) != len(set(refs)):
        raise ValidationError([ErrorDetail('duplicate_id', '$.requested_actions',
                                           'Action references must be unique')])
    needed = required_tools | {action.required_tool for action in requested_actions
                               if action.required_tool is not None}
    missing = sorted(needed - available_tools)
    scopes = {(scope.action_kind, scope.resource_ref) for scope in authorization}
    pending = []
    for action in requested_actions:
        reasons = []
        if (action.kind, action.resource_ref) not in scopes:
            reasons.append('Missing exact declared authorization for action kind and destination')
        if action.host_decision != HostDecision.ALLOWED:
            reasons.append(f'Host decision is {action.host_decision.value}')
        if action.required_tool is not None and action.required_tool not in available_tools:
            reasons.append(f'Required action tool is unavailable: {action.required_tool}')
        if reasons:
            pending.append(PendingAction(action.action_ref, '; '.join(reasons)))
    return PreflightResult(not missing and not pending, missing, pending)
