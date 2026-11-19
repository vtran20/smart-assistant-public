"""Strict source-bound assessment checks, never independent semantic acceptance."""
import hashlib
from pathlib import Path, PurePosixPath
import re

FIELDS = {'schema_version', 'case_id', 'role_id', 'knowledge', 'disposition', 'summary',
          'observations', 'gates', 'next_checks', 'blockers', 'limits'}
STATUSES = {'supported', 'not_proven', 'contradicted', 'not_applicable', 'stale'}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def safe_relative(value):
    if not nonempty(value) or '\\' in value or ':' in value or '\x00' in value:
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and str(path) == value
            and all(part not in ('', '.', '..') for part in path.parts))


def regular(path):
    path = Path(path).absolute()
    return path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))


def knowledge_identity(pack):
    """Use all raw pack bytes, including newline/whitespace, not deployment SHA."""
    import json
    path = Path(pack)
    if not regular(path):
        raise ValueError('Missing or unsafe knowledge pack')
    raw = path.read_bytes()
    data = json.loads(raw)
    if data.get('id') != 'xstore-triage-procedures' or data.get('version') != '1.0.0':
        raise ValueError('Unexpected knowledge identity/version')
    return dict(id=data['id'], version=data['version'], sha256=hashlib.sha256(raw).hexdigest())


def validate_assessment(value, input_root, selected_paths, knowledge, *, case_id):
    """Check shape, identity and selected ranges; statements are NOT fact checked."""
    errors = []
    def fail(message):
        errors.append(message)
    def shape(obj, fields, label):
        if not isinstance(obj, dict) or set(obj) != set(fields):
            fail(label + ': exact fields required')
            return False
        return True
    def strings(items, label, *, required=False, unique=False):
        if not isinstance(items, list) or (required and not items) or any(not nonempty(x) for x in items):
            fail(label + ': nonempty strings required')
            return []
        if unique and len(set(items)) != len(items):
            fail(label + ': duplicate value')
        return items
    root = Path(input_root).absolute()
    inventory = {}
    if not isinstance(selected_paths, (list, tuple, dict)):
        fail('selected input inventory required')
        selected_paths = []
    for name in selected_paths:
        if not safe_relative(name) or not regular(root / name):
            fail('Unsafe or missing selected input: ' + str(name))
            continue
        try:
            inventory[name] = len((root / name).read_text(encoding='utf-8').splitlines())
        except (OSError, UnicodeError):
            fail('Unreadable selected text input: ' + name)
    if not regular(root / next(iter(inventory), '__missing__')) and inventory:
        fail('Unsafe input root')
    def refs(items, label, required=False):
        if not isinstance(items, list) or (required and not items):
            fail(label + ': source refs required')
            return
        for ref in items:
            if not shape(ref, ('path', 'start_line', 'end_line'), label):
                continue
            name, start, end = ref['path'], ref['start_line'], ref['end_line']
            if not safe_relative(name) or name not in inventory:
                fail(label + ': ref not in selected regular input inventory')
            elif type(start) is not int or type(end) is not int or not 1 <= start <= end <= inventory[name]:
                fail(label + ': invalid actual source line range')
    if not shape(value, FIELDS, 'assessment'):
        return dict(structural_pass=False, errors=errors, semantic_review_required=True, acceptance='UNASSESSED')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        fail('schema_version must be integer 1')
    if not nonempty(case_id) or value['case_id'] != case_id:
        fail('case_id differs from supplied case')
    if value['role_id'] != 'xstore-triage':
        fail('role_id must be xstore-triage; declaration is not native proof')
    if (not shape(value['knowledge'], ('id', 'version', 'sha256'), 'knowledge')
            or value['knowledge'] != knowledge
            or not isinstance(knowledge, dict)
            or knowledge.get('id') != 'xstore-triage-procedures'
            or knowledge.get('version') != '1.0.0'
            or not isinstance(knowledge.get('sha256'), str)
            or not re.fullmatch('[0-9a-f]{64}', knowledge['sha256'])):
        fail('Knowledge raw digest/id/version differs from selected pack')
    if value['disposition'] not in ('ready_for_review', 'blocked', 'out_of_scope'):
        fail('Invalid disposition')
    if not nonempty(value['summary']):
        fail('Nonempty summary required')
    observations = value['observations']
    ids = set()
    if not isinstance(observations, list):
        fail('observations must be an array')
        observations = []
    for observation in observations:
        if not shape(observation, ('id', 'statement', 'source_refs'), 'observation'):
            continue
        identity = observation['id']
        if not nonempty(identity):
            fail('Nonempty observation ID required')
        elif identity in ids:
            fail('Duplicate observation ID')
        else:
            ids.add(identity)
        if not nonempty(observation['statement']):
            fail('Nonempty observation statement required')
        refs(observation['source_refs'], 'observation', True)
    gates = value['gates']
    gate_ids = set()
    if not isinstance(gates, list):
        fail('gates must be an array')
        gates = []
    for gate in gates:
        if not shape(gate, ('id', 'status', 'reason', 'observation_ids'), 'gate'):
            continue
        if not nonempty(gate['id']):
            fail('Nonempty gate ID required')
        elif gate['id'] in gate_ids:
            fail('Duplicate gate ID')
        else:
            gate_ids.add(gate['id'])
        if not isinstance(gate['status'], str) or gate['status'] not in STATUSES:
            fail('Invalid gate status')
        if not nonempty(gate['reason']):
            fail('Explicit gate reason required, including absent/scoped evidence')
        links = strings(gate['observation_ids'], 'observation links', unique=True)
        if any(identity not in ids for identity in links):
            fail('Gate has unknown observation ID')
        if gate['status'] in ('supported', 'contradicted', 'stale') and not links:
            fail('Grounded observation IDs required for supported/contradicted/stale gate')
    checks = value['next_checks']
    if not isinstance(checks, list):
        fail('next_checks must be an array')
        checks = []
    for check in checks:
        if not shape(check, ('question', 'reason', 'source_refs', 'execution'), 'next check'):
            continue
        if not nonempty(check['question']) or not nonempty(check['reason']):
            fail('Concrete question and case-specific reason required')
        if check['execution'] != 'not_executed':
            fail('Read-only next check must remain not_executed')
        refs(check['source_refs'], 'next check')
    blockers = strings(value['blockers'], 'blockers')
    if value['disposition'] == 'blocked' and not blockers:
        fail('Blocked disposition requires meaningful essential-input blocker')
    strings(value['limits'], 'limits', required=True)
    return dict(structural_pass=not errors, errors=errors, semantic_review_required=True, acceptance='UNASSESSED')


