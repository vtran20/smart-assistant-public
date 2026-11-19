import json
import fcntl
import queue
import multiprocessing
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from smart_assistant.contracts import CapabilityCatalog, CapabilityKind, CapabilityState, ProbePurpose, RevisionConflict, ValidationError, to_dict
from smart_assistant.catalog import load_catalog, eligible_capabilities
from smart_assistant.lifecycle import DeploymentStore
from tests.test_catalog import candidate, receipt, write_json


def prepare_worker(root, record, barrier, results):
    barrier.wait()
    try:
        results.put(('ok', DeploymentStore(Path(root)).prepare(record, 1)))
    except Exception as error:
        results.put(('error', type(error).__name__))


def eligibility_worker(root, catalog, start, entered, results):
    start.wait()
    entered.set()
    results.put([r.id for r in eligible_capabilities(catalog, {'tool.write'}, Path(root))])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        write_json(self.root / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [])))
        self.store = DeploymentStore(self.root)
        self.record = candidate(self.root)
    def tearDown(self): self.temp.cleanup()
    def activate(self, record=None, revision=1):
        record = record or self.record
        operation = self.store.prepare(record, revision)
        return self.store.finalize(operation, receipt(record, operation))
    def test_prepare_excludes_and_finalize_activates_complete_tree(self):
        operation = self.store.prepare(self.record, 1)
        self.assertEqual(load_catalog(self.root).revision, 1)
        self.assertEqual(eligible_capabilities(load_catalog(self.root), {'tool.write'}, self.root), [])
        catalog = self.store.finalize(operation, receipt(self.record, operation))
        self.assertEqual(catalog.revision, 2)
        self.assertEqual([r.id for r in eligible_capabilities(catalog, {'tool.write'}, self.root)], ['worker'])
        self.assertEqual(eligible_capabilities(catalog, set(), self.root), [])
        (self.root / self.record.deployed_path / 'references/help.txt').write_bytes(b'drift')
        self.assertEqual(eligible_capabilities(catalog, {'tool.write'}, self.root), [])
    def test_agent_staged_basename_is_normalized(self):
        record = candidate(self.root, CapabilityKind.AGENT)
        self.assertEqual(self.activate(record).records[0].deployed_sha256, record.deployed_sha256)
    def test_compare_and_swap_and_synchronized_concurrency(self):
        with self.assertRaises(RevisionConflict): self.store.prepare(self.record, 9)
        context = multiprocessing.get_context('fork')
        barrier, results = context.Barrier(2), context.Queue()
        processes = [context.Process(target=prepare_worker, args=(str(self.root), self.record, barrier, results)) for _ in range(2)]
        for process in processes: process.start()
        for process in processes: process.join(10); self.assertEqual(process.exitcode, 0)
        observed = [results.get(timeout=2)[0] for _ in processes]
        self.assertEqual(sorted(observed), ['error', 'ok'])
    def test_failed_activation_restores_original_version(self):
        self.activate()
        old = (self.root / self.record.deployed_path / 'SKILL.md').read_bytes()
        new = candidate(self.root, version='2.0.0', data=b'version-two')
        operation = self.store.prepare(new, 2)
        with self.assertRaises(ValidationError): self.store.finalize(operation, receipt(new, operation, invoked=False))
        self.assertEqual(load_catalog(self.root).revision, 2)
        self.assertEqual((self.root / self.record.deployed_path / 'SKILL.md').read_bytes(), old)
        self.assertEqual([r.version for r in eligible_capabilities(load_catalog(self.root), {'tool.write'}, self.root)], ['1.0.0'])
    def test_mismatched_and_stale_probe_restores(self):
        for change in ({'operation_id':'wrong-operation'}, {'manifest_sha256':'0'*64}, {'observed_at':'2000-01-01T00:00:00Z'}, {'evidence_refs':[]}):
            operation = self.store.prepare(self.record, 1)
            with self.assertRaises(ValidationError): self.store.finalize(operation, receipt(self.record, operation, **change))
            self.assertFalse((self.root / self.record.deployed_path).exists())
    def test_disable_requires_absence_and_fresh_session(self):
        catalog = self.activate()
        prior = json.loads((self.root / catalog.records[0].discovery_probe_ref).read_text())
        operation = self.store.prepare_disable('worker', 2)
        self.assertFalse((self.root / self.record.deployed_path).exists())
        with self.assertRaises(ValidationError): self.store.finalize_disable(operation, receipt(self.record, operation, ProbePurpose.DISABLE, discovered=True))
        self.assertEqual(eligible_capabilities(load_catalog(self.root), {'tool.write'}, self.root), [])
        with self.assertRaises(ValidationError): self.store.finalize_disable(operation, receipt(self.record, operation, ProbePurpose.DISABLE, session_ref=prior['session_ref']))
        self.store.restore(operation)
        operation = self.store.prepare_disable('worker', 2)
        catalog = self.store.finalize_disable(operation, receipt(self.record, operation, ProbePurpose.DISABLE))
        self.assertEqual((catalog.revision, catalog.records[0].state), (3, CapabilityState.DISABLED))
        with self.assertRaises(ValidationError): self.store.restore(operation)
    def test_native_drift_and_unsafe_sources(self):
        for change in ({'source_path':'.agents/skills/worker'}, {'deployed_path':'.codex/agents/unsafe/worker.toml'}):
            with self.assertRaises(ValidationError): self.store.prepare(replace(self.record, **change), 1)
        operation = self.store.prepare(self.record, 1)
        (self.root / self.record.deployed_path / 'extra').write_bytes(b'drift')
        with self.assertRaises(ValidationError): self.store.finalize(operation, receipt(self.record, operation))
        self.assertFalse((self.root / self.record.deployed_path).exists())
    def test_external_catalog_edit_never_overwritten(self):
        operation = self.store.prepare(self.record, 1)
        write_json(self.root / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 7, [])))
        with self.assertRaises(RevisionConflict): self.store.restore(operation)
        self.assertEqual(load_catalog(self.root).revision, 7)
        self.assertTrue((self.root / self.record.deployed_path).exists())
    def test_corrupt_journal_and_backup_fail_closed(self):
        self.activate()
        new = candidate(self.root, version='2.0.0')
        operation = self.store.prepare(new, 2)
        directory = self.root / '.smart-assistant/deployments' / operation
        (directory / 'backup/SKILL.md').write_bytes(b'corruption')
        with self.assertRaises(ValidationError): self.store.restore(operation)
        self.assertEqual((self.root / new.deployed_path / 'SKILL.md').read_bytes(), b'new')
        (directory / 'journal.json').write_text('{}')
        self.assertEqual(eligible_capabilities(load_catalog(self.root), {'tool.write'}, self.root), [])
        with self.assertRaises(ValidationError): self.store.prepare(new, 2)
    def test_interrupted_target_replace_recovers(self):
        self.activate()
        new = candidate(self.root, version='2.0.0', data=b'next')
        real_replace = os.replace
        def interrupt(source, destination):
            if Path(destination) == self.root / new.deployed_path: raise KeyboardInterrupt('replacement interruption')
            return real_replace(source, destination)
        with patch('os.replace', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.store.prepare(new, 2)
        operation = next(p.name for p in (self.root / '.smart-assistant/deployments').iterdir() if json.loads((p/'journal.json').read_text())['state'] == 'replacing')
        self.assertFalse((self.root / new.deployed_path).exists())
        with self.assertRaises(ValidationError): self.store.prepare(new, 2)
        self.store.restore(operation)
        self.assertEqual((self.root / new.deployed_path / 'SKILL.md').read_bytes(), b'new')
    def test_interrupted_catalog_commit_reconciles_without_rollback(self):
        operation = self.store.prepare(self.record, 1)
        real_replace = os.replace
        def interrupt(source, destination):
            result = real_replace(source, destination)
            if Path(destination) == self.root / 'capabilities/catalog.json': raise KeyboardInterrupt('after commit')
            return result
        with patch('os.replace', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.store.finalize(operation, receipt(self.record, operation))
        self.assertEqual(load_catalog(self.root).revision, 2)
        with self.assertRaises(ValidationError): self.store.restore(operation)
        self.assertEqual([r.id for r in eligible_capabilities(load_catalog(self.root), {'tool.write'}, self.root)], ['worker'])
    def test_interrupted_backup_and_restore_are_recoverable(self):
        self.activate()
        new = candidate(self.root, version='2.0.0', data=b'next')
        import shutil
        real_copy = shutil.copy2
        def interrupt(source, destination, **kwargs):
            result = real_copy(source, destination, **kwargs)
            if 'backup' in Path(destination).parts: raise KeyboardInterrupt('partial backup')
            return result
        with patch('shutil.copy2', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.store.prepare(new, 2)
        operation = next(p.name for p in (self.root / '.smart-assistant/deployments').iterdir() if json.loads((p/'journal.json').read_text())['state'] == 'preparing')
        self.store.restore(operation)
        self.assertEqual((self.root / new.deployed_path / 'SKILL.md').read_bytes(), b'new')
        operation = self.store.prepare(new, 2)
        real_replace = os.replace
        def stop_restore(source, destination):
            if Path(destination) == self.root / new.deployed_path: raise KeyboardInterrupt('restore interruption')
            return real_replace(source, destination)
        with patch('os.replace', side_effect=stop_restore):
            with self.assertRaises(KeyboardInterrupt): self.store.restore(operation)
        self.store.restore(operation)
        self.assertEqual((self.root / new.deployed_path / 'SKILL.md').read_bytes(), b'new')

    def test_stale_catalog_snapshot_cannot_route_superseded_metadata(self):
        old_catalog = self.activate()
        new = candidate(self.root, version='2.0.0', data=b'new')
        self.activate(new, 2)
        self.assertEqual(eligible_capabilities(old_catalog, {'tool.write'}, self.root), [])

    def test_altered_committed_probe_operation_is_not_eligible(self):
        catalog = self.activate()
        path = self.root / catalog.records[0].discovery_probe_ref
        proof = json.loads(path.read_text())
        proof['operation_id'] = 'different-operation'
        write_json(path, proof)
        self.assertEqual(eligible_capabilities(catalog, {'tool.write'}, self.root), [])

    def test_malformed_journal_types_fail_closed(self):
        catalog = self.activate()
        path = self.root / catalog.records[0].rollback_ref
        original = json.loads(path.read_text())
        for field, value in [('state', []), ('mode', {}), ('old_catalog', '\ud800'), ('target', '../escape')]:
            with self.subTest(field=field):
                malformed = dict(original, **{field: value})
                write_json(path, malformed)
                self.assertEqual(eligible_capabilities(catalog, {'tool.write'}, self.root), [])
                with self.assertRaises(ValidationError): self.store.prepare(candidate(self.root, version='2.0.0'), 2)
        write_json(path, original)

    def test_symlink_journal_is_rejected_without_following(self):
        operation = self.store.prepare(self.record, 1)
        path = self.root / '.smart-assistant/deployments' / operation / 'journal.json'
        outside = self.root / 'copied-journal.json'
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        self.assertEqual(eligible_capabilities(load_catalog(self.root), {'tool.write'}, self.root), [])
        with self.assertRaises(ValidationError): self.store.restore(operation)

    def test_interrupted_before_catalog_commit_restores_old_revision(self):
        self.activate()
        new = candidate(self.root, version='2.0.0', data=b'next')
        operation = self.store.prepare(new, 2)
        real_replace = os.replace
        def interrupt(source, destination):
            if Path(destination) == self.root / 'capabilities/catalog.json': raise KeyboardInterrupt('before commit')
            return real_replace(source, destination)
        with patch('os.replace', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt): self.store.finalize(operation, receipt(new, operation))
        self.assertEqual(load_catalog(self.root).revision, 2)
        self.store.restore(operation)
        self.assertEqual((self.root / new.deployed_path / 'SKILL.md').read_bytes(), b'new')

    def test_evidence_must_be_safe_existing_and_manifest_bound(self):
        ref = self.root / self.record.validation_refs[1]
        original = json.loads(ref.read_text())
        for changes in ({'passed': False}, {'manifest_sha256': '0'*64}, {'evidence_refs': ['../escape']}, {'evidence_refs': ['missing-file']}):
            write_json(ref, dict(original, **changes))
            with self.assertRaises(ValidationError): self.store.prepare(self.record, 1)
        write_json(ref, original)
        (self.root / self.record.source_path / 'link').symlink_to(self.root / 'evidence')
        with self.assertRaises(ValidationError): self.store.prepare(self.record, 1)

    def test_restore_rejects_symlink_scratch_without_external_write(self):
        self.activate()
        new = candidate(self.root, version='2.0.0', data=b'next')
        operation = self.store.prepare(new, 2)
        directory = self.root / '.smart-assistant/deployments' / operation
        outside = self.root / 'outside-assets'
        outside.mkdir()
        (outside / 'keep').write_text('keep')
        (directory / 'restoring-assets').symlink_to(outside)
        with self.assertRaises(ValidationError): self.store.restore(operation)
        self.assertEqual((outside / 'keep').read_text(), 'keep')
        self.assertEqual((self.root / new.deployed_path / 'SKILL.md').read_bytes(), b'next')

    def test_agent_restore_rejects_dangling_scratch_symlink_before_writing(self):
        old = candidate(self.root, CapabilityKind.AGENT)
        self.activate(old)
        new = candidate(self.root, CapabilityKind.AGENT, version='2.0.0', data=b'next')
        operation = self.store.prepare(new, 2)
        directory = self.root / '.smart-assistant/deployments' / operation
        outside = self.root / 'outside-file'
        (directory / 'restoring-assets').symlink_to(outside)
        with self.assertRaises(ValidationError): self.store.restore(operation)
        self.assertFalse(outside.exists())
        self.assertEqual((self.root / new.deployed_path).read_bytes(), b'next')

    def test_eligibility_waits_for_catalog_writer_lock(self):
        catalog = self.activate()
        context = multiprocessing.get_context('fork')
        start, entered, results = context.Event(), context.Event(), context.Queue()
        process = context.Process(target=eligibility_worker, args=(str(self.root), catalog, start, entered, results))
        process.start()
        descriptor = os.open(self.root / '.smart-assistant/catalog.lock', os.O_RDWR)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            asset = self.root / self.record.deployed_path / 'SKILL.md'
            asset.write_bytes(b'incomplete writer')
            start.set()
            self.assertTrue(entered.wait(5))
            with self.assertRaises(queue.Empty): results.get(timeout=0.1)
            asset.write_bytes(b'new')
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        process.join(5)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(results.get(timeout=2), ['worker'])

    def test_r1_equal_bytes_at_unprobed_native_target_are_rejected(self):
        import shutil
        from smart_assistant.catalog import validate_catalog
        catalog = self.activate()
        different = '.agents/skills/never-probed'
        shutil.copytree(self.root / self.record.deployed_path, self.root / different)
        edited = replace(catalog, records=[replace(catalog.records[0], deployed_path=different)])
        write_json(self.root / 'capabilities/catalog.json', to_dict(edited))
        self.assertFalse(validate_catalog(edited, self.root).passed)
        self.assertEqual(eligible_capabilities(edited, {'tool.write'}, self.root), [])

    def test_r2_impossible_old_existence_preserves_surviving_files(self):
        self.activate()
        new = candidate(self.root, version='2.0.0', data=b'v2')
        operation = self.store.prepare(new, 2)
        directory = self.root / '.smart-assistant/deployments' / operation
        journal_path = directory / 'journal.json'
        original = json.loads(journal_path.read_text())
        write_json(journal_path, dict(original, old_existed=False, old_manifest=None))
        with self.assertRaises(ValidationError): self.store.restore(operation)
        self.assertEqual((self.root / new.deployed_path / 'SKILL.md').read_bytes(), b'v2')
        self.assertEqual((directory / 'backup/SKILL.md').read_bytes(), b'new')
        self.assertEqual(load_catalog(self.root).revision, 2)

    def test_r3_agent_backup_directory_digest_collision_preserves_native_target(self):
        from smart_assistant.catalog import deployment_manifest
        old = candidate(self.root, CapabilityKind.AGENT)
        self.activate(old)
        new = candidate(self.root, CapabilityKind.AGENT, version='2.0.0', data=b'v2')
        operation = self.store.prepare(new, 2)
        directory = self.root / '.smart-assistant/deployments' / operation
        backup = directory / 'backup'
        old_bytes = backup.read_bytes()
        backup.unlink()
        backup.mkdir()
        (backup / 'worker.toml').write_bytes(old_bytes)
        self.assertEqual(deployment_manifest(backup).manifest_sha256, old.deployed_sha256)
        with self.assertRaises(ValidationError): self.store.restore(operation)
        self.assertEqual((self.root / new.deployed_path).read_bytes(), b'v2')
        self.assertEqual((backup / 'worker.toml').read_bytes(), old_bytes)
        self.assertEqual(load_catalog(self.root).revision, 2)

    def test_r5_runtime_ancestor_staging_rejected_before_copy(self):
        from smart_assistant.catalog import deployment_manifest, validate_catalog
        runtime = self.root / '.smart-assistant'
        runtime.mkdir(exist_ok=True)
        (runtime / 'catalog.lock').write_bytes(b'')
        digest = deployment_manifest(runtime).manifest_sha256
        record = replace(self.record, source_path='.smart-assistant', deployed_sha256=digest)
        for ref in record.validation_refs:
            value = json.loads((self.root / ref).read_text())
            write_json(self.root / ref, dict(value, manifest_sha256=digest))
        self.assertFalse(validate_catalog(CapabilityCatalog(1, 1, [record]), self.root).passed)
        with patch('shutil.copytree', side_effect=AssertionError('unsafe copy reached')):
            with self.assertRaises(ValidationError): self.store.prepare(record, 1)
        self.assertFalse((self.root / self.record.deployed_path).exists())
        self.assertFalse((runtime / 'deployments').exists())

    def test_r3_wrong_type_restoration_scratch_preserves_native_target(self):
        import shutil
        old = candidate(self.root, CapabilityKind.AGENT)
        self.activate(old)
        new = candidate(self.root, CapabilityKind.AGENT, version='2.0.0', data=b'v2')
        operation = self.store.prepare(new, 2)
        real_copy = shutil.copy2
        def change_scratch_type(source, destination, **kwargs):
            if Path(destination).name == 'restoring-assets':
                Path(destination).mkdir()
                return real_copy(source, Path(destination) / 'worker.toml', **kwargs)
            return real_copy(source, destination, **kwargs)
        with patch('shutil.copy2', side_effect=change_scratch_type):
            with self.assertRaises(ValidationError): self.store.restore(operation)
        self.assertEqual((self.root / new.deployed_path).read_bytes(), b'v2')
        directory = self.root / '.smart-assistant/deployments' / operation
        self.assertEqual((directory / 'backup').read_bytes(), b'new')

    def test_r4_active_nested_wire_catalog_returns_typed_records(self):
        from smart_assistant.catalog import validate_catalog
        catalog = self.activate()
        nested = CapabilityCatalog(catalog.schema_version, catalog.revision, [to_dict(r) for r in catalog.records])
        self.assertTrue(validate_catalog(nested, self.root).passed)
        selected = eligible_capabilities(nested, {'tool.write'}, self.root)
        self.assertEqual([r.id for r in selected], ['worker'])
        self.assertEqual(selected[0].kind, CapabilityKind.SKILL)

    def test_malformed_activation_receipt_restores_before_rejecting(self):
        operation = self.store.prepare(self.record, 1)
        malformed = receipt(self.record, operation, evidence_refs=[{}])
        with self.assertRaises(ValidationError): self.store.finalize(operation, malformed)
        self.assertFalse((self.root / self.record.deployed_path).exists())
        self.assertEqual(load_catalog(self.root).revision, 1)

    def test_w1_f1_initial_crlf_catalog_bytes_are_preserved_in_journal(self):
        import hashlib
        path = self.root / 'capabilities/catalog.json'
        original = (json.dumps(to_dict(CapabilityCatalog(1, 1, [])), indent=2) + '\n').encode().replace(b'\n', b'\r\n')
        path.write_bytes(original)
        operation = self.store.prepare(self.record, 1)
        journal_path = self.root / '.smart-assistant/deployments' / operation / 'journal.json'
        journal = json.loads(journal_path.read_bytes())
        self.assertEqual(journal['old_catalog'].encode('utf-8'), original)
        self.assertEqual(journal['old_catalog_sha256'], hashlib.sha256(original).hexdigest())
        self.store.restore(operation)
        self.assertEqual(path.read_bytes(), original)
        operation = self.store.prepare(self.record, 1)
        self.assertEqual(self.store.finalize(operation, receipt(self.record, operation)).revision, 2)

    def _assert_line_ending_edit_rejected(self, mode, action, old_ending, new_ending):
        with TemporaryDirectory() as name:
            root = Path(name).resolve()
            path = root / 'capabilities/catalog.json'
            write_json(path, to_dict(CapabilityCatalog(1, 1, [])))
            store = DeploymentStore(root)
            record = candidate(root)
            if mode == 'disable':
                operation = store.prepare(record, 1)
                catalog = store.finalize(operation, receipt(record, operation))
            else:
                catalog = load_catalog(root)
            lf = (json.dumps(to_dict(catalog), indent=2) + '\n').encode()
            original = lf.replace(b'\n', old_ending)
            path.write_bytes(original)
            operation = store.prepare_disable('worker', 2) if mode == 'disable' else store.prepare(record, 1)
            changed = original.replace(old_ending, new_ending)
            path.write_bytes(changed)
            with self.assertRaises(RevisionConflict):
                if action == 'restore': store.restore(operation)
                elif mode == 'disable': store.finalize_disable(operation, receipt(record, operation, ProbePurpose.DISABLE))
                else: store.finalize(operation, receipt(record, operation))
            self.assertEqual(path.read_bytes(), changed)
            directory = root / '.smart-assistant/deployments' / operation
            self.assertEqual(json.loads((directory / 'journal.json').read_bytes())['state'], 'prepared')
            if mode == 'disable':
                self.assertFalse((root / record.deployed_path).exists())
                self.assertEqual((directory / 'backup/SKILL.md').read_bytes(), b'new')
            else:
                self.assertEqual((root / record.deployed_path / 'SKILL.md').read_bytes(), b'new')

    def test_w1_f1_external_line_ending_edits_reject_activation_finalize_and_restore(self):
        for old_ending, new_ending in ((b'\n', b'\r\n'), (b'\r\n', b'\n')):
            for action in ('finalize', 'restore'):
                with self.subTest(original=old_ending, action=action):
                    self._assert_line_ending_edit_rejected('activate', action, old_ending, new_ending)

    def test_w1_f1_external_line_ending_edits_reject_disable_finalize_and_restore(self):
        for old_ending, new_ending in ((b'\n', b'\r\n'), (b'\r\n', b'\n')):
            for action in ('finalize', 'restore'):
                with self.subTest(original=old_ending, action=action):
                    self._assert_line_ending_edit_rejected('disable', action, old_ending, new_ending)

    def test_w1_f1_committed_retry_and_reconciliation_reject_changed_catalog_bytes(self):
        operation = self.store.prepare(self.record, 1)
        proof = receipt(self.record, operation)
        self.store.finalize(operation, proof)
        path = self.root / 'capabilities/catalog.json'
        committed = path.read_bytes()
        path.write_bytes(committed + b'\r\n')
        with self.assertRaises(RevisionConflict): self.store.finalize(operation, proof)
        self.assertEqual(path.read_bytes(), committed + b'\r\n')
        path.write_bytes(committed)
        new = candidate(self.root, version='2.0.0', data=b'v2')
        operation = self.store.prepare(new, 2)
        proof = receipt(new, operation)
        real_replace = os.replace
        def after_commit(source, destination):
            result = real_replace(source, destination)
            if Path(destination) == path: raise KeyboardInterrupt('after exact commit')
            return result
        with patch('os.replace', side_effect=after_commit):
            with self.assertRaises(KeyboardInterrupt): self.store.finalize(operation, proof)
        committed = path.read_bytes()
        changed = committed + b'\r\n'
        path.write_bytes(changed)
        with self.assertRaises(RevisionConflict): self.store.finalize(operation, proof)
        with self.assertRaises(RevisionConflict): self.store.restore(operation)
        self.assertEqual(path.read_bytes(), changed)
        journal_path = self.root / '.smart-assistant/deployments' / operation / 'journal.json'
        self.assertEqual(json.loads(journal_path.read_bytes())['state'], 'finalizing')
        self.assertEqual((self.root / new.deployed_path / 'SKILL.md').read_bytes(), b'v2')
        path.write_bytes(committed)
        self.assertEqual(self.store.finalize(operation, proof).revision, 3)

    def test_w1_f1_unicode_spelling_changes_are_bound_to_original_bytes(self):
        import hashlib
        original = json.dumps(to_dict(CapabilityCatalog(1, 1, [replace(self.record, name='Café')])), ensure_ascii=False, indent=2).encode('utf-8')
        path = self.root / 'capabilities/catalog.json'
        for replacement in ('e\u0301'.encode('utf-8'), b'\\u00e9'):
            with self.subTest(replacement=replacement):
                path.write_bytes(original)
                operation = self.store.prepare(self.record, 1)
                directory = self.root / '.smart-assistant/deployments' / operation
                journal = json.loads((directory / 'journal.json').read_bytes())
                self.assertEqual(journal['old_catalog'].encode('utf-8'), original)
                self.assertEqual(journal['old_catalog_sha256'], hashlib.sha256(original).hexdigest())
                changed = original.replace('é'.encode('utf-8'), replacement)
                path.write_bytes(changed)
                with self.assertRaises(RevisionConflict): self.store.restore(operation)
                self.assertEqual(path.read_bytes(), changed)
                self.assertTrue((self.root / self.record.deployed_path).exists())
                path.write_bytes(original)
                self.store.restore(operation)
