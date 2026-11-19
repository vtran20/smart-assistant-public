"""P08 source validation; policy coverage is not native behavioral proof."""
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import tomllib
import unittest

from smart_assistant.agent_lifecycle import stage_agent, validate_agent_definition
from smart_assistant.skill_lifecycle import stage_skill, validate_skill_definition
from smart_assistant.catalog import deployment_manifest
from smart_assistant.contracts import (CapabilityCatalog, CapabilityKind,
    CapabilityRecord, CapabilityState, to_dict)

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / 'examples/agents/engineering-lead.toml'
SKILL = ROOT / 'examples/skills/delegate-work'


class DelegationAssetsTests(unittest.TestCase):
    def test_actual_structural_validators(self):
        for validator, path in ((validate_agent_definition, AGENT),
                                (validate_skill_definition, SKILL)):
            with self.subTest(path=path):
                gate = validator(path)
                self.assertTrue(gate.passed, gate.errors)

    def test_inherited_configuration_and_identity(self):
        value = tomllib.loads(AGENT.read_text())
        self.assertEqual(set(value), {'name', 'description', 'developer_instructions'})
        self.assertEqual(value['name'], 'engineering-lead')
        self.assertTrue((SKILL / 'references/workflow.md').is_file())

    def test_required_policy_coverage_in_lead_and_workflow(self):
        # Requirement anchors detect accidental removal; actual native cases are
        # separate acceptance evidence, never inferred from these source checks.
        lead = tomllib.loads(AGENT.read_text())['developer_instructions'].lower()
        workflow = (SKILL / 'references/workflow.md').read_text().lower()
        anchors = ('two executing specialists', 'nested supervisors', 'exact-file',
                   'preflight', 'eligibility', 'validate_handoff',
                   'taskrecord.blockers', 'independent review', 'combined',
                   'review-only', 'three correction cycles', 'cancelled',
                   'follow-up task', 'failed history', 'draft')
        for text in (lead, workflow):
            for anchor in anchors:
                with self.subTest(anchor=anchor):
                    self.assertIn(anchor, text)
        skill = (SKILL / 'SKILL.md').read_text().lower()
        for boundary in ('use when', 'ordinary', 'unrelated', 'missing', 'small',
                         'references/workflow.md'):
            self.assertIn(boundary, skill)

    def test_private_staging_preserves_draft_and_complete_manifest(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'capabilities').mkdir()
            catalog = root / 'capabilities/catalog.json'
            original = json.dumps(to_dict(CapabilityCatalog(1, 1, [])))
            catalog.write_text(original)
            agent = root / 'examples/engineering-lead.toml'
            agent.parent.mkdir()
            shutil.copyfile(AGENT, agent)
            skill = root / 'examples/delegate-work'
            shutil.copytree(SKILL, skill)
            for identity, kind, source, target, stage in (
                ('engineering-lead', CapabilityKind.AGENT, agent,
                 '.codex/agents/engineering-lead.toml', stage_agent),
                ('delegate-work', CapabilityKind.SKILL, skill,
                 '.agents/skills/delegate-work', stage_skill)):
                record = CapabilityRecord(1, identity, kind, identity, '1.0.0',
                    CapabilityState.DRAFT, str(source.relative_to(root)), target,
                    None, ['bounded delegation'], ['local authorized work'],
                    ['assignment'], 'reviewable handoff', [], [], None, None)
                candidate = stage(root, source, record)
                self.assertEqual(candidate.state, CapabilityState.DRAFT)
                if kind == CapabilityKind.AGENT:
                    self.assertEqual(candidate.validation_refs, [])
                else:
                    self.assertEqual(len(candidate.validation_refs), 1)
                    proof = json.loads((root / candidate.validation_refs[0]).read_text())
                    self.assertEqual(proof["kind"], "validation")
                self.assertIsNone(candidate.discovery_probe_ref)
                manifest = deployment_manifest(root / candidate.source_path)
                expected = 1 if kind == CapabilityKind.AGENT else 2
                self.assertEqual(len(manifest.files), expected)
                if kind == CapabilityKind.SKILL:
                    self.assertTrue(any(f.relative_path.endswith('references/workflow.md')
                                        for f in manifest.files))
                self.assertFalse((root / target).exists())
            self.assertEqual(catalog.read_text(), original)


if __name__ == '__main__':
    unittest.main()
