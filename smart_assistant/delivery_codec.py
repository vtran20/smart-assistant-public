"""Closed mode-aware dispatch; request mode comes from the immutable task."""
import re
from . import contracts as c
from . import delivery_records as managed
from . import builtin_records as builtin
_COMMON={'DeliveryPolicy','DeliveryRegistration','DeliveryPlan','DependencyPin','ObservedRun','DecisionReceipt'}
_MANAGED=set(managed._TYPES)-_COMMON
_BUILTIN=set(builtin._TYPES)

def mode_for_task(task):
    managed._require(type(task) is c.TaskRecord,'invalid_type','$','Expected current TaskRecord')
    task=c.from_dict('TaskRecord',c.to_dict(task))
    refs=[v for v in task.request.source_refs if v.startswith(builtin.MODE_PREFIX)]
    if not refs:return 'managed'
    builtin.execution_marker(task.request)
    managed._require(task.request.requested_role is None,'configured_fallback','$.request','Configured capability cannot fall back')
    policies=[v for v in task.request.source_refs if v.startswith(managed.PREFIX)]
    managed._require(len(policies)==1 and re.fullmatch(re.escape(managed.PREFIX)+r'1\.0:[a-z][a-z0-9_-]{1,63}:[a-f0-9]{64}',policies[0]) is not None,'policy_mismatch','$.request.source_refs','Builtin requires one valid immutable policy marker')
    return 'builtin'

def record_from_dict(kind,wire,*,mode=None):
    managed._require(mode in (None,'managed','builtin'),'mode_mismatch','$','Unknown requested mode')
    managed._require(type(kind) is str and kind in _COMMON|_MANAGED|_BUILTIN,'invalid_type','$','Unknown closed record kind')
    if kind in ('DeliverySnapshot','BuiltinSnapshot'):
        managed._require(mode is not None,'mode_mismatch','$','Snapshot decoding requires request-derived mode')
    if kind in _COMMON:return managed.delivery_from_dict(kind,wire)
    if kind in _MANAGED:
        managed._require(mode in (None,'managed'),'mode_mismatch','$','Managed record in builtin mode')
        return managed.delivery_from_dict(kind,wire)
    managed._require(mode in (None,'builtin'),'mode_mismatch','$','Builtin record in managed mode')
    return builtin.builtin_from_dict(kind,wire)

def record_to_dict(record):
    if type(record) in managed._TYPES.values():return managed.delivery_to_dict(record)
    if type(record) in builtin._TYPES.values():return builtin.builtin_to_dict(record)
    managed._fail('invalid_type','$','Unknown exact delivery record type')

def record_digest(record):
    if type(record) in managed._TYPES.values():return managed.delivery_digest(record)
    if type(record) in builtin._TYPES.values():return builtin.builtin_digest(record)
    managed._fail('invalid_type','$','Unknown exact delivery record type')

def validate_snapshot(snapshot,task,previous=None):
    try:
        mode=mode_for_task(task)
        expected=builtin.BuiltinSnapshot if mode=='builtin' else managed.DeliverySnapshot
        managed._require(type(snapshot) is expected and (previous is None or type(previous) is expected),'mode_mismatch','$','Snapshot/history differ from request mode')
        if mode=='builtin':return builtin.validate_builtin(snapshot,task,previous)
        return managed.validate_delivery(snapshot,task,previous)
    except c.ValidationError as error:return c.GateResult(False,error.errors)

def validate_submission(envelope,submission,intent,artifact_root,*,dispatched_envelope=None):
    if type(envelope) is managed.AssignmentEnvelope:
        return managed.validate_submission(envelope,submission,intent,artifact_root,dispatched_envelope=dispatched_envelope)
    if type(envelope) is builtin.BuiltinAssignment:
        return builtin.validate_builtin_submission(envelope,submission,intent,artifact_root,dispatched_envelope=dispatched_envelope)
    return c.GateResult(False,[c.ErrorDetail('mode_mismatch','$','Unknown envelope mode')])
