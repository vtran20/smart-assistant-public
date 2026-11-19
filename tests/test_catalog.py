import hashlib
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from smart_assistant.contracts import (CapabilityCatalog, CapabilityRecord, CapabilityKind,
    CapabilityState, NativeProbeReceipt, ProbePurpose, canonical_json, to_dict, ValidationError)
from smart_assistant.catalog import load_catalog, deployment_manifest, eligible_capabilities, validate_catalog


def manifest_digest(files):
    return hashlib.sha256(canonical_json([{'relative_path': p, 'sha256': hashlib.sha256(v).hexdigest()} for p, v in sorted(files.items())])).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def candidate(root, kind=CapabilityKind.SKILL, version='1.0.0', data=b'new'):
    source = 'staging/worker' if kind == CapabilityKind.SKILL else 'staging/different.toml'
    target = '.agents/skills/worker' if kind == CapabilityKind.SKILL else '.codex/agents/worker.toml'
    files = {'SKILL.md': data, 'references/help.txt': b'help'} if kind == CapabilityKind.SKILL else {'worker.toml': data}
    if kind == CapabilityKind.SKILL:
        for p, value in files.items():
            asset = root / source / p
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(value)
    else:
        (root / source).parent.mkdir(parents=True, exist_ok=True)
        (root / source).write_bytes(data)
    digest = manifest_digest(files)
    (root / 'evidence').mkdir(exist_ok=True)
    (root / 'evidence/observation.txt').write_text('synthetic observation')
    refs = []
    for evidence_kind in ('validation', 'evaluation'):
        ref = f'evidence/{version}-{evidence_kind}.json'
        write_json(root / ref, dict(schema_version=1, kind=evidence_kind, capability_id='worker', version=version,
            manifest_sha256=digest, passed=True, evidence_refs=['evidence/observation.txt']))
        refs.append(ref)
    return CapabilityRecord(1, 'worker', kind, 'Worker', version, CapabilityState.DRAFT,
        source, target, digest, ['write'], ['local'], [], 'output', ['tool.write'], refs, None, None)


def receipt(record, operation, purpose=ProbePurpose.ACTIVATE, **changes):
    value = NativeProbeReceipt(1, operation, record.id, record.version, record.deployed_sha256,
        purpose, 'synthetic-client', '1', 'session-' + operation, purpose == ProbePurpose.ACTIVATE,
        True if purpose == ProbePurpose.ACTIVATE else None, '2099-01-01T00:00:00Z', ['evidence/observation.txt'])
    return replace(value, **changes)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        write_json(self.root / 'capabilities/catalog.json', to_dict(CapabilityCatalog(1, 1, [])))
    def tearDown(self):
        self.temp.cleanup()
    def test_load_empty_catalog(self):
        self.assertEqual(load_catalog(self.root).revision, 1)
    def test_full_manifest_and_symlinks(self):
        path = self.root / 'tree'
        (path / 'resources').mkdir(parents=True)
        (path / 'SKILL.md').write_bytes(b'skill')
        (path / 'resources/extra').write_bytes(b'extra')
        self.assertEqual(deployment_manifest(path).manifest_sha256,
            manifest_digest({'SKILL.md': b'skill', 'resources/extra': b'extra'}))
        (path / 'resources/link').symlink_to(self.root / 'outside')
        with self.assertRaises(ValidationError): deployment_manifest(path)
    def test_duplicate_ids_fail(self):
        record = candidate(self.root)
        self.assertFalse(validate_catalog(CapabilityCatalog(1, 1, [record, record]), self.root).passed)
    def test_active_without_proof_disabled_and_missing_tools(self):
        record = candidate(self.root)
        catalog = CapabilityCatalog(1, 1, [replace(record, state=CapabilityState.ACTIVE)])
        self.assertFalse(validate_catalog(catalog, self.root).passed)
        self.assertEqual(eligible_capabilities(catalog, {'tool.write'}, self.root), [])
        self.assertEqual(eligible_capabilities(CapabilityCatalog(1, 1, [replace(record, state=CapabilityState.DISABLED)]), {'tool.write'}, self.root), [])
    def test_unsafe_source_and_target(self):
        record = candidate(self.root)
        for bad in ('../outside', '.agents/skills/worker'):
            with self.subTest(path=bad):
                self.assertFalse(validate_catalog(CapabilityCatalog(1, 1, [replace(record, source_path=bad)]), self.root).passed)
        self.assertFalse(validate_catalog(CapabilityCatalog(1, 1, [replace(record, deployed_path='README.md')]), self.root).passed)

    def test_r4_nested_wire_records_are_consumed_as_normalized_contracts(self):
        record = candidate(self.root)
        catalog = CapabilityCatalog(1, 1, [to_dict(record)])
        self.assertTrue(to_dict(catalog))
        self.assertTrue(validate_catalog(catalog, self.root).passed)
        self.assertEqual(eligible_capabilities(catalog, {'tool.write'}, self.root), [])