def evaluate_case(value, controls):
    """Controller rubric checks catch known mistakes, never certify meaning.

    Run validate_assessment separately first. Substring controls are deliberately
    insufficient for semantic truth; an independent reviewer reads original ranges.
    """
    errors = []
    if not isinstance(value, dict) or not isinstance(controls, dict):
        errors.append('Assessment and controller controls must be objects')
    else:
        if value.get('disposition') != controls.get('disposition'):
            errors.append('Unexpected case disposition')
        gates = {g.get('id'): g.get('status') for g in value.get('gates', []) if isinstance(g, dict) and isinstance(g.get('id'), str)}
        for gate, status in controls.get('required_gates', {}).items():
            if gates.get(gate) != status:
                errors.append('Required gate differs: ' + gate)
        for gate in controls.get('forbidden_supported', []):
            if gates.get(gate) == 'supported':
                errors.append('Known unsupported supported gate: ' + gate)
        text = ' '.join(str(c.get('question', '')) + ' ' + str(c.get('reason', ''))
                        for c in value.get('next_checks', []) if isinstance(c, dict)).lower()
        for term in controls.get('required_next_terms', []):
            if term.lower() not in text:
                errors.append('Missing case-specific next-check cue: ' + term)
        if controls.get('require_observations') and not value.get('observations'):
            errors.append('Positive evidence must not become generic abstention')
        if controls.get('no_xstore_diagnostics') and (value.get('observations') or value.get('gates') or value.get('next_checks')):
            errors.append('Unrelated case must not invent Xstore findings/diagnostics')
        serialized = str(value)
        for term in controls.get('forbidden_output_terms', []):
            if term in serialized:
                errors.append('Sensitive/hostile data repeated in output')
    return dict(case_checks_pass=not errors, errors=errors, semantic_review_required=True, acceptance='UNASSESSED')
