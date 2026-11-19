"""P09 repository skill bundle references; structural proof, never native proof."""
from pathlib import Path
import shutil
import tempfile
import unittest

from smart_assistant.skill_lifecycle import validate_skill_definition

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('request-coordination', 'manage-agent', 'manage-skill',
          'draft-document', 'verify-completion', 'delegate-work')


class BootstrapResourceTests(unittest.TestCase):
    def test_all_current_bootstrap_and_managed_skill_bundles_validate(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                gate = validate_skill_definition(ROOT / '.agents/skills' / name)
                self.assertTrue(gate.passed, [(e.code, e.message) for e in gate.errors])

    def test_actual_bundle_resources_still_require_existence_and_containment(self):
        for instruction, error in (
            ('Read `references/missing-resource.md`.', 'missing_resource'),
            ('Read [outside](../outside.md).', 'unsafe_path'),
        ):
            with self.subTest(instruction=instruction), tempfile.TemporaryDirectory() as directory:
                skill = Path(directory).resolve() / 'request-coordination'
                shutil.copytree(ROOT / '.agents/skills/request-coordination', skill)
                path = skill / 'SKILL.md'
                path.write_text(path.read_text() + '\n' + instruction + '\n')
                gate = validate_skill_definition(skill)
                self.assertFalse(gate.passed)
                self.assertIn(error, [e.code for e in gate.errors])
                if error == 'missing_resource':
                    self.assertTrue(any('references/missing-resource.md' in e.message
                                        for e in gate.errors))


if __name__ == '__main__':
    unittest.main()
