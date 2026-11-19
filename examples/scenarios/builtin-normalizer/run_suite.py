"""Frozen stdlib runner; actual execution requires a root-created go.json."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tempfile
import traceback
import unittest

from suite_checks import ASSET_NAMES, TEST_IDS, contract_digest, safe_capture_path, summarize, validate_capture


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_test_ids = []

    def startTest(self, test):
        self.executed_test_ids.append(test.id())
        super().startTest(test)


def check_destination(output, root, run_info):
    """Reject unsafe names and preexisting input inode aliases before any write."""
    output.resolve().relative_to(Path.cwd().resolve())
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError('symlink output path')
    protected = [(root / name).resolve() for name in ASSET_NAMES]
    protected.append(Path(run_info).resolve())
    if output.resolve() in protected:
        raise ValueError('output aliases an input asset')
    if output.exists():
        info = output.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('output must be an ordinary file with exactly one hard link')
        if any(path.exists() and output.samefile(path) for path in protected):
            raise ValueError('output aliases a protected input file identity')


def save_capture(destination, capture, root, run_info):
    """Replace a safe output atomically; never truncate a preexisting inode."""
    temporary = None
    try:
        check_destination(destination, root, run_info)
        destination.parent.mkdir(parents=True, exist_ok=True)
        check_destination(destination, root, run_info)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                dir=destination.parent, prefix='.normalizer-capture-', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(capture, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        check_destination(destination, root, run_info)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def result_counts(result):
    return dict(tests_run=result.testsRun if result else 0,
                failures=len(result.failures) if result else 0,
                errors=len(result.errors) if result else 0,
                skipped=len(result.skipped) if result else 0,
                expected_failures=len(result.expectedFailures) if result else 0,
                unexpected_successes=len(result.unexpectedSuccesses) if result else 0)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture')
    parser.add_argument('--run-info', required=True)
    args = parser.parse_args(argv)
    started = utc_now()
    root = Path(__file__).resolve().parent
    stream = io.StringIO()
    errors = []
    provenance, manifest, digests = {}, {}, {}
    discovered, executed, observations = [], [], []
    result = None
    destination = None
    manifest_valid = False
    manifest_sha256 = None
    try:
        provenance = json.loads(Path(args.run_info).read_text(encoding='utf-8'))
        relative_output = args.capture if args.capture is not None else provenance.get('capture_path')
        if not safe_capture_path(relative_output):
            errors.append('capture_path must be a safe relative output path')
        else:
            output = Path.cwd() / relative_output
            # A lexical relative path must also stay in its workspace after resolution.
            try:
                check_destination(output, root, args.run_info)
                destination = output
            except (OSError, ValueError) as exc:
                errors.append(f'capture_path must stay in the workspace without symlinks ({exc})')
        if args.capture is not None and args.capture != provenance.get('capture_path'):
            errors.append('capture_path differs from explicit --capture output')
        manifest = json.loads((root / 'cases.json').read_text(encoding='utf-8'))
        digests = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ASSET_NAMES}
        # Fail before product execution when the startup metadata is malformed.
        from suite_checks import check_provenance, approved_manifest
        errors.extend(check_provenance(provenance, started))
        manifest_sha256 = contract_digest(manifest)
        manifest_valid = manifest_sha256 == contract_digest(approved_manifest())
        if not manifest_valid:
            errors.append('manifest differs from frozen contract')
        if not errors:
            loader = unittest.TestLoader()
            suite = loader.discover(str(root), pattern='test_normalize.py')
            discovered = [test.id() for test in flatten(suite)]
            errors.extend(loader.errors)
            result = unittest.TextTestRunner(stream=stream, verbosity=2,
                                             resultclass=RecordingResult).run(suite)
            executed = result.executed_test_ids
            module = sys.modules.get('test_normalize')
            observations = getattr(module, 'OBSERVATIONS', [])
    except Exception:
        errors.append(traceback.format_exc())
    if digests:
        try:
            after = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ASSET_NAMES}
            if after != digests:
                errors.append('frozen assets changed during execution')
        except OSError:
            errors.append('frozen assets became unavailable during execution')
    cases = []
    discovered_cases, executed_cases = [], []
    counts = summarize([], result_counts(result))
    try:
        lookup = {test: case for case, test in TEST_IDS.items()}
        discovered_cases = [lookup.get(test, 'UNKNOWN:' + test) for test in discovered]
        executed_cases = [lookup.get(test, 'UNKNOWN:' + test) for test in executed]
        # A rejected manifest is diagnostic data; never inspect its presumed shape.
        manifest_rows = {row['case_id']: row for row in manifest['cases']} if manifest_valid else {}
        for case_id, test_id in zip(executed_cases, executed):
            values = [row['input'] for row in observations if row['case_id'] == case_id]
            status = ('error' if not values or any(row['status'] == 'error' for row in values)
                      else 'fail' if any(row['status'] == 'fail' for row in values) else 'pass')
            reference = manifest_rows.get(case_id, {})
            cases.append(dict(case_id=case_id, test_id=test_id, required=reference.get('required'),
                              proof_level=reference.get('proof_level'),
                              requirement_ids=reference.get('requirement_ids'), inputs=values, status=status))
        counts = summarize(cases, result_counts(result))
    except Exception:
        errors.append('capture construction failed: ' + traceback.format_exc())
        cases = []
    capture = dict(schema_version='1.0', started_at=started, finished_at=utc_now(),
                   command=list(sys.orig_argv),
                   environment=dict(executable=sys.executable, python_version=platform.python_version(),
                                    platform=platform.platform(), cwd=str(Path.cwd())),
                   provenance=provenance, digests=digests,
                   manifest_contract_sha256=manifest_sha256,
                   discovered_test_ids=discovered, executed_test_ids=executed,
                   discovered_case_ids=discovered_cases, executed_case_ids=executed_cases,
                   cases=cases, counts=counts, raw_unittest_output=stream.getvalue(),
                   harness_errors=errors, complete=True,
                   exit_code=1 if counts['inputs_failed'] else 0)
    try:
        checked = validate_capture(capture, manifest)
        capture['complete'] = checked['complete']
        capture['exit_code'] = checked['exit_code']
        if checked['errors']:
            capture['harness_errors'] += checked['errors']
    except Exception:
        capture.update(complete=False, exit_code=2)
        capture['harness_errors'].append('capture validation failed: ' + traceback.format_exc())
    if destination is not None:
        try:
            save_capture(destination, capture, root, args.run_info)
        except Exception:
            capture.update(complete=False, exit_code=2)
            capture['harness_errors'].append('capture output failed: ' + traceback.format_exc())
    sys.stdout.write(capture['raw_unittest_output'])
    if capture['harness_errors']:
        sys.stderr.write('\n'.join(capture['harness_errors']) + '\n')
    return capture['exit_code']


if __name__ == '__main__':
    sys.exit(main())
