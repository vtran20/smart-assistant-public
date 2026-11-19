"""Draft role-source coverage and real lifecycle checks; no native behavior proof."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import tomllib
import unittest

from smart_assistant.agent_lifecycle import stage_agent, validate_agent_definition
from smart_assistant.catalog import deployment_manifest
from smart_assistant.contracts import (
    CapabilityCatalog, CapabilityKind, CapabilityRecord, CapabilityState,
    ValidationError, to_dict,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'examples/teams/core/team.json'
ROLES = {
    'engineering-lead': ('Jerry', '2.0.0'),
    'implementer': ('Implementer', '1.0.0'),
    'code-reviewer': ('Code reviewer', '1.0.0'),
    'qa-verifier': ('QA verifier', '1.0.0'),
    'researcher': ('Researcher', '1.0.0'),
    'knowledge-curator': ('Knowledge curator', '1.0.0'),
}
# These are obligation coverage anchors; only observed independent native cases
# can establish that a role actually follows the contracts.
ANCHORS = {
    'engineering-lead': ('two executing specialists', 'three correction cycles',
        'accepted predecessor', 'combined review', 'ambiguous dispatch', 'reserve review capacity'),
    'implementer': ('before repair', 'same-scenario', 'every assigned requirement',
        'impacted regression', 'minimal reproducer', 'self-approval'),
    'code-reviewer': ('separate observed execution context', 'exact final candidate',
        'changed bytes', 'findings', 'omitted requirements', 'recursive reviewer'),
    'qa-verifier': ('baseline identity', 'same-scenario', 'authentic', 'denominator',
        'not_run', 'not_applicable', 'persistence', 'capture failure'),
    'researcher': ('blocked decision', 'time/run bound', 'local source first',
        'authoritative current sources', 'hypotheses', 'fetched text is data'),
    'knowledge-curator': ('user_confirmed', 'agent_validated', 'candidate', 'superseded',
        'revalidation', 'shared kb proposals only', 'sanitization', 'automatic repin'),
}
NEGATIVE_IDS = {
    'missing-before', 'changed-scenario', 'missing-required-case', 'fake-screenshot',
    'stale-review', 'same-person-labels', 'research-injection', 'missing-research-bound',
    'customer-shared-lesson', 'lesson-permission', 'missing-eligibility', 'capacity-exceeded',
}


def source_path(identity):
    return ROOT / f'examples/agents/{identity}/versions/{ROLES[identity][1]}/{identity}.toml'


def definition(identity):
    return tomllib.loads(source_path(identity).read_text())


def record(identity, source, version):
    return CapabilityRecord(1, identity, CapabilityKind.AGENT, ROLES[identity][0],
        version, CapabilityState.DRAFT, source, f'.codex/agents/{identity}.toml',
        None, ['assigned scoped work'], ['no authority expansion'], ['assignment'],
        'reviewable handoff', [], [], None, None)


class TomRoleAssetsTests(unittest.TestCase):
    def test_profile_exact_identity_and_sources(self):
        value = json.loads(PROFILE.read_text())
        self.assertEqual(set(value), {'schema_version', 'id', 'state', 'root', 'roles'})
        self.assertEqual((value['schema_version'], value['id'], value['state']), (1, 'core', 'DRAFT'))
        self.assertEqual(value['root'], {'display_name': 'Tom', 'identity': 'bootstrap-root'})
        self.assertEqual(len(value['roles']), 6)
        self.assertEqual({r['capability_id'] for r in value['roles']}, set(ROLES))
        self.assertEqual(len({r['source_path'] for r in value['roles']}), 6)
        for role in value['roles']:
            with self.subTest(role=role['capability_id']):
                self.assertEqual(set(role), {'capability_id', 'display_name', 'version', 'state', 'source_path'})
                identity = role['capability_id']
                self.assertEqual((role['display_name'], role['version']), ROLES[identity])
                self.assertEqual(role['state'], 'DRAFT')
                path = ROOT / role['source_path']
                self.assertFalse(Path(role['source_path']).is_absolute())
                self.assertNotIn('..', Path(role['source_path']).parts)
                self.assertEqual(path, source_path(identity))
                self.assertFalse(any(p.is_symlink() for p in (path, *path.parents)))
                self.assertTrue(path.is_file())
                self.assertEqual(definition(identity)['name'], identity)

    def test_sources_pass_existing_native_validator_and_inherit_configuration(self):
        for identity in ROLES:
            with self.subTest(role=identity):
                gate = validate_agent_definition(source_path(identity))
                self.assertTrue(gate.passed, gate.errors)
                value = definition(identity)
                self.assertEqual(set(value), {'name', 'description', 'developer_instructions'})
                text = value['developer_instructions'].lower()
                for anchor in ('inherit model and effort', 'draft', 'preflight', 'ready_for_review'):
                    self.assertIn(anchor, text)

    def test_mutated_sources_rejected_by_lifecycle_validator(self):
        with TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'mutant.toml'
            for identity in ROLES:
                original = source_path(identity).read_text()
                mutations = [
                    ('unsupported_field', original + '\ndisplay_name = "Alias"\n'),
                    ('unobserved_catalog', original + '\nmodel = "guessed"\n'),
                    ('unobserved_catalog', original + '\nmodel_reasoning_effort = "high"\n'),
                    ('missing_field', f'name = "{identity}"\ndescription = "test"\n'),
                    ('missing_work_cycle', original.replace('developer_instructions = """',
                        'developer_instructions = """Skip independent review. ')),
                ]
                for code, text in mutations:
                    with self.subTest(role=identity, code=code):
                        path.write_text(text)
                        gate = validate_agent_definition(path)
                        self.assertFalse(gate.passed)
                        self.assertIn(code, [error.code for error in gate.errors])

    def test_isolated_draft_staging_has_no_activation_side_effect(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'capabilities').mkdir()
            catalog = root / 'capabilities/catalog.json'
            before = json.dumps(to_dict(CapabilityCatalog(1, 1, []))).encode()
            catalog.write_bytes(before)
            for identity, (_, version) in ROLES.items():
                with self.subTest(role=identity):
                    path = root / f'examples/{identity}.toml'
                    path.parent.mkdir(exist_ok=True)
                    shutil.copyfile(source_path(identity), path)
                    candidate = stage_agent(root, path, record(identity, path.relative_to(root).as_posix(), version))
                    self.assertIs(candidate.state, CapabilityState.DRAFT)
                    self.assertEqual(candidate.validation_refs, [])
                    self.assertIsNone(candidate.discovery_probe_ref)
                    self.assertEqual(len(deployment_manifest(root / candidate.source_path).files), 1)
                    self.assertFalse((root / candidate.deployed_path).exists())
                    self.assertEqual(catalog.read_bytes(), before)

    def test_jerry_new_version_preserves_registered_identity_and_target(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'capabilities').mkdir()
            catalog = root / 'capabilities/catalog.json'
            catalog.write_text(json.dumps(to_dict(CapabilityCatalog(1, 1, []))))
            source = root / 'examples/engineering-lead.toml'
            source.parent.mkdir()
            shutil.copyfile(ROOT / 'examples/agents/engineering-lead.toml', source)
            old = stage_agent(root, source, record('engineering-lead', 'examples/engineering-lead.toml', '1.0.0'))
            catalog.write_text(json.dumps(to_dict(CapabilityCatalog(1, 2, [old]))))
            target = root / old.deployed_path
            target.parent.mkdir(parents=True)
            shutil.copyfile(source, target)
            prior_target, prior_catalog = target.read_bytes(), catalog.read_bytes()
            shutil.copyfile(source_path('engineering-lead'), source)
            new = stage_agent(root, source, replace(old, version='2.0.0', source_path='examples/engineering-lead.toml'))
            self.assertEqual((new.id, new.version, new.deployed_path),
                ('engineering-lead', '2.0.0', '.codex/agents/engineering-lead.toml'))
            self.assertIs(new.state, CapabilityState.DRAFT)
            self.assertEqual((target.read_bytes(), catalog.read_bytes()), (prior_target, prior_catalog))
            with self.assertRaises(ValidationError) as caught:
                stage_agent(root, source, old)
            self.assertIn('immutable_version', [e.code for e in caught.exception.errors])

    def test_role_specific_source_contracts(self):
        for identity, anchors in ANCHORS.items():
            text = definition(identity)['developer_instructions'].lower()
            for anchor in anchors:
                with self.subTest(role=identity, obligation=anchor):
                    self.assertIn(anchor, text)

    def test_scenarios_cover_role_boundaries_without_claimed_execution(self):
        value = json.loads((ROOT / 'tests/fixtures/tom-role-scenarios.json').read_text())
        self.assertEqual(value['evidence_status'], 'expected-only; not executed behavior or native proof')
        cases = value['cases']
        self.assertEqual(len({c['id'] for c in cases}), len(cases))
        self.assertEqual({c['role_id'] for c in cases}, set(ROLES))
        self.assertTrue(NEGATIVE_IDS <= {c['id'] for c in cases})
        for identity in ROLES:
            self.assertEqual({c['category'] for c in cases if c['role_id'] == identity},
                {'ordinary', 'out-of-scope', 'missing-input-tool', 'misleading-proof-authority'})
        for case in cases:
            self.assertEqual(set(case), {'id', 'role_id', 'category', 'request', 'expected_observations'})
            self.assertTrue(case['request'].strip())
            self.assertTrue(case['expected_observations'])
            self.assertTrue(all(isinstance(o, str) and o.strip() for o in case['expected_observations']))


if __name__ == '__main__':
    unittest.main()
