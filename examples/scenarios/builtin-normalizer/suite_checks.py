"""Independent structural validation of the frozen local suite capture.

Hashes and self-reported JSON are not authenticity proof. Callers must bind actual
run observations and reviewed file hashes, then independently inspect semantics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re


ASSET_NAMES = ('normalize.py', 'cases.json', 'test_normalize.py',
               'run_suite.py', 'suite_checks.py')
APPROVED = (
    ('repeated-spaces', ('r01',), (('alpha  beta', 'alpha beta'),)),
    ('repeated-tabs', ('r01',), (('alpha\t\tbeta', 'alpha beta'),)),
    ('embedded-newline', ('r01',), (('alpha\nbeta', 'alpha beta'),)),
    ('mixed-whitespace', ('r01', 'r02'), ((' \talpha \n\t beta \n', 'alpha beta'),)),
    ('edge-whitespace', ('r02',), ((' \talpha beta \n', 'alpha beta'),)),
    ('already-normalized', ('r03',), (('alpha beta', 'alpha beta'),)),
    ('unicode-punctuation', ('r03',), (('Café ☕ — done!', 'Café ☕ — done!'),)),
    ('empty-blank', ('r04',), (('', ''), (' \t\n ', ''))),
)
TEST_IDS = {case: 'test_normalize.NormalizeSpacesTests.test_' + case.replace('-', '_')
            for case, _, _ in APPROVED}


def approved_manifest():
    return {'schema_version': '1.0', 'cases': [
        dict(case_id=case, required=True, requirement_ids=list(reqs), proof_level='unit',
             inputs=[dict(input=value, expected=expected) for value, expected in inputs])
        for case, reqs, inputs in APPROVED]}


def contract_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def _utc(value):
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError('UTC timestamp must end in Z')
    parsed = datetime.fromisoformat(value[:-1] + '+00:00')
    if parsed.tzinfo != timezone.utc:
        raise ValueError('UTC timestamp required')
    return parsed


def safe_capture_path(value):
    """Strict portable relative output name; no absolute/traversal/empty parts."""
    return (isinstance(value, str) and bool(value)
            and all(part not in ('.', '..') and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', part)
                    for part in value.split('/'))
            and value not in ASSET_NAMES and value != 'go.json')


def check_provenance(provenance, started_at, expected_run=None):
    """Return structural provenance errors; expected_run is the complete go object."""
    errors = []
    try:
        if set(provenance) != {'task_id', 'assignment_id', 'dispatch_token', 'capture_path', 'run'}:
            errors.append('provenance: exact go.json fields required')
        if not safe_capture_path(provenance['capture_path']):
            errors.append('provenance: capture_path must be a safe relative output path')
        for key in ('task_id', 'assignment_id', 'dispatch_token'):
            if not isinstance(provenance[key], str) or not provenance[key].strip():
                errors.append(f'provenance: nonempty {key} required')
        run = provenance['run']
        fields = {'schema_version', 'host_ref', 'actor_ref', 'run_ref', 'dispatch_token',
                  'observed_at', 'observation_ref'}
        if set(run) != fields or any(not isinstance(run[k], str) or not run[k].strip() for k in fields):
            errors.append('provenance: exact nonempty ObservedRun wire fields required')
        if run['schema_version'] != '1.0':
            errors.append('provenance: unsupported ObservedRun version')
        if run['dispatch_token'] != provenance['dispatch_token']:
            errors.append('provenance: dispatch token mismatch')
        if _utc(run['observed_at']) > _utc(started_at):
            errors.append('provenance: run was not observed before execution')
        if expected_run is not None and provenance != expected_run:
            errors.append('provenance: differs from independently expected run')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        errors.append(f'provenance: malformed metadata ({exc})')
    return errors


def summarize(cases, unittest_counts):
    """Derive case/input totals from observations, never supplied success labels."""
    inputs = [value for case in cases for value in case['inputs']]
    return dict(unittest_counts,
                cases_passed=sum(case['status'] == 'pass' for case in cases),
                cases_failed=sum(case['status'] == 'fail' for case in cases),
                cases_errored=sum(case['status'] == 'error' for case in cases),
                inputs_observed=len(inputs),
                inputs_passed=sum(row['status'] == 'pass' for row in inputs),
                inputs_failed=sum(row['status'] == 'fail' for row in inputs),
                inputs_errored=sum(row['status'] == 'error' for row in inputs))


def _inspect(capture, manifest, expected_run=None, expected_digests=None):
    errors = []
    need = lambda condition, message: errors.append(message) if not condition else None
    need(contract_digest(manifest) == contract_digest(approved_manifest()),
         'manifest: differs from frozen eight-case/nine-input contract')
    expected = {row['case_id']: row for row in approved_manifest()['cases']}
    need(capture['schema_version'] == '1.0', 'capture: unsupported schema')
    need(capture['manifest_contract_sha256'] == contract_digest(manifest), 'manifest: contract digest mismatch')
    for field in ('discovered_case_ids', 'executed_case_ids'):
        ids = capture[field]
        need(isinstance(ids, list) and len(ids) == 8 and len(set(ids)) == 8
             and set(ids) == set(expected), field + ': exact unique membership required')
    need(capture['discovered_test_ids'] == [TEST_IDS[c] for c in capture['discovered_case_ids']],
         'discovery: method/case IDs differ')
    need(capture['executed_test_ids'] == [TEST_IDS[c] for c in capture['executed_case_ids']],
         'execution: method/case IDs differ')
    rows = capture['cases']
    ids = [row['case_id'] for row in rows]
    need(len(ids) == 8 and len(set(ids)) == 8 and set(ids) == set(expected),
         'cases: exact unique required membership missing or duplicated')
    need(ids == capture['executed_case_ids'], 'cases: row order differs from actual execution')
    for row in rows:
        case = expected[row['case_id']]
        label = row['case_id']
        need(row['test_id'] == TEST_IDS[label], label + ': method ID differs')
        need(row['requirement_ids'] == case['requirement_ids'] and row['proof_level'] == 'unit'
             and row['required'] is True, label + ': requirement/required/proof mapping differs')
        values = row['inputs']
        need([value['index'] for value in values] == list(range(len(case['inputs']))),
             label + ': exact unique input indexes required')
        need(len(values) == len(case['inputs']), label + ': input count differs')
        for index, value in enumerate(values):
            reference = case['inputs'][index]
            need(type(value['index']) is int and value['input'] == reference['input']
                 and value['expected'] == reference['expected'], label + ': input/expected values differ')
            need(value['observed_present'] is True and isinstance(value['observed'], str)
                 and value['error'] == '', label + ': no actual string return or input execution error')
            actual = 'pass' if value['observed'] == reference['expected'] else 'fail'
            need(value['status'] == actual, label + ': input status disagrees with actual return')
        status = 'fail' if any(value['status'] == 'fail' for value in values) else 'pass'
        need(row['status'] == status, label + ': case status disagrees with input observations')
    counts = capture['counts']
    unittest_keys = ('tests_run', 'failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes')
    need(all(type(counts[key]) is int and counts[key] >= 0 for key in unittest_keys),
         'counts: unittest totals must be nonnegative integers')
    computed = summarize(rows, {key: counts[key] for key in unittest_keys})
    need(counts == computed and all(type(value) is int for value in counts.values()),
         'counts: observed case/input totals disagree')
    need(counts['tests_run'] == 8 and counts['inputs_observed'] == 9, 'counts: incomplete execution')
    need(all(counts[key] == 0 for key in unittest_keys[2:]), 'counts: errors/skips/expected failures/unexpected successes prohibited')
    need(counts['failures'] == counts['inputs_failed'], 'counts: assertion failures disagree with inputs')
    need(counts['inputs_errored'] == 0 and counts['cases_errored'] == 0, 'counts: input/case execution errors prohibited')
    raw = capture['raw_unittest_output']
    need(isinstance(raw, str) and bool(raw.strip()), 'raw: full unittest output required')
    ran = re.findall(r'^Ran (\d+) tests? in [0-9.]+s$', raw, re.MULTILINE)
    need(ran == [str(counts['tests_run'])], 'raw: actual unittest run count differs')
    raw_ids = re.findall(r'^test_\w+ \((test_normalize\.NormalizeSpacesTests\.test_\w+)\)', raw, re.MULTILINE)
    need(raw_ids == capture['executed_test_ids'], 'raw: verbose executed methods differ')
    summary = 'OK' if counts['failures'] == 0 else f"FAILED (failures={counts['failures']})"
    need(raw.rstrip().endswith(summary), 'raw: unittest final summary differs')
    # Each assertion mismatch is an actual unittest failure traceback.
    need(len(re.findall(r'^FAIL: ', raw, re.MULTILINE)) == counts['failures'],
         'raw: assertion failure traceback count differs')
    raw_failures = re.findall(r"^FAIL: test_\w+ \((test_normalize\.NormalizeSpacesTests\.test_\w+)\) "
                             r"\(case_id='([^']+)', input_index=(\d+)\)$", raw, re.MULTILINE)
    expected_failures = [(row['test_id'], row['case_id'], str(value['index']))
                         for row in rows for value in row['inputs'] if value['status'] == 'fail']
    need(raw_failures == expected_failures, 'raw: failing subtest IDs/indexes disagree with observed mismatches')
    need(capture['harness_errors'] == [], 'harness: recorded execution/collection errors')
    need(_utc(capture['started_at']) <= _utc(capture['finished_at']), 'time: execution timestamps out of order')
    environment = capture['environment']
    need(all(isinstance(environment[key], str) and environment[key].strip()
             for key in ('executable', 'python_version', 'platform', 'cwd')), 'environment: interpreter/platform/cwd required')
    need(environment['cwd'].startswith('/') and environment['executable'].startswith('/'),
         'environment: absolute cwd and interpreter required')
    command = capture['command']
    need(isinstance(command, list) and len(command) >= 4 and all(isinstance(v, str) for v in command)
         and 'run_suite.py' in command and '--run-info' in command,
         'command: actual runner invocation required')
    digests = capture['digests']
    need(set(digests) == set(ASSET_NAMES) and all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
         for value in digests.values()), 'digests: exact five valid asset digests required')
    if expected_digests is not None:
        need(digests == expected_digests, 'digests: differs from independently expected candidate')
    errors.extend(check_provenance(capture['provenance'], capture['started_at'], expected_run))
    exit_code = 1 if counts['inputs_failed'] else 0
    return errors, counts, exit_code


def validate_capture(capture, manifest, *, expected_run=None, expected_digests=None):
    """Return {valid, errors, complete, exit_code, counts}; malformed data fails closed.

    valid means complete eligible local execution, including genuine assertion
    mismatches (exit 1). It never means a baseline suite passed. expected_run is
    the complete independently held root go.json object, not only its run field.
    """
    counts = {}
    try:
        errors, counts, exit_code = _inspect(capture, manifest, expected_run, expected_digests)
        if capture['complete'] is not True:
            errors.append('complete: capture did not record complete execution')
        if type(capture['exit_code']) is not int or capture['exit_code'] != exit_code:
            errors.append('exit: capture disagrees with computed assertion outcome')
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        errors, exit_code = [f'capture: malformed or incomplete data ({type(exc).__name__}: {exc})'], 2
    return dict(valid=not errors, errors=errors, complete=not errors,
                exit_code=exit_code if not errors else 2, counts=counts)
